# app/src/specialists/router_specialist.py

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
    next_specialist: List[str] = Field(
        ...,
        description="The specialist(s) to route to next. Can be a single specialist or multiple for parallel execution. Must be from the AVAILABLE SPECIALISTS listed in the prompt."
    )

class RouterSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self.specialist_map: Dict[str, Dict] = {}
        logger.info("Initialized RouterSpecialist (awaiting contextual configuration from GraphBuilder).")

    def set_specialist_map(self, specialist_configs: Dict[str, Dict]):
        """Receives the full map of specialist configurations from the orchestrator."""
        self.specialist_map = {k: v for k, v in specialist_configs.items() if k != self.specialist_name}
        logger.info(f"Router now aware of all specialist configurations.")

    def _get_available_specialists(self, state: Dict[str, Any]) -> Dict[str, Dict]:
        """Returns the full list of specialists available for routing.

        ADR-CORE-016: Menu Filter Pattern (Tier 1)
        - Checks scratchpad for forbidden_specialists list (populated by InvariantMonitor on loop detection)
        - Removes forbidden specialists from returned menu (hard constraint, P=0)
        - Triage recommendations remain advisory context in LLM prompt (soft constraint)

        Context-Aware Routing:
        - After context gathering complete, prevents routing back to planning specialists
        - Fixes triage → facilitator → router → triage loop

        Returns:
            Dictionary of available specialists (filtered if menu filter active)
        """
        all_specialists = self.specialist_map

        # Context-Aware Routing: Prevent routing back to planning specialists after context gathered
        gathered_context = state.get("artifacts", {}).get("gathered_context")
        if gathered_context:
            # Triage and Facilitator jobs are DONE - remove from menu to force router to pick response specialist
            # Dynamic Tag-Based Filtering
            # Only remove context_engineering specialists. 'planning' specialists like systems_architect
            # must remain available as they are valid destinations for the actual work.
            planning_specialists = [
                name for name, spec in all_specialists.items() 
                if "context_engineering" in spec.get("tags", [])
            ]

            all_specialists = {
                name: spec
                for name, spec in all_specialists.items()
                if name not in planning_specialists
            }
            logger.info(
                f"Context gathering complete - removed planning specialists {planning_specialists} from routing menu "
                f"({len(all_specialists)} specialists remain)"
            )

        # ADR-CORE-016: Check for Menu Filter activation
        scratchpad = state.get("scratchpad", {})
        forbidden_specialists = scratchpad.get("forbidden_specialists")

        if not forbidden_specialists:
            # No menu filter active - return full specialist map
            return all_specialists

        # Apply Menu Filter: Remove forbidden specialists
        filtered_specialists = {
            name: spec
            for name, spec in all_specialists.items()
            if name not in forbidden_specialists
        }

        # Safety Check: Don't return an empty menu!
        if not filtered_specialists:
            logger.error(f"Menu Filter Error: All specialists forbidden ({forbidden_specialists}). Escalating to END.")
            # If we filtered everything, return only end_specialist as fallback
            # This should trigger circuit breaker in practice, but prevents hard crash
            return {CoreSpecialist.END.value: all_specialists.get(CoreSpecialist.END.value, {})}

        logger.info(f"Menu Filter active: Removed {forbidden_specialists} from routing options ({len(filtered_specialists)} specialists remain)")
        return filtered_specialists

    def _handle_llm_failure(self) -> Dict[str, Any]:
        """Provides a robust fallback mechanism if the LLM fails to make a decision."""
        logger.error("Router LLM failed to produce a valid tool call. Attempting to fall back to a default handler.")
        if CoreSpecialist.DEFAULT_RESPONDER.value in self.specialist_map:
            next_specialist = CoreSpecialist.DEFAULT_RESPONDER.value
            content = "Router failed to select a valid next specialist. Routing to DefaultResponderSpecialist."
        elif CoreSpecialist.ARCHIVER.value in self.specialist_map:
            next_specialist = CoreSpecialist.ARCHIVER.value
            content = "Router failed to select a valid next specialist. Routing to ArchiverSpecialist for a final report."
        else:
            next_specialist = END
            content = "Router failed to select a valid next specialist and no fallback handlers are available. Routing to EndSpecialist."
        return {"next_specialist": next_specialist, "tool_calls": [], "content": content}

    def _validate_llm_choice(self, llm_choice: str | List[str], valid_options: List[str]) -> str | List[str]:
        """Ensures the LLM's choice is a valid, available specialist."""
        if isinstance(llm_choice, list):
            validated_list = []
            for choice in llm_choice:
                if choice in valid_options:
                    validated_list.append(choice)
                else:
                    logger.warning(f"Router LLM returned an invalid specialist in list: '{choice}'. Valid options are {valid_options}.")
            
            if not validated_list:
                logger.warning("All choices in the list were invalid. Falling back to DefaultResponder.")
                return CoreSpecialist.DEFAULT_RESPONDER.value
            
            if len(validated_list) == 1:
                return validated_list[0]
            return validated_list

        if llm_choice not in valid_options:
            logger.warning(f"Router LLM returned an invalid specialist: '{llm_choice}'. Valid options are {valid_options}. Falling back to DefaultResponder.")
            return CoreSpecialist.DEFAULT_RESPONDER.value
        return llm_choice

    def _get_llm_choice(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes the LLM to get the next specialist and returns the validated decision."""
        messages: List[BaseMessage] = state["messages"][:]  # Make a copy
        current_specialists = self._get_available_specialists(state)

        if not current_specialists:
            logger.warning("Router has no specialists to choose from. Ending workflow.")
            return {"next_specialist": END, "content": "No specialists available to route to. Ending workflow."}

        # Build the list of all available specialists
        available_tools_desc = [f"- {name}: {conf.get('description', 'No description.')}" for name, conf in current_specialists.items()]
        tools_list_str = "\n".join(available_tools_desc)

        # Check if context gathering is complete
        gathered_context = state.get("artifacts", {}).get("gathered_context")
        context_gathering_note = ""
        if gathered_context:
            context_gathering_note = "\n\n**CONTEXT GATHERING COMPLETE**\nThe triage and facilitator specialists have finished gathering context. They are no longer available in the menu. Please choose a specialist to respond to the user's request based on the gathered context."

        # Check for specialist recommendations (could be from triage or from another specialist)
        # Task 2.7: recommended_specialists moved to scratchpad
        recommended_specialists = state.get("scratchpad", {}).get("recommended_specialists")
        routing_history = state.get("routing_history", [])
        recommendation_context = ""

        # CRITICAL: Filter recommendations to only include specialists that are currently available
        # Prevents LLM from choosing excluded specialists (e.g., planning specialists after context gathered)
        if recommended_specialists:
            available_specialist_names = set(current_specialists.keys())
            filtered_recommendations = [s for s in recommended_specialists if s in available_specialist_names]

            if not filtered_recommendations:
                # All recommendations were filtered out - don't show recommendation context
                logger.info(f"All recommended specialists {recommended_specialists} were filtered out (not in available menu)")
                recommended_specialists = None
            else:
                recommended_specialists = filtered_recommendations
                if len(filtered_recommendations) < len(state.get("scratchpad", {}).get("recommended_specialists", [])):
                    original = state.get("scratchpad", {}).get("recommended_specialists", [])
                    filtered_out = set(original) - set(filtered_recommendations)
                    logger.info(f"Filtered out unavailable recommendations: {filtered_out}. Remaining: {filtered_recommendations}")

        if recommended_specialists:
            # Determine if this is a triage suggestion or a specialist dependency
            # Check if the last specialist that ran (excluding router/triage/facilitator) is making this recommendation
            is_specialist_dependency = False
            recommending_specialist = None

            # Exclude planning specialists from dependency detection
            # Recommendations from triage_architect or facilitator_specialist should always be treated as advisory
            # Dynamic Tag-Based Filtering
            planning_specialists = [self.specialist_name] + [
                name for name, spec in self.specialist_map.items() 
                if "planning" in spec.get("tags", []) or "context_engineering" in spec.get("tags", [])
            ]

            if routing_history:
                # Find the last specialist that ran (not router, not planning specialists)
                for spec in reversed(routing_history):
                    if spec not in planning_specialists:
                        recommending_specialist = spec
                        is_specialist_dependency = True
                        break

            if is_specialist_dependency:
                # This is a specialist stating a hard dependency requirement
                # Format: If only one dependency, be explicit about routing to it
                if len(recommended_specialists) == 1:
                    target = recommended_specialists[0]
                    recommendation_context = f"\n\n**Dependency Requirement:**\n\nThe '{recommending_specialist}' specialist cannot proceed without artifacts from '{target}'. Please route to '{target}' next to satisfy this dependency.\n\n(Note: Routing back to '{recommending_specialist}' before running '{target}' will result in the same failure.)"
                else:
                    recommendation_context = f"\n\n**Dependency Requirement:**\n\nThe '{recommending_specialist}' specialist cannot proceed without artifacts from one of the following: {', '.join(recommended_specialists)}. Please route to one of these specialists to satisfy this dependency.\n\n(Note: Routing back to '{recommending_specialist}' before satisfying this dependency will result in the same failure.)"
                logger.warning(f"Specialist '{recommending_specialist}' has dependency on: {recommended_specialists}")
            else:
                # This is from triage - treat as advisory suggestion
                recommendation_context = f"\n\n**TRIAGE SUGGESTIONS (ADVISORY, NOT MANDATORY)**:\nThe triage specialist recommends considering these specialists: {', '.join(recommended_specialists)}.\nThese are suggestions based on initial analysis. You may choose a different specialist if you have stronger reasoning."
                logger.info(f"Triage provided advisory recommendations: {recommended_specialists}")

        # Check for uploaded image (Blind Router Support)
        # If the router is text-only, it won't see the image. We must explicitly tell it.
        if state.get("artifacts", {}).get("uploaded_image.png"):
            # Dynamic Tag-Based Filtering
            vision_candidates = [
                name for name, spec in current_specialists.items() 
                if "vision_capable" in spec.get("tags", [])
            ]
            if vision_candidates:
                recommendation_context += f"\n\n**CRITICAL: IMAGE DETECTED**\nThe user has uploaded an image. You cannot see it, but it is available in the artifacts. You MUST route to a specialist capable of vision analysis. Recommended: {', '.join(vision_candidates)}."
            else:
                recommendation_context += "\n\n**CRITICAL: IMAGE DETECTED**\nThe user has uploaded an image. You cannot see it. Please route to a specialist that can handle images."

        # Put CRITICAL dependency requirements FIRST, before specialist list
        # This ensures LLM sees it before making a decision
        contextual_prompt_addition = f"{context_gathering_note}{recommendation_context}\n\nBased on the current context, you MUST choose a specialist from the following list:\n{tools_list_str}"

        final_messages = messages + [SystemMessage(content=contextual_prompt_addition)]

        request = StandardizedLLMRequest(messages=final_messages, tools=[Route], force_tool_call=True)
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        next_specialist_from_llm = tool_calls[0]['args'].get('next_specialist') if tool_calls and tool_calls[0].get('args') else None
        if not next_specialist_from_llm:
            return self._handle_llm_failure()

        validated_choice = self._validate_llm_choice(next_specialist_from_llm, list(current_specialists.keys()))

        # Diagnostic logging for Thought Stream visibility
        available_specialists_list = list(current_specialists.keys())[:5]  # Show first 5
        logger.info(f"Router LLM chose: {next_specialist_from_llm}, validated as: {validated_choice}")
        logger.info(f"Available specialists were: {available_specialists_list}")

        content = f"Routing to specialist: {validated_choice}"
        return {
            "next_specialist": validated_choice,
            "tool_calls": tool_calls,
            "content": content,
            "router_diagnostics": {
                "llm_choice": next_specialist_from_llm,
                "validated_choice": validated_choice,
                "available_count": len(current_specialists),
                "top_5_available": available_specialists_list
            }
        }

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        turn_count = state.get("turn_count", 0) + 1
        logger.debug(f"Executing turn {turn_count}")

        # Initialize diagnostics (populated only for LLM routing path)
        router_diagnostics = None

        if state.get("artifacts", {}).get("archive_report.md"):
            logger.info("Router: Found 'archive_report.md'. Routing to END.")
            next_specialist_name = END
            routing_type = "deterministic_end"
            content = "Workflow complete. Archive report generated."
            tool_calls = []
        else:
            llm_decision = self._get_llm_choice(state)
            next_specialist_name = llm_decision["next_specialist"]
            routing_type = "llm_decision"
            content = llm_decision["content"]
            tool_calls = llm_decision.get("tool_calls", [])
            router_diagnostics = llm_decision.get("router_diagnostics", {})

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=content,
            additional_kwargs={
                "routing_decision": next_specialist_name,
                "routing_type": routing_type,
                "tool_calls": tool_calls,
            },
        )

        logger.info(f"Router decision: Routing to {next_specialist_name} (Type: {routing_type})")

        # TASK 3.3: Initialize parallel_tasks state if routing to multiple specialists
        parallel_tasks_update = []
        if isinstance(next_specialist_name, list) and len(next_specialist_name) > 1:
            parallel_tasks_update = next_specialist_name
            logger.info(f"Router initiating parallel execution for: {parallel_tasks_update}")

        # Prepare scratchpad with diagnostics for Thought Stream visibility
        scratchpad_update = {"recommended_specialists": None}  # Task 2.7: Consume recommendations after routing
        if router_diagnostics:
            scratchpad_update["router_decision"] = f"LLM chose '{router_diagnostics.get('llm_choice')}', validated as '{router_diagnostics.get('validated_choice')}'. ({router_diagnostics.get('available_count')} specialists available)"

        return {
            "messages": [ai_message],
            "next_specialist": next_specialist_name,
            "turn_count": turn_count,
            "scratchpad": scratchpad_update,
            "parallel_tasks": parallel_tasks_update, # Task 3.3: Initialize barrier
            # NOTE: routing_history is tracked centrally by GraphOrchestrator.safe_executor
        }
