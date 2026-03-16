# app/tests/integration/test_openai_endpoint.py
"""
Smoke tests for the OpenAI-compatible /v1/chat/completions endpoint.

Validates WI-1 (PD output quality) and WI-2 (headless discovery).
Requires Docker: `docker exec langgraph-app pytest app/tests/integration/test_openai_endpoint.py -v`
"""
import json
import pytest
import httpx

pytestmark = pytest.mark.integration

BASE_URL = "http://localhost:8000"
TIMEOUT = 180  # 3 minutes — PD runs may take a while


@pytest.fixture(scope="module")
def client():
    """Shared httpx client for the test module."""
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
        yield c


def test_models_endpoint(client):
    """GET /v1/models returns available routing profiles."""
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    ids = [m["id"] for m in data["data"]]
    assert "las-default" in ids


def test_sync_completion(client):
    """POST /v1/chat/completions (stream=false) returns a valid response."""
    resp = client.post("/v1/chat/completions", json={
        "model": "las-simple",
        "stream": False,
        "messages": [{"role": "user", "content": "What is 2+2?"}],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    content = data["choices"][0]["message"]["content"]
    assert content, "Response content should not be empty"
    assert len(content) > 5, f"Response suspiciously short: {content!r}"


def test_streaming_completion(client):
    """POST /v1/chat/completions (stream=true) yields valid SSE."""
    chunks = []
    has_reasoning = False
    has_content = False
    has_done = False

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as streaming_client:
        with streaming_client.stream("POST", "/v1/chat/completions", json={
            "model": "las-default",
            "stream": True,
            "messages": [{"role": "user", "content": "What is the capital of France?"}],
        }) as resp:
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    has_done = True
                    break
                chunk = json.loads(payload)
                chunks.append(chunk)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("reasoning_content"):
                    has_reasoning = True
                if delta.get("content"):
                    has_content = True

    assert has_done, "Stream should end with [DONE]"
    assert len(chunks) > 0, "Should have received at least one chunk"
    # Reasoning content (thought stream) is expected for default routing
    # Content (the actual answer) should appear at least once
    assert has_content, "Stream should contain at least one content delta"


def test_active_runs_endpoint(client):
    """GET /v1/runs/active returns a valid (possibly empty) run list."""
    resp = client.get("/v1/runs/active")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert isinstance(data["runs"], list)
