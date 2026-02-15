"""
Merge module for combining Whisper transcription segments with speaker diarization.

This module provides functions to align and merge transcript segments from Whisper
with speaker segments from a diarization model (e.g., pyannote.audio).
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum overlap ratio threshold for speaker assignment (50%)
MIN_OVERLAP_THRESHOLD = 0.5


def calculate_overlap(start1: float, end1: float, start2: float, end2: float) -> float:
    """
    Calculate the duration of overlap between two time intervals.

    Args:
        start1: Start time of the first interval (seconds).
        end1: End time of the first interval (seconds).
        start2: Start time of the second interval (seconds).
        end2: End time of the second interval (seconds).

    Returns:
        The duration of the intersection in seconds. Returns 0 if no overlap.

    Example:
        >>> calculate_overlap(0.0, 10.0, 5.0, 15.0)
        5.0
        >>> calculate_overlap(0.0, 5.0, 5.0, 10.0)
        0.0
    """
    # Calculate the intersection bounds
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)

    # Return the overlap duration (0 if no overlap)
    return max(0.0, overlap_end - overlap_start)


def _find_best_speaker_for_segment(
    whisper_segment: Dict,
    diarization_segments: List[Dict],
) -> Optional[str]:
    """
    Find the speaker with the highest overlap for a given whisper segment.

    Args:
        whisper_segment: A Whisper segment with 'start', 'end', and 'text' keys.
        diarization_segments: List of diarization segments with 'speaker', 'start', 'end'.

    Returns:
        The speaker ID with highest overlap, or None if no speaker meets threshold.
    """
    w_start = whisper_segment["start"]
    w_end = whisper_segment["end"]
    w_duration = w_end - w_start

    if w_duration <= 0:
        return None

    # Track overlap per speaker (handle overlapping diarization by summing overlaps)
    speaker_overlaps: Dict[str, float] = {}

    for diar_seg in diarization_segments:
        d_start = diar_seg["start"]
        d_end = diar_seg["end"]
        speaker = diar_seg["speaker"]

        overlap = calculate_overlap(w_start, w_end, d_start, d_end)

        if overlap > 0:
            # For overlapping diarization segments from same speaker, sum overlaps
            # For different speakers, we'll compare individual overlaps
            speaker_overlaps[speaker] = speaker_overlaps.get(speaker, 0.0) + overlap

    if not speaker_overlaps:
        return None

    # Find speaker with highest overlap
    best_speaker = max(speaker_overlaps, key=speaker_overlaps.get)
    max_overlap = speaker_overlaps[best_speaker]

    # Check if overlap meets threshold (50% of whisper segment duration)
    overlap_ratio = max_overlap / w_duration

    if overlap_ratio >= MIN_OVERLAP_THRESHOLD:
        return best_speaker
    else:
        return None


def _merge_consecutive_segments(
    segments: List[Dict],
) -> List[Dict]:
    """
    Merge consecutive segments that have the same speaker.

    Args:
        segments: List of merged segments with speaker assignments.

    Returns:
        List of segments with consecutive same-speaker segments merged.
    """
    if not segments:
        return []

    merged = []
    current = None

    for segment in segments:
        if current is None:
            current = {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"],
                "speaker": segment["speaker"],
            }
        elif segment["speaker"] == current["speaker"]:
            # Merge with current segment
            current["end"] = segment["end"]
            # Add space between texts if needed
            if current["text"] and segment["text"]:
                current["text"] = f"{current['text']} {segment['text']}".strip()
            else:
                current["text"] = (current["text"] + segment["text"]).strip()
        else:
            # Different speaker, save current and start new
            merged.append(current)
            current = {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"],
                "speaker": segment["speaker"],
            }

    # Don't forget the last segment
    if current is not None:
        merged.append(current)

    return merged


def merge_transcript_with_speakers(
    whisper_segments: List[Dict],
    diarization_segments: List[Dict],
) -> List[Dict]:
    """
    Merge Whisper transcription segments with speaker diarization segments.

    This function aligns transcript segments from Whisper with speaker labels
    from a diarization model. Each whisper segment is assigned to the speaker
    who was talking during most of that segment (must exceed 50% overlap).

    Args:
        whisper_segments: List of Whisper segments, each with 'start', 'end',
            and 'text' keys. Example:
            [
                {"start": 0.0, "end": 5.0, "text": "Hello world"},
                {"start": 5.5, "end": 10.0, "text": "How are you?"},
            ]
        diarization_segments: List of diarization segments, each with 'speaker',
            'start', and 'end' keys. Example:
            [
                {"speaker": "SPEAKER_00", "start": 0.0, "end": 6.0},
                {"speaker": "SPEAKER_01", "start": 5.5, "end": 12.0},
            ]

    Returns:
        List of merged segments with speaker labels:
        [
            {
                "start": float,
                "end": float,
                "text": str,
                "speaker": str (e.g., "SPEAKER_00" or "UNKNOWN")
            }
        ]

    Edge Cases:
        - Empty whisper_segments: Returns empty list.
        - Empty diarization_segments: Returns all segments with "SPEAKER_00".
        - Missing speaker for segment: Uses "UNKNOWN".
        - Overlapping diarization segments: Handles by taking longest overlap
          for each speaker.

    Example:
        >>> whisper = [
        ...     {"start": 0.0, "end": 5.0, "text": "Hello everyone"},
        ...     {"start": 6.0, "end": 10.0, "text": "Nice to meet you"},
        ... ]
        >>> diarization = [
        ...     {"speaker": "SPEAKER_00", "start": 0.0, "end": 5.5},
        ...     {"speaker": "SPEAKER_01", "start": 6.0, "end": 10.0},
        ... ]
        >>> merge_transcript_with_speakers(whisper, diarization)
        [
            {"start": 0.0, "end": 5.0, "text": "Hello everyone", "speaker": "SPEAKER_00"},
            {"start": 6.0, "end": 10.0, "text": "Nice to meet you", "speaker": "SPEAKER_01"},
        ]
    """
    # Edge case: Empty whisper segments
    if not whisper_segments:
        logger.debug("Empty whisper segments provided, returning empty list")
        return []

    # Edge case: Empty diarization - assign all to single speaker
    if not diarization_segments:
        logger.debug("Empty diarization segments, assigning all to SPEAKER_00")
        return [
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
                "speaker": "SPEAKER_00",
            }
            for seg in whisper_segments
        ]

    # Sort both segment lists by start time for efficient processing
    sorted_whisper = sorted(whisper_segments, key=lambda x: x["start"])
    sorted_diarization = sorted(diarization_segments, key=lambda x: x["start"])

    merged_segments = []

    for whisper_seg in sorted_whisper:
        best_speaker = _find_best_speaker_for_segment(
            whisper_seg,
            sorted_diarization,
        )

        # Use UNKNOWN if no speaker meets the threshold
        speaker = best_speaker if best_speaker is not None else "UNKNOWN"

        merged_segments.append({
            "start": whisper_seg["start"],
            "end": whisper_seg["end"],
            "text": whisper_seg["text"],
            "speaker": speaker,
        })

    # Merge consecutive segments with same speaker
    result = _merge_consecutive_segments(merged_segments)

    logger.debug(
        "Merged %d whisper segments with %d diarization segments into %d final segments",
        len(whisper_segments),
        len(diarization_segments),
        len(result),
    )

    return result
