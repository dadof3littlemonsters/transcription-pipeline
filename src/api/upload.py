"""
File upload handling utilities.
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile, HTTPException, status

# Allowed audio/video extensions
ALLOWED_EXTENSIONS = {
    # Audio
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma",
    # Video
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"
}

# Max file size: 500MB
MAX_FILE_SIZE = 500 * 1024 * 1024


def validate_audio_file(file: UploadFile) -> bool:
    """
    Validate uploaded audio/video file.
    
    Args:
        file: Uploaded file
        
    Returns:
        True if valid
        
    Raises:
        HTTPException: If file is invalid
    """
    # Check extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    return True


async def save_uploaded_file(
    file: UploadFile, 
    profile_id: str,
    base_dir: Path = Path("uploads")
) -> Path:
    """
    Save uploaded file to disk.
    
    Args:
        file: Uploaded file
        profile_id: Profile ID (used for subdirectory)
        base_dir: Base upload directory
        
    Returns:
        Absolute path to saved file
        
    Raises:
        HTTPException: If save fails
    """
    # Validate file
    validate_audio_file(file)
    
    # Sanitize profile_id to prevent path traversal
    safe_profile_id = re.sub(r'[^a-zA-Z0-9_-]', '', profile_id)
    if not safe_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid profile_id"
        )
    
    # Create upload directory
    upload_dir = base_dir / safe_profile_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename to prevent path traversal
    original_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', Path(file.filename).stem)
    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = ".bin"  # Fallback
    
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    unique_filename = f"{timestamp}_{original_name[:100]}{extension}"
    
    file_path = (upload_dir / unique_filename).resolve()
    
    # Verify the final path is within the upload directory
    if not str(file_path).startswith(str(base_dir.resolve())):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path"
        )
    
    # Save file with size limit enforcement
    try:
        bytes_written = 0
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(1024 * 1024):  # Read 1MB at a time
                bytes_written += len(chunk)
                if bytes_written > MAX_FILE_SIZE:
                    buffer.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    finally:
        file.file.close()
    
    return file_path.resolve()
