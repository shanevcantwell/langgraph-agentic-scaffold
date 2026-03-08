# app/tests/unit/test_concurrent_invocation.py
"""
Concurrent Invocation Tests — Shared Mutable State Integrity (#203)

Tests derived from a formal inventory of every shared mutable data store that
concurrent LAS invocations touch. Each test group maps to an invariant:

  Group 1: CancellationManager (I1-I4)  — class-level Set[str]
  Group 2: Specialist Instance Immutability (I5) — no self.* mutation during execute
  Group 3: Output Isolation Under Concurrency (I6) — concurrent execute() results are independent
  Group 4: SafeExecutor Isolation — routing_history, error reports don't cross-contaminate
  Group 5: Pool Slot Conservation (I7) — release() always matches acquire()
  Group 6: Cascade Cancellation (#203) — parent→child cancel propagation

See plan: .claude/plans/peaceful-wandering-dream.md for the full mutable state inventory.
"""

import copy
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from langchain_core.messages import HumanMessage, AIMessage

from app.src.utils.cancellation_manager import CancellationManager


# ═══════════════════════════════════════════════════════════════════════════════
# Group 1: CancellationManager Invariants (I1-I4)
#
# Singleton with class-level Set[str]. Shared across ALL invocations.
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=False)
def reset_cancellation_manager():
    """Reset CancellationManager singleton state between tests."""
    CancellationManager._cancelled_runs = set()
    yield
    CancellationManager._cancelled_runs = set()


class TestCancellationManagerConcurrency:
    """I1-I4: CancellationManager thread-safety under concurrent operations."""

    def test_add_then_check_under_concurrency(self, reset_cancellation_manager):
        """I1: After request_cancellation(id) returns, is_cancelled(id) == True.

        10 threads each add a unique run_id. After join, verify all 10 are present.
        """
        run_ids = [f"run_{i}" for i in range(10)]
        barrier = threading.Barrier(10)

        def add_run_id(rid):
            barrier.wait()  # Synchronize start
            CancellationManager.request_cancellation(rid)

        threads = [threading.Thread(target=add_run_id, args=(rid,)) for rid in run_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for rid in run_ids:
            assert CancellationManager.is_cancelled(rid), (
                f"I1 violated: {rid} not found after concurrent add"
            )

    def test_clear_cancellation_toctou(self, reset_cancellation_manager):
        """I4: No exception raised under any interleaving of concurrent operations.

        10 threads all call clear_cancellation("same_id") concurrently after
        one request_cancellation("same_id"). The if/remove pattern in the current
        code is a TOCTOU race — this test proves it.

        Expected: FAILS with current code (KeyError from set.remove).
        Once fixed (discard instead of if/remove), this test passes.
        """
        target_id = "shared_target"
        CancellationManager.request_cancellation(target_id)
        barrier = threading.Barrier(10)
        errors = []

        def clear_run(idx):
            barrier.wait()
            try:
                CancellationManager.clear_cancellation(target_id)
            except KeyError as e:
                errors.append(f"Thread {idx}: KeyError — {e}")

        threads = [threading.Thread(target=clear_run, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"I4 violated: TOCTOU race in clear_cancellation. Errors: {errors}"
        )

    def test_no_spurious_cancellation(self, reset_cancellation_manager):
        """I3: is_cancelled(id) never returns True for an id that was never added.

        10 threads add/clear their own run_ids in tight loops. After all threads
        complete, verify no run_id is cancelled that shouldn't be.
        """
        barrier = threading.Barrier(10)

        def add_and_clear(idx):
            barrier.wait()
            rid = f"ephemeral_{idx}"
            for _ in range(50):
                CancellationManager.request_cancellation(rid)
                CancellationManager.clear_cancellation(rid)

        threads = [threading.Thread(target=add_and_clear, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(10):
            assert not CancellationManager.is_cancelled(f"ephemeral_{i}"), (
                f"I3 violated: ephemeral_{i} still cancelled after clear"
            )

    def test_bulk_add_clear_stress(self, reset_cancellation_manager):
        """I1-I4: 20 threads × 100 iterations, mixed add/clear. No exceptions, no corruption."""
        barrier = threading.Barrier(20)
        errors = []

        def stress_worker(idx):
            barrier.wait()
            try:
                for iteration in range(100):
                    rid = f"stress_{idx}_{iteration}"
                    CancellationManager.request_cancellation(rid)
                    assert CancellationManager.is_cancelled(rid)  # I1
                    CancellationManager.clear_cancellation(rid)
                    # I3: After clearing, should not be cancelled
                    # (Note: another thread won't add THIS specific rid)
                    assert not CancellationManager.is_cancelled(rid)
            except Exception as e:
                errors.append(f"Thread {idx}: {type(e).__name__} — {e}")

        threads = [threading.Thread(target=stress_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"I1-I4 stress test failed. Errors: {errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# Group 2: Specialist Instance Immutability (I5)
#
# Each specialist is instantiated once by GraphBuilder. All concurrent
# invocations share the same instance. No self.* writes during execute.
# ═══════════════════════════════════════════════════════════════════════════════

def _make_mock_adapter(response_text="Test response"):
    """Create a mock LLM adapter that returns the specified text."""
    adapter = MagicMock()
    adapter.system_prompt = "You are a test specialist."
    adapter.model_name = "test-model"
    adapter.invoke.return_value = {"text_response": response_text}
    return adapter


def _minimal_state(**overrides):
    """Build a minimal valid state dict for specialist execution.

    Includes all keys required by check_state_structure() in invariants.py.
    """
    state = {
        "messages": [HumanMessage(content="test input")],
        "artifacts": {},
        "scratchpad": {},
        "routing_history": [],
        "turn_count": 0,
        "task_is_complete": False,
    }
    state.update(overrides)
    return state


class TestSpecialistInstanceImmutability:
    """I5: specialist.__dict__ is identical before and after _execute_logic()."""

    def test_chat_specialist_instance_unchanged(self, initialized_specialist_factory):
        """ChatSpecialist: no instance mutation during execute."""
        specialist = initialized_specialist_factory("ChatSpecialist", config_override={"is_enabled": True})
        specialist.llm_adapter = _make_mock_adapter("Hello from chat")

        snapshot_before = copy.deepcopy(specialist.__dict__)
        state = _minimal_state()
        specialist._execute_logic(state)
        snapshot_after = specialist.__dict__

        # Compare keys
        assert set(snapshot_before.keys()) == set(snapshot_after.keys()), (
            f"I5 violated: ChatSpecialist.__dict__ keys changed. "
            f"Before: {set(snapshot_before.keys())}, After: {set(snapshot_after.keys())}"
        )

        # Compare values (by identity for objects, by value for primitives)
        for key in snapshot_before:
            before_val = snapshot_before[key]
            after_val = snapshot_after[key]
            if isinstance(before_val, (str, int, float, bool, type(None))):
                assert before_val == after_val, (
                    f"I5 violated: ChatSpecialist.{key} changed from {before_val!r} to {after_val!r}"
                )

    def test_prompt_specialist_instance_unchanged(self, initialized_specialist_factory):
        """PromptSpecialist: no instance mutation during execute."""
        specialist = initialized_specialist_factory("PromptSpecialist", config_override={"is_enabled": True})
        specialist.llm_adapter = _make_mock_adapter("Hello from prompt")

        snapshot_before = copy.deepcopy(specialist.__dict__)
        state = _minimal_state()
        specialist._execute_logic(state)
        snapshot_after = specialist.__dict__

        assert set(snapshot_before.keys()) == set(snapshot_after.keys()), (
            f"I5 violated: PromptSpecialist.__dict__ keys changed."
        )
        for key in snapshot_before:
            before_val = snapshot_before[key]
            after_val = snapshot_after[key]
            if isinstance(before_val, (str, int, float, bool, type(None))):
                assert before_val == after_val, (
                    f"I5 violated: PromptSpecialist.{key} changed from {before_val!r} to {after_val!r}"
                )

    def test_project_director_instance_unchanged(self, initialized_specialist_factory):
        """ProjectDirector: no instance mutation during react_step loop.

        PD has the most complex _execute_logic() — a react_step loop with
        trace, captured_artifacts, successful_paths all as local variables.
        This test confirms none of them leak into self.
        """
        specialist = initialized_specialist_factory(
            "ProjectDirector",
            specialist_name_override="project_director",
            config_override={"is_enabled": True, "max_iterations": 2},
        )
        specialist.llm_adapter = _make_mock_adapter()

        # Mock external_mcp_client so is_react_available() returns True
        mock_mcp = MagicMock()
        mock_mcp.is_connected.return_value = True
        specialist.external_mcp_client = mock_mcp

        snapshot_before = copy.deepcopy(specialist.__dict__)

        # Mock call_react_step to return completed immediately
        with patch("app.src.specialists.project_director.call_react_step") as mock_crs:
            mock_crs.return_value = {
                "completed": True,
                "final_response": "Task done.",
                "call_counter": 1,
            }
            state = _minimal_state(artifacts={"user_request": "Test task"})
            specialist._execute_logic(state)

        snapshot_after = specialist.__dict__

        assert set(snapshot_before.keys()) == set(snapshot_after.keys()), (
            f"I5 violated: ProjectDirector.__dict__ keys changed. "
            f"Added: {set(snapshot_after.keys()) - set(snapshot_before.keys())}, "
            f"Removed: {set(snapshot_before.keys()) - set(snapshot_after.keys())}"
        )
        for key in snapshot_before:
            before_val = snapshot_before[key]
            after_val = snapshot_after[key]
            if isinstance(before_val, (str, int, float, bool, type(None))):
                assert before_val == after_val, (
                    f"I5 violated: ProjectDirector.{key} changed from {before_val!r} to {after_val!r}"
                )

    def test_exit_interview_instance_unchanged(self, initialized_specialist_factory):
        """ExitInterviewSpecialist: no instance mutation during react_step verification."""
        specialist = initialized_specialist_factory(
            "ExitInterviewSpecialist",
            specialist_name_override="exit_interview_specialist",
            config_override={"is_enabled": True, "max_iterations": 2},
        )
        specialist.llm_adapter = _make_mock_adapter()

        # Mock external_mcp_client so is_react_available() returns True
        mock_mcp = MagicMock()
        mock_mcp.is_connected.return_value = True
        specialist.external_mcp_client = mock_mcp

        # Set routable specialists (done once at graph build time)
        specialist.set_routable_specialists(["project_director", "chat_specialist"])

        snapshot_before = copy.deepcopy(specialist.__dict__)

        # Mock call_react_step to return a DONE tool call
        with patch("app.src.specialists.exit_interview_specialist.call_react_step") as mock_crs:
            mock_crs.return_value = {
                "completed": True,
                "done_args": {"is_complete": True, "reasoning": "All verified"},
                "final_response": "Verified.",
                "call_counter": 1,
            }
            state = _minimal_state(
                artifacts={"user_request": "Test task", "exit_plan": {}}
            )
            specialist._execute_logic(state)

        snapshot_after = specialist.__dict__

        assert set(snapshot_before.keys()) == set(snapshot_after.keys()), (
            f"I5 violated: EI.__dict__ keys changed."
        )
        for key in snapshot_before:
            before_val = snapshot_before[key]
            after_val = snapshot_after[key]
            if isinstance(before_val, (str, int, float, bool, type(None))):
                assert before_val == after_val, (
                    f"I5 violated: EI.{key} changed from {before_val!r} to {after_val!r}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Group 3: Output Isolation Under Concurrency (I6)
#
# Given concurrent execute(state_A) and execute(state_B) on the SAME instance,
# result_A derives only from state_A, result_B only from state_B.
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputIsolation:
    """I6: Concurrent executions on the same specialist instance produce isolated results."""

    def test_concurrent_chat_output_isolation(self, initialized_specialist_factory):
        """Same ChatSpecialist instance, two threads with different inputs.

        Thread A: messages=["Alpha"], adapter returns "Response Alpha"
        Thread B: messages=["Bravo"], adapter returns "Response Bravo"

        The mock adapter uses the input messages to determine the response,
        plus a sleep to force temporal overlap.
        """
        specialist = initialized_specialist_factory("ChatSpecialist", config_override={"is_enabled": True})

        # Adapter that echoes a discriminator from the input
        def mock_invoke(request):
            # Introduce delay to force thread overlap
            time.sleep(0.05)
            # Extract discriminator from the last message
            messages = request.messages
            last_content = messages[-1].content if messages else "unknown"
            return {"text_response": f"Response to: {last_content}"}

        mock_adapter = MagicMock()
        mock_adapter.system_prompt = "test"
        mock_adapter.model_name = "test-model"
        mock_adapter.invoke.side_effect = mock_invoke
        specialist.llm_adapter = mock_adapter

        results = {}
        barrier = threading.Barrier(2)

        def run_specialist(label, input_text):
            barrier.wait()
            state = _minimal_state(
                messages=[HumanMessage(content=input_text)]
            )
            results[label] = specialist._execute_logic(state)

        t_alpha = threading.Thread(target=run_specialist, args=("alpha", "Alpha input"))
        t_bravo = threading.Thread(target=run_specialist, args=("bravo", "Bravo input"))
        t_alpha.start()
        t_bravo.start()
        t_alpha.join()
        t_bravo.join()

        # Verify each thread got its own response
        alpha_msg = results["alpha"]["messages"][0].content
        bravo_msg = results["bravo"]["messages"][0].content

        assert "Alpha input" in alpha_msg, (
            f"I6 violated: Alpha got wrong response: {alpha_msg}"
        )
        assert "Bravo input" in bravo_msg, (
            f"I6 violated: Bravo got wrong response: {bravo_msg}"
        )
        assert "Bravo" not in alpha_msg, (
            f"I6 violated: Alpha response contaminated with Bravo: {alpha_msg}"
        )
        assert "Alpha" not in bravo_msg, (
            f"I6 violated: Bravo response contaminated with Alpha: {bravo_msg}"
        )

    def test_concurrent_pd_artifact_isolation(self, initialized_specialist_factory):
        """Same PD instance, two threads producing different artifacts.

        Thread A: user_request="Task A" → captured_artifacts includes "user_request": "Task A"
        Thread B: user_request="Task B" → captured_artifacts includes "user_request": "Task B"

        Verify no cross-contamination in returned artifact dicts.
        """
        specialist = initialized_specialist_factory(
            "ProjectDirector",
            specialist_name_override="project_director",
            config_override={"is_enabled": True, "max_iterations": 2},
        )
        specialist.llm_adapter = _make_mock_adapter()

        mock_mcp = MagicMock()
        mock_mcp.is_connected.return_value = True
        specialist.external_mcp_client = mock_mcp

        results = {}
        barrier = threading.Barrier(2)

        def run_pd(label, user_request):
            barrier.wait()
            with patch("app.src.specialists.project_director.call_react_step") as mock_crs:
                # Delay to force overlap
                def delayed_react_step(*args, **kwargs):
                    time.sleep(0.05)
                    return {
                        "completed": True,
                        "final_response": f"Done: {user_request}",
                        "call_counter": 1,
                    }
                mock_crs.side_effect = delayed_react_step

                state = _minimal_state(
                    artifacts={
                        "user_request": user_request,
                        f"artifact_{label}": f"data for {label}",
                    }
                )
                results[label] = specialist._execute_logic(state)

        t_a = threading.Thread(target=run_pd, args=("alpha", "Task Alpha"))
        t_b = threading.Thread(target=run_pd, args=("bravo", "Task Bravo"))
        t_a.start()
        t_b.start()
        t_a.join()
        t_b.join()

        # Verify artifact isolation
        alpha_artifacts = results["alpha"].get("artifacts", {})
        bravo_artifacts = results["bravo"].get("artifacts", {})

        assert alpha_artifacts.get("user_request") == "Task Alpha", (
            f"I6 violated: Alpha artifacts have wrong user_request: {alpha_artifacts.get('user_request')}"
        )
        assert bravo_artifacts.get("user_request") == "Task Bravo", (
            f"I6 violated: Bravo artifacts have wrong user_request: {bravo_artifacts.get('user_request')}"
        )
        assert "artifact_bravo" not in alpha_artifacts, (
            f"I6 violated: Alpha artifacts contain Bravo's artifact"
        )
        assert "artifact_alpha" not in bravo_artifacts, (
            f"I6 violated: Bravo artifacts contain Alpha's artifact"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Group 4: SafeExecutor Isolation
#
# Two concurrent SafeExecutors wrapping different specialists must produce
# independent routing_history and error state.
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeExecutorIsolation:
    """SafeExecutor wraps each specialist. Concurrent wrappers must not cross-contaminate."""

    def _make_safe_executor(self, specialist_name, response_text):
        """Create a SafeExecutor-wrapped specialist with mock adapter."""
        from app.src.workflow.executors.node_executor import NodeExecutor

        config = {
            "workflow": {"recursion_limit": 40, "max_loop_cycles": 3},
            "specialists": {specialist_name: {"type": "llm"}},
        }
        executor = NodeExecutor(config)

        # Create a minimal specialist mock
        specialist = MagicMock(spec=["specialist_name", "specialist_config", "execute",
                                     "llm_adapter", "_execute_logic"])
        specialist.specialist_name = specialist_name
        specialist.specialist_config = config["specialists"][specialist_name]
        specialist.llm_adapter = _make_mock_adapter(response_text)

        # execute() returns a valid result dict
        specialist.execute.return_value = {
            "messages": [AIMessage(content=response_text)],
            "scratchpad": {"user_response_snippets": [response_text]},
            "task_is_complete": True,
        }

        return executor.create_safe_executor(specialist)

    def test_concurrent_safe_executors_routing_history(self):
        """Two safe_executors called concurrently produce independent routing_history."""
        safe_exec_alpha = self._make_safe_executor("alpha_specialist", "Alpha response")
        safe_exec_bravo = self._make_safe_executor("bravo_specialist", "Bravo response")

        results = {}
        barrier = threading.Barrier(2)

        def run_executor(label, safe_exec):
            barrier.wait()
            state = _minimal_state()
            results[label] = safe_exec(state)

        t_a = threading.Thread(target=run_executor, args=("alpha", safe_exec_alpha))
        t_b = threading.Thread(target=run_executor, args=("bravo", safe_exec_bravo))
        t_a.start()
        t_b.start()
        t_a.join()
        t_b.join()

        alpha_history = results["alpha"].get("routing_history", [])
        bravo_history = results["bravo"].get("routing_history", [])

        assert alpha_history == ["alpha_specialist"], (
            f"Alpha routing_history wrong: {alpha_history}"
        )
        assert bravo_history == ["bravo_specialist"], (
            f"Bravo routing_history wrong: {bravo_history}"
        )

    def test_concurrent_safe_executor_error_isolation(self):
        """Thread A's specialist raises. Thread B's succeeds. No error contamination."""
        from app.src.workflow.executors.node_executor import NodeExecutor
        from app.src.utils.errors import SpecialistError

        config = {
            "workflow": {"recursion_limit": 40, "max_loop_cycles": 3},
            "specialists": {
                "failing_specialist": {"type": "llm"},
                "success_specialist": {"type": "llm"},
            },
        }
        executor = NodeExecutor(config)

        # Failing specialist
        failing_spec = MagicMock(spec=["specialist_name", "specialist_config", "execute",
                                       "llm_adapter", "_execute_logic"])
        failing_spec.specialist_name = "failing_specialist"
        failing_spec.specialist_config = config["specialists"]["failing_specialist"]
        failing_spec.llm_adapter = _make_mock_adapter()
        failing_spec.execute.side_effect = SpecialistError("Deliberate test failure")

        # Succeeding specialist
        success_spec = MagicMock(spec=["specialist_name", "specialist_config", "execute",
                                       "llm_adapter", "_execute_logic"])
        success_spec.specialist_name = "success_specialist"
        success_spec.specialist_config = config["specialists"]["success_specialist"]
        success_spec.llm_adapter = _make_mock_adapter("Success response")
        success_spec.execute.return_value = {
            "messages": [AIMessage(content="Success response")],
            "task_is_complete": True,
        }

        safe_exec_fail = executor.create_safe_executor(failing_spec)
        safe_exec_success = executor.create_safe_executor(success_spec)

        results = {}
        barrier = threading.Barrier(2)

        def run_executor(label, safe_exec):
            barrier.wait()
            # Add a small delay for the failing one to ensure overlap
            if label == "fail":
                time.sleep(0.02)
            state = _minimal_state()
            results[label] = safe_exec(state)

        t_fail = threading.Thread(target=run_executor, args=("fail", safe_exec_fail))
        t_success = threading.Thread(target=run_executor, args=("success", safe_exec_success))
        t_fail.start()
        t_success.start()
        t_fail.join()
        t_success.join()

        # Failing executor should have error in scratchpad
        fail_scratchpad = results["fail"].get("scratchpad", {})
        assert "error" in fail_scratchpad, (
            f"Failing executor should have error in scratchpad: {fail_scratchpad}"
        )

        # Succeeding executor should have NO error contamination
        success_scratchpad = results["success"].get("scratchpad", {})
        assert "error" not in success_scratchpad or success_scratchpad.get("error") is None, (
            f"Error contamination: success executor has error in scratchpad: {success_scratchpad}"
        )

        # Success result should have its own routing_history
        success_history = results["success"].get("routing_history", [])
        assert "failing_specialist" not in success_history, (
            f"Routing history contamination: {success_history}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Group 5: Pool Slot Conservation (I7)
#
# PooledLMStudioAdapter.invoke() acquires a slot, makes HTTP call, releases in
# finally. Total release() calls must equal total acquire() calls.
# ═══════════════════════════════════════════════════════════════════════════════

class TestPoolSlotConservation:
    """I7: Total release() calls equals total acquire() calls."""

    def _make_pooled_adapter(self, pool_mock, dispatcher_mock, loop_mock):
        """Create a PooledLocalInferenceAdapter with mocked pool infrastructure."""
        from app.src.llm.pooled_adapter import PooledLocalInferenceAdapter

        model_config = {
            "api_identifier": "test-model",
            "context_window": 4096,
        }

        adapter = PooledLocalInferenceAdapter(
            model_config=model_config,
            system_prompt="Test system prompt",
            pool=pool_mock,
            dispatcher=dispatcher_mock,
            loop=loop_mock,
        )
        return adapter

    def test_pool_release_on_success(self):
        """Slot released after successful invoke."""
        import asyncio

        pool_mock = MagicMock()
        pool_mock.servers = {"http://server1:1234": MagicMock(api_key=None)}
        dispatcher_mock = MagicMock()
        loop_mock = MagicMock()

        adapter = self._make_pooled_adapter(pool_mock, dispatcher_mock, loop_mock)

        # Mock the async bridge: run_coroutine_threadsafe returns a Future
        # that resolves to a server URL
        with patch("asyncio.run_coroutine_threadsafe") as mock_rctf:
            future_mock = MagicMock()
            future_mock.result.return_value = "http://server1:1234"
            mock_rctf.return_value = future_mock

            # Mock the OpenAI client call
            with patch("app.src.llm.pooled_adapter.OpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_completion = MagicMock()
                mock_completion.choices = [MagicMock()]
                mock_completion.choices[0].message.content = "Test response"
                mock_completion.choices[0].message.tool_calls = None
                mock_completion.model = "test-model"
                mock_completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
                mock_client.chat.completions.create.return_value = mock_completion
                mock_openai.return_value = mock_client

                from app.src.llm.adapter import StandardizedLLMRequest
                request = StandardizedLLMRequest(messages=[HumanMessage(content="test")])

                adapter.invoke(request)

        # Verify release was called
        pool_mock.release_server.assert_called_once_with("http://server1:1234")

    def test_pool_release_on_exception(self):
        """I7: Slot released even when HTTP call throws."""
        pool_mock = MagicMock()
        pool_mock.servers = {"http://server1:1234": MagicMock(api_key=None)}
        dispatcher_mock = MagicMock()
        loop_mock = MagicMock()

        adapter = self._make_pooled_adapter(pool_mock, dispatcher_mock, loop_mock)

        with patch("asyncio.run_coroutine_threadsafe") as mock_rctf:
            future_mock = MagicMock()
            future_mock.result.return_value = "http://server1:1234"
            mock_rctf.return_value = future_mock

            with patch("app.src.llm.pooled_adapter.OpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.chat.completions.create.side_effect = Exception("Connection refused")
                mock_openai.return_value = mock_client

                from app.src.llm.adapter import StandardizedLLMRequest
                from app.src.llm.adapter import LLMInvocationError
                request = StandardizedLLMRequest(messages=[HumanMessage(content="test")])

                with pytest.raises(LLMInvocationError):
                    adapter.invoke(request)

        # CRITICAL: release must still be called despite the exception
        pool_mock.release_server.assert_called_once_with("http://server1:1234")

    def test_concurrent_pool_acquire_release(self):
        """I7: 4 threads invoke adapter concurrently. release called exactly 4 times.

        Patches are applied at test scope (not per-thread) to avoid conflicts
        on module-level functions.
        """
        pool_mock = MagicMock()
        pool_mock.servers = {
            "http://server1:1234": MagicMock(api_key=None),
            "http://server2:1234": MagicMock(api_key=None),
        }
        dispatcher_mock = MagicMock()
        loop_mock = MagicMock()

        adapter = self._make_pooled_adapter(pool_mock, dispatcher_mock, loop_mock)

        barrier = threading.Barrier(4)
        errors = []

        # Single test-level patches — safe for concurrent threads
        with patch("asyncio.run_coroutine_threadsafe") as mock_rctf, \
             patch("app.src.llm.pooled_adapter.OpenAI") as mock_openai:

            # run_coroutine_threadsafe returns a new Future each call
            def make_future(*args, **kwargs):
                f = MagicMock()
                f.result.return_value = "http://server1:1234"
                return f
            mock_rctf.side_effect = make_future

            # OpenAI() returns a mock client each call
            def make_client(*args, **kwargs):
                client = MagicMock()
                completion = MagicMock()
                completion.choices = [MagicMock()]
                completion.choices[0].message.content = "Response"
                completion.choices[0].message.tool_calls = None
                completion.model = "test-model"
                completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
                client.chat.completions.create.return_value = completion
                return client
            mock_openai.side_effect = make_client

            def thread_invoke(idx):
                barrier.wait()
                try:
                    from app.src.llm.adapter import StandardizedLLMRequest
                    request = StandardizedLLMRequest(
                        messages=[HumanMessage(content=f"test {idx}")]
                    )
                    adapter.invoke(request)
                except Exception as e:
                    errors.append(f"Thread {idx}: {e}")

            threads = [threading.Thread(target=thread_invoke, args=(i,)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors, f"Thread errors: {errors}"

        # release_server should be called exactly 4 times (once per invoke)
        assert pool_mock.release_server.call_count == 4, (
            f"I7 violated: release_server called {pool_mock.release_server.call_count} times, expected 4"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Group 6: Cascade Cancellation (#203 — Parent→Child Propagation)
#
# Tests the parent-child tree in CancellationManager:
#   - register_child() establishes relationships
#   - request_cancellation() cascades to all descendants
#   - clear_cancellation() cleans up the tree
#   - SafeExecutor respects run_id cancellation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCascadeCancellation:
    """Verify parent→child cancellation propagation (#203)."""

    def setup_method(self):
        """Reset CancellationManager class-level state between tests."""
        CancellationManager._cancelled_runs.clear()
        CancellationManager._parent_to_children.clear()
        CancellationManager._child_to_parent.clear()

    def teardown_method(self):
        CancellationManager._cancelled_runs.clear()
        CancellationManager._parent_to_children.clear()
        CancellationManager._child_to_parent.clear()

    def test_register_child_creates_relationship(self):
        """register_child() establishes bidirectional parent-child link."""
        CancellationManager.register_child("parent-1", "child-1")

        assert "child-1" in CancellationManager._parent_to_children["parent-1"]
        assert CancellationManager._child_to_parent["child-1"] == "parent-1"

    def test_cancel_parent_cascades_to_child(self):
        """Cancelling parent also cancels registered children."""
        CancellationManager.register_child("parent-1", "child-1")
        CancellationManager.register_child("parent-1", "child-2")

        CancellationManager.request_cancellation("parent-1")

        assert CancellationManager.is_cancelled("parent-1")
        assert CancellationManager.is_cancelled("child-1")
        assert CancellationManager.is_cancelled("child-2")

    def test_cancel_parent_cascades_to_grandchildren(self):
        """Cancellation cascades recursively through the entire tree."""
        CancellationManager.register_child("parent", "child")
        CancellationManager.register_child("child", "grandchild")

        CancellationManager.request_cancellation("parent")

        assert CancellationManager.is_cancelled("parent")
        assert CancellationManager.is_cancelled("child")
        assert CancellationManager.is_cancelled("grandchild")

    def test_cancel_child_does_not_cascade_to_parent(self):
        """Cancelling a child does NOT propagate upward to the parent."""
        CancellationManager.register_child("parent", "child")

        CancellationManager.request_cancellation("child")

        assert CancellationManager.is_cancelled("child")
        assert not CancellationManager.is_cancelled("parent")

    def test_cancel_idempotent_prevents_infinite_recursion(self):
        """Repeated cancellation of same run_id is safe (no infinite loop)."""
        CancellationManager.register_child("parent", "child")
        CancellationManager.request_cancellation("parent")
        # Second call should be a no-op
        CancellationManager.request_cancellation("parent")

        assert CancellationManager.is_cancelled("parent")
        assert CancellationManager.is_cancelled("child")

    def test_clear_removes_from_tree(self):
        """clear_cancellation() cleans up the parent-child registry."""
        CancellationManager.register_child("parent", "child-1")
        CancellationManager.register_child("parent", "child-2")

        CancellationManager.clear_cancellation("child-1")

        # child-1 removed from parent's children set
        assert "child-1" not in CancellationManager._parent_to_children.get("parent", set())
        # child-2 still registered
        assert "child-2" in CancellationManager._parent_to_children["parent"]
        # child-1 no longer in child_to_parent
        assert "child-1" not in CancellationManager._child_to_parent

    def test_clear_parent_removes_children_registry(self):
        """clear_cancellation() on parent removes its children set."""
        CancellationManager.register_child("parent", "child")

        CancellationManager.clear_cancellation("parent")

        assert "parent" not in CancellationManager._parent_to_children

    def test_safe_executor_checks_cancellation(self):
        """SafeExecutor returns abort when run_id is cancelled."""
        from app.src.workflow.executors.node_executor import NodeExecutor

        # Minimal config for NodeExecutor
        config = {"specialists": {}, "invariant_monitor": {"max_loop_count": 10}}
        executor = NodeExecutor(config)

        # Create a minimal specialist
        specialist = MagicMock()
        specialist.specialist_name = "test_specialist"
        specialist.specialist_config = {}
        specialist.llm_adapter = None

        safe_exec = executor.create_safe_executor(specialist)

        # Cancel the run before execution
        CancellationManager.request_cancellation("cancelled-run")

        state = {
            "messages": [HumanMessage(content="test")],
            "artifacts": {},
            "scratchpad": {},
            "routing_history": [],
            "turn_count": 0,
            "task_is_complete": False,
            "run_id": "cancelled-run",
        }

        result = safe_exec(state)

        # Should return abort, not execute the specialist
        assert result["task_is_complete"] is True
        assert "cancelled" in result["scratchpad"]["error"].lower()
        specialist.execute.assert_not_called()

    def test_safe_executor_allows_uncancelled_run(self):
        """SafeExecutor proceeds normally when run_id is not cancelled."""
        from app.src.workflow.executors.node_executor import NodeExecutor

        config = {"specialists": {}, "invariant_monitor": {"max_loop_count": 10}}
        executor = NodeExecutor(config)

        specialist = MagicMock()
        specialist.specialist_name = "test_specialist"
        specialist.specialist_config = {"type": "llm"}
        specialist.llm_adapter = MagicMock()
        specialist.llm_adapter.system_prompt = "test"
        specialist.llm_adapter.model_name = "test-model"
        specialist.execute.return_value = {
            "messages": [AIMessage(content="done")],
            "artifacts": {},
        }

        safe_exec = executor.create_safe_executor(specialist)

        state = {
            "messages": [HumanMessage(content="test")],
            "artifacts": {},
            "scratchpad": {},
            "routing_history": [],
            "turn_count": 0,
            "task_is_complete": False,
            "run_id": "active-run",
        }

        result = safe_exec(state)

        # Specialist should have been called
        specialist.execute.assert_called_once()

    def test_concurrent_cancel_and_register(self):
        """Concurrent register_child + request_cancellation don't corrupt state."""
        barrier = threading.Barrier(3)
        errors = []

        def register_children():
            barrier.wait()
            try:
                for i in range(50):
                    CancellationManager.register_child("parent", f"child-{i}")
            except Exception as e:
                errors.append(f"register: {e}")

        def cancel_parent():
            barrier.wait()
            try:
                time.sleep(0.001)  # Let some registrations happen first
                CancellationManager.request_cancellation("parent")
            except Exception as e:
                errors.append(f"cancel: {e}")

        def clear_children():
            barrier.wait()
            try:
                time.sleep(0.002)  # Let cancel propagate first
                for i in range(50):
                    CancellationManager.clear_cancellation(f"child-{i}")
            except Exception as e:
                errors.append(f"clear: {e}")

        threads = [
            threading.Thread(target=register_children),
            threading.Thread(target=cancel_parent),
            threading.Thread(target=clear_children),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent operation errors: {errors}"
        # Parent should definitely be cancelled
        assert CancellationManager.is_cancelled("parent")
