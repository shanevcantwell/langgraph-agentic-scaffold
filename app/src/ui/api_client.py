# app/src/ui/api_client.py
import httpx
import json
import base64
from PIL import Image
import io

STREAM_URL = "http://127.0.0.1:8000/v1/graph/stream"
RESUME_URL = "http://127.0.0.1:8000/v1/graph/resume"  # ADR-CORE-042

class ApiClient:
    """Handles all communication with the backend agentic system API."""

    def _encode_image_to_base64(self, image_path):
        """Encodes an image file to a base64 string."""
        if not image_path:
            return None
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    async def invoke_agent_streaming(self, prompt: str, text_file_path: str, image_path: str, use_simple_chat: bool = False):
        """
        Calls the streaming FastAPI backend and yields updates for the UI.
        This function is a generator.
        """
        payload = {"input_prompt": prompt, "use_simple_chat": use_simple_chat}
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
                return

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

            # The final state with artifacts is now sent by the stream itself
            # No need to construct it separately - the stream sends all required data
                
        except Exception as e:
            yield {"status": f"API Error: {e}", "logs": log_history + f"\nERROR: {e}"}

    async def resume_workflow(self, thread_id: str, user_input: str):
        """
        ADR-CORE-042: Resume an interrupted workflow with user's clarification.

        When a specialist calls interrupt() to request clarification, the stream
        yields an interrupt event with a thread_id. This method resumes the workflow
        with the user's response.

        Args:
            thread_id: The thread_id from the interrupt event
            user_input: The user's clarification response

        Yields:
            Updates from the resumed workflow stream
        """
        payload = {"thread_id": thread_id, "user_input": user_input}

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", RESUME_URL, json=payload) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line:
                            decoded_line = line.strip()
                            if decoded_line.startswith("data:"):
                                try:
                                    data_str = decoded_line[len("data:"):].strip()
                                    data = json.loads(data_str)
                                    yield data
                                except json.JSONDecodeError:
                                    yield {"logs": f"[UI-CLIENT-ERROR] Failed to parse JSON: {decoded_line}"}

        except Exception as e:
            yield {"status": f"Resume Error: {e}", "error": str(e)}