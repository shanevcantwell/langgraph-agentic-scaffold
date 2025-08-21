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
    )]
):
    """
    Sends a prompt to the langgraph-agentic-scaffold API /v1/graph/invoke endpoint and prints the final response.
    """
    invoke_url = f"{API_BASE_URL}/v1/graph/invoke"
    print(f"▶️  Invoking agent via {invoke_url} with prompt: '{prompt}'")

    # The API expects a JSON payload matching the InvokeRequest Pydantic model.
    payload = {"input_prompt": prompt}

    try:
        # Make the POST request to the server.
        # Setting a long timeout as agentic workflows can take time.
        response = requests.post(invoke_url, json=payload, timeout=300)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        print("\n✅ --- Agent Final Response ---")
        # The API returns a JSON object with a 'final_output' key.
        # We extract and pretty-print that key's value.
        response_json = response.json()
        final_output = response_json.get("final_output", {})
        print(json.dumps(final_output, indent=2))
        print("---\n- End of Response ---") # Test comment

        # Check for successful content in the final_output
        if not final_output.get("text_to_process") and \
           not final_output.get("extracted_data") and \
           not final_output.get("json_artifact") and \
           not final_output.get("html_artifact"):
            # Also check the last message in the 'messages' list
            messages = final_output.get("messages", [])
            if not messages or not messages[-1].get("content"):
                print("\n❌ Verification FAILED: Agent did not return any meaningful content.", file=sys.stderr)
                sys.exit(1)
            else:
                print("\n✅ Verification PASSED: Agent returned meaningful content.")
        else:
            print("\n✅ Verification PASSED: Agent returned meaningful content.")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error: Could not connect to the API server at {invoke_url}.", file=sys.stderr)
        print("Please ensure the server is running with './scripts/server.sh' or '.\\scripts\\server.bat'.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    app()