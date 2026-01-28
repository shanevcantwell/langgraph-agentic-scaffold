"""
Unit tests for cycle detection module.

Tests the generalized cycle detection algorithm used by:
- react_mixin.py: Tool call stagnation detection
- invariants.py: Routing loop detection

Issue #78: Tool stagnation doesn't catch cyclic patterns.
"""
import pytest
from app.src.resilience.cycle_detection import detect_cycle, detect_cycle_with_pattern


class TestDetectCycle:
    """Test detect_cycle function."""

    def test_single_item_repeated(self):
        """Period-1 cycle: A-A-A-A."""
        history = ['a', 'a', 'a', 'a']
        assert detect_cycle(history, min_repetitions=2) == 1
        assert detect_cycle(history, min_repetitions=3) == 1
        assert detect_cycle(history, min_repetitions=4) == 1

    def test_two_step_cycle(self):
        """Period-2 cycle: A-B-A-B-A-B."""
        history = ['a', 'b', 'a', 'b', 'a', 'b']
        assert detect_cycle(history, min_repetitions=2) == 2
        assert detect_cycle(history, min_repetitions=3) == 2

    def test_four_step_cycle(self):
        """Period-4 cycle: A-B-C-D-A-B-C-D (batch of 4 files)."""
        history = ['a', 'b', 'c', 'd', 'a', 'b', 'c', 'd']
        assert detect_cycle(history, min_repetitions=2) == 4

    def test_four_step_cycle_with_more_repetitions(self):
        """Period-4 cycle repeated 3 times."""
        history = ['a', 'b', 'c', 'd'] * 3
        assert detect_cycle(history, min_repetitions=2) == 4
        assert detect_cycle(history, min_repetitions=3) == 4

    def test_no_cycle_short_history(self):
        """Not enough items to detect cycle."""
        assert detect_cycle(['a'], min_repetitions=2) is None
        assert detect_cycle(['a', 'b'], min_repetitions=2) is None
        assert detect_cycle(['a', 'b', 'c'], min_repetitions=2) is None

    def test_no_cycle_different_items(self):
        """No repeating pattern."""
        history = ['a', 'b', 'c', 'd', 'e', 'f']
        assert detect_cycle(history, min_repetitions=2) is None

    def test_cycle_at_end_only(self):
        """Cycle detection should focus on the end of history."""
        # Noise at start, cycle at end
        history = ['x', 'y', 'z', 'a', 'b', 'a', 'b']
        assert detect_cycle(history, min_repetitions=2) == 2

    def test_shortest_cycle_found_first(self):
        """When multiple cycles match, shortest period wins."""
        # 'a' repeated 4 times could be period-1 or period-2
        history = ['a', 'a', 'a', 'a']
        assert detect_cycle(history, min_repetitions=2) == 1  # Period 1, not 2

    def test_max_period_limit(self):
        """Respect max_period parameter."""
        history = ['a', 'b', 'c', 'd', 'a', 'b', 'c', 'd']
        # With max_period=3, won't find period-4 cycle
        assert detect_cycle(history, min_repetitions=2, max_period=3) is None
        # With max_period=4, will find it
        assert detect_cycle(history, min_repetitions=2, max_period=4) == 4

    def test_tool_call_signatures(self):
        """Real-world tool call signature cycle (Issue #78 scenario)."""
        # Simulates read_file called on 4 different files in a loop
        signatures = [
            "read_file:path=sort_by_contents/c.txt",
            "read_file:path=sort_by_contents/k.txt",
            "read_file:path=sort_by_contents/s.txt",
            "read_file:path=sort_by_contents/v.txt",
            "read_file:path=sort_by_contents/c.txt",
            "read_file:path=sort_by_contents/k.txt",
            "read_file:path=sort_by_contents/s.txt",
            "read_file:path=sort_by_contents/v.txt",
        ]
        assert detect_cycle(signatures, min_repetitions=2) == 4

    def test_empty_history(self):
        """Empty history returns None."""
        assert detect_cycle([], min_repetitions=2) is None


class TestDetectCycleWithPattern:
    """Test detect_cycle_with_pattern function."""

    def test_returns_pattern(self):
        """Should return both period and pattern."""
        history = ['a', 'b', 'a', 'b']
        period, pattern = detect_cycle_with_pattern(history, min_repetitions=2)
        assert period == 2
        assert pattern == ['a', 'b']

    def test_four_item_pattern(self):
        """Four-item pattern from batch operation."""
        history = ['c.txt', 'k.txt', 's.txt', 'v.txt', 'c.txt', 'k.txt', 's.txt', 'v.txt']
        period, pattern = detect_cycle_with_pattern(history, min_repetitions=2)
        assert period == 4
        assert pattern == ['c.txt', 'k.txt', 's.txt', 'v.txt']

    def test_no_cycle_returns_none(self):
        """No cycle returns (None, None)."""
        history = ['a', 'b', 'c', 'd']
        period, pattern = detect_cycle_with_pattern(history, min_repetitions=2)
        assert period is None
        assert pattern is None

    def test_single_item_pattern(self):
        """Period-1 cycle has single-item pattern."""
        history = ['a', 'a', 'a']
        period, pattern = detect_cycle_with_pattern(history, min_repetitions=2)
        assert period == 1
        assert pattern == ['a']


class TestMinRepetitionsEdgeCases:
    """Test min_repetitions parameter edge cases."""

    def test_min_repetitions_1_not_useful(self):
        """min_repetitions=1 would match everything, so not typically used."""
        # With min_rep=1, any suffix is a "cycle"
        history = ['a', 'b', 'c']
        # Period 1 matches: last 1 item repeated 1 time = trivially true
        assert detect_cycle(history, min_repetitions=1) == 1

    def test_high_min_repetitions(self):
        """Need enough history for high min_repetitions."""
        history = ['a', 'b'] * 5  # 10 items
        assert detect_cycle(history, min_repetitions=5) == 2
        assert detect_cycle(history, min_repetitions=6) is None  # Would need 12 items
