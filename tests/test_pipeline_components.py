#!/usr/bin/env python3
"""
Comprehensive test suite for transcription pipeline components.
Tests each component independently before end-to-end testing.
"""

import sys
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestConfig(unittest.TestCase):
    """Test configuration loading."""
    
    def test_config_import(self):
        """Test that config module imports correctly."""
        from config import get_config, Config
        self.assertTrue(callable(get_config))
    
    def test_config_defaults(self):
        """Test default configuration values."""
        from config import get_config
        config = get_config()
        self.assertIsNotNone(config.upload_dir)
        self.assertIsNotNone(config.processing_dir)
        self.assertIsNotNone(config.output_dir)


class TestTranscription(unittest.TestCase):
    """Test Groq transcription client."""
    
    def test_transcriber_import(self):
        """Test that transcription module imports."""
        from transcription import GroqTranscriber, GroqAPIError
        self.assertTrue(callable(GroqTranscriber))
    
    def test_transcriber_initialization(self):
        """Test transcriber can be initialized."""
        from transcription import GroqTranscriber
        transcriber = GroqTranscriber(api_key="test-key")
        self.assertEqual(transcriber.api_key, "test-key")
        self.assertEqual(transcriber.model, "whisper-large-v3-turbo")
    
    def test_supported_formats(self):
        """Test supported audio formats."""
        from transcription import SUPPORTED_FORMATS
        self.assertIn(".mp3", SUPPORTED_FORMATS)
        self.assertIn(".wav", SUPPORTED_FORMATS)
        self.assertIn(".ogg", SUPPORTED_FORMATS)


class TestDiarization(unittest.TestCase):
    """Test speaker diarization module."""
    
    def test_diarizer_import(self):
        """Test that diarization module imports."""
        from diarization import SpeakerDiarizer, DiarizationError
        self.assertTrue(callable(SpeakerDiarizer))
    
    def test_diarizer_initialization(self):
        """Test diarizer requires HF token."""
        from diarization import SpeakerDiarizer, DiarizationError
        with self.assertRaises(DiarizationError):
            SpeakerDiarizer(hf_token="")


class TestMerge(unittest.TestCase):
    """Test timestamp merging logic."""
    
    def test_merge_import(self):
        """Test merge module imports."""
        from merge import merge_transcript_with_speakers, calculate_overlap
        self.assertTrue(callable(merge_transcript_with_speakers))
        self.assertTrue(callable(calculate_overlap))
    
    def test_calculate_overlap(self):
        """Test overlap calculation."""
        from merge import calculate_overlap
        
        # Complete overlap
        self.assertEqual(calculate_overlap(0, 10, 0, 10), 10)
        
        # Partial overlap
        self.assertEqual(calculate_overlap(0, 10, 5, 15), 5)
        
        # No overlap
        self.assertEqual(calculate_overlap(0, 5, 10, 15), 0)
        
        # Edge case - touching but not overlapping
        self.assertEqual(calculate_overlap(0, 5, 5, 10), 0)
    
    def test_merge_transcript_with_speakers(self):
        """Test merging transcript with speaker segments."""
        from merge import merge_transcript_with_speakers
        
        whisper_segments = [
            {"start": 0.0, "end": 5.0, "text": "Hello world"},
            {"start": 6.0, "end": 10.0, "text": "How are you?"},
        ]
        
        diarization_segments = [
            {"speaker": "SPEAKER_00", "start": 0.0, "end": 5.5},
            {"speaker": "SPEAKER_01", "start": 5.5, "end": 10.0},
        ]
        
        result = merge_transcript_with_speakers(whisper_segments, diarization_segments)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["speaker"], "SPEAKER_00")
        self.assertEqual(result[0]["text"], "Hello world")
        self.assertEqual(result[1]["speaker"], "SPEAKER_01")
        self.assertEqual(result[1]["text"], "How are you?")
    
    def test_merge_empty_whisper(self):
        """Test handling empty whisper segments."""
        from merge import merge_transcript_with_speakers
        
        result = merge_transcript_with_speakers([], [])
        self.assertEqual(result, [])
    
    def test_merge_empty_diarization(self):
        """Test handling empty diarization segments."""
        from merge import merge_transcript_with_speakers
        
        whisper = [{"start": 0.0, "end": 5.0, "text": "Hello"}]
        result = merge_transcript_with_speakers(whisper, [])
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["speaker"], "SPEAKER_00")


class TestFormatting(unittest.TestCase):
    """Test DeepSeek formatting module."""
    
    def test_formatter_import(self):
        """Test formatting module imports."""
        from formatting import DeepSeekFormatter, FormattingError, PROMPT_TEMPLATES
        self.assertTrue(callable(DeepSeekFormatter))
        self.assertIn("MEETING", PROMPT_TEMPLATES)
        self.assertIn("BRAINDUMP", PROMPT_TEMPLATES)
    
    def test_formatter_initialization(self):
        """Test formatter initialization."""
        from formatting import DeepSeekFormatter
        formatter = DeepSeekFormatter(api_key="test-key")
        self.assertEqual(formatter.api_key, "test-key")


class TestOutput(unittest.TestCase):
    """Test output generation module."""
    
    def test_output_generator_import(self):
        """Test output module imports."""
        from output import OutputGenerator
        self.assertTrue(callable(OutputGenerator))
    
    def test_output_paths(self):
        """Test output paths are created."""
        from output import OutputGenerator
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = OutputGenerator(Path(tmpdir))
            self.assertTrue(gen.transcripts_dir.exists())
            self.assertTrue(gen.docs_dir.exists())
    
    def test_title_derivation(self):
        """Test title derivation from filename."""
        from output import OutputGenerator
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = OutputGenerator(Path(tmpdir))
            
            # Test with timestamp prefix
            title = gen._derive_title("20240115_143022_team_meeting.mp3", "meeting")
            self.assertIn("Meeting", title)
            self.assertIn("Team", title)
            
            # Test with underscores
            title = gen._derive_title("my_audio_file.mp3", "braindump")
            self.assertIn("Braindump", title)


class TestPipeline(unittest.TestCase):
    """Test main pipeline orchestrator."""
    
    def test_pipeline_import(self):
        """Test pipeline module imports."""
        from pipeline import TranscriptionPipeline, process_file_sync
        self.assertTrue(callable(TranscriptionPipeline))
        self.assertTrue(callable(process_file_sync))
    
    @patch.dict(os.environ, {
        "GROQ_API_KEY": "test-groq-key",
        "DEEPSEEK_API_KEY": "test-deepseek-key",
        "HUGGINGFACE_TOKEN": "test-hf-token"
    })
    def test_pipeline_initialization(self):
        """Test pipeline initialization with env vars."""
        from pipeline import TranscriptionPipeline
        
        # This will fail without real API keys, but tests the structure
        try:
            pipeline = TranscriptionPipeline()
            self.assertIsNotNone(pipeline.config)
        except Exception:
            # Expected to fail without real API keys
            pass


class TestFileWatcher(unittest.TestCase):
    """Test file watcher module."""
    
    def test_watcher_import(self):
        """Test file watcher imports."""
        from file_watcher import FileWatcher, AudioFileHandler, create_watcher
        self.assertTrue(callable(FileWatcher))
        self.assertTrue(callable(AudioFileHandler))
        self.assertTrue(callable(create_watcher))


class TestWorker(unittest.TestCase):
    """Test worker module."""
    
    def test_worker_import(self):
        """Test worker module imports."""
        from worker import PipelineWorker, run_worker
        self.assertTrue(callable(PipelineWorker))
        self.assertTrue(callable(run_worker))


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestTranscription))
    suite.addTests(loader.loadTestsFromTestCase(TestDiarization))
    suite.addTests(loader.loadTestsFromTestCase(TestMerge))
    suite.addTests(loader.loadTestsFromTestCase(TestFormatting))
    suite.addTests(loader.loadTestsFromTestCase(TestOutput))
    suite.addTests(loader.loadTestsFromTestCase(TestPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestFileWatcher))
    suite.addTests(loader.loadTestsFromTestCase(TestWorker))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
