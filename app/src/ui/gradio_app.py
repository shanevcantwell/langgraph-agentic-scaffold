# In src/ui/gradio_app.py
import gradio as gr
import requests
import json
import base64
from PIL import Image
import io
import argparse # Add this import for argument parsing

# The API endpoints defined in your api.py
API_BASE_URL = "http://127.0.0.1:8000"
INVOKE_URL = f"{API_BASE_URL}/v1/graph/invoke"
STREAM_URL = f"{API_BASE_URL}/v1/graph/stream"

def encode_image_to_base64(image_path):
    """Encodes an image file to a base64 string."""
    if not image_path:
        return None
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def invoke_agent(prompt: str, text_file_path: str, image_path: str):
    """
    Calls the streaming FastAPI backend and yields updates for the UI.
    This function is a generator.
    """
    payload = {"input_prompt": prompt}
    log_history = ""

    if text_file_path:
        try:
            with open(text_file_path.name, "r", encoding="utf-8") as f:
                payload["text_to_process"] = f.read()
        except Exception as e:
            yield {status_output: f"Error reading file: {e}"}
            return

    if image_path:
        payload["image_to_process"] = encode_image_to_base64(image_path.name)
    
    try:
        # Use a single streaming request to get both logs and the final state
        with requests.post(STREAM_URL, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            
            final_state_json = None
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line.startswith("FINAL_STATE::"):
                        final_state_json = decoded_line.replace("FINAL_STATE::", "", 1)
                        break # Stop processing lines after final state is found
                    else:
                        log_history += decoded_line + "\n"
                        yield {log_output: log_history}
        
        if final_state_json:
            final_state = json.loads(final_state_json)
            html_content = final_state.get("html_artifact", "")
            image_ui_output = None
            if image_artifact_b64 := final_state.get("image_artifact_b64"):
                try:
                    img_data = base64.b64decode(image_artifact_b64)
                    image_ui_output = Image.open(io.BytesIO(img_data))
                except Exception as e:
                    log_history += f"\nError decoding image artifact: {e}"
            
            # Final yield with all the completed artifacts
            yield {
                status_output: "Workflow Complete!",
                json_output: final_state,
                html_output: html_content,
                image_output: image_ui_output,
                log_output: log_history
            }

    except requests.exceptions.RequestException as e:
        yield {status_output: f"API Error: {e}", log_output: log_history + f"\nERROR: {e}"}

def main():
    """Parses command-line arguments and launches the Gradio app."""
    # --- New Argument Parsing Logic ---
    parser = argparse.ArgumentParser(description="Gradio UI for the Agentic System")
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the Gradio app on."
    )
    args = parser.parse_args()
    
    # --- Gradio UI Definition ---
    with gr.Blocks(theme=gr.themes.Soft(), title="Agentic System UI") as demo:
        # (The UI definition remains unchanged)
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
                    with gr.TabItem("Rendered HTML Artifact"):
                        html_output = gr.HTML()

                    with gr.TabItem("Generated Image Artifact"):
                        image_output = gr.Image(label="Generated Image")
                    with gr.TabItem("Full JSON Response"):
                        json_output = gr.JSON()

        submit_button.click(
            fn=invoke_agent,
            inputs=[prompt_input, file_input, image_input],
            outputs=[status_output, json_output, html_output, image_output, log_output]
        )
    
    print(f"Launching Gradio UI on port {args.port}...")
    demo.launch(server_port=args.port)

# --- Standard Python entry point ---
if __name__ == "__main__":
    main()