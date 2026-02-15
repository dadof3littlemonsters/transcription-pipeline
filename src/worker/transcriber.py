"""
Groq Whisper API Transcription Client

This module provides a client for transcribing audio files using the Groq Whisper API.
It includes robust error handling, retries, audio validation, and rich logging output.
"""

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

import requests
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

# Configure rich logging
console = Console()
logger = logging.getLogger("groq_transcriber")


# Custom exception for Groq API errors
class GroqAPIError(Exception):
    """Exception raised for Groq API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


# Supported audio formats
SUPPORTED_FORMATS = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.ogg', '.flac'}
MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# API configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_TIMEOUT = 300  # 5 minutes for large files

# Retry configuration
MAX_RETRIES_5XX = 3
BACKOFF_DELAYS = [1, 2, 4]  # Exponential backoff delays for 429 errors


def compress_audio_file(audio_path: Path, target_size_mb: float = 20.0) -> Path:
    """
    Compress an audio file to meet Groq's size requirements.
    
    Uses pydub to convert to OGG format with reduced bitrate.
    OGG provides good compression while maintaining quality.
    
    Args:
        audio_path: Path to the original audio file
        target_size_mb: Target file size in MB (default 20MB to stay under 25MB limit)
        
    Returns:
        Path to the compressed file (in temp directory)
        
    Raises:
        ValueError: If pydub is not available or compression fails
    """
    if not PYDUB_AVAILABLE:
        raise ValueError(
            "Audio compression requires pydub. "
            "Install with: pip install pydub"
        )
    
    logger.info(f"Compressing audio file: {audio_path.name}")
    
    try:
        # Load audio file
        audio = AudioSegment.from_file(str(audio_path))
        
        # Calculate duration and current size
        duration_sec = len(audio) / 1000.0
        original_size_mb = audio_path.stat().st_size / (1024 * 1024)
        
        logger.info(f"  Original: {original_size_mb:.1f}MB, {duration_sec:.1f}s duration")
        
        # Create temp file with .ogg extension
        temp_fd, temp_path = tempfile.mkstemp(suffix='.ogg')
        os.close(temp_fd)
        temp_file = Path(temp_path)
        
        # Calculate bitrate needed to achieve target size
        # Formula: bitrate (kbps) = (target_size_bytes * 8) / duration_seconds / 1000
        target_size_bytes = target_size_mb * 1024 * 1024
        target_bitrate_kbps = int((target_size_bytes * 8) / duration_sec / 1000)
        
        # Ensure minimum quality (32 kbps mono is reasonable for speech)
        bitrate = max(32, min(target_bitrate_kbps, 128))
        
        # Export with calculated bitrate
        # Convert to mono for speech transcription (reduces size by 50%)
        audio = audio.set_channels(1)
        audio.export(str(temp_file), format='ogg', bitrate=f'{bitrate}k')
        
        compressed_size_mb = temp_file.stat().st_size / (1024 * 1024)
        logger.info(f"  Compressed: {compressed_size_mb:.1f}MB ({bitrate}k mono OGG)")
        
        # Verify compressed file is under limit
        if temp_file.stat().st_size > MAX_FILE_SIZE_BYTES:
            # Try with lower bitrate
            bitrate = 24  # Very low for speech
            audio.export(str(temp_file), format='ogg', bitrate=f'{bitrate}k')
            compressed_size_mb = temp_file.stat().st_size / (1024 * 1024)
            logger.info(f"  Re-compressed: {compressed_size_mb:.1f}MB ({bitrate}k mono OGG)")
            
            if temp_file.stat().st_size > MAX_FILE_SIZE_BYTES:
                temp_file.unlink()
                raise ValueError(
                    f"Cannot compress file under {MAX_FILE_SIZE_MB}MB limit. "
                    f"File may be too long or already compressed."
                )
        
        return temp_file
        
    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_file' in locals() and temp_file.exists():
            temp_file.unlink()
        raise ValueError(f"Audio compression failed: {e}")


class GroqTranscriber:
    """
    A client for transcribing audio files using the Groq Whisper API.
    
    This class handles audio file validation, API communication with retries,
    and returns structured transcription data with segments and metadata.
    
    Attributes:
        api_key: The Groq API key for authentication
        model: The Whisper model to use (default: whisper-large-v3-turbo)
    
    Example:
        >>> transcriber = GroqTranscriber(api_key="your-api-key")
        >>> result = transcriber.transcribe(Path("audio.mp3"))
        >>> print(result["text"])
    """
    
    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo"):
        """
        Initialize the GroqTranscriber.
        
        Args:
            api_key: The Groq API key for authentication
            model: The Whisper model to use (default: whisper-large-v3-turbo)
        """
        self.api_key = api_key
        self.model = model
        self.session = requests.Session()
        logger.info(f"GroqTranscriber initialized with model: {model}")
    
    def _validate_audio_file(self, audio_path: Path) -> None:
        """
        Validate the audio file before transcription.
        
        Checks:
        - File exists and is readable
        - File size is under 25MB (Groq limit)
        - File format is supported
        
        Args:
            audio_path: Path to the audio file
            
        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file is not readable
            ValueError: If file size or format is invalid
        """
        logger.info(f"Validating audio file: {audio_path}")
        
        # Check file exists
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Check it's a file (not a directory)
        if not audio_path.is_file():
            raise ValueError(f"Path is not a file: {audio_path}")
        
        # Check file is readable
        try:
            with open(audio_path, 'rb') as f:
                f.read(1)
        except PermissionError:
            raise PermissionError(f"Audio file is not readable: {audio_path}")
        except Exception as e:
            raise ValueError(f"Cannot read audio file: {audio_path} - {e}")
        
        # Check file size
        file_size = audio_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"Audio file too large: {file_size / (1024 * 1024):.2f}MB "
                f"(max {MAX_FILE_SIZE_MB}MB)"
            )
        
        # Check file format
        file_ext = audio_path.suffix.lower()
        if file_ext not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format: {file_ext}. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )
        
        logger.info(f"Audio file validated: {file_size / (1024 * 1024):.2f}MB, format: {file_ext}")
    
    def _make_api_request(
        self, 
        audio_path: Path, 
        attempt: int = 1,
        is_retry: bool = False
    ) -> Dict:
        """
        Make the API request to Groq with retry logic.
        
        Args:
            audio_path: Path to the audio file
            attempt: Current attempt number
            is_retry: Whether this is a retry after rate limiting
            
        Returns:
            The JSON response from the API
            
        Raises:
            GroqAPIError: If the API request fails after all retries
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": self.model,
            "response_format": "json"
            # timestamp_granularities removed - not supported by Groq API
        }
        
        try:
            with open(audio_path, 'rb') as f:
                files = {
                    "file": (audio_path.name, f, f"audio/{audio_path.suffix.lstrip('.')}")
                }
                
                logger.info(f"Making API call to Groq (attempt {attempt})")
                if is_retry:
                    logger.info(f"Retrying after rate limit backoff")
                
                response = self.session.post(
                    GROQ_API_URL,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=DEFAULT_TIMEOUT
                )
                
                # Log response status
                logger.info(f"API response status: {response.status_code}")
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    if attempt <= len(BACKOFF_DELAYS):
                        delay = BACKOFF_DELAYS[attempt - 1]
                        logger.warning(
                            f"Rate limit hit (429). Retrying in {delay}s..."
                        )
                        time.sleep(delay)
                        return self._make_api_request(audio_path, attempt + 1, is_retry=True)
                    else:
                        raise GroqAPIError(
                            "Rate limit exceeded. Max retries reached.",
                            status_code=429,
                            response_text=response.text
                        )
                
                # Handle 5xx server errors with retry
                if 500 <= response.status_code < 600:
                    if attempt < MAX_RETRIES_5XX:
                        delay = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                        logger.warning(
                            f"Server error ({response.status_code}). "
                            f"Retrying in {delay}s... (attempt {attempt + 1}/{MAX_RETRIES_5XX})"
                        )
                        time.sleep(delay)
                        return self._make_api_request(audio_path, attempt + 1)
                    else:
                        raise GroqAPIError(
                            f"Server error persisted after {MAX_RETRIES_5XX} attempts",
                            status_code=response.status_code,
                            response_text=response.text
                        )
                
                # Handle other errors
                if not response.ok:
                    raise GroqAPIError(
                        f"API request failed: {response.status_code} - {response.text}",
                        status_code=response.status_code,
                        response_text=response.text
                    )
                
                # Parse and return response
                result = response.json()
                logger.info("API call successful")
                return result
                
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES_5XX:
                delay = 2 ** attempt
                logger.warning(
                    f"Request timeout. Retrying in {delay}s... (attempt {attempt + 1}/{MAX_RETRIES_5XX})"
                )
                time.sleep(delay)
                return self._make_api_request(audio_path, attempt + 1)
            raise GroqAPIError(
                f"Request timeout after {MAX_RETRIES_5XX} attempts",
                status_code=None,
                response_text=None
            )
            
        except requests.exceptions.ConnectionError as e:
            if attempt < MAX_RETRIES_5XX:
                delay = 2 ** attempt
                logger.warning(
                    f"Connection error: {e}. Retrying in {delay}s... (attempt {attempt + 1}/{MAX_RETRIES_5XX})"
                )
                time.sleep(delay)
                return self._make_api_request(audio_path, attempt + 1)
            raise GroqAPIError(
                f"Connection error persisted after {MAX_RETRIES_5XX} attempts: {e}",
                status_code=None,
                response_text=None
            )
            
        except requests.exceptions.RequestException as e:
            raise GroqAPIError(
                f"Request failed: {e}",
                status_code=None,
                response_text=None
            )
    
    def _parse_response(self, response: Dict, audio_path: Path) -> Dict:
        """
        Parse the API response into the expected format.
        
        Args:
            response: The raw API response
            audio_path: Path to the audio file (for duration calculation)
            
        Returns:
            Parsed transcription result with text, segments, language, and duration
        """
        # Extract full text
        text = response.get("text", "").strip()
        
        # Extract segments
        raw_segments = response.get("segments", [])
        segments = []
        
        for idx, seg in enumerate(raw_segments):
            segments.append({
                "id": seg.get("id", idx),
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": seg.get("text", "").strip()
            })
        
        # If no segments but we have text, create a single segment
        if not segments and text:
            # Try to get duration from the response or estimate
            duration = response.get("duration", 0.0)
            segments = [{
                "id": 0,
                "start": 0.0,
                "end": float(duration) if duration else 0.0,
                "text": text
            }]
        
        # Calculate duration from last segment end time
        duration = 0.0
        if segments:
            duration = max(seg["end"] for seg in segments)
        
        result = {
            "text": text,
            "segments": segments,
            "language": response.get("language", "unknown"),
            "duration": float(duration)
        }
        
        logger.info(
            f"Parsed transcription: {len(segments)} segments, "
            f"duration: {duration:.2f}s, language: {result['language']}"
        )
        
        return result
    
    def transcribe(self, audio_path: Union[str, Path]) -> Dict:
        """
        Transcribe an audio file using the Groq Whisper API.
        
        Automatically compresses files over 25MB before transcription.
        
        Args:
            audio_path: Path to the audio file to transcribe
            
        Returns:
            Dictionary containing:
                - text: Full transcript string
                - segments: List of segment dictionaries with id, start, end, text
                - language: Detected language code
                - duration: Audio duration in seconds
                
        Raises:
            FileNotFoundError: If the audio file doesn't exist
            PermissionError: If the audio file is not readable
            ValueError: If the audio file is too large or in an unsupported format
            GroqAPIError: If the API request fails after all retries
            
        Example:
            >>> transcriber = GroqTranscriber(api_key="your-key")
            >>> result = transcriber.transcribe("audio.mp3")
            >>> print(f"Transcript: {result['text']}")
            >>> for seg in result['segments']:
            ...     print(f"[{seg['start']:.2f}s - {seg['end']:.2f}s]: {seg['text']}")
        """
        audio_path = Path(audio_path)
        compressed_file = None
        file_to_transcribe = audio_path
        
        # Check if file needs compression
        file_size = audio_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            logger.info(f"File size {file_size / (1024 * 1024):.1f}MB exceeds {MAX_FILE_SIZE_MB}MB limit, compressing...")
            try:
                compressed_file = compress_audio_file(audio_path)
                file_to_transcribe = compressed_file
                logger.info(f"Using compressed file: {compressed_file.name}")
            except ValueError as e:
                logger.error(f"Compression failed: {e}")
                raise ValueError(
                    f"Audio file too large: {file_size / (1024 * 1024):.2f}MB "
                    f"(max {MAX_FILE_SIZE_MB}MB). Compression failed: {e}"
                )
        
        # Validate the audio file (or compressed version)
        self._validate_audio_file(file_to_transcribe)
        
        # Show progress spinner during transcription
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"Transcribing {audio_path.name}...",
                total=None
            )
            
            try:
                # Make the API request with the file (original or compressed)
                response = self._make_api_request(file_to_transcribe)
                
                # Parse the response (pass original path for metadata)
                result = self._parse_response(response, audio_path)
                
                progress.update(task, completed=True)
                
                logger.info(
                    f"Transcription complete: {len(result['text'])} characters, "
                    f"{len(result['segments'])} segments"
                )
                
                return result
                
            except Exception as e:
                progress.update(task, completed=True)
                logger.error(f"Transcription failed: {e}")
                raise
            
            finally:
                # Clean up compressed file if it was created
                if compressed_file and compressed_file.exists():
                    compressed_file.unlink()
                    logger.info(f"Cleaned up compressed file: {compressed_file.name}")
    
    def close(self):
        """Close the HTTP session."""
        self.session.close()
        logger.info("GroqTranscriber session closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


# Convenience function for one-off transcriptions
def transcribe_audio(
    audio_path: Union[str, Path],
    api_key: str,
    model: str = "whisper-large-v3-turbo"
) -> Dict:
    """
    Convenience function to transcribe an audio file without creating a class instance.
    
    Args:
        audio_path: Path to the audio file
        api_key: Groq API key
        model: Whisper model to use (default: whisper-large-v3-turbo)
        
    Returns:
        Transcription result dictionary
        
    Example:
        >>> result = transcribe_audio("audio.mp3", api_key="your-key")
        >>> print(result["text"])
    """
    with GroqTranscriber(api_key=api_key, model=model) as transcriber:
        return transcriber.transcribe(audio_path)


if __name__ == "__main__":
    # Example usage
    import os
    
    # Check if we have an API key in environment
    api_key = os.environ.get("GROQ_API_KEY")
    
    if not api_key:
        console.print("[red]Please set GROQ_API_KEY environment variable[/red]")
        exit(1)
    
    # Example: transcribe a file
    # result = transcribe_audio("path/to/audio.mp3", api_key=api_key)
    # console.print(result)
    
    console.print("[green]GroqTranscriber module loaded successfully[/green]")
    console.print(f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}")
    console.print(f"Max file size: {MAX_FILE_SIZE_MB}MB")
