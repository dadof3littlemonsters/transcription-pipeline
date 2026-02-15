"""
Main transcription pipeline orchestrator.

Coordinates the entire processing flow:
1. Groq Whisper transcription
2. Pyannote speaker diarization (optional based on profile)
3. Timestamp merging (optional based on profile)
4. DeepSeek formatting (single-stage or multi-stage based on profile)
5. Output generation
"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from rich.console import Console
from rich.logging import RichHandler
import logging

from config import get_config
from transcription import GroqTranscriber, GroqAPIError
from diarization import SpeakerDiarizer, DiarizationError
from merge import merge_transcript_with_speakers
from formatting import (
    DeepSeekFormatter, 
    MultiStageFormatter, 
    FormattingError,
    DEGREE_PROFILES,
    should_skip_diarization
)
from output import OutputGenerator
from email_sender import EmailSender, get_kate_email, get_keira_email, get_keira_cohort_email

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("pipeline")


class TranscriptionPipeline:
    """Main pipeline for processing audio files through transcription and formatting."""
    
    def __init__(self):
        self.config = get_config()
        
        # Initialize components
        self.groq = None
        self.diarizer = None
        self.formatter = None
        self.multi_stage_formatter = None
        self.output_generator = None
        self.email_sender = None
        
        # Directory setup with safety folders
        self.error_dir = self.config.processing_dir / "errors"
        self.error_dir.mkdir(parents=True, exist_ok=True)
        
        # Archive directory for processed originals (safety backup)
        self.archive_dir = self.config.processing_dir / "archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Quarantine directory for files that failed but might be recoverable
        self.quarantine_dir = self.config.processing_dir / "quarantine"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize API clients with credentials from environment."""
        # Groq client
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.groq = GroqTranscriber(api_key=groq_key)
            logger.info("[green]✓ Groq client initialized[/green]")
        else:
            logger.warning("[yellow]⚠ GROQ_API_KEY not set - transcription will fail[/yellow]")
        
        # Pyannote diarizer
        hf_token = os.getenv("HUGGINGFACE_TOKEN")
        if hf_token:
            try:
                logger.info(f"Initializing Pyannote diarizer with token: {hf_token[:10]}...")
                self.diarizer = SpeakerDiarizer(hf_token=hf_token)
                logger.info("[green]✓ Pyannote diarizer initialized[/green]")
            except Exception as e:
                logger.error(f"[red]✗ Failed to initialize Pyannote diarizer: {e}[/red]")
                self.diarizer = None
        else:
            logger.warning("[yellow]⚠ HUGGINGFACE_TOKEN not set - diarization will be disabled[/yellow]")
        
        # DeepSeek formatter (single-stage)
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            self.formatter = DeepSeekFormatter(api_key=deepseek_key)
            logger.info("[green]✓ DeepSeek formatter initialized[/green]")
        else:
            logger.warning("[yellow]⚠ DEEPSEEK_API_KEY not set - formatting will be skipped[/yellow]")
        
        # Multi-stage formatter (initialized on demand based on profile)
        self.multi_stage_formatter = None
        
        # Output generator
        self.output_generator = OutputGenerator(self.config.output_dir)
        logger.info("[green]✓ Output generator initialized[/green]")
        
        # Email sender
        self.email_sender = EmailSender()
        if self.email_sender.is_configured():
            logger.info("[green]✓ Email sender initialized[/green]")
        else:
            logger.info("[dim]Email sender not configured (optional)[/dim]")
    
    def _get_multi_stage_formatter(self, profile_name: str) -> MultiStageFormatter:
        """Get or create multi-stage formatter for a profile."""
        if self.multi_stage_formatter is None or self.multi_stage_formatter.profile_name != profile_name:
            deepseek_key = os.getenv("DEEPSEEK_API_KEY")
            if not deepseek_key:
                raise RuntimeError("DEEPSEEK_API_KEY not set - required for multi-stage processing")
            
            self.multi_stage_formatter = MultiStageFormatter(
                api_key=deepseek_key,
                profile_name=profile_name
            )
        return self.multi_stage_formatter
    
    def process_file(
        self, 
        audio_path: Path, 
        note_type: str = "meeting",
        profile_name: Optional[str] = None
    ) -> dict:
        """
        Process a single audio file through the entire pipeline.
        
        Args:
            audio_path: Path to the audio file
            note_type: Type of note (meeting, supervision, client, lecture, braindump)
                      or profile name (social_work_lecture, business_lecture)
            profile_name: Optional degree profile name for specialized processing
        
        Returns:
            dict with processing results and output paths
        """
        start_time = time.time()
        logger.info(f"[bold cyan]Processing: {audio_path.name}[/bold cyan]")
        logger.info(f"[dim]Note type: {note_type}[/dim]")
        if profile_name:
            logger.info(f"[dim]Profile: {profile_name}[/dim]")
        
        result = {
            "input_file": str(audio_path),
            "note_type": note_type,
            "profile_name": profile_name,
            "success": False,
            "outputs": {},
            "error": None,
            "duration": 0,
        }
        
        # Safety: Move to quarantine first (protect original while processing)
        quarantine_path = self.quarantine_dir / audio_path.name
        original_path = audio_path  # Keep reference to original path
        try:
            shutil.move(str(audio_path), str(quarantine_path))
            logger.info(f"[dim]Moved to quarantine: {quarantine_path.name}[/dim]")
            audio_path = quarantine_path  # Work with quarantined copy
        except Exception as q_err:
            logger.warning(f"[yellow]⚠ Could not quarantine file: {q_err}[/yellow]")
            # Continue with original location
        
        try:
            # Step 1: Transcription with Groq Whisper
            logger.info("[cyan]Step 1/5: Transcribing with Groq Whisper...[/cyan]")
            if not self.groq:
                raise RuntimeError("Groq client not initialized - check GROQ_API_KEY")
            
            transcription = self.groq.transcribe(audio_path)
            whisper_segments = transcription.get("segments", [])
            full_text = transcription.get("text", "")
            audio_duration = transcription.get("duration", 0)
            
            logger.info(f"[green]  ✓ Transcription complete: {len(whisper_segments)} segments[/green]")
            
            # Check if we're using multi-stage processing (degree profile)
            if profile_name and profile_name in DEGREE_PROFILES:
                # Multi-stage processing for degree profiles
                result = self._process_with_profile(
                    audio_path=audio_path,
                    whisper_segments=whisper_segments,
                    full_text=full_text,
                    audio_duration=audio_duration,
                    profile_name=profile_name,
                    result=result,
                    start_time=start_time
                )
            else:
                # Standard single-stage processing with diarization
                result = self._process_standard(
                    audio_path=audio_path,
                    whisper_segments=whisper_segments,
                    full_text=full_text,
                    audio_duration=audio_duration,
                    note_type=note_type,
                    result=result,
                    start_time=start_time
                )
            
        except Exception as e:
            logger.error(f"[red]✗ Processing failed: {e}[/red]")
            result["error"] = str(e)
            result["success"] = False
            
            # Move from quarantine to error directory (keep for recovery)
            error_path = self.error_dir / audio_path.name
            try:
                shutil.move(str(audio_path), str(error_path))
                logger.info(f"[dim]Moved to error directory: {error_path}[/dim]")
                logger.info(f"[yellow]⚠ File preserved in errors folder for recovery[/yellow]")
            except Exception as move_err:
                logger.error(f"[red]Failed to move to error directory: {move_err}[/red]")
        
        finally:
            result["duration"] = time.time() - start_time
            if result["success"]:
                logger.info(f"[bold green]✓ Processing complete in {result['duration']:.1f}s[/bold green]")
                # Archive the original file instead of deleting
                self._safe_archive(audio_path, result)
            else:
                logger.error(f"[bold red]✗ Processing failed after {result['duration']:.1f}s[/bold red]")
                # File is already in error directory from exception handler
        
        return result
    
    def _safe_archive(self, audio_path: Path, result: Dict) -> None:
        """
        Safely archive or delete the audio file after successful processing.
        
        Only deletes if outputs are verified to exist.
        Otherwise moves to archive directory for safety.
        
        Args:
            audio_path: Path to the audio file
            result: Processing result dict with output info
        """
        # Verify outputs exist before deleting
        outputs_verified = self._verify_outputs_exist(result)
        
        if not outputs_verified:
            logger.warning("[yellow]⚠ Could not verify outputs - moving to archive instead of deleting[/yellow]")
            archive_path = self.archive_dir / audio_path.name
            try:
                shutil.move(str(audio_path), str(archive_path))
                logger.info(f"[dim]  Archived to: {archive_path}[/dim]")
            except Exception as e:
                logger.error(f"[red]  Failed to archive: {e}[/red]")
            return
        
        # Outputs verified - safe to delete
        try:
            audio_path.unlink()
            logger.info("[green]  ✓ Original audio deleted (outputs verified)[/green]")
        except Exception as e:
            logger.warning(f"[yellow]  ⚠ Failed to delete audio: {e}[/yellow]")
    
    def _verify_outputs_exist(self, result: Dict) -> bool:
        """
        Verify that output files actually exist.
        
        Args:
            result: Processing result dict
            
        Returns:
            True if at least one output file exists, False otherwise
        """
        try:
            outputs = result.get("outputs", {})
            
            # Check stage_files
            if "stage_files" in outputs:
                for stage_file in outputs["stage_files"]:
                    path = Path(stage_file.get("path", ""))
                    if path.exists():
                        return True
            
            # Check other output paths
            for key, path_str in outputs.items():
                if key == "stage_files":
                    continue
                if isinstance(path_str, (str, Path)):
                    path = Path(path_str)
                    if path.exists():
                        return True
            
            # Also check docx files
            docs_dir = self.config.output_dir / "docs"
            for subdir in ["keira", "kate", ""]:
                check_dir = docs_dir / subdir if subdir else docs_dir
                if check_dir.exists():
                    md_files = list(check_dir.glob("*.md"))
                    docx_files = list(check_dir.glob("*.docx"))
                    if md_files or docx_files:
                        return True
            
            return False
        except Exception as e:
            logger.warning(f"[yellow]⚠ Error verifying outputs: {e}[/yellow]")
            return False
    
    def _process_with_profile(
        self,
        audio_path: Path,
        whisper_segments: List[Dict],
        full_text: str,
        audio_duration: float,
        profile_name: str,
        result: Dict,
        start_time: float
    ) -> Dict:
        """
        Process using multi-stage formatter for degree profiles.
        Skips diarization and uses specialized prompts.
        """
        logger.info("[cyan]Using multi-stage processing (diarization skipped)[/cyan]")
        
        # Step 2-3: Skip diarization and merging for profile-based processing
        logger.info("[dim]Step 2-3: Skipped (no diarization for profile-based processing)[/dim]")
        
        # Build raw transcript from Whisper segments for multi-stage processing
        raw_transcript = self._build_raw_transcript(whisper_segments)
        
        # Step 4: Multi-stage formatting
        logger.info("[cyan]Step 4/5: Multi-stage formatting with DeepSeek...[/cyan]")
        if not self.formatter:
            raise RuntimeError("DeepSeek formatter not initialized - check DEEPSEEK_API_KEY")
        
        try:
            # Get multi-stage formatter for this profile
            multi_formatter = self._get_multi_stage_formatter(profile_name)
            
            # Run through all stages
            stage_results = multi_formatter.process_transcript(
                transcript=raw_transcript,
                metadata={
                    "filename": audio_path.name,
                    "duration": audio_duration,
                }
            )
            
            # Get outputs to save
            stage_outputs = multi_formatter.get_stage_outputs(stage_results)
            logger.info(f"[green]  ✓ Multi-stage formatting complete: {len(stage_outputs)} outputs[/green]")
            
            # Step 5: Generate outputs for each stage
            logger.info("[cyan]Step 5/5: Generating outputs...[/cyan]")
            
            metadata = {
                "duration": audio_duration,
                "processed_at": datetime.now().isoformat(),
                "profile": profile_name,
            }
            
            # Determine user subdirectory for Syncthing
            user_subdir = None
            if profile_name == "business_lecture":
                user_subdir = "keira"
            
            # Get user-specific docs directory for Syncthing
            docs_dir = self.output_generator.get_user_docs_dir(user_subdir)
            if user_subdir:
                logger.info(f"[dim]  Output directory: {docs_dir}[/dim]")
            
            # Generate output files for each stage
            all_outputs = []
            for stage_output in stage_outputs:
                outputs = self.output_generator.generate_multi_stage_output(
                    content=stage_output["content"],
                    filename_base=audio_path.stem,
                    suffix=stage_output["suffix"],
                    stage_name=stage_output["stage"],
                    metadata=metadata,
                    docs_dir=docs_dir
                )
                all_outputs.extend(outputs)
            
            # Store output paths in result
            result["outputs"] = {
                "stage_files": [
                    {
                        "stage": stage_output["stage"],
                        "path": str(self.output_generator.transcripts_dir / 
                                   self.output_generator._derive_filename(audio_path.stem, stage_output["suffix"], ".md"))
                    }
                    for stage_output in stage_outputs
                ],
                "final_stage": stage_results.get("final_suffix", ""),
            }
            
            logger.info(f"[green]  ✓ Generated {len(all_outputs)} output files[/green]")
            
            result["success"] = True
            
            # Send email notification if configured
            if self.email_sender.is_configured():
                recipient_email = None
                user_name = None
                cc_email = None
                
                if profile_name == "social_work_lecture":
                    recipient_email = get_kate_email()
                    user_name = "Kate"
                elif profile_name == "business_lecture":
                    recipient_email = get_keira_email()
                    user_name = "Keira"
                    cc_email = get_keira_cohort_email()  # Optional cohort email
                
                if recipient_email:
                    if cc_email:
                        logger.info(f"[cyan]Sending email notification to {user_name} and cohort...[/cyan]")
                    else:
                        logger.info(f"[cyan]Sending email notification to {user_name}...[/cyan]")
                    # Get list of all output file paths
                    output_file_paths = [Path(o["path"]) for o in all_outputs if o.get("type") == "docx"]
                    email_sent = self.email_sender.send_lecture_complete(
                        to_email=recipient_email,
                        lecture_name=audio_path.stem,
                        output_files=output_file_paths,
                        profile_name=profile_name,
                        user_name=user_name,
                        cc_email=cc_email
                    )
                    if email_sent:
                        logger.info("[green]  ✓ Email notification sent[/green]")
                    else:
                        logger.warning("[yellow]  ⚠ Email failed to send[/yellow]")
            
            # Note: File cleanup is handled centrally in process_file() via _safe_archive()
            
        except Exception as e:
            logger.error(f"[red]  ✗ Multi-stage formatting failed: {e}[/red]")
            raise
        
        return result
    
    def _process_standard(
        self,
        audio_path: Path,
        whisper_segments: List[Dict],
        full_text: str,
        audio_duration: float,
        note_type: str,
        result: Dict,
        start_time: float
    ) -> Dict:
        """
        Standard processing with diarization and single-stage formatting.
        """
        # Step 2: Speaker Diarization with Pyannote
        diarization_segments = []
        if self.diarizer:
            logger.info("[cyan]Step 2/5: Running speaker diarization...[/cyan]")
            try:
                diarization_segments = self.diarizer.diarize(audio_path)
                logger.info(f"[green]  ✓ Diarization complete: {len(diarization_segments)} speaker segments[/green]")
                
                # Count unique speakers
                speakers = set(s["speaker"] for s in diarization_segments)
                logger.info(f"[dim]  Found {len(speakers)} unique speaker(s)[/dim]")
            except DiarizationError as e:
                logger.warning(f"[yellow]  ⚠ Diarization failed: {e}. Using single speaker.[/yellow]")
                # Create single-speaker fallback
                diarization_segments = [{"speaker": "SPEAKER_00", "start": 0, "end": audio_duration}]
        else:
            logger.info("[dim]Step 2/5: Diarization skipped (no HF token)[/dim]")
            diarization_segments = [{"speaker": "SPEAKER_00", "start": 0, "end": audio_duration}]
        
        # Step 3: Merge timestamps with speakers
        logger.info("[cyan]Step 3/5: Merging timestamps with speakers...[/cyan]")
        merged_segments = merge_transcript_with_speakers(whisper_segments, diarization_segments)
        
        # Build speaker-labeled transcript
        speaker_transcript = self._build_speaker_transcript(merged_segments)
        logger.info(f"[green]  ✓ Merged: {len(merged_segments)} labeled segments[/green]")
        
        # Step 4: Format with DeepSeek
        formatted_text = speaker_transcript
        if self.formatter:
            logger.info("[cyan]Step 4/5: Formatting with DeepSeek...[/cyan]")
            try:
                metadata = {
                    "duration": audio_duration,
                    "num_speakers": len(set(s["speaker"] for s in merged_segments)),
                    "note_type": note_type,
                }
                formatted_text = self.formatter.format_transcript(
                    speaker_transcript, note_type, metadata
                )
                logger.info("[green]  ✓ Formatting complete[/green]")
            except FormattingError as e:
                logger.warning(f"[yellow]  ⚠ Formatting failed: {e}. Using raw transcript.[/yellow]")
                formatted_text = speaker_transcript
        else:
            logger.info("[dim]Step 4/5: Formatting skipped (no DeepSeek key)[/dim]")
        
        # Step 5: Generate outputs
        logger.info("[cyan]Step 5/5: Generating outputs...[/cyan]")
        metadata = {
            "duration": audio_duration,
            "num_speakers": len(set(s["speaker"] for s in merged_segments)),
            "processed_at": datetime.now().isoformat(),
        }
        outputs = self.output_generator.generate_outputs(
            formatted_text, note_type, audio_path.stem, metadata
        )
        
        result["outputs"] = {
            "markdown": str(outputs["markdown_path"]) if outputs["markdown_path"] else None,
            "docx": str(outputs["docx_path"]) if outputs["docx_path"] else None,
            "title": outputs["title"],
        }
        logger.info(f"[green]  ✓ Outputs generated:[/green]")
        if outputs["markdown_path"]:
            logger.info(f"[dim]    - Markdown: {outputs['markdown_path'].name}[/dim]")
        if outputs["docx_path"]:
            logger.info(f"[dim]    - Word: {outputs['docx_path'].name}[/dim]")
        
        result["success"] = True
        
        # Note: File cleanup is handled centrally in process_file() via _safe_archive()
        
        return result
    
    def _build_speaker_transcript(self, segments: list) -> str:
        """Build a transcript string with speaker labels."""
        lines = []
        current_speaker = None
        current_text = []
        
        for seg in segments:
            speaker = seg.get("speaker", "UNKNOWN")
            text = seg.get("text", "").strip()
            
            if not text:
                continue
            
            # Start new speaker section if speaker changes
            if speaker != current_speaker:
                if current_text:
                    lines.append(f"{' '.join(current_text)}")
                    lines.append("")
                lines.append(f"**{speaker}:**")
                current_speaker = speaker
                current_text = []
            
            current_text.append(text)
        
        # Add final section
        if current_text:
            lines.append(f"{' '.join(current_text)}")
        
        return "\n".join(lines)
    
    def _build_raw_transcript(self, segments: list) -> str:
        """Build a simple transcript from Whisper segments with timestamps."""
        lines = []
        for seg in segments:
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "").strip()
            
            if text:
                # Format: [00:01:23] Text of segment
                start_str = self._format_timestamp(start)
                lines.append(f"[{start_str}] {text}")
        
        return "\n".join(lines)
    
    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def health_check(self) -> dict:
        """Check health of all pipeline components."""
        health = {
            "groq": False,
            "diarization": False,
            "formatting": False,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Check Groq
        if self.groq:
            try:
                # Try a simple API call (we could use a lighter endpoint)
                import requests
                response = requests.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {self.groq.api_key}"},
                    timeout=10
                )
                health["groq"] = response.status_code == 200
            except Exception:
                pass
        
        # Check DeepSeek
        if self.formatter:
            try:
                import requests
                response = requests.get(
                    "https://api.deepseek.com/v1/models",
                    headers={"Authorization": f"Bearer {self.formatter.api_key}"},
                    timeout=10
                )
                health["formatting"] = response.status_code == 200
            except Exception:
                pass
        
        # Diarization is local - just check if initialized
        health["diarization"] = self.diarizer is not None
        
        return health


def process_file_sync(audio_path: str, note_type: str = "meeting", profile_name: Optional[str] = None) -> dict:
    """
    Convenience function to process a single file.
    
    Usage:
        result = process_file_sync("/path/to/audio.mp3", "meeting")
    """
    pipeline = TranscriptionPipeline()
    return pipeline.process_file(Path(audio_path), note_type, profile_name)


if __name__ == "__main__":
    # Quick test
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <audio_file> [note_type] [profile_name]")
        print("  note_type: meeting, supervision, client, lecture, braindump")
        print("  profile_name: social_work_lecture, business_lecture")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    note_type = sys.argv[2] if len(sys.argv) > 2 else "meeting"
    profile_name = sys.argv[3] if len(sys.argv) > 3 else None
    
    result = process_file_sync(audio_file, note_type, profile_name)
    print("\n" + "="*50)
    print("RESULT:")
    print(f"  Success: {result['success']}")
    print(f"  Duration: {result['duration']:.1f}s")
    if result['outputs']:
        print(f"  Outputs: {result['outputs']}")
    if result['error']:
        print(f"  Error: {result['error']}")
