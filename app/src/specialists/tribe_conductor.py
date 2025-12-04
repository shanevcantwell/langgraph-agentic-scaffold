import logging
from typing import Dict, Any, List, Optional

from ..specialists.base import BaseSpecialist
from ..utils.manifest_manager import ManifestManager
from ..convening.agent_router import AgentRouter
from ..convening.semantic_firewall import SemanticFirewall
from ..specialists.schemas._manifest import AgentAffinity, BranchStatus

logger = logging.getLogger(__name__)

class TribeConductor(BaseSpecialist):
    """
    The "CPU" of the Convening architecture.
    
    Responsibilities:
    1. Orchestrate the execution cycle (Route -> Execute -> Commit).
    2. Manage context switching (Heap <-> Stack).
    3. Coordinate synchronous subroutines (Fishbowl).
    4. Trigger synthesis events.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # Components will be initialized lazily or via dependency injection if possible.
        # For now, we initialize stateless components here.
        self.agent_router = AgentRouter()
        self.firewall = SemanticFirewall()
        self.manifest_manager: Optional[ManifestManager] = None

    def _get_manifest_manager(self, state: Dict[str, Any]) -> ManifestManager:
        """
        Retrieve or initialize the ManifestManager based on state.
        """
        # Priority: State > Config > Default
        manifest_path = state.get("manifest_path")
        if not manifest_path:
            manifest_path = self.specialist_config.get("manifest_path")
        
        if not manifest_path:
            # Fallback to workspace default
            manifest_path = "workspace/manifest.json"
            logger.warning(f"TribeConductor: No manifest_path in state or config. Defaulting to {manifest_path}")
        
        if not self.manifest_manager or str(self.manifest_manager.manifest_path) != manifest_path:
            self.manifest_manager = ManifestManager(manifest_path)
            # Try to load existing manifest, ignore if not found (will be created)
            try:
                self.manifest_manager.load()
            except FileNotFoundError:
                pass
                
        return self.manifest_manager

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution cycle:
        1. Check for active Fishbowl (debate).
        2. Check for pending Synthesis.
        3. Assess active branch status.
        4. Route to appropriate agent.
        """
        logger.info("TribeConductor: Starting execution cycle")
        
        manager = self._get_manifest_manager(state)
        active_branch_id = state.get("active_branch_id")
        
        # --- 1. Fishbowl Handling (Subroutine) ---
        if state.get("fishbowl_active"):
            return self._handle_fishbowl(state)

        # --- 2. Synthesis Handling ---
        if state.get("synthesis_pending"):
            return self._handle_synthesis(state)

        # --- 3. Branch Assessment & Routing ---
        if not active_branch_id:
            # No active branch -> Triage / Root
            # For now, we default to creating a root branch or routing to Triage
            # This logic will be expanded.
            logger.info("TribeConductor: No active branch, routing to Triage/Default")
            return {
                "scratchpad": {
                    "next_specialist": "triage_architect", # Or router_specialist
                    "routing_reason": "No active branch"
                }
            }

        # Load branch metadata
        try:
            branch = manager.manifest.branches[active_branch_id]
        except (KeyError, AttributeError):
            logger.error(f"TribeConductor: Active branch {active_branch_id} not found in manifest")
            return {"error": f"Branch {active_branch_id} not found"}

        # Check status
        if branch.status == BranchStatus.COMPLETE:
             # Branch done -> Return to parent or synthesis
             pass
        elif branch.status == BranchStatus.CLARIFICATION_REQUIRED:
             # Route to DialogueSpecialist (HitL)
             return {
                 "scratchpad": {
                     "next_specialist": "dialogue_specialist",
                     "routing_reason": "Branch requires clarification"
                 }
             }

        # Route based on Affinity
        next_agent_id = self.agent_router.route(branch.affinity)
        
        # Dereference context (Load Heap -> Stack)
        context_content = self.dereference_branch(manager, active_branch_id)
        
        # Prepare state for the agent
        # We inject the context into the scratchpad or messages
        return {
            "scratchpad": {
                "next_specialist": next_agent_id,
                "routing_reason": f"Routing to {branch.affinity} specialist",
                "loaded_context": context_content
            }
        }

    def dereference_branch(self, manager: ManifestManager, branch_id: str) -> str:
        """
        Load branch context from Heap to Stack.
        Applies Semantic Firewall (Input Sanitization).
        """
        # TODO: Implement actual file reading via manager (manager needs get_branch_content method?)
        # For now, we assume manager has a way to get content or we read the file path.
        # The ManifestManager in ADR-022 doesn't have a 'read_content' method explicitly, 
        # but it has the filepath.
        
        branch = manager.manifest.branches.get(branch_id)
        if not branch:
            return ""
            
        # Read file content (Manager should probably handle this to ensure path safety, 
        # but for now we do it here using the safe path from the branch)
        # Wait, manager._validate_path ensures the path in the branch object is safe.
        
        full_path = manager.project_root / branch.filepath
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read branch file {full_path}: {e}")
            return ""

        # Apply Firewall
        sanitized_content = self.firewall.sanitize_input(content)
        return sanitized_content

    def commit_branch(self, manager: ManifestManager, branch_id: str, content: str, agent_id: str):
        """
        Save agent output from Stack to Heap.
        Applies Semantic Firewall (Output Sanitization).
        """
        # Apply Firewall
        clean_content = self.firewall.sanitize_output(content)
        if clean_content is None:
            logger.warning(f"TribeConductor: Output from {agent_id} rejected by firewall")
            return

        # Update Manifest
        # We need to update the file and log the contribution.
        # Manager needs methods for this.
        # manager.update_branch_content(...) ? 
        # The ADR says: "commit_branch(branch_id, content, agent_id): Store results Stack -> Heap"
        
        # 1. Write to file
        branch = manager.manifest.branches.get(branch_id)
        if branch:
            # Use atomic write via manager
            manager.write_branch_content(branch_id, clean_content)
            
            # 2. Log contribution
            manager.log_contribution(
                branch_id=branch_id,
                agent_id=agent_id,
                agent_model="unknown", # TODO: Get from state
                summary="Agent update", # TODO: Generate summary
                content=clean_content
            )

    def _handle_fishbowl(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manage the synchronous debate loop.
        """
        # Placeholder for ADR-017 logic
        logger.info("TribeConductor: Handling Fishbowl")
        return {
            "scratchpad": {
                "next_specialist": "progenitor_alpha_specialist", # Start with Alpha
                "routing_reason": "Fishbowl debate"
            }
        }

    def _handle_synthesis(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manage synthesis of converged branches.
        """
        logger.info("TribeConductor: Handling Synthesis")
        return {
            "scratchpad": {
                "next_specialist": "tiered_synthesizer_specialist",
                "routing_reason": "Synthesis pending"
            }
        }
