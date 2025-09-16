# app/src/cli.py
import typer
import requests
import json
import sys
from typing_extensions import Annotated
from typing import Optional

# The base URL for the running FastAPI application
API_BASE_URL = "http://127.0.0.1:8000"

app = typer.Typer(
    help="A command-line interface to interact with the agentic system."
)


@app.command()
def invoke(
    prompt: Annotated[Optional[str], typer.Argument(
        help="The initial prompt to send to the agentic system. If omitted, the CLI will read from standard input."
    )] = None,
    json_only: Annotated[bool, typer.Option(
        "--json-only",
        "-j",
        help="Output only the JSON response, suppressing other messages."
    )] = False
):
    """
    Sends a prompt to the langgraph-agentic-scaffold API /v1/graph/invoke endpoint and prints the final response.
    If no prompt is provided as an argument, it reads multi-line input from stdin until EOF (Ctrl+D).
    """
    # --- MODIFICATION START ---
    # If no prompt is passed as a command-line argument, read from standard input.
    if prompt is None:
        if not json_only and sys.stdin.isatty():
            print("▶️  Enter your multi-line prompt below. Press Ctrl+D (Linux/macOS) or Ctrl+Z+Enter (Windows) when finished.")
            print("---")
        prompt = sys.stdin.read().strip()

    if not prompt:
        if not json_only:
            print("❌ Error: Prompt is empty. No request sent.", file=sys.stderr)
        sys.exit(1)
    # --- MODIFICATION END ---

    invoke_url = f"{API_BASE_URL}/v1/graph/invoke"
    if not json_only:
        # Truncate long prompts for cleaner display
        display_prompt = (prompt[:150] + '...') if len(prompt) > 150 else prompt
        print(f"▶️  Invoking agent via {invoke_url} with prompt: '{display_prompt}'")


    # The API expects a JSON payload matching the InvokeRequest Pydantic model.
    payload = {"input_prompt": prompt}

    try:
        # Make the POST request to the server.
        # Setting a long timeout as agentic workflows can take time.
        response = requests.post(invoke_url, json=payload, timeout=300)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        response_json = response.json()
        final_output = response_json.get("final_output", {})

        # Check for a specific error report first. If it exists, the run failed.
        if error_report := final_output.get("error_report"):
            if not json_only:
                print("\n❌ --- Agent Workflow Failed ---")
                # The report is already formatted as markdown, so just print it.
                print(error_report)
                print("--- End of Error Report ---")
            else:
                print(json.dumps(final_output, indent=2))
            sys.exit(1) # Exit with an error code

        if json_only:
            print(json.dumps(final_output, indent=2))
        else:
            print("\n✅ --- Agent Final Response ---")
            print(json.dumps(final_output, indent=2))
            print("--- End of Response ---")

        # --- Verification Logic ---
        # This logic provides a general-purpose check to see if the agent
        # produced any meaningful output. It's more robust than just checking
        # the last message, which is often an empty-content tool call from the router.
        messages = final_output.get("messages", [])
        last_content_message = ""
        # Find the last message that has actual content, ignoring tool calls.
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("content", "").strip():
                last_content_message = msg.get("content")
                break

        # Check for any known data artifacts in the root of the output.
        has_artifact = any(
            final_output.get(key)
            for key in [
                "text_to_process",
                "extracted_data",
                "json_artifact",
                "html_artifact",
                "archive_report",
            ]
        )

        # Success is defined as having an artifact or a non-empty content message.
        is_successful = has_artifact or last_content_message

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
def stream(
    prompt: Annotated[Optional[str], typer.Argument(
        help="The initial prompt to send to the agentic system. If omitted, the CLI will read from standard input."
    )] = None,
    json_only: Annotated[bool, typer.Option(
        "--json-only",
        "-j",
        help="Output only the final JSON state, suppressing live logs."
    )] = False
):
    """
    Connects to the streaming endpoint (/v1/graph/stream) to get real-time logs from the agent.
    If no prompt is provided as an argument, it reads multi-line input from stdin until EOF (Ctrl+D).
    """
    if prompt is None:
        if not json_only and sys.stdin.isatty():
            print("▶️  Enter your multi-line prompt for streaming. Press Ctrl+D (Linux/macOS) or Ctrl+Z+Enter (Windows) when finished.")
            print("---")
        prompt = sys.stdin.read().strip()

    if not prompt:
        if not json_only:
            print("❌ Error: Prompt is empty. No request sent.", file=sys.stderr)
        sys.exit(1)

    stream_url = f"{API_BASE_URL}/v1/graph/stream"
    if not json_only:
        display_prompt = (prompt[:150] + '...') if len(prompt) > 150 else prompt
        print(f"▶️  Streaming agent via {stream_url} with prompt: '{display_prompt}'")
        print("--- Agent Log Stream ---")

    payload = {"input_prompt": prompt}

    try:
        with requests.post(stream_url, json=payload, stream=True, timeout=300) as response:
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
            
            if not json_only:
                print("--- End of Stream ---")
            
            if final_state_json:
                # Always print the final state for scripting purposes
                print(final_state_json)

    except requests.exceptions.RequestException as e:
        if not json_only:
            print(f"\n❌ Error: Could not connect to the API server at {stream_url}.", file=sys.stderr)
            print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    app()
