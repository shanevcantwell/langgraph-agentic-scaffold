import typer
import requests
import json
import sys
from typing_extensions import Annotated

# The base URL for the running FastAPI application
API_BASE_URL = "http://127.0.0.1:8000"

app = typer.Typer(
    help="A command-line interface to interact with the agentic system."
)


@app.command()
def invoke(
    prompt: Annotated[str, typer.Argument(
        help="The initial prompt to send to the agentic system."
    )],
    json_only: Annotated[bool, typer.Option(
        "--json-only",
        "-j",
        help="Output only the JSON response, suppressing other messages."
    )] = False
):
    """
    Sends a prompt to the langgraph-agentic-scaffold API /v1/graph/invoke endpoint and prints the final response.
    """
    invoke_url = f"{API_BASE_URL}/v1/graph/invoke"
    if not json_only:
        print(f"▶️  Invoking agent via {invoke_url} with prompt: '{prompt}'")

    # The API expects a JSON payload matching the InvokeRequest Pydantic model.
    payload = {"input_prompt": prompt}

    try:
        # Make the POST request to the server.
        # Setting a long timeout as agentic workflows can take time.
        response = requests.post(invoke_url, json=payload, timeout=300)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        response_json = response.json()
        final_output = response_json.get("final_output", {})

        if json_only:
            print(json.dumps(final_output, indent=2))
        else:
            print("\n✅ --- Agent Final Response ---")
            print(json.dumps(final_output, indent=2))
            print("--- End of Response ---")

        # --- Verification Logic ---
        # This logic provides a general-purpose check to see if the agent
        # produced any meaningful output. This is a baseline success metric,
        # distinct from the stricter routing validation in `verify.sh`.
        messages = final_output.get("messages", [])
        # The last message is expected to be a dict from AIMessage.
        last_message_content = None
        if messages and isinstance(messages[-1], dict):
            last_message_content = messages[-1].get("content")

        # Check for any known data artifacts in the root of the output.
        has_artifact = any(
            final_output.get(key)
            for key in [
                "text_to_process",
                "extracted_data",
                "json_artifact",
                "html_artifact",
            ]
        )

        # Success is defined as having an artifact or non-empty content in the last message.
        is_successful = has_artifact or (last_message_content and last_message_content.strip())

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


if __name__ == "__main__":
    app()
