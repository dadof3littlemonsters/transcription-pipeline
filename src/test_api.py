#!/usr/bin/env python3
"""
Simple test script to verify API endpoints.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Verify API keys are loaded
print("API Keys Status:")
print(f"  GROQ_API_KEY: {'✓' if os.getenv('GROQ_API_KEY') else '✗'}")
print(f"  DEEPSEEK_API_KEY: {'✓' if os.getenv('DEEPSEEK_API_KEY') else '✗'}")
print(f"  HUGGINGFACE_TOKEN: {'✓' if os.getenv('HUGGINGFACE_TOKEN') else '✗'}")
print()

# Start server
import uvicorn
from src.main import app

print("Starting API server on http://localhost:8888")
print("Press CTRL+C to stop")
print()

uvicorn.run(app, host="0.0.0.0", port=8888)
