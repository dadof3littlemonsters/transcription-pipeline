# Backend Task: Add Multi-Provider LLM Support (OpenRouter + OpenAI)

## Overview

The transcription pipeline currently hardcodes DeepSeek as the only LLM provider for processing stages. I want to add support for multiple providers so I can test different models on the same pipeline. The key providers are:

1. **OpenRouter** (priority — single API, hundreds of models including Claude, GPT-4o, Gemini, Llama, Qwen, Mistral, etc.)
2. **OpenAI** (for Whisper transcription as an alternative to Groq, plus GPT models for processing)
3. **DeepSeek** (keep as default, already working)

All three use OpenAI-compatible chat completion APIs, so the changes are mostly about routing to the right base URL with the right API key based on the model string.

## Current Architecture

### Formatter (`src/worker/formatter.py`)
- `DeepSeekFormatter` — has a `_call_api()` method that POSTs to `{base_url}/chat/completions`
- `MultiStageFormatter` extends it — calls `_call_api()` per stage, passing `stage.model`, `stage.temperature`, etc.
- Currently hardcodes DeepSeek's base URL and API key

### Profile YAML stages
```yaml
stages:
  - name: "Clean & Structure"
    model: "deepseek-chat"      # Currently just a model name
    temperature: 0.3
    max_tokens: 4096
```

### Processor (`src/worker/processor.py`)
- `_initialize_clients()` — creates a `DeepSeekFormatter` with `DEEPSEEK_API_KEY`
- `_get_multi_stage_formatter()` — creates a `MultiStageFormatter` with `DEEPSEEK_API_KEY`

### Types (`src/worker/types.py`)
```python
@dataclass
class ProcessingStage:
    name: str
    prompt_file: str
    system_message: str
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120
    requires_previous: bool = False
    save_intermediate: bool = True
    filename_suffix: str = ""
```

## What I Need

### 1. Add a `provider` field to ProcessingStage

In `src/worker/types.py`, add an optional `provider` field:

```python
@dataclass
class ProcessingStage:
    name: str
    prompt_file: str
    system_message: str
    model: str = "deepseek-chat"
    provider: str = "deepseek"  # NEW: "deepseek", "openrouter", "openai"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120
    requires_previous: bool = False
    save_intermediate: bool = True
    filename_suffix: str = ""
    prompt_template: str = field(default="", init=False)
```

### 2. Create a provider resolver

Create a new file `src/worker/providers.py`:

```python
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
    "claude": "openrouter",         # Claude via OpenRouter (easier than native Anthropic API)
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
```

### 3. Refactor the Formatter to be provider-agnostic

In `src/worker/formatter.py`, the `_call_api` method needs to accept a provider config instead of always using the instance's base_url and api_key. The cleanest approach:

**In `DeepSeekFormatter.__init__`**: Keep it mostly the same but rename to something more generic, or just keep the name (it's fine, it's the default).

**In `DeepSeekFormatter._call_api`**: Add optional `base_url` and `api_key` overrides:

```python
def _call_api(
    self, 
    prompt: str, 
    system_message: str = "You are a helpful assistant.",
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 120,
    provider_config: Optional['ProviderConfig'] = None,  # NEW
) -> str:
    # Use provider_config if given, otherwise fall back to instance defaults
    api_key = provider_config.api_key if provider_config else self.api_key
    base_url = provider_config.base_url if provider_config else self.base_url
    
    if not api_key:
        raise FormattingError("No API key available for this provider")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # OpenRouter requires extra headers
    if provider_config and provider_config.name == "openrouter":
        headers["HTTP-Referer"] = "https://transcribe.delboysden.uk"
        headers["X-Title"] = "Transcription Pipeline"
    
    # ... rest of the method stays the same, using base_url variable
```

**In `MultiStageFormatter.process_transcript`**: For each stage, resolve the provider and pass it:

```python
from .providers import resolve_provider

# Inside the stage loop:
for i, stage in enumerate(self.stages, 1):
    # Resolve provider for this stage's model
    provider_config = resolve_provider(stage.model, getattr(stage, 'provider', None))
    
    # ... prepare prompt as before ...
    
    output = self._call_api(
        prompt=prompt,
        system_message=stage.system_message,
        model=stage.model,
        temperature=stage.temperature,
        max_tokens=stage.max_tokens,
        timeout=stage.timeout,
        provider_config=provider_config,  # NEW
    )
```

### 4. Update the Processor

In `src/worker/processor.py`:

**`_initialize_clients`**: Keep the DeepSeek formatter as the default for standard processing. Also log which providers are available:

```python
from .providers import get_configured_providers

def _initialize_clients(self):
    # ... existing Groq, Pyannote, DeepSeek init ...
    
    # Log available providers
    providers = get_configured_providers()
    for name, configured in providers.items():
        if configured:
            logger.info(f"Provider available: {name}")
        else:
            logger.info(f"Provider not configured: {name}")
```

**`_get_multi_stage_formatter`**: Instead of requiring DEEPSEEK_API_KEY specifically, just check that at least one LLM provider is configured:

```python
def _get_multi_stage_formatter(self, profile_id: str) -> MultiStageFormatter:
    profile = self.profile_loader.get_profile(profile_id)
    if not profile:
        raise ValueError(f"Profile not found: {profile_id}")
    
    # Use DeepSeek key as default, but the MultiStageFormatter
    # will resolve per-stage providers automatically
    from .providers import get_configured_providers
    providers = get_configured_providers()
    any_configured = any(providers.values())
    
    if not any_configured:
        raise RuntimeError("No LLM providers configured. Set at least one API key.")
    
    # Pass DeepSeek key as the default (for backward compatibility)
    # Individual stages will override via provider resolution
    default_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
    
    return MultiStageFormatter(
        api_key=default_key,
        prompts_dir=self.config_dir / "prompts",
        profile=profile
    )
```

### 5. Update ProfileLoader

In `src/worker/profile_loader.py`, parse the new `provider` field from YAML:

```python
stage = ProcessingStage(
    name=stage_data.get("name"),
    prompt_file=stage_data.get("prompt_file"),
    system_message=stage_data.get("system_message", ""),
    model=stage_data.get("model", "deepseek-chat"),
    provider=stage_data.get("provider", ""),  # NEW - empty string means auto-detect
    temperature=stage_data.get("temperature", 0.3),
    # ... rest stays the same
)
```

### 6. Update API health/readiness checks

In `src/api/dependencies.py`, add the new API keys:

```python
def validate_api_keys() -> Dict[str, bool]:
    """Check which API keys are configured."""
    return {
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "deepseek": bool(os.getenv("DEEPSEEK_API_KEY")),
        "huggingface": bool(os.getenv("HUGGINGFACE_TOKEN")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "zai": bool(os.getenv("ZAI_API_KEY")),
    }
```

**IMPORTANT**: Update `require_api_keys()` so it doesn't require ALL keys — it should only require Groq (for transcription) and at least one LLM provider:

```python
def require_api_keys():
    """Dependency that raises error if minimum required API keys are missing."""
    keys = validate_api_keys()
    
    # Must have Groq for transcription
    if not keys["groq"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable: GROQ_API_KEY required for transcription"
        )
    
    # Must have at least one LLM provider
    llm_providers = ["deepseek", "openrouter", "openai", "zai"]
    has_llm = any(keys.get(p) for p in llm_providers)
    if not has_llm:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable: At least one LLM API key required (DEEPSEEK, OPENROUTER, OPENAI, or ZAI)"
        )
```

### 7. Update docker-compose.yml

Add the new environment variables to BOTH `app` and `worker` services:

```yaml
environment:
  # Existing
  - GROQ_API_KEY=${GROQ_API_KEY:-}
  - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
  - HUGGINGFACE_TOKEN=${HUGGINGFACE_TOKEN:-}
  # New providers
  - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
  - OPENAI_API_KEY=${OPENAI_API_KEY:-}
  - ZAI_API_KEY=${ZAI_API_KEY:-}
```

### 8. Update .env file

Add placeholders (don't commit actual keys):

```
OPENROUTER_API_KEY=your-openrouter-key-here
OPENAI_API_KEY=your-openai-key-here
ZAI_API_KEY=your-zai-key-here
```

### 9. Update the profiles API schema

In `src/api/schemas.py`, add `provider` to `ProfileStageInfo` so the frontend can see it:

```python
class ProfileStageInfo(BaseModel):
    name: str
    model: str
    provider: Optional[str] = None  # NEW
    description: Optional[str] = None
```

And in the profiles route where `ProfileStageInfo` objects are built, include the provider:

```python
stages = [
    ProfileStageInfo(
        name=stage.name,
        model=stage.model,
        provider=getattr(stage, 'provider', None) or "auto",  # NEW
        description=f"Stage {i+1}: {stage.name}",
    )
    for i, stage in enumerate(profile.stages)
]
```

Also add `provider` to `ProfileCreateStage` if that schema exists from the previous backend task:

```python
class ProfileCreateStage(BaseModel):
    name: str
    model: str = "deepseek-chat"
    provider: str = ""  # NEW - empty = auto-detect
    temperature: float = 0.3
    # ... etc
```

And make sure the profile creation endpoint writes `provider` into the YAML.

## How It Works After Implementation

**Existing profiles** continue to work exactly as before — DeepSeek is the default.

**New profiles** can specify a provider per stage in the YAML:
```yaml
stages:
  - name: "Clean"
    model: "deepseek-chat"
    provider: "deepseek"      # Explicit
  - name: "Analysis"
    model: "anthropic/claude-sonnet-4"
    provider: "openrouter"    # Explicit
  - name: "Summary"
    model: "gpt-4o"
    # provider not set — auto-detected as "openai" from model name
```

**Auto-detection** means you can just put a model name and the system figures out which provider to use. If auto-detection fails, it falls back to OpenRouter (which supports almost everything).

**The Control Hub** already has a model dropdown in the Create Profile modal. I'll update the frontend separately to also include a provider dropdown — but even without that, auto-detection means profiles created from the UI will work as long as the model name is recognisable.

## Files Summary

| File | Action |
|------|--------|
| `src/worker/types.py` | Add `provider` field to `ProcessingStage` |
| `src/worker/providers.py` | **NEW FILE** — provider registry and resolver |
| `src/worker/formatter.py` | Add `provider_config` param to `_call_api`, use it in `MultiStageFormatter` |
| `src/worker/processor.py` | Update `_initialize_clients` and `_get_multi_stage_formatter` |
| `src/worker/profile_loader.py` | Parse `provider` from YAML |
| `src/api/dependencies.py` | Add new keys to `validate_api_keys`, fix `require_api_keys` |
| `src/api/schemas.py` | Add `provider` to `ProfileStageInfo` and `ProfileCreateStage` |
| `src/api/routes/profiles.py` | Include `provider` when building stage info responses and writing YAML |
| `docker-compose.yml` | Add `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ZAI_API_KEY` env vars |
| `.env` | Add placeholder keys |

## Testing

After implementation:
1. Set `OPENROUTER_API_KEY` in your `.env`
2. Rebuild: `docker compose up -d --build`
3. Check health: `curl https://transcribe.delboysden.uk/ready` — should show openrouter as configured
4. Create a test profile via the Control Hub with model `anthropic/claude-sonnet-4` (provider will auto-detect to openrouter)
5. Upload a short audio file and verify it processes through OpenRouter

Don't rebuild until I've reviewed the changes.
