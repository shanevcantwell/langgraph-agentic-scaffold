# app/src/cli.py
import typer
import requests
import json
import sys
from typing_extensions import Annotated
from typing import Optional


API_BASE_URL = "http://127.0.0.1:8000"

# The main callback is now only for the --json-only flag and default command logic.
app = typer.Typer(
    help="A command-line interface for interacting with the agentic system.",
    invoke_without_command=True,
)

@app.callback()
def main(
    ctx: typer.Context,
    json_only: Annotated[bool, typer.Option(
        "--json-only",
        "-j",
        help="Output only the JSON response, suppressing other messages."
    )] = False,
    simple_chat: Annotated[bool, typer.Option(
        "--simple-chat",
        "-s",
        help="Use simple chat mode (single ChatSpecialist). Default is tiered chat mode (parallel progenitors)."
    )] = False
):
    """
    Main callback that handles default command routing.
    If no subcommand is provided, route to invoke command with remaining args.
    """
    # If a subcommand was invoked, let it handle execution
    if ctx.invoked_subcommand is not None:
        return

    # No subcommand provided - default to invoke
    # Get the prompt from remaining args
    prompt = None
    if ctx.args:
        # Join all remaining arguments as the prompt
        prompt = " ".join(ctx.args)

    # Call invoke logic directly
    _run_invoke(prompt, json_only, simple_chat)

def _run_invoke(prompt: Optional[str], json_only: bool, simple_chat: bool):
    """Shared logic for the invoke command."""
    if prompt is None:
        if not json_only and sys.stdin.isatty():
            print("▶️  Enter your multi-line prompt below. Press Ctrl+D (Linux/macOS) or Ctrl+Z+Enter (Windows) when finished.")
            print("---")
        prompt = sys.stdin.read().strip()

    if not prompt:
        if not json_only:
            print("❌ Error: Prompt is empty. No request sent.", file=sys.stderr)
        sys.exit(1)

    invoke_url = f"{API_BASE_URL}/v1/graph/invoke"
    if not json_only:
        display_prompt = (prompt[:150] + '...') if len(prompt) > 150 else prompt
        mode_str = "simple chat" if simple_chat else "tiered chat"
        print(f"▶️  Invoking agent via {invoke_url} with prompt: '{display_prompt}' ({mode_str} mode)")

    payload = {"input_prompt": prompt, "use_simple_chat": simple_chat}

    try:
        response = requests.post(invoke_url, json=payload, timeout=300)
        response.raise_for_status()

        response_json = response.json()
        final_output = response_json.get("final_output", {})

        if error_report := final_output.get("error_report"):
            if not json_only:
                print("\n❌ --- Agent Workflow Failed ---")
                print(error_report)
                print("--- End of Error Report ---")
            else:
                print(json.dumps(final_output, indent=2))
            sys.exit(1)

        if json_only:
            print(json.dumps(final_output, indent=2))
        else:
            print("\n✅ --- Agent Final Response (Full State) ---")
            print(json.dumps(final_output, indent=2))
            print("--- End of Response ---")

        messages = final_output.get("messages", [])
        last_content_message = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("content", "").strip():
                last_content_message = msg.get("content")
                break

        has_final_response_artifact = "final_user_response.md" in final_output.get("artifacts", {})
        is_successful = has_final_response_artifact or last_content_message

        if not is_successful:
            if not json_only:
                print("\n❌ Verification FAILED: Agent did not return any meaningful content.", file=sys.stderr)
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        if not json_only:
            print(f"\n❌ Error: Could not connect to the API server at {invoke_url}.", file=sys.stderr)
            print("Please ensure the server is running with './scripts/server.sh' or '.\\scripts\\server.bat'.", file=sys.stderr)
            print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)

@app.command()
def invoke(
    prompt: Annotated[Optional[str], typer.Argument(
        help=(
            "The initial prompt to send to the agentic system. If omitted, the CLI will read from standard input."
        )
    )] = None,
    json_only: Annotated[bool, typer.Option(
        "--json-only",
        "-j",
        help="Output only the JSON response, suppressing other messages."
    )] = False,
    simple_chat: Annotated[bool, typer.Option(
        "--simple-chat",
        "-s",
        help="Use simple chat mode (single ChatSpecialist). Default is tiered chat mode (parallel progenitors)."
    )] = False
):
    """
    Sends a prompt to the agent's /v1/graph/invoke endpoint and prints the final response.
    If no prompt is provided as an argument, it reads multi-line input from stdin until EOF (Ctrl+D).
    """
    _run_invoke(prompt, json_only, simple_chat)


@app.command()
def stream(
    prompt: Annotated[Optional[str], typer.Argument(
        help=(
            "The initial prompt to send to the agentic system. If omitted, the CLI will read from "
            "standard input."
        )
    )] = None,
    json_only: Annotated[bool, typer.Option(
        "--json-only", "-j", help="Output only the final JSON state."
    )] = False,
    simple_chat: Annotated[bool, typer.Option(
        "--simple-chat",
        "-s",
        help="Use simple chat mode (single ChatSpecialist). Default is tiered chat mode (parallel progenitors)."
    )] = False
):
    """
    Connects to the streaming endpoint (/v1/graph/stream) to get real-time logs from the agent.
    If no prompt is provided as an argument, it reads multi-line input from stdin until EOF (Ctrl+D).
    """
    if prompt is None:
        if not json_only and sys.stdin.isatty():
            print("▶️  Enter your multi-line prompt for streaming. Press Ctrl+D (Linux/macOS) or "
                  "Ctrl+Z+Enter (Windows) when finished.")
            print("---")
        prompt = sys.stdin.read().strip()

    if not prompt:
        if not json_only:
            print("❌ Error: Prompt is empty. No request sent.", file=sys.stderr)
        sys.exit(1)

    stream_url = f"{API_BASE_URL}/v1/graph/stream"
    if not json_only:
        display_prompt = (prompt[:150] + '...') if len(prompt) > 150 else prompt
        mode_str = "simple chat" if simple_chat else "tiered chat"
        print(f"▶️  Streaming agent via {stream_url} with prompt: '{display_prompt}' ({mode_str} mode)")
        print("--- Agent Log Stream ---")

    payload = {"input_prompt": prompt, "use_simple_chat": simple_chat}

    try: # The payload now includes optional null values.
        with requests.post(stream_url, json=payload, stream=True, timeout=300) as response: # The payload now includes optional null values.
            response.raise_for_status()
            final_state_json = None
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line.startswith("FINAL_STATE::"):
                        final_state_json = decoded_line.replace("FINAL_STATE::", "", 1)
                        break  # Final state received, stop processing stream
                    else:
                        if not json_only:
                            print(decoded_line)
            
            if not json_only and sys.stdout.isatty():
                print("--- End of Stream ---")
            
            if final_state_json:
                # Always print the final state for scripting purposes
                try:
                    # Validate it's JSON before just printing
                    json.loads(final_state_json)
                    print(final_state_json)
                except json.JSONDecodeError:
                    if not json_only:
                        print("\n❌ Verification FAILED: Failed to parse FINAL_STATE JSON.", file=sys.stderr)
                    sys.exit(1)
            else:
                if not json_only:
                    print("\n❌ Verification FAILED: Stream completed without a FINAL_STATE message.", file=sys.stderr)
                sys.exit(1)

    except requests.exceptions.RequestException as e:
        if not json_only:
            print(f"\n❌ Error: Could not connect to the API server at {stream_url}.", file=sys.stderr)
            print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)


@app.command()
def distill(
    domains: Annotated[Optional[str], typer.Option(
        "--domains",
        "-d",
        help="Comma-separated list of domains to process (default: all configured domains)"
    )] = None,
    json_only: Annotated[bool, typer.Option(
        "--json-only",
        "-j",
        help="Output only the JSON response, suppressing other messages."
    )] = False
):
    """
    Runs the distillation workflow to generate training datasets across knowledge domains.

    This command sends a special prompt to trigger the distillation coordinator specialist,
    which will:
    1. Load seed prompts for each domain
    2. Generate variations of each seed prompt
    3. Collect teacher model responses for all variations
    4. Write results to hierarchical JSONL files in ./datasets/

    Note: This is a long-running operation. Each domain may take hours depending on
    rate limits and number of seeds configured.
    """
    # Construct prompt to trigger distillation
    if domains:
        prompt = f"Generate distillation training dataset for domains: {domains}"
        if not json_only:
            print(f"▶️  Running distillation workflow for domains: {domains}")
    else:
        prompt = "Generate distillation training dataset for all configured domains"
        if not json_only:
            print("▶️  Running distillation workflow for all configured domains")

    if not json_only:
        print("⚠️  This is a long-running operation. Progress will be shown below.")
        print("    Datasets will be written to ./datasets/<domain>/ as they complete.")
        print("    Press Ctrl+C to cancel (progress will be lost).\n")

    # Use streaming endpoint for real-time progress
    stream_url = f"{API_BASE_URL}/v1/graph/stream"
    payload = {"input_prompt": prompt, "use_simple_chat": False}

    try:
        with requests.post(stream_url, json=payload, stream=True, timeout=86400) as response:  # 24h timeout
            response.raise_for_status()
            final_state_json = None

            if not json_only:
                print("--- Distillation Workflow Progress ---\n")

            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line.startswith("FINAL_STATE::"):
                        final_state_json = decoded_line.replace("FINAL_STATE::", "", 1)
                        break
                    else:
                        if not json_only:
                            print(decoded_line)

            if not json_only:
                print("\n--- Workflow Complete ---\n")

            if final_state_json:
                final_state = json.loads(final_state_json)

                if json_only:
                    print(json.dumps(final_state, indent=2))
                else:
                    # Extract distillation results
                    dist_state = final_state.get("distillation_state", {})
                    completed_paths = dist_state.get("completed_dataset_paths", [])
                    total_responses = dist_state.get("total_responses_collected_global", 0)
                    total_errors = dist_state.get("total_errors_global", 0)
                    duration = dist_state.get("workflow_duration_seconds", 0)

                    print("✅ Distillation workflow completed successfully!\n")
                    print(f"   Duration: {duration // 3600}h {(duration % 3600) // 60}m")
                    print(f"   Responses collected: {total_responses}")
                    print(f"   Errors: {total_errors}")
                    print(f"\n   Dataset files:")
                    for path in completed_paths:
                        print(f"      - {path}")
            else:
                if not json_only:
                    print("❌ Workflow completed without final state", file=sys.stderr)
                sys.exit(1)

    except requests.exceptions.RequestException as e:
        if not json_only:
            print(f"\n❌ Error: Could not connect to the API server at {stream_url}.", file=sys.stderr)
            print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        if not json_only:
            print("\n\n⚠️  Workflow cancelled by user. Progress has been lost.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    app()
