import importlib
from typing import Type

from .base import BaseSpecialist


def get_specialist_class(specialist_name: str) -> Type[BaseSpecialist]:
    """
    Dynamically finds and returns a specialist class from this module.
    The class name is expected to be the PascalCase version of the snake_case specialist_name.
    e.g., 'systems_architect' -> 'SystemsArchitect'
    """
    module_name = f".{specialist_name}"
    class_name = "".join(word.capitalize() for word in specialist_name.split("_"))

    # Import the module (e.g., .systems_architect) relative to the current package
    module = importlib.import_module(module_name, package=__name__)
    return getattr(module, class_name)