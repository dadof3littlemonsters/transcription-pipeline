"""
Profile management API routes.
"""

import re
import yaml
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas import (
    ProfileResponse, 
    ProfileDetailResponse, 
    ProfileStageInfo,
    ProfileCreateRequest,
    ProfileCreateStage,
)
from src.api.dependencies import get_profile_loader
from src.worker.profile_loader import ProfileLoader

router = APIRouter(prefix="/api/profiles", tags=["Profiles"])


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
            profiles.append(ProfileResponse(
                id=profile_id,
                name=profile.name,
                description=getattr(profile, 'description', ''),
                stage_count=len(profile.stages),
                stages=[stage.name for stage in profile.stages],
                syncthing_folder=profile.syncthing.folder if profile.syncthing else None,
                syncthing_subfolder=profile.syncthing.subfolder if profile.syncthing else None,
            ))
    
    # Add standard note types
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
async def create_profile(
    request: ProfileCreateRequest,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    """Create a new profile with YAML config and prompt files."""
    
    # 1. Check profile doesn't already exist
    if profile_loader.get_profile(request.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile '{request.id}' already exists"
        )
    
    # 2. Auto-generate prompt_file paths if not provided
    stages_data = []
    for i, stage in enumerate(request.stages):
        if not stage.prompt_file:
            stage.prompt_file = f"{request.id}/stage_{i+1}_{auto_id(stage.name)}.md"
        
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
    
    # 3. Build YAML dict (excluding prompt_content and icon)
    yaml_data = {
        "name": request.name,
        "description": request.description or "",
        "skip_diarization": request.skip_diarization,
        "stages": stages_data,
    }
    
    # Add syncthing config if provided
    if request.syncthing_folder:
        yaml_data["syncthing"] = {
            "share_folder": request.syncthing_folder,
            "subfolder": request.syncthing_subfolder or "",
        }
    
    # 4. Write YAML to config/profiles/{request.id}.yaml
    config_dir = Path("config")
    profiles_dir = config_dir / "profiles"
    prompts_dir = config_dir / "prompts"
    
    profiles_dir.mkdir(parents=True, exist_ok=True)
    profile_yaml_path = profiles_dir / f"{request.id}.yaml"
    
    try:
        with open(profile_yaml_path, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)
        
        # 5. Write each stage's prompt_content to config/prompts/{stage.prompt_file}
        written_prompts = []
        try:
            for stage in request.stages:
                prompt_path = prompts_dir / stage.prompt_file
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(prompt_path, 'w') as f:
                    f.write(stage.prompt_content)
                
                written_prompts.append(prompt_path)
        
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
        
        # 7. Return the new profile
        profile = profile_loader.get_profile(request.id)
        if not profile:
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
            id=request.id,
            name=profile.name,
            description=profile.description,
            stages=stages,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        # Clean up YAML file if it was created
        if profile_yaml_path.exists():
            profile_yaml_path.unlink()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create profile: {str(e)}"
        )


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
    
    # 1. Check the profile exists
    profile = profile_loader.get_profile(profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile_id}' not found"
        )
    
    # 2. Remove the YAML file from config/profiles/
    config_dir = Path("config")
    profile_yaml_path = config_dir / "profiles" / f"{profile_id}.yaml"
    
    if profile_yaml_path.exists():
        profile_yaml_path.unlink()
    
    # 3. Optionally remove the prompt directory from config/prompts/{id}/
    prompts_dir = config_dir / "prompts" / profile_id
    if prompts_dir.exists() and prompts_dir.is_dir():
        import shutil
        shutil.rmtree(prompts_dir)
    
    # 4. Reload the ProfileLoader
    profile_loader.reload()


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
    prompt_path = Path("config/prompts") / stage.prompt_file
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(body.get("prompt", ""), encoding="utf-8")
    
    # Reload so the in-memory templates are up to date
    profile_loader.reload()
    
    return {"saved": True, "filename": stage.prompt_file}
