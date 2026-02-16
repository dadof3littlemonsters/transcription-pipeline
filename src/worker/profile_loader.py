import yaml
import logging
from pathlib import Path
from typing import Dict, Optional, Any

from .types import DegreeProfile, ProcessingStage, SyncthingConfig, NotificationConfig

logger = logging.getLogger(__name__)

class ProfileLoader:
    """Loads degree profiles and prompt templates from configuration files."""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.profiles_dir = config_dir / "profiles"
        self.prompts_dir = config_dir / "prompts"
        self._profiles: Dict[str, DegreeProfile] = {}
        self._folder_map: Dict[str, str] = {}
        
        # Load immediately
        self.reload()
        
    def reload(self):
        """Reload all profiles and configuration."""
        logger.info("Reloading profiles and configuration...")
        # BUG FIX: Clear existing profiles before reload so deleted profiles
        # don't persist as stale entries
        self._profiles = {}
        self._load_folder_map()
        self._load_profiles()
        
    def _load_folder_map(self):
        """Load folder to profile mapping."""
        map_file = self.profiles_dir / "folder_map.yaml"
        if map_file.exists():
            try:
                with open(map_file, 'r') as f:
                    data = yaml.safe_load(f)
                    self._folder_map = data.get("folder_map", {})
                    logger.info(f"Loaded {len(self._folder_map)} folder mappings")
            except Exception as e:
                logger.error(f"Failed to load folder map: {e}")
        else:
            logger.warning(f"Folder map file not found: {map_file}")
            
    def _load_profiles(self):
        """Load all profile YAML files."""
        if not self.profiles_dir.exists():
            logger.warning(f"Profiles directory not found: {self.profiles_dir}")
            return
            
        for yaml_file in self.profiles_dir.glob("*.yaml"):
            if yaml_file.name == "folder_map.yaml":
                continue
                
            try:
                # BUG FIX: Use filename stem as profile ID, not the YAML 'name' field.
                # The API routes look up profiles by ID (e.g. "data_protection"),
                # but the old code stored them under the display name (e.g. "Data Protection").
                # This caused get_profile(request.id) to return None after create+reload.
                profile_id = yaml_file.stem
                
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                    self._parse_profile(data, profile_id)
            except Exception as e:
                logger.error(f"Failed to load profile {yaml_file.name}: {e}")
                
    def _parse_profile(self, data: Dict[str, Any], profile_id: str):
        """Parse a single profile dictionary into a DegreeProfile object."""
        profile_name = data.get("name")
        if not profile_name:
            logger.warning("Profile missing 'name' field")
            return
            
        stages_data = data.get("stages", [])
        stages = []
        
        for stage_data in stages_data:
            stage = ProcessingStage(
                name=stage_data.get("name"),
                prompt_file=stage_data.get("prompt_file"),
                system_message=stage_data.get("system_message", ""),
                model=stage_data.get("model", "deepseek-chat"),
                provider=stage_data.get("provider", ""),
                temperature=stage_data.get("temperature", 0.3),
                max_tokens=stage_data.get("max_tokens", 4096),
                timeout=stage_data.get("timeout", 120),
                requires_previous=stage_data.get("requires_previous", False),
                save_intermediate=stage_data.get("save_intermediate", True),
                filename_suffix=stage_data.get("filename_suffix", "")
            )
            
            # Load prompt content
            self._load_prompt_content(stage)
            stages.append(stage)
            
        # Parse syncthing config
        syncthing_data = data.get("syncthing")
        syncthing = None
        if syncthing_data and isinstance(syncthing_data, dict):
            # BUG FIX: Accept both 'share_folder' and 'folder' keys for robustness.
            # The create_profile route writes 'share_folder' but users might use 'folder'.
            syncthing = SyncthingConfig(
                share_folder=syncthing_data.get("share_folder", syncthing_data.get("folder", "")),
                subfolder=syncthing_data.get("subfolder", ""),
            )
        
        # Parse notification config
        notif_data = data.get("notifications")
        notifications = None
        if notif_data and isinstance(notif_data, dict):
            notifications = NotificationConfig(
                ntfy_topic=notif_data.get("ntfy_topic", ""),
                ntfy_url=notif_data.get("ntfy_url", ""),
                discord_webhook=notif_data.get("discord_webhook", ""),
                pushover_user=notif_data.get("pushover_user", ""),
                pushover_token=notif_data.get("pushover_token", ""),
            )
        
        profile = DegreeProfile(
            name=profile_name,
            stages=stages,
            skip_diarization=data.get("skip_diarization", False),
            description=data.get("description", ""),
            syncthing=syncthing,
            notifications=notifications,
            priority=data.get("priority", 5),
        )
        
        # BUG FIX: Key by profile_id (filename stem) not by YAML display name
        self._profiles[profile_id] = profile
        logger.info(f"Loaded profile: {profile_id} ({profile_name}) with {len(stages)} stages")
        
    def _load_prompt_content(self, stage: ProcessingStage):
        """Load the prompt template content from file."""
        prompt_path = self.prompts_dir / stage.prompt_file
        if prompt_path.exists():
            try:
                stage.prompt_template = prompt_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to read prompt file {prompt_path}: {e}")
                stage.prompt_template = f"ERROR: Could not load prompt from {stage.prompt_file}"
        else:
            logger.error(f"Prompt file not found: {prompt_path}")
            stage.prompt_template = f"ERROR: Prompt file not found: {stage.prompt_file}"

    def get_profile(self, profile_id: str) -> Optional[DegreeProfile]:
        """Get a profile by ID (filename stem)."""
        return self._profiles.get(profile_id)
        
    def get_profile_for_folder(self, folder_name: str) -> Optional[str]:
        """Get the profile name for a given folder."""
        return self._folder_map.get(folder_name.lower())
        
    def should_skip_diarization(self, profile_name: str) -> bool:
        """Check if diarization should be skipped for a profile."""
        profile = self.get_profile(profile_name)
        if profile:
            return profile.skip_diarization
        return False

    def add_folder_mapping(self, folder_name: str, profile_id: str):
        """Add a folder → profile mapping and persist to disk.
        
        Args:
            folder_name: The inbound folder name (e.g., 'data_protection')
            profile_id: The profile ID to map to
        """
        self._folder_map[folder_name.lower()] = profile_id
        self._save_folder_map()
        logger.info(f"Added folder mapping: {folder_name} → {profile_id}")

    def remove_folder_mapping(self, folder_name: str):
        """Remove a folder → profile mapping and persist to disk.
        
        Args:
            folder_name: The inbound folder name to remove
        """
        key = folder_name.lower()
        if key in self._folder_map:
            del self._folder_map[key]
            self._save_folder_map()
            logger.info(f"Removed folder mapping: {folder_name}")

    def _save_folder_map(self):
        """Write the current folder_map back to disk."""
        map_file = self.profiles_dir / "folder_map.yaml"
        try:
            data = {"folder_map": dict(self._folder_map)}
            with open(map_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to save folder map: {e}")

    def get_folder_map(self) -> dict:
        """Return the current folder → profile mapping."""
        return dict(self._folder_map)
