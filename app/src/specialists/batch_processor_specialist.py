"""
BatchProcessorSpecialist - Batch file operations via Operation Dispatcher pattern.

Architecture (ADR-CORE-049):
    Specialist (LLM) → list[FileOperation] → Dispatcher → Filesystem MCP

The LLM handles inference (what operations to perform).
The dispatcher handles dispatch (how to execute via MCP).

Supported operations:
- CREATE: "Create files a.txt, b.txt, c.txt"
- SORT: "Sort files in to_sort/ into alphabetic subfolders"
- MOVE: "Move old.txt to archive/"
- MIXED: "Create x.txt then move it to backup/"

Example Flow:
    User: "Create empty files named e.txt, l.txt, p.txt"
      ↓
    Router → BatchProcessorSpecialist
      ↓
    1. LLM parses user intent → list[FileOperation]
    2. FileOperationDispatcher dispatches to filesystem MCP
    3. Return results with detailed artifacts

Note: external_mcp_client is injected by GraphBuilder after specialist loading.
"""
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas._file_operations import FileOperation, FileOperationList
from ..dispatchers import FileOperationDispatcher, OperationResult
from ..mcp import sync_call_external_mcp, extract_text_from_mcp_result

logger = logging.getLogger(__name__)


class BatchProcessorSpecialist(BaseSpecialist):
    """
    Specialist for batch file operations via Operation Dispatcher pattern (ADR-CORE-049).

    LLM produces list[FileOperation], dispatcher dispatches to filesystem MCP.
    Handles: create multiple files, sort files, batch moves, mixed operations.

    Uses external filesystem MCP container for file operations (ADR-CORE-035).
    """

    def _is_filesystem_available(self) -> bool:
        """Check if external filesystem MCP is connected."""
        if not hasattr(self, 'external_mcp_client') or self.external_mcp_client is None:
            return False
        return self.external_mcp_client.is_connected("filesystem")

    def _call_filesystem_mcp(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call external filesystem MCP and extract text result."""
        result = sync_call_external_mcp(
            self.external_mcp_client,
            "filesystem",
            tool_name,
            arguments
        )
        return extract_text_from_mcp_result(result)

    def _file_exists(self, path: str) -> bool:
        """Check if file exists using filesystem MCP get_file_info."""
        try:
            self._call_filesystem_mcp("get_file_info", {"path": path})
            return True
        except Exception:
            return False

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute batch file operations via Operation Dispatcher pattern.

        Flow:
        1. LLM parses user intent → list[FileOperation]
        2. FileOperationDispatcher dispatches each operation to MCP
        3. Format results and return artifacts
        """
        if not self._is_filesystem_available():
            logger.error("BatchProcessorSpecialist: Filesystem MCP not available")
            return {
                "messages": [AIMessage(content="Error: File operations service not available. The filesystem container may not be running.")],
                "task_is_complete": True
            }

        messages = self._get_enriched_messages(state)
        if not messages:
            return {
                "messages": [AIMessage(content="Error: No batch operation request to process.")],
                "task_is_complete": True
            }

        try:
            # Phase 1: LLM parses user intent → list[FileOperation]
            operations = self._parse_operations(messages)
            logger.info(f"Phase 1: parsed {len(operations)} operations")

            # Phase 2: Execute via FileOperationDispatcher (ADR-CORE-049)
            dispatcher = FileOperationDispatcher(self.external_mcp_client)
            results = dispatcher.dispatch_sync(operations)

            # Phase 3: Format results
            formatted = self._format_results(operations, results)

            # Build reasoning for Thought Stream observability
            reasoning_lines = [f"Parsed {len(operations)} operations:"]
            for op in operations:
                if op.destination:
                    reasoning_lines.append(f"  • {op.type}: {op.path} → {op.destination}")
                else:
                    reasoning_lines.append(f"  • {op.type}: {op.path}")

            success_count = sum(1 for r in results if r.success)
            fail_count = len(results) - success_count
            if fail_count > 0:
                failed_paths = [r.operation.path for r in results if not r.success]
                reasoning_lines.append(f"⚠️ {fail_count} failed: {failed_paths}")

            return {
                "messages": [AIMessage(content=formatted["summary"])],
                "artifacts": {
                    "batch_operation_summary": {
                        "total": len(results),
                        "successful": success_count,
                        "failed": fail_count
                    },
                    "batch_operation_details": formatted["details"],
                    "batch_operation_report.md": formatted["report"]
                },
                "scratchpad": {
                    "batch_processor_reasoning": "\n".join(reasoning_lines)
                },
                "task_is_complete": True
            }

        except Exception as e:
            logger.error(f"BatchProcessorSpecialist error: {e}", exc_info=True)
            return {
                "messages": [AIMessage(content=f"Error performing batch operation: {str(e)}")],
                "task_is_complete": True
            }

    def _parse_operations(self, messages: List) -> List[FileOperation]:
        """
        Use LLM to parse user intent into list of file operations.

        The LLM analyzes the user request and produces a structured list of
        operations (create, move, sort, etc.). For SORT operations, the LLM
        decides destination directories based on file names.

        Args:
            messages: Conversation history

        Returns:
            List of FileOperation objects

        Raises:
            ValueError: If LLM cannot parse request
        """
        # System prompt guides the LLM to produce FileOperationList
        system_prompt = """You are a file operations assistant. Parse the user's request into a list of file operations.

Operation types:
- "write": Create or overwrite a file (use for "create file", "make file", etc.)
- "move": Move a file to a new location
- "mkdir": Create a directory
- "read": Read file contents
- "list": List directory contents
- "delete": Delete a file (note: may not be supported)

For SORT operations (e.g., "sort files into folders"):
1. Identify the files to sort
2. Decide appropriate destination directories based on file names
3. Return "move" operations with FULL destination paths (including filename)

CRITICAL - Move destinations must include filename:
- CORRECT: destination="a-m/e.txt" (full path with filename)
- WRONG: destination="a-m/" (directory only - causes EISDIR error)

For CREATE operations (e.g., "create files a.txt, b.txt"):
1. Extract each file path
2. Return "write" operations (content="" for empty files)

CRITICAL - Path format:
- Use ONLY relative paths. Never produce absolute paths.
- GOOD: ".", "to_sort", "to_sort/file.txt", "./archive/old.txt"
- BAD: "/to_sort", "/to_sort/file.txt", "/usr/bin"
- For alphabetic sorting: use "a-m/" and "n-z/" directories

Return a FileOperationList with all operations needed."""

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=system_prompt)] + messages,
            output_model_class=FileOperationList
        )

        response = self.llm_adapter.invoke(request)

        # Parse structured output
        json_response = response.get("json_response")
        if not json_response:
            raise ValueError(
                "LLM did not return valid JSON for FileOperationList. "
                f"Response keys: {list(response.keys())}"
            )

        try:
            operation_list = FileOperationList(**json_response)
        except Exception as e:
            raise ValueError(f"Failed to parse FileOperationList from LLM response: {e}")

        if not operation_list.operations:
            raise ValueError("LLM returned empty operation list")

        logger.info(
            f"Parsed {len(operation_list.operations)} operations: "
            f"{[op.type for op in operation_list.operations]}"
        )
        return operation_list.operations

    def _format_results(
        self,
        operations: List[FileOperation],
        results: List[OperationResult]
    ) -> Dict[str, Any]:
        """
        Format execution results for user and artifacts.

        Args:
            operations: Original operation list
            results: Execution results from executor

        Returns:
            Dict with summary, details, and report
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = len(results)
        success_count = sum(1 for r in results if r.success)
        fail_count = total - success_count
        success_rate = (success_count / total * 100) if total > 0 else 0

        # Build details list
        details = []
        for result in results:
            op = result.operation
            detail = {
                "type": op.type,
                "path": op.path,
                "destination": op.destination,
                "status": "success" if result.success else "failed",
            }
            if result.success:
                detail["result"] = result.result
            else:
                detail["error"] = result.error
            details.append(detail)

        # Build markdown report
        report_lines = [
            "# Batch Operation Report",
            "",
            f"**Timestamp**: {timestamp}",
            f"**Total Operations**: {total}",
            f"**Success Rate**: {success_rate:.0f}% ({success_count}/{total})",
            ""
        ]

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if successful:
            report_lines.append("## Successful Operations")
            for i, r in enumerate(successful, 1):
                op = r.operation
                if op.destination:
                    report_lines.append(f"{i}. ✓ {op.type}: `{op.path}` → `{op.destination}`")
                else:
                    report_lines.append(f"{i}. ✓ {op.type}: `{op.path}`")
                if r.result:
                    report_lines.append(f"   - Result: {r.result}")
            report_lines.append("")

        if failed:
            report_lines.append("## Failed Operations")
            for i, r in enumerate(failed, 1):
                op = r.operation
                if op.destination:
                    report_lines.append(f"{i}. ✗ {op.type}: `{op.path}` → `{op.destination}`")
                else:
                    report_lines.append(f"{i}. ✗ {op.type}: `{op.path}`")
                report_lines.append(f"   - Error: {r.error}")
            report_lines.append("")

        # Build summary
        if fail_count == 0:
            summary = f"Successfully completed all {total} operations."
        elif success_count == 0:
            summary = f"All {total} operations failed. Check batch_operation_report.md for details."
        else:
            failed_paths = [r.operation.path for r in failed]
            summary = f"Completed {success_count}/{total} operations. Failed: {', '.join(failed_paths)}"

        return {
            "summary": summary,
            "details": details,
            "report": "\n".join(report_lines)
        }
