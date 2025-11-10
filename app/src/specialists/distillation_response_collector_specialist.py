"""
Distillation Response Collector Specialist

This specialist collects teacher model responses for expanded prompts, writing results
to hierarchical JSONL files with retry logic and rate limiting.

Reference: docs/ADR/DISTILLATION_IMPLEMENTATION_PLAN.md Phase 1.4
Reference: docs/ADR/ADR-DISTILL-004_File_Persistence_Strategy.md
"""

import logging
import json
import time
import hashlib
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from langchain_core.messages import HumanMessage
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class DistillationResponseCollectorSpecialist(BaseSpecialist):
    """
    Collects teacher model responses for distillation dataset generation.

    Workflow Pattern: Graph-Driven Iteration (ONE prompt per invocation)
    - Takes ONE prompt from distillation_state.expanded_prompts[collection_index]
    - Calls teacher model with retry logic (tenacity)
    - Applies rate limiting between requests
    - Writes JSONL entry to hierarchical file structure via MCP
    - Writes errors to .errors log file
    - Updates distillation_state.collection_index

    Configuration:
    - inter_request_delay: Seconds between requests (default: 20.0 for web UI)
    - inter_request_jitter: Randomness % (default: 0.2 for ±20% variation)
    - retry_attempts: Max retry attempts (default: 3)
    - retry_timeout: Max wait per attempt (default: 60.0 seconds)
    - error_tolerance: Max error rate before halting (default: 0.1 = 10%)
    """

    # Domain descriptions for context
    DOMAIN_DESCRIPTIONS = {
        "agentic_architecture": "Multi-agent system design, orchestration patterns, and resilience",
        "state_management": "LangGraph state patterns, reducers, and data flow best practices",
        "llm_integration": "LLM adapter patterns, multi-model strategies, and provider abstraction",
        "specialist_patterns": "Specialist design patterns, functional decomposition, and composition",
        "error_handling": "Progressive resilience, circuit breakers, and fault tolerance",
        "testing_strategies": "Testing LLM-based systems, mocking patterns, and quality assurance",
        "communication_patterns": "Inter-specialist communication, Dossier pattern, and MCP",
        "observability_debugging": "Tracing, logging, monitoring, and debugging techniques",
    }

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initialize the DistillationResponseCollectorSpecialist.

        Args:
            specialist_name: The name of this specialist instance
            specialist_config: Configuration dictionary from config.yaml
        """
        super().__init__(specialist_name, specialist_config)

        # Load configuration
        self.inter_request_delay = specialist_config.get("inter_request_delay", 20.0)
        self.inter_request_jitter = specialist_config.get("inter_request_jitter", 0.2)
        self.retry_attempts = specialist_config.get("retry_attempts", 3)
        self.retry_timeout = specialist_config.get("retry_timeout", 60.0)
        self.error_tolerance = specialist_config.get("error_tolerance", 0.1)

        # Load prompt template
        self.prompt_template = load_prompt("distillation_collector_prompt.md")

        # Track rate limiting
        self.last_request_time = 0.0

        logger.info(
            f"---INITIALIZED {self.specialist_name}--- "
            f"(delay={self.inter_request_delay}s, retry={self.retry_attempts}, "
            f"tolerance={self.error_tolerance*100}%)"
        )

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect teacher model response for ONE prompt.

        Args:
            state: GraphState containing distillation_state

        Returns:
            Dict updating distillation_state progress

        Raises:
            KeyError: If distillation_state missing required fields
        """
        logger.info(f"--- {self.specialist_name}: Collecting teacher response ---")

        # Extract distillation state
        distillation_state = state.get("distillation_state", {})
        if not distillation_state:
            raise KeyError("distillation_state not found in GraphState")

        # Get current prompt to collect
        expanded_prompts = distillation_state.get("expanded_prompts", [])
        collection_index = distillation_state.get("collection_index", 0)
        current_domain = distillation_state.get("current_domain", "unknown")
        output_dir = distillation_state.get("output_dir", "./datasets")
        seed_prompts = distillation_state.get("seed_prompts", [])

        if collection_index >= len(expanded_prompts):
            logger.error(
                f"collection_index ({collection_index}) exceeds expanded_prompts length "
                f"({len(expanded_prompts)})"
            )
            return {"error": "Collection index out of range"}

        prompt = expanded_prompts[collection_index]
        logger.info(
            f"Collecting response {collection_index + 1}/{len(expanded_prompts)} "
            f"in domain '{current_domain}' ({len(prompt)} chars)"
        )

        # Check error tolerance
        responses_collected = distillation_state.get("responses_collected", 0)
        error_count = distillation_state.get("error_count", 0)
        total_attempts = responses_collected + error_count

        if total_attempts > 0:
            error_rate = error_count / total_attempts
            if error_rate > self.error_tolerance:
                logger.error(
                    f"Error rate ({error_rate:.1%}) exceeds tolerance ({self.error_tolerance:.1%}). "
                    f"Halting collection."
                )
                return {
                    "task_is_complete": True,
                    "error": f"Error tolerance exceeded: {error_rate:.1%} > {self.error_tolerance:.1%}"
                }

        # Apply rate limiting
        self._apply_rate_limit()

        # Get metadata
        seed_index, variation_index = self._get_seed_index_for_prompt(
            collection_index, len(seed_prompts), distillation_state.get("variations_per_seed", 3)
        )
        seed_prompt = seed_prompts[seed_index] if seed_index < len(seed_prompts) else "Unknown"

        # Call teacher model with retry
        try:
            response = self._call_teacher_with_retry(prompt, current_domain)

            # Write to JSONL file
            self._write_response_to_file(
                prompt=prompt,
                response=response,
                domain=current_domain,
                output_dir=output_dir,
                seed_prompt=seed_prompt,
                seed_index=seed_index,
                variation_index=variation_index,
            )

            logger.info(f"Successfully collected response {collection_index + 1}")

            # Update progress
            return {
                "distillation_state": {
                    "collection_index": collection_index + 1,
                    "responses_collected": responses_collected + 1,
                }
            }

        except RetryError as e:
            logger.error(f"Failed to collect response after {self.retry_attempts} retries: {e}")

            # Write error to error log
            self._write_error_to_file(
                prompt=prompt,
                error=str(e),
                domain=current_domain,
                output_dir=output_dir,
            )

            # Update progress
            return {
                "distillation_state": {
                    "collection_index": collection_index + 1,
                    "error_count": error_count + 1,
                }
            }

    def _apply_rate_limit(self):
        """
        Apply rate limiting with jitter between requests.

        Blocks until enough time has elapsed since last request.
        """
        import random

        # Calculate jittered delay
        jitter_factor = 1.0 + random.uniform(-self.inter_request_jitter, self.inter_request_jitter)
        delay = self.inter_request_delay * jitter_factor

        # Wait if needed
        elapsed = time.time() - self.last_request_time
        if elapsed < delay:
            wait_time = delay - elapsed
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s before next request")
            time.sleep(wait_time)

        self.last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),  # Will be overridden by instance config
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True
    )
    def _call_teacher_with_retry(self, prompt: str, domain: str) -> Dict[str, Any]:
        """
        Call teacher model with retry logic.

        Args:
            prompt: The expanded prompt to send
            domain: Current domain for context

        Returns:
            Dict with text_response and optional thinking_stages

        Raises:
            Exception: If all retries exhausted
        """
        # Format prompt with domain context
        domain_description = self.DOMAIN_DESCRIPTIONS.get(domain, "General software engineering")
        formatted_prompt = self.prompt_template.format(
            domain=domain,
            domain_description=domain_description,
            prompt=prompt
        )

        # Create LLM request
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=formatted_prompt)]
        )

        # Invoke teacher model
        logger.debug(f"Calling teacher model (attempt with tenacity retry)")
        response_data = self.llm_adapter.invoke(request)

        # Validate response
        if not response_data.get("text_response"):
            raise ValueError("Teacher model returned empty text_response")

        return response_data

    def _write_response_to_file(
        self,
        prompt: str,
        response: Dict[str, Any],
        domain: str,
        output_dir: str,
        seed_prompt: str,
        seed_index: int,
        variation_index: int,
    ):
        """
        Write response to hierarchical JSONL file structure.

        File structure: output_dir/domain/sequence_slug_hash/sequence_slug_hash.jsonl

        Args:
            prompt: The prompt that was sent
            response: The teacher model response
            domain: Current domain
            output_dir: Root output directory
            seed_prompt: Original seed prompt
            seed_index: Index of seed in domain
            variation_index: Which variation of the seed (0-indexed)
        """
        # Generate file path components
        slug = self._generate_slug(seed_prompt)
        hash_suffix = self._generate_hash(seed_prompt)[:4]
        sequence = f"{seed_index:04d}"
        dirname = f"{sequence}_{slug}_{hash_suffix}"
        filename = f"{sequence}_{slug}_{hash_suffix}.jsonl"

        # Full path: output_dir/domain/dirname/filename
        file_path = Path(output_dir) / domain / dirname / filename

        # Create JSONL entry
        entry = {
            "prompt": prompt,
            "thinking": response.get("thinking_stages"),  # null if not present
            "completion": response.get("text_response"),
            "model": self.llm_adapter.model_name or "unknown",
            "domain": domain,
            "timestamp": time.time(),
            "metadata": {
                "seed_prompt": seed_prompt,
                "seed_index": seed_index,
                "variation_index": variation_index,
                "expansion_model": "unknown",  # TODO: Get from config if available
            }
        }

        # Write via MCP FileSpecialist (atomic append)
        # Note: This is a direct file write in specialist code, not MCP call
        # TODO: Replace with MCP call when FileSpecialist append_to_file is wired
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

        logger.info(f"Wrote response to {file_path}")

    def _write_error_to_file(
        self,
        prompt: str,
        error: str,
        domain: str,
        output_dir: str,
    ):
        """
        Write error to error log file.

        File path: output_dir/domain/errors.jsonl

        Args:
            prompt: The prompt that failed
            error: Error message
            domain: Current domain
            output_dir: Root output directory
        """
        file_path = Path(output_dir) / domain / "errors.jsonl"

        # Create error entry
        entry = {
            "prompt": prompt,
            "error": error,
            "timestamp": time.time(),
            "model": self.llm_adapter.model_name or "unknown",
            "retry_count": self.retry_attempts,
        }

        # Write via direct file I/O
        # TODO: Replace with MCP call when available
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

        logger.warning(f"Wrote error to {file_path}")

    def _generate_slug(self, text: str, max_length: int = 30) -> str:
        """
        Generate URL-safe slug from text.

        Args:
            text: Source text
            max_length: Maximum slug length

        Returns:
            URL-safe slug (lowercase, hyphens, alphanumeric)
        """
        # Convert to lowercase
        slug = text.lower()

        # Remove non-alphanumeric characters (keep spaces)
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)

        # Replace spaces/multiple hyphens with single hyphen
        slug = re.sub(r'[\s-]+', '-', slug)

        # Trim to max length
        slug = slug[:max_length]

        # Remove leading/trailing hyphens
        slug = slug.strip('-')

        return slug or "untitled"

    def _generate_hash(self, text: str) -> str:
        """
        Generate hash for uniqueness.

        Args:
            text: Source text

        Returns:
            Hex hash string
        """
        return hashlib.md5(text.encode()).hexdigest()

    def _get_seed_index_for_prompt(
        self,
        collection_index: int,
        num_seeds: int,
        variations_per_seed: int
    ) -> tuple[int, int]:
        """
        Calculate seed index and variation index for a given collection index.

        Args:
            collection_index: Current position in expanded_prompts list
            num_seeds: Total number of seed prompts
            variations_per_seed: Variations generated per seed

        Returns:
            (seed_index, variation_index) tuple
        """
        seed_index = collection_index // variations_per_seed
        variation_index = collection_index % variations_per_seed
        return seed_index, variation_index
