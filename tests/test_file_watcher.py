"""
Test script for the file watcher module.

Tests file detection, validation, and movement functionality.
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Config, get_config
from file_watcher import FileWatcher, AudioFileHandler, create_watcher


def test_config_defaults():
    """Test configuration defaults."""
    print("\n" + "="*60)
    print("TEST: Configuration Defaults")
    print("="*60)
    
    config = Config()
    
    print(f"✓ Upload dir: {config.upload_dir}")
    print(f"✓ Processing dir: {config.processing_dir}")
    print(f"✓ Output dir: {config.output_dir}")
    print(f"✓ Supported formats: {config.supported_audio_formats}")
    print(f"✓ Max file size: {config.max_file_size_mb} MB")
    print(f"✓ Log level: {config.log_level}")
    
    # Test directory creation
    config.ensure_directories()
    assert config.upload_dir.exists(), "Upload dir should exist"
    assert config.processing_dir.exists(), "Processing dir should exist"
    assert config.output_dir.exists(), "Output dir should exist"
    print("✓ All directories created successfully")
    
    print("\n✅ Config defaults test PASSED")


def test_file_validation():
    """Test audio file validation."""
    print("\n" + "="*60)
    print("TEST: File Validation")
    print("="*60)
    
    config = Config()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create test files
        valid_mp3 = tmp_path / "test.mp3"
        valid_wav = tmp_path / "test.wav"
        invalid_txt = tmp_path / "test.txt"
        
        # Create dummy files
        valid_mp3.write_bytes(b"dummy mp3 content")
        valid_wav.write_bytes(b"dummy wav content")
        invalid_txt.write_bytes(b"dummy text content")
        
        # Test validation
        assert config.is_valid_audio_file(valid_mp3), "MP3 should be valid"
        print("✓ MP3 file validated")
        
        assert config.is_valid_audio_file(valid_wav), "WAV should be valid"
        print("✓ WAV file validated")
        
        assert not config.is_valid_audio_file(invalid_txt), "TXT should be invalid"
        print("✓ TXT file rejected as expected")
        
        assert not config.is_valid_audio_file(tmp_path / "nonexistent.mp3"), "Nonexistent file should be invalid"
        print("✓ Nonexistent file rejected as expected")
    
    print("\n✅ File validation test PASSED")


def test_file_size_validation():
    """Test file size validation."""
    print("\n" + "="*60)
    print("TEST: File Size Validation")
    print("="*60)
    
    config = Config(max_file_size_mb=1)  # 1 MB limit for testing
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create small file (valid)
        small_file = tmp_path / "small.mp3"
        small_file.write_bytes(b"x" * 1024)  # 1 KB
        assert config.is_valid_audio_file(small_file), "Small file should be valid"
        print("✓ Small file (1 KB) validated")
        
        # Create large file (invalid)
        large_file = tmp_path / "large.mp3"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
        assert not config.is_valid_audio_file(large_file), "Large file should be invalid"
        print("✓ Large file (2 MB) rejected as expected")
    
    print("\n✅ File size validation test PASSED")


def test_file_handler_validation():
    """Test AudioFileHandler validation."""
    print("\n" + "="*60)
    print("TEST: AudioFileHandler Validation")
    print("="*60)
    
    config = Config()
    handler = AudioFileHandler(config)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create test audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"dummy audio content")
        
        # Test handler validation
        assert handler._validate_file(audio_file), "Handler should validate MP3"
        print("✓ Handler validates MP3 file")
        
        # Test with non-audio file
        text_file = tmp_path / "test.txt"
        text_file.write_bytes(b"text content")
        assert not handler._validate_file(text_file), "Handler should reject TXT"
        print("✓ Handler rejects non-audio file")
    
    print("\n✅ AudioFileHandler validation test PASSED")


def test_file_watcher_lifecycle():
    """Test file watcher start/stop."""
    print("\n" + "="*60)
    print("TEST: FileWatcher Lifecycle")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        config = Config(
            upload_dir=tmp_path / "uploads",
            processing_dir=tmp_path / "processing"
        )
        
        watcher = FileWatcher(config=config)
        
        # Test initial state
        assert not watcher.is_running(), "Watcher should not be running initially"
        print("✓ Watcher initially not running")
        
        # Test start
        watcher.start()
        assert watcher.is_running(), "Watcher should be running after start"
        print("✓ Watcher started successfully")
        
        # Test stop
        watcher.stop()
        time.sleep(0.5)  # Give time to stop
        assert not watcher.is_running(), "Watcher should not be running after stop"
        print("✓ Watcher stopped successfully")
    
    print("\n✅ FileWatcher lifecycle test PASSED")


def test_file_detection():
    """Test file detection and movement."""
    print("\n" + "="*60)
    print("TEST: File Detection and Movement")
    print("="*60)
    
    detected_files = []
    moved_files = []
    
    def on_detected(file_path):
        detected_files.append(file_path.name)
        print(f"  → Callback: Detected {file_path.name}")
    
    def on_moved(src, dst):
        moved_files.append((src.name, dst.name))
        print(f"  → Callback: Moved {src.name} → {dst.name}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        upload_dir = tmp_path / "uploads"
        processing_dir = tmp_path / "processing"
        upload_dir.mkdir()
        processing_dir.mkdir()
        
        config = Config(
            upload_dir=upload_dir,
            processing_dir=processing_dir
        )
        
        watcher = FileWatcher(
            config=config,
            on_file_detected=on_detected,
            on_file_moved=on_moved
        )
        
        # Create test file in upload directory
        test_file = upload_dir / "test_recording.mp3"
        test_file.write_bytes(b"dummy mp3 content for testing")
        
        # Scan existing files
        count = watcher.scan_existing_files()
        assert count == 1, f"Should process 1 file, got {count}"
        print("✓ Scanned and processed existing file")
        
        # Verify callbacks were called
        assert len(detected_files) == 1, f"Should have 1 detected file, got {len(detected_files)}"
        assert detected_files[0] == "test_recording.mp3"
        print("✓ File detection callback fired")
        
        assert len(moved_files) == 1, f"Should have 1 moved file, got {len(moved_files)}"
        assert moved_files[0][0] == "test_recording.mp3"
        print("✓ File move callback fired")
        
        # Verify file was moved
        assert not test_file.exists(), "Original file should not exist"
        assert len(list(processing_dir.glob("*.mp3"))) == 1, "File should be in processing dir"
        print("✓ File successfully moved to processing directory")
    
    print("\n✅ File detection test PASSED")


def test_create_watcher():
    """Test create_watcher factory function."""
    print("\n" + "="*60)
    print("TEST: Create Watcher Factory")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        upload_dir = tmp_path / "custom_uploads"
        processing_dir = tmp_path / "custom_processing"
        
        watcher = create_watcher(
            upload_dir=str(upload_dir),
            processing_dir=str(processing_dir)
        )
        
        assert watcher.config.upload_dir == upload_dir, "Upload dir should match"
        assert watcher.config.processing_dir == processing_dir, "Processing dir should match"
        print("✓ Custom directories set correctly")
        
        # Verify directories are Path objects
        assert isinstance(watcher.config.upload_dir, Path)
        assert isinstance(watcher.config.processing_dir, Path)
        print("✓ Directories are Path objects")
    
    print("\n✅ Create watcher factory test PASSED")


def test_supported_formats():
    """Test all supported audio formats."""
    print("\n" + "="*60)
    print("TEST: Supported Audio Formats")
    print("="*60)
    
    config = Config()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for ext in config.supported_audio_formats:
            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(f"dummy {ext} content".encode())
            assert config.is_valid_audio_file(test_file), f"{ext} should be valid"
            print(f"✓ {ext} format validated")
    
    print("\n✅ Supported formats test PASSED")


def test_uppercase_extensions():
    """Test that uppercase file extensions are recognized."""
    print("\n" + "="*60)
    print("TEST: Uppercase File Extensions")
    print("="*60)
    
    config = Config()
    handler = AudioFileHandler(config)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Test uppercase extensions
        uppercase_extensions = ['.WAV', '.Wav', '.MP3', '.Mp3', '.M4A', '.OGG']
        
        for ext in uppercase_extensions:
            test_file = tmp_path / f"test{ext}"
            test_file.write_bytes(f"dummy {ext} content".encode())
            assert handler._validate_file(test_file), f"{ext} should be valid (case insensitive)"
            print(f"✓ {ext} extension validated (case insensitive)")
    
    print("\n✅ Uppercase extensions test PASSED")


def run_all_tests():
    """Run all tests."""
    print("\n" + "#"*60)
    print("# FILE WATCHER TEST SUITE")
    print("#"*60)
    
    tests = [
        ("Configuration Defaults", test_config_defaults),
        ("File Validation", test_file_validation),
        ("File Size Validation", test_file_size_validation),
        ("AudioFileHandler Validation", test_file_handler_validation),
        ("FileWatcher Lifecycle", test_file_watcher_lifecycle),
        ("File Detection and Movement", test_file_detection),
        ("Create Watcher Factory", test_create_watcher),
        ("Supported Audio Formats", test_supported_formats),
        ("Uppercase File Extensions", test_uppercase_extensions),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ {name} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ {name} ERROR: {e}")
            failed += 1
    
    print("\n" + "#"*60)
    print("# TEST SUMMARY")
    print("#"*60)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
