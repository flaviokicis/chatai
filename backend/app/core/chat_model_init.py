"""Enhanced chat model initialization with GPT-5 reasoning support."""

from typing import Any, Literal
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel


def init_chat_model_with_reasoning(
    model: str,
    model_provider: str | None = None,
    reasoning_effort: Literal["minimal", "medium", "high"] | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Initialize a chat model with optional GPT-5 reasoning support.
    
    Args:
        model: Model name (e.g., "gpt-5", "gpt-4", "gemini-2.5-flash")
        model_provider: Provider name (e.g., "openai", "google_genai", "anthropic")
        reasoning_effort: For GPT-5, set reasoning effort ("minimal", "medium", "high")
        **kwargs: Additional model configuration parameters
        
    Returns:
        Initialized chat model
    """
    # For GPT-5 models with reasoning support
    if model.startswith("gpt-5") and reasoning_effort:
        # Add reasoning to model_kwargs for now (until langchain supports it directly)
        model_kwargs = kwargs.get("model_kwargs", {})
        model_kwargs["reasoning"] = {"effort": reasoning_effort}
        kwargs["model_kwargs"] = model_kwargs
    
    return init_chat_model(model, model_provider=model_provider, **kwargs)
