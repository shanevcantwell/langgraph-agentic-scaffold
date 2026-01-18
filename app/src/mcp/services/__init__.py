# app/src/mcp/services/__init__.py
"""
MCP Services - Standalone service modules for tool capabilities.

Services provide tool functionality that can be exposed via MCP to specialists.
Unlike specialists, services are not graph nodes - they're pure capability providers.

Available services:
- InferenceService: LLM inference for MCP tool execution
"""

from .inference_service import InferenceService, InferenceResponse

__all__ = ["InferenceService", "InferenceResponse"]
