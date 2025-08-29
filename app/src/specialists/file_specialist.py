import logging
import os
from typing import Optional, Dict, Any

from langchain_core.messages import AIMessage, ToolMessage

from app.src.llm.adapter import StandardizedLLMRequest
from app.src.utils.errors import SpecialistError
from app.src.utils.path_utils import PROJECT_ROOT
from app.src.specialists.base import BaseSpecialist
from .helpers import create_llm_message
from .schemas import ReadFileParams, WriteFileParams, ListDirectoryParams

logger = logging.getLogger(__name__)


# --- Specialist Implementation ---

class FileSpecialist(BaseSpecialist):
    """
    A specialist for interacting with the filesystem, using Pydantic for structured tool calls.
    It can read files and list directories. Write operations are disabled by a safety lock.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # Resolve root_dir relative to the project root for robustness.
        # This prevents issues where the script is run from a different directory.
        relative_root_dir = self.specialist_config.get("root_dir", "./workspace")
        self.root_dir = str(PROJECT_ROOT / relative_root_dir)
        os.makedirs(self.root_dir, exist_ok=True) # Ensure the workspace exists
        logger.info(f"Initialized {self.__class__.__name__} with workspace directory: {self.root_dir}")
        
        # Dead man's switch: Check for a lock file to enable write operations.
        self.safety_lock_file = ".agent_safety_off.lock"
        self.is_safety_on = not os.path.exists(self.safety_lock_file)
        if self.is_safety_on:
            logger.warning(f"FileSpecialist safety is ON. No file modifications will be made. To disable, create a file named '{self.safety_lock_file}' in the project root.")
        else:
            logger.warning(f"FileSpecialist safety is OFF. The agent can now write to the filesystem within its workspace.")

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
        
        # Instead of asking for one complex JSON object, we provide a list of tools
        # and let the LLM choose which one to call. This is more robust.
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[ReadFileParams, WriteFileParams, ListDirectoryParams]
        )
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls:
            error_message = "File Specialist Error: The model did not request a valid tool call. Please rephrase your request."
            return {"messages": [AIMessage(content=error_message, name=self.specialist_name)]}

        # This specialist is designed to handle one tool call at a time for simplicity.
        tool_call = tool_calls[0]
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        
        updated_state: Dict[str, Any] = {}
        result_content = ""
        action_name_for_report = tool_name # Keep original for logging

        try:
            # --- Tool Name Normalization ---
            # Create a mapping from various possible LLM-hallucinated names to the
            # canonical Pydantic class. This makes the system more robust.
            tool_map = {
                ReadFileParams.__name__: ReadFileParams,
                "read_file": ReadFileParams,
                "ReadFile": ReadFileParams,
                WriteFileParams.__name__: WriteFileParams,
                "write_file": WriteFileParams,
                "WriteFile": WriteFileParams,
                ListDirectoryParams.__name__: ListDirectoryParams,
                "list_directory": ListDirectoryParams,
                "ListDirectory": ListDirectoryParams,
            }

            TargetToolClass = tool_map.get(tool_name)

            if TargetToolClass == ReadFileParams:
                action_name_for_report = "ReadFile"
                file_content, result_content = self._read_file(TargetToolClass(**tool_args))
                if file_content is not None:
                    updated_state["text_to_process"] = file_content
                    # By not making a recommendation, we return control to the router
                    # to make an intelligent decision based on the new context.
            elif TargetToolClass == ListDirectoryParams:
                action_name_for_report = "ListDirectory"
                result_content = self._list_directory(TargetToolClass(**tool_args))
                # The list of files is also content that might be processed
                updated_state["text_to_process"] = result_content
            elif TargetToolClass == WriteFileParams:
                action_name_for_report = "WriteFile"
                result_content = self._write_file(TargetToolClass(**tool_args))
            else:
                result_content = f"Error: Unknown tool '{tool_name}' requested."
        except SpecialistError as e:
            result_content = f"Error executing tool '{tool_name}': {e}"
        except Exception as e:
            logger.error(f"An unexpected error occurred in FileSpecialist during '{tool_name}': {e}", exc_info=True)
            result_content = f"An unexpected error occurred during '{tool_name}': {e}"

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"FileSpecialist action '{action_name_for_report}' completed. Status: {result_content}",
        )

        updated_state["messages"] = [ai_message]
        return updated_state