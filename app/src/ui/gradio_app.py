# In src/ui/gradio_app.py
import gradio as gr
import argparse
import sys
import os

from .api_client import ApiClient

def handle_submit(api_client: ApiClient, status_output, json_output, html_output, image_output, log_output, archive_output):
    """
    Returns a closure for handling the Gradio submit event.
    This structure makes the core logic testable independently of the Gradio UI components.
    """
    async def _handle_submit_closure(prompt: str, text_file: object, image_file: object):
        """Generator function to handle the streaming UI updates."""
        if not prompt.strip():
            yield {status_output: "Please enter a prompt."}
            return

        # In modern Gradio, we build the update dictionary dynamically.
        # We use `async for` because invoke_agent_streaming is an async generator.
        async for update in api_client.invoke_agent_streaming(prompt, text_file, image_file): # text_file and image_file are Gradio file objects
            ui_update = {}
            if "status" in update:
                ui_update[status_output] = update["status"]
            if "logs" in update:
                ui_update[log_output] = update["logs"]
            if "final_state" in update:
                ui_update[json_output] = update["final_state"]
            if "html" in update:
                ui_update[html_output] = gr.update(value=update["html"], visible=bool(update["html"]))
            if "image" in update:
                ui_update[image_output] = gr.update(value=update["image"], visible=bool(update["image"]))
            if "archive" in update:
                ui_update[archive_output] = update["archive"]
            
            if ui_update:
                yield ui_update
    
    return _handle_submit_closure

def create_ui(api_client: ApiClient):
    """Creates the Gradio UI and wires up the components."""
    with gr.Blocks(theme=gr.themes.Soft(), title="Agentic System UI") as demo:
        gr.Markdown("# Agentic System Testing UI")
        gr.Markdown("Interact with the agent by providing a prompt and optional files.")
        
        with gr.Row():
            with gr.Column(scale=2):
                prompt_input = gr.Textbox(label="Your Prompt", lines=3, placeholder="e.g., Describe the attached image...")
                with gr.Row():
                    file_input = gr.File(label="Upload Text File")
                    image_input = gr.Image(type="pil", label="Upload Image")
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
        
        submit_button.click(
            fn=submit_handler,
            inputs=[prompt_input, file_input, image_input],
            outputs=[status_output, json_output, html_output, image_output, log_output, archive_output]
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
    demo.launch(server_port=args.port)

if __name__ == "__main__":
    main()