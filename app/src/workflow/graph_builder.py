# app/src/workflow/graph_builder.py
import logging
from typing import Dict, Any

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
        self.specialists = self._load_and_configure_specialists()
        self.orchestrator = GraphOrchestrator(self.config, self.specialists)

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

    def build(self) -> StateGraph:
        """
        Builds and compiles the LangGraph StateGraph instance.
        """
        workflow = StateGraph(GraphState)
        self._add_nodes_to_graph(workflow)
        self._wire_hub_and_spoke_edges(workflow)
        workflow.set_entry_point(self.entry_point)
        compiled_graph = workflow.compile()
        logger.info(f"---GraphBuilder: Graph compiled successfully with entry point '{self.entry_point}'.---")
        return compiled_graph

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
                        strategy_llm_binding = config.get("llm_config")
                        strategy_prompt_file = strategy_config.get("prompt_file")
                        if not (strategy_llm_binding and strategy_prompt_file):
                            raise ValueError("LLM critique_strategy requires 'llm_config' and 'prompt_file'.")
                        
                        strategy_llm_adapter = self.adapter_factory.create_adapter(strategy_llm_binding, "")
                        critique_strategy_instance = LLMCritiqueStrategy(llm_adapter=strategy_llm_adapter, prompt_file=strategy_prompt_file)
                    else:
                        raise NotImplementedError(f"Critique strategy type '{strategy_type}' is not supported.")

                    instance = SpecialistClass(specialist_name=name, specialist_config=config, critique_strategy=critique_strategy_instance)
                elif name == "end_specialist":
                    end_specialist_deps = {
                        "response_synthesizer_specialist": specialists_config.get("response_synthesizer_specialist", {}),
                        "archiver_specialist": specialists_config.get("archiver_specialist", {}),
                    }
                    instance = SpecialistClass(specialist_name=name, specialist_config=end_specialist_deps, adapter_factory=self.adapter_factory)
                else:
                    instance = SpecialistClass(specialist_name=name, specialist_config=config)

                if not instance._perform_pre_flight_checks() or not instance.is_enabled:
                    logger.warning(f"Specialist '{name}' failed pre-flight checks or is disabled. It will not be loaded.")
                    continue
                
                binding_key = config.get("llm_config")
                if binding_key and name not in [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value]:
                    system_prompt = ""
                    if prompt_file := config.get("prompt_file"):
                        system_prompt = load_prompt(prompt_file)
                    if hasattr(instance, 'SYSTEM_PROMPT'):
                        system_prompt = getattr(instance, 'SYSTEM_PROMPT', system_prompt)
                    instance.llm_adapter = self.adapter_factory.create_adapter(binding_key, system_prompt)

                loaded_specialists[name] = instance
                logger.info(f"Successfully instantiated specialist: {name}")
            except (ImportError, IOError) as e:
                # Re-raise as a specific, catchable error for testing and clarity
                raise SpecialistLoadError(f"Could not load specialist '{name}' due to: {e}") from e
            except Exception as e:
                logger.error(f"An unexpected error occurred while loading specialist '{name}', it will be disabled. Error: {e}", exc_info=True)
                continue

        all_configs = self.config.get("specialists", {})
        available_configs = {name: all_configs[name] for name in loaded_specialists.keys() if name in all_configs}

        if CoreSpecialist.ROUTER.value in loaded_specialists:
            self._configure_router(loaded_specialists, available_configs)
        
        if CoreSpecialist.TRIAGE.value in loaded_specialists:
            self._configure_triage(loaded_specialists, available_configs)

        return loaded_specialists

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        router_instance = specialists[CoreSpecialist.ROUTER.value]
        router_instance.set_specialist_map(configs)
        router_config = configs.get(CoreSpecialist.ROUTER.value, {})
        base_prompt = load_prompt(router_config.get("prompt_file", ""))
        available_specialists = {name: conf for name, conf in configs.items() if name != CoreSpecialist.ROUTER.value}
        standup_report = "\n\n--- AVAILABLE SPECIALISTS (Morning Standup) ---\n" + "\n".join([f"- {name}: {conf.get('description', 'No description.')}" for name, conf in available_specialists.items()])
        feedback_instruction = (
            "\nIMPORTANT ROUTING INSTRUCTIONS:\n"
            "1. **Precondition Fulfillment**: Review the conversation history. If a specialist (e.g., 'systems_architect') previously stated it was blocked waiting for an artifact, and the most recent specialist (e.g., 'file_specialist') just provided that artifact, your next step is to route back to the original, blocked specialist.\n"
            "2. **Error Correction**: If a specialist reports an error or that it cannot perform a task, you MUST use that feedback to select a different, more appropriate specialist to resolve the issue. Do not give up.\n"
            "3. **Follow the Plan**: If a `system_plan` has just been added to the state, you MUST route to the specialist best suited to execute the next step (e.g., 'web_builder').\n"
            "4. **Use Provided Tools**: You MUST choose from the list of specialists provided to you."
        )
        dynamic_system_prompt = f"{base_prompt}{standup_report}\n{feedback_instruction}"
        router_instance.llm_adapter = self.adapter_factory.create_adapter(router_config.get("llm_config"), dynamic_system_prompt)
        logger.info("RouterSpecialist adapter created with dynamic, context-aware prompt.")

    def _configure_triage(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        triage_instance = specialists[CoreSpecialist.TRIAGE.value]
        excluded = [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value, CoreSpecialist.ARCHIVER.value, CoreSpecialist.RESPONSE_SYNTHESIZER.value, CoreSpecialist.END.value, "critic_specialist"]
        available_specialists = {name: conf for name, conf in configs.items() if name not in excluded}
        triage_instance.set_specialist_map(available_specialists)
        triage_config = configs.get(CoreSpecialist.TRIAGE.value, {})
        base_prompt = load_prompt(triage_config.get("prompt_file", ""))
        specialist_descs = "\n".join([f"- {name}: {conf.get('description', 'No description.')}" for name, conf in available_specialists.items()])
        dynamic_system_prompt = f"{base_prompt}\n\n--- AVAILABLE SPECIALISTS ---\nYou MUST choose one or more of the following specialists:\n{specialist_descs}"
        triage_instance.llm_adapter = self.adapter_factory.create_adapter(triage_config.get("llm_config"), dynamic_system_prompt)
        logger.info("Triage specialist adapter created with dynamic, context-aware prompt.")

    def _add_nodes_to_graph(self, workflow: StateGraph):
        for name, instance in self.specialists.items():
            if name == CoreSpecialist.ROUTER.value:
                workflow.add_node(name, instance.execute)
            else:
                workflow.add_node(name, self.orchestrator.create_safe_executor(instance))

    def _wire_hub_and_spoke_edges(self, workflow: StateGraph):
        router_name = CoreSpecialist.ROUTER.value
        destinations = {name: name for name in self.specialists if name != router_name}
        workflow.add_conditional_edges(router_name, self.orchestrator.route_to_next_specialist, destinations)

        for name in self.specialists:
            if name in [router_name, CoreSpecialist.RESPONSE_SYNTHESIZER.value, CoreSpecialist.ARCHIVER.value, CoreSpecialist.END.value, CoreSpecialist.CRITIC.value]:
                continue
            workflow.add_conditional_edges(name, self.orchestrator.check_task_completion, {CoreSpecialist.END.value: CoreSpecialist.END.value, router_name: router_name})

        if CoreSpecialist.CRITIC.value in self.specialists:
            critic_config = self.config.get("specialists", {}).get(CoreSpecialist.CRITIC.value, {})
            revision_target = critic_config.get("revision_target", router_name)
            workflow.add_conditional_edges(
                CoreSpecialist.CRITIC.value,
                self.orchestrator.after_critique_decider,
                {revision_target: revision_target, CoreSpecialist.END.value: CoreSpecialist.END.value, router_name: router_name}
            )

        if CoreSpecialist.END.value in self.specialists:
            workflow.add_edge(CoreSpecialist.END.value, END)
            logger.info(f"Graph Edge: Added final edge from {CoreSpecialist.END.value} to END.")