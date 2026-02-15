"""
File watcher module for monitoring upload directories.

Uses watchdog to detect new audio files and move them to the processing directory.
"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, DirCreatedEvent
from rich.console import Console
from rich.logging import RichHandler
import logging

try:
    from .config import Config, get_config
except ImportError:
    from config import Config, get_config

# Setup rich console and logging
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("file_watcher")


class AudioFileHandler(FileSystemEventHandler):
    """
    Event handler for audio file detection.
    
    Handles file creation events and processes valid audio files.
    """
    
    def __init__(
        self,
        config: Config,
        on_file_detected: Optional[Callable[[Path], None]] = None,
        on_file_moved: Optional[Callable[[Path, Path], None]] = None
    ):
        """
        Initialize the file handler.
        
        Args:
            config: Configuration instance
            on_file_detected: Optional callback when file is detected
            on_file_moved: Optional callback when file is moved to processing
        """
        self.config = config
        self.on_file_detected = on_file_detected
        self.on_file_moved = on_file_moved
        self._processed_files: Set[str] = set()
        
        # Ensure directories exist
        self.config.ensure_directories()
    
    def on_created(self, event):
        """Handle file/directory creation events."""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Check if already processed (prevents duplicate processing)
        if str(file_path) in self._processed_files:
            return
        
        # Validate the file
        if not self._validate_file(file_path):
            return
        
        # Wait for file to be completely written
        if not self._wait_for_file_complete(file_path):
            logger.warning(f"File not stable, skipping: {file_path.name}")
            return
        
        # Process the file
        self._process_file(file_path)
    
    def _validate_file(self, file_path: Path) -> bool:
        """
        Validate if the file is a valid audio file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if valid, False otherwise
        """
        # Check if file exists and is readable
        if not file_path.exists():
            logger.debug(f"File does not exist: {file_path}")
            return False
        
        # Check extension
        ext = file_path.suffix.lower()
        if ext not in self.config.supported_audio_formats:
            logger.debug(f"Unsupported file format: {ext}")
            return False
        
        # Check file size
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > self.config.max_file_size_mb:
                logger.warning(
                    f"File too large: {file_path.name} ({size_mb:.1f} MB > "
                    f"{self.config.max_file_size_mb} MB limit)"
                )
                return False
        except OSError as e:
            logger.error(f"Cannot access file {file_path}: {e}")
            return False
        
        return True
    
    def _wait_for_file_complete(
        self,
        file_path: Path,
        timeout_sec: float = 30.0,
        check_interval: float = 0.5
    ) -> bool:
        """
        Wait for a file to be completely written.
        
        Args:
            file_path: Path to the file
            timeout_sec: Maximum time to wait
            check_interval: Interval between size checks
            
        Returns:
            True if file is stable, False if timeout
        """
        start_time = time.time()
        last_size = -1
        stable_count = 0
        required_stable_checks = 3  # File size must be stable for this many checks
        
        while time.time() - start_time < timeout_sec:
            try:
                current_size = file_path.stat().st_size
                
                if current_size == last_size and current_size > 0:
                    stable_count += 1
                    if stable_count >= required_stable_checks:
                        return True
                else:
                    stable_count = 0
                    last_size = current_size
                    
            except OSError:
                # File might be temporarily inaccessible
                pass
            
            time.sleep(check_interval)
        
        return False
    
    def _process_file(self, file_path: Path) -> None:
        """
        Process a detected audio file.
        
        Args:
            file_path: Path to the detected file
        """
        timestamp = datetime.now().isoformat()
        file_size = file_path.stat().st_size / (1024 * 1024)  # MB
        
        logger.info(
            f"[bold green]Audio file detected:[/bold green] {file_path.name} "
            f"({file_size:.2f} MB) at {timestamp}"
        )
        
        # Mark as processed to prevent duplicates
        self._processed_files.add(str(file_path))
        
        # Trigger callback if provided
        if self.on_file_detected:
            try:
                self.on_file_detected(file_path)
            except Exception as e:
                logger.error(f"Error in on_file_detected callback: {e}")
        
        # Move to processing directory
        self._move_to_processing(file_path)
    
    def _move_to_processing(self, file_path: Path) -> Optional[Path]:
        """
        Move file to the processing directory.
        
        Args:
            file_path: Original file path
            
        Returns:
            New path in processing directory, or None if failed
        """
        # Generate unique filename to avoid collisions
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_name = f"{timestamp}_{file_path.name}"
        dest_path = self.config.processing_dir / unique_name
        
        try:
            shutil.move(str(file_path), str(dest_path))
            logger.info(
                f"[bold blue]File moved:[/bold blue] {file_path.name} -> "
                f"{dest_path.relative_to(self.config.processing_dir.parent)}"
            )
            
            # Trigger callback if provided
            if self.on_file_moved:
                try:
                    self.on_file_moved(file_path, dest_path)
                except Exception as e:
                    logger.error(f"Error in on_file_moved callback: {e}")
            
            return dest_path
            
        except Exception as e:
            logger.error(f"Failed to move file {file_path.name}: {e}")
            return None


class FileWatcher:
    """
    File watcher service for monitoring upload directories.
    
    Uses watchdog to detect and process new audio files.
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        on_file_detected: Optional[Callable[[Path], None]] = None,
        on_file_moved: Optional[Callable[[Path, Path], None]] = None
    ):
        """
        Initialize the file watcher.
        
        Args:
            config: Configuration instance (uses default if None)
            on_file_detected: Callback when file is detected
            on_file_moved: Callback when file is moved to processing
        """
        self.config = config or get_config()
        self.event_handler = AudioFileHandler(
            config=self.config,
            on_file_detected=on_file_detected,
            on_file_moved=on_file_moved
        )
        self.observer: Optional[Observer] = None
        self._running = False
    
    def start(self) -> None:
        """Start watching for files."""
        if self._running:
            logger.warning("File watcher is already running")
            return
        
        # Ensure upload directory exists
        self.config.upload_dir.mkdir(parents=True, exist_ok=True)
        
        self.observer = Observer()
        self.observer.schedule(
            self.event_handler,
            str(self.config.upload_dir),
            recursive=self.config.watch_recursive
        )
        
        logger.info(
            f"[bold cyan]Starting file watcher...[/bold cyan]\n"
            f"  Watching: {self.config.upload_dir}\n"
            f"  Recursive: {self.config.watch_recursive}\n"
            f"  Supported formats: {', '.join(self.config.supported_audio_formats)}"
        )
        
        self.observer.start()
        self._running = True
    
    def stop(self) -> None:
        """Stop watching for files."""
        if not self._running:
            return
        
        logger.info("[bold yellow]Stopping file watcher...[/bold yellow]")
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        self._running = False
        logger.info("File watcher stopped")
    
    def run_forever(self) -> None:
        """Run the watcher until interrupted."""
        self.start()
        
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()
    
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running and self.observer is not None and self.observer.is_alive()
    
    def scan_existing_files(self) -> int:
        """
        Scan and process existing files in the upload directory.
        
        Returns:
            Number of files processed
        """
        if not self.config.upload_dir.exists():
            logger.warning(f"Upload directory does not exist: {self.config.upload_dir}")
            return 0
        
        count = 0
        pattern = "**/*" if self.config.watch_recursive else "*"
        
        logger.info(f"Scanning existing files in {self.config.upload_dir}...")
        
        for file_path in self.config.upload_dir.glob(pattern):
            if file_path.is_file():
                if self.event_handler._validate_file(file_path):
                    self.event_handler._process_file(file_path)
                    count += 1
        
        logger.info(f"Processed {count} existing files")
        return count


def create_watcher(
    upload_dir: Optional[str] = None,
    processing_dir: Optional[str] = None,
    on_file_detected: Optional[Callable[[Path], None]] = None,
    on_file_moved: Optional[Callable[[Path, Path], None]] = None
) -> FileWatcher:
    """
    Create a file watcher with custom or default settings.
    
    Args:
        upload_dir: Custom upload directory (optional)
        processing_dir: Custom processing directory (optional)
        on_file_detected: Callback when file is detected
        on_file_moved: Callback when file is moved
        
    Returns:
        Configured FileWatcher instance
    """
    config = get_config()
    
    # Override paths if provided
    if upload_dir:
        config.upload_dir = Path(upload_dir)
    if processing_dir:
        config.processing_dir = Path(processing_dir)
    
    return FileWatcher(
        config=config,
        on_file_detected=on_file_detected,
        on_file_moved=on_file_moved
    )


# Example usage
if __name__ == "__main__":
    # Define example callbacks
    def on_detected(file_path: Path):
        console.print(f"[Callback] Detected: {file_path.name}")
    
    def on_moved(src: Path, dst: Path):
        console.print(f"[Callback] Moved to: {dst.name}")
    
    # Create and run watcher
    watcher = create_watcher(
        on_file_detected=on_detected,
        on_file_moved=on_moved
    )
    
    # Process any existing files first
    watcher.scan_existing_files()
    
    # Start watching for new files
    console.print("\n[dim]Press Ctrl+C to stop...[/dim]\n")
    watcher.run_forever()
