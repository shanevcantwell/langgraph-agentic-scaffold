# app/src/specialists/__init__.py
import importlib
import logging
import inflection

# First, import the base class so it's available for other modules and for export.
from .base import BaseSpecialist

logger = logging.getLogger(__name__)

def get_specialist_class(specialist_name: str, config: dict) -> type:
    """
    Dynamically imports and returns a specialist class based on its name.
    This allows for a plug-and-play architecture where new specialists can be
    added without changing the core orchestration logic.

    Args:
        specialist_name: The snake_case name of the specialist (e.g., 'file_specialist').
        config: The configuration dictionary for the specialist.

    Returns:
        The specialist class type.

    Raises:
        ImportError: If the specialist module or class cannot be found.
    """
    class_name = inflection.camelize(specialist_name)
    module_name = f".{specialist_name}"
    try:
        # Dynamically import the module within the 'specialists' package.
        module = importlib.import_module(module_name, package='src.specialists')
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import specialist '{specialist_name}'. Could not find class '{class_name}' in module '{module_name}'. Error: {e}", exc_info=True)
        raise ImportError(f"Could not find specialist class '{class_name}' in module '{module_name}'. Error: {e}") from e