# app/src/ui/gradio_vegas.py
"""
VEGAS UI - LangGraph-Agentic-Scaffold Selected Interface
Retro terminal UI with NIXIE readouts and CRT effects
"""
import gradio as gr
import argparse
import html
from .api_client import ApiClient

VEGAS_CSS = """
@import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');

/* === Base Terminal Styling === */
.gradio-container {
    font-family: 'VT323', monospace !important;
    background: #0a0a0a !important;
    color: #33ff33 !important;
}

/* CRT Screen Effect */
.gradio-container::before {
    content: '';
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
        rgba(18, 16, 16, 0) 50%,
        rgba(0, 0, 0, 0.1) 50%
    );
    background-size: 100% 6px;
    z-index: 999;
    pointer-events: none;
    animation: scanline 18s linear infinite;
}

@keyframes scanline {
    0% { background-position: 0 0; }
    100% { background-position: 0 100%; }
}

/* CRT Curvature & Glow */
.gradio-container {
    border-radius: 20px;
    box-shadow:
        inset 0 0 100px rgba(51, 255, 51, 0.1),
        0 0 50px rgba(51, 255, 51, 0.2);
}

/* === NIXIE Tube Readouts === */
.nixie-panel {
    background: linear-gradient(180deg, #1a1a1a 0%, #0d0d0d 100%) !important;
    border: 2px solid #33ff33 !important;
    border-radius: 8px !important;
    padding: 12px !important;
    box-shadow:
        0 0 20px rgba(51, 255, 51, 0.3),
        inset 0 0 10px rgba(0, 0, 0, 0.8) !important;
    font-family: 'VT323', monospace !important;
    margin-bottom: 16px !important;
}

.nixie-label {
    color: #33ff33 !important;
    font-size: 18px !important;
    text-transform: uppercase !important;
    letter-spacing: 2px !important;
    margin-bottom: 8px !important;
    text-shadow: 0 0 10px rgba(51, 255, 51, 0.8) !important;
}

.nixie-value {
    color: #ff9933 !important;
    font-size: 48px !important;
    font-weight: bold !important;
    text-shadow:
        0 0 20px rgba(255, 153, 51, 0.8),
        0 0 40px rgba(255, 153, 51, 0.4) !important;
    font-variant-numeric: tabular-nums !important;
    letter-spacing: 8px !important;
}

/* === Specialist Ticker === */
.specialist-ticker {
    background: #0d0d0d !important;
    border: 2px solid #33ff33 !important;
    border-radius: 8px !important;
    padding: 16px !important;
    min-height: 200px !important;
    max-height: 400px !important;
    overflow-y: auto !important;
    box-shadow:
        0 0 20px rgba(51, 255, 51, 0.3),
        inset 0 0 10px rgba(0, 0, 0, 0.8) !important;
}

.specialist-ticker::-webkit-scrollbar {
    width: 12px;
}

.specialist-ticker::-webkit-scrollbar-track {
    background: #0a0a0a;
    border: 1px solid #33ff33;
}

.specialist-ticker::-webkit-scrollbar-thumb {
    background: #33ff33;
    box-shadow: 0 0 10px rgba(51, 255, 51, 0.8);
}

/* === Terminal Text Areas === */
.gradio-container textarea,
.gradio-container input[type="text"] {
    background: #0d0d0d !important;
    color: #33ff33 !important;
    border: 2px solid #33ff33 !important;
    font-family: 'VT323', monospace !important;
    font-size: 20px !important;
    border-radius: 8px !important;
    box-shadow:
        0 0 15px rgba(51, 255, 51, 0.2),
        inset 0 0 10px rgba(0, 0, 0, 0.8) !important;
}

.gradio-container textarea::placeholder {
    color: #226622 !important;
}

/* === Buttons === */
.gradio-container button {
    background: linear-gradient(180deg, #1a4d1a 0%, #0d260d 100%) !important;
    color: #33ff33 !important;
    border: 2px solid #33ff33 !important;
    font-family: 'VT323', monospace !important;
    font-size: 22px !important;
    text-transform: uppercase !important;
    letter-spacing: 2px !important;
    border-radius: 8px !important;
    box-shadow:
        0 0 20px rgba(51, 255, 51, 0.3),
        inset 0 0 10px rgba(0, 0, 0, 0.5) !important;
    transition: all 0.2s ease !important;
}

.gradio-container button:hover {
    background: linear-gradient(180deg, #267326 0%, #133d13 100%) !important;
    box-shadow:
        0 0 30px rgba(51, 255, 51, 0.6),
        inset 0 0 15px rgba(0, 0, 0, 0.5) !important;
    transform: translateY(-2px) !important;
}

.gradio-container button:active {
    transform: translateY(0) !important;
    box-shadow:
        0 0 15px rgba(51, 255, 51, 0.4),
        inset 0 0 20px rgba(0, 0, 0, 0.7) !important;
}

/* === Labels === */
.gradio-container label {
    color: #33ff33 !important;
    font-family: 'VT323', monospace !important;
    font-size: 22px !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    text-shadow: 0 0 8px rgba(51, 255, 51, 0.6) !important;
}

/* === Tabs === */
.gradio-container .tab-nav button {
    background: #0d0d0d !important;
    color: #33ff33 !important;
    border: 2px solid #33ff33 !important;
    border-radius: 8px 8px 0 0 !important;
}

.gradio-container .tab-nav button.selected {
    background: #1a4d1a !important;
    box-shadow: 0 0 20px rgba(51, 255, 51, 0.5) !important;
}

/* === Checkboxes === */
.gradio-container input[type="checkbox"] {
    accent-color: #33ff33 !important;
    width: 24px !important;
    height: 24px !important;
}

/* === File Upload === */
.gradio-container .file-preview {
    background: #0d0d0d !important;
    border: 2px dashed #33ff33 !important;
    border-radius: 8px !important;
    color: #33ff33 !important;
}

/* === JSON Output === */
.gradio-container .json-holder {
    background: #0d0d0d !important;
    color: #33ff33 !important;
    font-family: 'VT323', monospace !important;
}

/* === Headers === */
.gradio-container h1,
.gradio-container h2,
.gradio-container h3 {
    color: #33ff33 !important;
    font-family: 'VT323', monospace !important;
    text-shadow: 0 0 15px rgba(51, 255, 51, 0.8) !important;
    letter-spacing: 3px !important;
}

/* === Markdown Content === */
.gradio-container .markdown {
    color: #33ff33 !important;
    font-family: 'VT323', monospace !important;
    font-size: 18px !important;
}

.gradio-container .markdown code {
    background: #1a1a1a !important;
    color: #ff9933 !important;
    border: 1px solid #33ff33 !important;
    padding: 2px 6px !important;
}

.gradio-container .markdown pre {
    background: #0d0d0d !important;
    border: 2px solid #33ff33 !important;
    border-radius: 8px !important;
    padding: 12px !important;
}

/* === Info Text === */
.gradio-container .info {
    color: #33ff33 !important;
    font-family: 'VT323', monospace !important;
    font-size: 18px !important;
}

/* === HTML/Image Output === */
.gradio-container iframe,
.gradio-container img {
    border: 2px solid #33ff33 !important;
    border-radius: 8px !important;
    box-shadow: 0 0 20px rgba(51, 255, 51, 0.3) !important;
}
"""


def handle_submit(api_client: ApiClient, status_output, turn_counter, latency_display, specialist_ticker, log_output, json_output, html_output, image_output, archive_output):
    """
    Returns a closure for handling the Gradio submit event with VEGAS UI updates.
    """
    turn_count = 0

    async def _handle_submit_closure(prompt: str, text_file: object, image_file: object, use_simple_chat: bool):
        """Generator function to handle the streaming UI updates."""
        nonlocal turn_count

        if not prompt.strip() and not text_file and not image_file:
            yield {status_output: "⚠ ERROR: PROVIDE PROMPT OR FILE"}
            return

        turn_count += 1
        specialist_log = []

        async for update in api_client.invoke_agent_streaming(prompt, text_file, image_file, use_simple_chat):
            ui_update = {}

            # Update status
            if "status" in update:
                ui_update[status_output] = f"► {update['status']}"

            # Update turn counter
            ui_update[turn_counter] = str(turn_count).zfill(3)

            # Update latency (mock for now - would need actual timing from API)
            if "logs" in update:
                ui_update[latency_display] = "042"  # Mock latency in ms

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

            # Update HTML output
            if "html" in update:
                html_content = update["html"]
                if html_content:
                    iframe_html = f'<iframe srcdoc="{html.escape(html_content if isinstance(html_content, str) else "")}" style="width: 100%; height: 600px; border: none;"></iframe>'
                    ui_update[html_output] = gr.update(value=iframe_html, visible=True)
                else:
                    ui_update[html_output] = gr.update(value="", visible=False)

            # Update image output
            if "image" in update:
                ui_update[image_output] = gr.update(value=update["image"], visible=bool(update["image"]))

            # Update archive report
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

    return _handle_submit_closure


def create_ui(api_client: ApiClient):
    """Creates the VEGAS Gradio UI with retro terminal styling."""
    with gr.Blocks(theme=gr.themes.Monochrome(), title="LAS VEGAS Terminal", css=VEGAS_CSS) as demo:

        # Header
        gr.Markdown("# 🖥️ V.E.G.A.S. TERMINAL")
        gr.Markdown("**Visual Agentic-Scaffold**")
        gr.Markdown("```SYSTEM STATUS: OPERATIONAL | CLEARANCE LEVEL: ALPHA```")

        with gr.Row():
            # === LEFT COLUMN: Command Input & Specialist Monitor ===
            with gr.Column(scale=2):
                gr.Markdown("### ⌨️ COMMAND BAR")

                prompt_input = gr.Textbox(
                    label="COMMAND INPUT",
                    lines=4,
                    placeholder="█ ENTER DIRECTIVE... (ENTER: EXECUTE | SHIFT+ENTER: NEW LINE)",
                    submit_btn=True
                )

                with gr.Row():
                    file_input = gr.File(label="📄 TEXT FILE STAGING", visible=False)  # Disabled pending Dockyard/MCP integration (ADR-MCP-002)
                    image_input = gr.Image(type="filepath", label="🖼️ IMAGE FILE STAGING", visible=False)  # Disabled pending Dockyard/MCP integration (ADR-MCP-002)

                simple_chat_checkbox = gr.Checkbox(
                    label="SIMPLE CHAT MODE",
                    value=False,
                    info="ENABLE: Single-perspective | DISABLE: Parallel progenitor analysis (default)"
                )

                submit_button = gr.Button("▶️ EXECUTE", variant="primary")

                # NIXIE Tube Readouts
                gr.Markdown("### 📊 SYSTEM READOUTS")

                with gr.Row():
                    with gr.Column(elem_classes="nixie-panel"):
                        gr.Markdown('<div class="nixie-label">TURN COUNT</div>', elem_classes="nixie-label")
                        turn_counter = gr.Textbox(value="000", show_label=False, interactive=False, elem_classes="nixie-value")

                    with gr.Column(elem_classes="nixie-panel"):
                        gr.Markdown('<div class="nixie-label">LATENCY (MS)</div>', elem_classes="nixie-label")
                        latency_display = gr.Textbox(value="000", show_label=False, interactive=False, elem_classes="nixie-value")

                # Specialist Routing Ticker
                gr.Markdown("### 🔀 SPECIALIST ROUTING LOG")
                specialist_ticker = gr.Textbox(
                    label="ACTIVE ROUTING SEQUENCE",
                    lines=8,
                    interactive=False,
                    elem_classes="specialist-ticker"
                )

            # === RIGHT COLUMN: Agent Output & Artifacts ===
            with gr.Column(scale=3):
                gr.Markdown("### 📡 SYSTEM STATUS")
                status_output = gr.Textbox(label="CURRENT STATUS", interactive=False)

                gr.Markdown("### 📜 AGENT EXECUTION LOG")
                log_output = gr.Textbox(label="EXECUTION TRACE", lines=12, interactive=False)

                gr.Markdown("### 📦 ARTIFACTS")
                with gr.Tabs():
                    with gr.TabItem("🌐 RENDERED HTML"):
                        html_output = gr.HTML()

                    with gr.TabItem("🖼️ GENERATED IMAGE"):
                        image_output = gr.Image(label="Generated Image", visible=False)

                    with gr.TabItem("🗄️ ARCHIVE REPORT"):
                        archive_output = gr.Markdown()

                    with gr.TabItem("⚙️ FINAL STATE (JSON)"):
                        json_output = gr.JSON()

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
    """Parses command-line arguments and launches the VEGAS Gradio app."""
    parser = argparse.ArgumentParser(description="VEGAS UI for the Agentic System")
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the Gradio app on."
    )
    args = parser.parse_args()

    api_client = ApiClient()
    demo = create_ui(api_client)

    print(f"🖥️  Launching V.E.G.A.S. Terminal on port {args.port}...")
    demo.launch(server_port=args.port, server_name="0.0.0.0")


if __name__ == "__main__":
    main()
