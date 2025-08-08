# src/main.py

import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

# Load environment variables from .env file
load_dotenv()

from .graph.state import GraphState
from .enums import Specialist, Edge
from .specialists.router_specialist import RouterSpecialist
from .specialists.prompt_specialist import PromptSpecialist
from .specialists.data_extractor_specialist import DataExtractorSpecialist
from .specialists.file_specialist import FileSpecialist
from .llm.factory import LLMClientFactory

# --- Configuration ---
# Determines which LLM provider the specialists will use.
# Can be 'gemini', 'ollama', 'lmstudio', etc.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

def route_to_specialist(state: GraphState) -> str:
    """
    Reads the 'next_specialist' key from the state and determines the next node.
    This function is the core of the graph's routing logic. It provides a
    robust fallback to the PROMPT specialist if the router's decision is
    invalid or missing.

    Args:
        state (GraphState): The current state of the graph.

    Returns:
        str: The name of the next node to execute.
    """
    next_specialist_name = state.get("next_specialist")
    print(f"---ROUTING DECISION: {next_specialist_name}---")

    # A set of all valid, routable specialists
    valid_specialists = {s.value for s in Specialist if s != Specialist.ROUTER}

    if next_specialist_name == Edge.END.value:
        return Edge.END.value
    elif next_specialist_name in valid_specialists:
        return next_specialist_name
    
    print(f"---INVALID ROUTE: '{next_specialist_name}', defaulting to PROMPT specialist.---")
    return Specialist.PROMPT.value

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
    # All specialists should be called via their .execute() method for consistency.
    workflow.add_node(Specialist.FILE.value, file_specialist.execute)

    # --- Define Edges ---

    # The entry point is the router.
    workflow.set_entry_point(Specialist.ROUTER.value)

    # After the router runs, the 'route_to_specialist' function is called to
    # decide which specialist node to run next.
    workflow.add_conditional_edges(
        Specialist.ROUTER.value,
        route_to_specialist,
        {
            Specialist.PROMPT.value: Specialist.PROMPT.value,
            Specialist.DATA_EXTRACTOR.value: Specialist.DATA_EXTRACTOR.value,
            Specialist.FILE.value: Specialist.FILE.value,
        }
    )

    # After a specialist runs, the graph ends.
    workflow.add_edge(Specialist.PROMPT.value, Specialist.ROUTER.value)
    workflow.add_edge(Specialist.DATA_EXTRACTOR.value, Specialist.ROUTER.value)
    workflow.add_edge(Specialist.FILE.value, Specialist.ROUTER.value) # Add edge for FileSpecialist
    
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
