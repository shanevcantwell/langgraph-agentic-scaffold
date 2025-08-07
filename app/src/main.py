# src/main.py

import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

# Load environment variables from .env file
load_dotenv()

from .graph.state import GraphState
from .enums import Specialist
from .specialists.router_specialist import RouterSpecialist
from .specialists.prompt_specialist import PromptSpecialist
from .specialists.data_extractor_specialist import DataExtractorSpecialist
from .specialists.file_specialist import FileSpecialist
from .llm.factory import LLMClientFactory

# --- Configuration ---
# Determines which LLM provider the specialists will use.
# Can be 'gemini', 'ollama', 'lmstudio', etc.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

def create_graph() -> StateGraph:
    """
    Assembles the LangGraph by defining nodes and edges.
    """
    # --- Instantiate Specialists ---
    router = RouterSpecialist(llm_provider=LLM_PROVIDER)
    prompt_specialist = PromptSpecialist(llm_provider=LLM_PROVIDER)
    data_extractor_specialist = DataExtractorSpecialist(llm_provider=LLM_PROVIDER)
    file_specialist = FileSpecialist(llm_provider=LLM_PROVIDER)

    workflow = StateGraph(GraphState)

    # --- Define Nodes ---
    workflow.add_node(Specialist.ROUTER.value, router.execute)
    workflow.add_node(Specialist.PROMPT.value, prompt_specialist.execute)
    workflow.add_node(Specialist.DATA_EXTRACTOR.value, data_extractor_specialist.execute)
    workflow.add_node(Specialist.FILE.value, file_specialist.invoke) # Use .invoke for FileSpecialist

    # --- Define Edges ---

    # The entry point is now the router.
    workflow.set_conditional_entry_point(
        # The router's 'execute' method returns a dictionary with a 'next' key.
        # This key's value determines which node to go to next.
        router.execute,
        {
            # The router's output string is mapped to the destination node's name
            Specialist.PROMPT.value: Specialist.PROMPT.value,
            Specialist.DATA_EXTRACTOR.value: Specialist.DATA_EXTRACTOR.value,
            Specialist.FILE.value: Specialist.FILE.value, # Add FileSpecialist to the routing
        }
    )

    # Any node that isn't a conditional branch should have a direct edge to the end
    workflow.add_edge(Specialist.PROMPT.value, END)
    workflow.add_edge(Specialist.DATA_EXTRACTOR.value, END)
    workflow.add_edge(Specialist.FILE.value, END) # Add edge for FileSpecialist
    
    return workflow.compile()

if __name__ == "__main__":
    import sys

    print("Compiling graph...")
    app = create_graph()

    user_input = None
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    
    if user_input:
        print(f"\n--- INVOKING GRAPH WITH USER PROMPT ---")
        initial_prompt = user_input
        inputs = {"messages": [HumanMessage(content=initial_prompt)]}

        for output in app.stream(inputs):
            for key, value in output.items():
                print(f"Output from node '{key}':")
                print("---")
                print(value)
                print("\n---\n")
    else:
        print("\n--- NO USER PROMPT PROVIDED. RUNNING DEFAULT EXAMPLES. ---")
        # --- Example 1: A general prompt that should go to the PromptSpecialist ---
        print("\n--- INVOKING GRAPH WITH GENERAL PROMPT ---")
        initial_prompt = "What is the capital of France?"
        inputs = {"messages": [HumanMessage(content=initial_prompt)]}

        for output in app.stream(inputs):
            for key, value in output.items():
                print(f"Output from node '{key}':")
                print("---")
                print(value)
                print("\n---\n")

        # --- Example 2: A data extraction prompt ---
        print("\n--- INVOKING GRAPH WITH DATA EXTRACTION PROMPT ---")
        extraction_prompt = "Hi, my name is John Smith and my email is john.s@work.com. Please register me."
        # The data extractor needs the text in a specific state key
        inputs = {
            "messages": [HumanMessage(content=extraction_prompt)],
            "text_to_process": extraction_prompt
        }
        for output in app.stream(inputs):
            for key, value in output.items():
                print(f"Output from node '{key}':")
                print("---")
                print(value)
                print("\n---\n")

    print("Graph execution complete.")
