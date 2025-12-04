# app/src/workflow/graph_builder.py
import logging
from typing import Dict, Any, Callable

from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt
from ..specialists import get_specialist_class, BaseSpecialist
from ..graph.state import GraphState
from ..enums import CoreSpecialist
from ..llm.factory import AdapterFactory
from ..utils.errors import SpecialistLoadError, WorkflowError
from ..strategies.critique.base import BaseCritiqueStrategy
from .graph_orchestrator import GraphOrchestrator
from .executors.node_executor import NodeExecutor
from .subgraphs.tiered_chat import TieredChatSubgraph
from .subgraphs.distillation import DistillationSubgraph
from .subgraphs.context_engineering import ContextEngineeringSubgraph
from .subgraphs.critic_loop import CriticLoopSubgraph
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

        # TASK 1.2: Build allowed destinations for route validation
        # Include all specialists except router (which can't be a routing destination)
        router_name = CoreSpecialist.ROUTER.value
        mcp_only_specialists = ["summarizer_specialist"]
        self.allowed_destinations = {
            name for name in self.specialists 
            if name != router_name and name not in mcp_only_specialists
        }

        self.orchestrator = GraphOrchestrator(self.config, self.specialists, self.allowed_destinations)
        
        # Initialize Subgraphs
        self.subgraphs = [
            TieredChatSubgraph(self.specialists, self.orchestrator, self.config),
            DistillationSubgraph(self.specialists, self.orchestrator, self.config),
            ContextEngineeringSubgraph(self.specialists, self.orchestrator, self.config),
            CriticLoopSubgraph(self.specialists, self.orchestrator, self.config),
            EmergentProjectSubgraph(self.specialists, self.orchestrator, self.config)
        ]

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

        # ADR-CORE-018: Enable checkpointing for HitL workflows
        if checkpointer:
            compiled_graph = workflow.compile(checkpointer=checkpointer)
            logger.info(f"---GraphBuilder: Graph compiled with checkpointer ({type(checkpointer).__name__}) and entry point '{self.entry_point}'.---")
        else:
            compiled_graph = workflow.compile()
            logger.info(f"---GraphBuilder: Graph compiled successfully with entry point '{self.entry_point}'.---")

        return compiled_graph

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

        # Connect to configured services
        services = external_config.get("services", {})
        for service_name, service_config in services.items():
            if not service_config.get("enabled", False):
                logger.debug(f"External MCP service '{service_name}' is disabled")
                continue

            command = service_config.get("command")
            args = service_config.get("args", [])
            required = service_config.get("required", False)

            if not command or not args:
                logger.warning(
                    f"External MCP service '{service_name}' missing command or args, skipping"
                )
                continue

            try:
                tools = await self.external_mcp_client.connect_service(
                    service_name=service_name,
                    command=command,
                    args=args
                )
                logger.info(
                    f"✓ External MCP service '{service_name}' connected successfully "
                    f"({len(tools)} tools available)"
                )

            except Exception as e:
                error_msg = (
                    f"Failed to connect external MCP service '{service_name}': {e}\n"
                    f"Command: {command} {' '.join(args)}"
                )

                if required:
                    logger.error(f"CRITICAL: {error_msg}")
                    # Cleanup any successfully connected services before failing
                    await self.external_mcp_client.cleanup()
                    raise RuntimeError(
                        f"Critical external MCP service '{service_name}' failed to start. "
                        "Application cannot continue. See logs for details."
                    ) from e
                else:
                    logger.warning(f"Optional service unavailable: {error_msg}")

        # Attach external_mcp_client to specialists that need it
        # Currently all specialists get access (they can choose whether to use it)
        for instance in self.specialists.values():
            instance.external_mcp_client = self.external_mcp_client

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

    def _attach_llm_adapter(self, specialist_instance: BaseSpecialist):
        """
        Attaches an LLM adapter to a specialist instance if it is configured to use one.
        This is the single, authoritative method for adapter attachment.
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
            specialist_instance.llm_adapter = self.adapter_factory.create_adapter(name, system_prompt)
            logger.debug(f"Attached LLM adapter to '{name}' using binding '{binding_key}'.")

    def _load_and_configure_specialists(self) -> Dict[str, BaseSpecialist]:
        specialists_config = self.config.get("specialists", {})
        loaded_specialists: Dict[str, BaseSpecialist] = {}
        for name, config in specialists_config.items():
            try:
                SpecialistClass = get_specialist_class(name, config)
                
                if name == "critic_specialist":
                    from ..strategies.critique.llm_strategy import LLMCritiqueStrategy
                    strategy_config = config.get("critique_strategy")
                    if not strategy_config:
                        raise ValueError("CriticSpecialist config is missing required 'critique_strategy' section.")
                    
                    strategy_type = strategy_config.get("type")
                    if strategy_type == "llm":
                        logger.debug("CriticSpecialist: Found LLM critique strategy. Configuring...")
                        strategy_llm_binding = config.get("llm_config")
                        strategy_prompt_file = strategy_config.get("prompt_file")
                        if not (strategy_llm_binding and strategy_prompt_file):
                            raise ValueError("LLM critique_strategy requires 'llm_config' and 'prompt_file'.")
                        
                        logger.debug(f"CriticSpecialist: Creating internal adapter for strategy using specialist name '{name}'.")
                        strategy_llm_adapter = self.adapter_factory.create_adapter(name, "") # Pass specialist name
                        if not strategy_llm_adapter: # pragma: no cover
                            logger.error(f"CRITICAL: AdapterFactory returned None for CriticSpecialist's internal strategy adapter.")
                        critique_strategy_instance = LLMCritiqueStrategy(llm_adapter=strategy_llm_adapter, prompt_file=strategy_prompt_file)
                    else:
                        raise NotImplementedError(f"Critique strategy type '{strategy_type}' is not supported.")

                    instance = SpecialistClass(specialist_name=name, specialist_config=config, critique_strategy=critique_strategy_instance)
                
                elif name == "web_specialist":
                    # TASK: Inject Search Strategy
                    from ..strategies.search.duckduckgo_strategy import DuckDuckGoSearchStrategy
                    # TODO: Read from config to allow switching strategies (e.g. Tavily, Google)
                    # For now, default to DuckDuckGo
                    search_strategy_instance = DuckDuckGoSearchStrategy()
                    instance = SpecialistClass(specialist_name=name, specialist_config=config, search_strategy=search_strategy_instance)

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

        try:
            if CoreSpecialist.ROUTER.value in loaded_specialists:
                self._configure_router(loaded_specialists, all_configs)
        except (IOError, FileNotFoundError) as e:
            raise SpecialistLoadError(f"Could not load specialist '{CoreSpecialist.ROUTER.value}' due to a prompt loading error: {e}") from e
        
        if CoreSpecialist.TRIAGE.value in loaded_specialists:
            self._configure_triage(loaded_specialists, all_configs)

        # --- Context Engineering Ecosystem ---
        # TriageArchitect is now a distinct specialist from prompt_triage_specialist
        if "triage_architect" in loaded_specialists:
            # No special configuration needed for now, uses standard prompt loading
            pass

        # Now that all specialists, including router/triage, have their final
        # configurations, iterate through and attach adapters. This loop will
        # only attach adapters to specialists that don't already have one.
        # This is crucial because deferred configuration methods like _configure_router
        # and _configure_triage have already attached adapters with dynamic,
        # context-aware prompts. This check prevents this generic loop from
        # overwriting those specialized adapters.
        for instance in loaded_specialists.values():
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

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        router_instance = specialists[CoreSpecialist.ROUTER.value]
        router_config = configs.get(CoreSpecialist.ROUTER.value, {})
        base_prompt = load_prompt(router_config.get("prompt_file", ""))

        # CORE-CHAT-002: Exclude tiered chat subgraph components from router's tool choices
        # They are triggered via hardcoded routing logic in GraphOrchestrator, not LLM decision
        excluded_from_router = [
            CoreSpecialist.ROUTER.value,
            "progenitor_alpha_specialist",   # Internal to tiered chat subgraph
            "progenitor_bravo_specialist",   # Internal to tiered chat subgraph
            "tiered_synthesizer_specialist", # Internal to tiered chat subgraph
            "file_specialist",               # MCP-only service layer - use file_operations_specialist for user requests
            "summarizer_specialist",         # MCP-only specialist (Task 5.3) - no graph routing
            # DISTILLATION SUBGRAPH: Exclude internal specialists from router
            "distillation_prompt_expander_specialist",   # Internal to distillation subgraph
            "distillation_prompt_aggregator_specialist", # Internal to distillation subgraph
            "distillation_response_collector_specialist" # Internal to distillation subgraph
        ]
        available_specialists = {name: conf for name, conf in configs.items() if name not in excluded_from_router}
        router_instance.set_specialist_map(available_specialists)
        standup_report = "\n\n--- AVAILABLE SPECIALISTS ---\n" + "\n".join([f"- {name}: {conf.get('description', 'No description.')}" for name, conf in available_specialists.items()])
        feedback_instruction = (
            "\nIMPORTANT ROUTING INSTRUCTIONS:\n"
            "1. **Precondition Fulfillment**: Review the conversation history. If a specialist (e.g., 'systems_architect') previously stated it was blocked waiting for an artifact, and the most recent specialist (e.g., 'file_specialist') just provided that artifact, your next step is to route back to the original, blocked specialist.\n"
            "2. **Error Correction**: If a specialist reports an error or that it cannot perform a task, you MUST use that feedback to select a different, more appropriate specialist to resolve the issue. Do not give up.\n"
            "3. **Follow the Plan**: If a `system_plan` has just been added to the state, you MUST route to the specialist best suited to execute the next step (e.g., 'web_builder').\n"
            "4. **Use Provided Tools**: You MUST choose from the list of specialists provided to you."
        )
        dynamic_system_prompt = f"{base_prompt}{standup_report}\n{feedback_instruction}"
        binding_key = router_config.get("llm_config")
        if not binding_key:
            raise WorkflowError(f"Could not resolve LLM binding for '{CoreSpecialist.ROUTER.value}'. Ensure it is bound in 'user_settings.yaml' or a 'default_llm_config' is set.")
        
        router_instance.llm_adapter = self.adapter_factory.create_adapter(CoreSpecialist.ROUTER.value, dynamic_system_prompt)
        logger.info("RouterSpecialist adapter attached with dynamic, context-aware prompt.")

    def _configure_triage(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        triage_instance = specialists[CoreSpecialist.TRIAGE.value]
        triage_config = configs.get(CoreSpecialist.TRIAGE.value, {})
        base_prompt = load_prompt(triage_config.get("prompt_file", ""))
        excluded = [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value, CoreSpecialist.ARCHIVER.value, CoreSpecialist.END.value, CoreSpecialist.CRITIC.value]
        available_specialists = {name: conf for name, conf in configs.items() if name not in excluded}
        triage_instance.set_specialist_map(available_specialists)
        specialist_descs = "\n".join([f"- {name}: {conf.get('description', 'No description.')}" for name, conf in available_specialists.items()])
        dynamic_system_prompt = f"{base_prompt}\n\n--- AVAILABLE SPECIALISTS ---\nYou MUST choose one or more of the following specialists:\n{specialist_descs}"
        
        logger.debug(f"Attempting to configure adapter for '{triage_instance.specialist_name}'.")
        binding_key = triage_config.get("llm_config")
        if not binding_key:
            raise WorkflowError(f"Could not resolve LLM binding for '{CoreSpecialist.TRIAGE.value}'. Ensure it is bound in 'user_settings.yaml' or a 'default_llm_config' is set.")
        
        try:
            adapter = self.adapter_factory.create_adapter(CoreSpecialist.TRIAGE.value, dynamic_system_prompt)
            if adapter is None:
                logger.error(f"CRITICAL: AdapterFactory returned None for '{triage_instance.specialist_name}' with binding key '{binding_key}'.")
            triage_instance.llm_adapter = adapter
            logger.info(f"Triage specialist adapter attached with dynamic, context-aware prompt. Adapter is {'present' if adapter else 'MISSING'}.")
        except Exception as e:
            logger.error(f"CRITICAL: An unexpected error occurred while creating the adapter for '{triage_instance.specialist_name}': {e}", exc_info=True)
            triage_instance.llm_adapter = None

    def _add_nodes_to_graph(self, workflow: StateGraph, streaming_callback: Callable[[str], None] = None):
        # CORE-CHAT-002: Both simple and tiered chat patterns coexist in graph
        # Runtime decision in GraphOrchestrator determines which path to use
        
        # MCP-only specialists that should not be graph nodes
        mcp_only_specialists = ["summarizer_specialist"]

        for name, instance in self.specialists.items():
            if name in mcp_only_specialists:
                continue

            if name == CoreSpecialist.ROUTER.value:
                workflow.add_node(name, instance.execute)
            else:
                workflow.add_node(name, self.node_executor.create_safe_executor(instance))

    def _wire_hub_and_spoke_edges(self, workflow: StateGraph):
        router_name = CoreSpecialist.ROUTER.value
        mcp_only_specialists = ["summarizer_specialist"]

        # Build destinations dict for router conditional edges
        # Include all specialists except router itself
        destinations = {
            name: name for name in self.specialists 
            if name != router_name and name not in mcp_only_specialists
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

        # Collect excluded specialists from all subgraphs
        excluded_specialists = [
            router_name,
            CoreSpecialist.ARCHIVER.value,
            CoreSpecialist.END.value,
            CoreSpecialist.CRITIC.value,
            "summarizer_specialist", # MCP-only
        ]
        
        for subgraph in self.subgraphs:
            excluded_specialists.extend(subgraph.get_excluded_specialists())

        for name in self.specialists:
            if name in excluded_specialists:
                continue

            workflow.add_conditional_edges(name, self.orchestrator.check_task_completion, {CoreSpecialist.END.value: CoreSpecialist.END.value, router_name: router_name})

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
            
        # Compile
        if checkpointer:
            compiled_graph = workflow.compile(checkpointer=checkpointer)
            logger.info(f"---GraphBuilder: Convening Graph compiled with checkpointer ({type(checkpointer).__name__}).---")
        else:
            compiled_graph = workflow.compile()
            logger.info(f"---GraphBuilder: Convening Graph compiled successfully.---")

        return compiled_graph