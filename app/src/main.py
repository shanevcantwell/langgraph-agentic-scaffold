import os
import logging

from dotenv import load_dotenv
from src.llm.factory import LLMClientFactory
from src.specialists.chief_of_staff import ChiefOfStaffSpecialist
from src.specialists.systems_architect import SystemsArchitect
from src.specialists.web_builder import WebBuilder

load_dotenv()
logger = logging.getLogger(__name__)

def run_diagram_generation_workflow():
    """
    Initializes the specialists and runs the diagram generation workflow.
    """
    # 1. Define the high-level goal
    goal = (
        "Create a sequence diagram that shows the interaction between a User, "
        "a Chief of Staff, a Systems Architect, and a Web Builder. The User asks "
        "the Chief of Staff to create a diagram. The Chief of Staff first calls the "
        "Systems Architect to get the diagram's code, then calls the Web Builder "
        "to embed that code into an HTML page, and finally returns the result to the User."
    )

    # 2. Instantiate the specialist agents
    llm_provider_name = os.getenv("LLM_PROVIDER", "gemini")
    systems_architect = SystemsArchitect(llm_provider=llm_provider_name)
    web_builder = WebBuilder(llm_provider=llm_provider_name)

    # 3. Instantiate the Chief of Staff, providing it with the specialists it needs
    chief_of_staff = ChiefOfStaffSpecialist(
        systems_architect=systems_architect,
        web_builder=web_builder
    )

    # 4. Invoke the workflow
    final_state = chief_of_staff.invoke(goal)

    # 5. Log the results
    logger.info("--- FINAL WORKFLOW OUTPUT ---")
    if final_state.get("error"):
        logger.error(f"An error occurred: {final_state['error']}")
    else:
        logger.info("JSON Artifact Generated:")
        logger.info("-----------------------")
        logger.info(final_state.get("json_artifact"))
        logger.info("\nFinal HTML Artifact:")
        logger.info("--------------------")
        logger.info(final_state.get("html_artifact"))
        logger.info("\nWorkflow executed successfully.")


if __name__ == "__main__":
    run_diagram_generation_workflow()

