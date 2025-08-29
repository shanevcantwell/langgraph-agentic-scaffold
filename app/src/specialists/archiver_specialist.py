# ./app/src/archiver_specialist.py
import os
import logging
from typing import Dict, Any, List
import json
import codecs
import html
from datetime import datetime
from langchain_core.messages import AIMessage, BaseMessage
from .base import BaseSpecialist

logger = logging.getLogger(__name__)

class ArchiverSpecialist(BaseSpecialist):
    """
    A procedural specialist that creates a final summary report of the agentic run.
    It gathers all artifacts and conversation history into a single markdown file.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # This is a procedural specialist, so no LLM adapter is needed.
        if os.environ.get("AGENTIC_SCAFFOLD_ARCHIVER_ENABLED", "true").lower() == "false":
            self.is_enabled = False
        # Determine the archive path with a clear order of precedence:
        # 1. Environment variable (AGENTIC_SCAFFOLD_ARCHIVE_PATH) for user-level overrides.
        # 2. Specialist configuration in config.yaml (archive_path) for project-level settings.
        # 3. A hardcoded default ('./archives') as a fallback.
        env_path = os.environ.get("AGENTIC_SCAFFOLD_ARCHIVE_PATH")
        config_path = self.specialist_config.get("archive_path")
        default_path = "./archives"
        self.archive_dir_path = env_path or config_path or default_path

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gathers all artifacts from the state and compiles a final report.
        """
        logger.info("Executing ArchiverSpecialist to create final report.")

        report_parts = []
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

        # --- Header ---
        report_parts.append(f"# Archive Report: Run {run_id}")
        report_parts.append(f"- **Status:** Completed")
        report_parts.append("---")

        # --- Triage Recommendations ---
        if triage_recs := state.get("triage_recommendations"):
            report_parts.append("## 🚦 Triage Recommendations")
            if triage_recs:
                recs_md = "\n".join([f"- `{rec}`" for rec in triage_recs])
                report_parts.append(f"The initial prompt was triaged with the following specialist recommendations:\n{recs_md}")
            else:
                report_parts.append("The Triage Specialist found no relevant specialists for the initial prompt.")
            report_parts.append("---")

        # --- System Plan ---
        if system_plan := state.get("system_plan"):
            report_parts.append("## 📝 System Plan")
            report_parts.append(f"_{system_plan.get('plan_summary', 'No plan summary provided.')}_")
            if steps := system_plan.get('execution_steps'):
                steps_md = "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
                report_parts.append(f"\n**Execution Steps:**\n{steps_md}")
            report_parts.append("---")

        # --- Artifacts ---
        artifacts = {
            "HTML": ("html_artifact", "html"),
            "JSON": ("json_artifact", "json"),
            "Text": ("text_to_process", "text"),
        }
        has_artifacts = False
        artifact_section = ["## artifacts"]
        for title, (key, lang) in artifacts.items():
            if content := state.get(key):
                has_artifacts = True

                # For structured data, pretty-print it as JSON. For others, just use string representation.
                if isinstance(content, (dict, list)):
                    content_str = json.dumps(content, indent=2)
                else:
                    content_str = str(content)

                # Process content for readability in the final report.
                if key == "html_artifact":
                    # Un-escape HTML entities to make the raw HTML readable in the report.
                    final_content = html.unescape(content_str)
                else:
                    try:
                        final_content = codecs.decode(content_str, 'unicode_escape')
                    except (UnicodeDecodeError, TypeError):
                        logger.warning(f"Could not unicode-decode artifact '{key}'. Using raw string representation.")
                        final_content = content_str

                artifact_section.append(f"### 📄 {title} Output")
                artifact_section.append(f"```{lang}\n{final_content}\n```")
        
        if has_artifacts:
            report_parts.extend(artifact_section)
            report_parts.append("---")

        # --- Conversation Summary ---
        messages: List[BaseMessage] = state.get("messages", [])
        if messages:
            report_parts.append("## 💬 Conversation Summary")
            # Create a simplified, clean summary of the interaction flow
            summary_lines = []
            for i, msg in enumerate(messages):
                # Robustly get the sender's name, falling back to type, then to a default.
                sender_name_val = getattr(msg, 'name', None) or getattr(msg, 'type', 'unknown_sender')
                sender = str(sender_name_val).replace('_', ' ').title()

                # Check for the LLM name in additional_kwargs and append it if present.
                llm_name = msg.additional_kwargs.get("llm_name") if hasattr(msg, 'additional_kwargs') else None
                if llm_name:
                    sender += f" ({llm_name})"

                content_preview = msg.content.split('\n')[0] # First line for brevity
                summary_lines.append(f"{i+1}. **{sender}:** *{content_preview}...*")
            report_parts.append("\n".join(summary_lines))

        final_report = "\n\n".join(report_parts)

        # --- Save Report to File ---
        if self.is_enabled:
            try:
                os.makedirs(self.archive_dir_path, exist_ok=True)
                file_path = os.path.join(self.archive_dir_path, f"run_report_{run_id}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(final_report)
                logger.info(f"Successfully saved archive report to {file_path}")
            except Exception as e:
                logger.error(f"Failed to save archive report. Error: {e}", exc_info=True)

        ai_message = AIMessage(
            content="Final report has been generated and the workflow is complete.",
            name=self.specialist_name
        )

        # The ChiefOfStaff is configured to route from this specialist to END.
        # We do not need to set next_specialist; the graph structure handles it.
        return {
            "messages": [ai_message],
            "archive_report": final_report,
            "task_is_complete": True
        }
