# app/src/specialists/archiver_specialist.py
import logging
import os
import shutil
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List

from langgraph.graph import END

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..utils import state_pruner
from .schemas._archiver import SuccessReport
from .schemas._manifest import AtomicManifest, ArtifactManifest
from ..enums import CoreSpecialist

logger = logging.getLogger(__name__)


class ArchiverSpecialist(BaseSpecialist):
    """
    A procedural specialist responsible for summarizing the final state of the
    graph into an Atomic Archival Package (.zip) and saving it.
    It is the final step in a successful workflow.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # Determine the archive path with layered precedence.
        raw_path = os.getenv("AGENTIC_SCAFFOLD_ARCHIVE_PATH") or "./archives"
        self.archive_dir = os.path.expanduser(raw_path)
        self.pruning_strategy = self.specialist_config.get("pruning_strategy", "none")
        self.pruning_max_count = self.specialist_config.get("pruning_max_count", 50)
        os.makedirs(self.archive_dir, exist_ok=True)
        self._cleanup_orphaned_directories()

    def _cleanup_orphaned_directories(self) -> None:
        """
        Removes orphaned directories in the archive folder from failed/interrupted runs.
        Called at startup to ensure clean slate.
        """
        try:
            all_entries = [os.path.join(self.archive_dir, f) for f in os.listdir(self.archive_dir)]
            orphaned_dirs = [f for f in all_entries if os.path.isdir(f)]

            for orphan in orphaned_dirs:
                logger.warning(f"Cleaning up orphaned archive directory from failed run: {orphan}")
                shutil.rmtree(orphan)

            if orphaned_dirs:
                logger.info(f"Cleaned up {len(orphaned_dirs)} orphaned archive directory(ies) at startup.")
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned directories: {e}")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a final report, creates an Atomic Archival Package (.zip),
        and returns the package path.
        """
        logger.info(f"--- Archiver: Preparing Atomic Archival Package. ---")

        # Prune the state to get a clean conversation summary
        # pruned_state = state_pruner.prune_state(state) # REMOVED: prune_state removes 'messages' list

        final_user_response = state.get("artifacts", {}).get("final_user_response.md", "No final response was generated.")
        report_data = SuccessReport(
            final_user_response=final_user_response,
            routing_history=state.get("routing_history", []),
            artifacts=state.get("artifacts", {}),
            scratchpad=state.get("scratchpad", {}),
            conversation_summary=self._summarize_conversation(state.get("messages", [])), # Use full state messages
        )

        markdown_report = state_pruner.generate_success_report(report_data)

        # Create Atomic Archival Package
        package_path = self._create_atomic_package(state, markdown_report)
        self._prune_archive()

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter, # Will be None, but helper handles it
            content=f"Workflow complete. Atomic Archival Package created at: {package_path}",
        )

        # CRITICAL FIX for UI Crash (Unterminated string in JSON):
        # We replace the heavy artifacts in the returned state with just the package path
        # and the final response. This prevents massive JSON payloads from crashing the UI.
        # However, key artifacts like html_document.html must be included for downstream access.
        safe_artifacts = {
            "final_user_response.md": final_user_response,
            "archive_report.md": markdown_report,
            "archive_package_path": package_path
        }

        # Include key string artifacts that downstream consumers (tests, UI) need access to
        artifacts = state.get("artifacts", {})
        key_artifacts = ["html_document.html", "alpha_response.md", "bravo_response.md"]
        for key in key_artifacts:
            if key in artifacts and isinstance(artifacts[key], str):
                safe_artifacts[key] = artifacts[key]

        return {
            "messages": [ai_message],
            "artifacts": safe_artifacts, # Replaces the heavy artifacts dict
        }

    def _create_atomic_package(self, state: Dict[str, Any], report_md: str) -> str:
        """
        Creates a self-contained .zip package with manifest, artifacts, and report.
        Returns the absolute path to the .zip file.
        """
        run_id = str(uuid.uuid4())
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        package_name = f"run_{timestamp}_{run_id[:8]}"
        package_dir = os.path.join(self.archive_dir, package_name)
        
        os.makedirs(package_dir, exist_ok=True)

        try:
            # 1. Write Report
            with open(os.path.join(package_dir, "report.md"), "w", encoding="utf-8") as f:
                f.write(report_md)

            # 2. Write Artifacts
            artifacts = state.get("artifacts", {})
            artifact_manifests = []
            
            for key, content in artifacts.items():
                # #175: Serialize dict/list artifacts as JSON files
                if isinstance(content, (dict, list)):
                    import json as _json
                    content = _json.dumps(content, indent=2, default=str)
                    content_type = "application/json"
                elif isinstance(content, bytes):
                    content_type = "application/octet-stream"
                elif isinstance(content, str):
                    content_type = "text/plain"
                else:
                    logger.warning(f"Skipping artifact '{key}' - unsupported type {type(content)}")
                    continue

                # Sanitize filename
                safe_filename = "".join(c for c in key if c.isalnum() or c in "._- ")
                # Add .json extension for serialized dict/list artifacts
                if content_type == "application/json" and not safe_filename.endswith(".json"):
                    safe_filename += ".json"
                file_path = os.path.join(package_dir, safe_filename)

                mode = "wb" if isinstance(content, bytes) else "w"
                encoding = None if isinstance(content, bytes) else "utf-8"

                with open(file_path, mode, encoding=encoding) as f:
                    f.write(content)

                artifact_manifests.append(ArtifactManifest(
                    filename=safe_filename,
                    original_key=key,
                    content_type=content_type,
                    size_bytes=os.path.getsize(file_path)
                ))

            # 3. Write LLM Traces (for fine-tuning datasets)
            llm_traces = state.get("llm_traces", [])
            if llm_traces:
                traces_path = os.path.join(package_dir, "llm_traces.jsonl")
                with open(traces_path, "w", encoding="utf-8") as f:
                    for trace in llm_traces:
                        f.write(json.dumps(trace) + "\n")
                logger.info(f"Wrote {len(llm_traces)} LLM trace(s) to llm_traces.jsonl")
                artifact_manifests.append(ArtifactManifest(
                    filename="llm_traces.jsonl",
                    original_key="llm_traces",
                    content_type="application/jsonl",
                    size_bytes=os.path.getsize(traces_path)
                ))

            # 3b. Write State Timeline (observability snapshots at each specialist boundary)
            state_timeline = state.get("state_timeline", [])
            if state_timeline:
                timeline_path = os.path.join(package_dir, "state_timeline.jsonl")
                with open(timeline_path, "w", encoding="utf-8") as f:
                    for entry in state_timeline:
                        f.write(json.dumps(entry, default=str) + "\n")
                logger.info(f"Wrote {len(state_timeline)} state timeline entries to state_timeline.jsonl")
                artifact_manifests.append(ArtifactManifest(
                    filename="state_timeline.jsonl",
                    original_key="state_timeline",
                    content_type="application/jsonl",
                    size_bytes=os.path.getsize(timeline_path)
                ))

            # 4. Write Final State (Issue #39)
            final_state_path = os.path.join(package_dir, "final_state.json")
            with open(final_state_path, "w", encoding="utf-8") as f:
                json.dump(self._serialize_state(state), f, indent=2, default=str)
            logger.info("Wrote final_state.json to archive")
            artifact_manifests.append(ArtifactManifest(
                filename="final_state.json",
                original_key="final_state",
                content_type="application/json",
                size_bytes=os.path.getsize(final_state_path)
            ))

            # 5. Create Manifest
            manifest = AtomicManifest(
                run_id=run_id,
                routing_history=state.get("routing_history", []),
                artifacts=artifact_manifests,
                final_response_generated=bool(state.get("artifacts", {}).get("final_user_response.md")),
                termination_reason=state.get("scratchpad", {}).get("termination_reason", "success")
            )

            with open(os.path.join(package_dir, "manifest.json"), "w", encoding="utf-8") as f:
                f.write(manifest.model_dump_json(indent=2))

            # 6. Zip Package
            zip_path = shutil.make_archive(package_dir, 'zip', package_dir)
            logger.info(f"Created Atomic Archival Package: {zip_path}")
            
            return zip_path

        finally:
            # Cleanup temp dir
            if os.path.exists(package_dir):
                shutil.rmtree(package_dir)

    def _summarize_conversation(self, messages: List[Any]) -> str:
        """Creates a concise, human-readable summary of the agentic workflow for the report."""
        summary_lines = []
        for i, msg in enumerate(messages):
            # Handle both dicts (legacy/pruned) and BaseMessage objects (runtime)
            if isinstance(msg, dict):
                role = msg.get("role", "unknown")
                name = msg.get("name", "unknown")
                content = str(msg.get("content", "")).strip()
                kwargs = msg.get("additional_kwargs", {})
            else:
                # Assume LangChain BaseMessage object
                role = getattr(msg, "type", "unknown")
                name = getattr(msg, "name", "unknown")
                content = str(getattr(msg, "content", "")).strip()
                kwargs = getattr(msg, "additional_kwargs", {})

            # Shorten long content for display
            if len(content) > 120:
                content = content[:120] + "..."

            if role == "human" or role == "user":
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

    def _serialize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts GraphState to JSON-serializable dict.
        Handles LangChain BaseMessage objects in the messages list.
        """
        serialized = {}

        for key, value in state.items():
            if key == "messages":
                # Convert LangChain messages to dicts
                serialized[key] = [self._serialize_message(msg) for msg in value]
            elif key == "llm_traces":
                # Already serializable (list of dicts from model_dump)
                serialized[key] = value
            else:
                # Other state fields (artifacts, scratchpad, routing_history, etc.)
                serialized[key] = value

        return serialized

    def _serialize_message(self, msg: Any) -> Dict[str, Any]:
        """Converts a single message (BaseMessage or dict) to serializable dict."""
        if isinstance(msg, dict):
            return msg

        # LangChain BaseMessage object
        return {
            "type": getattr(msg, "type", "unknown"),
            "name": getattr(msg, "name", None),
            "content": getattr(msg, "content", ""),
            "additional_kwargs": getattr(msg, "additional_kwargs", {}),
        }

    def _save_report(self, report_content: str):
        """Saves the report content to a timestamped file."""
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        filename = f"run_{timestamp}.md"
        filepath = os.path.join(self.archive_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report_content)
            logger.info(f"Final report saved to {filepath}")
        except IOError as e:
            logger.error(f"Failed to save report to {filepath}: {e}")

    def _prune_archive(self):
        """Prunes the archive directory based on the configured strategy.

        Archives are training data - set pruning_max_count to 0 to disable pruning.
        """
        # 0 means no pruning (archives are training data)
        if self.pruning_strategy != "count" or self.pruning_max_count == 0:
            return

        # Only prune regular files (not directories from failed/incomplete archives)
        all_entries = [os.path.join(self.archive_dir, f) for f in os.listdir(self.archive_dir)]
        files = sorted([f for f in all_entries if os.path.isfile(f)], key=os.path.getmtime)

        # Warn about any orphaned directories (failed archive cleanup)
        orphaned_dirs = [f for f in all_entries if os.path.isdir(f)]
        if orphaned_dirs:
            logger.warning(f"Found {len(orphaned_dirs)} orphaned archive directories (likely from failed runs): {orphaned_dirs}")

        while len(files) > self.pruning_max_count:
            os.remove(files.pop(0))
            logger.info(f"Pruned old archive file.")