"""
Generalized cycle detection for sequences.

Used by:
- react_mixin.py: Detect tool call cycles (e.g., read_file on same N files repeatedly)
- invariants.py: Detect routing cycles (e.g., specialist A→B→A→B)

Addresses Issue #78: Tool stagnation doesn't catch cyclic patterns.
"""
from typing import List, Optional, Any, Tuple


def detect_cycle(history: List[Any], min_repetitions: int = 2, max_period: Optional[int] = None) -> Optional[int]:
    """
    Detect if history ends with a repeating cycle.

    Returns the cycle period if found, None otherwise.
    Finds the shortest cycle that repeats at least min_repetitions times.

    Args:
        history: Sequence of items to check (e.g., tool call signatures, specialist names)
        min_repetitions: Minimum number of times the cycle must repeat (default: 2)
        max_period: Maximum cycle length to check (default: len(history) // min_repetitions)

    Returns:
        Cycle period (int) if detected, None if no cycle found

    Examples:
        >>> detect_cycle(['a', 'a', 'a', 'a'])  # Same item repeated
        1
        >>> detect_cycle(['a', 'b', 'a', 'b', 'a', 'b'])  # 2-step cycle
        2
        >>> detect_cycle(['a', 'b', 'c', 'd', 'a', 'b', 'c', 'd'])  # 4-step cycle
        4
        >>> detect_cycle(['a', 'b', 'c'])  # No cycle
        None
    """
    n = len(history)
    if n < min_repetitions:
        return None

    # Default max_period: largest period that could repeat min_repetitions times
    if max_period is None:
        max_period = n // min_repetitions

    # Try each possible period from 1 (shortest) to max_period
    for period in range(1, max_period + 1):
        # Need at least period * min_repetitions items to verify this period
        if n < period * min_repetitions:
            continue

        # Extract the candidate pattern (last `period` items)
        pattern = history[-period:]

        # Check if pattern repeats min_repetitions times at the end
        is_cycle = True
        for rep in range(1, min_repetitions):
            # Calculate slice for the rep-th repetition from the end
            start = -(period * (rep + 1))
            end = -(period * rep)
            segment = history[start:end]

            if segment != pattern:
                is_cycle = False
                break

        if is_cycle:
            return period

    return None


def detect_cycle_with_pattern(history: List[Any], min_repetitions: int = 2, max_period: Optional[int] = None) -> Tuple[Optional[int], Optional[List[Any]]]:
    """
    Like detect_cycle, but also returns the repeating pattern.

    Returns:
        (period, pattern) tuple. Both are None if no cycle detected.

    Example:
        >>> detect_cycle_with_pattern(['a', 'b', 'a', 'b', 'a', 'b'])
        (2, ['a', 'b'])
    """
    period = detect_cycle(history, min_repetitions, max_period)
    if period is None:
        return None, None
    return period, history[-period:]
