# app/tests/unit/test_artifact_tools.py
"""
Tests for shared artifact tools (mcp/artifact_tools.py).

read tools: list_artifacts, retrieve_artifact (extracted #195)
write tool:  write_artifact (ADR-076 — data flow primitives)
"""
import json
import pytest

from app.src.mcp.artifact_tools import (
    list_artifacts,
    retrieve_artifact,
    write_artifact,
    format_artifact_value,
    artifact_tool_defs,
    dispatch_artifact_tool,
    ARTIFACT_TOOL_PARAMS,
    _generate_artifact_name,
    _resolve_collision,
)


# =============================================================================
# list_artifacts
# =============================================================================

class TestListArtifacts:
    """Tests for listing artifacts with type/size hints."""

    def test_empty_artifacts(self):
        assert list_artifacts({}) == "No artifacts available."

    def test_dict_artifact(self):
        result = list_artifacts({"plan": {"a": 1, "b": 2}})
        assert "plan: dict (2 keys)" in result

    def test_list_artifact(self):
        result = list_artifacts({"steps": [1, 2, 3]})
        assert "steps: list (3 items)" in result

    def test_string_artifact(self):
        result = list_artifacts({"user_request": "Sort files"})
        assert "user_request: str (10 chars)" in result

    def test_bytes_artifact(self):
        result = list_artifacts({"image": b"\x89PNG" + b"\x00" * 100})
        assert "image: bytes (104 bytes)" in result

    def test_other_type(self):
        result = list_artifacts({"flag": True})
        assert "flag: bool" in result

    def test_sorted_keys(self):
        result = list_artifacts({"z_key": "z", "a_key": "a", "m_key": "m"})
        lines = result.split("\n")[1:]  # Skip "Artifacts:" header
        keys = [line.strip().split(":")[0] for line in lines]
        assert keys == ["a_key", "m_key", "z_key"]


# =============================================================================
# retrieve_artifact
# =============================================================================

class TestRetrieveArtifact:
    """Tests for retrieving individual artifacts."""

    def test_retrieve_string(self):
        result = retrieve_artifact({"msg": "hello"}, "msg")
        assert result == "hello"

    def test_retrieve_dict(self):
        data = {"summary": "AI safety", "word_count": 500}
        result = retrieve_artifact({"analysis": data}, "analysis")
        parsed = json.loads(result)
        assert parsed["summary"] == "AI safety"
        assert parsed["word_count"] == 500

    def test_retrieve_missing_key(self):
        result = retrieve_artifact({"a": 1}, "missing")
        assert "not found" in result
        assert "list_artifacts" in result

    def test_retrieve_none_value(self):
        result = retrieve_artifact({"empty": None}, "empty")
        assert result == "(empty)"

    def test_retrieve_binary(self):
        result = retrieve_artifact({"img": b"\x89PNG\x00\x00"}, "img")
        assert "binary" in result
        assert "6 bytes" in result


# =============================================================================
# format_artifact_value
# =============================================================================

class TestFormatArtifactValue:
    """Tests for artifact value formatting. No truncation (#183)."""

    def test_none_value(self):
        assert format_artifact_value(None) == "(empty)"

    def test_string_value_preserved_fully(self):
        """String values must not be truncated (#183)."""
        long_string = "x" * 1000
        assert format_artifact_value(long_string) == long_string

    def test_dict_to_json(self):
        result = format_artifact_value({"key": "val"})
        parsed = json.loads(result)
        assert parsed["key"] == "val"

    def test_list_to_json(self):
        result = format_artifact_value([1, 2, 3])
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_binary_shows_size(self):
        result = format_artifact_value(b"\x89PNG" + b"\x00" * 1000)
        assert "binary" in result
        assert "1004 bytes" in result

    def test_other_type_str(self):
        assert format_artifact_value(42) == "42"
        assert format_artifact_value(True) == "True"


# =============================================================================
# ToolDef + schema integration
# =============================================================================

class TestToolDefIntegration:
    """Tests for artifact_tool_defs() and ARTIFACT_TOOL_PARAMS."""

    def test_tool_defs_are_local(self):
        """Artifact tools should be marked as local (not external MCP)."""
        defs = artifact_tool_defs()
        assert "list_artifacts" in defs
        assert "retrieve_artifact" in defs
        assert "write_artifact" in defs
        assert defs["list_artifacts"].is_external is False
        assert defs["retrieve_artifact"].is_external is False
        assert defs["write_artifact"].is_external is False

    def test_tool_defs_service_is_local(self):
        defs = artifact_tool_defs()
        assert defs["list_artifacts"].service == "local"
        assert defs["retrieve_artifact"].service == "local"
        assert defs["write_artifact"].service == "local"

    def test_param_schemas_present(self):
        assert "list_artifacts" in ARTIFACT_TOOL_PARAMS
        assert "retrieve_artifact" in ARTIFACT_TOOL_PARAMS
        assert "write_artifact" in ARTIFACT_TOOL_PARAMS

    def test_retrieve_artifact_requires_key(self):
        schema = ARTIFACT_TOOL_PARAMS["retrieve_artifact"]
        assert "key" in schema["properties"]
        assert "key" in schema["required"]

    def test_write_artifact_requires_content_not_key(self):
        schema = ARTIFACT_TOOL_PARAMS["write_artifact"]
        assert "content" in schema["properties"]
        assert "key" in schema["properties"]
        assert "content" in schema["required"]
        assert "key" not in schema.get("required", [])


# =============================================================================
# dispatch_artifact_tool
# =============================================================================

class TestDispatchArtifactTool:
    """Tests for the dispatch function used in specialist tool routing."""

    def test_dispatch_list_artifacts(self):
        result = dispatch_artifact_tool("list_artifacts", {}, {"a": "b"})
        assert "a: str" in result

    def test_dispatch_retrieve_artifact(self):
        result = dispatch_artifact_tool("retrieve_artifact", {"key": "msg"}, {"msg": "hello"})
        assert result == "hello"

    def test_dispatch_unknown_tool(self):
        result = dispatch_artifact_tool("unknown_tool", {}, {})
        assert "Unknown artifact tool" in result

    def test_dispatch_retrieve_missing_key(self):
        result = dispatch_artifact_tool("retrieve_artifact", {"key": "missing"}, {"a": 1})
        assert "not found" in result

    def test_dispatch_write_artifact(self):
        artifacts = {"existing": "data"}
        result = dispatch_artifact_tool(
            "write_artifact", {"content": "hello world", "key": "notes"}, artifacts
        )
        assert "notes" in result
        assert artifacts["notes"] == "hello world"

    def test_dispatch_write_artifact_no_key(self):
        artifacts = {}
        result = dispatch_artifact_tool(
            "write_artifact", {"content": "observation"}, artifacts
        )
        assert "written as" in result
        assert len(artifacts) == 1  # One auto-named entry


# =============================================================================
# write_artifact
# =============================================================================

class TestWriteArtifact:
    """Tests for write_artifact (ADR-076 — data flow primitives)."""

    def test_write_with_key(self):
        artifacts = {}
        result = write_artifact(artifacts, "dolphin facts", key="observations")
        assert "observations" in result
        assert artifacts["observations"] == "dolphin facts"

    def test_write_without_key_generates_name(self):
        artifacts = {}
        result = write_artifact(artifacts, "some content")
        assert "written as" in result
        # Should have one artifact with an auto-generated key
        assert len(artifacts) == 1
        key = list(artifacts.keys())[0]
        assert "-" in key  # word-word-word format

    def test_write_collision_appends_suffix(self):
        artifacts = {"notes": "prior notes"}
        result = write_artifact(artifacts, "new notes", key="notes")
        assert "notes-2" in result
        assert artifacts["notes"] == "prior notes"  # Original unchanged
        assert artifacts["notes-2"] == "new notes"

    def test_write_multiple_collisions(self):
        artifacts = {"log": "v1", "log-2": "v2", "log-3": "v3"}
        result = write_artifact(artifacts, "v4", key="log")
        assert "log-4" in result
        assert artifacts["log-4"] == "v4"

    def test_write_visible_to_list(self):
        artifacts = {"user_request": "Sort files"}
        write_artifact(artifacts, "1.txt is about dolphins", key="file_obs")
        listing = list_artifacts(artifacts)
        assert "file_obs" in listing

    def test_write_visible_to_retrieve(self):
        artifacts = {}
        write_artifact(artifacts, "categorization plan here", key="plan")
        retrieved = retrieve_artifact(artifacts, "plan")
        assert retrieved == "categorization plan here"

    def test_write_returns_char_count(self):
        artifacts = {}
        result = write_artifact(artifacts, "x" * 42, key="data")
        assert "42 chars" in result

    def test_write_empty_content_rejected(self):
        """Empty content is rejected with an error — prevents ghost artifacts."""
        artifacts = {}
        result = write_artifact(artifacts, "", key="empty")
        assert "Error" in result
        assert "empty" not in artifacts

    def test_write_whitespace_only_rejected(self):
        """Whitespace-only content is rejected — prevents ghost artifacts."""
        artifacts = {}
        result = write_artifact(artifacts, "   \n  ", key="blank")
        assert "Error" in result
        assert "blank" not in artifacts

    def test_dispatch_empty_args_rejected(self):
        """write_artifact called with {} args doesn't create ghost artifact."""
        artifacts = {}
        result = dispatch_artifact_tool("write_artifact", {}, artifacts)
        assert "Error" in result
        assert len(artifacts) == 0


# =============================================================================
# Name generation helpers
# =============================================================================

class TestNameGeneration:
    """Tests for artifact name generation and collision resolution."""

    def test_generated_name_is_three_words(self):
        name = _generate_artifact_name(set())
        parts = name.split("-")
        assert len(parts) == 3

    def test_generated_name_avoids_existing(self):
        existing = set()
        names = set()
        for _ in range(20):
            name = _generate_artifact_name(existing)
            assert name not in existing
            existing.add(name)
            names.add(name)
        assert len(names) == 20  # All unique

    def test_collision_no_conflict(self):
        assert _resolve_collision(set(), "notes") == "notes"

    def test_collision_appends_suffix(self):
        assert _resolve_collision({"notes"}, "notes") == "notes-2"

    def test_collision_skips_existing_suffixes(self):
        existing = {"log", "log-2", "log-3"}
        assert _resolve_collision(existing, "log") == "log-4"
