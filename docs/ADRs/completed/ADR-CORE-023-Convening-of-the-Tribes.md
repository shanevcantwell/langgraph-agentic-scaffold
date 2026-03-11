# ADR-CORE-023: Convening of the Tribes — Multi-Model Orchestration

**Status:** Completed
**Date:** 2025-12-03  
**Context:** langgraph-agentic-scaffold (LAS)  
**Layer:** Orchestration (Policy)  
**Depends On:** ADR-CORE-022 (The Heap)  
**Supersedes:** ADR-CORE-017 (Fishbowl)  
**Relates to:** ADR-CORE-018 (Checkpoints), ADR-CORE-020 (InferenceSpecialist)  

---

## Abstract

This ADR establishes the orchestration policy for multi-model collaboration in LAS. Building on ADR-CORE-022 (The Heap), it defines:

- **TribeConductor:** The "CPU" that routes work to agents and manages context switching
- **AgentRouter:** Affinity-based assignment of branches to agent types
- **Fishbowl:** Synchronous debate subroutine (preserved from ADR-017)
- **Synthesis Events:** Controlled merging of branch findings
- **Semantic Firewall:** I/O filtering between Heap and context window

This is POLICY (how agents collaborate) built on MECHANISM (The Heap).

---

## 1. Context and Problem Statement

### 1.1 What The Heap Provides

ADR-CORE-022 established the persistence layer:
- `ProjectManifest` tracks project state
- `BranchPointer` references work in progress
- `ManifestManager` handles atomic I/O
- Security (hash chains, path confinement) is built-in

But the Heap is dumb storage. It doesn't know:
- Which agent should work on which branch
- When to load context into the Stack
- When branches should be synthesized
- How to handle conflicts between agents

### 1.2 The Orchestration Gap

| Question | Heap (022) | Convening (023) |
|----------|------------|-----------------|
| Where is state stored? | ✅ Filesystem | — |
| Which agent works on what? | — | ✅ AgentRouter |
| When is context loaded? | — | ✅ TribeConductor |
| How do agents debate? | — | ✅ Fishbowl subroutine |
| When do branches merge? | — | ✅ Synthesis Events |
| What filters I/O? | — | ✅ Semantic Firewall |

### 1.3 Preserving the Fishbowl

ADR-CORE-017 introduced synchronous Alpha/Bravo debate. This pattern remains valuable for:
- Immediate contradiction resolution
- High-bandwidth back-and-forth on specific issues
- Quality improvement before user sees output

Rather than discard it, we subsume Fishbowl as a **subroutine** within the larger async architecture.

---

## 2. Decision

We will implement **Convening of the Tribes** as the orchestration layer for multi-model collaboration.

### 2.1 Core Metaphor: The CPU

| Concept | CPU | Convening |
|---------|-----|-----------|
| **Scheduler** | Decides which process runs | TribeConductor routes to agents |
| **Context Switch** | Save/restore process state | Load branch context into Stack |
| **Registers** | Fast execution memory | Active context window |
| **RAM/Disk** | Slower persistent storage | The Heap (Manifest + files) |
| **Interrupts** | External events | HitL clarification, synthesis triggers |

### 2.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CONVENING ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    THE STACK (Context Window)                         │  │
│  │                                                                       │  │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │  │
│  │   │   System    │  │  Context    │  │   Active    │                  │  │
│  │   │   Prompt    │  │  Snippet    │  │  Inference  │                  │  │
│  │   └─────────────┘  └─────────────┘  └──────┬──────┘                  │  │
│  │                                            │                          │  │
│  │            ┌───────────────────────────────┘                          │  │
│  │            │ Fishbowl (when active)                                   │  │
│  │            ▼                                                          │  │
│  │   ┌─────────────────────────────────────────────────┐                │  │
│  │   │  Alpha ◄──► Bravo  (Synchronous Debate Loop)    │                │  │
│  │   └─────────────────────────────────────────────────┘                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                              │
│                              │ Commit                                       │
│                              ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    SEMANTIC FIREWALL                                  │  │
│  │   Read: Sanitize before loading │ Write: Compress before storing      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                              │
│                              ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    THE CPU (TribeConductor)                           │  │
│  │                                                                       │  │
│  │   ┌─────────────────┐    ┌─────────────────┐    ┌────────────────┐   │  │
│  │   │  AgentRouter    │    │ Context Switch  │    │ Synthesis      │   │  │
│  │   │  (Affinity)     │    │ (Load/Store)    │    │ Scheduler      │   │  │
│  │   └────────┬────────┘    └────────┬────────┘    └───────┬────────┘   │  │
│  │            │                      │                     │            │  │
│  └────────────┼──────────────────────┼─────────────────────┼────────────┘  │
│               │                      │                     │               │
│               ▼                      ▼                     ▼               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    THE HEAP (ADR-CORE-022)                            │  │
│  │   Manifest.json ─► Branch Documents ─► Contribution Log               │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Specifications

### 3.1 TribeConductor (The CPU)

The Conductor manages the execution cycle:

1. **FETCH:** Load Manifest, assess current state
2. **DECODE:** Determine which branch needs work, check for triggers
3. **DISPATCH:** Route to appropriate agent via AgentRouter
4. **COMMIT:** Save results back to Heap via Semantic Firewall
5. **CHECK INTERRUPTS:** HitL requests, synthesis triggers, staleness

```python
# app/src/specialists/tribe_conductor.py
"""
TribeConductor - The CPU for multi-model orchestration.

Responsibilities:
- Route work to agents based on branch affinity
- Manage context switching (load/store from Heap)
- Coordinate Fishbowl debates when needed
- Trigger synthesis events
- Handle interrupts (HitL, staleness)
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from langchain_core.messages import BaseMessage, SystemMessage

from app.src.utils.manifest_manager import ManifestManager
from app.src.specialists.schemas import (
    BranchPointer,
    BranchStatus,
    BranchPhase,
    AgentAffinity,
)

logger = logging.getLogger(__name__)


class TribeConductor:
    """
    Orchestrates multi-model collaboration.
    
    The Conductor is the ONLY component that:
    - Decides which agent works on which branch
    - Loads context from Heap to Stack
    - Commits results from Stack to Heap
    - Triggers Fishbowl debates
    - Schedules synthesis events
    """
    
    # Configuration
    MAX_FISHBOWL_TURNS = 4
    STALENESS_THRESHOLD_HOURS = 72
    
    def __init__(
        self,
        manifest_manager: ManifestManager,
        semantic_firewall: Optional["SemanticFirewall"] = None,
    ):
        self.manifest = manifest_manager
        self.firewall = semantic_firewall
        
        # Fishbowl state (when active)
        self._fishbowl_buffer: List[Dict] = []
        self._fishbowl_turn_count: int = 0
        self._fishbowl_active: bool = False
    
    # =========================================================================
    # MAIN EXECUTION CYCLE
    # =========================================================================
    
    def execute_cycle(self, state: Dict) -> Dict:
        """
        Main execution entry point.
        
        Returns state updates for LangGraph.
        """
        # If Fishbowl is active, handle synchronous debate
        if self._fishbowl_active:
            return self._handle_fishbowl(state)
        
        # Otherwise, assess and route
        return self._assess_and_route(state)
    
    def _assess_and_route(self, state: Dict) -> Dict:
        """Assess Heap state and determine next action."""
        updates = {}
        
        # Check for synthesis-ready branches
        ready = self._get_synthesis_ready_branches()
        if ready:
            updates["synthesis_pending"] = [b.id for b in ready]
        
        # Check for stale branches
        stale = self.manifest.get_stale_branches(self.STALENESS_THRESHOLD_HOURS)
        if stale:
            updates["stale_warning"] = [b.id for b in stale]
            logger.warning(f"Stale branches detected: {[b.id for b in stale]}")
        
        # Check for HitL requirements
        hitl = self.manifest.get_branches_by_status(BranchStatus.CLARIFICATION_REQUIRED)
        if hitl:
            updates["hitl_required"] = [b.id for b in hitl]
            return updates  # Pause for human
        
        # Route next work
        next_branch = self._select_next_branch()
        if next_branch:
            updates["next_action"] = {
                "action": "work_branch",
                "branch_id": next_branch.id,
                "affinity": next_branch.affinity.value,
            }
        else:
            updates["next_action"] = {"action": "idle"}
        
        return updates
    
    # =========================================================================
    # CONTEXT SWITCHING (Load/Store)
    # =========================================================================
    
    def dereference_branch(self, branch_id: str) -> List[BaseMessage]:
        """
        LOAD: Heap → Stack
        
        Load branch context into messages for agent consumption.
        Applies Semantic Firewall on read path.
        """
        branch = self.manifest.get_branch(branch_id)
        if not branch:
            raise ValueError(f"Branch '{branch_id}' not found")
        
        # Get context snippet
        context = branch.context_snippet
        
        # Apply firewall (read-side sanitization)
        if self.firewall:
            context, warnings = self.firewall.sanitize_input(context)
            if warnings:
                logger.warning(f"Firewall warnings for {branch_id}: {warnings}")
        
        # Build context messages
        system_content = f"""You are working on branch: {branch.title}

Branch Status: {branch.status.value}
Branch Phase: {branch.phase.value}
Affinity: {branch.affinity.value}

Context from previous work:
{context}

Continue the investigation. Focus on the specific scope of this branch.
"""
        
        return [SystemMessage(content=system_content)]
    
    def commit_branch(
        self,
        branch_id: str,
        content: str,
        agent_id: str,
        agent_model: str,
        new_snippet: Optional[str] = None,
    ) -> None:
        """
        STORE: Stack → Heap
        
        Commit work results back to persistent storage.
        Applies Semantic Firewall on write path.
        """
        # Apply firewall (write-side compression)
        if self.firewall:
            content = self.firewall.sanitize_output(content)
        
        # Log contribution (with hash chain)
        self.manifest.log_contribution(
            branch_id=branch_id,
            agent_id=agent_id,
            agent_model=agent_model,
            summary=content[:100] + "..." if len(content) > 100 else content,
            content=content,
        )
        
        # Update context snippet if provided
        if new_snippet:
            self.manifest.update_context_snippet(branch_id, new_snippet)
        
        logger.info(f"Committed work to branch '{branch_id}' by {agent_id}")
    
    # =========================================================================
    # FISHBOWL (Synchronous Debate Subroutine)
    # =========================================================================
    
    def start_fishbowl(self, topic: str, branch_id: Optional[str] = None) -> None:
        """
        Initialize a Fishbowl debate.
        
        The Fishbowl is a synchronous Alpha/Bravo debate loop
        for immediate contradiction resolution.
        """
        self._fishbowl_active = True
        self._fishbowl_buffer = []
        self._fishbowl_turn_count = 0
        self._fishbowl_topic = topic
        self._fishbowl_branch = branch_id
        
        logger.info(f"Fishbowl started on topic: {topic}")
    
    def _handle_fishbowl(self, state: Dict) -> Dict:
        """Handle synchronous Fishbowl debate."""
        
        # Check termination conditions
        if self._fishbowl_turn_count >= self.MAX_FISHBOWL_TURNS:
            return self._end_fishbowl("max_turns")
        
        if self._detect_circular_argument():
            return self._end_fishbowl("circular_detected")
        
        # Determine next speaker
        if not self._fishbowl_buffer:
            next_speaker = "alpha"
            phase = "opening"
        else:
            last_speaker = self._fishbowl_buffer[-1]["speaker"]
            next_speaker = "bravo" if last_speaker == "alpha" else "alpha"
            phase = "rebuttal"
        
        self._fishbowl_turn_count += 1
        
        return {
            "fishbowl_active": True,
            "fishbowl_phase": phase,
            "fishbowl_next_speaker": next_speaker,
            "fishbowl_topic": self._fishbowl_topic,
            "fishbowl_history": self._fishbowl_buffer.copy(),
        }
    
    def record_fishbowl_turn(self, speaker: str, content: str) -> None:
        """Record a turn in the Fishbowl debate."""
        self._fishbowl_buffer.append({
            "speaker": speaker,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def _end_fishbowl(self, reason: str) -> Dict:
        """End Fishbowl and synthesize result."""
        self._fishbowl_active = False
        
        # Synthesize the debate
        synthesis = self._synthesize_fishbowl()
        
        # If attached to a branch, commit the synthesis
        if self._fishbowl_branch:
            self.commit_branch(
                branch_id=self._fishbowl_branch,
                content=synthesis,
                agent_id="fishbowl_synthesizer",
                agent_model="internal",
            )
        
        logger.info(f"Fishbowl ended: {reason}")
        
        return {
            "fishbowl_active": False,
            "fishbowl_result": synthesis,
            "fishbowl_end_reason": reason,
        }
    
    def _synthesize_fishbowl(self) -> str:
        """Synthesize Fishbowl debate into summary."""
        # This would typically call a synthesizer agent
        # For now, return formatted debate
        lines = [f"Fishbowl Debate Summary: {self._fishbowl_topic}"]
        lines.append(f"Turns: {len(self._fishbowl_buffer)}")
        lines.append("")
        
        for turn in self._fishbowl_buffer:
            lines.append(f"[{turn['speaker'].upper()}]: {turn['content'][:200]}...")
        
        return "\n".join(lines)
    
    def _detect_circular_argument(self) -> bool:
        """Detect if debate has become repetitive."""
        if len(self._fishbowl_buffer) < 4:
            return False
        
        # Simple heuristic: check for repeated key phrases
        recent = [t["content"][:200] for t in self._fishbowl_buffer[-4:]]
        # Could use embedding similarity for more robust detection
        return len(set(recent)) < len(recent)
    
    # =========================================================================
    # ROUTING LOGIC
    # =========================================================================
    
    def _select_next_branch(self) -> Optional[BranchPointer]:
        """
        Select next branch to work on.
        
        Priority:
        1. ACTIVE branches with satisfied dependencies
        2. Oldest first (fairness)
        """
        active = self.manifest.get_active_branches()
        
        # Filter to those with satisfied dependencies
        ready = [
            b for b in active
            if self.manifest.check_dependencies_satisfied(b.id)
        ]
        
        if not ready:
            return None
        
        # Sort by created_at (oldest first for fairness)
        ready.sort(key=lambda b: b.created_at)
        return ready[0]
    
    def _get_synthesis_ready_branches(self) -> List[BranchPointer]:
        """Find branches ready for synthesis."""
        return self.manifest.get_branches_by_status(BranchStatus.CONVERGED)
    
    # =========================================================================
    # SYNTHESIS EVENTS
    # =========================================================================
    
    def trigger_synthesis(
        self,
        branch_ids: List[str],
        target: str = "trunk",
    ) -> str:
        """
        Merge branch findings into target.
        
        Args:
            branch_ids: Branches to synthesize
            target: Where to merge ("trunk" or another branch_id)
        
        Returns:
            Synthesis summary
        """
        branches = [self.manifest.get_branch(bid) for bid in branch_ids]
        branches = [b for b in branches if b is not None]
        
        if not branches:
            raise ValueError("No valid branches to synthesize")
        
        # Collect context snippets
        contexts = [f"## {b.title}\n{b.context_snippet}" for b in branches]
        combined = "\n\n---\n\n".join(contexts)
        
        # Mark branches as complete
        for branch in branches:
            self.manifest.update_branch_status(branch.id, BranchStatus.COMPLETE)
        
        logger.info(f"Synthesis triggered for branches: {branch_ids}")
        
        # Return combined context (actual synthesis would involve an agent)
        return combined
```

### 3.2 AgentRouter (Affinity-Based Dispatch)

```python
# app/src/convening/agent_router.py
"""
AgentRouter - Maps branch affinity to agent execution.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List

from app.src.specialists.schemas import AgentAffinity


@dataclass
class AgentProfile:
    """Configuration for an available agent."""
    agent_id: str
    model: str
    affinities: List[AgentAffinity]
    latency_class: str   # "low", "medium", "high"
    cost_class: str      # "minimal", "medium", "high"
    is_tool_node: bool = False  # True = no LLM, just function execution


class AgentRouter:
    """
    Routes work to agents based on branch affinity.
    
    Design: Workers don't know about each other.
    The Router knows about workers. No hard edges between workers.
    """
    
    # Default agent pool
    DEFAULT_POOL: Dict[str, AgentProfile] = {
        "progenitor_alpha": AgentProfile(
            agent_id="progenitor_alpha",
            model="claude-opus-4",
            affinities=[AgentAffinity.ARCHITECTURE],
            latency_class="high",
            cost_class="high",
        ),
        "progenitor_bravo": AgentProfile(
            agent_id="progenitor_bravo",
            model="claude-sonnet-4",
            affinities=[AgentAffinity.IMPLEMENTATION, AgentAffinity.DEFAULT],
            latency_class="medium",
            cost_class="medium",
        ),
        "inference_specialist": AgentProfile(
            agent_id="inference_specialist",
            model="claude-sonnet-4",
            affinities=[AgentAffinity.INFERENCE],
            latency_class="medium",
            cost_class="medium",
        ),
        "research_specialist": AgentProfile(
            agent_id="research_specialist",
            model="gemini-2.0-flash",
            affinities=[AgentAffinity.RESEARCH],
            latency_class="medium",
            cost_class="medium",
        ),
        "local_monitor": AgentProfile(
            agent_id="local_monitor",
            model="lfm2-vl-1.6b",
            affinities=[AgentAffinity.MONITORING],
            latency_class="low",
            cost_class="minimal",
            is_tool_node=False,  # Still uses LLM, just local
        ),
    }
    
    def __init__(self, pool: Optional[Dict[str, AgentProfile]] = None):
        self.pool = pool or self.DEFAULT_POOL
    
    def route(
        self,
        affinity: AgentAffinity,
        prefer_fast: bool = False,
        prefer_cheap: bool = False,
    ) -> str:
        """
        Select agent for given affinity.
        
        Returns:
            agent_id of selected agent
        """
        # Find agents that handle this affinity
        candidates = [
            (aid, profile) for aid, profile in self.pool.items()
            if affinity in profile.affinities
        ]
        
        if not candidates:
            # Fallback to DEFAULT affinity
            candidates = [
                (aid, profile) for aid, profile in self.pool.items()
                if AgentAffinity.DEFAULT in profile.affinities
            ]
        
        if not candidates:
            raise ValueError(f"No agent available for affinity: {affinity}")
        
        # Apply preferences
        if prefer_fast:
            candidates.sort(key=lambda x: {"low": 0, "medium": 1, "high": 2}[x[1].latency_class])
        elif prefer_cheap:
            candidates.sort(key=lambda x: {"minimal": 0, "medium": 1, "high": 2}[x[1].cost_class])
        
        return candidates[0][0]
    
    def get_profile(self, agent_id: str) -> Optional[AgentProfile]:
        """Get configuration for agent."""
        return self.pool.get(agent_id)
```

### 3.3 Semantic Firewall (I/O Filter)

```python
# app/src/convening/semantic_firewall.py
"""
Semantic Firewall - Sanitizes data between Heap and Stack.

Read Path (Heap → Stack): Prevents prompt injection
Write Path (Stack → Heap): Compresses and validates output
"""

import re
from typing import Tuple, List
import logging

logger = logging.getLogger(__name__)


class SemanticFirewall:
    """
    I/O filter between Heap and Stack.
    
    Prevents:
    - Prompt injection via stored context
    - Hallucination drift via accumulated errors
    - Low-entropy token accumulation ("slop")
    """
    
    # Patterns that suggest prompt injection
    INJECTION_PATTERNS = [
        r'ignore\s+(all\s+)?previous\s+instructions',
        r'you\s+are\s+now\s+in\s+(\w+\s+)?mode',
        r'system\s*:\s*',
        r'<\s*system\s*>',
        r'IMPORTANT:\s*disregard',
        r'new\s+instructions\s*:',
        r'override\s+(safety|guidelines)',
        r'jailbreak',
        r'DAN\s+mode',
    ]
    
    # Patterns that indicate low-value content
    SLOP_PATTERNS = [
        r'^As an AI( language model)?,',
        r'^I\'d be happy to',
        r'^Certainly!',
        r'^Of course!',
        r'^Great question!',
    ]
    
    MAX_CONTEXT_LENGTH = 2000  # ~500 words
    
    def sanitize_input(self, content: str) -> Tuple[str, List[str]]:
        """
        Sanitize content before loading into Stack.
        
        Returns:
            Tuple of (sanitized_content, warnings)
        """
        warnings = []
        
        # Length limit
        if len(content) > self.MAX_CONTEXT_LENGTH:
            content = content[:self.MAX_CONTEXT_LENGTH]
            warnings.append(f"Truncated to {self.MAX_CONTEXT_LENGTH} chars")
        
        # Check for injection patterns
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(f"Injection pattern detected: {pattern}")
                content = re.sub(pattern, '[REDACTED]', content, flags=re.IGNORECASE)
        
        return content, warnings
    
    def sanitize_output(self, content: str) -> str:
        """
        Sanitize content before storing to Heap.
        
        Strips low-value patterns to keep storage high-entropy.
        """
        # Strip slop patterns
        for pattern in self.SLOP_PATTERNS:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        # Normalize whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = content.strip()
        
        return content
```

---

## 4. LangGraph Integration

```python
# app/src/workflow/convening_graph.py
"""
Convening Workflow Graph - LangGraph integration.
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, List, Dict, Literal

from app.src.specialists.tribe_conductor import TribeConductor
from app.src.convening.agent_router import AgentRouter
from app.src.utils.manifest_manager import ManifestManager


class ConveningState(TypedDict):
    """Runtime state for Convening workflow."""
    # Standard LAS
    messages: List
    
    # Convening coordination
    manifest_path: str
    active_branch_id: Optional[str]
    
    # Routing
    next_action: Optional[Dict]
    
    # Fishbowl (when active)
    fishbowl_active: bool
    fishbowl_phase: Optional[str]
    fishbowl_next_speaker: Optional[str]
    fishbowl_topic: Optional[str]
    fishbowl_history: List[Dict]
    
    # Synthesis
    synthesis_pending: List[str]
    
    # Escalations
    hitl_required: List[str]
    stale_warning: List[str]


def build_convening_graph(manifest_path: str) -> StateGraph:
    """Build the Convening workflow graph."""
    
    # Initialize components
    manifest = ManifestManager(manifest_path)
    manifest.load_or_create("default", "Default Project", "trunk.md")
    conductor = TribeConductor(manifest)
    router = AgentRouter()
    
    graph = StateGraph(ConveningState)
    
    # Nodes
    graph.add_node("conductor", lambda s: conductor.execute_cycle(s))
    graph.add_node("progenitor_alpha", _create_agent_node("progenitor_alpha"))
    graph.add_node("progenitor_bravo", _create_agent_node("progenitor_bravo"))
    graph.add_node("inference_specialist", _create_agent_node("inference_specialist"))
    graph.add_node("research_specialist", _create_agent_node("research_specialist"))
    graph.add_node("local_monitor", _create_agent_node("local_monitor"))
    graph.add_node("synthesizer", _synthesis_node)
    graph.add_node("human_intervention", _human_node)
    
    # Entry
    graph.set_entry_point("conductor")
    
    # Routing
    graph.add_conditional_edges(
        "conductor",
        _route_from_conductor,
        {
            "alpha": "progenitor_alpha",
            "bravo": "progenitor_bravo",
            "inference": "inference_specialist",
            "research": "research_specialist",
            "monitor": "local_monitor",
            "synthesis": "synthesizer",
            "human": "human_intervention",
            "end": END,
        }
    )
    
    # All agents return to conductor
    for node in ["progenitor_alpha", "progenitor_bravo", 
                 "inference_specialist", "research_specialist", "local_monitor"]:
        graph.add_edge(node, "conductor")
    
    graph.add_edge("synthesizer", END)
    graph.add_edge("human_intervention", END)
    
    return graph.compile()


def _route_from_conductor(state: ConveningState) -> str:
    """Route based on conductor output."""
    
    # Fishbowl mode
    if state.get("fishbowl_active"):
        speaker = state.get("fishbowl_next_speaker")
        return "alpha" if speaker == "alpha" else "bravo"
    
    # HitL required
    if state.get("hitl_required"):
        return "human"
    
    # Synthesis pending
    if state.get("synthesis_pending"):
        return "synthesis"
    
    # Normal routing
    action = state.get("next_action", {})
    if action.get("action") == "idle":
        return "end"
    
    affinity = action.get("affinity", "default")
    
    affinity_map = {
        "architecture": "alpha",
        "implementation": "bravo",
        "inference": "inference",
        "research": "research",
        "monitoring": "monitor",
        "default": "bravo",
    }
    
    return affinity_map.get(affinity, "bravo")


def _create_agent_node(agent_id: str):
    """Factory for agent nodes."""
    def node(state: ConveningState) -> Dict:
        # Actual implementation would invoke the agent
        return {"messages": state["messages"]}
    return node


def _synthesis_node(state: ConveningState) -> Dict:
    """Synthesis node."""
    return {"synthesis_pending": []}


def _human_node(state: ConveningState) -> Dict:
    """Human intervention node."""
    return {"hitl_required": []}
```

---

## 5. The Reasonable Agent Test

Not everything needs to be agentic. Apply this test to each operation:

| Operation | Agentic? | Reasoning |
|-----------|----------|-----------|
| TribeConductor routing | **Yes** | Requires judgment about priority |
| Agent work on branch | **Yes** | Core reasoning task |
| Fishbowl debate | **Yes** | Requires argumentation |
| Manifest I/O | **No** | Deterministic file operations |
| Hash chain computation | **No** | Pure function |
| Path validation | **No** | Regex/pathlib |
| Context snippet generation | **Maybe** | Could be LLM (summary) or heuristic |

Operations marked "No" should be implemented as tool nodes or pure functions, not LLM calls.

---

## 6. Implementation Plan

### Phase 1: TribeConductor Core (Week 1)
- Implement basic routing logic
- Implement context switching (dereference/commit)
- Unit tests for routing decisions

### Phase 2: Fishbowl Integration (Week 2)
- Port existing Fishbowl logic as subroutine
- Integration with TribeConductor
- Circular argument detection

### Phase 3: AgentRouter (Week 2)
- Affinity-based routing
- Agent profile configuration
- Integration tests

### Phase 4: Semantic Firewall (Week 3)
- Input sanitization
- Output compression
- Integration with dereference/commit

### Phase 5: LangGraph Wiring (Week 3-4)
- Build full graph
- Integration with existing LAS workflow
- End-to-end testing

---

## 7. Consequences

### Positive

- **Persistent Collaboration:** Multi-session work streams
- **Heterogeneous Agents:** Right model for right task
- **Quality Control:** Fishbowl debate improves output quality
- **Forensic Trail:** All activity logged via Heap
- **Graceful Degradation:** Staleness detection, HitL escalation

### Negative

- **Complexity:** More moving parts than simple chat
- **Latency:** Context switching adds overhead
- **Coordination Cost:** Conductor is single point of throughput

### Mitigations

- **Complexity:** TribeConductor encapsulates orchestration logic
- **Latency:** Context snippets minimize load time
- **Throughput:** Conductor is lightweight; agents do heavy work

---

## 8. References

1. ADR-CORE-022: The Heap — Filesystem-Backed Cognitive Memory
2. ADR-CORE-017: Fishbowl (superseded, patterns preserved)
3. ADR-CORE-018: Checkpoints (HitL integration)
4. ADR-CORE-020: InferenceSpecialist (INFERENCE affinity)

---

*"The Convening is not a meeting—it is a sustained dialogue across time, where different minds contribute to shared understanding through structured collaboration."*
