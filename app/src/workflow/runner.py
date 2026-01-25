# src/workflow/runner.py
import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, Optional

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.messages import messages_to_dict
from langgraph.types import Command
from pydantic import BaseModel

from ..utils.errors import ConfigError
from ..utils.cancellation_manager import CancellationManager
from ..graph.state import GraphState
from ..graph.state_factory import create_initial_state
from ..persistence.checkpoint_manager import get_checkpointer, create_checkpointer_context
from .graph_builder import GraphBuilder

logger = logging.getLogger(__name__)


def _make_state_serializable(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively traverses a state dictionary and converts non-serializable
    objects (like LangChain messages, Pydantic models, and datetimes)
    into JSON-compatible formats.
    """
    if isinstance(state, dict):
        new_dict = {}
        for k, v in state.items():
            new_dict[k] = _make_state_serializable(v)
        return new_dict
    elif isinstance(state, list):
        if state and isinstance(state[0], BaseMessage):
            return messages_to_dict(state)
        return [_make_state_serializable(item) for item in state]
    elif isinstance(state, BaseModel):
        return state.model_dump()
    elif isinstance(state, datetime):
        return state.isoformat()
    return state


class WorkflowRunner:
    """
    A service class that encapsulates the logic for running the agentic workflow.
    This acts as a Facade, providing a simple interface to the complex internal system.
    """
    def __init__(self):
        """
        Initializes the WorkflowRunner by instantiating the GraphBuilder
        and compiling the LangGraph application.

        NOTE: For async checkpointing (required for streaming), call
        set_async_checkpointer() from the FastAPI lifespan context after init.
        """
        self.builder = GraphBuilder()
        self.config = self.builder.config
        self.specialists = self.builder.specialists
        self._perform_pre_flight_checks()
        self.recursion_limit = self.config.get("workflow", {}).get("recursion_limit", 25)

        # Checkpointer is OPTIONAL - only needed for RECESS/ESM multi-request patterns.
        # For basic streaming (astream) with interrupt(), LangGraph manages state in-memory.
        # See checkpoint_manager.py docstring for architectural distinction.
        self.checkpointer = None
        self.app = self.builder.build(checkpointer=None)

        logger.info("WorkflowRunner initialized (async checkpointer will be set in lifespan)")

    def set_async_checkpointer(self, checkpointer):
        """
        Set the async checkpointer and rebuild the graph.

        This must be called from an async context (e.g., FastAPI lifespan)
        after the checkpointer has been initialized via create_checkpointer_context().

        Args:
            checkpointer: An async checkpointer instance (e.g., AsyncSqliteSaver)
        """
        self.checkpointer = checkpointer
        self.app = self.builder.build(checkpointer=self.checkpointer)

        if self.checkpointer:
            logger.info(f"WorkflowRunner: async checkpointer set ({type(self.checkpointer).__name__})")
        else:
            logger.info("WorkflowRunner: checkpointing disabled")

    def reload(self, overrides: Dict[str, Any] = None):
        """
        Reloads the workflow configuration and rebuilds the graph.
        This allows for dynamic switching of LLM providers without restarting the server.
        """
        logger.info("Reloading WorkflowRunner...")
        from ..utils.config_loader import ConfigLoader

        # Reload configuration with overrides
        ConfigLoader().reload(overrides)

        # Re-initialize builder with new config
        self.builder = GraphBuilder()
        self.config = self.builder.config
        self.specialists = self.builder.specialists

        # Re-run checks and build
        self._perform_pre_flight_checks()
        self.recursion_limit = self.config.get("workflow", {}).get("recursion_limit", 25)

        # ADR-CORE-018: Re-initialize checkpointer on reload
        self.checkpointer = get_checkpointer(self.config)
        self.app = self.builder.build(checkpointer=self.checkpointer)
        logger.info("WorkflowRunner successfully reloaded.")

    def _perform_pre_flight_checks(self):
        """
        Performs critical environment checks before the application is fully wired.
        This ensures the system fails fast if essential configurations are missing.
        """
        logger.info("Performing pre-flight environment checks...")
        llm_providers = self.config.get("llm_providers", {})
        
        # Build a comprehensive set of all provider bindings that are actually in use.
        used_provider_bindings = set()
        # 1. Check bindings on individual specialists
        for spec_config in self.config.get("specialists", {}).values():
            if binding := spec_config.get("llm_config"):
                used_provider_bindings.add(binding)
        # 2. Check the default binding
        if default_binding := self.config.get("workflow", {}).get("default_llm_config"):
            used_provider_bindings.add(default_binding)

        if not used_provider_bindings:
            logger.warning("Pre-flight check: No LLM providers appear to be in use.")

        for binding_key, provider_config in llm_providers.items():
            if binding_key not in used_provider_bindings:
                continue

            provider_type = provider_config.get("type")
            if provider_type == "gemini" and not provider_config.get("api_key"):
                raise ConfigError(
                    f"Pre-flight check failed: Provider '{binding_key}' is type 'gemini' but "
                    "the GOOGLE_API_KEY environment variable is not set."
                )
            elif provider_type == "lmstudio" and not provider_config.get("base_url"):
                raise ConfigError(
                    f"Pre-flight check failed: Provider '{binding_key}' is type 'lmstudio' but "
                    "the LMSTUDIO_BASE_URL environment variable is not set."
                )

        workflow_config = self.config.get("workflow", {})
        critical_specialists = workflow_config.get("critical_specialists", [])
        if critical_specialists:
            loaded_specialist_names = self.specialists.keys()
            missing_critical = [name for name in critical_specialists if name not in loaded_specialist_names]
            if missing_critical:
                raise ConfigError(
                    f"Pre-flight check failed: The following critical specialists failed to load: {missing_critical}. "
                    "The application cannot start in this state. Please check the logs for errors related to these specialists."
                )
            logger.info(f"Successfully validated that all critical specialists are loaded: {critical_specialists}")

        # BUG-STARTUP-001: Validate LLM provider connectivity
        # Actually ping providers to catch network/proxy issues at startup
        from ..llm.factory import ping_provider
        failed_providers = []
        for binding_key, provider_config in llm_providers.items():
            if binding_key not in used_provider_bindings:
                continue
            if provider_config.get("skip_ping", False):
                logger.info(f"Provider '{binding_key}' skipped ping (skip_ping=true)")
                continue
            result = ping_provider(binding_key, provider_config)
            if result["success"]:
                logger.info(f"Provider '{binding_key}' ping OK ({result['latency_ms']}ms)")
            else:
                logger.warning(f"Provider '{binding_key}' failed ping: {result['error']}")
                failed_providers.append(binding_key)

        if failed_providers:
            logger.warning(f"Pre-flight: {len(failed_providers)} provider(s) failed connectivity check: {failed_providers}")

        logger.info("All pre-flight checks passed successfully.")

    def run(self, goal: str, text_to_process: str = None, image_to_process: str = None, use_simple_chat: bool = False) -> Dict[str, Any]:
        """
        Executes the workflow with a given goal.
        """
        logger.info(f"--- Starting workflow for goal: '{goal}' ---")

        initial_state: GraphState = create_initial_state(
            goal=goal,
            text_to_process=text_to_process,
            image_to_process=image_to_process,
            use_simple_chat=use_simple_chat
        )

        config = {"recursion_limit": self.recursion_limit}
        if self.checkpointer:
            thread_id = str(uuid.uuid4())
            config["configurable"] = {"thread_id": thread_id}
            logger.info(f"Running workflow with thread_id: {thread_id}")

        try:
            final_state = self.app.invoke(initial_state, config=config)
            logger.info("--- Workflow completed successfully ---")

            # Return the entire final state so the API layer can decide what to do with it.
            # This ensures the client receives the full context, including artifacts.
            return _make_state_serializable(final_state)

        except Exception as e:
            logger.error(f"--- Workflow failed with an unhandled exception: {e} ---", exc_info=True)
            return {
                "error": f"Workflow failed catastrophically: {e}",
                "messages": [HumanMessage(content=goal)], "turn_count": 0,
            }

    async def run_streaming(self, goal: str, text_to_process: str = None, image_to_process: str = None, use_simple_chat: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes the workflow with a given goal and streams back the raw
        LangGraph events. The API layer is responsible for formatting these
        events for the client.
        """
        logger.info(f"--- Starting streaming workflow for goal: '{goal}' ---")

        initial_state: GraphState = create_initial_state(
            goal=goal,
            text_to_process=text_to_process,
            image_to_process=image_to_process,
            use_simple_chat=use_simple_chat
        )

        # Generate a unique run_id for this execution to enable trace tracking
        run_id = uuid.uuid4()
        # Yield the run_id immediately so the client can start tracking traces
        yield {"run_id": str(run_id)}
        # ADR-CORE-042: Also yield thread_id for interrupt handling (same as run_id)
        # The stream formatter needs this to include in interrupt responses
        if self.checkpointer:
            yield {"thread_id": str(run_id)}

        config = {"recursion_limit": self.recursion_limit, "run_id": run_id}
        if self.checkpointer:
            # Use the same ID for thread_id to keep things consistent for this run
            config["configurable"] = {"thread_id": str(run_id)}
            logger.info(f"Streaming workflow with thread_id: {run_id}")

        try:
            async for event in self.app.astream(initial_state, config=config):
                # Check for cancellation request
                if CancellationManager.is_cancelled(str(run_id)):
                    logger.warning(f"Run {run_id} was cancelled by user request.")
                    yield {"error": "Mission aborted by user.", "scratchpad": {"error_report": "## Mission Aborted\n\nThe user manually cancelled this mission."}}
                    break
                yield event
            logger.info("--- Streaming workflow complete. ---")
        except Exception as e:
            logger.error(f"--- Streaming workflow failed with an unhandled exception: {e} ---", exc_info=True)
            # Create a serializable error message
            error_message_dict = {"error": f"Workflow failed catastrophically: {str(e)}"}
            yield {"error_report": error_message_dict}
        finally:
            # Cleanup cancellation state
            CancellationManager.clear_cancellation(str(run_id))

    async def resume(self, thread_id: str, user_input: str) -> Dict[str, Any]:
        """
        RECESS/ESM: Resume a workflow from a checkpointed interrupt point.

        NOTE: This method is for STATELESS multi-request patterns where the client
        disconnects between turns. For basic streaming with interrupt(), the client
        stays connected and LangGraph manages state in-memory - no resume() needed.

        Use cases requiring resume():
        - RECESS "Subgraph as a Service" (client makes separate HTTP requests per turn)
        - Long-running workflows where process may restart
        - Load-balanced deployments where requests hit different servers

        Args:
            thread_id: The unique identifier for this conversation thread.
                       Must match the thread_id used when the interrupt occurred.
            user_input: The user's response to the clarification questions.

        Returns:
            The final state after the graph completes.

        Raises:
            ValueError: If checkpointing is not enabled.
            RuntimeError: If no interrupt is pending for the given thread_id.
        """
        if not self.checkpointer:
            raise ValueError(
                "Cannot resume workflow: checkpointing is not enabled. "
                "Set checkpointing.enabled=true in user_settings.yaml"
            )

        logger.info(f"--- Resuming workflow for thread_id: '{thread_id}' with user input ---")

        try:
            # Create a Command to resume with the user's input
            # The user_input will be available as the return value of interrupt()
            resume_command = Command(resume=user_input)

            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": self.recursion_limit
            }

            # Resume the graph from the interrupt point
            final_state = await self.app.ainvoke(resume_command, config=config)
            logger.info(f"--- Workflow resumed and completed for thread_id: '{thread_id}' ---")

            return _make_state_serializable(final_state)

        except Exception as e:
            logger.error(f"--- Resume failed for thread_id '{thread_id}': {e} ---", exc_info=True)
            return {
                "error": f"Failed to resume workflow: {e}",
                "thread_id": thread_id
            }

    def run_with_thread(
        self,
        goal: str,
        thread_id: Optional[str] = None,
        text_to_process: str = None,
        image_to_process: str = None,
        use_simple_chat: bool = False
    ) -> tuple[Dict[str, Any], str]:
        """
        ADR-CORE-018: Execute workflow with explicit thread tracking.

        This version of run() supports checkpointing by using a thread_id.
        If the workflow is interrupted (e.g., by DialogueSpecialist), the
        client can later call resume() with the same thread_id.

        Args:
            goal: The user's input/request
            thread_id: Optional thread identifier. If not provided, a new UUID is generated.
            text_to_process: Optional text content
            image_to_process: Optional base64 image
            use_simple_chat: Whether to use simple chat mode

        Returns:
            Tuple of (final_state, thread_id). The thread_id is needed for resume().
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        logger.info(f"--- Starting workflow for goal: '{goal}' (thread_id: {thread_id}) ---")

        initial_state: GraphState = create_initial_state(
            goal=goal,
            text_to_process=text_to_process,
            image_to_process=image_to_process,
            use_simple_chat=use_simple_chat
        )

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self.recursion_limit
        }

        try:
            final_state = self.app.invoke(initial_state, config=config)
            logger.info(f"--- Workflow completed for thread_id: '{thread_id}' ---")
            return _make_state_serializable(final_state), thread_id

        except Exception as e:
            logger.error(f"--- Workflow failed for thread_id '{thread_id}': {e} ---", exc_info=True)
            return {
                "error": f"Workflow failed: {e}",
                "thread_id": thread_id
            }, thread_id