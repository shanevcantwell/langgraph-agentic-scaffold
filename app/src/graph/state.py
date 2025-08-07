# src/graph/state.py

from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage
import operator

class GraphState(TypedDict):
    """
    Represents the state of our graph as a conversation.

    Attributes:
        messages: A list of messages that form the conversation.
                  The `Annotated` type hint combined with `operator.add` is a
                  special instruction to LangGraph. It tells the framework to
                  always APPEND new messages to this list, rather than
                  overwriting the list with the new value. This creates an
                  append-only log, which is perfect for conversations.
    """
    messages: Annotated[List[BaseMessage], operator.add]

