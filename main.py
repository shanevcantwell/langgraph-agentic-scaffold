import logging
import argparse

from src.specialists.chief_of_staff import ChiefOfStaffSpecialist
from src.specialists.systems_architect import SystemsArchitect
from src.specialists.web_builder import WebBuilder

# Configure logging
def setup_logging(debug_mode: bool):
    level = logging.DEBUG if debug_mode else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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
    # For this example, their internal logic can be simple placeholders
    systems_architect = SystemsArchitect()
    web_builder = WebBuilder()

    # 3. Instantiate the Chief of Staff, providing it with the specialists it needs
    chief_of_staff = ChiefOfStaffSpecialist(
        systems_architect=systems_architect,
        web_builder=web_builder
    )

    # 4. Invoke the workflow
    final_state = chief_of_staff.invoke(goal)

    # 5. Print the results
    logging.info("\n--- FINAL WORKFLOW OUTPUT ---")
    if final_state.get("error"):
        logging.error(f"An error occurred: {final_state['error']}")
    else:
        logging.info("JSON Artifact Generated:")
        logging.info("-----------------------")
        logging.info(final_state.get("json_artifact"))
        logging.info("\nFinal HTML Artifact:")
        logging.info("--------------------")
        logging.info(final_state.get("html_artifact"))
        logging.info("\nWorkflow executed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the diagram generation workflow.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    setup_logging(args.debug)
    logging.info("Starting diagram generation workflow.")
    run_diagram_generation_workflow()
    logging.info("Diagram generation workflow completed.")