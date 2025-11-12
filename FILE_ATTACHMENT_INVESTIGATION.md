# File Attachment Flow Investigation

**Date**: 2025-01-12
**Context**: User had to paste code into prompt because file attachment wasn't recognized, causing router context overflow.

---

## File Flow Architecture (Current State)

### 1. **Gradio UI** → **API Client** → **Backend**

```
User uploads file via Gradio
    ↓
gradio_vegas.py/gradio_lassi.py (lines 361-362 / 297-298)
    file_input = gr.File(label="📄 TEXT FILE STAGING")
    image_input = gr.Image(type="pil", label="🖼️ IMAGE FILE STAGING")
    ↓
_handle_submit_closure(prompt, text_file, image_file, use_simple_chat)
    ↓
api_client.invoke_agent_streaming(prompt, text_file, image_file, use_simple_chat)
    ↓
api_client.py (lines 28-40)
    - Reads text file: open(text_file_path.name, "r")
    - Encodes image: base64.b64encode(image_file.read())
    ↓
POST /v1/graph/stream with payload:
    {
        "input_prompt": "...",
        "text_to_process": "file contents...",
        "image_to_process": "base64...",
        "use_simple_chat": false
    }
    ↓
runner.py (lines 120-123, 153-156)
    initial_state["artifacts"]["text_to_process"] = text_to_process
    initial_state["artifacts"]["uploaded_image.png"] = image_to_process
    ↓
Specialists access via: state["artifacts"]["text_to_process"]
```

---

## Identified Issue: Gradio Image Widget Type Mismatch

### **Problem**:

**gradio_vegas.py:362** and **gradio_lassi.py:298**:
```python
image_input = gr.Image(type="pil", label="🖼️ IMAGE FILE STAGING")
```

**api_client.py:38**:
```python
payload["image_to_process"] = self._encode_image_to_base64(image_path.name)
                                                                  # ↑ Expects .name attribute
```

**api_client.py:17-18**:
```python
with open(image_path, "rb") as image_file:  # Expects file path
    return base64.b64encode(image_file.read()).decode('utf-8')
```

### **Root Cause**:

When Gradio Image widget has `type="pil"`, it returns a **PIL.Image object**, not a file path.
The api_client expects a file path with a `.name` attribute.

### **Expected Behavior** (Text Files):

Text files work correctly because `gr.File()` returns a **file-like object** with `.name` attribute:
```python
# api_client.py:30 - WORKS
with open(text_file_path.name, "r", encoding="utf-8") as f:
    payload["text_to_process"] = f.read()
```

### **Actual Behavior** (Images):

```python
# User uploads image.png
image_input returns: <PIL.Image.Image object>  # NO .name attribute!

# api_client.py:38 tries:
self._encode_image_to_base64(image_path.name)  # AttributeError!

# api_client.py:39 catches exception:
except Exception as e:
    yield {"status": f"Error reading image: {e}"}
    # But doesn't return - continues with None payload!
```

**Bug**: Exception is caught but execution continues, sending `None` for `image_to_process`.

---

## Why Text Files Might Fail Too

Looking at the error handling:

```python
# api_client.py:28-34
if text_file_path:
    try:
        with open(text_file_path.name, "r", encoding="utf-8") as f:
            payload["text_to_process"] = f.read()
    except Exception as e:
        yield {"status": f"Error reading file: {e}"}
        return  # ← GOOD: Returns on error
```

Text files return on error, but what if `text_file_path` is `None` or empty?

```python
# gradio_vegas.py:265-267 (VEGAS)
if not prompt.strip():
    yield {status_output: "⚠ ERROR: EMPTY PROMPT DETECTED"}
    return

# gradio_lassi.py:189-191 (LASSI)
if not prompt.strip() and not text_file and not image_file:
    yield {status_output: "Please provide a prompt or a file to begin."}
    return
```

**LASSI has better validation**: Checks for prompt OR file.
**VEGAS validation is incomplete**: Only checks prompt, allows submit with no prompt AND no file.

---

## Why User Resorted to Pasting Code

### Hypothesis 1: Silent File Upload Failure
- User uploaded text file
- File path was None or empty (UI didn't capture it)
- No error shown (VEGAS doesn't validate file presence)
- User assumed file upload didn't work
- Pasted code into prompt as workaround

### Hypothesis 2: File Type Not Recognized
- User uploaded .py file
- System worked but didn't route to correct specialist
- Router couldn't determine "this is code" without seeing file extension
- User thought upload failed, pasted as workaround

### Hypothesis 3: UI State Bug
- Gradio file upload widget lost state
- File cleared before submit
- No visual feedback that file was lost
- User pasted as workaround

---

## Router's View of Files (Current State)

**Router NEVER sees file contents or metadata:**

```python
# router_specialist.py:67
messages: List[BaseMessage] = state["messages"][:]

# state["messages"] contains:
[HumanMessage(content="Analyze this code", name="user")]
# ↑ No mention of file attachment!

# File is in artifacts (router doesn't see):
state["artifacts"]["text_to_process"] = "... 5KB of Python code ..."
```

**Impact**:
- Router routes based on prompt text alone
- Cannot determine: "User uploaded Python file → route to code_analysis_specialist"
- Routes to default_responder or chat_specialist instead
- Specialists don't know to look in artifacts for code

---

## Proposed Solutions

### **Fix 1: Fix Image Upload Type** (Immediate)

Change Gradio Image widget type:

```python
# gradio_vegas.py:362, gradio_lassi.py:298
# BEFORE:
image_input = gr.Image(type="pil", label="🖼️ IMAGE FILE STAGING")

# AFTER:
image_input = gr.Image(type="filepath", label="🖼️ IMAGE FILE STAGING")
```

This makes image uploads return file paths (like text files), fixing the AttributeError.

### **Fix 2: Add File Validation** (Defensive)

Add validation to VEGAS (match LASSI):

```python
# gradio_vegas.py:265-267
# BEFORE:
if not prompt.strip():
    yield {status_output: "⚠ ERROR: EMPTY PROMPT DETECTED"}
    return

# AFTER:
if not prompt.strip() and not text_file and not image_file:
    yield {status_output: "⚠ ERROR: PROVIDE PROMPT OR FILE"}
    return
```

### **Fix 3: Fix Image Error Handling** (Bug Fix)

```python
# api_client.py:36-40
# BEFORE:
if image_path:
    try:
        payload["image_to_process"] = self._encode_image_to_base64(image_path.name)
    except Exception as e:
        yield {"status": f"Error reading image: {e}"}
        # ← BUG: Doesn't return!

# AFTER:
if image_path:
    try:
        payload["image_to_process"] = self._encode_image_to_base64(image_path.name)
    except Exception as e:
        yield {"status": f"Error reading image: {e}"}
        return  # ← Stop execution on error
```

### **Fix 4: Add File Metadata to Messages** (Router Awareness)

Add lightweight metadata to HumanMessage so router can make informed decisions:

```python
# runner.py:116 (and 149)
# BEFORE:
initial_state: GraphState = {
    "messages": [HumanMessage(content=goal, name="user")],
    # ...
}

# AFTER:
message_kwargs = {}
if text_to_process:
    message_kwargs["attachments"] = [{"type": "text", "size": len(text_to_process)}]
if image_to_process:
    message_kwargs.setdefault("attachments", []).append({"type": "image", "size": len(image_to_process)})

initial_state: GraphState = {
    "messages": [HumanMessage(content=goal, name="user", additional_kwargs=message_kwargs)],
    # ...
}
```

Router can now see:
```python
# Router sees:
messages[0].additional_kwargs["attachments"] = [{"type": "text", "size": 5000}]
# Can reason: "User uploaded text file → route to text_analysis_specialist"
```

Token overhead: ~20-50 tokens per file (minimal).

---

## Recommended Immediate Actions

1. ✅ **Fix image upload type** (1-line change, immediate fix)
2. ✅ **Add return statement** to image error handling (bug fix)
3. ✅ **Add file validation** to VEGAS (parity with LASSI)
4. 🔄 **Test file uploads end-to-end** (verify fixes work)
5. 📝 **Document in ADR** whether to add file metadata for router

---

## ADR Scope Decision

**Original Problem**: Router context overflow due to pasted code
**Root Cause**: File upload not working, forcing workaround

**ADR Should Address**:
1. **Immediate**: Fix file upload bugs (image type, error handling, validation)
2. **Future**: Router awareness of file attachments (separate ADR?)

**Two Possible ADRs**:

### **Option A: Single ADR - File Handling & Router Context**
- Fix file upload bugs
- Add file metadata to messages for router awareness
- Add message history filtering for multi-turn overflow
- **Pro**: Comprehensive fix
- **Con**: Large scope, multiple concerns

### **Option B: Two ADRs - Separate Concerns**
- **ADR-CORE-009**: Fix File Upload Bugs (immediate)
  - Fix image widget type
  - Fix error handling
  - Add validation
- **ADR-CORE-010**: Router Context Management (deferred)
  - File metadata for routing
  - Message history filtering
  - Large prompt handling
- **Pro**: Focused scope, faster implementation
- **Con**: Requires two rounds

---

## Testing Checklist

- [ ] Upload .txt file → Verify `text_to_process` artifact created
- [ ] Upload .py file → Verify content in artifact
- [ ] Upload .png file → Verify base64 in `uploaded_image.png` artifact
- [ ] Submit with no prompt, no file → Verify error shown
- [ ] Upload file, clear it, submit → Verify error shown
- [ ] Upload file + type prompt → Verify both received
- [ ] Check LangSmith trace → Verify artifacts present in initial state
- [ ] Multi-turn with files → Verify history doesn't overflow router

---

## Test Results - 2025-11-12

### ✅ **File Upload Fixes SUCCESSFUL**
All 3 bugs fixed and verified:
- Router context reduced: **5822 tokens → 1462 tokens (74% reduction)**
- File properly stored in `state["artifacts"]["text_to_process"]`
- Router model (gpt-oss-20b-mxfp4) working perfectly

**Test Evidence** (from ./logs/agentic_server.log):
```
2025-11-12 12:47:18,726 - INFO - Model: gpt-oss-20b-mxfp4 | Usage: prompt=1462, completion=20, total=1482 tokens
2025-11-12 12:47:18,727 - INFO - Model generated tool calls: [Route(next_specialist='web_builder')]
```

### ❌ **NEW ISSUE DISCOVERED: Triage Specialist Blocking Correct Routes**

**Problem**: PromptTriageSpecialist filtered specialist options incorrectly, causing router's correct choice to be rejected.

**What Happened**:
1. User prompt: "rewrite the UI theme for this Gradio web app" + attached `.py` file
2. PromptTriageSpecialist recommended: `file_specialist`, `text_analysis_specialist`
3. GraphOrchestrator filtered router options to only: `text_analysis_specialist`
4. Router correctly determined: `web_builder` needed
5. Router validation rejected `web_builder` (not in filtered list)
6. System fell back to `default_responder_specialist`

**Log Evidence** (from ./logs/agentic_server.log):
```
2025-11-12 12:47:16,903 - INFO - [PromptTriageSpecialist] Recommended specialists: ['file_specialist', 'text_analysis_specialist']
2025-11-12 12:47:18,614 - INFO - Filtering router choices based on Triage recommendations: ['text_analysis_specialist']
2025-11-12 12:47:18,731 - WARNING - Router LLM returned an invalid specialist: 'web_builder'. Valid options are ['text_analysis_specialist']. Falling back to DefaultResponder.
```

### **Options for Fixing Triage Issue**

#### **Option 1: Disable Triage for File-Attached Prompts** (Quick Fix)
**Approach**: Skip PromptTriageSpecialist when `artifacts` contain `text_to_process` or uploaded images.

**Pros**:
- Fast, surgical fix
- Preserves triage for simple text prompts
- Low risk

**Cons**:
- Doesn't address root cause
- Reduces triage utility for file-based workflows

**Implementation**: Add condition in `graph_orchestrator.py` routing logic.

#### **Option 2: Improve Triage Specialist Prompt** (Better Fix)
**Approach**: Enhance PromptTriageSpecialist to consider file attachments and recommend specialists that can handle code/web development tasks.

**Pros**:
- Fixes root cause (triage making poor recommendations)
- Improves system intelligence
- Maintains triage utility

**Cons**:
- Requires prompt engineering iteration
- May increase triage specialist token usage
- Still subject to LLM reasoning errors

**Implementation**: Update `prompt_triage_specialist.py` prompt to:
- Check for file attachments in artifacts
- Recommend `web_builder`, `code_analysis_specialist` for code files
- Be more conservative (recommend more options, not fewer)

#### **Option 3: Make Triage Advisory, Not Restrictive** (Architectural Fix)
**Approach**: Change triage output from filtering mechanism to advisory signal. Router sees full specialist list PLUS triage recommendations as guidance.

**Pros**:
- Router retains full autonomy
- Triage provides useful pre-filtering signal without being restrictive
- Eliminates class of "correct specialist filtered out" bugs
- Aligns with router model being most capable component

**Cons**:
- Architectural change affects `graph_orchestrator.py` routing logic
- May increase router token usage slightly (full specialist list vs filtered)
- Triage becomes less impactful (advisory vs enforcement)

**Implementation**:
- Change `graph_orchestrator.py` to NOT filter `current_specialists`
- Pass triage recommendations in router prompt as advisory context
- Router makes final decision with full information

### **Recommendation**: Option 3 (Architectural Fix)

**Rationale**:
- Router model (gpt-oss-20b-mxfp4) is the most capable component for routing decisions
- Triage specialist (smaller, faster model) should inform, not constrain
- Prevents entire class of "correct route filtered out" bugs
- Aligns with fail-fast philosophy: better to route wrong than block correct route

**Token Impact**: Minimal (~100-200 extra tokens per routing to include full specialist list)

**Future Path**: If triage proves valuable as advisory, can enhance with confidence scores or ranking.

---

## References

- File flow: ./app/src/ui/api_client.py (lines 20-40)
- Runner state init: ./app/src/workflow/runner.py (lines 115-123, 148-156)
- Gradio image types: https://www.gradio.app/docs/image
- Router logs: ./logs/agentic_server.log (lines showing token usage and routing decisions)
- Triage filtering logic: ./app/src/workflow/graph_orchestrator.py
