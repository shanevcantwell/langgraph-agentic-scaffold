# Audited on Sept 23, 2025
import pytest
import pkgutil
import importlib
import app.src.specialists

def get_all_modules(package):
    """Helper to discover all modules in a given package."""
    modules = []
    for _, name, is_pkg in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
        if not is_pkg:
            modules.append(name)
    return modules

CRITICAL_MODULES = [
    "app.src.api",
    "app.src.cli",
    "app.src.workflow.graph_builder",
    "app.src.workflow.graph_orchestrator",
    "app.src.workflow.runner",
    "app.src.llm.factory",
    "app.src.utils.config_loader",
]

SPECIALIST_MODULES = get_all_modules(app.src.specialists)

ALL_MODULES_TO_TEST = CRITICAL_MODULES + SPECIALIST_MODULES

@pytest.mark.parametrize("module_name", ALL_MODULES_TO_TEST)
def test_import_all_modules(module_name):
    """
    A smoke test to ensure all critical modules and specialist modules
    can be imported without raising an ImportError. This helps catch
    dependency issues early.
    """
    try:
        importlib.import_module(module_name)
    except ImportError as e:
        pytest.fail(f"Failed to import module '{module_name}': {e}")
