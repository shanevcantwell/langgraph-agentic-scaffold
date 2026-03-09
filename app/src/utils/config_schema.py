# app/src/utils/config_schema.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Literal, Union, Optional, Any, List


class LLMProviderConfig(BaseModel):
    """Defines the configuration for a single LLM provider instance."""

    model_config = ConfigDict(extra="allow")  # Allow provider-specific fields (e.g., session_cookies, rate_limit_delay)

    type: Literal["gemini", "local", "local_pool", "lmstudio", "lmstudio_pool", "llama_server", "llama_server_pool", "ollama", "gemini_webui"] = Field( # The adapter type
        ..., description="The type of the LLM provider implementation to use."
    )
    api_identifier: Optional[str] = Field(
        None, description="The specific model identifier for the provider's API (e.g., 'gemini-1.5-pro' or 'local-model/nous-hermes-gguf'). Not required for all provider types."
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="A dictionary of parameters to pass to the model's API (e.g., max_tokens, temperature)."
    )


class CheckpointingConfig(BaseModel):
    """ADR-CORE-018: Configuration for HitL interrupt/resume checkpointing."""

    enabled: bool = Field(
        default=False,
        description="Enable graph state persistence for interrupt/resume workflows."
    )
    backend: Literal["sqlite", "postgres"] = Field(
        default="sqlite",
        description="Checkpointing backend: 'sqlite' for dev, 'postgres' for production."
    )
    sqlite_path: Optional[str] = Field(
        default="./data/checkpoints.db",
        description="Path to SQLite database file (only used when backend='sqlite')."
    )
    postgres_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection URL (only used when backend='postgres'). Can use ${DATABASE_URL} syntax."
    )


class ReactConfig(BaseModel):
    """
    ADR-CORE-051: Per-specialist ReAct configuration.

    Enables iterative tool use (LLM → tool → LLM → tool → ... → done) for specialists
    that need to perform multiple tool calls within a single execution.

    Example:
        react:
          enabled: true
          max_iterations: 10
          stop_on_error: false
    """

    enabled: bool = Field(
        default=False,
        description="Enable ReAct-style iterative tool use for this specialist."
    )
    max_iterations: Optional[int] = Field(
        default=None,
        description="Maximum number of LLM calls before stopping. Uses global default if not specified."
    )
    stop_on_error: Optional[bool] = Field(
        default=None,
        description="If true, halt on first tool error. If false, report error to LLM. Uses global default if not specified."
    )


class ReactDefaultsConfig(BaseModel):
    """
    ADR-CORE-051: Global defaults for ReAct configuration.

    These defaults apply to any specialist with react.enabled=true that doesn't
    specify its own max_iterations or stop_on_error values.

    Example:
        react:
          defaults:
            max_iterations: 10
            stop_on_error: false
    """

    max_iterations: int = Field(
        default=10,
        description="Default maximum iterations for ReAct loops."
    )
    stop_on_error: bool = Field(
        default=False,
        description="Default error handling: halt vs report to LLM."
    )


class ReactRootConfig(BaseModel):
    """ADR-CORE-051: Root-level ReAct configuration with global defaults."""

    defaults: Optional[ReactDefaultsConfig] = Field(
        default=None,
        description="Global defaults for specialist ReAct configurations."
    )


class WorkflowConfig(BaseModel):
    """Defines the graph's execution flow."""

    entry_point: str = Field(
        ..., description="The name of the specialist that serves as the entry point for the graph."
    )
    max_loop_cycles: int = Field(
        default=3, description="The number of times a short sequence of specialists can repeat before the workflow is halted."
    )
    recursion_limit: int = Field(
        default=40, description="The maximum number of steps the graph can take before halting."
    )
    critical_specialists: list[str] = Field(
        default_factory=list, description="A list of specialists that are considered essential for the application to function."
    )
    stabilization_actions: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="Maps invariant violations to stabilization actions (e.g., 'max_turn_count_exceeded': 'HALT')."
    )


class BaseSpecialistConfig(BaseModel):
    """
    A base model for specialist configurations.
    It allows for extra, specialist-specific parameters (e.g., 'root_dir' for file_specialist)
    which will be passed into the specialist's constructor.
    """

    model_config = ConfigDict(extra="allow")
    description: str = Field(
        ...,
        description="A clear, concise description of the specialist's capabilities, used by the router for decision-making.",
    )

    # ADR-CORE-051: External MCP tool permissions
    # Maps service names to allowed tools: {"filesystem": ["read_file", "write_file"]}
    # Use "*" for wildcard access: {"filesystem": "*"}
    tools: Optional[Dict[str, Union[List[str], str]]] = Field(
        default=None,
        description="External MCP tool permissions. Maps service name to tool list or '*' for all tools."
    )

    # ADR-CORE-051: ReAct configuration for iterative tool use
    react: Optional[ReactConfig] = Field(
        default=None,
        description="ReAct configuration for iterative tool use loops."
    )

    # ADR-CORE-053: Config-driven specialist menu exclusion
    excluded_from: Optional[List[str]] = Field(
        default=None,
        description="List of specialist names whose menus should NOT include this specialist."
    )


class LLMSpecialistConfig(BaseSpecialistConfig):
    """Configuration for a specialist that uses a Large Language Model."""

    type: Literal["llm"]
    prompt_file: str = Field(
        ...,
        description="The filename of the markdown prompt for this specialist, located in the `app/prompts` directory.",
    )


class ProceduralSpecialistConfig(BaseSpecialistConfig):
    """Configuration for a specialist that executes deterministic Python code without an LLM."""

    type: Literal["procedural"]


class HybridSpecialistConfig(BaseSpecialistConfig):
    """Configuration for a specialist that uses an LLM for planning but executes code procedurally."""

    type: Literal["hybrid"]
    prompt_file: Optional[str] = Field(
        None,
        description="The optional filename of a markdown prompt for this specialist, located in the `app/prompts` directory.",
    )


# A discriminated union to handle the different types of specialists.
# Pydantic will use the 'type' field to determine which model to use for validation.
SpecialistConfig = Union[LLMSpecialistConfig, ProceduralSpecialistConfig, HybridSpecialistConfig]


class ExternalMcpServiceConfig(BaseModel):
    """
    Configuration for a single external MCP service (Docker container, Node.js server, etc.).

    Supports two connection modes (ADR-CORE-027):
    1. container_name mode: Connect to running container via docker exec
    2. command/args mode: Launch subprocess directly

    Example (container_name mode):
        surf:
          enabled: true
          container_name: "surf-mcp"  # Uses: docker exec -i {name} {entrypoint}
          entrypoint: "surf-mcp"      # Optional, defaults to container_name

    Example (command/args mode):
        filesystem:
          enabled: true
          command: "docker"
          args: ["run", "-i", "--rm", "mcp/filesystem"]
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False, description="Whether this external MCP service is enabled.")
    required: bool = Field(default=False, description="If true, application fails to start if service unavailable.")

    # Connection mode 1: container_name (docker exec to running container)
    container_name: Optional[str] = Field(
        default=None,
        description="Container name for docker exec mode. Uses: docker exec -i {name} {entrypoint}"
    )
    entrypoint: Optional[str] = Field(
        default=None,
        description="Entrypoint command for container_name mode. Defaults to container_name if not specified."
    )

    # Connection mode 2: command/args (direct subprocess)
    command: Optional[str] = Field(default=None, description="Executable command (e.g., 'docker', 'npx').")
    args: list[str] = Field(default_factory=list, description="Command arguments.")

    # Common settings
    timeout_ms: Optional[int] = Field(default=30000, description="Timeout in milliseconds for tool calls.")


class ExternalMcpConfig(BaseModel):
    """Configuration for external MCP services (Docker containers, etc.)."""

    enabled: bool = Field(default=False, description="Global enable/disable for all external MCP services.")
    tracing_enabled: bool = Field(default=True, description="Toggle LangSmith trace spans for external MCP calls.")
    services: Dict[str, ExternalMcpServiceConfig] = Field(
        default_factory=dict, description="Configuration for individual external MCP services."
    )


class McpConfig(BaseModel):
    """Configuration for the MCP (Message-Centric Protocol) system."""

    tracing_enabled: bool = Field(default=True, description="Toggle LangSmith trace spans for internal MCP calls.")
    timeout_seconds: int = Field(default=5, description="Maximum execution time per MCP call.")
    external_mcp: Optional[ExternalMcpConfig] = Field(
        default=None, description="Configuration for external MCP services (Docker containers, etc.)."
    )


class RootConfig(BaseModel):
    """The root model for the entire config.yaml file."""

    workflow: WorkflowConfig
    specialists: Dict[str, SpecialistConfig]
    mcp: Optional[McpConfig] = Field(default=None, description="MCP configuration for internal and external services.")
    # ADR-CORE-051: Global ReAct defaults
    react: Optional[ReactRootConfig] = Field(
        default=None,
        description="Global defaults for specialist ReAct configurations."
    )


class UserSettings(BaseModel):
    """The root model for the user_settings.yaml file."""

    # UI Configuration
    ui_module: Optional[str] = Field(
        default="gradio_app",
        description="UI module to load (filename without .py extension). Available: 'gradio_app' (standard), 'gradio_lassie' (retro terminal)."
    )

    # This is now the authoritative source for defining and naming LLM provider configurations.
    llm_providers: Optional[Dict[str, LLMProviderConfig]] = Field(
        default_factory=dict,
        description="Defines the user's named LLM provider configurations (e.g., 'my_fast_model', 'my_strong_model')."
    )

    specialist_model_bindings: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Maps a specialist name to one of the llm_providers defined above.",
    )
    default_llm_config: Optional[str] = Field(
        None,
        description="The default llm_provider key to use for any LLM specialist not explicitly bound. Must exist in llm_providers.",
    )

    # ADR-CORE-018: Checkpointing configuration for HitL workflows
    checkpointing: Optional[CheckpointingConfig] = Field(
        default=None,
        description="Configuration for graph state persistence (interrupt/resume workflows)."
    )

    # Global LLM settings (Issue #16)
    max_image_size_mb: Optional[int] = Field(
        default=10,
        description="Maximum image size in MB (base64 encoded). Rejects uploads exceeding this limit."
    )