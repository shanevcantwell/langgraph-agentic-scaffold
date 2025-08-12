# MANIFEST: Proper Logging Implementation

This manifest outlines the steps to replace `print` statements with Python's standard `logging` module, enabling configurable log levels and improving application observability.

## 1. Logging Setup

We will configure the logging system to:
*   Default to `INFO` level output (showing `INFO`, `WARNING`, `ERROR`, `CRITICAL` messages).
*   Allow a `--debug` command-line argument to switch the log level to `DEBUG` (showing `DEBUG` and all higher levels).

### Proposed Changes to `main.py` (Project Root)

Modify the `main.py` file to include logging configuration and argument parsing.

```python
# main.py
import logging
import argparse
# ... existing imports ...

# Configure logging
def setup_logging(debug_mode: bool):
    level = logging.DEBUG if debug_mode else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def run_diagram_generation_workflow():
    # ... existing code ...

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the diagram generation workflow.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    setup_logging(args.debug)
    logging.info("Starting diagram generation workflow.")
    run_diagram_generation_workflow()
    logging.info("Diagram generation workflow completed.")

```

## 2. Replacing `print` Statements

All `print` statements should be replaced with appropriate logging calls. Choose the log level that best reflects the importance and verbosity of the message.

### Common Logging Levels:

*   `logging.debug()`: Detailed information, typically of interest only when diagnosing problems.
*   `logging.info()`: Confirmation that things are working as expected.
*   `logging.warning()`: An indication that something unexpected happened, or indicative of some problem in the near future (e.g., ‘disk space low’). The software is still working as expected.
*   `logging.error()`: Due to a more serious problem, the software has not been able to perform some function.
*   `logging.critical()`: A serious error, indicating that the program itself may be unable to continue running.

### Example Replacements:

#### Before:
```python
# In src/llm/clients.py
print(f"---INITIALIZED GEMINI CLIENT (Model: {model})---")
print(f"---CALLING GEMINI API---")
print(f"An error occurred while calling the Gemini API: {e}")
```

#### After:
```python
# In src/llm/clients.py
import logging
logger = logging.getLogger(__name__)

# ... inside GeminiClient.__init__
logger.info(f"INITIALIZED GEMINI CLIENT (Model: {model})")

# ... inside GeminiClient.invoke
logger.debug("CALLING GEMINI API") # Use debug for frequent calls
logger.error(f"An error occurred while calling the Gemini API: {e}")
```

### Files to Modify (Examples):

*   `/home/shane/github/shanevcantwell/langgraph-agentic-scaffold/main.py` (Project Root)
*   `/home/shane/github/shanevcantwell/langgraph-agentic-scaffold/app/src/llm/clients.py`
*   `/home/shane/github/shanevcantwell/langgraph-agentic-scaffold/app/src/specialists/systems_architect.py`
*   `/home/shane/github/shanevcantwell/langgraph-agentic-scaffold/app/src/specialists/web_builder.py`
*   `/home/shane/github/shanevcantwell/langgraph-agentic-scaffold/app/src/specialists/chief_of_staff.py`
*   Any other files containing `print` statements that should be part of the application's logging.

## 3. Implementation Steps:

1.  **Apply Logging Setup:** Implement the `setup_logging` function and argument parsing in `main.py`.
2.  **Import `logging`:** In each file where `print` statements are replaced, add `import logging` and create a logger instance (e.g., `logger = logging.getLogger(__name__)`).
3.  **Replace `print`s:** Go through each file and replace `print` statements with appropriate `logger.debug()`, `logger.info()`, `logger.warning()`, `logger.error()`, or `logger.critical()` calls.
4.  **Test:** Run the application with and without the `--debug` flag to verify logging behavior.
