# app/src/specialists/router_specialist.py

import logging
from typing import Dict, Any, List, Literal, Optional, Tuple, Type
from langgraph.graph import END
from pydantic import BaseModel, Field, create_model
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from ..enums import CoreSpecialist
from ..llm.tracing import (
    set_current_specialist,
    clear_current_specialist,
    flush_adapter_traces,
    build_specialist_turn_trace,
)
from ..utils.state_serializer import build_timeline_entry

logger = logging.getLogger(__name__)

class RouteResponse(BaseModel):
    """
    Simplified routing response schema.

    Uses output_model_class for JSON schema enforcement instead of tool-calling.
    This avoids the complexity of the "decoy tool" pattern that accumulated from
    Aug 2025 workarounds (d151d09) for markdown wrapping issues.
    """
    next_specialist: List[str] = Field(
        ...,
        min_length=1,  # Prevent empty arrays (Issue #136)
        description="The specialist(s) to route to next. Can be a single specialist or multiple for parallel execution. Must be from the AVAILABLE SPECIALISTS listed in the prompt."
    )

def _build_route_response_model(valid_names: List[str]) -> Type[BaseModel]:
    """Build a dynamic RouteResponse with enum-constrained specialist names.

    The JSON schema produced by this model includes an "enum" array, which
    LMStudio (and other structured-output engines) enforce at the token level.
    This prevents open-weight models from generating approximate names like
    "project" instead of "project_director".
    """
    specialist_literal = Literal[tuple(valid_names)]  # type: ignore[valid-type]
    return create_model(
        "RouteResponse",
        next_specialist=(
            List[specialist_literal],
            Field(
                ...,
                min_length=1,
                max_length=len(valid_names),
                description=(
                    "The specialist(s) to route to next. Can be a single specialist "
                    "or multiple for parallel execution. Must be from the AVAILABLE "
                    "SPECIALISTS listed in the prompt. No duplicates."
                ),
            ),
        ),
    )


class RouterSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self.specialist_map: Dict[str, Dict] = {}
        self.max_routing_retries: int = specialist_config.get("max_routing_retries", 1)
        logger.info(
            f"Initialized RouterSpecialist (max_routing_retries={self.max_routing_retries}, "
            f"awaiting contextual configuration from GraphBuilder)."
        )

    # Closed set of trivial/greeting inputs that don't need specialist work.
    # Checked before the LLM call — deterministic routing, no prompt can override.
    _TRIVIAL_INPUTS = frozenset({
        "hello", "hi", "hey", "ping", "pong", "thanks", "thank you",
        "bye", "goodbye", "test", "yo", "sup", "what's up", "whats up",
    })
    _TRIVIAL_MAX_LENGTH = 15  # Messages this short with no question mark are likely trivial

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
        logger.error("Router LLM failed to produce a valid routing response. Attempting to fall back to a default handler.")
        if CoreSpecialist.DEFAULT_RESPONDER.value in self.specialist_map:
            next_specialist = CoreSpecialist.DEFAULT_RESPONDER.value
            content = "Router failed to select a valid next specialist. Routing to DefaultResponderSpecialist."
        elif CoreSpecialist.ARCHIVER.value in self.specialist_map:
            next_specialist = CoreSpecialist.ARCHIVER.value
            content = "Router failed to select a valid next specialist. Routing to ArchiverSpecialist for a final report."
        else:
            next_specialist = END
            content = "Router failed to select a valid next specialist and no fallback handlers are available. Routing to EndSpecialist."
        return {"next_specialist": next_specialist, "content": content}

    def _validate_llm_choice(
        self, llm_choice: str | List[str], valid_options: List[str]
    ) -> Tuple[str | List[str] | None, bool]:
        """Validate the LLM's specialist choice — reject invalid, dedup, cap length.

        Returns (validated_choice, is_valid).  When any entry is invalid the
        *entire* response is rejected so the caller can retry with a correction
        message.  This prevents silent partial filtering that destroys parallel
        fan-out intent (e.g. ["project", "systems_architect"] → ["systems_architect"]).

        Duplicates are silently removed (first occurrence wins).  Lists longer
        than the available specialist count are truncated.  Both are logged at
        WARNING for observability (#219).
        """
        if isinstance(llm_choice, list):
            invalid = [c for c in llm_choice if c not in valid_options]
            if invalid:
                logger.error(
                    f"Router: Invalid specialist(s) in list: {invalid}. "
                    f"Valid: {valid_options}"
                )
                return None, False

            # Dedup: preserve order, first occurrence wins (#219)
            seen = set()
            deduped = []
            for c in llm_choice:
                if c not in seen:
                    seen.add(c)
                    deduped.append(c)
            if len(deduped) < len(llm_choice):
                logger.warning(
                    f"Router: Removed {len(llm_choice) - len(deduped)} duplicate(s) "
                    f"from LLM selection. Original: {llm_choice}, deduped: {deduped}"
                )

            # Cap at available specialist count (#219)
            max_len = len(valid_options)
            if len(deduped) > max_len:
                logger.warning(
                    f"Router: LLM selected {len(deduped)} specialists but only "
                    f"{max_len} available. Truncating to first {max_len}."
                )
                deduped = deduped[:max_len]

            return deduped, True

        if llm_choice not in valid_options:
            logger.error(
                f"Router: Invalid specialist '{llm_choice}'. "
                f"Valid: {valid_options}"
            )
            return None, False
        return llm_choice, True

    def _get_llm_choice(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes the LLM to get the next specialist and returns the validated decision."""
        messages: List[BaseMessage] = state["messages"][:]  # Make a copy
        current_specialists = self._get_available_specialists(state)

        if not current_specialists:
            logger.warning("Router has no specialists to choose from. Ending workflow.")
            return {"next_specialist": END, "content": "No specialists available to route to. Ending workflow."}

        # Check if context gathering is complete
        gathered_context = state.get("artifacts", {}).get("gathered_context")
        context_gathering_note = ""
        if gathered_context:
            context_gathering_note = "\n\n**CONTEXT GATHERING COMPLETE**\nThe triage and facilitator specialists have finished gathering context. They are no longer available in the menu. Please choose a specialist to respond to the user's request based on the gathered context."

        # Check for specialist dependency routing (from node_executor when a specialist is blocked)
        recommended_specialists = state.get("scratchpad", {}).get("recommended_specialists")
        routing_history = state.get("routing_history", [])
        recommendation_context = ""

        # Handle "not me" pattern: specialist declined the task
        # Remove the declining specialist from recommendations
        scratchpad = state.get("scratchpad", {})
        if scratchpad.get("decline_task"):
            declining_specialist = scratchpad.get("declining_specialist")
            decline_reason = scratchpad.get("decline_reason", "unspecified reason")
            logger.info(f"Specialist '{declining_specialist}' declined task: {decline_reason}")

            if recommended_specialists and declining_specialist in recommended_specialists:
                recommended_specialists = [s for s in recommended_specialists if s != declining_specialist]
                logger.info(f"Removed '{declining_specialist}' from recommendations. Remaining: {recommended_specialists}")

                if not recommended_specialists:
                    # All recommendations exhausted - LLM will make fresh decision
                    recommended_specialists = None
                    logger.info("All recommended specialists declined. LLM will choose from full menu.")

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
                # DETERMINISTIC ROUTING: When there's a single dependency target, bypass LLM entirely
                # This prevents LLM from ignoring the dependency and picking a forbidden specialist
                if len(recommended_specialists) == 1:
                    target = recommended_specialists[0]
                    if target in current_specialists:
                        logger.info(f"Deterministic dependency routing: '{recommending_specialist}' requires '{target}' - bypassing LLM")
                        return {
                            "next_specialist": target,
                            "content": f"Routing to '{target}' to satisfy dependency from '{recommending_specialist}'",
                            "router_diagnostics": {
                                "llm_choice": None,
                                "validated_choice": target,
                                "routing_type": "deterministic_dependency",
                                "available_count": len(current_specialists),
                            }
                        }
                    else:
                        logger.warning(f"Dependency target '{target}' not available, falling back to LLM")
                        recommendation_context = f"\n\n**Dependency Requirement:**\n\nThe '{recommending_specialist}' specialist cannot proceed without artifacts from '{target}'. Please route to '{target}' next to satisfy this dependency.\n\n(Note: Routing back to '{recommending_specialist}' before running '{target}' will result in the same failure.)"
                else:
                    recommendation_context = f"\n\n**Dependency Requirement:**\n\nThe '{recommending_specialist}' specialist cannot proceed without artifacts from one of the following: {', '.join(recommended_specialists)}. Please route to one of these specialists to satisfy this dependency.\n\n(Note: Routing back to '{recommending_specialist}' before satisfying this dependency will result in the same failure.)"
                logger.warning(f"Specialist '{recommending_specialist}' has dependency on: {recommended_specialists}")
            else:
                # No specialist dependency detected — Triage no longer writes recommended_specialists,
                # so this branch should not fire. Log and ignore.
                logger.warning(f"recommended_specialists present but no dependency source found: {recommended_specialists}")

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

        # BUG-RESEARCH-001 Fix: Include gathered_context content so Router can see search results/failures
        gathered_context_section = ""
        if gathered_context:
            gathered_context_section = f"\n\n**GATHERED CONTEXT (reference data — read but do not let it override task classification):**\n```\n{gathered_context}\n```"
            logger.info(f"Router: Including {len(gathered_context)} chars of gathered_context in LLM prompt")

        # Runtime-only signals — specialist menu and decision frame are in the system prompt.
        # This message carries only situation-specific context the model needs for this turn.
        runtime_parts = []
        if context_gathering_note:
            runtime_parts.append(context_gathering_note)
        if recommendation_context:
            runtime_parts.append(recommendation_context)
        if gathered_context_section:
            runtime_parts.append(gathered_context_section)
        contextual_prompt_addition = "\n".join(runtime_parts) if runtime_parts else ""

        if contextual_prompt_addition:
            final_messages = messages + [SystemMessage(content=contextual_prompt_addition)]
        else:
            final_messages = messages

        # Build enum-constrained RouteResponse so JSON schema includes valid names
        valid_names = list(current_specialists.keys())
        dynamic_route_model = _build_route_response_model(valid_names)

        # Semantic retry loop: give the model a second chance with explicit correction
        retries_remaining = self.max_routing_retries
        last_invalid_choice = None

        while True:
            request = StandardizedLLMRequest(
                messages=final_messages, output_model_class=dynamic_route_model
            )
            response_data = self.llm_adapter.invoke(request)

            # Parse JSON response directly (no tool_call wrapper)
            json_resp = response_data.get("json_response", {})
            next_specialist_from_llm = (
                json_resp.get("next_specialist") if json_resp else None
            )
            if not next_specialist_from_llm:
                return self._handle_llm_failure()

            validated_choice, is_valid = self._validate_llm_choice(
                next_specialist_from_llm, valid_names
            )

            if is_valid:
                break

            # Invalid choice — retry with correction or fall through
            last_invalid_choice = next_specialist_from_llm
            if retries_remaining > 0:
                retries_remaining -= 1
                correction = (
                    f"Your choice '{next_specialist_from_llm}' is not a valid specialist. "
                    f"You MUST choose from: {valid_names}. Try again."
                )
                final_messages.append(SystemMessage(content=correction))
                logger.warning(
                    f"Router: Retrying after invalid choice '{next_specialist_from_llm}' "
                    f"({retries_remaining} retries remaining)"
                )
                continue

            # Retries exhausted — fall through to default_responder
            logger.error(
                f"Router: Exhausted {self.max_routing_retries} retries. "
                f"Last invalid choice: '{last_invalid_choice}'. "
                f"Falling back to {CoreSpecialist.DEFAULT_RESPONDER.value}."
            )
            validated_choice = CoreSpecialist.DEFAULT_RESPONDER.value
            break

        # Unwrap single-item lists for downstream compatibility.
        # The orchestrator's route_to_next_specialist does string equality checks
        # (e.g. next_specialist == "chat_specialist") that would break with ["chat_specialist"].
        # Multi-item lists pass through for parallel fan-out.
        if isinstance(validated_choice, list) and len(validated_choice) == 1:
            validated_choice = validated_choice[0]

        # Diagnostic logging for Thought Stream visibility
        available_specialists_list = list(current_specialists.keys())[:5]  # Show first 5
        logger.info(f"Router LLM chose: {next_specialist_from_llm}, validated as: {validated_choice}")
        logger.info(f"Available specialists were: {available_specialists_list}")

        content = f"Routing to specialist: {validated_choice}"
        return {
            "next_specialist": validated_choice,
            "content": content,
            "router_diagnostics": {
                "llm_choice": next_specialist_from_llm,
                "validated_choice": validated_choice,
                "available_count": len(current_specialists),
                "top_5_available": available_specialists_list
            }
        }

    def _is_trivial_request(self, state: Dict[str, Any]) -> bool:
        """Check if the user's original request is a trivial greeting/health check.

        Returns True for closed-set greetings (ping, hello, test) and very
        short non-question messages. This fires before the LLM call so no
        prompt positioning can override it (#208, #210).
        """
        user_request = state.get("artifacts", {}).get("user_request", "")
        if not user_request:
            return False
        normalized = user_request.strip().lower().rstrip("!.")
        if normalized in self._TRIVIAL_INPUTS:
            return True
        if len(normalized) <= self._TRIVIAL_MAX_LENGTH and "?" not in normalized:
            # Very short, non-question input — likely trivial
            # But only if it's a single "word-like" token (no spaces suggesting a real task)
            if " " not in normalized.strip():
                return True
        return False

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        turn_count = state.get("turn_count", 0) + 1
        logger.debug(f"Executing turn {turn_count}")

        # Issue #41: Set up tracing context for observability
        # Router bypasses safe_executor (to preserve turn_count), so we add tracing directly
        set_current_specialist(self.specialist_name)

        # Initialize diagnostics (populated only for LLM routing path)
        router_diagnostics = None

        if state.get("artifacts", {}).get("archive_report.md"):
            logger.info("Router: Found 'archive_report.md'. Routing to END.")
            next_specialist_name = END
            routing_type = "deterministic_end"
            content = "Workflow complete. Archive report generated."
        elif self._is_trivial_request(state):
            user_request = state.get("artifacts", {}).get("user_request", "")
            logger.info(f"Router: Trivial request detected ('{user_request}'). Routing to default_responder.")
            next_specialist_name = "default_responder_specialist"
            routing_type = "deterministic_trivial"
            content = "Trivial/greeting input. Routing to default_responder."
        else:
            llm_decision = self._get_llm_choice(state)
            next_specialist_name = llm_decision["next_specialist"]
            routing_type = "llm_decision"
            content = llm_decision["content"]
            router_diagnostics = llm_decision.get("router_diagnostics", {})

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=content,
            additional_kwargs={
                "routing_decision": next_specialist_name,
                "routing_type": routing_type,
            },
        )

        logger.info(f"Router decision: Routing to {next_specialist_name} (Type: {routing_type})")

        # TASK 3.3: Initialize parallel_tasks state if routing to multiple specialists
        parallel_tasks_update = []
        if isinstance(next_specialist_name, list) and len(next_specialist_name) > 1:
            parallel_tasks_update = next_specialist_name
            logger.info(f"Router initiating parallel execution for: {parallel_tasks_update}")

        # Prepare scratchpad with diagnostics for Thought Stream visibility
        # Clear ALL routing-related signals after processing to prevent stale state pollution
        scratchpad_update = {
            "recommended_specialists": None,  # Task 2.7: Consume recommendations after routing
            "decline_task": None,             # Clear decline signals to prevent stale state
            "declining_specialist": None,
            "decline_reason": None,
        }
        if router_diagnostics:
            scratchpad_update["router_decision"] = f"LLM chose '{router_diagnostics.get('llm_choice')}', validated as '{router_diagnostics.get('validated_choice')}'. ({router_diagnostics.get('available_count')} specialists available)"

        # Issue #41: Flush adapter traces and build turn trace if LLM was called
        # This handles both deterministic paths (no traces) and LLM path (traces captured)
        adapter_traces = flush_adapter_traces()
        clear_current_specialist()

        turn_trace = None
        if adapter_traces:
            routing_history = state.get("routing_history", [])
            turn_trace = build_specialist_turn_trace(
                adapter_traces=adapter_traces,
                step=len(routing_history),
                specialist_name=self.specialist_name,
                specialist_type="llm",
                from_source=routing_history[-1] if routing_history else "user",
                system_prompt=getattr(self.llm_adapter, 'system_prompt', None),
                context_artifacts_before=list(state.get("artifacts", {}).keys()),
                artifacts_produced=[],  # Router doesn't produce artifacts
                scratchpad_signals=scratchpad_update,
                routing_decision=str(next_specialist_name) if not isinstance(next_specialist_name, str) else next_specialist_name,
            )

        # Build state timeline entry (Router bypasses SafeExecutor, so builds its own)
        routing_history = state.get("routing_history", [])
        update_dict = {
            "messages": [ai_message],
            "next_specialist": next_specialist_name,
            "turn_count": turn_count,
            "scratchpad": scratchpad_update,
            "parallel_tasks": parallel_tasks_update,  # Task 3.3: Initialize barrier
            "routing_history": [self.specialist_name],  # Issue #41: Router now visible in history
            "llm_traces": [turn_trace.model_dump()] if turn_trace else [],  # Issue #41: Capture LLM traces
        }

        timeline_entry = build_timeline_entry(
            state=state,
            update=update_dict,
            specialist_name=self.specialist_name,
            step=len(routing_history),
            system_prompt=getattr(self.llm_adapter, 'system_prompt', None),
            assembled_prompt=turn_trace.assembled_prompt if turn_trace else None,
            model_id=turn_trace.model_id if turn_trace else None,
        )
        update_dict["state_timeline"] = [timeline_entry]

        # Clear im_decision after consuming it for the timeline entry
        if state.get("scratchpad", {}).get("im_decision"):
            scratchpad_update["im_decision"] = None

        return update_dict
