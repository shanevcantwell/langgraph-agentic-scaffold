import os
import logging
import argparse

from dotenv import load_dotenv
from src.llm.factory import LLMClientFactory
from src.specialists.chief_of_staff import ChiefOfStaffSpecialist
from src.specialists.systems_architect import SystemsArchitect
from src.specialists.web_builder import WebBuilder

load_dotenv()

def setup_logging(debug_mode: bool):
    """Configures the logging for the application."""
    level = logging.DEBUG if debug_mode else logging.INFO
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=level, format=log_format)

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
    result = chief_of_staff.invoke(goal)

    # 5. Log the results
    logger.info("--- FINAL WORKFLOW OUTPUT ---")
    if result.get("status") == "error":
        logger.error(f"An error occurred: {result.get('message')}")
        logger.error(f"Details: {result.get('details')}")
    else:
        final_state = result.get("final_state", {})
        logger.info("JSON Artifact Generated:")
        logger.info("-----------------------")
        logger.info(final_state.get("json_artifact", "Not found in final state."))
        logger.info("\nFinal HTML Artifact:")
        logger.info("--------------------")
        logger.info(final_state.get("html_artifact", "Not found in final state."))
        logger.info("\nWorkflow executed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the diagram generation workflow.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    setup_logging(args.debug)
    # Re-initialize logger after basicConfig is called to ensure it picks up the config
    logger = logging.getLogger(__name__)

    logger.info("Starting diagram generation workflow.")
    run_diagram_generation_workflow()
    logger.info("Diagram generation workflow completed.")
