# app/src/workflow/react_wrapper.py
"""
ReactEnabledSpecialist wrapper for config-driven ReAct capability (ADR-CORE-051).

Extracted from graph_builder.py to reduce file size and improve maintainability.
"""
import logging
import types
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..specialists import BaseSpecialist

logger = logging.getLogger(__name__)


class ReactEnabledSpecialist:
    """
    Wrapper that adds ReAct capability to any specialist via config.

    This enables config-driven iterative tool use without requiring specialists
    to explicitly inherit from ReActMixin. GraphBuilder wraps specialists with
    this class when their config has `react: enabled: true`.

    The wrapper injects ReActMixin methods onto the inner specialist instance,
    allowing it to call self.execute_with_tools() for ReAct-style loops.

    Config example:
        specialists:
          my_specialist:
            type: "llm"
            react:
              enabled: true
              max_iterations: 10
              stop_on_error: false

    See ADR-CORE-051 for architectural details.
    """

    def __init__(
        self,
        inner: "BaseSpecialist",
        max_iterations: int = 10,
        stop_on_error: bool = False
    ):
        """
        Initialize the wrapper.

        Args:
            inner: The specialist instance to wrap
            max_iterations: Default max iterations for ReAct loops
            stop_on_error: Whether to halt on first tool error
        """
        self._inner = inner
        self._max_iterations = max_iterations
        self._stop_on_error = stop_on_error

        # Inject ReActMixin methods onto the inner specialist
        self._inject_react_capability()

        logger.debug(
            f"ReactEnabledSpecialist wrapping '{inner.specialist_name}' "
            f"(max_iterations={max_iterations}, stop_on_error={stop_on_error})"
        )

    def _inject_react_capability(self):
        """
        Inject ReActMixin methods onto the inner specialist instance.

        This allows the specialist's code to call self.execute_with_tools()
        as if it had inherited from ReActMixin directly.
        """
        from ..specialists.mixins.react_mixin import ReActMixin

        # Methods to inject from ReActMixin
        methods_to_inject = [
            'execute_with_tools',
            '_build_tool_schemas',
            '_execute_tool',
            '_is_external_service',  # Config-driven external MCP dispatch
            '_format_tool_result_message',
            '_compute_call_signature',  # For stagnation detection
            '_serialize_for_provider',  # ADR-CORE-055: trace-based message serialization
            '_check_stagnation',  # ADR-CORE-055: cycle detection
            '_trace_to_tool_result',  # ADR-CORE-055: trace conversion helper
        ]

        for method_name in methods_to_inject:
            if hasattr(ReActMixin, method_name):
                method = getattr(ReActMixin, method_name)
                # Bind the method to the inner specialist instance
                bound_method = types.MethodType(method, self._inner)
                setattr(self._inner, method_name, bound_method)

        # Inject class attributes needed by the methods (fixes #69)
        class_attrs_to_inject = [
            'CYCLE_MIN_REPETITIONS',  # For stagnation/cycle detection
            'TOOL_PARAMETERS',  # For proper tool schema generation
        ]

        for attr_name in class_attrs_to_inject:
            if hasattr(ReActMixin, attr_name):
                setattr(self._inner, attr_name, getattr(ReActMixin, attr_name))

        # Store config values on inner specialist for reference
        self._inner._react_config = {
            'max_iterations': self._max_iterations,
            'stop_on_error': self._stop_on_error,
        }

    def __getattr__(self, name):
        """Forward attribute access to the inner specialist."""
        return getattr(self._inner, name)

    def __repr__(self):
        return f"ReactEnabledSpecialist({self._inner.specialist_name})"
