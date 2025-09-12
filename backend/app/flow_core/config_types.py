"""Typed configuration objects for flow parameters and settings.

This module provides typed alternatives to raw dictionaries for flow configuration,
enabling better validation, IDE support, and maintainability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, field_validator


@dataclass(slots=True)
class QuestionConfig:
    """Configuration for a single question in a flow."""

    key: str
    prompt: str
    priority: int = 100
    dependencies: list[str] = field(default_factory=list)

    # Validation options
    required: bool = True
    validation_type: str | None = None  # email, phone, number, etc.
    allowed_values: list[str] | None = None

    # UI hints
    input_type: str = "text"  # text, number, select, multiselect, etc.
    placeholder: str | None = None
    help_text: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.key.strip():
            raise ValueError("Question key cannot be empty")
        if not self.prompt.strip():
            raise ValueError("Question prompt cannot be empty")
        if self.priority < 0:
            raise ValueError("Priority must be non-negative")


@dataclass(slots=True)
class FlowBuildConfig:
    """Configuration for building flows from questions."""

    flow_id: str
    questions: list[QuestionConfig] = field(default_factory=list)

    # Flow metadata
    title: str | None = None
    description: str | None = None
    version: str = "1.0"

    # Behavior settings
    allow_skip: bool = False
    require_all_answers: bool = True
    completion_message: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.flow_id.strip():
            raise ValueError("Flow ID cannot be empty")

        # Validate question keys are unique
        keys = [q.key for q in self.questions]
        if len(keys) != len(set(keys)):
            raise ValueError("Question keys must be unique")


class ProjectStyleConfig(BaseModel):
    """Configuration for project-specific styling and behavior."""

    # Communication style
    tone: str = Field(default="professional", description="Communication tone")
    formality: str = Field(default="formal", description="Level of formality")
    language: str = Field(default="pt-BR", description="Primary language")

    # Response characteristics
    response_length: str = Field(default="medium", description="Preferred response length")
    emoji_usage: str = Field(default="minimal", description="Emoji usage preference")

    # Business context
    business_type: str | None = Field(default=None, description="Type of business")
    target_audience: str | None = Field(default=None, description="Target audience description")

    # Brand voice
    brand_personality: list[str] = Field(default_factory=list, description="Brand personality traits")
    key_values: list[str] = Field(default_factory=list, description="Key brand values")

    # Custom instructions
    custom_instructions: str | None = Field(default=None, description="Additional custom instructions")

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v: str) -> str:
        """Validate tone is from allowed values."""
        allowed_tones = {"professional", "friendly", "casual", "formal", "warm", "authoritative"}
        if v not in allowed_tones:
            raise ValueError(f"Tone must be one of: {', '.join(allowed_tones)}")
        return v

    @field_validator("formality")
    @classmethod
    def validate_formality(cls, v: str) -> str:
        """Validate formality level."""
        allowed_levels = {"very_formal", "formal", "neutral", "informal", "very_informal"}
        if v not in allowed_levels:
            raise ValueError(f"Formality must be one of: {', '.join(allowed_levels)}")
        return v


class LLMConfig(BaseModel):
    """Configuration for LLM behavior and parameters."""

    # Model settings
    model: str = Field(description="LLM model identifier")
    provider: str = Field(description="LLM provider")

    # Generation parameters
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Generation temperature")
    max_tokens: int | None = Field(default=None, ge=1, description="Maximum tokens to generate")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter")

    # Retry and timeout settings
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    timeout_seconds: int = Field(default=30, ge=1, description="Request timeout in seconds")

    # Response preferences
    prefer_structured_output: bool = Field(default=True, description="Prefer structured JSON responses")
    enforce_json_mode: bool = Field(default=False, description="Force JSON mode if supported")


@dataclass(slots=True)
class FlowExecutionConfig:
    """Configuration for flow execution behavior."""

    # Timing settings
    max_processing_time_ms: int = 30000
    message_delay_ms: int = 1000
    typing_simulation: bool = True

    # Error handling
    max_retries: int = 3
    fallback_message: str = "Desculpe, ocorreu um erro. Pode tentar novamente?"

    # Rate limiting
    max_messages_per_minute: int = 60
    max_messages_per_hour: int = 1000

    # Context management
    max_context_length: int = 8000
    context_truncation_strategy: str = "oldest_first"  # oldest_first, summarize, compress

    # Feature flags
    enable_human_handoff: bool = True
    enable_flow_modification: bool = False
    enable_external_actions: bool = True

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.max_processing_time_ms <= 0:
            raise ValueError("Max processing time must be positive")
        if self.max_retries < 0:
            raise ValueError("Max retries must be non-negative")
        if self.max_context_length <= 0:
            raise ValueError("Max context length must be positive")


@dataclass(slots=True)
class ResponseGenerationConfig:
    """Configuration for response generation behavior."""

    # Content preferences
    allowed_values: list[str] | None = None
    is_completion: bool = False
    is_admin: bool = False

    # Context
    agent_custom_instructions: str | None = None
    project_style: ProjectStyleConfig | None = None
    llm_config: LLMConfig | None = None

    # Flow-specific
    available_edges: list[dict[str, Any]] | None = None
    flow_graph: dict[str, Any] | None = None
    current_node_id: str | None = None

    # Additional context
    extra_context: dict[str, Any] = field(default_factory=dict)


