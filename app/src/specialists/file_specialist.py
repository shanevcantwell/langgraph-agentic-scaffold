# app/src/specialists/file_specialist.py

import logging
import os
import json
from typing import Dict, Any, List
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool, Tool

from .base import BaseSpecialist
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class FileSpecialist(BaseSpecialist):
    """Specialist for handling file system operations."""

    def __init__(self, llm_provider: str, root_dir: str = "."):
        system_prompt = load_prompt("file_specialist")

        # Define tools as class attributes, instantiating them as Tool objects
        self._read_file_tool = Tool(name="read_file", func=self._read_file_impl, description="Reads the content of a file.")
        self._write_file_tool = Tool(name="write_file", func=self._write_file_impl, description="Writes content to a file.")
        self._list_directory_tool = Tool(name="list_directory", func=self._list_directory_impl, description="Lists the contents of a directory.")

        tools = [self._read_file_tool, self._write_file_tool, self._list_directory_tool]
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider, tools=tools)

        self.root_dir = os.path.abspath(root_dir)
        logger.info(f"---INITIALIZED {self.__class__.__name__} (Root Dir: {self.root_dir})---")

    def _get_full_path(self, file_path: str) -> str:
        """Validates and returns the full, safe path for a file."""
        if ".." in file_path:
            raise ValueError("File path cannot contain '..' to prevent directory traversal.")

        full_path = os.path.abspath(os.path.join(self.root_dir, file_path))

        if not full_path.startswith(self.root_dir):
            raise ValueError("File path is outside the allowed directory.")

        return full_path

    def _read_file_impl(self, file_path: str) -> str:
        """Reads the content of a file."""
        try:
            full_path = self._get_full_path(file_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    def _write_file_impl(self, file_path: str, content: str) -> str:
        """Writes content to a file."""
        try:
            full_path = self._get_full_path(file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def _list_directory_impl(self, dir_path: str) -> str:
        """Lists the contents of a directory."""
        try:
            full_path = self._get_full_path(dir_path)
            if not os.path.isdir(full_path):
                return f"Error: {dir_path} is not a directory."
            return "\n".join(os.listdir(full_path))
        except Exception as e:
            return f"Error listing directory: {e}"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses the LLM to determine which file operation to perform and executes it.
        """
        logger.info("---FILE SPECIALIST EXECUTING---")
        user_prompt_message = state['messages'][-1]

        messages_to_send = [
            SystemMessage(content=self.system_prompt_content),
            user_prompt_message
        ]

        # Invoke the LLM with the messages, tools, and a low temperature for deterministic tool use.
        ai_response = self.llm_client.invoke(
            messages=messages_to_send,
            tools=self.tools,
            temperature=0
        )
        tool_calls = ai_response.tool_calls

        if not tool_calls:
            return {"messages": [AIMessage(content="File Specialist: No tool calls detected.")]}

        tool_results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})

            # Call the actual implementation methods
            if tool_name == "read_file":
                result = self._read_file_impl(**tool_args)
            elif tool_name == "write_file":
                result = self._write_file_impl(**tool_args)
            elif tool_name == "list_directory":
                result = self._list_directory_impl(**tool_args)
            else:
                result = f"Error: Unknown tool: {tool_name}"
            tool_results.append(ToolMessage(content=result, tool_call_id=tool_call["id"])) # Assuming tool_call has an 'id'

        return {"messages": tool_results}
