# app/src/ui/gradio_lassi.py
"""
L.A.S.S.I. UI - LangGraph-Agentic-Scaffold Selected Interface
Dark mode with warm glowing mango accents.
"""
import gradio as gr
import argparse
import html
from .api_client import ApiClient

# --- CSS for Mango Lassi Theme (Dark Mode) ---
LASSI_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Lato:wght@400;700&display=swap');

/* === Base & Color Palette === */
:root {
    --bg-color: #1A1410; /* Deep Mango Brown */
    --card-bg: #2A1F16;
    --primary-accent: #FF9F40; /* Glowing Mango */
    --primary-accent-dark: #FFB366;
    --secondary-accent: #3D2A1A; /* Rich Brown */
    --text-color: #F5E6D3; /* Cream (high contrast on dark) */
    --text-color-light: #C9A882;
    --border-color: #4D3820;
    --font-ui: 'Lato', sans-serif;
}

/* === Base Theme Overrides === */
.gradio-container {
    font-family: var(--font-ui) !important;
    background: var(--bg-color) !important;
    color: var(--text-color) !important;
}

/* === Layout & Cards === */
.gradio-container .panel { /* Base for gr.Group */
    background: var(--card-bg) !important;
    border: 2px solid var(--border-color) !important;
    border-radius: 16px !important;
    box-shadow: 0 0 20px rgba(255, 159, 64, 0.1) !important;
}

/* === Headers === */
.gradio-container h1, .gradio-container h2, .gradio-container h3 {
    color: var(--text-color) !important;
    font-family: var(--font-ui) !important;
    font-weight: 700 !important;
}

/* === Readout Panel (Clean Stats) === */
.readout-panel {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    background: var(--card-bg) !important;
    border: 2px solid var(--border-color) !important;
    border-radius: 16px !important;
    padding: 16px !important;
    margin-bottom: 16px !important;
    box-shadow: 0 0 20px rgba(255, 159, 64, 0.15) !important;
}
.readout { text-align: left; }
.readout-label {
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: var(--text-color-light) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 4px !important;
}
.readout-value {
    font-size: 2.5rem !important;
    font-weight: 700 !important;
    color: var(--primary-accent) !important;
    line-height: 1 !important;
    text-shadow: 0 0 15px rgba(255, 159, 64, 0.6) !important;
}

/* === Input Fields === */
.gradio-container textarea,
.gradio-container input[type="text"] {
    background: var(--card-bg) !important;
    color: var(--text-color) !important;
    border: 2px solid var(--border-color) !important;
    border-radius: 12px !important;
    font-size: 1rem !important;
    font-family: var(--font-ui) !important;
}
.gradio-container textarea:focus,
.gradio-container input[type="text"]:focus {
    border-color: var(--primary-accent) !important;
    box-shadow: 0 0 10px rgba(255, 159, 64, 0.5) !important;
}

/* === Buttons === */
.gradio-container button.gradio-button.primary {
    background: var(--primary-accent) !important;
    color: #1A1410 !important;
    border: none !important;
    border-radius: 12px !important;
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 0 20px rgba(255, 159, 64, 0.4) !important;
}
.gradio-container button.gradio-button.primary:hover {
    background: var(--primary-accent-dark) !important;
    box-shadow: 0 0 30px rgba(255, 179, 102, 0.6) !important;
    transform: translateY(-2px) !important;
}
.gradio-container button.gradio-button.primary:active {
    transform: translateY(0) !important;
    box-shadow: 0 0 20px rgba(255, 159, 64, 0.4) !important;
}

/* === Tabs === */
.gradio-container .tab-nav button {
    background: none !important;
    color: var(--text-color-light) !important;
    border: none !important;
    border-bottom: 3px solid transparent !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    border-radius: 0 !important;
}
.gradio-container .tab-nav button.selected {
    color: var(--primary-accent) !important;
    border-bottom-color: var(--primary-accent) !important;
    text-shadow: 0 0 10px rgba(255, 159, 64, 0.5) !important;
}

/* === Checkboxes === */
.gradio-container input[type="checkbox"] {
    accent-color: var(--primary-accent) !important;
    width: 20px !important;
    height: 20px !important;
}
.gradio-container .info { /* Checkbox info text */
    color: var(--text-color-light) !important;
    font-size: 0.9rem !important;
}

/* === File Upload === */
.gradio-container .file-preview {
    background: var(--card-bg) !important;
    border: 2px dashed var(--primary-accent) !important;
    border-radius: 12px !important;
    color: var(--text-color) !important;
}

/* === JSON/Markdown Output === */
.gradio-container .json-holder,
.gradio-container .markdown {
    background: var(--card-bg) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 12px !important;
    padding: 12px !important;
}
.gradio-container .markdown {
    color: var(--text-color) !important;
    font-size: 1rem !important;
}
.gradio-container .markdown pre {
    background: var(--secondary-accent) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-color) !important;
}
.gradio-container .markdown code {
    background: var(--secondary-accent) !important;
    color: var(--primary-accent) !important;
    border-radius: 4px !important;
    padding: 2px 6px !important;
    border: 1px solid var(--border-color) !important;
}
"""


def handle_submit(api_client: ApiClient, status_output, turn_counter, latency_display, specialist_ticker, log_output, json_output, html_output, image_output, archive_output):
    """
    Returns a closure for handling the Gradio submit event with L.A.S.S.I. UI updates.
    (This logic is identical to gradio_vegas, just driving a different UI)
    """
    turn_count = 0

    async def _handle_submit_closure(prompt: str, text_file: object, image_file: object, use_simple_chat: bool):
        """Generator function to handle the streaming UI updates."""
        nonlocal turn_count

        if not prompt.strip() and not text_file and not image_file:
            yield {status_output: "Please provide a prompt or a file to begin."}
            return

        turn_count += 1
        specialist_log = []
        log_text = ""

        # Reset UI
        yield {
            status_output: "► Invoking Agent...",
            turn_counter: str(turn_count).zfill(2),
            latency_display: "0",
            specialist_ticker: "---",
            log_output: "---",
            archive_output: "...",
            json_output: {}
        }

        async for update in api_client.invoke_agent_streaming(prompt, text_file, image_file, use_simple_chat):
            ui_update = {}

            # Update status
            if "status" in update:
                ui_update[status_output] = f"► {update['status']}"

            # Mock latency
            if "logs" in update:
                ui_update[latency_display] = "42" # Mock

            # Track specialist activity
            if "logs" in update:
                log_text = update["logs"]
                # Extract specialist execution and routing events
                if "---" in log_text or "→" in log_text or "Routing to" in log_text:
                    # Get the last meaningful line
                    lines = [l.strip() for l in log_text.split('\n') if l.strip()]
                    if lines:
                        specialist_log.append(lines[-1])
                        ticker_text = "\n".join(specialist_log[-15:])  # Last 15 entries
                        ui_update[specialist_ticker] = ticker_text
                ui_update[log_output] = log_text

            # Update final state
            if "final_state" in update:
                ui_update[json_output] = update["final_state"]
            if "html" in update:
                html_content = update["html"]
                if html_content:
                    iframe_html = f'<iframe srcdoc="{html.escape(html_content if isinstance(html_content, str) else "")}" style="width: 100%; height: 600px; border: none;"></iframe>'
                    ui_update[html_output] = gr.update(value=iframe_html, visible=True)
                else:
                    ui_update[html_output] = gr.update(value="", visible=False)
            if "image" in update:
                ui_update[image_output] = gr.update(value=update["image"], visible=bool(update["image"]))
            if "archive" in update:
                ui_update[archive_output] = update["archive"]

            # Show error report if present
            if "error" in update or "error_report" in update:
                error_msg = update.get("error", "Unknown error")
                error_report = update.get("error_report", "")

                # Show error in status
                ui_update[status_output] = f"❌ ERROR: {error_msg}"

                # Show full error report in archive tab
                if error_report:
                    ui_update[archive_output] = f"## ❌ Error Report\n\n{error_report}"

            if ui_update:
                yield ui_update
        
        yield {status_output: "✅ Workflow Complete."}

    return _handle_submit_closure


def create_ui(api_client: ApiClient):
    """Creates the L.A.S.S.I. Gradio UI with dark mode and glowing mango accents."""
    with gr.Blocks(theme=gr.themes.Soft(), title="L.A.S.S.I. Interface", css=LASSI_CSS) as demo:

        # Header
        gr.Markdown("# 🥭 L.A.S.S.I. Interface")
        gr.Markdown("**LangGraph-Agentic-Scaffold Selected Interface**")

        with gr.Row(equal_height=False):
            # === LEFT COLUMN: Command Input & Files ===
            with gr.Column(scale=2):
                with gr.Group():
                    gr.Markdown("### 💬 Command Bar")
                    prompt_input = gr.Textbox(
                        label="Your Prompt",
                        show_label=False,
                        lines=5,
                        placeholder="Enter your prompt here...",
                        submit_btn=True
                    )
                    simple_chat_checkbox = gr.Checkbox(
                        label="Simple Chat Mode",
                        value=False,
                        info="Enable for faster, single-perspective responses."
                    )
                    submit_button = gr.Button("Invoke Agent", variant="primary")

                with gr.Group():
                    gr.Markdown("### 📂 File Staging")
                    with gr.Row():
                        file_input = gr.File(label="Upload Text File")
                        image_input = gr.Image(type="filepath", label="Upload Image")

            # === RIGHT COLUMN: Agent Output & Monitors ===
            with gr.Column(scale=3):
                with gr.Group():
                    gr.Markdown("### 📊 System Readouts")
                    with gr.Row(elem_classes="readout-panel"):
                        with gr.Column(elem_classes="readout"):
                            gr.Markdown('<div class="readout-label">Turn Count</div>', elem_classes="readout-label")
                            turn_counter = gr.Textbox(value="0", show_label=False, interactive=False, elem_classes="readout-value")
                        with gr.Column(elem_classes="readout"):
                            gr.Markdown('<div class="readout-label">Latency (ms)</div>', elem_classes="readout-label")
                            latency_display = gr.Textbox(value="0", show_label=False, interactive=False, elem_classes="readout-value")
                
                with gr.Group():
                    gr.Markdown("### Monitor")
                    status_output = gr.Textbox(label="Current Status", interactive=False)
                    specialist_ticker = gr.Textbox(
                        label="Specialist Routing",
                        lines=4,
                        interactive=False
                    )
                    log_output = gr.Textbox(label="Agent Log", lines=8, interactive=False)
                
                with gr.Group():
                    gr.Markdown("### 📦 Artifacts")
                    with gr.Tabs():
                        with gr.TabItem("Archive Report"):
                            archive_output = gr.Markdown()
                        with gr.TabItem("Final State (JSON)"):
                            json_output = gr.JSON()
                        with gr.TabItem("Rendered HTML"):
                            html_output = gr.HTML()
                        with gr.TabItem("Generated Image"):
                            image_output = gr.Image(label="Generated Image", visible=False)

        # Create the handler function
        submit_handler = handle_submit(
            api_client, status_output, turn_counter, latency_display,
            specialist_ticker, log_output, json_output, html_output,
            image_output, archive_output
        )

        # Wire up events
        submit_inputs = [prompt_input, file_input, image_input, simple_chat_checkbox]
        submit_outputs = [status_output, turn_counter, latency_display, specialist_ticker, log_output, json_output, html_output, image_output, archive_output]

        submit_button.click(fn=submit_handler, inputs=submit_inputs, outputs=submit_outputs)
        prompt_input.submit(fn=submit_handler, inputs=submit_inputs, outputs=submit_outputs)

    return demo


def main():
    """Parses command-line arguments and launches the L.A.S.S.I. Gradio app."""
    parser = argparse.ArgumentParser(description="L.A.S.S.I. UI for the Agentic System")
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the Gradio app on."
    )
    args = parser.parse_args()

    api_client = ApiClient()
    demo = create_ui(api_client)

    print(f"🥭 Launching L.A.S.S.I. Interface on port {args.port}...")
    demo.launch(server_port=args.port, server_name="0.0.0.0")


if __name__ == "__main__":
    main()