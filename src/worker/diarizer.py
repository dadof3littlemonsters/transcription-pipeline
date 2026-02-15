"""Speaker diarization module using Pyannote."""

import logging
import re
from pathlib import Path
from typing import Union

import torch
from pyannote.audio import Pipeline

logger = logging.getLogger(__name__)


class DiarizationError(Exception):
    """Custom exception for diarization errors."""
    pass


class SpeakerDiarizer:
    """Speaker diarization using Pyannote.
    
    Lazily loads the model on first use and caches the pipeline instance.
    """

    def __init__(
        self,
        hf_token: str,
        model: str = "pyannote/speaker-diarization-3.1",
        device: str = "auto"
    ):
        """Initialize the diarizer.
        
        Args:
            hf_token: HuggingFace token for model access
            model: Model name to use
            device: Device to run on ('cuda', 'cpu', or 'auto')
        
        Raises:
            DiarizationError: If hf_token is missing or invalid
        """
        if not hf_token:
            raise DiarizationError("HuggingFace token is required")
        
        self.hf_token = hf_token
        self.model = model
        
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        self._pipeline: Pipeline | None = None

    def _load_pipeline(self) -> Pipeline:
        """Load the pyannote pipeline (cached after first call).
        
        Returns:
            Loaded Pipeline instance
        
        Raises:
            DiarizationError: If model download fails
        """
        if self._pipeline is not None:
            return self._pipeline

        logger.info("Loading model...")
        logger.info(f"Using HuggingFace token: {self.hf_token[:10]}... (length: {len(self.hf_token)})")
        
        try:
            pipeline = Pipeline.from_pretrained(
                self.model,
                token=self.hf_token
            )
        except Exception as e:
            logger.error(f"Failed to load pyannote model: {e}")
            logger.error(f"Token used: {self.hf_token[:10]}... (length: {len(self.hf_token)})")
            raise DiarizationError(
                f"Failed to load model '{self.model}': {e}"
            ) from e

        try:
            pipeline.to(torch.device(self.device))
        except Exception as e:
            raise DiarizationError(
                f"Failed to move model to device '{self.device}': {e}"
            ) from e

        self._pipeline = pipeline
        logger.info(f"Model loaded on {self.device}")
        
        return self._pipeline

    def _format_speaker_label(self, label: str) -> str:
        """Format speaker label as SPEAKER_XX.
        
        Args:
            label: Original label from pyannote (e.g., 'A', 'B' or 'SPEAKER_00')
        
        Returns:
            Formatted label like 'SPEAKER_00', 'SPEAKER_01', etc.
        """
        # Try to extract numeric suffix if already formatted
        match = re.search(r'\d+', label)
        if match:
            speaker_num = int(match.group())
        else:
            # Convert letter labels (A, B, C...) to numbers
            speaker_num = ord(label.upper()) - ord('A') if len(label) == 1 else 0
        
        return f"SPEAKER_{speaker_num:02d}"

    def diarize(self, audio_path: Union[str, Path]) -> list[dict]:
        """Run speaker diarization on audio file.
        
        Args:
            audio_path: Path to audio file
        
        Returns:
            List of segments with speaker, start, and end times.
            Each segment is a dict with keys:
                - speaker: str (e.g., 'SPEAKER_00')
                - start: float (seconds)
                - end: float (seconds)
            
            Segments are sorted by start time.
        
        Raises:
            DiarizationError: If audio file is invalid or processing fails
        """
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            raise DiarizationError(f"Audio file not found: {audio_path}")
        
        if not audio_path.is_file():
            raise DiarizationError(f"Path is not a file: {audio_path}")

        pipeline = self._load_pipeline()
        
        logger.info("Processing audio...")
        
        try:
            diarization_output = pipeline(audio_path)
        except Exception as e:
            raise DiarizationError(
                f"Failed to process audio '{audio_path}': {e}"
            ) from e

        segments = []
        speaker_ids = set()
        
        # Handle pyannote 4.x DiarizeOutput object
        # It contains speaker_diarization which is the Annotation with itertracks
        if hasattr(diarization_output, 'speaker_diarization'):
            annotation = diarization_output.speaker_diarization
        else:
            # Fallback for older pyannote versions that return Annotation directly
            annotation = diarization_output
        
        # Iterate through the annotation to extract segments
        for segment, track, label in annotation.itertracks(yield_label=True):
            formatted_label = self._format_speaker_label(label)
            segments.append({
                "speaker": formatted_label,
                "start": float(segment.start),
                "end": float(segment.end)
            })
            speaker_ids.add(formatted_label)

        # Sort by start time
        segments.sort(key=lambda x: x["start"])
        
        logger.info(f"Found {len(speaker_ids)} speaker(s)")
        
        # Handle single-speaker files gracefully
        # (segments will just have one speaker label)
        
        return segments
