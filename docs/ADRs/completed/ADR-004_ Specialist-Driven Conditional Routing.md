### **Specialist-Driven Conditional Routing**

* **Status:** Completed  
* **Date:** 2025-09-18  
* **Author:** Senior Systems Architect

### 1. Context

The current workflow for artifact refinement (e.g., `SystemsArchitect` -> `WebBuilder` -> `CriticSpecialist`) is defined implicitly by the `RouterSpecialist`'s LLM-based reasoning. This creates a rigid, pre-ordained loop. The system lacks a mechanism for a specialist to act as an autonomous "gatekeeper," making a firm decision that directly alters the graph's path. This places an excessive inferential burden on the `Router` and prevents the creation of more dynamic, state-driven workflows where an artifact's quality can determine the next step (e.g., "Is this good enough to show the user, or does it need more work?").

To mature the architecture, we need a pattern that allows for conditional branching based on the explicit, structured output of a specialist, with the branching logic itself being defined declaratively in the system's configuration.

### 2. Decision

We will introduce the **Specialist-Driven Conditional Routing** pattern. This pattern elevates a specialist from a simple data processor to a decision-making node within the graph. The `CriticSpecialist` will be the first to implement this pattern.

The implementation consists of three coordinated parts:

1. **Specialist as Decider:** The `CriticSpecialist` will be enhanced to produce a structured, machine-readable `decision` (`ACCEPT` or `REVISE`) as part of its output, which it will write to the `scratchpad`.  
2. **Orchestrator as Wire-Puller:** The `ChiefOfStaff` will be taught to read a new `conditional_routing` flag from `config.yaml`. If this flag is present for a specialist, it will wire a conditional edge in the graph instead of the default edge back to the router.  
3. **Configuration as Blueprint:** The `config.yaml` file will be used to declaratively enable this behavior and define the target for the "revision" branch, making the workflow's structure explicit and easily modifiable.

### 3. Implementation Details

#### 3.1. Schema Enhancement (`_orchestration.py`)

The `Critique` schema, which serves as the data contract for the `CriticSpecialist`, must be updated to include the new decision field. This is the correct location as it pertains to orchestration-level feedback.

# app/src/specialists/schemas/_orchestration.py

from pydantic import BaseModel, Field

from typing import List, Literal

class TriageRecommendations(BaseModel):

    """A model for the Triage specialist's recommendations."""

    recommended_specialists: List[str] = Field(

        ...,

        description="A list of specialist names that are best suited to handle the user's request. The names MUST be chosen from the list of AVAILABLE SPECIALISTS provided in the prompt."

    )

class SystemPlan(BaseModel):

    """A model for the Systems Architect's technical plan."""

    plan_summary: str = Field(..., description="A concise, one-sentence summary of the plan.")

    required_components: List[str] = Field(..., description="A list of technologies, libraries, or assets needed.")

    execution_steps: List[str] = Field(..., description="A list of detailed, sequential steps to implement the plan.")

    refinement_cycles: int = Field(default=1, description="The number of refinement cycles (e.g., with a critic) to perform.")

class Critique(BaseModel):

    """A structured critique of a generated artifact, used by the CriticSpecialist."""

    overall_assessment: str = Field(..., description="A brief, one-paragraph summary of the critique, assessing how well the artifact meets the requirements.")

    points_for_improvement: List[str] = Field(..., description="A list of specific, actionable points of feedback for what to change or add in the next iteration.")

    positive_feedback: List[str] = Field(..., description="Specific aspects of the artifact that were well-executed and should be kept or built upon.")

    # MODIFICATION: Add a machine-readable decision field to enable conditional routing.

    decision: Literal["ACCEPT", "REVISE"] = Field(..., description="The final verdict. 'REVISE' if significant changes are needed, otherwise 'ACCEPT'.")

#### 3.2. Specialist Logic (`critic_specialist.py`)

The specialist's logic is updated to use the new schema, leverage the `create_llm_message` helper, and write its decision to the `scratchpad`. The responsibility of recommending the next specialist is removed, as this is now handled by the graph's structure.

# app/src/specialists/critic_specialist.py

import logging

from typing import Dict, Any, List

import jmespath

from .base import BaseSpecialist

from .helpers import create_llm_message, create_missing_artifact_response

from ..enums import CoreSpecialist

from ..llm.adapter import StandardizedLLMRequest

from .schemas import Critique

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)

class CriticSpecialist(BaseSpecialist):

    """

    A specialist that analyzes an HTML artifact, provides a critique for

    improvement, and makes a decision to either accept or revise the artifact.

    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):

        super().__init__(specialist_name, specialist_config)

        logger.info("---INITIALIZED CriticSpecialist---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:

        logger.info("Executing CriticSpecialist logic.")

        html_artifact = state.get("artifacts", {}).get("html_document.html")

        if not html_artifact:

            # This is a critical failure. The critic cannot operate without the HTML.

            return create_missing_artifact_response(

                specialist_name=self.specialist_name,

                missing_artifacts=["html_document.html"],

                recommended_specialists=[CoreSpecialist.WEB_BUILDER.value]

            )

        contextual_messages: List[BaseMessage] = state["messages"][:]

        contextual_messages.append(HumanMessage(

            content=f"Here is the HTML document to critique:nn```htmln{html_artifact}n```"

        ))

        request = StandardizedLLMRequest(

            messages=contextual_messages,

            output_model_class=Critique

        )

        response_data = self.llm_adapter.invoke(request)

        json_response = response_data.get("json_response")

        if not json_response:

            raise ValueError("CriticSpecialist failed to get a valid structured response from the LLM.")

        try:

            critique = Critique(**json_response)

        except Exception as e:

            logger.error(f"Pydantic validation failed for critic: {e}", exc_info=True)

            raise e

        critique_text_parts = [f"**Overall Assessment:**n{critique.overall_assessment}n"]

        if critique.points_for_improvement:

            improvement_points = "n".join([f"- {point}" for point in critique.points_for_improvement])

            critique_text_parts.append(f"**Points for Improvement:**n{improvement_points}n")

        if critique.positive_feedback:

            positive_points = "n".join([f"- {point}" for point in critique.positive_feedback])

            critique_text_parts.append(f"**What Went Well:**n{positive_points}")

        critique_text = "n".join(critique_text_parts)

        ai_message = create_llm_message(

            specialist_name=self.specialist_name,

            llm_adapter=self.llm_adapter,

            content=f"Critique complete. My decision is to **{critique.decision}** the artifact.",

        )

        # The specialist's output is now a decision placed in the scratchpad.

        # The graph's structure, not this specialist, will determine the next step.

        return {

            "messages": [ai_message],

            "artifacts": {"critique.md": critique_text},

            "scratchpad": {"critique_decision": critique.decision}

        }

#### 3.3. Orchestration Logic (`chief_of_staff.py`)

The `ChiefOfStaff` is enhanced to read the new configuration and wire the graph accordingly.

# app/src/workflow/chief_of_staff.py

import logging

import traceback

from typing import Dict, Any

from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader

from ..utils.prompt_loader import load_prompt

from ..utils import state_pruner

from ..utils.errors import SpecialistError

from ..utils.report_schema import ErrorReport

from ..specialists import get_specialist_class, BaseSpecialist

from ..graph.state import GraphState

from ..enums import CoreSpecialist

from ..llm.factory import AdapterFactory

from ..specialists.helpers import create_missing_artifact_response

logger = logging.getLogger(__name__)

class ChiefOfStaff:

    # ... __init__ and other _configure methods remain the same ...

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

                if not issubclass(SpecialistClass, BaseSpecialist):

                    logger.warning(f"Skipping '{name}': Class '{SpecialistClass.__name__}' does not inherit from BaseSpecialist.")

                    continue

                # Instantiate the specialist, injecting its name and its specific configuration block.

                # This completes the decoupling of specialists from a global config loader.

                instance = SpecialistClass(specialist_name=name, specialist_config=config)

                # --- Pre-flight Check ---

                # Immediately after instantiation, check if the specialist's dependencies are met.

                if not instance._perform_pre_flight_checks():

                    logger.error(f"Specialist '{name}' failed pre-flight checks. It will be disabled.")

                    continue

                if not instance.is_enabled:

                    logger.warning(f"Specialist '{name}' initialized but is disabled. It will not be added to the graph.")

                    continue

                

                # --- Adapter Creation ---

                # Any specialist that needs an LLM, regardless of type, gets an adapter.

                # The presence of the 'llm_config' key, added by the ConfigLoader, is the trigger.

                binding_key = config.get("llm_config")

                if binding_key:

                    # Defer adapter creation for router/triage as they have complex, dynamic prompt construction.

                    if name in [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value]:

                        logger.info(f"Deferring adapter creation for '{name}' to its specialized configuration method.")

                    else:

                        system_prompt = ""

                        if prompt_file := config.get("prompt_file"):

                            system_prompt = load_prompt(prompt_file)

                        # Allow procedural specialists to define their own hardcoded prompt via a class attribute.

                        # This was the bug: it was an elif, but it should be a separate if.

                        # A procedural specialist can have an llm_config binding AND a SYSTEM_PROMPT.

                        if hasattr(instance, 'SYSTEM_PROMPT'):

                            system_prompt = getattr(instance, 'SYSTEM_PROMPT', system_prompt)

                        instance.llm_adapter = self.adapter_factory.create_adapter(binding_key, system_prompt)

                loaded_specialists[name] = instance

                logger.info(f"Successfully instantiated specialist: {name}")

            except Exception as e:

                logger.error(f"Failed to load specialist '{name}', it will be disabled. Error: {e}", exc_info=True)

                continue # Allow the app to start with the specialists that did load correctly.

        # This is the key change: only provide the orchestration specialists (Router, Triage)

        # with a list of specialists that were *successfully* loaded. This prevents them

        # from trying to route to a specialist that is configured but failed to start.

        all_configs = self.config.get("specialists", {})

        available_configs = {name: all_configs[name] for name in loaded_specialists.keys() if name in all_configs}

        if CoreSpecialist.ROUTER.value in loaded_specialists:

            self._configure_router(loaded_specialists, available_configs)

        

        # If the Triage specialist exists, configure it with the full map of other specialists.

        if CoreSpecialist.TRIAGE.value in loaded_specialists:

            self._configure_triage(loaded_specialists, available_configs)

        return loaded_specialists

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):

        logger.info("Conducting 'morning standup' to configure the router...")

        router_instance = specialists[CoreSpecialist.ROUTER.value]

        # Provide the router with the full map of specialist configurations.

        # It will use this map at runtime to filter specialists based on the routing channel.

        router_instance.set_specialist_map(configs)

        # The static part of the router's prompt, including the full list of specialists.

        # A dynamic, filtered list may be added at runtime by the router itself.

        router_config = configs.get(CoreSpecialist.ROUTER.value, {})

        base_prompt_file = router_config.get("prompt_file")

        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""

        # The router needs to know about all other specialists for its prompt.

        available_specialists = {name: conf for name, conf in configs.items() if name != CoreSpecialist.ROUTER.value}

        standup_report = "nn--- AVAILABLE SPECIALISTS (Morning Standup) ---n"

        specialist_descs = [f"- {name}: {conf.get('description', 'No description available.')}" for name, conf in available_specialists.items()]

        standup_report += "n".join(specialist_descs)

        feedback_instruction = (

            "nIMPORTANT ROUTING INSTRUCTIONS:n"

            "1. **Task Completion**: If the last message is a report or summary that appears to fully satisfy the user's request, your job is done. You MUST route to `__end__`.n"

            "2. **Precondition Fulfillment**: Review the conversation history. If a specialist (e.g., 'systems_architect') previously stated it was blocked waiting for an artifact, and the most recent specialist (e.g., 'file_specialist') just provided that artifact, your next step is to route back to the original, blocked specialist.n"

            "3. **Error Correction**: If a specialist reports an error or that it cannot perform a task, you MUST use that feedback to select a different, more appropriate specialist to resolve the issue. Do not give up.n"

            "4. **Follow the Plan**: If a `system_plan` has just been added to the state, you MUST route to the specialist best suited to execute the next step (e.g., 'web_builder').n"

            "5. **Use Provided Tools**: You MUST choose from the list of specialists provided to you."

        )

        dynamic_system_prompt = f"{base_prompt}{standup_report}n{feedback_instruction}"        

        

        # Create the adapter from scratch with the final, complete prompt.

        # This ensures the router gets the correct configuration and prompt in one step.

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

        # The Triage specialist needs to know about all other functional specialists for its prompt.

        # Exclude orchestration specialists to prevent loops or nonsensical recommendations.

        excluded = [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value, CoreSpecialist.ARCHIVER.value]

        available_specialists = {name: conf for name, conf in configs.items() if name not in excluded}

        

        # This call is still useful for the specialist's internal logic.

        triage_instance.set_specialist_map(available_specialists)

        triage_config = configs.get(CoreSpecialist.TRIAGE.value, {})

        base_prompt_file = triage_config.get("prompt_file")

        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""

        specialist_descs = [f"- {name}: {conf.get('description', 'No description available.')}" for name, conf in available_specialists.items()]

        available_specialists_prompt = "n".join(specialist_descs)

        

        dynamic_system_prompt = f"{base_prompt}nn--- AVAILABLE SPECIALISTS ---nYou MUST choose one or more of the following specialists:n{available_specialists_prompt}"

        triage_instance.llm_adapter = self.adapter_factory.create_adapter(

            binding_key=triage_config.get("llm_config"),

            system_prompt=dynamic_system_prompt

        )

        logger.info("Triage specialist adapter created with dynamic, context-aware prompt.")

    def _create_safe_executor(self, specialist_instance: BaseSpecialist):

        """

        Creates a wrapper around a specialist's execute method to enforce global rules

        like turn count modification, declarative preconditions, and to provide

        centralized exception handling and reporting.

        """

        specialist_name = specialist_instance.specialist_name

        specialist_config = specialist_instance.specialist_config

        required_artifacts = specialist_config.get("requires_artifacts", [])

        artifact_providers = specialist_config.get("artifact_providers", {})

        def safe_executor(state: GraphState) -> Dict[str, Any]:

            # --- Declarative State Artifact Check (Runtime) ---

            if required_artifacts:

                for artifact in required_artifacts:

                    # MODIFICATION: Check for the artifact within the 'artifacts' dictionary,

                    # which is the new architectural standard.

                    if not state.get("artifacts", {}).get(artifact):

                        logger.warning(

                            f"Specialist '{specialist_name}' cannot execute. "

                            f"Missing required artifact: '{artifact}'. Bypassing execution."

                        )

                        # Look up the recommended specialist to fix this.

                        recommended_specialist = artifact_providers.get(artifact)

                        # Generate a standardized response to inform the router.

                        return create_missing_artifact_response(

                            specialist_name=specialist_name,

                            missing_artifacts=[artifact],

                            # recommended_specialist=recommended_specialist,  # does not work

                            recommended_specialists=[recommended_specialist] if recommended_specialist else [],

                        )

            try:

                update = specialist_instance.execute(state)

                if "turn_count" in update:

                    logger.warning(

                        f"Specialist '{specialist_instance.specialist_name}' returned a 'turn_count'. "

                        "This is not allowed and will be ignored to preserve the global count."

                    )

                    del update["turn_count"]

                return update

            except (SpecialistError, Exception) as e:

                logger.error(

                    f"Caught unhandled exception from specialist '{specialist_instance.specialist_name}': {e}",

                    exc_info=True

                )

                # Generate a detailed error report for debugging and user feedback.

                tb_str = traceback.format_exc()

                pruned_state = state_pruner.prune_state(state)

                routing_history = state.get("routing_history", [])

                report_data = ErrorReport(

                    error_message=str(e),

                    traceback=tb_str,

                    routing_history=routing_history,

                    pruned_state=pruned_state

                )

                markdown_report = state_pruner.generate_report(report_data)

                # Return an update that halts the graph and provides the report.

                return {

                    "error": f"Specialist '{specialist_instance.specialist_name}' failed. See report for details.",

                    "error_report": markdown_report

                }

        return safe_executor

    def _add_nodes_to_graph(self, workflow: StateGraph):

        """Adds all loaded specialists as nodes to the graph."""

        for name, instance in self.specialists.items():

            if name == CoreSpecialist.ROUTER.value:

                workflow.add_node(name, instance.execute)

            else:

                workflow.add_node(name, self._create_safe_executor(instance))

    def _wire_hub_and_spoke_edges(self, workflow: StateGraph):

        """Defines the 'hub-and-spoke' architecture for the graph."""

        router_name = CoreSpecialist.ROUTER.value

        all_specialists_config = self.config.get("specialists", {})

        workflow.add_conditional_edges(router_name, self.decide_next_specialist, {

            **{name: name for name in self.specialists if name != router_name},

            END: END

        })

        for name in self.specialists:

            if name == router_name:

                continue

            specialist_config = all_specialists_config.get(name, {})

            # MODIFICATION: Check for the new conditional_routing flag.

            if specialist_config.get("conditional_routing"):

                if name == CoreSpecialist.CRITIC.value:

                    revision_target = specialist_config.get("revision_target", router_name)

                    workflow.add_conditional_edges(

                        name,

                        self.after_critique_decider,

                        {revision_target: revision_target, router_name: router_name}

                    )

                    logger.info(f"Graph Edge: Added conditional routing for '{name}' to targets '{revision_target}' and '{router_name}'.")

                # Future conditional specialists can be added here with elif blocks.

                continue  # Skip adding the default edge back to the router.

            if name == CoreSpecialist.RESPONSE_SYNTHESIZER.value:

                workflow.add_conditional_edges(

                    name,

                    self.after_synthesis_decider,

                    {CoreSpecialist.ARCHIVER.value: CoreSpecialist.ARCHIVER.value, END: END}

                )

                logger.info("Graph Edge: Added explicit edge from ResponseSynthesizer to Archiver.")

                continue

            workflow.add_edge(name, router_name)

    def _build_graph(self) -> StateGraph:

        workflow = StateGraph(GraphState)

        self._add_nodes_to_graph(workflow)

        self._wire_hub_and_spoke_edges(workflow)

        workflow.set_entry_point(self.entry_point)

        return workflow.compile()

    # MODIFICATION: New decider function for the critic's conditional branch.

    def after_critique_decider(self, state: GraphState) -> str:

        """

        Reads the critic's decision from the scratchpad and routes to the

        configured revision target or back to the main router.

        """

        decision = state.get("scratchpad", {}).get("critique_decision")

        logger.info(f"--- ChiefOfStaff: After Critique. Decision: {decision} ---")

        critic_config = self.config.get("specialists", {}).get(CoreSpecialist.CRITIC.value, {})

        revision_target = critic_config.get("revision_target", CoreSpecialist.ROUTER.value)

        if decision == "REVISE":

            logger.info(f"Routing to configured revision target: {revision_target}")

            return revision_target

        else:  # ACCEPT or any other case

            logger.info("Critique accepted. Returning to the main router for next steps.")

            return CoreSpecialist.ROUTER.value

    def after_synthesis_decider(self, state: GraphState) -> str:

        # ... this method remains the same ...

        logger.info("--- ChiefOfStaff: After Synthesis. Routing to Archiver. ---")

        if CoreSpecialist.ARCHIVER.value in self.specialists:

            return CoreSpecialist.ARCHIVER.value

        else:

            return END

    def decide_next_specialist(self, state: GraphState) -> str:

        # ... this method remains the same ...

        turn_count = state.get("turn_count", 0)

        # The number of graph steps is roughly 2 * turn_count because of the hub-and-spoke model (Specialist -> Router).

        # This log helps clarify why a recursion limit might be reached.

        approx_steps = (turn_count * 2) + 1

        logger.info(f"--- ChiefOfStaff: Deciding next specialist (Turn: {turn_count}, Approx. Graph Steps: {approx_steps}) ---")

        

        if (state.get("scratchpad", {}).get("web_builder_iteration", 0)) > 0:

            logger.info("Intentional refinement loop detected (web_builder_iteration > 0). Bypassing generic loop detection for this turn.")

        else:

            # Check for unproductive loops to prevent the system from getting stuck.

            # This is a more intelligent safeguard than a simple max turn count.

            routing_history = state.get("routing_history", [])

            if len(routing_history) >= self.min_loop_len * self.max_loop_cycles:

                # Iterate through possible loop lengths

                for loop_len in range(self.min_loop_len, (len(routing_history) // self.max_loop_cycles) + 1):

                    # Extract the most recent block, which is our reference pattern

                    last_block = tuple(routing_history[-loop_len:])

                    is_loop = True

                    # Compare it with the preceding blocks

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

#### 3.4. Declarative Configuration (`config.yaml`)

The workflow is now defined declaratively. The `revision_target` can be changed to point to `systems_architect` to trigger a full re-planning, or to `web_builder` for a simple rebuild, all without code changes.

# in config.yaml

specialists:

  # ... other specialists

  critic_specialist:

    type: "llm"

    prompt_file: "critic_prompt.md"

    description: "Analyzes an artifact, provides a critique, and decides if revision is needed."

    requires_artifacts: ["html_document.html"]

    artifact_providers:

      html_document.html: "web_builder"

    

    # --- NEW CONFIGURATION FOR CONDITIONAL ROUTING ---

    # This flag tells the ChiefOfStaff to wire this specialist as a conditional node.

    conditional_routing: true

    # This key defines the destination for the 'REVISE' branch.

    # To re-run the builder: "web_builder"

    # To re-run the entire plan: "systems_architect"

    revision_target: "web_builder"

### 4. Consequences

**4.1. Positive**

* **Declarative Workflows:** The core logic of the refinement loop is now controlled via configuration, making the system more flexible and easier to modify without code deployments.  
* **Increased Agent Autonomy:** The `CriticSpecialist` is now a more intelligent agent that makes a meaningful decision, reducing the inferential burden on the central `Router`.  
* **Enhanced Flexibility:** The rigid, mandatory loop is broken. Workflows that do not require a critique can now bypass it entirely, allowing the `Router` to send a completed artifact directly to the `ResponseSynthesizer`.  
* **Extensible Pattern:** This `conditional_routing` pattern can be extended to other specialists (e.g., a `code_tester_specialist`) to create more complex, state-driven workflows.

**4.2. Negative & Risks**

* **Increased Orchestration Complexity:** The logic within `ChiefOfStaff` is now more complex, as it must handle both default and conditional edges. This complexity must be managed carefully as more conditional nodes are added.  
* **Implicit Contracts:** The pattern relies on an implicit contract between the specialist (which writes to `scratchpad['critique_decision']`) and the orchestrator (which reads from it). This contract should be formally documented.

### 5. Workflow Diagram

The new, dynamic workflow can be visualized as follows:

graph TD

    subgraph Main Workflow

        A[Router] --> B(SystemsArchitect);

        B --> A;

        A --> C(WebBuilder);

        A --> E(ResponseSynthesizer);

        E --> F(Archiver);

        F --> A;

        A --> G[END];

    end

    subgraph Refinement Sub-Graph

        C --> D{CriticSpecialist};

        D -- Decision: REVISE --> C;

        D -- Decision: ACCEPT --> A;

    end  
