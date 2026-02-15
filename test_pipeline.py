#!/usr/bin/env python3
"""
Test script for the transcription pipeline.

Usage:
    python test_pipeline.py <audio_file> [note_type]

Example:
    python test_pipeline.py uploads/meeting/test.mp3 meeting
    python test_pipeline.py uploads/braindump/ideas.ogg braindump
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import process_file_sync

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_pipeline.py <audio_file> [note_type]")
        print("  note_type: meeting, supervision, client, lecture, braindump")
        print("\nExample:")
        print("  python test_pipeline.py uploads/meeting/test.mp3 meeting")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    note_type = sys.argv[2] if len(sys.argv) > 2 else "meeting"
    
    # Validate file exists
    if not os.path.exists(audio_file):
        print(f"Error: File not found: {audio_file}")
        sys.exit(1)
    
    # Validate note type
    valid_types = ["meeting", "supervision", "client", "lecture", "braindump"]
    if note_type not in valid_types:
        print(f"Error: Invalid note type '{note_type}'")
        print(f"Valid types: {', '.join(valid_types)}")
        sys.exit(1)
    
    print(f"Testing pipeline with: {audio_file}")
    print(f"Note type: {note_type}")
    print("=" * 50)
    
    result = process_file_sync(audio_file, note_type)
    
    print("\n" + "=" * 50)
    print("RESULT:")
    print(f"  Success: {result['success']}")
    print(f"  Duration: {result['duration']:.1f}s")
    
    if result['outputs']:
        print(f"\n  Outputs:")
        if result['outputs'].get('markdown'):
            print(f"    - Markdown: {result['outputs']['markdown']}")
        if result['outputs'].get('docx'):
            print(f"    - Word Doc: {result['outputs']['docx']}")
    
    if result['error']:
        print(f"\n  Error: {result['error']}")
    
    return 0 if result['success'] else 1

if __name__ == "__main__":
    sys.exit(main())
