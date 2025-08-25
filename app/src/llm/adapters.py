# app/src/llm/adapters.py

# This file serves as the public interface for the adapters package.
# It imports the concrete adapter classes from their respective modules,
# making them easily accessible for the AdapterFactory.

from .gemini_adapter import GeminiAdapter
from .lmstudio_adapter import LMStudioAdapter

# By importing them here, other parts of the application can do:
# from app.src.llm.adapters import GeminiAdapter
# without needing to know the exact file structure.
