import importlib
import inflection
from typing import Type

from .base import BaseSpecialist


def get_specialist_class(specialist_name: str) -> Type[BaseSpecialist]:
    """
    Dynamically imports and returns a specialist class by its snake_case name.
    This function assumes the file is named `specialist_name.py` and the class
    is named `SpecialistName` (PascalCase), as per the project's naming conventions.
    """
    module_name = f".{specialist_name}"
    # Convert snake_case (e.g., "data_processor_specialist") to PascalCase (e.g., "DataProcessorSpecialist")
    class_name = inflection.camelize(specialist_name)
    try:
        module = importlib.import_module(module_name, package=__name__)
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Could not find specialist '{class_name}' in module '{specialist_name}.py'. Please ensure the file and class are named correctly.") from e
