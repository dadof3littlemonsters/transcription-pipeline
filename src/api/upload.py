"""
File upload handling utilities.
"""

import os
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
    
    # Create upload directory
    upload_dir = base_dir / profile_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    original_name = Path(file.filename).stem
    extension = Path(file.filename).suffix
    unique_filename = f"{timestamp}_{original_name}{extension}"
    
    file_path = upload_dir / unique_filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    finally:
        file.file.close()
    
    return file_path.resolve()
