"""
Transcription pipeline worker.

Monitors upload directories and processes audio files through the complete pipeline.
"""

import os
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
import logging

from config import get_config
from pipeline import TranscriptionPipeline
from formatting import get_profile_for_folder, should_skip_diarization

try:
    from file_watcher import FileWatcher, AudioFileHandler
except ImportError:
    from file_watcher import FileWatcher, AudioFileHandler

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("worker")


class PipelineWorker:
    """
    Worker that combines file watching with pipeline processing.
    
    Monitors upload directories for new audio files and processes them
    through the complete transcription pipeline.
    """
    
    def __init__(self):
        self.config = get_config()
        self.pipeline = TranscriptionPipeline()
        self.watcher = None
        
    def start(self):
        """Start the worker - health check, then begin watching."""
        logger.info("[bold cyan]Starting Transcription Pipeline Worker[/bold cyan]")
        logger.info("=" * 50)
        
        # Run health check
        health = self.pipeline.health_check()
        logger.info("[bold]Health Check:[/bold]")
        logger.info(f"  Groq API: {'[green]✓[/green]' if health['groq'] else '[red]✗[/red]'}")
        logger.info(f"  Diarization: {'[green]✓[/green]' if health['diarization'] else '[red]✗[/red]'}")
        logger.info(f"  DeepSeek API: {'[green]✓[/green]' if health['formatting'] else '[red]✗[/red]'}")
        
        if not health['groq']:
            logger.error("[red]Groq API is not healthy. Processing will fail.[/red]")
            logger.info("[dim]Set GROQ_API_KEY environment variable.[/dim]")
        
        logger.info("=" * 50)
        
        # Create watcher with pipeline integration
        self.watcher = FileWatcher(
            config=self.config,
            on_file_detected=self._on_file_detected,
            on_file_moved=self._on_file_moved
        )
        
        # Process existing files
        self.watcher.scan_existing_files()
        
        # Start watching
        logger.info("\n[dim]Starting file watcher...[/dim]")
        self.watcher.run_forever()
    
    def _on_file_detected(self, file_path: Path):
        """Callback when a new file is detected."""
        logger.info(f"[dim]Detected: {file_path.name}[/dim]")
    
    def _on_file_moved(self, src_path: Path, dst_path: Path):
        """Callback when a file is moved to processing - trigger pipeline."""
        logger.info(f"[dim]Moved to processing: {dst_path.name}[/dim]")
        
        # Determine note type and profile from directory
        note_type = self._detect_note_type(src_path)
        profile_name = self._detect_profile(src_path)
        
        # Log detection
        if profile_name:
            logger.info(f"[cyan]Profile detected: {profile_name}[/cyan]")
            logger.info(f"[cyan]Note type: {note_type} (diarization: {'skipped' if should_skip_diarization(src_path.parent.name) else 'enabled'})[/cyan]")
        else:
            logger.info(f"[cyan]Note type: {note_type}[/cyan]")
        
        # Process the file
        try:
            result = self.pipeline.process_file(
                dst_path, 
                note_type=note_type,
                profile_name=profile_name
            )
            
            if result['success']:
                logger.info(f"[bold green]✓ Successfully processed: {dst_path.name}[/bold green]")
                if 'outputs' in result and result['outputs']:
                    # Handle multi-stage outputs (list of stage files)
                    if 'stage_files' in result['outputs']:
                        for stage_file in result['outputs']['stage_files']:
                            logger.info(f"[dim]  - {stage_file['stage']}: {Path(stage_file['path']).name}[/dim]")
                    # Handle standard outputs (markdown/docx paths)
                    else:
                        for output_type, output_path in result['outputs'].items():
                            if output_path and isinstance(output_path, (str, Path)):
                                logger.info(f"[dim]  - {output_type}: {Path(output_path).name}[/dim]")
            else:
                logger.error(f"[bold red]✗ Failed to process: {dst_path.name}[/bold red]")
                if result['error']:
                    logger.error(f"  Error: {result['error']}")
        
        except Exception as e:
            logger.error(f"[red]Unexpected error processing {dst_path.name}: {e}[/red]")
    
    def _detect_note_type(self, file_path: Path) -> str:
        """
        Detect note type from the file's parent directory.
        
        Returns one of: meeting, supervision, client, lecture, braindump, social_work_lecture
        """
        # Get the parent directory name
        parent = file_path.parent.name.lower()
        
        # Check for degree profile folders first
        profile = get_profile_for_folder(parent)
        if profile:
            return profile  # Return the profile name as note type
        
        # Map to standard note types
        type_mapping = {
            'meeting': 'meeting',
            'meetings': 'meeting',
            'supervision': 'supervision',
            'supervisions': 'supervision',
            'client': 'client',
            'clients': 'client',
            'therapy': 'client',
            'lecture': 'lecture',
            'lectures': 'lecture',
            'presentation': 'lecture',
            'braindump': 'braindump',
            'braindumps': 'braindump',
            'voicenote': 'braindump',
            'voicenotes': 'braindump',
            'notes': 'braindump',
        }
        
        return type_mapping.get(parent, 'meeting')  # Default to meeting
    
    def _detect_profile(self, file_path: Path) -> Optional[str]:
        """
        Detect degree profile from the file's parent directory.
        
        Args:
            file_path: Path to the audio file.
        
        Returns:
            Profile name if mapped, None otherwise.
        """
        parent = file_path.parent.name.lower()
        return get_profile_for_folder(parent)
    
    def stop(self):
        """Stop the worker."""
        if self.watcher:
            self.watcher.stop()


def run_worker():
    """Run the worker (entry point)."""
    worker = PipelineWorker()
    
    try:
        worker.start()
    except KeyboardInterrupt:
        logger.info("\n[yellow]Shutting down...[/yellow]")
        worker.stop()
    except Exception as e:
        logger.error(f"[red]Worker crashed: {e}[/red]")
        raise


if __name__ == "__main__":
    run_worker()
