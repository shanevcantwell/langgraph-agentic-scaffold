import pytest

def test_import_tool():
    try:
        from langchain_core.tools import tool, Tool
    except ImportError as e:
        pytest.fail(f"Failed to import tool and Tool from langchain_core.tools: {e}")
