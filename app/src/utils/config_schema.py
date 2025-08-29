# app/src/utils/config_schema.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Literal, Union, Optional, Any


class LLMProviderConfig(BaseModel):
    """Defines the configuration for a single LLM provider instance."""

    type: Literal["gemini", "lmstudio", "ollama"] = Field(
        ..., description="The type of the LLM provider implementation to use."
    )
    api_identifier: str = Field(
        ...,
        description="The specific model identifier for the provider's API (e.g., 'gemini-1.5-pro' or 'local-model/nous-hermes-gguf').",
    )
    context_window: Optional[int] = Field(
        None, description="The total context window size of the model (input + output)."
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
    external_llm_provider_binding: Optional[str] = Field(
        None,
        description="For procedural specialists that wrap an external library which requires its own LLM, this key binds it to an llm_provider from config.yaml."
    )


# A discriminated union to handle the different types of specialists.
# Pydantic will use the 'type' field to determine which model to use for validation.
SpecialistConfig = Union[LLMSpecialistConfig, ProceduralSpecialistConfig]


class RootConfig(BaseModel):
    """The root model for the entire config.yaml file."""

    llm_providers: Dict[str, LLMProviderConfig]
    workflow: WorkflowConfig
    specialists: Dict[str, SpecialistConfig]


class UserSettings(BaseModel):
    """The root model for the user_settings.yaml file."""

    specialist_model_bindings: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Maps a specialist name to the key of an llm_provider from config.yaml.",
    )
    default_llm_config: Optional[str] = Field(
        None,
        description="The default llm_provider key to use for any LLM specialist not explicitly bound. Must exist in llm_providers.",
    )