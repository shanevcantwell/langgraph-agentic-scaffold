import logging
import os
from dotenv import load_dotenv

from .workflow.runner import WorkflowRunner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """
    The main entry point for the application.
    Initializes the environment, sets a goal, and uses the WorkflowRunner to execute it.
    """
    load_dotenv()
    
    # MODIFIED: The validation check now uses the correct, documented environment variable.
    if os.getenv("LLM_PROVIDER") == "gemini" and not os.getenv("GOOGLE_API_KEY"):
        logger.error("GOOGLE_API_KEY must be set in your .env file for the 'gemini' provider.")
        return
        
    if not os.getenv("LLM_PROVIDER"):
        logger.warning("LLM_PROVIDER not set, defaulting to 'gemini'.")
        os.environ["LLM_PROVIDER"] = "gemini"
    if not os.getenv("GEMINI_MODEL"):
        logger.warning("GEMINI_MODEL not set, defaulting to 'gemini-1.5-flash'.")
        os.environ["GEMINI_MODEL"] = "gemini-1.5-flash"

    logger.info("Starting agentic workflow.")

    # 1. Define the high-level goal
    goal = (
        "Create a sequence diagram that shows the interaction between a User, a Chief of Staff, "
        "a Systems Architect, and a Web Builder. The User asks the Chief of Staff to create a diagram. "
        "The Chief of Staff first calls the Systems Architect to get the diagram's code, then calls "
        "the Web Builder to embed that code into an HTML page, and finally returns the result to the User."
    )

    # 2. Instantiate and use the WorkflowRunner. All complexity is now hidden.
    runner = WorkflowRunner()
    final_state = runner.run(goal=goal)

    # 3. Process and display the final results
    logger.info("--- FINAL WORKFLOW OUTPUT ---")
    if final_state.get("error"):
        logger.error(f"An error occurred: {final_state['error']}")
    else:
        json_artifact = final_state.get("json_artifact")
        html_artifact = final_state.get("html_artifact")

        if json_artifact:
            logger.info("JSON Artifact Generated:")
            logger.info("-----------------------")
            logger.info(json_artifact)
        
        if html_artifact:
            logger.info("\nFinal HTML Artifact:")
            logger.info("--------------------")
            
            output_path = "output.html"
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(html_artifact)
                logger.info(f"HTML output saved to {os.path.abspath(output_path)}")
            except Exception as e:
                logger.error(f"Failed to save HTML artifact: {e}")
                logger.info(html_artifact) # Log to console as a fallback

        logger.info("\nWorkflow executed successfully.")

    logger.info("Workflow completed.")

if __name__ == "__main__":
    main()
