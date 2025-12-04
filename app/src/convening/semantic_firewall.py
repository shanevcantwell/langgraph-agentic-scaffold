import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

class SemanticFirewall:
    """
    Security and hygiene layer between The Heap (Disk) and The Stack (Context Window).
    
    Responsibilities:
    1. Sanitize Input (Heap -> Stack): Prevent prompt injection, excessive tokens, or malformed data.
    2. Sanitize Output (Stack -> Heap): Prevent "slop" (repetitive loops, refusals, empty content) from polluting the permanent record.
    """

    # Regex patterns for "slop" detection (e.g., "I cannot fulfill this request", "As an AI...")
    # These are simple heuristics to catch low-value outputs.
    _SLOP_PATTERNS = [
        r"I cannot (fulfill|comply|answer)",
        r"As an (AI|language model)",
        r"I apologize, but I cannot",
        r"^(\s*)$" # Empty or whitespace only
    ]

    def __init__(self):
        self.slop_regex = [re.compile(p, re.IGNORECASE) for p in self._SLOP_PATTERNS]

    def sanitize_input(self, content: str, max_length: int = 100000) -> str:
        """
        Clean content before loading it into the Context Window (Stack).
        
        Args:
            content: The raw content from a file or branch.
            max_length: Hard limit on character count to prevent context window overflow.
            
        Returns:
            Sanitized content string.
        """
        if not content:
            return ""

        # 1. Length Check
        if len(content) > max_length:
            logger.warning(f"SemanticFirewall: Truncating input from {len(content)} to {max_length} chars")
            content = content[:max_length] + "\n...[TRUNCATED BY FIREWALL]..."

        # 2. Injection Pattern Stripping (Placeholder)
        # TODO: Add sophisticated injection detection here.
        # For now, we assume the Heap is relatively trusted, but we might want to 
        # strip specific control tokens if they appear in the text.

        return content

    def sanitize_output(self, content: str) -> Optional[str]:
        """
        Clean content before writing it to The Heap.
        
        Args:
            content: The raw output from an agent.
            
        Returns:
            Sanitized content string, or None if the content is rejected (e.g., pure slop).
        """
        if not content:
            return None

        # 1. Slop Detection
        for pattern in self.slop_regex:
            if pattern.search(content):
                logger.warning(f"SemanticFirewall: Rejected output matching slop pattern: {pattern.pattern}")
                return None

        # 2. PII/Secret Redaction (Placeholder)
        # TODO: Integrate with a PII scrubber (e.g., Microsoft Presidio) if needed.

        return content.strip()
