# ADR-CORE-024: Deep Research — Focused Investigation Pattern

**Status:** Proposed
**Date:** 2025-12-03
**Context:** langgraph-agentic-scaffold (LAS)
**Layer:** Application (Workflow)
**Depends On:** ADR-CORE-022 (The Heap)
**Informed By:** ADR-CORE-023 (Convening) — integration in Phase 3
**Relates to:** ADR-CORE-018 (Checkpoints), ADR-CORE-020 (InferenceSpecialist)

---

## Abstract

This ADR establishes the pattern for **focused investigation workflows** in LAS. Unlike Convening (sustained multi-model collaboration), Deep Research is optimized for single-purpose investigations: search → browse → extract → synthesize.

Deep Research embodies the **"Dumb Tool" pattern**: primitives (WebSpecialist, BrowseSpecialist) are LLM-free API wrappers, while semantic judgment lives in InferenceSpecialist (MCP service) and the Synthesizer (full agent). This separation honors RECESS: workers don't know about each other; the ResearchOrchestrator knows about workers.

---

## 1. Context and Problem Statement

### 1.1 The Gap Between Chat and Research

Current LAS handles:
- **Chat:** Single-turn Q&A, immediate response
- **Convening:** Multi-session collaboration, persistent state

Missing:
- **Research:** Focused investigation with external data (web, documents)
- **Tool Integration:** Systematic use of search, browse, extract primitives
- **Semantic Judgment:** Pure reasoning about relevance, quality, contradiction

### 1.2 The Agentic Quantization Problem

From the Deep Research Dialectic:

> "There's a difference between a tool that performs an action and an agent that makes a judgment. Right now, LAS is missing a specialist that just... *thinks*."

The risk: forcing everything into discrete tool calls loses continuous semantic reasoning. Deep Research addresses this by:
1. **Separating execution from judgment** — WebSpecialist fetches; InferenceSpecialist judges
2. **Preserving semantic continuity** — Synthesizer has full LLM context for report generation
3. **Explicit judgment points** — InferenceSpecialist called at defined moments, not ambient

### 1.3 Relationship to Convening

| Aspect | Convening (023) | Deep Research (024) |
|--------|-----------------|---------------------|
| **Duration** | Multi-session, indefinite | Single session or short pipeline |
| **Purpose** | Sustained collaboration | Focused investigation |
| **Agent Types** | Heterogeneous pool | Specialized primitives |
| **State** | Branches with affinity | Research steps with artifacts |
| **Output** | Synthesized findings | Research report |
| **Orchestration** | TribeConductor | ResearchOrchestrator |

### 1.4 Integration Decision: Phased Approach

| Phase | Integration Level | Rationale |
|-------|------------------|-----------|
| **Phase 1** | Independent pipeline | Faster iteration, prove the primitives |
| **Phase 2** | Heap artifact storage | Persistence without Convening overhead |
| **Phase 3** | Convening subgraph | Research as branch, full forensic logging |

**Current Implementation Target:** Phase 1, with hooks for Phase 2/3.

---

## 2. Core Concepts

### 2.1 The Research Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  SEARCH  │───►│  BROWSE  │───►│ EXTRACT  │───►│SYNTHESIZE│
│          │    │          │    │          │    │          │
│ Web/Doc  │    │ Read Full│    │ Structure│    │  Report  │
│ Discovery│    │ Content  │    │   Data   │    │ Generate │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
      │               │               │               │
      ▼               ▼               ▼               ▼
   [Tool]          [Tool]         [Hybrid]       [Agent]
      │               │               │               │
      └───────────────┴───────────────┴───────────────┘
                              │
                    ┌─────────▼─────────┐
                    │ InferenceSpecialist│
                    │   (MCP Service)    │
                    │  Semantic Judgment │
                    └───────────────────┘
```

### 2.2 The "Dumb Tool" Pattern

From the Deep Research Falsification:

> WebSpecialist should be a "dumb tool" — no LLM, just API calls. The judgment happens elsewhere.

This pattern prevents the **God Object antipattern** where specialists embed orchestration logic.

| Component | Type | Responsibility | Has LLM? |
|-----------|------|----------------|----------|
| **WebSpecialist** | Tool Node | Execute search API, return results | No |
| **BrowseSpecialist** | Tool Node | Fetch page content, parse HTML | No |
| **DataExtractor** | Hybrid | LLM for extraction, tool for storage | Yes (extraction) |
| **Synthesizer** | Agent | Full LLM reasoning for report | Yes |
| **InferenceSpecialist** | MCP Service | Semantic judgment (relevance, quality) | Yes (minimal prompt) |
| **ResearchOrchestrator** | Controller | Pipeline coordination, HitL checkpoints | No |

### 2.3 InferenceSpecialist: Pure Semantic Judgment

InferenceSpecialist addresses the Agentic Quantization Problem by providing **pure reasoning without tools**:

```python
class InferenceSpecialist:
    """
    MCP Service for semantic judgment.

    No tools, no state mutation — just reasoning.
    Callable from any point in any workflow.
    """

    async def judge_relevance(
        self,
        query: str,
        content: str
    ) -> RelevanceJudgment:
        """Is this content relevant to the query?"""
        # Minimal prompt, focused judgment
        pass

    async def detect_contradiction(
        self,
        claim_a: str,
        claim_b: str
    ) -> ContradictionAnalysis:
        """Do these claims contradict each other?"""
        pass

    async def assess_source_quality(
        self,
        url: str,
        content: str
    ) -> QualityAssessment:
        """How reliable is this source?"""
        pass
```

**Why MCP Service, not Graph Node:**
- Callable from any specialist, any workflow
- No routing overhead for simple judgment calls
- Synchronous call semantics (judgment doesn't fork)
- Reusable across Deep Research, Convening, and future workflows

### 2.4 Research-Specific Metadata

When using the Heap (Phase 2+), Deep Research uses the `research.*` namespace:

```python
metadata = {
    "research.query": "CRM comparison startups 2025",
    "research.clarified_query": "Compare HubSpot, Salesforce, Pipedrive for <50 employee startups",
    "research.sources": ["hubspot.com", "salesforce.com", "g2crowd.com"],
    "research.results_count": 15,
    "research.pages_browsed": 5,
    "research.extraction_schema": "pricing_comparison",
    "research.contradictions_detected": 2,
    "research.hitl_pauses": 1,
}
```

---

## 3. Resolved Questions

### 3.1 Architecture Questions — Resolved

**Q1: Should research findings persist to HEAP between sessions?**

**A:** Phase-dependent:
- **Phase 1:** No. In-memory artifacts, discarded after synthesis. Proves the pipeline.
- **Phase 2:** Yes. `ManifestManager` stores artifacts. Research is recoverable/resumable.
- **Phase 3:** Yes, as branches. `BranchPointer` with `affinity=RESEARCH`.

**Q2: Should search result branches use Convening's `BranchPointer` structure?**

**A:** In Phase 3, yes. Research becomes a branch type:
```python
class AgentAffinity(Enum):
    GENERAL = "general"
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    RESEARCH = "research"  # Added for Deep Research
```

Benefits: Consistency, forensic logging, hash chaining, conflict tracking.

**Q3: How should contradictory findings be tracked?**

**A:** Use Convening's `Conflict` pattern (reuse, don't reinvent):
```python
@dataclass
class ResearchConflict:
    """Contradiction between research sources."""
    source_a: str          # URL or document reference
    source_b: str
    claim_a: str
    claim_b: str
    detected_by: str       # "inference_specialist"
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None  # "synthesizer" or "hitl"
```

In Phase 1, tracked in `ResearchState.contradictions`. In Phase 3, promoted to `Conflict` records in Heap.

### 3.2 Implementation Questions — Resolved

**Q4: Where does InferenceSpecialist live?**

**A:** MCP Service (Option A).

Rationale:
- Callable from any specialist without routing overhead
- Synchronous call semantics for judgment
- No state mutation (pure function)
- Reusable across workflows

```python
# Registration
mcp_registry.register("inference", InferenceSpecialist())

# Invocation from any specialist
relevance = await mcp_client.call(
    service="inference",
    method="judge_relevance",
    params={"query": query, "content": page_content}
)
```

**Q5: How does HitL clarification integrate?**

**A:** Via `clarification_required` status and ADR-CORE-018 checkpointing.

From the HitL Integration document:
```python
class StepResult(BaseModel):
    """Result from any research pipeline step."""
    status: Literal["success", "failed", "clarification_required"]
    data: Optional[dict] = None
    clarification_question: Optional[str] = None
    clarification_context: Optional[dict] = None
    checkpoint_id: Optional[str] = None  # For resumption

class ResearchState(TypedDict):
    # ... other fields ...
    hitl_status: Literal["running", "paused", "complete"]
    pending_clarification: Optional[StepResult]
```

**When clarification triggers:**
1. Ambiguous query (InferenceSpecialist can't determine intent)
2. Contradictory sources (resolution requires human judgment)
3. Low-confidence extraction (schema mismatch)
4. Source quality concerns (all sources low-quality)

**Mechanism:**
```python
if step_result.status == "clarification_required":
    # Create checkpoint (ADR-CORE-018)
    checkpoint_id = await checkpoint_manager.save(state)

    # Pause graph execution
    state["hitl_status"] = "paused"
    state["pending_clarification"] = step_result

    # Graph yields control to human
    return Command(goto="hitl_wait", update=state)
```

**Q6: What is the artifact format for research output?**

**A:** Both structured JSON and Markdown presentation.

```python
class ResearchOutput(BaseModel):
    """Final research output."""

    # Structured data (for programmatic use)
    query: str
    clarified_query: Optional[str]
    sources: List[SourceReference]
    extracted_data: List[dict]
    contradictions: List[ResearchConflict]

    # Presentation (for human consumption)
    report_markdown: str

    # Metadata
    duration_seconds: float
    hitl_pauses: int
    confidence_score: float
```

### 3.3 Integration Questions — Resolved

**Q7: Should Deep Research be invokable from Convening?**

**A:** Yes, in Phase 3, as a **Fishbowl-style subroutine**.

From ADR-CORE-023, Fishbowl is a synchronous debate. Deep Research can follow the same pattern:
```python
# From TribeConductor
async def invoke_research(self, query: str, branch_id: str) -> ResearchOutput:
    """Spawn Deep Research as subroutine, await result."""

    # Create research subgraph
    research_graph = build_research_graph()

    # Execute synchronously (blocks Convening branch)
    result = await research_graph.ainvoke({
        "query": query,
        "parent_branch_id": branch_id,
    })

    # Result flows back to Convening
    return result["output"]
```

**Q8: Should research results feed back into Convening branches?**

**A:** Yes, as committed artifacts.

```python
# After research completes
manifest.log_contribution(
    branch_id=branch_id,
    agent_id="deep_research",
    agent_model="pipeline",
    summary=f"Research: {query}",
    content=research_output.report_markdown,
    metadata={
        "research.sources": [s.url for s in research_output.sources],
        "research.confidence": research_output.confidence_score,
    }
)
```

---

## 4. Component Specifications

### 4.1 ResearchState

```python
class ResearchState(TypedDict):
    """State for Deep Research workflow."""

    # Query
    query: str
    clarified_query: Optional[str]

    # Pipeline progress
    phase: Literal["clarify", "search", "browse", "extract", "synthesize", "complete"]

    # Artifacts (in-memory Phase 1, Heap-backed Phase 2+)
    search_results: List[SearchResult]    # Raw search hits
    browsed_pages: List[PageContent]      # Fetched content
    extracted_data: List[ExtractedRecord] # Structured findings

    # Judgment
    relevance_scores: Dict[str, float]    # URL -> relevance score
    contradictions: List[ResearchConflict]

    # Synthesis
    report: Optional[ResearchOutput]

    # Control
    hitl_status: Literal["running", "paused", "complete"]
    pending_clarification: Optional[StepResult]

    # Metadata (for forensics)
    started_at: datetime
    checkpoint_ids: List[str]
```

### 4.2 WebSpecialist (Tool Node)

```python
class WebSpecialist:
    """
    Dumb tool for web search.

    No LLM — just API calls and result formatting.
    Judgment happens in InferenceSpecialist or Synthesizer.

    RECESS: This specialist knows nothing about the pipeline.
    It receives a query, returns results. Period.
    """

    def __init__(self, search_provider: SearchProvider):
        self.provider = search_provider  # Brave, SerpAPI, etc.

    async def search(
        self,
        query: str,
        num_results: int = 10
    ) -> List[SearchResult]:
        """Execute search and return raw results."""
        raw = await self.provider.search(query, num_results)
        return [
            SearchResult(
                url=r["url"],
                title=r["title"],
                snippet=r["snippet"],
                rank=i,
            )
            for i, r in enumerate(raw)
        ]
```

### 4.3 BrowseSpecialist (Tool Node)

```python
class BrowseSpecialist:
    """
    Dumb tool for page fetching.

    No LLM — HTTP fetch, HTML parsing, content extraction.
    Does NOT judge relevance or quality.
    """

    async def browse(self, url: str) -> PageContent:
        """Fetch and parse page content."""
        response = await self.http_client.get(url)

        # Parse HTML, extract main content
        soup = BeautifulSoup(response.text, "html.parser")
        main_content = self._extract_main_content(soup)

        return PageContent(
            url=url,
            title=soup.title.string if soup.title else "",
            content=main_content,
            fetched_at=datetime.utcnow(),
            status_code=response.status_code,
        )
```

### 4.4 DataExtractor (Hybrid)

```python
class DataExtractor:
    """
    Hybrid: LLM for extraction, structured output.

    Uses LLM to extract structured data from unstructured content.
    Schema can be inferred from query or provided explicitly.
    """

    async def extract(
        self,
        pages: List[PageContent],
        schema: Optional[Type[BaseModel]] = None,
        query: str = "",
    ) -> List[ExtractedRecord]:
        """Extract structured data from pages."""

        if schema is None:
            # Infer schema from query
            schema = await self._infer_schema(query)

        records = []
        for page in pages:
            # LLM extraction with structured output
            extracted = await self.llm.extract(
                content=page.content,
                schema=schema,
                context=f"Extracting data relevant to: {query}",
            )
            records.append(ExtractedRecord(
                source_url=page.url,
                data=extracted,
                extracted_at=datetime.utcnow(),
            ))

        return records
```

### 4.5 Synthesizer (Full Agent)

```python
class Synthesizer:
    """
    Full LLM agent for report synthesis.

    Has full context: query, sources, extracted data, contradictions.
    Produces final research report.
    """

    async def synthesize(
        self,
        query: str,
        extracted_data: List[ExtractedRecord],
        contradictions: List[ResearchConflict],
    ) -> ResearchOutput:
        """Generate research report from extracted data."""

        # Resolve contradictions where possible
        resolved_contradictions = await self._resolve_contradictions(
            contradictions
        )

        # Generate report
        report_markdown = await self.llm.generate(
            template=SYNTHESIS_TEMPLATE,
            context={
                "query": query,
                "data": extracted_data,
                "contradictions": resolved_contradictions,
            },
        )

        return ResearchOutput(
            query=query,
            sources=[...],
            extracted_data=[r.data for r in extracted_data],
            contradictions=resolved_contradictions,
            report_markdown=report_markdown,
            confidence_score=self._calculate_confidence(extracted_data),
        )
```

### 4.6 ResearchOrchestrator (Controller)

```python
class ResearchOrchestrator:
    """
    Lightweight orchestrator for research pipeline.

    Unlike TribeConductor, this is single-purpose.
    Follows RECESS: knows about workers, workers don't know about each other.

    Responsibilities:
    - Pipeline coordination
    - HitL checkpoint management
    - Artifact storage (Phase 2+)
    - InferenceSpecialist invocation at judgment points
    """

    def __init__(
        self,
        web_specialist: WebSpecialist,
        browse_specialist: BrowseSpecialist,
        data_extractor: DataExtractor,
        synthesizer: Synthesizer,
        inference_client: McpClient,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ):
        self.web = web_specialist
        self.browse = browse_specialist
        self.extractor = data_extractor
        self.synthesizer = synthesizer
        self.inference = inference_client
        self.checkpoints = checkpoint_manager

    async def execute_research(
        self,
        query: str,
        hitl_callback: Optional[Callable] = None,
    ) -> ResearchOutput:
        """Run full research pipeline, return report."""

        state = ResearchState(
            query=query,
            phase="clarify",
            hitl_status="running",
            started_at=datetime.utcnow(),
            # ... initialize other fields
        )

        # 1. Clarify query (optional InferenceSpecialist call)
        clarify_result = await self._clarify_query(state, hitl_callback)
        if clarify_result.status == "clarification_required":
            return await self._pause_for_hitl(state, clarify_result)

        state["clarified_query"] = clarify_result.data["clarified_query"]
        state["phase"] = "search"

        # 2. Search (tool node)
        search_query = state["clarified_query"] or state["query"]
        state["search_results"] = await self.web.search(search_query)
        state["phase"] = "browse"

        # 3. Judge relevance (InferenceSpecialist)
        for result in state["search_results"]:
            relevance = await self.inference.call(
                service="inference",
                method="judge_relevance",
                params={"query": search_query, "content": result.snippet},
            )
            state["relevance_scores"][result.url] = relevance.score

        # 4. Browse top relevant results (tool node)
        top_urls = self._select_top_relevant(state, limit=5)
        state["browsed_pages"] = [
            await self.browse.browse(url) for url in top_urls
        ]
        state["phase"] = "extract"

        # 5. Extract structured data (hybrid)
        state["extracted_data"] = await self.extractor.extract(
            pages=state["browsed_pages"],
            query=search_query,
        )

        # 6. Detect contradictions (InferenceSpecialist)
        state["contradictions"] = await self._detect_contradictions(state)

        if state["contradictions"] and self._needs_human_resolution(state):
            return await self._pause_for_hitl(state, StepResult(
                status="clarification_required",
                clarification_question="Contradictory sources found. Which should be trusted?",
                clarification_context={"contradictions": state["contradictions"]},
            ))

        state["phase"] = "synthesize"

        # 7. Synthesize report (full LLM)
        state["report"] = await self.synthesizer.synthesize(
            query=search_query,
            extracted_data=state["extracted_data"],
            contradictions=state["contradictions"],
        )

        state["phase"] = "complete"
        state["hitl_status"] = "complete"

        return state["report"]
```

---

## 5. Heap Integration (Phase 2+)

### 5.1 Phase 1: No Heap

```python
# In-memory only, artifacts discarded after report generation
state = ResearchState(...)
report = await orchestrator.execute_research(query)
# state is garbage collected
```

### 5.2 Phase 2: Lightweight Heap Integration

```python
# Research artifacts stored, no full branch structure
async def execute_research_with_heap(
    self,
    query: str,
    manifest: ManifestManager,
) -> ResearchOutput:
    """Research with artifact persistence."""

    # Create ad-hoc branch for research
    branch_id = f"research-{uuid4().hex[:8]}"

    # ... execute pipeline ...

    # Log artifacts
    for page in state["browsed_pages"]:
        manifest.log_contribution(
            branch_id=branch_id,
            agent_id="browse_specialist",
            agent_model="tool",
            summary=f"Fetched: {page.url}",
            content=page.content,
        )

    # Log final report
    manifest.log_contribution(
        branch_id=branch_id,
        agent_id="synthesizer",
        agent_model=self.synthesizer.model_id,
        summary=f"Research report: {query}",
        content=state["report"].report_markdown,
        metadata={"research.confidence": state["report"].confidence_score},
    )

    return state["report"]
```

### 5.3 Phase 3: Full Convening Integration

```python
# Research as a proper branch with BranchPointer
async def execute_research_as_branch(
    self,
    query: str,
    manifest: ManifestManager,
    parent_branch_id: Optional[str] = None,
) -> ResearchOutput:
    """Research as Convening branch."""

    # Create branch with RESEARCH affinity
    branch = BranchPointer(
        branch_id=f"research-{uuid4().hex[:8]}",
        title=f"Research: {query}",
        filepath=f"branches/research-{...}.md",
        context_snippet=query,
        status=BranchStatus.ACTIVE,
        phase=BranchPhase.DEVELOPMENT,
        affinity=AgentAffinity.RESEARCH,
        parent_branch_id=parent_branch_id,
        metadata={
            "research.query": query,
            "research.phase": "clarify",
        },
    )

    manifest.add_branch(branch)

    # ... execute pipeline, logging contributions ...

    # Update branch status on completion
    manifest.update_branch(
        branch_id=branch.branch_id,
        updates={
            "status": BranchStatus.RESOLVED,
            "metadata.research.phase": "complete",
            "metadata.research.confidence": state["report"].confidence_score,
        },
    )

    return state["report"]
```

---

## 6. HitL Integration

### 6.1 Clarification Required Pattern

```python
async def _pause_for_hitl(
    self,
    state: ResearchState,
    step_result: StepResult,
) -> ResearchOutput:
    """Pause pipeline for human clarification."""

    # Create checkpoint (ADR-CORE-018)
    if self.checkpoints:
        checkpoint_id = await self.checkpoints.save(state)
        step_result.checkpoint_id = checkpoint_id
        state["checkpoint_ids"].append(checkpoint_id)

    state["hitl_status"] = "paused"
    state["pending_clarification"] = step_result

    # Return partial result indicating pause
    return ResearchOutput(
        query=state["query"],
        sources=[],
        extracted_data=[],
        contradictions=[],
        report_markdown="",
        confidence_score=0.0,
        hitl_paused=True,
        pending_clarification=step_result,
    )

async def resume_research(
    self,
    checkpoint_id: str,
    clarification_response: str,
) -> ResearchOutput:
    """Resume paused research with human clarification."""

    # Restore state from checkpoint
    state = await self.checkpoints.load(checkpoint_id)

    # Apply clarification
    state["clarified_query"] = clarification_response
    state["hitl_status"] = "running"
    state["pending_clarification"] = None

    # Continue from where we left off
    return await self._continue_from_phase(state)
```

### 6.2 Clarification Triggers

| Trigger | Detection | Question Template |
|---------|-----------|-------------------|
| Ambiguous query | InferenceSpecialist confidence < 0.6 | "Did you mean X or Y?" |
| No relevant results | All relevance scores < 0.3 | "No results found. Rephrase query?" |
| Contradictory sources | 2+ sources disagree on key fact | "Sources disagree on X. Which to trust?" |
| Low-quality sources | All sources score < 0.5 on quality | "Only low-quality sources found. Proceed anyway?" |
| Schema mismatch | Extraction fails on >50% of pages | "Can't extract expected data. Adjust expectations?" |

---

## 7. Implementation Plan

### Phase 1: Standalone Pipeline (MVP)

**Goal:** Prove the primitives work.

1. Implement `WebSpecialist` with one search provider (Brave or SerpAPI)
2. Implement `BrowseSpecialist` with basic HTML parsing
3. Implement `DataExtractor` with schema inference
4. Implement `Synthesizer` with simple report template
5. Wire together in `ResearchOrchestrator`
6. In-memory state only, no Heap

**Success Criteria:**
- Can execute query → report pipeline
- Returns structured + markdown output
- Handles basic error cases

### Phase 2: Add InferenceSpecialist + HitL

**Goal:** Add judgment and human control.

1. Implement `InferenceSpecialist` as MCP service
2. Add relevance scoring at search result stage
3. Add contradiction detection at extraction stage
4. Implement `clarification_required` status
5. Add checkpoint save/restore (ADR-CORE-018)

**Success Criteria:**
- InferenceSpecialist callable from pipeline
- HitL pauses work, can resume
- Contradictions detected and logged

### Phase 3: Heap Integration

**Goal:** Persistent, auditable research.

1. Add artifact logging via `ManifestManager`
2. Add `research.*` metadata namespace
3. Create research-specific branch type

**Success Criteria:**
- Research artifacts persist to filesystem
- Can audit research trail
- Can resume interrupted research

### Phase 4: Convening Integration

**Goal:** Research as collaboration primitive.

1. Add `AgentAffinity.RESEARCH`
2. Implement research as Fishbowl-style subroutine
3. Allow Convening to spawn research branches
4. Research findings flow back to parent branch

**Success Criteria:**
- TribeConductor can invoke research
- Research results appear in Convening branches
- Full forensic trail with hash chaining

---

## 8. Testing Strategy

### Unit Tests

```python
# Test dumb tools return raw data
async def test_web_specialist_returns_raw_results():
    specialist = WebSpecialist(MockSearchProvider())
    results = await specialist.search("test query")
    assert all(isinstance(r, SearchResult) for r in results)
    assert len(results) <= 10

# Test orchestrator coordinates correctly
async def test_orchestrator_pipeline_order():
    orchestrator = ResearchOrchestrator(...)
    with patch.object(orchestrator.web, 'search') as mock_search:
        await orchestrator.execute_research("test")
        mock_search.assert_called_once()
```

### Integration Tests

```python
@pytest.mark.integration
async def test_full_research_pipeline():
    """End-to-end test with real search API."""
    orchestrator = ResearchOrchestrator(
        web_specialist=WebSpecialist(BraveSearchProvider()),
        browse_specialist=BrowseSpecialist(),
        data_extractor=DataExtractor(),
        synthesizer=Synthesizer(),
        inference_client=McpClient(),
    )

    result = await orchestrator.execute_research(
        "Compare Python web frameworks 2025"
    )

    assert result.report_markdown
    assert len(result.sources) > 0
    assert result.confidence_score > 0.5
```

### HitL Tests

```python
async def test_hitl_pause_and_resume():
    """Test clarification workflow."""
    orchestrator = ResearchOrchestrator(...)

    # Force ambiguous query
    result = await orchestrator.execute_research("compare things")

    assert result.hitl_paused
    assert result.pending_clarification.status == "clarification_required"

    # Resume with clarification
    resumed = await orchestrator.resume_research(
        checkpoint_id=result.pending_clarification.checkpoint_id,
        clarification_response="Compare Python and JavaScript",
    )

    assert not resumed.hitl_paused
    assert resumed.report_markdown
```

---

## 9. Security Considerations

### Input Validation

- Sanitize search queries before API calls
- Validate URLs before browsing (no file://, no internal IPs)
- Rate limit search/browse calls per session

### Content Handling

- Sandbox HTML parsing (BeautifulSoup, not eval)
- Limit page content size (prevent memory exhaustion)
- Strip scripts and potentially dangerous content

### LLM Safety

- InferenceSpecialist has minimal prompt surface
- Synthesizer prompt includes injection guards
- All extracted data validated against schema

---

## 10. Metrics

### Pipeline Metrics

| Metric | Description |
|--------|-------------|
| `research.query_count` | Total queries processed |
| `research.avg_duration_seconds` | Average pipeline duration |
| `research.sources_per_query` | Average sources browsed |
| `research.hitl_pause_rate` | Fraction requiring clarification |
| `research.contradiction_rate` | Fraction with detected contradictions |

### Quality Metrics

| Metric | Description |
|--------|-------------|
| `research.avg_confidence` | Average report confidence score |
| `research.avg_relevance` | Average source relevance score |
| `research.extraction_success_rate` | Fraction of successful extractions |

---

## 11. References

1. **ADR-CORE-022:** The Heap — Persistence infrastructure
2. **ADR-CORE-023:** Convening of the Tribes — Multi-model orchestration
3. **ADR-CORE-018:** Checkpoints — HitL integration
4. **ADR-CORE-020:** InferenceSpecialist — Semantic judgment
5. **Deep Research Dialectic** — Design refinement with Gemini
6. **Deep Research Falsification** — Devil's advocate challenges
7. **Deep Research HitL Integration** — Clarification pattern
8. **Cathedral and Codex** — Vision for cognitive partnership

---

*"Deep Research is Convening's focused sibling—where Convening sustains dialogue across time, Deep Research pursues a single question to its conclusion. Together, they form the Cathedral's investigative capacity."*
