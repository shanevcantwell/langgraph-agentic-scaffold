# src/main.py

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from .graph.state import GraphState
from .graph.nodes import router
from .agents.hello_world import HelloWorldSpecialist
from .enums import Specialist

def create_graph() -> StateGraph:
    """
    Assembles the LangGraph by defining nodes and edges.
    """
    hello_world_node = HelloWorldSpecialist(
        system_prompt_path="prompts/hello_world_prompt.txt"
    )

    workflow = StateGraph(GraphState)

    # --- Define Nodes ---
    workflow.add_node(Specialist.HELLO_WORLD.value, hello_world_node.execute)

    # --- Define Edges ---

    # THIS IS THE FIX:
    # Instead of adding the router as a node and then adding conditional edges,
    # we use a single method that defines the entry point IS a routing decision.
    workflow.set_conditional_entry_point(
        router,
        {
            # The router's output string is mapped to the destination node name
            Specialist.HELLO_WORLD.value: Specialist.HELLO_WORLD.value,
        }
    )

    # Any node that isn't a conditional branch should have a direct edge to the end
    workflow.add_edge(Specialist.HELLO_WORLD.value, END)
    
    return workflow.compile()

# The rest of the file remains the same...
if __name__ == "__main__":
    print("Compiling graph...")
    app = create_graph()

    print("Invoking graph...")
    initial_prompt = "This is a test request for the boilerplate."
    inputs = {"messages": [HumanMessage(content=initial_prompt)]}

    # Invoke the graph and stream the results.
    for output in app.stream(inputs):
        for key, value in output.items():
            print(f"Output from node '{key}':")
            print("---")
            print(value)
            print("\n---\n")

    print("Graph execution complete.")
