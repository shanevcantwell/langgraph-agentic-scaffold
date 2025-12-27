# app/src/specialists/schemas/_exit_interview.py
"""
Exit Interview Artifact Schema (Stopgap for ADR-CORE-036)

Defines artifacts that should be presented to the user or used as context
when DefaultResponderSpecialist generates the final response.

This is a schema-driven approach that replaces hardcoded artifact checks.
Specialists that produce user-facing output register their artifacts here.
"""
from typing import Dict, Any, Callable, Optional, Literal
from pydantic import BaseModel, Field


class ExitInterviewArtifactConfig(BaseModel):
    """Configuration for how an artifact should be handled in the exit interview."""

    mode: Literal["present", "context"] = Field(
        ...,
        description=(
            "'present' = show artifact content directly to user, "
            "'context' = inject artifact as LLM context for response generation"
        )
    )
    context_prompt: Optional[str] = Field(
        None,
        description="For 'context' mode: prompt to include with artifact when injecting into LLM context."
    )
    # Note: formatter functions are registered separately since Pydantic can't serialize callables


# Registry of artifacts that should be handled in exit interview
# Key: artifact name as it appears in state["artifacts"]
# Value: ExitInterviewArtifactConfig
EXIT_INTERVIEW_ARTIFACTS: Dict[str, ExitInterviewArtifactConfig] = {
    "system_plan": ExitInterviewArtifactConfig(
        mode="present",
        # Uses custom formatter (registered below)
    ),
    "image_description": ExitInterviewArtifactConfig(
        mode="context",
        context_prompt="Please use this image analysis to help with the user's original request.",
    ),
    # Add new artifacts here as specialists are created:
    # "code_analysis": ExitInterviewArtifactConfig(
    #     mode="context",
    #     context_prompt="Please use this code analysis to answer the user's question.",
    # ),
}


# Formatter functions for "present" mode artifacts
# (Separate from config since Pydantic can't serialize functions)
def format_system_plan(plan: Dict[str, Any]) -> str:
    """Formatter for system_plan artifact."""
    plan_summary = plan.get("plan_summary", "See details below")
    plan_steps = plan.get("execution_steps", [])
    if plan_steps:
        steps_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(plan_steps))
        return f"Here's the plan I created:\n\n**{plan_summary}**\n\nSteps:\n{steps_text}"
    return f"Here's the plan I created:\n\n**{plan_summary}**"


ARTIFACT_FORMATTERS: Dict[str, Callable[[Any], str]] = {
    "system_plan": format_system_plan,
    # Add formatters for other "present" mode artifacts here
}


def get_presentable_artifact(artifacts: Dict[str, Any]) -> Optional[tuple[str, ExitInterviewArtifactConfig, Any]]:
    """
    Check artifacts for any that should be presented/used in exit interview.

    Returns:
        Tuple of (artifact_key, config, artifact_value) if found, None otherwise.
        Returns the first matching artifact (priority order is dict insertion order).
    """
    for artifact_key, config in EXIT_INTERVIEW_ARTIFACTS.items():
        if artifact_key in artifacts:
            return (artifact_key, config, artifacts[artifact_key])
    return None
