"""
LLM Provider configuration and resolution.

Maps provider names to their base URLs and API key environment variables.
Supports auto-detection of provider from model name.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str

    @property
    def api_key(self) -> Optional[str]:
        return os.getenv(self.api_key_env)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


# Provider registry
PROVIDERS = {
    "deepseek": ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "openrouter": ProviderConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
    "openai": ProviderConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    ),
    "zai": ProviderConfig(
        name="zai",
        base_url="https://api.z.ai/v1",
        api_key_env="ZAI_API_KEY",
    ),
}

# Model-to-provider auto-detection rules
# If a model string contains these prefixes/patterns, route to that provider
MODEL_PROVIDER_HINTS = {
    "deepseek": "deepseek",
    "gpt-": "openai",
    "o1": "openai",
    "o3": "openai",
    "claude": "openrouter",
    "anthropic/": "openrouter",
    "google/": "openrouter",
    "meta-llama/": "openrouter",
    "mistralai/": "openrouter",
    "qwen": "openrouter",
    "gemini": "openrouter",
    "llama": "openrouter",
}


def resolve_provider(model: str, explicit_provider: Optional[str] = None) -> ProviderConfig:
    """
    Resolve which provider to use for a given model.

    Priority:
    1. Explicit provider from profile YAML
    2. Auto-detect from model name
    3. Default to deepseek

    Args:
        model: The model string (e.g. "deepseek-chat", "gpt-4o", "anthropic/claude-sonnet-4")
        explicit_provider: Provider explicitly set in profile YAML

    Returns:
        ProviderConfig for the resolved provider

    Raises:
        ValueError: If resolved provider is not configured (no API key)
    """
    # 1. Explicit provider
    if explicit_provider and explicit_provider in PROVIDERS:
        provider = PROVIDERS[explicit_provider]
        if not provider.is_configured:
            raise ValueError(
                f"Provider '{explicit_provider}' selected but {provider.api_key_env} is not set"
            )
        return provider

    # 2. Auto-detect from model name
    model_lower = model.lower()
    for hint, provider_name in MODEL_PROVIDER_HINTS.items():
        if hint in model_lower:
            provider = PROVIDERS[provider_name]
            if provider.is_configured:
                logger.info(f"Auto-detected provider '{provider_name}' for model '{model}'")
                return provider
            else:
                logger.warning(
                    f"Auto-detected provider '{provider_name}' for model '{model}' "
                    f"but {provider.api_key_env} is not set. Trying fallbacks..."
                )

    # 3. Try OpenRouter as universal fallback (it supports most models)
    openrouter = PROVIDERS["openrouter"]
    if openrouter.is_configured:
        logger.info(f"Using OpenRouter as fallback for model '{model}'")
        return openrouter

    # 4. Default to deepseek
    deepseek = PROVIDERS["deepseek"]
    if deepseek.is_configured:
        return deepseek

    raise ValueError(f"No configured provider found for model '{model}'")


def get_configured_providers() -> dict:
    """Return dict of provider_name -> is_configured for health checks."""
    return {name: config.is_configured for name, config in PROVIDERS.items()}
