# Backend Task: Add POST /api/profiles Endpoint

## Context

I have a transcription pipeline application built with FastAPI + SQLModel. The project is at `/home/craig/transcription-pipeline/` (or wherever you have it — adjust path as needed).

The app already has:
- `src/api/routes/profiles.py` — GET endpoints for listing and viewing profiles
- `src/worker/profile_loader.py` — loads profiles from YAML files in `config/profiles/`
- `src/worker/types.py` — defines `ProcessingStage` and `DegreeProfile` dataclasses
- `src/api/schemas.py` — Pydantic schemas for API responses
- Prompt templates stored as Markdown files in `config/prompts/`

Profiles are YAML files like this (example `config/profiles/business_lecture.yaml`):

```yaml
name: business_lecture
description: "Business & Management lectures"
skip_diarization: true
stages:
  - name: "Clean & Structure"
    prompt_file: "business_lecture/stage_1_clean_structure.md"
    system_message: ""
    model: "deepseek-chat"
    temperature: 0.3
    max_tokens: 4096
    timeout: 120
    requires_previous: false
    save_intermediate: true
    filename_suffix: "_clean"
  - name: "Strategic Analysis"
    prompt_file: "business_lecture/stage_2_strategic_analysis.md"
    system_message: ""
    model: "deepseek-chat"
    temperature: 0.3
    max_tokens: 4096
    timeout: 120
    requires_previous: true
    save_intermediate: true
    filename_suffix: "_analysis"
```

Each stage's `prompt_file` points to a Markdown file relative to `config/prompts/`. So `business_lecture/stage_1_clean_structure.md` lives at `config/prompts/business_lecture/stage_1_clean_structure.md`.

## What I Need

Add a `POST /api/profiles` endpoint that:

1. **Accepts this JSON body:**

```json
{
  "id": "data_protection",
  "name": "Data Protection",
  "description": "Data protection coursework processing",
  "skip_diarization": false,
  "icon": "book",
  "stages": [
    {
      "name": "Clean & Structure",
      "model": "deepseek-chat",
      "temperature": 0.3,
      "max_tokens": 4096,
      "prompt_content": "You are a transcript cleaner. Take the raw transcript and...",
      "prompt_file": "data_protection/stage_1_clean_structure.md",
      "requires_previous": false,
      "save_intermediate": true,
      "filename_suffix": "_clean"
    },
    {
      "name": "Analysis",
      "model": "deepseek-chat",
      "temperature": 0.3,
      "max_tokens": 4096,
      "prompt_content": "You are an analyst. Take the cleaned transcript and...",
      "prompt_file": "data_protection/stage_2_analysis.md",
      "requires_previous": true,
      "save_intermediate": true,
      "filename_suffix": "_analysis"
    }
  ]
}
```

2. **Validates** that `id` and `name` are provided and `id` doesn't already exist as a profile.

3. **Creates the profile YAML** at `config/profiles/{id}.yaml` — write only the YAML fields the ProfileLoader expects (name, description, skip_diarization, stages with name, prompt_file, system_message, model, temperature, max_tokens, timeout, requires_previous, save_intermediate, filename_suffix). Do NOT include `prompt_content` or `icon` in the YAML.

4. **Creates prompt Markdown files** — for each stage, write `prompt_content` to `config/prompts/{stage.prompt_file}`. Create subdirectories as needed.

5. **Reloads the ProfileLoader** so the new profile is immediately available without restart. The `ProfileLoader` class has a `reload()` method.

6. **Returns** the new profile in the same format as `GET /api/profiles/{id}` (using `ProfileDetailResponse` schema).

## Files to Modify

### `src/api/schemas.py`
Add a request schema:

```python
class ProfileCreateStage(BaseModel):
    name: str
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 4096
    prompt_content: str = ""
    prompt_file: Optional[str] = None  # Auto-generated if not provided
    requires_previous: bool = False
    save_intermediate: bool = True
    filename_suffix: str = ""

class ProfileCreateRequest(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    skip_diarization: bool = False
    icon: Optional[str] = None
    stages: List[ProfileCreateStage]
```

### `src/api/routes/profiles.py`
Add the POST endpoint. Key logic:

```python
@router.post("", response_model=ProfileDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    request: ProfileCreateRequest,
    profile_loader: ProfileLoader = Depends(get_profile_loader),
):
    # 1. Check profile doesn't already exist
    # 2. Auto-generate prompt_file paths if not provided:
    #    f"{request.id}/stage_{i+1}_{auto_id(stage.name)}.md"
    # 3. Build YAML dict (excluding prompt_content and icon)
    # 4. Write YAML to config/profiles/{request.id}.yaml
    # 5. Write each stage's prompt_content to config/prompts/{stage.prompt_file}
    # 6. Reload profile_loader
    # 7. Return the new profile
```

Use `yaml.dump()` with `default_flow_style=False` for readable YAML output.

For auto-generating filename-safe IDs from stage names:
```python
import re
def auto_id(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
```

### `src/api/dependencies.py`
The `get_profile_loader()` currently creates a new instance each request. That's fine — it reloads from disk each time, so new profiles will be picked up automatically after the YAML is written.

## Important Notes

- The `config/` directory is mounted read-only in Docker (`./config:/app/config:ro`). For the create endpoint to work in production, you'll need to change this to read-write: `./config:/app/config` in `docker-compose.yml`. Flag this to the user.
- Use `PyYAML` (already a dependency) for writing YAML.
- Make sure the prompt subdirectory is created with `mkdir(parents=True, exist_ok=True)`.
- Add proper error handling — if YAML write fails, clean up any prompt files already written.
- Keep `system_message` as empty string in the YAML (the prompt content goes in the Markdown file, not the YAML).

## Also Needed: DELETE /api/profiles/{id}

Add a DELETE endpoint that:
1. Checks the profile exists
2. Removes the YAML file from `config/profiles/`
3. Optionally removes the prompt directory from `config/prompts/{id}/`
4. Reloads the ProfileLoader
5. Returns 204

## Docker Compose Change

In `docker-compose.yml`, change the config volume from read-only to read-write for BOTH the `app` and `worker` services:

```yaml
# Change this:
- ./config:/app/config:ro
# To this:
- ./config:/app/config
```

This is required for the API to write new profile YAML and prompt files.
