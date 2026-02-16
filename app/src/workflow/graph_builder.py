# app/src/workflow/graph_builder.py
import logging
from collections import defaultdict
from typing import Dict, Any, Callable, Optional, Set

from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt
from ..specialists import get_specialist_class, BaseSpecialist
from ..graph.state import GraphState
from ..enums import CoreSpecialist
from ..llm.factory import AdapterFactory
from ..utils.errors import SpecialistLoadError, WorkflowError
from .graph_orchestrator import GraphOrchestrator
from .executors.node_executor import NodeExecutor
from .specialist_categories import SpecialistCategories
from .subgraphs.tiered_chat import TieredChatSubgraph
from .subgraphs.distillation import DistillationSubgraph
from .subgraphs.context_engineering import ContextEngineeringSubgraph
from .subgraphs.emergent_project import EmergentProjectSubgraph
from ..specialists.tribe_conductor import TribeConductor
logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    Handles the build-time construction of the agentic workflow graph.
    This class is responsible for reading configuration, instantiating all
    specialists, and compiling the final, executable StateGraph.
    """
    def __init__(self, config_loader: ConfigLoader = None, adapter_factory: AdapterFactory = None):
        self.config_loader = config_loader or ConfigLoader()
        self.config = self.config_loader.get_config()
        self.adapter_factory = adapter_factory or AdapterFactory(self.config)
        self.node_executor = NodeExecutor(self.config)

        # Validate provider dependencies before attempting to load specialists
        missing_deps = self.adapter_factory.validate_provider_dependencies()
        if missing_deps:
            logger.warning("="*80)
            logger.warning("OPTIONAL DEPENDENCIES MISSING")
            logger.warning("="*80)
            for provider_key, provider_type, error_msg in missing_deps:
                logger.warning(error_msg)
            logger.warning("="*80)
            logger.warning("Specialists bound to these providers will fail to initialize.")
            logger.warning("To fix: Install missing dependencies or rebind specialists to other providers.")
            logger.warning("="*80)

        # TASK 2.5: Initialize MCP registry (per-graph-instance for test isolation)
        from ..mcp import McpRegistry, McpClient
        self.mcp_registry = McpRegistry(self.config)

        # ADR-MCP-003: External MCP (lazy initialization - call initialize_external_mcp() after build())
        self.external_mcp_client = None

        self.specialists = self._load_and_configure_specialists()
        
        # Register internal MCP services (e.g. InferenceService)
        self._register_internal_mcp_services()

        # TASK 1.2: Build allowed destinations for route validation
        # Include all specialists except router (which can't be a routing destination)
        # ADR-CORE-028: Use centralized exclusion logic
        router_name = CoreSpecialist.ROUTER.value
        self.allowed_destinations = {
            name for name in self.specialists
            if name != router_name and name not in SpecialistCategories.get_node_exclusions()
        }

        self.orchestrator = GraphOrchestrator(self.config, self.specialists, self.allowed_destinations)
        
        # Initialize Subgraphs
        self.subgraphs = [
            TieredChatSubgraph(self.specialists, self.orchestrator, self.config),
            DistillationSubgraph(self.specialists, self.orchestrator, self.config),
            ContextEngineeringSubgraph(self.specialists, self.orchestrator, self.config),
            EmergentProjectSubgraph(self.specialists, self.orchestrator, self.config)
        ]

        # ADR-CORE-028: Configure router AFTER subgraphs are initialized
        # because router exclusions now dynamically query subgraph exclusions
        all_configs = self.config.get("specialists", {})
        try:
            if CoreSpecialist.ROUTER.value in self.specialists:
                self._configure_router(self.specialists, all_configs)
        except (IOError, FileNotFoundError) as e:
            raise SpecialistLoadError(f"Could not load specialist '{CoreSpecialist.ROUTER.value}' due to a prompt loading error: {e}") from e

        workflow_config = self.config.get("workflow", {})
        raw_entry_point = workflow_config.get("entry_point", CoreSpecialist.ROUTER.value)
        if raw_entry_point not in self.specialists:
            logger.error(
                f"Configured entry point '{raw_entry_point}' is not an available specialist. "
                f"Defaulting to '{CoreSpecialist.ROUTER.value}'."
            )
            self.entry_point = CoreSpecialist.ROUTER.value
        else:
            self.entry_point = raw_entry_point

    def build(self, streaming_callback: Callable[[str], None] = None, checkpointer=None) -> StateGraph:
        """
        Builds and compiles the LangGraph StateGraph instance.

        Args:
            streaming_callback: Optional callback for streaming specialist output
            checkpointer: Optional LangGraph checkpointer for HitL interrupt/resume
                          (ADR-CORE-018). Pass SqliteSaver or PostgresSaver instance.
        """
        # Feature Flag: Check for Convening Architecture
        architecture = self.config.get("architecture", "default")
        if architecture == "convening":
            logger.info("---GraphBuilder: Building 'Convening of the Tribes' architecture---")
            return self._build_convening_graph(streaming_callback, checkpointer)

        workflow = StateGraph(GraphState)
        self._add_nodes_to_graph(workflow, streaming_callback)
        self._wire_hub_and_spoke_edges(workflow)
        workflow.set_entry_point(self.entry_point)

        # ADR-CORE-028: Use extracted compile helper
        return self._compile_graph(workflow, checkpointer, "default")

    async def initialize_external_mcp(self):
        """
        Initialize external MCP services (Docker containers, Node.js servers, etc).

        Must be called AFTER build() and BEFORE first graph invocation.
        This method is async because external MCP uses JSON-RPC protocol.

        See ADR-MCP-003 for architecture details.

        Usage:
            ```python
            graph_builder = GraphBuilder(config)
            graph = graph_builder.build()

            # Initialize external MCP (async)
            await graph_builder.initialize_external_mcp()

            # Now graph is ready
            result = graph.invoke(state)
            ```

        Raises:
            RuntimeError: If critical external MCP service fails to start
            ImportError: If mcp package not installed
        """
        external_config = self.config.get("mcp", {}).get("external_mcp", {})

        if not external_config or not external_config.get("enabled", False):
            logger.info("External MCP not enabled in configuration")
            return

        from ..mcp import ExternalMcpClient

        logger.info("Initializing external MCP services...")
        self.external_mcp_client = ExternalMcpClient(self.config)

        # Connect to all configured services using config-driven initialization
        # Supports both container_name mode (docker exec) and command/args mode (subprocess)
        # See ADR-CORE-027 for container_name pattern
        try:
            connected_services = await self.external_mcp_client.connect_all_from_config()
            for service_name, tools in connected_services.items():
                logger.info(
                    f"✓ External MCP service '{service_name}' connected successfully "
                    f"({len(tools)} tools available)"
                )
        except RuntimeError as e:
            # Required service failed - cleanup and re-raise
            logger.error(f"CRITICAL: External MCP service startup failed: {e}")
            await self.external_mcp_client.cleanup()
            raise

        # ADR-CORE-051: Attach permissioned external MCP clients per specialist
        # Permissions are defined in config.yaml under each specialist's "tools:" key
        # Specialists without tools: config get no external MCP access (secure default)
        from ..mcp import PermissionedMcpClient

        for name, instance in self.specialists.items():
            specialist_config = self.config.get("specialists", {}).get(name, {})
            tool_permissions = specialist_config.get("tools", {})

            if tool_permissions:
                # Specialist has explicit tool config - wrap with permissions
                instance.external_mcp_client = PermissionedMcpClient(
                    self.external_mcp_client,
                    allowed_tools=tool_permissions
                )
                logger.debug(f"Attached PermissionedMcpClient to '{name}' with tools: {list(tool_permissions.keys())}")
            else:
                # No tools config = no external MCP access (ADR-CORE-051 secure default)
                instance.external_mcp_client = None
                logger.debug(f"No external MCP access for '{name}' (no tools: config)")

        logger.info(
            f"External MCP initialization complete. "
            f"Connected services: {self.external_mcp_client.get_connected_services()}"
        )

    async def cleanup_external_mcp(self):
        """
        Cleanup external MCP connections at shutdown.

        Should be called during application shutdown to gracefully
        close container connections.
        """
        if self.external_mcp_client:
            await self.external_mcp_client.cleanup()
            logger.info("External MCP cleanup complete")

    def _format_tool_descriptions(self, tools: dict) -> str:
        """
        Format tool permissions for injection into specialist prompts (ADR-CORE-051).

        Args:
            tools: Dict mapping service names to tool lists or "*" wildcard
                   Example: {"filesystem": ["read_file", "write_file"]}

        Returns:
            Formatted string for prompt injection, or empty string if no tools
        """
        if not tools:
            return ""

        lines = ["", "--- AVAILABLE MCP TOOLS ---"]
        for service, tool_list in tools.items():
            if tool_list == "*":
                lines.append(f"- {service}: ALL tools available")
            else:
                lines.append(f"- {service}: {', '.join(tool_list)}")
        lines.append("")
        return "\n".join(lines)

    def _attach_llm_adapter(self, specialist_instance: BaseSpecialist):
        """
        Attaches an LLM adapter to a specialist instance if it is configured to use one.
        This is the single, authoritative method for adapter attachment.

        ADR-CORE-051: Also injects tool descriptions into the prompt if specialist
        has tools: config, keeping prompts in sync with actual permissions.
        """
        name = specialist_instance.specialist_name
        config = specialist_instance.specialist_config
        binding_key = config.get("llm_config")
        if binding_key:
            system_prompt = ""
            # EndSpecialist uses synthesis_prompt_file for its internal synthesis
            if prompt_file := config.get("synthesis_prompt_file"):
                system_prompt = load_prompt(prompt_file)
            elif prompt_file := config.get("prompt_file"):
                system_prompt = load_prompt(prompt_file)

            # ADR-CORE-051: Inject tool descriptions if specialist has tools config
            tool_descriptions = self._format_tool_descriptions(config.get("tools", {}))
            if tool_descriptions:
                system_prompt = f"{system_prompt}{tool_descriptions}"

            specialist_instance.llm_adapter = self.adapter_factory.create_adapter(name, system_prompt)
            logger.debug(f"Attached LLM adapter to '{name}' using binding '{binding_key}'.")

    def _load_and_configure_specialists(self) -> Dict[str, BaseSpecialist]:
        specialists_config = self.config.get("specialists", {})
        loaded_specialists: Dict[str, BaseSpecialist] = {}
        for name, config in specialists_config.items():
            try:
                SpecialistClass = get_specialist_class(name, config)
                
                if name == "web_specialist":
                    # TASK: Inject Search Strategy
                    from ..strategies.search.duckduckgo_strategy import DuckDuckGoSearchStrategy
                    # TODO: Read from config to allow switching strategies (e.g. Tavily, Google)
                    # For now, default to DuckDuckGo
                    search_strategy_instance = DuckDuckGoSearchStrategy()

                    # NOTE: FaraService removed - visual browsing now handled by
                    # navigator_browser_specialist via surf-mcp (see GH #32)
                    instance = SpecialistClass(
                        specialist_name=name,
                        specialist_config=config,
                        search_strategy=search_strategy_instance
                    )

                else:
                    instance = SpecialistClass(specialist_name=name, specialist_config=config)

                is_critical = name in self.config.get("workflow", {}).get("critical_specialists", [])
                if not instance.is_enabled:
                    logger.warning(f"Specialist '{name}' is disabled in its configuration. It will not be loaded.")
                    continue
                if not instance._perform_pre_flight_checks():
                    if is_critical:
                        raise SpecialistLoadError(f"Critical specialist '{name}' failed its pre-flight checks and could not be loaded. The application cannot start.")
                    logger.error(f"Specialist '{name}' failed its pre-flight checks and will be disabled.")
                    continue
                
                loaded_specialists[name] = instance
                logger.info(f"Successfully instantiated specialist: {name}")
            except (ImportError, IOError) as e:
                # Re-raise as a specific, catchable error for testing and clarity
                raise SpecialistLoadError(f"Could not load specialist '{name}' due to: {e}") from e
            except Exception as e:
                logger.error(f"An unexpected error occurred while loading specialist '{name}', it will be disabled. Error: {e}", exc_info=True)
                continue

        # --- Deferred Configuration and Adapter Attachment ---
        all_configs = self.config.get("specialists", {})

        # ADR-CORE-053: Build config-driven exclusion index for triage menus
        self.exclusion_index = self._build_exclusion_index(all_configs)

        # Note: Router configuration is deferred until after subgraphs are initialized
        # in __init__ because it needs to query subgraph exclusions (ADR-CORE-028).
        # Triage configuration can happen now as it doesn't depend on subgraphs.
        if CoreSpecialist.TRIAGE.value in loaded_specialists:
            self._configure_triage(loaded_specialists, all_configs)

        # --- Context Engineering Ecosystem ---
        # TriageArchitect needs dynamic specialist roster in system prompt (same as prompt_triage_specialist)
        if "triage_architect" in loaded_specialists:
            self._configure_triage(loaded_specialists, all_configs, specialist_name="triage_architect")

        # Now that all specialists, including triage, have their final
        # configurations, iterate through and attach adapters. This loop will
        # only attach adapters to specialists that don't already have one.
        # This is crucial because deferred configuration methods like _configure_router
        # and _configure_triage have already attached adapters with dynamic,
        # context-aware prompts. This check prevents this generic loop from
        # overwriting those specialized adapters.
        # ADR-CORE-028: Router is configured AFTER subgraphs in __init__, so skip it here
        for name, instance in loaded_specialists.items():
            if name == CoreSpecialist.ROUTER.value:
                continue  # Router configured after subgraphs in __init__
            if not instance.llm_adapter:
                self._attach_llm_adapter(instance)

        # TASK 2.5: Attach MCP client and register services
        # Do this after all specialists are loaded and configured
        from ..mcp import McpClient
        mcp_client = McpClient(self.mcp_registry)

        for instance in loaded_specialists.values():
            # Attach MCP client to all specialists
            instance.mcp_client = mcp_client

            # Register MCP services if specialist implements registration method
            if hasattr(instance, 'register_mcp_services'):
                try:
                    instance.register_mcp_services(self.mcp_registry)
                    logger.debug(f"Registered MCP services for '{instance.specialist_name}'")
                except Exception as e:
                    logger.error(
                        f"Failed to register MCP services for '{instance.specialist_name}': {e}",
                        exc_info=True
                    )

        return loaded_specialists

    def _build_exclusion_index(self, configs: Dict[str, Any]) -> Dict[str, Set[str]]:
        """
        ADR-CORE-053: Build inverted index of config-driven exclusions.

        Reads the `excluded_from` field from each specialist config and inverts it:
        Input:  specialist_a: {excluded_from: ["triage_architect", "router"]}
        Output: {"triage_architect": {"specialist_a"}, "router": {"specialist_a"}}

        This allows any menu-building specialist to query which specialists should
        be excluded from its menu by name.

        Args:
            configs: Dict of specialist configurations from config.yaml

        Returns:
            Dict mapping excluder name -> set of excluded specialist names
        """
        index: Dict[str, Set[str]] = defaultdict(set)
        for name, conf in configs.items():
            # Handle both dict configs and Pydantic model instances
            if hasattr(conf, 'excluded_from'):
                excluded_from = conf.excluded_from
            else:
                excluded_from = conf.get("excluded_from")

            if excluded_from:
                for excluder in excluded_from:
                    index[excluder].add(name)

        if index:
            logger.info(f"ADR-CORE-053: Built exclusion index with {len(index)} excluders")
            for excluder, excluded in index.items():
                logger.debug(f"  {excluder} excludes: {sorted(excluded)}")

        return dict(index)  # Convert defaultdict to regular dict

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        router_instance = specialists[CoreSpecialist.ROUTER.value]
        router_config = configs.get(CoreSpecialist.ROUTER.value, {})
        base_prompt = load_prompt(router_config.get("prompt_file", ""))

        # ADR-CORE-028: Dynamically collect exclusions from subgraphs
        # This replaces the hardcoded list and stays in sync with subgraph definitions
        subgraph_exclusions = []
        for subgraph in self.subgraphs:
            subgraph_exclusions.extend(subgraph.get_router_excluded_specialists())

        # Issue #90: Config-driven exclusions for router (same pattern as triage)
        config_exclusions = list(self.exclusion_index.get(CoreSpecialist.ROUTER.value, set()))
        excluded_from_router = SpecialistCategories.get_router_exclusions(subgraph_exclusions, config_exclusions)
        available_specialists = {name: conf for name, conf in configs.items() if name not in excluded_from_router}
        router_instance.set_specialist_map(available_specialists)

        # Inject routable specialist names into EI for DONE schema enum
        ei_name = CoreSpecialist.EXIT_INTERVIEW.value
        if ei_name in self.specialists and hasattr(self.specialists[ei_name], 'set_routable_specialists'):
            self.specialists[ei_name].set_routable_specialists(list(available_specialists.keys()))
            logger.info(f"ExitInterview: injected {len(available_specialists)} routable specialist names")

        standup_report = "\n\n--- AVAILABLE SPECIALISTS ---\n" + "\n".join([f"- {name}: {conf.get('description', 'No description.')}" for name, conf in available_specialists.items()])
        feedback_instruction = (
            "\nIMPORTANT ROUTING INSTRUCTIONS:\n"
            "1. **Precondition Fulfillment**: Review the conversation history. If a specialist (e.g., 'systems_architect') previously stated it was blocked waiting for an artifact, and the most recent specialist (e.g., 'file_specialist') just provided that artifact, your next step is to route back to the original, blocked specialist.\n"
            "2. **Error Correction**: If a specialist reports an error or that it cannot perform a task, you MUST use that feedback to select a different, more appropriate specialist to resolve the issue. Do not give up.\n"
            "3. **Follow the Plan**: If a `task_plan` exists in state, route to the specialist best suited to execute it. The task_plan captures the system's understanding of the user's intent.\n"
            "4. **Use Provided Tools**: You MUST choose from the list of specialists provided to you."
        )
        dynamic_system_prompt = f"{base_prompt}{standup_report}\n{feedback_instruction}"
        binding_key = router_config.get("llm_config")
        if not binding_key:
            raise WorkflowError(f"Could not resolve LLM binding for '{CoreSpecialist.ROUTER.value}'. Ensure it is bound in 'user_settings.yaml' or a 'default_llm_config' is set.")
        
        router_instance.llm_adapter = self.adapter_factory.create_adapter(CoreSpecialist.ROUTER.value, dynamic_system_prompt)
        logger.info("RouterSpecialist adapter attached with dynamic, context-aware prompt.")

    def _configure_triage(self, specialists: Dict[str, BaseSpecialist], configs: Dict, specialist_name: str = None):
        """Configure a triage specialist with dynamic ecosystem awareness.

        Triage is a pass/fail classifier: does the user's request need clarification
        (ask_user) or can the system proceed? It needs to know what specialists exist
        so it can judge whether the system can handle the request.

        Args:
            specialists: Dict of loaded specialist instances
            configs: Dict of specialist configurations
            specialist_name: The name of the triage specialist to configure.
                           Defaults to CoreSpecialist.TRIAGE.value for backwards compatibility.
        """
        if specialist_name is None:
            specialist_name = CoreSpecialist.TRIAGE.value

        triage_instance = specialists[specialist_name]
        triage_config = configs.get(specialist_name, {})
        base_prompt = load_prompt(triage_config.get("prompt_file", ""))

        # Build ecosystem awareness: what specialists can the system route to?
        # Uses config-driven exclusions (exclusion_index built at line 312).
        # Subgraph exclusions aren't available yet but config.yaml excluded_from covers them.
        config_exclusions = list(self.exclusion_index.get(specialist_name, set()))
        triage_exclusions = SpecialistCategories.get_triage_exclusions(
            config_exclusions=config_exclusions,
            current_triage_name=specialist_name
        )
        available_specialists = {
            name: conf for name, conf in configs.items()
            if name not in triage_exclusions
        }

        ecosystem_report = "\n\n--- SYSTEM CAPABILITIES ---\nThe following specialists are available to handle tasks:\n" + "\n".join(
            [f"- **{name}**: {conf.get('description', 'No description.')}" for name, conf in available_specialists.items()]
        )
        dynamic_system_prompt = f"{base_prompt}{ecosystem_report}"

        logger.debug(f"Attempting to configure adapter for '{triage_instance.specialist_name}'.")
        binding_key = triage_config.get("llm_config")
        if not binding_key:
            raise WorkflowError(f"Could not resolve LLM binding for '{specialist_name}'. Ensure it is bound in 'user_settings.yaml' or a 'default_llm_config' is set.")

        try:
            adapter = self.adapter_factory.create_adapter(specialist_name, dynamic_system_prompt)
            if adapter is None:
                logger.error(f"CRITICAL: AdapterFactory returned None for '{triage_instance.specialist_name}' with binding key '{binding_key}'.")
            triage_instance.llm_adapter = adapter
            logger.info(f"Triage specialist '{specialist_name}' adapter attached with {len(available_specialists)} specialists in ecosystem report.")
        except Exception as e:
            logger.error(f"CRITICAL: An unexpected error occurred while creating the adapter for '{triage_instance.specialist_name}': {e}", exc_info=True)
            triage_instance.llm_adapter = None

    def _add_nodes_to_graph(self, workflow: StateGraph, streaming_callback: Callable[[str], None] = None):
        # CORE-CHAT-002: Both simple and tiered chat patterns coexist in graph
        # Runtime decision in GraphOrchestrator determines which path to use

        # ADR-CORE-028: Use centralized node exclusion logic
        node_exclusions = SpecialistCategories.get_node_exclusions()

        for name, instance in self.specialists.items():
            if name in node_exclusions:
                continue

            if name == CoreSpecialist.ROUTER.value:
                workflow.add_node(name, instance.execute)
            else:
                workflow.add_node(name, self.node_executor.create_safe_executor(instance))

    def _wire_hub_and_spoke_edges(self, workflow: StateGraph):
        router_name = CoreSpecialist.ROUTER.value

        # ADR-CORE-028: Use centralized node exclusion logic
        node_exclusions = SpecialistCategories.get_node_exclusions()

        # Build destinations dict for router conditional edges
        # Include all specialists except router itself
        destinations = {
            name: name for name in self.specialists
            if name != router_name and name not in node_exclusions
        }

        # CORE-CHAT-002: chat_specialist is now always a node (both patterns coexist)
        # GraphOrchestrator will decide at runtime whether to use simple or tiered chat
        has_tiered_chat = ("progenitor_alpha_specialist" in self.specialists and
                          "progenitor_bravo_specialist" in self.specialists and
                          "tiered_synthesizer_specialist" in self.specialists)

        if has_tiered_chat:
            logger.info("Both simple and tiered chat patterns available - runtime decision in GraphOrchestrator")

        workflow.add_conditional_edges(router_name, self.orchestrator.route_to_next_specialist, destinations)

        # Delegate wiring to subgraphs
        for subgraph in self.subgraphs:
            subgraph.build(workflow)

        # ADR-CORE-028: Collect exclusions using centralized logic
        subgraph_exclusions = []
        for subgraph in self.subgraphs:
            subgraph_exclusions.extend(subgraph.get_excluded_specialists())

        excluded_specialists = SpecialistCategories.get_hub_spoke_exclusions(subgraph_exclusions)

        # ADR-CORE-061: Terminal specialists that legitimately signal completion
        # These use check_task_completion and skip Exit Interview validation
        # (conversational specialists with no success criteria to evaluate)
        terminal_specialists = SpecialistCategories.SKIP_EXIT_INTERVIEW

        # ADR-CORE-061: Build destinations for check_task_completion (terminal specialists)
        check_completion_destinations = {
            CoreSpecialist.END.value: CoreSpecialist.END.value,
            router_name: router_name
        }
        if CoreSpecialist.EXIT_INTERVIEW.value in self.specialists:
            check_completion_destinations[CoreSpecialist.EXIT_INTERVIEW.value] = CoreSpecialist.EXIT_INTERVIEW.value

        # ADR-CORE-061: Build destinations for classify_interrupt (non-terminal specialists)
        # Interrupt Classifier routes to: Exit Interview, Router, Facilitator, or End
        classify_interrupt_destinations = {
            CoreSpecialist.EXIT_INTERVIEW.value: CoreSpecialist.EXIT_INTERVIEW.value,
            CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value,
            CoreSpecialist.END.value: CoreSpecialist.END.value,
        }
        if "facilitator_specialist" in self.specialists:
            classify_interrupt_destinations["facilitator_specialist"] = "facilitator_specialist"
        # Interrupt Evaluator destination (for pathological interrupts)
        if "interrupt_evaluator_specialist" in self.specialists:
            classify_interrupt_destinations["interrupt_evaluator_specialist"] = "interrupt_evaluator_specialist"

        for name in self.specialists:
            if name in excluded_specialists:
                continue

            # ADR-CORE-061: Terminal specialists use check_task_completion
            # Non-terminal specialists use classify_interrupt
            if name in terminal_specialists:
                workflow.add_conditional_edges(
                    name,
                    self.orchestrator.check_task_completion,
                    check_completion_destinations
                )
            else:
                workflow.add_conditional_edges(
                    name,
                    self.orchestrator.classify_interrupt,
                    classify_interrupt_destinations
                )

        # ADR-ROADMAP-001 Phase 1: Exit Interview gates the END node
        # ExitInterviewSpecialist validates task completion before allowing termination
        if CoreSpecialist.EXIT_INTERVIEW.value in self.specialists:
            exit_interview_name = CoreSpecialist.EXIT_INTERVIEW.value
            # Build destinations dict - include facilitator if present for context refresh on retry
            exit_interview_destinations = {
                CoreSpecialist.END.value: CoreSpecialist.END.value,
                router_name: router_name
            }
            if "facilitator_specialist" in self.specialists:
                exit_interview_destinations["facilitator_specialist"] = "facilitator_specialist"
            workflow.add_conditional_edges(
                exit_interview_name,
                self.orchestrator.after_exit_interview,
                exit_interview_destinations
            )
            logger.info(f"Graph Edge: Added Exit Interview conditional edges (→ END, → Router, or → Facilitator)")

        if CoreSpecialist.END.value in self.specialists:
            workflow.add_edge(CoreSpecialist.END.value, END)
            logger.info(f"Graph Edge: Added final edge from {CoreSpecialist.END.value} to END.")

    def _build_convening_graph(self, streaming_callback, checkpointer) -> StateGraph:
        """
        Builds the 'Convening of the Tribes' graph (ADR-CORE-023).
        """
        workflow = StateGraph(GraphState)
        
        # 1. Add TribeConductor
        conductor_name = CoreSpecialist.TRIBE_CONDUCTOR.value
        if conductor_name in self.specialists:
            conductor = self.specialists[conductor_name]
        else:
            # Instantiate manually if not in config
            conductor = TribeConductor(conductor_name, self.config)
            
        workflow.add_node(conductor_name, conductor.execute)
        
        # 2. Add other specialists (Spokes)
        # We add all available specialists as nodes, except the old router
        for name, specialist in self.specialists.items():
            if name == CoreSpecialist.ROUTER.value: continue 
            if name == conductor_name: continue
            workflow.add_node(name, specialist.execute)
            
        # 3. Set Entry Point
        workflow.set_entry_point(conductor_name)
        
        # 4. Wire Edges
        # Conductor -> Specialists
        # We use the AgentRouter logic to determine destinations.
        router_mapping = conductor.agent_router.mapping
        destinations = list(router_mapping.values())
        
        # Also add special destinations
        destinations.extend([
            CoreSpecialist.TRIAGE_ARCHITECT.value, 
            CoreSpecialist.DIALOGUE.value, 
            CoreSpecialist.END.value
        ])
        
        # Filter destinations to only those that exist in the graph
        valid_destinations = {}
        for d in destinations:
            if d in self.specialists:
                valid_destinations[d] = d
            elif d == CoreSpecialist.END.value:
                valid_destinations[d] = END
        
        # Add explicit "end" key for fallback
        valid_destinations["end"] = END
        
        def route_from_conductor(state: GraphState):
            scratchpad = state.get("scratchpad", {})
            next_node = scratchpad.get("next_specialist")
            if next_node and next_node in valid_destinations:
                return next_node
            return "end"

        workflow.add_conditional_edges(
            conductor_name,
            route_from_conductor,
            valid_destinations
        )
        
        # Specialists -> Conductor (Return to CPU)
        for name in self.specialists:
            if name == CoreSpecialist.ROUTER.value: continue
            if name == conductor_name: continue
            
            # All specialists return to Conductor
            workflow.add_edge(name, conductor_name)
            
        # ADR-CORE-028: Use extracted compile helper
        return self._compile_graph(workflow, checkpointer, "Convening")

    def _compile_graph(self, workflow: StateGraph, checkpointer, architecture_name: str = "default"):
        """
        Compiles the workflow graph with optional checkpointer.

        Args:
            workflow: The StateGraph to compile
            checkpointer: Optional LangGraph checkpointer for HitL support
            architecture_name: Name for logging (e.g., "default", "Convening")

        Returns:
            Compiled Pregel graph

        See ADR-CORE-028 for details on this extraction.
        """
        if checkpointer:
            compiled_graph = workflow.compile(checkpointer=checkpointer)
            logger.info(
                f"---GraphBuilder: {architecture_name} Graph compiled with checkpointer "
                f"({type(checkpointer).__name__}) and entry point '{self.entry_point}'.---"
            )
        else:
            compiled_graph = workflow.compile()
            logger.info(
                f"---GraphBuilder: {architecture_name} Graph compiled successfully "
                f"with entry point '{self.entry_point}'.---"
            )
        return compiled_graph

    def _register_internal_mcp_services(self):
        """
        Registers internal MCP services that are not specialists (e.g. InferenceService).
        """
        try:
            from ..mcp.services.inference_service import InferenceService
            
            service_name = "inference_service"
            
            # Check if service is already registered (e.g. by tests)
            if hasattr(self.mcp_registry, '_services') and service_name in self.mcp_registry._services:
                return

            # Create adapter
            # AdapterFactory looks up binding by name. Ensure 'inference_service' is bound in user_settings.yaml
            adapter = self.adapter_factory.create_adapter(service_name, "")
            
            if adapter:
                service = InferenceService(llm_adapter=adapter)
                self.mcp_registry.register_service(service_name, service.get_mcp_functions())
                logger.info(f"Registered internal MCP service: {service_name}")
            else:
                # If no adapter found (e.g. no binding), we can't register the service
                # This is acceptable if the user hasn't configured it yet
                logger.debug(f"Could not create adapter for {service_name}. Service not registered.")
                
        except ImportError:
            logger.warning("Could not import InferenceService. Skipping registration.")
        except Exception as e:
            logger.error(f"Failed to register internal MCP service {service_name}: {e}")