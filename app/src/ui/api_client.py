# app/src/ui/api_client.py
import httpx
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

        try: # Use httpx.AsyncClient for non-blocking streaming
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", STREAM_URL, json=payload) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line:
                            decoded_line = line.strip()
                            # SSE format is "data: { ... }"
                            if decoded_line.startswith("data:"):
                                try:
                                    data_str = decoded_line[len("data:"):].strip()
                                    data = json.loads(data_str)
                                    # The API now sends discrete updates. The client's job
                                    # is to simply yield them to the UI handler.
                                    yield data
                                except json.JSONDecodeError:
                                    log_history += f"\n[UI-CLIENT-ERROR] Failed to parse JSON from stream: {decoded_line}"
                                    yield {"logs": log_history}

                # The backend now sends Server-Sent Events (SSE) with a JSON payload.
                # We need to parse these events correctly.
            
            # After the stream is complete, we can make a separate call to get the final state.
            # This is a more robust pattern than trying to parse it from the stream.
            # For now, we will just yield the final status from the stream.
            
            # The final state is no longer sent in the stream. The UI handler will
            # receive the final status update from the stream itself. We yield an
            # empty final block to ensure the UI updates correctly on completion.
            artifacts = {}
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
                "final_state": {},
                "html": html_content,
                "image": image_ui_output,
                "logs": log_history,
                "archive": archive_report
            }
                
        except Exception as e:
            yield {"status": f"API Error: {e}", "logs": log_history + f"\nERROR: {e}"}