# In src/ui/gradio_app.py
import gradio as gr
import argparse
import sys
import os

import html
from .api_client import ApiClient

# --- Pip-Boy M-II Theme CSS ---
PIPBOY_CSS = """
/* Import Fonts */
@import url('https://fonts.googleapis.com/css2?family=VT323&family=Oswald:wght@400;700&display=swap');

/* Pip-Boy theme - only applies when .pipboy-theme class is present */
.pipboy-theme {
    --bg-color: #1a1a1a;
    --screen-bg: #0a1a0a;
    --screen-text: #00e021;
    --screen-text-glow: 0 0 5px var(--screen-text);
    --glow-color: #00ff41;
    --glow-shadow: 0 0 5px var(--glow-color), 0 0 10px var(--glow-color);
    --accent-color: #008a12;
    --accent-light: #a0c0a0;
    --font-ui: 'Oswald', sans-serif;
    --font-screen: 'VT323', monospace;

    /* Gradio overrides */
    --body-background-fill: var(--bg-color) !important;
    --body-text-color: var(--accent-light) !important;
    --input-background-fill: var(--screen-bg) !important;
    --input-border-color: var(--accent-color) !important;
    --input-text-color: var(--screen-text) !important;
    --button-primary-background-fill: var(--accent-color) !important;
    --button-primary-background-fill-hover: var(--glow-color) !important;
    --button-primary-text-color: var(--bg-color) !important;
    --panel-background-fill: #2a2a2a !important;
}

.pipboy-theme h1, .pipboy-theme h2 {
    color: var(--glow-color) !important;
    text-shadow: var(--glow-shadow) !important;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-family: var(--font-ui) !important;
}

.pipboy-theme .crt-screen,
.pipboy-theme textarea,
.pipboy-theme .prose {
    background: var(--screen-bg) !important;
    color: var(--screen-text) !important;
    font-family: var(--font-screen) !important;
    font-size: 1.1rem !important;
    border: 3px solid #000 !important;
    border-radius: 10px !important;
    box-shadow: inset 0 0 15px #000 !important;
    text-shadow: var(--screen-text-glow) !important;
    position: relative;
}

/* CRT scanline effect */
.pipboy-theme textarea::before {
    content: " ";
    display: block;
    position: absolute;
    top: 0; left: 0; bottom: 0; right: 0;
    background: linear-gradient(rgba(0, 255, 65, 0.1) 50%, transparent 50%);
    background-size: 100% 3px;
    animation: scanlines 10s linear infinite;
    pointer-events: none;
    z-index: 10;
}

@keyframes scanlines {
    from { background-position: 0 0; }
    to { background-position: 0 90px; }
}

.pipboy-theme button {
    font-family: var(--font-ui) !important;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Theme toggle styling */
.theme-toggle {
    position: fixed;
    top: 10px;
    right: 10px;
    z-index: 1000;
    background: rgba(0,0,0,0.7);
    padding: 8px 12px;
    border-radius: 5px;
    border: 1px solid #666;
}

.theme-toggle label {
    color: #fff !important;
    font-size: 0.9rem;
}
"""

def handle_submit(api_client: ApiClient, status_output, json_output, html_output, image_output, log_output, archive_output):
    """
    Returns a closure for handling the Gradio submit event.
    This structure makes the core logic testable independently of the Gradio UI components.
    """
    async def _handle_submit_closure(prompt: str, text_file: object, image_file: object, use_simple_chat: bool):
        """Generator function to handle the streaming UI updates."""
        if not prompt.strip():
            yield {status_output: "Please enter a prompt."}
            return

        # In modern Gradio, we build the update dictionary dynamically.
        # We use `async for` because invoke_agent_streaming is an async generator.
        async for update in api_client.invoke_agent_streaming(prompt, text_file, image_file, use_simple_chat): # text_file and image_file are Gradio file objects
            ui_update = {}
            if "status" in update:
                ui_update[status_output] = update["status"]
            if "logs" in update:
                ui_update[log_output] = update["logs"]
            if "final_state" in update:
                ui_update[json_output] = update["final_state"]
            if "html" in update:
                html_content = update["html"]
                if html_content:
                    # Ensure we only escape raw strings, not Gradio update objects
                    iframe_html = f'<iframe srcdoc="{html.escape(html_content if isinstance(html_content, str) else "")}" style="width: 100%; height: 600px; border: none;"></iframe>'
                    ui_update[html_output] = gr.update(value=iframe_html, visible=True)
                else:
                    ui_update[html_output] = gr.update(value="", visible=False)
            if "image" in update:
                ui_update[image_output] = gr.update(value=update["image"], visible=bool(update["image"]))
            if "archive" in update:
                ui_update[archive_output] = update["archive"]
            
            if ui_update:
                yield ui_update
    
    return _handle_submit_closure

def create_ui(api_client: ApiClient):
    """Creates the Gradio UI and wires up the components."""
    with gr.Blocks(theme=gr.themes.Soft(), title="Agentic System UI", css=PIPBOY_CSS) as demo:
        # Theme toggle
        with gr.Row(elem_classes="theme-toggle"):
            theme_toggle = gr.Radio(
                choices=["Standard", "Pip-Boy M-II"],
                value="Standard",
                label="UI Theme",
                interactive=True,
            )

        gr.Markdown("# Agentic System Testing UI")
        gr.Markdown("Interact with the agent by providing a prompt and optional files.")

        with gr.Row():
            with gr.Column(scale=2):
                prompt_input = gr.Textbox(
                    label="Your Prompt",
                    lines=3,
                    placeholder="e.g., Describe the attached image... (Press Enter to submit, Shift+Enter for new line)",
                    submit_btn=True
                )
                with gr.Row():
                    file_input = gr.File(label="Upload Text File")
                    image_input = gr.Image(type="pil", label="Upload Image")
                simple_chat_checkbox = gr.Checkbox(
                    label="Simple Chat Mode",
                    value=False,
                    info="Enable for faster, single-perspective responses. Disable (default) for parallel progenitor analysis."
                )
                submit_button = gr.Button("▶️ Invoke Agent", variant="primary")
    
            with gr.Column(scale=3):
                status_output = gr.Textbox(label="Status", interactive=False)
                log_output = gr.Textbox(label="Agent Log", lines=10, interactive=False)
                with gr.Tabs():
                    with gr.TabItem("🌐 Rendered HTML"):
                        html_output = gr.HTML()
                    with gr.TabItem("🖼️ Generated Image"):
                        image_output = gr.Image(label="Generated Image", visible=False)
                    with gr.TabItem("🗄️ Archive Report"):
                        archive_output = gr.Markdown()
                    with gr.TabItem("⚙️ Final State (JSON)"):
                        json_output = gr.JSON()
        
        # Create the handler function by passing the UI components to our testable function
        submit_handler = handle_submit(
            api_client, status_output, json_output, html_output, image_output, log_output, archive_output
        )

        # Wire up both button click and Enter key submission
        submit_inputs = [prompt_input, file_input, image_input, simple_chat_checkbox]
        submit_outputs = [status_output, json_output, html_output, image_output, log_output, archive_output]

        submit_button.click(fn=submit_handler, inputs=submit_inputs, outputs=submit_outputs)
        prompt_input.submit(fn=submit_handler, inputs=submit_inputs, outputs=submit_outputs)

        # Wire up theme toggle
        theme_toggle.change(
            fn=None,
            inputs=[theme_toggle],
            outputs=None,
            js="""
            (theme) => {
                const container = document.querySelector('.gradio-container');
                if (theme === 'Pip-Boy M-II') {
                    container.classList.add('pipboy-theme');
                    document.title = 'L.A.S. Interface - Pip-Boy M-II';
                } else {
                    container.classList.remove('pipboy-theme');
                    document.title = 'Agentic System UI';
                }
                return null;
            }
            """
        )

    return demo

def main():
    """Parses command-line arguments and launches the Gradio app."""
    parser = argparse.ArgumentParser(description="Gradio UI for the Agentic System")
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the Gradio app on."
    )
    args = parser.parse_args()

    api_client = ApiClient()
    demo = create_ui(api_client)

    print(f"Launching Gradio UI on port {args.port}...")
    demo.launch(server_port=args.port,server_name="0.0.0.0")

if __name__ == "__main__":
    main()