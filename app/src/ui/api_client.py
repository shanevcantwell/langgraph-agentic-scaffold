# app/src/ui/api_client.py
import requests
import json
import base64
from PIL import Image
import io

STREAM_URL = "http://127.0.0.1:8000/v1/graph/stream"

class ApiClient:
    """Handles all communication with the backend agentic system API."""

    def _encode_image_to_base64(self, image_path):
        """Encodes an image file to a base64 string."""
        if not image_path:
            return None
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    async def invoke_agent_streaming(self, prompt: str, text_file_path: str, image_path: str):
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
                yield {"status": f"Error reading file: {e}"}
                return

        if image_path:
            try:
                payload["image_to_process"] = self._encode_image_to_base64(image_path.name)
            except Exception as e:
                yield {"status": f"Error reading image: {e}"}

        try:
            with requests.post(STREAM_URL, json=payload, stream=True, timeout=300) as response:
                response.raise_for_status()

                final_state_json_parts = []
                is_capturing_final_state = False

                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8').strip()
                        if is_capturing_final_state:
                            final_state_json_parts.append(decoded_line)
                        elif decoded_line.startswith("FINAL_STATE::"):
                            is_capturing_final_state = True
                            # Add the first part of the JSON, stripping the prefix
                            final_state_json_parts.append(decoded_line.replace("FINAL_STATE::", "", 1))
                        else:
                            log_history += decoded_line + "\n"
                            yield {"logs": log_history}
                final_state_json = "".join(final_state_json_parts)

            if final_state_json:
                # --- MODIFICATION: Add robust JSON parsing ---
                try:
                    final_state = json.loads(final_state_json)
                except json.JSONDecodeError as e:
                    # If parsing fails, show the raw string and error in the UI.
                    error_report = {
                        "JSON Parsing Error": str(e),
                        "Received Malformed String": final_state_json
                    }
                    yield {
                        "status": "Error: Received invalid JSON from backend.",
                        "final_state": error_report,
                        "logs": log_history + "\nERROR: Failed to parse final state JSON."
                    }
                    return
                # --- END MODIFICATION ---

                artifacts = final_state.get("artifacts", {})
                archive_report = artifacts.get("archive_report.md", "No archive report was generated.")
                html_content = artifacts.get("html_document.html", "")
                image_ui_output = None
                if image_artifact_b64 := artifacts.get("image_artifact_b64"):
                    try:
                        img_data = base64.b64decode(image_artifact_b64)
                        image_ui_output = Image.open(io.BytesIO(img_data))
                    except Exception as e:
                        log_history += f"\nError decoding image artifact: {e}"

                yield {
                    "status": "Workflow Complete!",
                    "final_state": final_state,
                    "html": html_content,
                    "image": image_ui_output,
                    "logs": log_history,
                    "archive": archive_report
                }

        except Exception as e:
            yield {"status": f"API Error: {e}", "logs": log_history + f"\nERROR: {e}"}