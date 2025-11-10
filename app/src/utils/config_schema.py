# app/src/utils/config_schema.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Literal, Union, Optional, Any


class LLMProviderConfig(BaseModel):
    """Defines the configuration for a single LLM provider instance."""

    model_config = ConfigDict(extra="allow")  # Allow provider-specific fields (e.g., session_cookies, rate_limit_delay)

    type: Literal["gemini", "lmstudio", "ollama", "gemini_webui"] = Field( # The adapter type
        ..., description="The type of the LLM provider implementation to use."
    )
    api_identifier: Optional[str] = Field(
        None, description="The specific model identifier for the provider's API (e.g., 'gemini-1.5-pro' or 'local-model/nous-hermes-gguf'). Not required for all provider types."
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="A dictionary of parameters to pass to the model's API (e.g., max_tokens, temperature)."
    )


class WorkflowConfig(BaseModel):
    """Defines the graph's execution flow."""

    entry_point: str = Field(
        ..., description="The name of the specialist that serves as the entry point for the graph."
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


class RootConfig(BaseModel):
    """The root model for the entire config.yaml file."""

    workflow: WorkflowConfig
    specialists: Dict[str, SpecialistConfig]


class UserSettings(BaseModel):
    """The root model for the user_settings.yaml file."""

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