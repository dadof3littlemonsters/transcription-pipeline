from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass
class ProcessingStage:
    """Defines a single stage in a multi-stage processing pipeline."""
    name: str
    prompt_file: str  # Path relative to config/prompts/
    system_message: str
    model: str = "deepseek-chat"
    provider: str = ""  # "deepseek", "openrouter", "openai", "zai", or "" for auto-detect
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120
    requires_previous: bool = False  # Whether this stage needs previous stage output
    save_intermediate: bool = True  # Whether to save this stage's output
    filename_suffix: str = ""  # Suffix for intermediate file (e.g., "_filtered", "_clean")
    
    # Resolved prompt template content (loaded at runtime)
    prompt_template: str = field(default="", init=False)

@dataclass
class SyncthingConfig:
    """Syncthing output routing configuration for a profile."""
    share_folder: str = ""   # Syncthing folder ID
    subfolder: str = ""      # Optional subfolder within the share

@dataclass
class NotificationConfig:
    """Notification configuration for a profile."""
    ntfy_topic: str = ""
    ntfy_url: str = ""  # Defaults to https://ntfy.sh
    discord_webhook: str = ""
    pushover_user: str = ""
    pushover_token: str = ""


@dataclass
class DegreeProfile:
    """Defines a degree-specific processing profile."""
    name: str
    stages: List[ProcessingStage]
    skip_diarization: bool = False
    description: str = ""
    syncthing: Optional[SyncthingConfig] = None
    notifications: Optional[NotificationConfig] = None
    priority: int = 5  # Default priority 1=highest, 10=lowest
