"""
BatchProcessorSpecialist - Batch file operations with emergent LLM-driven sorting.

Architecture Pattern:
- Interface Layer: Interprets user batch operation requests
- Service Layer: Calls FileSpecialist via MCP for atomic operations
- Decision Logic: LLM decides file destinations based on names/content

Example Flow:
    User: "Sort these files into a-m/ and n-z/: e.txt, l.txt, n.txt, q.txt"
      ↓
    Router → BatchProcessorSpecialist
      ↓
    1. LLM parses user intent → BatchSortRequest
    2. (Optional) Read file metadata/content via MCP
    3. LLM generates BatchSortPlan with decisions
    4. Execute moves via FileSpecialist MCP calls
    5. Return detailed results in artifacts
"""
import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas._batch_ops import BatchSortRequest, BatchSortPlan, FileSortDecision

logger = logging.getLogger(__name__)


class BatchProcessorSpecialist(BaseSpecialist):
    """
    Specialist for batch file operations with emergent LLM-driven decision making.

    Processes collections of files atomically (single graph node execution) using
    internal iteration rather than graph-level looping.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute batch file sorting with emergent destination logic.
        """
        if not self.mcp_client:
            logger.error("BatchProcessorSpecialist: MCP client not available")
            return {
                "messages": [AIMessage(content="Error: File operations service not available.")],
                "task_is_complete": True
            }

        messages = self._get_enriched_messages(state)
        if not messages:
            return {
                "messages": [AIMessage(content="Error: No batch operation request to process.")],
                "task_is_complete": True
            }

        try:
            # Phase 1: Parse user intent into structured batch request
            batch_request = self._parse_batch_request(messages)

            # Phase 2: Gather file information (optional content reading)
            file_context = self._gather_file_context(batch_request)

            # Phase 3: LLM generates sorting plan
            sort_plan = self._generate_sort_plan(batch_request, file_context)

            # Phase 4: Execute file operations
            results = self._execute_batch_operations(sort_plan.decisions)

            # Phase 5: Generate report and artifacts
            report = self._generate_report(batch_request, results)

            # Build reasoning for Thought Stream observability
            reasoning_lines = [
                f"Parsed {len(batch_request.file_paths)} files → {batch_request.destination_directories}"
            ]
            for decision in sort_plan.decisions:
                reasoning_lines.append(f"  • {decision.file_path} → {decision.destination}: {decision.rationale}")
            if results["failed"]:
                reasoning_lines.append(f"⚠️ {len(results['failed'])} failed: {[f['file'] for f in results['failed']]}")

            return {
                "messages": [AIMessage(content=self._format_summary(results))],
                "artifacts": {
                    "batch_sort_summary": {
                        "total_files": results["total"],
                        "successful": len(results["successful"]),
                        "failed": len(results["failed"])
                    },
                    "batch_sort_details": results["successful"] + results["failed"],
                    "batch_sort_report.md": report
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

    def _parse_batch_request(self, messages: List) -> BatchSortRequest:
        """
        Use LLM to parse user's batch operation request.

        Args:
            messages: Conversation history

        Returns:
            Structured BatchSortRequest

        Raises:
            ValueError: If LLM cannot parse request
        """
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[BatchSortRequest],
            force_tool_call=True
        )

        response = self.llm_adapter.invoke(request)
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            raise ValueError(
                "Could not parse batch operation request. "
                "Please specify files and destinations clearly."
            )

        batch_request = BatchSortRequest(**tool_calls[0]['args'])
        logger.info(f"Phase 1 parsed: {len(batch_request.file_paths)} files={batch_request.file_paths}, "
                    f"destinations={batch_request.destination_directories}")
        return batch_request

    def _gather_file_context(self, batch_request: BatchSortRequest) -> str:
        """
        Gather file metadata (and optionally content) for LLM decision making.

        Args:
            batch_request: Parsed batch operation request

        Returns:
            Formatted context string with file information
        """
        context_lines = ["Files to sort:"]

        for i, file_path in enumerate(batch_request.file_paths, 1):
            try:
                # Check existence
                exists = self.mcp_client.call(
                    "file_specialist",
                    "file_exists",
                    path=file_path
                )

                if not exists:
                    context_lines.append(f"{i}. {file_path} (exists: no)")
                    continue

                # Optionally read content
                if batch_request.strategy.read_content:
                    content = self.mcp_client.call(
                        "file_specialist",
                        "read_file",
                        path=file_path
                    )
                    # Truncate long content
                    preview = content[:200] + "..." if len(content) > 200 else content
                    context_lines.append(f"{i}. {file_path} (exists: yes, preview: {preview})")
                else:
                    context_lines.append(f"{i}. {file_path} (exists: yes)")

            except Exception as e:
                logger.warning(f"Failed to gather context for {file_path}: {e}")
                context_lines.append(f"{i}. {file_path} (error: {str(e)})")

        return "\n".join(context_lines)

    def _generate_sort_plan(self, batch_request: BatchSortRequest, file_context: str) -> BatchSortPlan:
        """
        Use LLM to decide where each file should go.

        Args:
            batch_request: Parsed batch request with destinations
            file_context: Formatted file information

        Returns:
            BatchSortPlan with decisions for each file

        Raises:
            ValueError: If LLM does not return valid plan
        """
        planning_prompt = f"""You are sorting files into directories.

Available Destinations:
{chr(10).join(f'- {dest}' for dest in batch_request.destination_directories)}

{file_context}

For each file, decide which destination directory it should go into and provide a brief rationale.
Return a BatchSortPlan with decisions for all files."""

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=planning_prompt)],
            output_model_class=BatchSortPlan
        )

        response = self.llm_adapter.invoke(request)

        # Parse structured output - adapter returns json_response, we validate with Pydantic
        json_response = response.get("json_response")
        if not json_response:
            raise ValueError(
                "LLM did not return valid JSON for BatchSortPlan. "
                f"Response keys: {list(response.keys())}"
            )

        try:
            sort_plan = BatchSortPlan(**json_response)
        except Exception as e:
            raise ValueError(f"Failed to parse BatchSortPlan from LLM response: {e}")

        # Validate completeness: every requested file must have a decision
        decided_files = {d.file_path for d in sort_plan.decisions}
        requested_files = set(batch_request.file_paths)
        missing = requested_files - decided_files
        if missing:
            logger.warning(f"LLM omitted {len(missing)} files from sort plan: {missing}")
            # Don't raise - let partial results proceed, but log for observability

        return sort_plan

    def _execute_batch_operations(self, decisions: List[FileSortDecision]) -> Dict[str, Any]:
        """
        Execute file moves with granular error tracking.

        Args:
            decisions: List of file sorting decisions from LLM

        Returns:
            Dict with successful/failed operations and stats
        """
        results = {
            "successful": [],
            "failed": [],
            "total": len(decisions)
        }

        for decision in decisions:
            try:
                # Validate source exists
                exists = self.mcp_client.call(
                    "file_specialist",
                    "file_exists",
                    path=decision.file_path
                )

                if not exists:
                    results["failed"].append({
                        "file": decision.file_path,
                        "destination": decision.destination,
                        "rationale": decision.rationale,
                        "status": "failed",
                        "error": "File not found"
                    })
                    continue

                # Ensure destination directory exists
                self.mcp_client.call(
                    "file_specialist",
                    "create_directory",
                    path=decision.destination
                )

                # Compute new path
                filename = Path(decision.file_path).name
                new_path = f"{decision.destination.rstrip('/')}/{filename}"

                # Move file
                self.mcp_client.call(
                    "file_specialist",
                    "rename_file",
                    old_path=decision.file_path,
                    new_path=new_path
                )

                results["successful"].append({
                    "file": decision.file_path,
                    "destination": new_path,
                    "rationale": decision.rationale,
                    "status": "success"
                })

            except Exception as e:
                logger.error(f"Failed to move {decision.file_path}: {e}")
                results["failed"].append({
                    "file": decision.file_path,
                    "destination": decision.destination,
                    "rationale": decision.rationale,
                    "status": "failed",
                    "error": str(e)
                })

        return results

    def _generate_report(self, batch_request: BatchSortRequest, results: Dict[str, Any]) -> str:
        """
        Generate markdown report for archival.

        Args:
            batch_request: Original batch request
            results: Execution results with successes/failures

        Returns:
            Markdown-formatted report
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        success_rate = (len(results["successful"]) / results["total"] * 100) if results["total"] > 0 else 0

        lines = [
            "# Batch File Sort Report",
            "",
            f"**Timestamp**: {timestamp}",
            f"**Strategy**: {batch_request.strategy.strategy.capitalize()}",
            f"**Read Content**: {batch_request.strategy.read_content}",
            f"**Total Files**: {results['total']}",
            f"**Success Rate**: {success_rate:.0f}% ({len(results['successful'])}/{results['total']})",
            ""
        ]

        if results["successful"]:
            lines.append("## Successful Operations")
            for i, item in enumerate(results["successful"], 1):
                lines.append(f"{i}. ✓ `{item['file']}` → `{item['destination']}`")
                lines.append(f"   - Rationale: {item['rationale']}")
                lines.append("")

        if results["failed"]:
            lines.append("## Failed Operations")
            for i, item in enumerate(results["failed"], 1):
                lines.append(f"{i}. ✗ `{item['file']}` → `{item['destination']}`")
                lines.append(f"   - Error: {item['error']}")
                lines.append(f"   - Rationale: {item['rationale']}")
                lines.append("")

        return "\n".join(lines)

    def _format_summary(self, results: Dict[str, Any]) -> str:
        """
        Format user-facing summary message.

        Args:
            results: Execution results

        Returns:
            Concise summary string
        """
        total = results["total"]
        success_count = len(results["successful"])
        fail_count = len(results["failed"])

        if fail_count == 0:
            return f"Successfully sorted all {total} files."
        elif success_count == 0:
            return f"Failed to sort all {total} files. Check batch_sort_report.md for details."
        else:
            failed_files = ", ".join(item["file"] for item in results["failed"])
            return f"Sorted {success_count}/{total} files successfully. Failed: {failed_files}"
