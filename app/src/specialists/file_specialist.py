import logging
import os
from typing import Union, Literal, Optional, Dict, Any

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field

from app.src.llm.adapter import StandardizedLLMRequest
from app.src.utils.errors import SpecialistError
from app.src.specialists.base import BaseSpecialist

logger = logging.getLogger(__name__)

# --- Pydantic Models for Tool Definitions ---
# This defines the "hard contract" for the LLM. It must fill these fields.

class ReadFileParams(BaseModel):
    """Parameters for reading the contents of a file."""
    file_path: str = Field(..., description="The relative path to the file to be read.")

class WriteFileParams(BaseModel):
    """Parameters for writing content to a file."""
    file_path: str = Field(..., description="The relative path to the file to be written.")
    content: str = Field(..., description="The content to write into the file.")

class ListDirectoryParams(BaseModel):
    """Parameters for listing the contents of a directory."""
    dir_path: str = Field(default=".", description="The relative path to the directory to be listed.")

class FileOperation(BaseModel):
    """A single file operation to be performed."""
    tool_name: Literal["read_file", "write_file", "list_directory"]
    tool_input: Union[ReadFileParams, WriteFileParams, ListDirectoryParams]


# --- Specialist Implementation ---

class FileSpecialist(BaseSpecialist):
    """
    A specialist for interacting with the filesystem, using Pydantic for structured tool calls.
    It can read files and list directories. Write operations are disabled by a safety lock.
    """

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        self.root_dir = os.path.abspath(self.specialist_config.get("root_dir", "."))
        logger.info(f"Initialized {self.__class__.__name__} with root directory: {self.root_dir}")
        
        # Dead man's switch: Check for a lock file to enable write operations.
        self.safety_lock_file = ".agent_safety_off.lock"
        self.is_safety_on = not os.path.exists(self.safety_lock_file)
        if self.is_safety_on:
            logger.warning(f"FileSpecialist safety is ON. No file modifications will be made. To disable, create a file named '{self.safety_lock_file}' in the project root.")
        else:
            logger.warning(f"FileSpecialist safety is OFF. The agent can now write to the filesystem within its workspace.")
            
        self.output_model_class = FileOperation

    def _get_full_path(self, relative_path: str) -> str:
        """Validates and resolves a relative path against the root directory."""
        if ".." in relative_path or os.path.isabs(relative_path):
            raise SpecialistError("Access denied: Only relative paths are allowed.")
        
        full_path = os.path.abspath(os.path.join(self.root_dir, relative_path))
        
        if not full_path.startswith(self.root_dir):
            raise SpecialistError("Access denied: Path is outside the allowed directory.")
        
        return full_path

    def _read_file(self, params: ReadFileParams) -> tuple[Optional[str], str]:
        """
        Implementation for reading a file.
        Returns a tuple of (file_content, status_message).
        """
        try:
            full_path = self._get_full_path(params.file_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            status_message = f"Successfully read file '{params.file_path}'. Content is now in context."
            return content, status_message
        except Exception as e:
            return None, f"Error reading file '{params.file_path}': {e}"

    def _write_file(self, params: WriteFileParams) -> str:
        """Implementation for writing a file."""
        try:
            full_path = self._get_full_path(params.file_path)
            if self.is_safety_on:
                return f"[DRY RUN] Operation successful. Would have written content to file: {params.file_path}"
            else:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(params.content)
                return f"Successfully wrote to {params.file_path}"
        except Exception as e:
            return f"Error writing file '{params.file_path}': {e}"

    def _list_directory(self, params: ListDirectoryParams) -> str:
        """Implementation for listing a directory."""
        try:
            full_path = self._get_full_path(params.dir_path)
            if not os.path.isdir(full_path):
                return f"Error: '{params.dir_path}' is not a directory."
            return ".\n" + "\n".join(os.listdir(full_path))
        except Exception as e:
            return f"Error listing directory '{params.dir_path}': {e}"

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the file operation based on the LLM's structured output."""
        messages = state["messages"]

        request = StandardizedLLMRequest(messages=messages, output_model_class=self.output_model_class)
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            error_message = "File Specialist Error: The model did not return a valid, structured tool call. Please rephrase your request."
            # Return an AIMessage, as this is a failure in the LLM's response, not a tool failure.
            return {"messages": messages + [AIMessage(content=error_message)]}

        try:
            structured_response = self.output_model_class(**json_response)
        except Exception as e:
            error_message = f"File Specialist Error: Failed to validate the model's response. Error: {e}"
            return {"messages": messages + [AIMessage(content=error_message)]}

        tool_name = structured_response.tool_name
        tool_input = structured_response.tool_input
        
        result_message = ""
        text_to_process = None

        try:
            if tool_name == "read_file":
                text_to_process, result_message = self._read_file(tool_input)
            elif tool_name == "list_directory":
                result_message = self._list_directory(tool_input)
                # The list of files is also content that might be processed
                text_to_process = result_message
            elif tool_name == "write_file":
                result_message = self._write_file(tool_input)
            else:
                result_message = f"Error: Unknown tool '{tool_name}' requested."
        except SpecialistError as e:
            result_message = f"Error executing tool '{tool_name}': {e}"
        except Exception as e:
            logger.error(f"An unexpected error occurred in FileSpecialist during '{tool_name}': {e}", exc_info=True)
            result_message = f"An unexpected error occurred during '{tool_name}': {e}"

        # Create a ToolMessage to record the outcome of the tool call.
        tool_message = ToolMessage(
            content=result_message,
            tool_call_id=tool_name # Using tool_name as a stand-in for a real tool_call_id
        )

        # Return the updated state, including the text content if a file was read.
        updated_state = {"messages": messages + [tool_message]}
        if text_to_process is not None:
            updated_state["text_to_process"] = text_to_process
        
        return updated_state