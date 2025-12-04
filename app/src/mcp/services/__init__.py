# app/src/mcp/services/__init__.py
"""
MCP Services - Standalone service modules for tool capabilities.

Services provide tool functionality that can be exposed via MCP to specialists.
Unlike specialists, services are not graph nodes - they're pure capability providers.

Available services:
- FaraService: Visual UI verification using Fara-7B vision model
"""

from .fara_service import FaraService

__all__ = ["FaraService"]
