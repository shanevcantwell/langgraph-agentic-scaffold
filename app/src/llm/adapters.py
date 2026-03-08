# app/src/llm/adapters.py

# This file serves as the public interface for the adapters package.
# It imports the concrete adapter classes from their respective modules,
# making them easily accessible for the AdapterFactory.

from .gemini_adapter import GeminiAdapter
from .local_inference_adapter import LocalInferenceAdapter
from .lmstudio_adapter import LMStudioAdapter
from .pooled_adapter import PooledLocalInferenceAdapter

# By importing them here, other parts of the application can do:
# from app.src.llm.adapters import LocalInferenceAdapter
# without needing to know the exact file structure.
