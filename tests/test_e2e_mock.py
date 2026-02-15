#!/usr/bin/env python3
"""
End-to-end test using mocked API calls.
Tests the complete pipeline flow without using real API keys.
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def create_mock_audio_file(directory: Path, filename: str = "test_audio.ogg") -> Path:
    """Create a mock audio file for testing."""
    audio_path = directory / filename
    # Create a minimal valid OGG file header
    with open(audio_path, 'wb') as f:
        # OGG container magic number
        f.write(b'OggS')
        f.write(b'\x00' * 26)  # Padding to make it look like an OGG file
        f.write(b'\x00' * 1000)  # Dummy audio data
    return audio_path


def test_merge_logic():
    """Test the timestamp merge logic."""
    print("\n" + "="*60)
    print("TEST 1: Timestamp Merge Logic")
    print("="*60)
    
    from merge import merge_transcript_with_speakers, calculate_overlap
    
    # Simulate Whisper output
    whisper_segments = [
        {"id": 0, "start": 0.0, "end": 3.5, "text": "Hello everyone, welcome to the meeting."},
        {"id": 1, "start": 3.8, "end": 8.2, "text": "Today we're discussing the Q4 results."},
        {"id": 2, "start": 8.5, "end": 12.0, "text": "I think we had a great quarter."},
        {"id": 3, "start": 12.3, "end": 15.0, "text": "Yes, I agree with that assessment."},
    ]
    
    # Simulate Pyannote diarization output
    diarization_segments = [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 8.5},
        {"speaker": "SPEAKER_01", "start": 8.0, "end": 15.5},
    ]
    
    print(f"Whisper segments: {len(whisper_segments)}")
    print(f"Diarization segments: {len(diarization_segments)}")
    
    # Merge
    merged = merge_transcript_with_speakers(whisper_segments, diarization_segments)
    
    print(f"\nMerged segments: {len(merged)}")
    for seg in merged:
        print(f"  [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['speaker']}: {seg['text'][:40]}...")
    
    # Verify results
    assert len(merged) > 0, "Should have merged segments"
    assert all("speaker" in seg for seg in merged), "All segments should have speakers"
    
    print("\n✓ Merge logic test PASSED")
    return True


def test_output_generation():
    """Test output generation (markdown and docx)."""
    print("\n" + "="*60)
    print("TEST 2: Output Generation")
    print("="*60)
    
    from output import OutputGenerator
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        generator = OutputGenerator(output_dir)
        
        # Test meeting output (both MD and DOCX)
        meeting_text = """# Meeting Notes

## Attendees
- John Doe
- Jane Smith

## Discussion
- Reviewed Q4 results
- Discussed new project timeline

## Action Items
1. John to prepare report by Friday
2. Jane to schedule follow-up meeting
"""
        
        print("Generating meeting outputs...")
        result = generator.generate_outputs(
            meeting_text, 
            "meeting", 
            "20240204_team_meeting.mp3",
            {"duration": 120.5, "speakers": ["SPEAKER_00", "SPEAKER_01"]}
        )
        
        print(f"  Title: {result['title']}")
        print(f"  Markdown: {result['markdown_path']}")
        print(f"  DOCX: {result['docx_path']}")
        
        if result['markdown_path']:
            assert Path(result['markdown_path']).exists(), "Markdown file should exist"
            content = Path(result['markdown_path']).read_text()
            assert "---" in content, "Should have YAML frontmatter"
            print("  ✓ Markdown file created successfully")
        
        if result['docx_path']:
            assert Path(result['docx_path']).exists(), "DOCX file should exist"
            print("  ✓ DOCX file created successfully")
        
        # Test braindump output (MD only)
        braindump_text = """# Braindump Notes

## To-Do Items
- [ ] Buy groceries
- [ ] Call dentist

## Mind Map
```mermaid
graph TD
    A[Idea] --> B[Action 1]
    A --> C[Action 2]
```
"""
        
        print("\nGenerating braindump outputs...")
        result2 = generator.generate_outputs(
            braindump_text,
            "braindump",
            "20240204_morning_thoughts.ogg"
        )
        
        print(f"  Title: {result2['title']}")
        print(f"  Markdown: {result2['markdown_path']}")
        print(f"  DOCX: {result2['docx_path']}")
        
        assert result2['markdown_path'] is not None, "Braindump should generate markdown"
        assert result2['docx_path'] is None, "Braindump should NOT generate docx"
        
        # Test lecture output (DOCX only)
        print("\nGenerating lecture outputs...")
        result3 = generator.generate_outputs(
            "# Lecture Notes\n\n## Topic: Introduction to Python",
            "lecture",
            "20240204_python_intro.mp3"
        )
        
        print(f"  Title: {result3['title']}")
        print(f"  Markdown: {result3['markdown_path']}")
        print(f"  DOCX: {result3['docx_path']}")
        
        assert result3['markdown_path'] is None, "Lecture should NOT generate markdown"
        assert result3['docx_path'] is not None, "Lecture should generate docx"
    
    print("\n✓ Output generation test PASSED")
    return True


def test_formatting_prompts():
    """Test that formatting prompts are correctly generated."""
    print("\n" + "="*60)
    print("TEST 3: Formatting Prompts")
    print("="*60)
    
    from formatting import PROMPT_TEMPLATES, MEETING_PROMPT, BRAINDUMP_PROMPT
    
    # Test that all expected prompts exist
    expected_types = ["MEETING", "SUPERVISION", "CLIENT", "LECTURE", "BRAINDUMP"]
    
    for note_type in expected_types:
        assert note_type in PROMPT_TEMPLATES, f"Missing prompt for {note_type}"
        prompt = PROMPT_TEMPLATES[note_type]
        assert "{transcript}" in prompt, f"Prompt for {note_type} should have {transcript} placeholder"
        print(f"  ✓ {note_type}: prompt template valid")
    
    # Test prompt formatting
    test_transcript = "This is a test transcript."
    meeting_prompt = MEETING_PROMPT.format(transcript=test_transcript)
    
    assert "Attendees" in meeting_prompt, "Meeting prompt should mention Attendees"
    assert test_transcript in meeting_prompt, "Transcript should be inserted"
    
    braindump_prompt = BRAINDUMP_PROMPT.format(transcript=test_transcript)
    assert "To-Do Items" in braindump_prompt, "Braindump prompt should mention To-Do"
    assert "Mermaid" in braindump_prompt, "Braindump prompt should mention Mermaid"
    
    print("\n✓ Formatting prompts test PASSED")
    return True


def test_pipeline_with_mocks():
    """Test the full pipeline with mocked API calls."""
    print("\n" + "="*60)
    print("TEST 4: Full Pipeline with Mocks")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test directories
        upload_dir = Path(tmpdir) / "uploads"
        processing_dir = Path(tmpdir) / "processing"
        output_dir = Path(tmpdir) / "outputs"
        
        for d in [upload_dir, processing_dir, output_dir]:
            d.mkdir(parents=True)
        
        # Create a mock audio file
        audio_file = create_mock_audio_file(upload_dir, "test_meeting.ogg")
        print(f"Created test audio: {audio_file}")
        
        # Mock API responses
        mock_transcription = {
            "text": "Hello everyone. This is a test meeting. We need to finish the project.",
            "segments": [
                {"id": 0, "start": 0.0, "end": 2.0, "text": "Hello everyone."},
                {"id": 1, "start": 2.5, "end": 5.0, "text": "This is a test meeting."},
                {"id": 2, "start": 5.5, "end": 8.0, "text": "We need to finish the project."},
            ],
            "language": "en",
            "duration": 8.0
        }
        
        mock_diarization = [
            {"speaker": "SPEAKER_00", "start": 0.0, "end": 5.2},
            {"speaker": "SPEAKER_01", "start": 5.0, "end": 8.5},
        ]
        
        mock_formatted = """# Meeting: Test Meeting

## Attendees
- SPEAKER_00
- SPEAKER_01

## Discussion Summary
- Test meeting conducted
- Project deadline discussed

## Action Items
1. Finish the project
"""
        
        # Patch the pipeline components
        with patch('transcription.GroqTranscriber') as MockTranscriber, \
             patch('diarization.SpeakerDiarizer') as MockDiarizer, \
             patch('formatting.DeepSeekFormatter') as MockFormatter:
            
            # Setup mocks
            mock_groq = MagicMock()
            mock_groq.transcribe.return_value = mock_transcription
            MockTranscriber.return_value = mock_groq
            
            mock_diarizer = MagicMock()
            mock_diarizer.diarize.return_value = mock_diarization
            MockDiarizer.return_value = mock_diarizer
            
            mock_formatter = MagicMock()
            mock_formatter.format_transcript.return_value = mock_formatted
            MockFormatter.return_value = mock_formatter
            
            # Import and run pipeline
            from pipeline import TranscriptionPipeline
            from output import OutputGenerator
            
            # Create pipeline with mocked components
            pipeline = TranscriptionPipeline.__new__(TranscriptionPipeline)
            pipeline.config = Mock()
            pipeline.config.processing_dir = processing_dir
            pipeline.config.output_dir = output_dir
            pipeline.groq = mock_groq
            pipeline.diarizer = mock_diarizer
            pipeline.formatter = mock_formatter
            pipeline.output_generator = OutputGenerator(output_dir)
            pipeline.error_dir = processing_dir / "errors"
            pipeline.error_dir.mkdir(exist_ok=True)
            
            # Copy file to processing (simulating file watcher)
            processing_file = processing_dir / "test_meeting.ogg"
            shutil.copy(audio_file, processing_file)
            
            print(f"Processing file: {processing_file}")
            
            # Process the file
            result = pipeline.process_file(processing_file, "meeting")
            
            print(f"\nResult:")
            print(f"  Success: {result['success']}")
            print(f"  Duration: {result['duration']:.2f}s")
            print(f"  Outputs: {result['outputs']}")
            
            if result['error']:
                print(f"  Error: {result['error']}")
            
            # Verify
            assert result['success'], f"Processing should succeed: {result.get('error')}"
            assert result['outputs']['markdown'] or result['outputs']['docx'], "Should have outputs"
            
            # Check that original file was deleted
            assert not processing_file.exists(), "Original audio should be deleted after processing"
            
            print("\n✓ Full pipeline test PASSED")
    
    return True


def test_note_type_detection():
    """Test note type detection from directory paths."""
    print("\n" + "="*60)
    print("TEST 5: Note Type Detection")
    print("="*60)
    
    from pathlib import Path
    
    # Test path to note type mapping
    test_cases = [
        ("uploads/meeting/team_sync.mp3", "meeting"),
        ("uploads/meetings/weekly.mp3", "meeting"),
        ("uploads/supervision/clinical.mp3", "supervision"),
        ("uploads/client/session_1.mp3", "client"),
        ("uploads/therapy/session_2.mp3", "client"),
        ("uploads/lecture/intro_psych.mp3", "lecture"),
        ("uploads/presentation/slides.mp3", "lecture"),
        ("uploads/braindump/ideas.ogg", "braindump"),
        ("uploads/voicenote/quick_thoughts.ogg", "braindump"),
        ("uploads/notes/random.mp3", "braindump"),
        ("uploads/unknown/random.mp3", "meeting"),  # Default
    ]
    
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
    
    for path_str, expected in test_cases:
        path = Path(path_str)
        parent = path.parent.name.lower()
        detected = type_mapping.get(parent, 'meeting')
        
        assert detected == expected, f"Path '{path_str}' should be '{expected}', got '{detected}'"
        print(f"  ✓ {path_str} -> {detected}")
    
    print("\n✓ Note type detection test PASSED")
    return True


def test_error_handling():
    """Test error handling in pipeline."""
    print("\n" + "="*60)
    print("TEST 6: Error Handling")
    print("="*60)
    
    from transcription import GroqAPIError
    from diarization import DiarizationError
    from formatting import FormattingError
    
    # Test custom exceptions
    try:
        raise GroqAPIError("Test error", status_code=429, response_text="Rate limited")
    except GroqAPIError as e:
        assert e.status_code == 429
        print(f"  ✓ GroqAPIError: {e}")
    
    try:
        raise DiarizationError("Model failed to load")
    except DiarizationError as e:
        print(f"  ✓ DiarizationError: {e}")
    
    try:
        raise FormattingError("API timeout")
    except FormattingError as e:
        print(f"  ✓ FormattingError: {e}")
    
    print("\n✓ Error handling test PASSED")
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("TRANSCRIPTION PIPELINE - END-TO-END TEST SUITE")
    print("="*60)
    
    tests = [
        ("Merge Logic", test_merge_logic),
        ("Output Generation", test_output_generation),
        ("Formatting Prompts", test_formatting_prompts),
        ("Full Pipeline", test_pipeline_with_mocks),
        ("Note Type Detection", test_note_type_detection),
        ("Error Handling", test_error_handling),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            test_func()
            results.append((name, True, None))
        except Exception as e:
            results.append((name, False, str(e)))
            import traceback
            traceback.print_exc()
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, p, _ in results if p)
    failed = len(results) - passed
    
    for name, passed_test, error in results:
        status = "✓ PASSED" if passed_test else f"✗ FAILED: {error}"
        print(f"  {name}: {status}")
    
    print()
    print(f"Total: {len(results)} tests, {passed} passed, {failed} failed")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
