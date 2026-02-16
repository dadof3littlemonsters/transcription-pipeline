"""
Profile management API routes.
"""

import re
import yaml
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

from src.api.schemas import (
    ProfileResponse, 
    ProfileDetailResponse, 
    ProfileStageInfo,
    ProfileCreateRequest,
    ProfileCreateStage,
)
from src.api.dependencies import get_profile_loader
from src.worker.profile_loader import ProfileLoader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profiles", tags=["Profiles"])


def _safe_prompt_path(prompts_dir: Path, prompt_file: str) -> Path:
    """Resolve a prompt file path and verify it's within the prompts directory."""
    # Sanitize: no absolute paths, no parent traversal
    if prompt_file.startswith("/") or ".." in prompt_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid prompt_file path: {prompt_file}"
        )
    
    resolved = (prompts_dir / prompt_file).resolve()
    if not str(resolved).startswith(str(prompts_dir.resolve())):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt file path escapes config directory"
        )
    return resolved


def auto_id(name: str) -> str:
    """Generate filename-safe ID from stage name."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


@router.get("", response_model=List[ProfileResponse])
async def list_profiles(
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """List all available profiles."""
    profiles = []
    
    # Get all profile IDs
    for profile_id in profile_loader._profiles.keys():
        profile = profile_loader.get_profile(profile_id)
        if profile:
            has_notif = bool(getattr(profile, 'notifications', None) and (
                profile.notifications.ntfy_topic or
                profile.notifications.discord_webhook or
                profile.notifications.pushover_user
            ))
            profiles.append(ProfileResponse(
                id=profile_id,
                name=profile.name,
                description=getattr(profile, 'description', ''),
                stage_count=len(profile.stages),
                stages=[stage.name for stage in profile.stages],
                syncthing_folder=profile.syncthing.share_folder if profile.syncthing else None,
                syncthing_subfolder=profile.syncthing.subfolder if profile.syncthing else None,
                priority=getattr(profile, 'priority', 5),
                has_notifications=has_notif,
            ))
    
    # Add standard note types (only if not already loaded as a profile)
    standard_types = ["meeting", "supervision", "client", "lecture", "braindump"]
    for note_type in standard_types:
        if note_type not in profile_loader._profiles:
            profiles.append(ProfileResponse(
                id=note_type,
                name=note_type.title(),
                description=f"Standard {note_type} transcription",
                stage_count=1,
                stages=["format"],
            ))
    
    return profiles


@router.post("", response_model=ProfileDetailResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_profile(
    request: Request,
    profile_request: ProfileCreateRequest,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Create a new profile with YAML config and prompt files."""
    
    # 0. Validate profile ID format
    if not re.match(r'^[a-z0-9][a-z0-9_-]{0,63}$', profile_request.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile ID must be lowercase alphanumeric with hyphens/underscores, 1-64 chars, starting with a letter or number"
        )
    
    # 1. Check profile doesn't already exist
    if profile_loader.get_profile(profile_request.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile '{request.id}' already exists"
        )
    
    # 2. Auto-generate prompt_file paths if not provided
    stages_data = []
    for i, stage in enumerate(profile_request.stages):
        if not stage.prompt_file:
            stage.prompt_file = f"{profile_request.id}/stage_{i+1}_{auto_id(stage.name)}.md"
        
        stages_data.append({
            "name": stage.name,
            "prompt_file": stage.prompt_file,
            "system_message": "",  # Empty, content goes in prompt file
            "model": stage.model,
            "provider": stage.provider or "",
            "temperature": stage.temperature,
            "max_tokens": stage.max_tokens,
            "timeout": 120,  # Default timeout
            "requires_previous": stage.requires_previous,
            "save_intermediate": stage.save_intermediate,
            "filename_suffix": stage.filename_suffix,
        })
    
    # 3. Build YAML dict
    yaml_data = {
        "name": profile_request.name,
        "description": profile_request.description or "",
        "skip_diarization": profile_request.skip_diarization,
        "stages": stages_data,
    }
    
    # Priority
    yaml_data["priority"] = profile_request.priority
    
    # Add syncthing config if provided
    if profile_request.syncthing_folder:
        yaml_data["syncthing"] = {
            "share_folder": profile_request.syncthing_folder,
            "subfolder": profile_request.syncthing_subfolder or "",
        }
    
    # Add notification config if provided
    if profile_request.notifications:
        notif = profile_request.notifications
        notif_data = {}
        if notif.ntfy_topic: notif_data["ntfy_topic"] = notif.ntfy_topic
        if notif.ntfy_url: notif_data["ntfy_url"] = notif.ntfy_url
        if notif.discord_webhook: notif_data["discord_webhook"] = notif.discord_webhook
        if notif.pushover_user: notif_data["pushover_user"] = notif.pushover_user
        if notif.pushover_token: notif_data["pushover_token"] = notif.pushover_token
        if notif_data:
            yaml_data["notifications"] = notif_data
    
    # 4. Write YAML to config/profiles/{request.id}.yaml
    # BUG FIX: Use profile_loader.config_dir for path resolution instead of
    # relative Path("config") which depends on the working directory.
    profiles_dir = profile_loader.profiles_dir
    prompts_dir = profile_loader.prompts_dir
    
    profiles_dir.mkdir(parents=True, exist_ok=True)
    profile_yaml_path = profiles_dir / f"{profile_request.id}.yaml"
    
    try:
        with open(profile_yaml_path, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Wrote profile YAML to {profile_yaml_path}")
        
        # 5. Write each stage's prompt_content to config/prompts/{stage.prompt_file}
        written_prompts = []
        try:
            for stage in profile_request.stages:
                prompt_path = _safe_prompt_path(prompts_dir, stage.prompt_file)
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(prompt_path, 'w') as f:
                    f.write(stage.prompt_content)
                
                written_prompts.append(prompt_path)
                logger.info(f"Wrote prompt file: {prompt_path}")
        
        except Exception as e:
            # Clean up prompt files if any write fails
            for prompt_path in written_prompts:
                if prompt_path.exists():
                    prompt_path.unlink()
            
            # Remove YAML file
            if profile_yaml_path.exists():
                profile_yaml_path.unlink()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to write prompt files: {str(e)}"
            )
        
        # 6. Reload profile_loader
        profile_loader.reload()
        
        # 6b. Auto-register inbound folder mapping
        # Maps the profile ID as a folder name so files dropped in
        # uploads/{profile_id}/ get routed to this profile automatically
        profile_loader.add_folder_mapping(profile_request.id, profile_request.id)
        
        # 7. Return the new profile
        profile = profile_loader.get_profile(profile_request.id)
        if not profile:
            logger.error(
                f"Profile created but failed to load. "
                f"profile_request.id='{profile_request.id}', "
                f"available profiles: {list(profile_loader._profiles.keys())}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Profile created but failed to load"
            )
        
        stages = [
            ProfileStageInfo(
                name=stage.name,
                model=stage.model,
                provider=stage.provider or None,
                description=f"Stage {i+1}: {stage.name}",
            )
            for i, stage in enumerate(profile.stages)
        ]
        
        return ProfileDetailResponse(
            id=profile_request.id,
            name=profile.name,
            description=profile.description,
            stages=stages,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create profile: {e}", exc_info=True)
        # Clean up YAML file if it was created
        if profile_yaml_path.exists():
            profile_yaml_path.unlink()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create profile: {str(e)}"
        )


@router.get("/folder-map", response_model=dict)
async def get_folder_map(
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Get the current inbound folder → profile mapping."""
    return {"folder_map": profile_loader.get_folder_map()}


@router.put("/folder-map/{folder_name}")
async def set_folder_mapping(
    folder_name: str,
    body: dict,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Set or update a folder → profile mapping.
    
    Body: {"profile_id": "some_profile"}
    """
    profile_id = body.get("profile_id")
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")
    
    profile_loader.add_folder_mapping(folder_name, profile_id)
    return {"folder": folder_name, "profile_id": profile_id}


@router.delete("/folder-map/{folder_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder_mapping(
    folder_name: str,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Remove a folder → profile mapping."""
    profile_loader.remove_folder_mapping(folder_name)


@router.get("/{profile_id}", response_model=ProfileDetailResponse)
async def get_profile(
    profile_id: str,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Get detailed profile configuration."""
    profile = profile_loader.get_profile(profile_id)
    
    if not profile:
        # Check if it's a standard note type
        standard_types = ["meeting", "supervision", "client", "lecture", "braindump"]
        if profile_id in standard_types:
            return ProfileDetailResponse(
                id=profile_id,
                name=profile_id.title(),
                description=f"Standard {profile_id} transcription with single-stage formatting",
                stages=[ProfileStageInfo(
                    name="format",
                    model="deepseek-chat",
                    description="Format transcript using DeepSeek",
                )],
            )
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found"
        )
    
    # Build stage info
    stages = [
        ProfileStageInfo(
            name=stage.name,
            model=stage.model,
            provider=stage.provider or None,
            description=f"Stage {i+1}: {stage.name}",
        )
        for i, stage in enumerate(profile.stages)
    ]
    
    return ProfileDetailResponse(
        id=profile_id,
        name=profile.name,
        description=profile.description,
        stages=stages,
    )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Delete a profile and its associated files."""
    
    # Prevent deletion of standard types
    standard_types = ["meeting", "supervision", "client", "lecture", "braindump"]
    if profile_id in standard_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete built-in profile '{profile_id}'"
        )
    
    # 1. Check the profile exists
    profile = profile_loader.get_profile(profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_id}' not found"
        )
    
    # 2. Remove the YAML file from config/profiles/
    profile_yaml_path = profile_loader.profiles_dir / f"{profile_id}.yaml"
    
    if profile_yaml_path.exists():
        profile_yaml_path.unlink()
        logger.info(f"Deleted profile YAML: {profile_yaml_path}")
    
    # 3. Remove the prompt directory from config/prompts/{id}/
    prompts_dir = profile_loader.prompts_dir / profile_id
    if prompts_dir.exists() and prompts_dir.is_dir():
        import shutil
        shutil.rmtree(prompts_dir)
        logger.info(f"Deleted prompt directory: {prompts_dir}")
    
    # 4. Reload the ProfileLoader (clears stale entries due to our fix)
    profile_loader.reload()
    
    # 5. Remove inbound folder mapping
    profile_loader.remove_folder_mapping(profile_id)


@router.get("/{profile_id}/prompts/{stage_index}")
async def get_stage_prompt(
    profile_id: str,
    stage_index: int,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Get the prompt content for a specific stage."""
    profile = profile_loader.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if stage_index < 0 or stage_index >= len(profile.stages):
        raise HTTPException(status_code=404, detail="Stage not found")
    stage = profile.stages[stage_index]
    return {"prompt": stage.prompt_template, "filename": stage.prompt_file}


@router.put("/{profile_id}/prompts/{stage_index}")
async def update_stage_prompt(
    profile_id: str,
    stage_index: int,
    body: dict,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Update the prompt content for a specific stage."""
    profile = profile_loader.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if stage_index < 0 or stage_index >= len(profile.stages):
        raise HTTPException(status_code=404, detail="Stage not found")
    
    stage = profile.stages[stage_index]
    # BUG FIX: Use profile_loader.prompts_dir instead of relative path
    prompt_path = _safe_prompt_path(profile_loader.prompts_dir, stage.prompt_file)
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(body.get("prompt", ""), encoding="utf-8")
    
    # Reload so the in-memory templates are up to date
    profile_loader.reload()
    
    return {"saved": True, "filename": stage.prompt_file}


@router.post("/{profile_id}/dry-run")
@limiter.limit("10/minute")
async def dry_run_stage(
    request: Request,
    profile_id: str,
    body: dict,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """
    Run a single stage against sample text without creating a job.
    
    Body: {
        "stage_index": 0,
        "transcript": "sample text...",
        "job_id": null  // Optional: pull transcript from a previous job's transcription
    }
    """
    profile = profile_loader.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    stage_index = body.get("stage_index", 0)
    if stage_index < 0 or stage_index >= len(profile.stages):
        raise HTTPException(status_code=400, detail=f"Invalid stage_index. Profile has {len(profile.stages)} stages.")
    
    # Get transcript: from body or from a previous job
    transcript = body.get("transcript")
    job_id = body.get("job_id")
    
    if not transcript and job_id:
        # Try to load from job's transcription cache
        from pathlib import Path
        transcription_path = Path("processing/job_data") / job_id / "transcription.json"
        if transcription_path.exists():
            import json
            with open(transcription_path) as f:
                data = json.load(f)
                transcript = data.get("text", "")
        
        if not transcript:
            raise HTTPException(status_code=400, detail=f"Could not load transcript from job {job_id}")
    
    if not transcript:
        raise HTTPException(status_code=400, detail="Provide 'transcript' or 'job_id'")
    
    # Truncate for safety (dry runs shouldn't be full-length)
    max_chars = body.get("max_chars", 5000)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n[... truncated for dry-run ...]"
    
    stage = profile.stages[stage_index]
    
    try:
        from src.worker.providers import resolve_provider
        from src.worker.formatter import MultiStageFormatter
        from src.worker.pricing import estimate_cost
        import os
        
        provider_config = resolve_provider(stage.model, stage.provider or None)
        
        # Build prompt
        prompt_kwargs = {"transcript": transcript}
        if "{cleaned_transcript}" in stage.prompt_template:
            prompt_kwargs["cleaned_transcript"] = transcript
        
        prompt = stage.prompt_template.format(**prompt_kwargs)
        
        # Create a temporary formatter to call the API
        default_key = (
            os.getenv("DEEPSEEK_API_KEY") or
            os.getenv("OPENROUTER_API_KEY") or
            os.getenv("OPENAI_API_KEY") or
            ""
        )
        
        formatter = MultiStageFormatter(
            api_key=default_key,
            prompts_dir=profile_loader.prompts_dir,
            profile=profile,
        )
        
        output, usage_info = formatter._call_api(
            prompt=prompt,
            system_message=stage.system_message,
            model=stage.model,
            temperature=stage.temperature,
            max_tokens=stage.max_tokens,
            timeout=stage.timeout,
            provider_config=provider_config,
        )
        
        input_tokens = usage_info.get("input_tokens", 0)
        output_tokens = usage_info.get("output_tokens", 0)
        cost = estimate_cost(stage.model, input_tokens, output_tokens)
        
        return {
            "stage": stage.name,
            "model": stage.model,
            "provider": provider_config.name,
            "output": output,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(cost, 6),
            "input_length": len(transcript),
            "output_length": len(output),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dry-run failed: {str(e)}")
