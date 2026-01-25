# In src/ui/gradio_app.py
import gradio as gr
import argparse
import sys
import os

import html
from .api_client import ApiClient

def handle_submit(api_client: ApiClient, status_output, json_output, html_output, image_output, log_output, archive_output, clarification_row, clarification_input, clarification_thread_id):
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

            # ADR-CORE-042: Handle interrupt events ("Raise Hand" pattern)
            if "interrupt" in update:
                interrupt_data = update["interrupt"]
                thread_id = update.get("thread_id")
                questions = interrupt_data.get("questions", [])

                # Format questions for display
                question_lines = []
                for q in questions:
                    if isinstance(q, dict):
                        question_lines.append(f"• {q.get('question', 'Unknown question')}")
                        if q.get('reason'):
                            question_lines.append(f"  ({q['reason']})")
                    else:
                        question_lines.append(f"• {q}")
                question_text = "\n".join(question_lines)

                # Show clarification UI
                ui_update[status_output] = f"🙋 Clarification needed:\n{question_text}"
                ui_update[clarification_row] = gr.update(visible=True)
                ui_update[clarification_input] = gr.update(value="", placeholder="Enter your clarification...")
                ui_update[clarification_thread_id] = thread_id
                yield ui_update
                return  # Stop streaming - wait for clarification submission

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


def handle_clarification(api_client: ApiClient, status_output, json_output, html_output, image_output, log_output, archive_output, clarification_row, clarification_input, clarification_thread_id):
    """
    ADR-CORE-042: Handler for clarification submission.
    Resumes the interrupted workflow with user's response.
    """
    async def _handle_clarification_closure(user_input: str, thread_id: str):
        """Resume workflow with user's clarification."""
        if not user_input.strip():
            yield {status_output: "Please enter your clarification."}
            return

        if not thread_id:
            yield {status_output: "Error: No pending clarification (missing thread_id)."}
            return

        # Hide clarification row, show resuming status
        yield {
            clarification_row: gr.update(visible=False),
            status_output: "Resuming workflow with your clarification..."
        }

        # Resume the workflow
        async for update in api_client.resume_workflow(thread_id, user_input):
            ui_update = {}

            # Check for another interrupt (recursive clarification)
            if "interrupt" in update:
                interrupt_data = update["interrupt"]
                new_thread_id = update.get("thread_id")
                questions = interrupt_data.get("questions", [])

                question_lines = []
                for q in questions:
                    if isinstance(q, dict):
                        question_lines.append(f"• {q.get('question', 'Unknown question')}")
                        if q.get('reason'):
                            question_lines.append(f"  ({q['reason']})")
                    else:
                        question_lines.append(f"• {q}")
                question_text = "\n".join(question_lines)

                ui_update[status_output] = f"🙋 Follow-up clarification needed:\n{question_text}"
                ui_update[clarification_row] = gr.update(visible=True)
                ui_update[clarification_input] = gr.update(value="", placeholder="Enter your clarification...")
                ui_update[clarification_thread_id] = new_thread_id
                yield ui_update
                return

            if "status" in update:
                ui_update[status_output] = update["status"]
            if "logs" in update:
                ui_update[log_output] = update["logs"]
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

            if ui_update:
                yield ui_update

    return _handle_clarification_closure

def create_ui(api_client: ApiClient):
    """Creates the Gradio UI and wires up the components."""
    # Custom JavaScript to make Enter=submit, Shift+Enter=newline (standard AI chat behavior)
    custom_js = """
    function setupEnterKeyBehavior() {
        const textareas = document.querySelectorAll('textarea[data-testid="textbox"]');
        textareas.forEach(textarea => {
            if (textarea.hasAttribute('data-enter-fixed')) return;
            textarea.setAttribute('data-enter-fixed', 'true');
            textarea.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const submitBtn = textarea.closest('.gradio-container').querySelector('button[aria-label="Submit"]') ||
                                     textarea.parentElement.parentElement.querySelector('button.primary');
                    if (submitBtn) submitBtn.click();
                }
            });
        });
    }
    setTimeout(setupEnterKeyBehavior, 100);
    """

    with gr.Blocks(theme=gr.themes.Soft(), title="Agentic System UI", js=custom_js) as demo:
        gr.Markdown("# Agentic System Testing UI")
        gr.Markdown("Interact with the agent by providing a prompt and optional files.")

        with gr.Row():
            with gr.Column(scale=2):
                prompt_input = gr.Textbox(
                    label="Your Prompt",
                    lines=3,
                    placeholder="e.g., Describe the attached image... (Enter to submit, Shift+Enter for new line)",
                    elem_id="prompt_input"
                )
                with gr.Row():
                    file_input = gr.File(label="Upload Text File", visible=False)  # Disabled pending Dockyard/MCP integration (ADR-MCP-002)
                    image_input = gr.Image(type="pil", label="Upload Image", visible=False)  # Disabled pending Dockyard/MCP integration (ADR-MCP-002)
                simple_chat_checkbox = gr.Checkbox(
                    label="Simple Chat Mode",
                    value=False,
                    info="Enable for faster, single-perspective responses. Disable (default) for parallel progenitor analysis."
                )
                submit_button = gr.Button("▶️ Invoke Agent", variant="primary")

                # ADR-CORE-042: Clarification UI (hidden until interrupt)
                with gr.Row(visible=False) as clarification_row:
                    with gr.Column():
                        gr.Markdown("### 🙋 Clarification Needed")
                        clarification_input = gr.Textbox(
                            label="Your Answer",
                            lines=2,
                            placeholder="Enter your clarification..."
                        )
                        clarification_submit = gr.Button("Submit Clarification", variant="secondary")
                clarification_thread_id = gr.State(value=None)  # Stores pending thread_id

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
            api_client, status_output, json_output, html_output, image_output, log_output, archive_output,
            clarification_row, clarification_input, clarification_thread_id
        )

        # Wire up both button click and Enter key submission
        submit_inputs = [prompt_input, file_input, image_input, simple_chat_checkbox]
        submit_outputs = [status_output, json_output, html_output, image_output, log_output, archive_output,
                         clarification_row, clarification_input, clarification_thread_id]

        submit_button.click(fn=submit_handler, inputs=submit_inputs, outputs=submit_outputs)
        prompt_input.submit(fn=submit_handler, inputs=submit_inputs, outputs=submit_outputs)

        # ADR-CORE-042: Wire up clarification handler
        clarification_handler = handle_clarification(
            api_client, status_output, json_output, html_output, image_output, log_output, archive_output,
            clarification_row, clarification_input, clarification_thread_id
        )
        clarification_inputs = [clarification_input, clarification_thread_id]
        clarification_outputs = [status_output, json_output, html_output, image_output, log_output, archive_output,
                                 clarification_row, clarification_input, clarification_thread_id]
        clarification_submit.click(fn=clarification_handler, inputs=clarification_inputs, outputs=clarification_outputs)

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