# app/src/specialists/archiver_specialist.py
import logging
import os
from datetime import datetime
from typing import Dict, Any, List

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..utils import state_pruner
from .schemas._archiver import SuccessReport

logger = logging.getLogger(__name__)


class ArchiverSpecialist(BaseSpecialist):
    """
    A procedural specialist responsible for summarizing the final state of the
    graph into a markdown report and saving it to a file. It is the final
    step in a successful workflow.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # Determine the archive path with layered precedence.
        raw_path = os.getenv("AGENTIC_SCAFFOLD_ARCHIVE_PATH") or "./archives"
        self.archive_dir = os.path.expanduser(raw_path)
        self.pruning_strategy = self.specialist_config.get("pruning_strategy", "none")
        self.pruning_max_count = self.specialist_config.get("pruning_max_count", 50)
        os.makedirs(self.archive_dir, exist_ok=True)

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a final report from the state, saves it, and crucially,
        returns the report content in the state to signal completion to the router.
        """
        logger.info(f"--- Archiver: Preparing final report. ---")

        pruned_state = state_pruner.prune_state(state)

        final_user_response = pruned_state.get("artifacts", {}).get("final_user_response.md", "No final response was generated.")
        report_data = SuccessReport(
            final_user_response=final_user_response,
            routing_history=pruned_state.get("routing_history", []),
            artifacts=pruned_state.get("artifacts", {}),
            scratchpad=pruned_state.get("scratchpad", {}),
            conversation_summary=self._summarize_conversation(pruned_state.get("messages", [])),
        )

        markdown_report = state_pruner.generate_success_report(report_data)

        self._save_report(markdown_report)
        self._prune_archive()

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter, # Will be None, but helper handles it
            content="Final report has been generated and the workflow is complete.",
        )

        # Preserve existing artifacts (like final_user_response.md) and add the new one.
        updated_artifacts = state.get("artifacts", {}).copy()
        updated_artifacts["archive_report.md"] = markdown_report

        return {
            "messages": [ai_message],
            "artifacts": updated_artifacts,
        }

    def _summarize_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Creates a concise, human-readable summary of the agentic workflow for the report."""
        summary_lines = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            name = msg.get("name", "unknown")
            content = str(msg.get("content", "")).strip()
            kwargs = msg.get("additional_kwargs", {})

            # Shorten long content for display
            if len(content) > 120:
                content = content[:120] + "..."

            if role == "user":
                summary_lines.append(f"{i+1}. **User:** *{content}*")

            elif role == "tool":
                summary_lines.append(f"{i+1}. **{name}:** *Tool execution result: {content}*")

            elif role == "ai":
                # For the Router, the decision is the most important part.
                if name == CoreSpecialist.ROUTER.value and "routing_decision" in kwargs:
                    decision = kwargs['routing_decision']
                    if decision == END:
                        summary_lines.append(f"{i+1}. **Router Specialist:** *Task is complete. Terminating workflow.*")
                    else:
                        summary_lines.append(f"{i+1}. **Router Specialist:** *Routing to specialist: {decision}...*")
                # For other specialists, use their conversational content.
                else:
                    summary_lines.append(f"{i+1}. **{name}:** *{content}*")

            else:
                summary_lines.append(f"{i+1}. **{name} ({role}):** *{content}*")

        return "\n".join(summary_lines)

    def _save_report(self, report_content: str):
        """Saves the report content to a timestamped file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"run_{timestamp}.md"
        filepath = os.path.join(self.archive_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report_content)
            logger.info(f"Final report saved to {filepath}")
        except IOError as e:
            logger.error(f"Failed to save report to {filepath}: {e}")

    def _prune_archive(self):
        """Prunes the archive directory based on the configured strategy."""
        if self.pruning_strategy == "count":
            files = sorted([os.path.join(self.archive_dir, f) for f in os.listdir(self.archive_dir)], key=os.path.getmtime)
            while len(files) > self.pruning_max_count:
                os.remove(files.pop(0))
                logger.info(f"Pruned old report file.")