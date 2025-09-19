import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt
from ..utils import state_pruner
from ..utils.report_schema import ErrorReport
from ..specialists import get_specialist_class, BaseSpecialist
from ..graph.state import GraphState
from ..enums import CoreSpecialist
from ..llm.factory import AdapterFactory
# Import the new strategy components
from ..strategies.critique.base import BaseCritiqueStrategy
from ..strategies.critique.llm_strategy import LLMCritiqueStrategy
from .workflow_helpers import create_safe_executor

logger = logging.getLogger(__name__)

class ChiefOfStaff:
    def __init__(self):
        self.config = ConfigLoader().get_config()
        self.adapter_factory = AdapterFactory(self.config)

        # Load specialists first, so we know which ones are available.
        self.specialists = self._load_and_configure_specialists()

        # Now, validate the entry point against the list of *loaded* specialists.
        workflow_config = self.config.get("workflow", {})
        raw_entry_point = workflow_config.get("entry_point", CoreSpecialist.ROUTER.value)
        if raw_entry_point not in self.specialists:
            logger.error(
                f"Configured entry point '{raw_entry_point}' is not an available specialist. "
                f"This can happen if it's missing from config.yaml or failed to load. "
                f"Defaulting to '{CoreSpecialist.ROUTER.value}'."
            )
            self.entry_point = CoreSpecialist.ROUTER.value
        else:
            self.entry_point = raw_entry_point

        # Configure loop detection parameters
        self.max_loop_cycles = workflow_config.get("max_loop_cycles", 3)
        # A loop can involve one or more specialists. Start detection at 1.
        self.min_loop_len = 1
        logger.info(f"Loop detection configured with max_loop_cycles={self.max_loop_cycles}")

        self.graph = self._build_graph()
        logger.info(f"---ChiefOfStaff: Graph compiled successfully with entry point '{self.entry_point}'.---")

    def _load_and_configure_specialists(self) -> Dict[str, BaseSpecialist]:
        """
        Iterates through the validated specialist configurations from ConfigLoader,
        instantiates each specialist class, and logs errors for any that fail,
        allowing the application to start with the successfully loaded specialists.
        """
        specialists_config = self.config.get("specialists", {})
        loaded_specialists: Dict[str, BaseSpecialist] = {}
        for name, config in specialists_config.items():
            try:
                SpecialistClass = get_specialist_class(name, config)
                
                if name == "critic_specialist":
                    strategy_config = config.get("critique_strategy")
                    if not strategy_config:
                        raise ValueError("CriticSpecialist config is missing required 'critique_strategy' section.")
                    
                    strategy_type = strategy_config.get("type")
                    critique_strategy_instance: BaseCritiqueStrategy

                    if strategy_type == "llm":
                        strategy_llm_binding = strategy_config.get("llm_config")
                        strategy_prompt_file = strategy_config.get("prompt_file")
                        if not (strategy_llm_binding and strategy_prompt_file):
                            raise ValueError("LLM critique_strategy requires 'llm_config' and 'prompt_file'.")
                        
                        strategy_llm_adapter = self.adapter_factory.create_adapter(strategy_llm_binding, "")
                        critique_strategy_instance = LLMCritiqueStrategy(llm_adapter=strategy_llm_adapter, prompt_file=strategy_prompt_file)
                    else:
                        raise NotImplementedError(f"Critique strategy type '{strategy_type}' is not supported.")

                    instance = SpecialistClass(specialist_name=name, specialist_config=config, critique_strategy=critique_strategy_instance)
                else:
                    instance = SpecialistClass(specialist_name=name, specialist_config=config)

                if not instance._perform_pre_flight_checks():
                    logger.error(f"Specialist '{name}' failed pre-flight checks. It will be disabled.")
                    continue

                if not instance.is_enabled:
                    logger.warning(f"Specialist '{name}' initialized but is disabled. It will not be added to the graph.")
                    continue
                
                binding_key = config.get("llm_config")
                if binding_key:
                    if name in [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value]:
                        logger.info(f"Deferring adapter creation for '{name}' to its specialized configuration method.")
                    else:
                        system_prompt = ""
                        if prompt_file := config.get("prompt_file"):
                            system_prompt = load_prompt(prompt_file)
                        if hasattr(instance, 'SYSTEM_PROMPT'):
                            system_prompt = getattr(instance, 'SYSTEM_PROMPT', system_prompt)

                        instance.llm_adapter = self.adapter_factory.create_adapter(binding_key, system_prompt)

                loaded_specialists[name] = instance
                logger.info(f"Successfully instantiated specialist: {name}")
            except Exception as e:
                logger.error(f"Failed to load specialist '{name}', it will be disabled. Error: {e}", exc_info=True)
                continue

        all_configs = self.config.get("specialists", {})
        available_configs = {name: all_configs[name] for name in loaded_specialists.keys() if name in all_configs}

        if CoreSpecialist.ROUTER.value in loaded_specialists:
            self._configure_router(loaded_specialists, available_configs)
        
        if CoreSpecialist.TRIAGE.value in loaded_specialists:
            self._configure_triage(loaded_specialists, available_configs)

        return loaded_specialists

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        logger.info("Conducting 'morning standup' to configure the router...")
        router_instance = specialists[CoreSpecialist.ROUTER.value]
        router_instance.set_specialist_map(configs)
        router_config = configs.get(CoreSpecialist.ROUTER.value, {})
        base_prompt_file = router_config.get("prompt_file")
        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""
        available_specialists = {name: conf for name, conf in configs.items() if name != CoreSpecialist.ROUTER.value}
        standup_report = "\n\n--- AVAILABLE SPECIALISTS (Morning Standup) ---\n"
        specialist_descs = [f"- {name}: {conf.get('description', 'No description available.')}" for name, conf in available_specialists.items()]
        standup_report += "\n".join(specialist_descs)
        feedback_instruction = (
            "\nIMPORTANT ROUTING INSTRUCTIONS:\n"
            "1. **Task Completion**: If the last message is a report or summary that appears to fully satisfy the user's request, your job is done. You MUST route to `__end__`.\n"
            "2. **Precondition Fulfillment**: Review the conversation history. If a specialist (e.g., 'systems_architect') previously stated it was blocked waiting for an artifact, and the most recent specialist (e.g., 'file_specialist') just provided that artifact, your next step is to route back to the original, blocked specialist.\n"
            "3. **Error Correction**: If a specialist reports an error or that it cannot perform a task, you MUST use that feedback to select a different, more appropriate specialist to resolve the issue. Do not give up.\n"
            "4. **Follow the Plan**: If a `system_plan` has just been added to the state, you MUST route to the specialist best suited to execute the next step (e.g., 'web_builder').\n"
            "5. **Use Provided Tools**: You MUST choose from the list of specialists provided to you."
        )
        dynamic_system_prompt = f"{base_prompt}{standup_report}\n{feedback_instruction}"        
        binding_key = router_config.get("llm_config")
        router_instance.llm_adapter = self.adapter_factory.create_adapter(
            binding_key=binding_key,
            system_prompt=dynamic_system_prompt
        )
        logger.info("RouterSpecialist adapter created with dynamic, context-aware prompt.")

    def _configure_triage(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        """Provides the Triage specialist with the map of all other specialists so it can make recommendations."""
        logger.info("Configuring the Triage specialist with a dynamic prompt of system capabilities...")
        triage_instance = specialists[CoreSpecialist.TRIAGE.value]

        # --- MODIFICATION: Create a complete exclusion list ---
        # The Triage specialist should only recommend specialists that can be a valid
        # *first step* in a workflow. This excludes not only other orchestrators but
        # also specialists that require a pre-existing artifact (like the critic)
        # or are part of the terminal sequence (like the synthesizer).
        excluded = [
            CoreSpecialist.ROUTER.value,
            CoreSpecialist.TRIAGE.value,
            CoreSpecialist.ARCHIVER.value,
            CoreSpecialist.RESPONSE_SYNTHESIZER.value,
            "critic_specialist", # Cannot be the first step; requires an artifact to critique.
        ]
        available_specialists = {name: conf for name, conf in configs.items() if name not in excluded}
        
        triage_instance.set_specialist_map(available_specialists)
        triage_config = configs.get(CoreSpecialist.TRIAGE.value, {})
        base_prompt_file = triage_config.get("prompt_file")
        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""
        specialist_descs = [f"- {name}: {conf.get('description', 'No description available.')}" for name, conf in available_specialists.items()]
        available_specialists_prompt = "\n".join(specialist_descs)
        dynamic_system_prompt = f"{base_prompt}\n\n--- AVAILABLE SPECIALISTS ---\nYou MUST choose one or more of the following specialists:\n{available_specialists_prompt}"
        triage_instance.llm_adapter = self.adapter_factory.create_adapter(
            binding_key=triage_config.get("llm_config"),
            system_prompt=dynamic_system_prompt
        )
        logger.info("Triage specialist adapter created with dynamic, context-aware prompt.")

    def _add_nodes_to_graph(self, workflow: StateGraph):
        """Adds all loaded specialists as nodes to the graph."""
        for name, instance in self.specialists.items():
            if name == CoreSpecialist.ROUTER.value:
                workflow.add_node(name, instance.execute)
            else:
                workflow.add_node(name, create_safe_executor(instance))

    def _wire_hub_and_spoke_edges(self, workflow: StateGraph):
        """Defines the 'hub-and-spoke' architecture for the graph."""
        router_name = CoreSpecialist.ROUTER.value
        destinations = {name: name for name in self.specialists if name != router_name}
        destinations[END] = END
        workflow.add_conditional_edges(router_name, self.decide_next_specialist, destinations)

        for name in self.specialists:
            if name in [router_name, CoreSpecialist.RESPONSE_SYNTHESIZER.value]:
                continue
            workflow.add_edge(name, router_name)

        if CoreSpecialist.RESPONSE_SYNTHESIZER.value in self.specialists:
            workflow.add_conditional_edges(
                CoreSpecialist.RESPONSE_SYNTHESIZER.value,
                self.after_synthesis_decider,
                {
                    CoreSpecialist.ARCHIVER.value: CoreSpecialist.ARCHIVER.value,
                    END: END
                }
            )
            logger.info("Graph Edge: Added explicit edge from ResponseSynthesizer to Archiver.")

    def _build_graph(self) -> StateGraph:
        """
        Builds the LangGraph StateGraph by adding nodes and defining the "hub-and-spoke"
        edge architecture.
        """
        workflow = StateGraph(GraphState)
        self._add_nodes_to_graph(workflow)
        self._wire_hub_and_spoke_edges(workflow)
        workflow.set_entry_point(self.entry_point)
        return workflow.compile()

    def after_synthesis_decider(self, state: GraphState) -> str:
        """
        Decision function that runs after the ResponseSynthesizer.
        It explicitly routes to the Archiver, enshrining the finalization sequence.
        """
        logger.info("--- ChiefOfStaff: After Synthesis. Routing to Archiver. ---")
        if CoreSpecialist.ARCHIVER.value in self.specialists:
            return CoreSpecialist.ARCHIVER.value
        else:
            return END

    def decide_next_specialist(self, state: GraphState) -> str:
        """
        This is now a pure decision function. It reads the state and returns
        the next node's name. It does not and cannot modify the state.
        """
        turn_count = state.get("turn_count", 0)
        approx_steps = (turn_count * 2) + 1
        logger.info(f"--- ChiefOfStaff: Deciding next specialist (Turn: {turn_count}, Approx. Graph Steps: {approx_steps}) ---")
        
        if (state.get("scratchpad", {}).get("web_builder_iteration", 0)) > 0:
            logger.info("Intentional refinement loop detected (web_builder_iteration > 0). Bypassing generic loop detection for this turn.")
        else:
            routing_history = state.get("routing_history", [])
            if len(routing_history) >= self.min_loop_len * self.max_loop_cycles:
                for loop_len in range(self.min_loop_len, (len(routing_history) // self.max_loop_cycles) + 1):
                    last_block = tuple(routing_history[-loop_len:])
                    is_loop = True
                    for i in range(1, self.max_loop_cycles):
                        start_index = -(i + 1) * loop_len
                        end_index = -i * loop_len
                        preceding_block = tuple(routing_history[start_index:end_index])
                        if last_block != preceding_block:
                            is_loop = False
                            break
                    if is_loop:
                        logger.error(
                            f"Unproductive loop detected. The specialist sequence '{list(last_block)}' "
                            f"has repeated {self.max_loop_cycles} times. Halting workflow."
                        )
                        return END
        
        next_specialist = state.get("next_specialist")
        logger.info(f"Router has selected next specialist: {next_specialist}")

        if next_specialist is None:
            logger.error("Routing Error: The router failed to select a next step. Halting workflow.")
            return END
        
        return next_specialist

    def get_graph(self) -> StateGraph:
        return self.graph
