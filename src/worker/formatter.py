"""
Transcript formatting module using DeepSeek API.

This module provides the DeepSeekFormatter and MultiStageFormatter classes for formatting raw transcripts
into structured markdown notes.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Dict, List, Callable, Union

import requests

from .types import ProcessingStage, DegreeProfile

# Configure logging
logger = logging.getLogger(__name__)


class FormattingError(Exception):
    """Custom exception for transcript formatting errors."""
    pass


class DeepSeekFormatter:
    """
    Formats transcripts using DeepSeek's API (DeepSeek-V3).
    
    Handlers for standard note types (meeting, lecture, etc.) and
    provides base functionality for multi-stage formatting.
    """
    
    def __init__(
        self, 
        api_key: str, 
        prompts_dir: Path,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1"
    ):
        """
        Initialize the formatter.
        
        Args:
            api_key: The DeepSeek API key.
            prompts_dir: Directory containing prompt markdown files.
            model: The model to use (default: deepseek-chat).
            base_url: The base URL for the DeepSeek API.
        """
        self.api_key = api_key
        self.prompts_dir = prompts_dir
        self.model = model
        self.base_url = base_url.rstrip('/')
        
        if not api_key:
            logger.warning("DeepSeek API key not provided. Formatting will fail.")

    def _get_prompt(self, note_type: str, transcript: str) -> str:
        """
        Get the prompt for a specific note type.
        
        Args:
            note_type: The type of note (MEETING, LECTURE, etc.)
            transcript: The raw transcript to format.
            
        Returns:
            The formatted prompt string.
            
        Raises:
            FormattingError: If the prompt file is not found.
        """
        note_type_lower = note_type.lower()
        prompt_file = self.prompts_dir / "standard" / f"{note_type_lower}.md"
        
        if not prompt_file.exists():
            # Try to match legacy names if file not found directly
            # For now, we assume strict mapping based on extracted files
            valid_types = [f.stem for f in (self.prompts_dir / "standard").glob("*.md")]
            raise FormattingError(
                f"Unknown note type: {note_type}. "
                f"Available standard types: {', '.join(valid_types)}"
            )
            
        try:
            template = prompt_file.read_text(encoding="utf-8")
            return template.format(transcript=transcript)
        except Exception as e:
            raise FormattingError(f"Failed to load/format prompt for {note_type}: {e}")

    def _call_api(
        self, 
        prompt: str, 
        system_message: str = "You are a helpful assistant.",
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 120,
        provider_config: Optional['ProviderConfig'] = None,
    ) -> str:
        """
        Call an LLM API.
        
        Args:
            prompt: The user prompt.
            system_message: The system message.
            model: Model override.
            temperature: Temperature.
            max_tokens: Max output tokens.
            timeout: Request timeout.
            provider_config: Optional provider config to override instance defaults.
            
        Returns:
            The content of the response.
            
        Raises:
            FormattingError: If the API call fails.
        """
        # Use provider_config if given, otherwise fall back to instance defaults
        api_key = provider_config.api_key if provider_config else self.api_key
        base_url = provider_config.base_url if provider_config else self.base_url
        provider_name = provider_config.name if provider_config else "deepseek"
        
        if not api_key:
            raise FormattingError(f"No API key available for provider '{provider_name}'")
            
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # OpenRouter requires extra headers
        if provider_config and provider_config.name == "openrouter":
            headers["HTTP-Referer"] = "https://transcribe.delboysden.uk"
            headers["X-Title"] = "Transcription Pipeline"
        
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout
            )
            duration = time.time() - start_time
            
            if response.status_code != 200:
                error_msg = f"API Error {response.status_code} ({provider_name}): {response.text}"
                logger.error(error_msg)
                raise FormattingError(error_msg)
                
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Extract token usage
            usage = data.get("usage", {})
            usage_info = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "model": model or self.model,
            }
            logger.info(
                f"{provider_name} call successful ({duration:.1f}s). "
                f"Model: {model or self.model}. "
                f"Tokens: {usage.get('total_tokens', '?')}"
            )
            
            return content, usage_info
            
        except requests.exceptions.RequestException as e:
            raise FormattingError(f"API request failed ({provider_name}): {e}")
        except KeyError as e:
            raise FormattingError(f"Unexpected API response format: {e}")
        except FormattingError:
            raise
        except Exception as e:
            raise FormattingError(f"Unexpected error ({provider_name}): {e}")

    def format_transcript(
        self, 
        transcript: str, 
        note_type: str = "meeting",
        metadata: Optional[dict] = None
    ) -> str:
        """
        Format a transcript using a standard note type.
        
        Args:
            transcript: The raw transcript text.
            note_type: The type of note (meeting, supervision, etc.).
            metadata: Optional metadata.
            
        Returns:
            The formatted markdown string.
        """
        logger.info(f"Formatting transcript as: {note_type}")
        
        try:
            prompt = self._get_prompt(note_type, transcript)
            content, _usage = self._call_api(prompt)
            return content
        except Exception as e:
            logger.error(f"Formatting failed: {e}")
            # Return raw transcript with error as fallback
            return f"<!-- Formatting failed: {e} -->\n\n# Raw Transcript\n\n{transcript}"


class MultiStageFormatter(DeepSeekFormatter):
    """
    Multi-stage formatter for degree-specific lecture processing.
    
    Executes a pipeline of stages defined in a DegreeProfile.
    """
    
    def __init__(
        self,
        api_key: str,
        prompts_dir: Path,
        profile: DegreeProfile,
        base_url: str = "https://api.deepseek.com/v1"
    ):
        """
        Initialize with a specific profile.
        
        Args:
            api_key: DeepSeek API key.
            prompts_dir: Prompt directory.
            profile: The DegreeProfile object defining the pipeline.
            base_url: API base URL.
        """
        super().__init__(api_key, prompts_dir, base_url=base_url)
        self.profile = profile
        self.stages = profile.stages
        
        logger.info(f"MultiStageFormatter initialized for profile: {profile.name} ({len(self.stages)} stages)")

    def process_transcript(
        self,
        transcript: str,
        metadata: Optional[dict] = None
    ) -> Dict[str, str]:
        """
        Process a transcript through all stages of the pipeline.
        
        Args:
            transcript: The raw transcript.
            metadata: Optional metadata.
        
        Returns:
            Dictionary mapping stage names to their outputs.
        """
        results = {
            "raw_input": transcript,
            "profile": self.profile.name,
        }
        
        current_input = transcript
        previous_outputs = {}
        
        logger.info(f"Starting {len(self.stages)}-stage processing pipeline")
        
        for i, stage in enumerate(self.stages, 1):
            logger.info(f"Stage {i}/{len(self.stages)}: {stage.name}")
            
            try:
                # Resolve provider for this stage's model
                from .providers import resolve_provider
                provider_config = resolve_provider(stage.model, stage.provider or None)
                
                # Prepare prompt
                # If stage prompt has {cleaned_transcript}, inject it from previous 'clean' stage
                # This is a bit specific to the current logic, might need generalization
                prompt_kwargs = {"transcript": current_input}
                
                if "{cleaned_transcript}" in stage.prompt_template and "clean" in previous_outputs:
                    prompt_kwargs["cleaned_transcript"] = previous_outputs.get("clean", current_input)
                elif "{cleaned_transcript}" in stage.prompt_template:
                     # Fallback if clean stage missing or named differently
                     prompt_kwargs["cleaned_transcript"] = current_input

                # Format the prompt
                prompt = stage.prompt_template.format(**prompt_kwargs)
                
                # Call API with resolved provider
                output, usage_info = self._call_api(
                    prompt=prompt,
                    system_message=stage.system_message,
                    model=stage.model,
                    temperature=stage.temperature,
                    max_tokens=stage.max_tokens,
                    timeout=stage.timeout,
                    provider_config=provider_config,
                )
                
                # Store result
                results[stage.name] = output
                results[f"{stage.name}_suffix"] = stage.filename_suffix
                results[f"{stage.name}_usage"] = usage_info
                
                # Accumulate total token usage
                results.setdefault("_total_input_tokens", 0)
                results.setdefault("_total_output_tokens", 0)
                results["_total_input_tokens"] += usage_info.get("input_tokens", 0)
                results["_total_output_tokens"] += usage_info.get("output_tokens", 0)
                
                # Update for next stage
                current_input = output
                previous_outputs[stage.name] = output
                
                logger.info(f"  ✓ Stage {stage.name} complete ({len(output)} chars)")
                
            except Exception as e:
                logger.error(f"  ✗ Stage {stage.name} failed: {e}")
                results[stage.name] = f"<!-- ERROR in stage {stage.name}: {e} -->\n\n{current_input}"
                results[f"{stage.name}_error"] = str(e)
                # Continue pipeline? Maybe stop?
                # For now we continue passing the error output (or previous input)
        
        # Mark final output
        if self.stages:
            results["final"] = current_input
            results["final_suffix"] = self.stages[-1].filename_suffix
        else:
            results["final"] = transcript
            results["final_suffix"] = ""
            
        logger.info("Multi-stage processing complete")
        return results

    def get_stage_outputs(self, results: Dict[str, str]) -> List[Dict]:
        """
        Extract list of stage outputs that should be saved as files.
        """
        outputs = []
        for stage in self.stages:
            if stage.name in results and stage.save_intermediate:
                outputs.append({
                    "stage": stage.name,
                    "suffix": stage.filename_suffix,
                    "content": results[stage.name]
                })
        return outputs
