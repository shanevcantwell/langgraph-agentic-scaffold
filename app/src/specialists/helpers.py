from typing import List
from langchain_core.messages import AIMessage

def create_missing_artifact_response(
    specialist_name: str,
    missing_artifacts: List[str],
    recommended_specialists: List[str]
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