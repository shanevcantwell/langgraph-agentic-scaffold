import logging
from typing import Dict, Any

from .base import BaseSpecialist
from ..interface.system_plan import SystemPlan, ExecutionStatus

logger = logging.getLogger(__name__)

class PlanExecutor(BaseSpecialist):
    """
    The 'Foreman' or 'Project Manager' of the architecture.
    
    Responsibilities:
    1. Inspects the results from 'worker' specialists (e.g., WebSpecialist).
    2. Updates the SystemPlan (marks steps as COMPLETED/FAILED).
    3. Stores results in the plan.
    4. Advances the plan index.
    5. Determines if the plan is finished.
    
    This is a PROCEDURAL specialist. It does not use an LLM.
    """

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
        plan_data = artifacts.get("system_plan")
        
        # We look for specific result keys that workers might have left
        # This allows us to be agnostic about WHO did the work
        search_results = state.get("search_results")
        step_error = state.get("error")
        
        if not plan_data:
            return {"error": "PlanExecutor ran but no SystemPlan found."}

        try:
            plan = SystemPlan(**plan_data)
            current_step = plan.get_current_step()
            
            if not current_step:
                logger.warning("PlanExecutor: No current step found. Plan might be complete or malformed.")
                return {}

            logger.info(f"PlanExecutor: Updating status for Step {current_step.step_number} ({current_step.capability})")

            # 1. Update Step Status based on inputs
            if step_error:
                current_step.status = ExecutionStatus.FAILED
                current_step.error = step_error
                logger.error(f"PlanExecutor: Step {current_step.step_number} marked FAILED: {step_error}")
            elif search_results is not None:
                current_step.status = ExecutionStatus.COMPLETED
                current_step.result = search_results
                logger.info(f"PlanExecutor: Step {current_step.step_number} marked COMPLETED.")
            else:
                # If we ran but have no results, something is wrong, or it was a side-effect only step
                # For now, we assume success if no error, but log a warning
                logger.warning(f"PlanExecutor: Step {current_step.step_number} finished with no explicit result data.")
                current_step.status = ExecutionStatus.COMPLETED

            # 2. Advance the Plan
            plan.current_step_index += 1
            
            # 3. Check for Plan Completion
            if plan.current_step_index >= len(plan.steps):
                plan.status = ExecutionStatus.COMPLETED
                logger.info("PlanExecutor: SystemPlan execution COMPLETED.")
            
            # 4. Return updated artifacts and CLEAR the transient result keys
            # We must clear 'search_results' so they don't persist to the next step
            return {
                "artifacts": {
                    "system_plan": plan.model_dump()
                },
                "search_results": None, # Clear transient data
                "error": None           # Clear transient error
            }

        except Exception as e:
            logger.error(f"PlanExecutor failed: {e}", exc_info=True)
            return {"error": f"PlanExecutor internal error: {str(e)}"}
