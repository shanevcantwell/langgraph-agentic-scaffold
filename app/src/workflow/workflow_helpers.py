# app/src/workflow/workflow_helpers.py
import logging
import traceback
from typing import Dict, Any, Callable

from langchain_core.messages import AIMessage

from ..graph.state import GraphState
from ..specialists.base import BaseSpecialist
from ..utils import state_pruner
from ..utils.errors import SpecialistError
from ..utils.report_schema import ErrorReport

logger = logging.getLogger(__name__)

def create_missing_artifact_response(
    specialist_name: str,
    missing_artifacts: list[str],
    recommended_specialists: list[str]
) -> dict:
    """
    Generates a standardized response when required artifacts are missing from the state.

    This response informs the user, provides a self-correction recommendation to the
    router, and prevents the specialist from executing with incomplete data.
    """
    missing_list = ", ".join(f"'{a}'" for a in missing_artifacts)
    content = (
        f"I, {specialist_name}, cannot execute because the following required artifacts "
        f"are missing from the current state: {missing_list}. "
        f"I recommend running the following specialist(s) first: {', '.join(recommended_specialists)}."
    )
    ai_message = AIMessage(content=content, name=specialist_name)
    return {"messages": [ai_message], "recommended_specialists": recommended_specialists}


def create_safe_executor(specialist_instance: BaseSpecialist) -> Callable[[GraphState], Dict[str, Any]]:
    """
    Creates a wrapper around a specialist's execute method to enforce global rules
    like declarative preconditions and to provide centralized exception handling.
    """
    specialist_name = specialist_instance.specialist_name
    specialist_config = specialist_instance.specialist_config
    required_artifacts = specialist_config.get("requires_artifacts", [])
    artifact_providers = specialist_config.get("artifact_providers", {})

    def safe_executor(state: GraphState) -> Dict[str, Any]:
        if required_artifacts:
            is_conditional = isinstance(required_artifacts[0], list)

            if is_conditional:
                satisfied_sets = 0
                for dependency_set in required_artifacts:
                    if all(state.get("artifacts", {}).get(artifact) for artifact in dependency_set):
                        satisfied_sets += 1
                        break

                if satisfied_sets == 0:
                    error_msg = f"Specialist '{specialist_name}' cannot execute. No dependency sets were satisfied. Required sets: {required_artifacts}"
                    logger.warning(error_msg)
                    first_artifact = required_artifacts[0][0]
                    recommended_specialist = artifact_providers.get(first_artifact)
                    return create_missing_artifact_response(
                        specialist_name=specialist_name,
                        missing_artifacts=[f"At least one of {required_artifacts}"],
                        recommended_specialists=[recommended_specialist] if recommended_specialist else []
                    )
            else:
                for artifact in required_artifacts:
                    if not state.get("artifacts", {}).get(artifact):
                        logger.warning(f"Specialist '{specialist_name}' cannot execute. Missing required artifact: '{artifact}'.")
                        recommended_specialist = artifact_providers.get(artifact)
                        return create_missing_artifact_response(
                            specialist_name=specialist_name,
                            missing_artifacts=[artifact],
                            recommended_specialists=[recommended_specialist] if recommended_specialist else []
                        )

        try:
            update = specialist_instance.execute(state)
            if "turn_count" in update:
                logger.warning(f"Specialist '{specialist_name}' returned a 'turn_count'. This is not allowed and will be ignored.")
                del update["turn_count"]
            return update
        except (SpecialistError, Exception) as e:
            logger.error(f"Caught unhandled exception from specialist '{specialist_name}': {e}", exc_info=True)
            tb_str = traceback.format_exc()
            pruned_state = state_pruner.prune_state(state)
            report_data = ErrorReport(
                error_message=str(e),
                traceback=tb_str,
                routing_history=state.get("routing_history", []),
                pruned_state=pruned_state
            )
            markdown_report = state_pruner.generate_report(report_data)
            return {"error": f"Specialist '{specialist_name}' failed. See report for details.", "error_report": markdown_report}

    return safe_executor