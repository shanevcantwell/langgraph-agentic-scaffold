import logging
import os
import json
from typing import Dict, Any, List
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import Tool

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

class FileSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)

        # The specialist_config is already loaded by the BaseSpecialist constructor.
        # We can access it via self.specialist_config.
        self.root_dir = os.path.abspath(self.specialist_config.get("root_dir", "."))
        logger.info(f"Initialized {self.__class__.__name__} with root directory: {self.root_dir}")

        self.tools = [
            Tool(name="read_file", func=self._read_file_impl, description="Reads the content of a file at a given path."),
            Tool(name="write_file", func=self._write_file_impl, description="Writes content to a file at a given path."),
            Tool(name="list_directory", func=self._list_directory_impl, description="Lists the contents of a directory at a given path.")
        ]

    def _get_full_path(self, file_path: str) -> str:
        if ".." in file_path:
            raise ValueError("File path cannot contain '..' to prevent directory traversal.")
        full_path = os.path.abspath(os.path.join(self.root_dir, file_path))
        if not full_path.startswith(self.root_dir):
            raise ValueError("File path is outside the allowed directory.")
        return full_path

    def _read_file_impl(self, file_path: str) -> str:
        try:
            full_path = self._get_full_path(file_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    def _write_file_impl(self, file_path: str, content: str) -> str:
        try:
            full_path = self._get_full_path(file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def _list_directory_impl(self, dir_path: str = ".") -> str:
        try:
            full_path = self._get_full_path(dir_path)
            if not os.path.isdir(full_path):
                return f"Error: {dir_path} is not a directory."
            return "\n".join(os.listdir(full_path))
        except Exception as e:
            return f"Error listing directory: {e}"

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state['messages']
        
        request = StandardizedLLMRequest(
            messages=messages,
            tools=self.tools,
        )

        llm_response = self.llm_adapter.invoke(request)
        tool_calls = llm_response.get("tool_calls")

        if not tool_calls:
            no_op_message = llm_response.get("text_response", "File Specialist: No file operation was requested.")
            return {"messages": state["messages"] + [AIMessage(content=no_op_message)]}

        updated_state = state.copy()
        tool_results = []
        text_to_process = None
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_map = {tool.name: tool.func for tool in self.tools}

            if tool_func := tool_map.get(tool_name):
                try:
                    result = tool_func(**tool_args)
                    # If we successfully read a file, capture its content to be placed
                    # into the shared state for other specialists to process.
                    if tool_name == "read_file" and not str(result).startswith("Error"):
                        text_to_process = result
                except TypeError as e:
                    result = f"Error calling tool '{tool_name}': Invalid arguments provided. {e}"
            else:
                result = f"Error: Unknown tool '{tool_name}'"
            
            tool_results.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        updated_state["messages"] = state["messages"] + tool_results
        if text_to_process:
            updated_state["text_to_process"] = text_to_process

        return updated_state