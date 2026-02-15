"""
Configuration management for the transcription pipeline.

Uses Pydantic Settings to load configuration from environment variables
and optional config files.
"""

import os
from pathlib import Path
from typing import List, Optional
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """
    Configuration class for the transcription pipeline.
    
    Loads settings from environment variables and optional .env file.
    All paths have sensible defaults.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application settings
    app_name: str = Field(default="transcription-pipeline", description="Application name")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Path settings
    upload_dir: Path = Field(
        default=Path(os.getenv("UPLOAD_DIR", "/app/uploads")),
        description="Directory for uploaded audio files"
    )
    processing_dir: Path = Field(
        default=Path(os.getenv("PROCESSING_DIR", "/app/processing")),
        description="Directory for files being processed"
    )
    output_dir: Path = Field(
        default=Path(os.getenv("OUTPUT_DIR", "/app/outputs")),
        description="Directory for transcription outputs"
    )
    
    # File watcher settings
    supported_audio_formats: List[str] = Field(
        default=[".mp3", ".wav", ".m4a", ".ogg", ".flac"],
        description="Supported audio file extensions"
    )
    max_file_size_mb: int = Field(
        default=500,
        description="Maximum file size in MB"
    )
    watch_recursive: bool = Field(
        default=True,
        description="Watch subdirectories recursively"
    )
    
    # Model settings
    whisper_model: str = Field(
        default="base",
        description="Whisper model size (tiny, base, small, medium, large)"
    )
    diarization_model: str = Field(
        default="pyannote/speaker-diarization-3.1",
        description="Pyannote diarization model name"
    )
    hf_token: Optional[str] = Field(
        default=None,
        description="HuggingFace API token for model access"
    )
    
    # API settings
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_endpoint: str = Field(
        default="http://localhost:8000",
        description="Base URL for transcription API"
    )
    webhook_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for completion notifications"
    )
    
    # Processing settings
    max_workers: int = Field(
        default=2,
        description="Maximum number of parallel workers"
    )
    chunk_duration_sec: int = Field(
        default=30,
        description="Audio chunk duration in seconds"
    )
    language: Optional[str] = Field(
        default=None,
        description="Language code (auto-detect if None)"
    )
    
    # Output settings
    output_formats: List[str] = Field(
        default=["txt", "json", "docx", "md"],
        description="Output format types"
    )
    include_timestamps: bool = Field(
        default=True,
        description="Include timestamps in output"
    )
    include_speaker_labels: bool = Field(
        default=True,
        description="Include speaker labels in output"
    )
    
    @field_validator("upload_dir", "processing_dir", "output_dir", mode="before")
    @classmethod
    def validate_paths(cls, v: str | Path) -> Path:
        """Convert string paths to Path objects and create directories."""
        path = Path(v) if isinstance(v, str) else v
        return path
    
    @field_validator("supported_audio_formats", mode="before")
    @classmethod
    def validate_formats(cls, v: str | List[str]) -> List[str]:
        """Ensure formats start with a dot and are lowercase."""
        if isinstance(v, str):
            v = [fmt.strip() for fmt in v.split(",")]
        return [(fmt if fmt.startswith(".") else f".{fmt}").lower() for fmt in v]
    
    @field_validator("output_formats", mode="before")
    @classmethod
    def validate_output_formats(cls, v: str | List[str]) -> List[str]:
        """Parse comma-separated output formats."""
        if isinstance(v, str):
            v = [fmt.strip() for fmt in v.split(",")]
        return [fmt.lower() for fmt in v]
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper
    
    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        for path in [self.upload_dir, self.processing_dir, self.output_dir]:
            path.mkdir(parents=True, exist_ok=True)
    
    def is_valid_audio_file(self, file_path: Path) -> bool:
        """
        Check if a file is a valid audio file for processing.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if valid, False otherwise
        """
        if not file_path.is_file():
            return False
        
        # Check extension
        if file_path.suffix.lower() not in self.supported_audio_formats:
            return False
        
        # Check file size
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > self.max_file_size_mb:
                return False
        except OSError:
            return False
        
        return True


@lru_cache()
def get_config() -> Config:
    """
    Get cached configuration instance.
    
    Returns:
        Config instance loaded from environment
    """
    return Config()


# For testing and direct usage
if __name__ == "__main__":
    config = get_config()
    print(f"Configuration loaded:")
    print(f"  Upload dir: {config.upload_dir}")
    print(f"  Processing dir: {config.processing_dir}")
    print(f"  Output dir: {config.output_dir}")
    print(f"  Supported formats: {config.supported_audio_formats}")
    print(f"  Log level: {config.log_level}")
