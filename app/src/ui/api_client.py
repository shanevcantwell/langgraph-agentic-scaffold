# app/src/ui/api_client.py
#
# Gradio UI API client — uses the OpenAI-compatible endpoint (ADR-UI-003 WS3).
# Parses ChatCompletionChunk SSE into UI updates.
#
import httpx
import json
import base64

CHAT_URL = "http://127.0.0.1:8000/v1/chat/completions"
RESUME_URL = "http://127.0.0.1:8000/v1/graph/resume"  # ADR-CORE-042 (no OpenAI equivalent)


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
        Calls the OpenAI-compatible streaming endpoint and yields updates for the UI.
        """
        # Build OpenAI ChatCompletionRequest
        messages = [{"role": "user", "content": prompt}]
        model = "las-simple" if use_simple_chat else "las-default"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        # File attachments — prepend as system context in messages
        if text_file_path:
            try:
                with open(text_file_path.name, "r", encoding="utf-8") as f:
                    text_content = f.read()
                messages.insert(0, {"role": "system", "content": f"[Uploaded document]\n{text_content}"})
            except Exception as e:
                yield {"status": f"Error reading file: {e}"}
                return

        if image_path:
            try:
                b64 = self._encode_image_to_base64(image_path.name)
                messages.insert(0, {"role": "system", "content": f"[Uploaded image: base64 encoded]\n{b64}"})
            except Exception as e:
                yield {"status": f"Error reading image: {e}"}
                return

        accumulated_content = ""

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", CHAT_URL, json=payload) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line or not line.strip().startswith("data:"):
                            continue

                        data_str = line.strip()[len("data:"):].strip()

                        # OpenAI stream terminator
                        if data_str == "[DONE]":
                            if accumulated_content:
                                yield {
                                    "status": "Workflow complete.",
                                    "final_state": {"routing_history": [], "task_is_complete": True},
                                    "archive": accumulated_content,
                                }
                            break

                        try:
                            chunk = json.loads(data_str)
                            # Extract delta content from ChatCompletionChunk
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    accumulated_content += content
                                    yield {"status": f"Receiving response..."}
                        except json.JSONDecodeError:
                            yield {"logs": f"[UI-CLIENT-ERROR] Failed to parse: {data_str[:100]}"}

        except Exception as e:
            yield {"status": f"API Error: {e}", "logs": f"ERROR: {e}"}

    async def resume_workflow(self, thread_id: str, user_input: str):
        """
        ADR-CORE-042: Resume an interrupted workflow with user's clarification.
        Stays on the bespoke /v1/graph/resume endpoint (no OpenAI equivalent).
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
