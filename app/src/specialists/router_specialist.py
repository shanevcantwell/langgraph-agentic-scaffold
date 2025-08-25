# src/specialists/router_specialist.py
import logging
from typing import Dict, Any, List, Optional
from langgraph.graph import END
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from ..enums import CoreSpecialist

logger = logging.getLogger(__name__)

class Route(BaseModel):
    # By changing from a dynamic Enum to a simple string, we generate a much simpler
    # JSON schema. This helps bypass potential bugs in the LLM server's grammar
    # engine, which can be sensitive to complex schemas with enum constraints.
    next_specialist: str = Field(
        ...,
        description=f"The specialist to route to next. Must be one of the AVAILABLE SPECIALISTS listed in the prompt, or '{END}' if the task is complete."
    )

class RouterSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        self.specialist_map: Dict[str, Dict] = {}
        logger.info("Initialized RouterSpecialist (awaiting contextual configuration from ChiefOfStaff).")

    def set_specialist_map(self, specialist_configs: Dict[str, Dict]):
        """Receives the full map of specialist configurations from the orchestrator."""
        self.specialist_map = {k: v for k, v in specialist_configs.items() if k != self.specialist_name}
        logger.info(f"Router now aware of all specialist configurations.")

    def _handle_error_signal(self, state: Dict[str, Any], turn_count: int) -> Optional[Dict[str, Any]]:
        """Checks for and handles the error flag from a failed specialist."""
        if error_message := state.get("error"):
            if CoreSpecialist.ARCHIVER.value in self.specialist_map:
                logger.error(f"Error detected in state: '{error_message}'. Routing to ArchiverSpecialist for final report.")
                ai_message = create_llm_message(
                    specialist_name=self.specialist_name,
                    llm_adapter=self.llm_adapter,
                    content=f"An error occurred: {error_message}. Routing to ArchiverSpecialist for final report.",
                    additional_kwargs={"routing_decision": CoreSpecialist.ARCHIVER.value, "routing_type": "error_signal"}
                )
                return { "messages": [ai_message], "next_specialist": CoreSpecialist.ARCHIVER.value, "turn_count": turn_count, "routing_history": [CoreSpecialist.ARCHIVER.value] }
            else:
                logger.error(f"Error detected in state: '{error_message}'. ArchiverSpecialist not available. Routing to END.")
                ai_message = create_llm_message(
                    specialist_name=self.specialist_name,
                    llm_adapter=self.llm_adapter,
                    content=f"An error occurred: {error_message}. Halting workflow.",
                    additional_kwargs={"routing_decision": END, "routing_type": "error_signal"}
                )
                return { "messages": [ai_message], "next_specialist": END, "turn_count": turn_count, "routing_history": [END] }
        return None

    def _handle_completion_signal(self, state: Dict[str, Any], turn_count: int) -> Optional[Dict[str, Any]]:
        """Checks for and handles the task_is_complete flag."""
        if state.get("task_is_complete", False):
            if CoreSpecialist.ARCHIVER.value in self.specialist_map:
                logger.info("A specialist has signaled task completion. Routing to ArchiverSpecialist for final report.")
                ai_message = create_llm_message(
                    specialist_name=self.specialist_name,
                    llm_adapter=self.llm_adapter,
                    content="Task is complete. Routing to ArchiverSpecialist for final report.",
                    additional_kwargs={"routing_decision": CoreSpecialist.ARCHIVER.value, "routing_type": "completion_signal"}
                )
                # The archiver will need the final artifacts to create its report.
                # While LangGraph's default state update is a merge, being explicit
                # here makes the data dependency clear and protects against
                # potential misconfiguration of the graph state.
                final_artifacts = {
                    "system_plan": state.get("system_plan"),
                    "html_artifact": state.get("html_artifact"),
                    "json_artifact": state.get("json_artifact"),
                    "text_to_process": state.get("text_to_process"),
                    "extracted_data": state.get("extracted_data"),
                }

                update = {
                    "messages": [ai_message],
                    "next_specialist": CoreSpecialist.ARCHIVER.value,
                    "turn_count": turn_count,
                    "task_is_complete": False,  # Consume the flag
                    "routing_history": [CoreSpecialist.ARCHIVER.value],
                    "recommended_specialists": None # Consume any lingering recommendations
                }
                update.update({k: v for k, v in final_artifacts.items() if v is not None})
                return update
            else:
                logger.info("A specialist has signaled task completion, but ArchiverSpecialist is not available. Routing to END.")
                return {"next_specialist": END, "turn_count": turn_count, "routing_history": [END]}
        return None

    def _handle_deterministic_recommendation(self, state: Dict[str, Any], turn_count: int) -> Optional[Dict[str, Any]]:
        """Checks for and handles a single, deterministic specialist recommendation."""
        recommended_specialists = state.get("recommended_specialists")
        if recommended_specialists and len(recommended_specialists) == 1:
            next_specialist = recommended_specialists[0]
            if next_specialist in self.specialist_map:
                logger.info(f"Using deterministic recommendation for next specialist: {next_specialist}")
                ai_message = create_llm_message(
                    specialist_name=self.specialist_name,
                    llm_adapter=self.llm_adapter,
                    content=f"Proceeding with recommended specialist: {next_specialist}",
                    additional_kwargs={"routing_decision": next_specialist, "routing_type": "recommendation"}
                )
                return {
                    "messages": [ai_message],
                    "next_specialist": next_specialist,
                    "turn_count": turn_count,
                    "recommended_specialists": None,  # Consume the recommendation
                    "routing_history": [next_specialist]
                }
            else:
                logger.warning(f"Ignoring invalid recommendation for specialist: {next_specialist}")
        return None

    def _get_llm_choice(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes the LLM to get the next specialist and returns the validated decision."""
        messages: List[BaseMessage] = state["messages"][:]  # Make a copy
        recommended_specialists = state.get("recommended_specialists")

        if recommended_specialists:
            current_specialists = {name: self.specialist_map[name] for name in recommended_specialists if name in self.specialist_map}
            logger.info(f"Filtering router choices based on Triage recommendations: {list(current_specialists.keys())}")
        else:
            current_specialists = self.specialist_map

        if not current_specialists:
            logger.warning("Router has no specialists to choose from after filtering. Ending workflow.")
            return {"next_specialist": END, "ai_message_content": "No specialists available to route to. Ending workflow."}

        available_tools_desc = [f"- {name}: {conf.get('description', 'No description.')}" for name, conf in current_specialists.items()]
        tools_list_str = "\n".join(available_tools_desc)
        contextual_prompt_addition = f"Based on the current context, you MUST choose a specialist from the following list:\n{tools_list_str}"
        
        final_messages = messages + [SystemMessage(content=contextual_prompt_addition)]

        request = StandardizedLLMRequest(messages=final_messages, tools=[Route])
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls or not tool_calls[0].get('args'):
            logger.warning("Router LLM did not return a valid tool call.")
            # Instead of immediately ending, try to gracefully fallback to a generalist.
            if CoreSpecialist.PROMPT.value in self.specialist_map:
                logger.warning(f"Falling back to '{CoreSpecialist.PROMPT.value}' for a conversational response.")
                return {"next_specialist": CoreSpecialist.PROMPT.value, "tool_calls": [], "ai_message_content": "I am having trouble deciding the next step. I will consult the general prompt specialist."}
            
            # If no fallback is available, then end.
            logger.warning("No fallback specialist available. Ending workflow.")
            return {"next_specialist": END, "tool_calls": [], "ai_message_content": "Router failed to select a valid next specialist and no fallback is available. Ending workflow."}
        
        next_specialist_from_llm = tool_calls[0]['args'].get('next_specialist', END)
        
        # Validate the choice
        valid_options = list(current_specialists.keys())
        if next_specialist_from_llm not in valid_options and next_specialist_from_llm != END:
            logger.warning(f"Router LLM returned an invalid specialist: '{next_specialist_from_llm}'. Valid options are {valid_options + [END]}. Routing to END.")
            return {"next_specialist": END, "tool_calls": tool_calls, "ai_message_content": f"Router attempted to route to an unknown specialist '{next_specialist_from_llm}'. Halting workflow."}
        
        return {"next_specialist": next_specialist_from_llm, "tool_calls": tool_calls}

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        turn_count = state.get("turn_count", 0) + 1
        logger.debug(f"Executing turn {turn_count}")

        # Priority 1: Handle error state from a failed specialist
        if (error_result := self._handle_error_signal(state, turn_count)):
            return error_result

        # Priority 2: Handle task completion signal
        if (completion_result := self._handle_completion_signal(state, turn_count)):
            return completion_result

        # Priority 3: Handle deterministic recommendation
        if (recommendation_result := self._handle_deterministic_recommendation(state, turn_count)):
            return recommendation_result

        # Priority 4: Fallback to LLM-based routing
        llm_decision = self._get_llm_choice(state)
        next_specialist_name = llm_decision["next_specialist"]
        tool_calls = llm_decision.get("tool_calls", [])
        
        if "ai_message_content" in llm_decision:
            content = llm_decision["ai_message_content"]
        else:
            content = f"Routing to specialist: {next_specialist_name}" if next_specialist_name != END else "Task is complete. Routing to END."

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=content,
            additional_kwargs={
                "routing_decision": next_specialist_name,
                "routing_type": "llm_decision",
                "tool_calls": tool_calls,
            },
        )

        logger.info(f"Router decision: Routing to {next_specialist_name}")

        return {
            "messages": [ai_message],
            "next_specialist": next_specialist_name,
            "turn_count": turn_count,
            "recommended_specialists": None,
            "routing_history": [next_specialist_name]
        }
