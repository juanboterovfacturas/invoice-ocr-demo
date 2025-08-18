#!/usr/bin/env python3
"""
Invoice OCR Demo Runner
Run this script to start the portfolio demo application
"""

import subprocess
import sys
import os
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import streamlit
        import google.generativeai
        import pandas
        import PIL
        print("✅ All dependencies found")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Run: uv sync")
        return False

def setup_directories():
    """Create necessary directories"""
    directories = ["uploads", "exports", "processed_images", "images"]
    for dir_name in directories:
        Path(dir_name).mkdir(exist_ok=True)
    print("✅ Directories set up")

def main():
    """Main function to run the demo"""
    print("🚀 Invoice OCR Demo - Portfolio Version")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        return
    
    # Setup directories
    setup_directories()
    
    # Set environment variables
    os.environ["GEMINI_API_KEY"] = "AIzaSyBXVD6tdm4v9xcv5dzduTfpfDGqX2zr3yc"
    
    print("🌐 Starting Streamlit server...")
    print("📧 Portfolio: meetmoeed.com")
    print("🤖 Powered by: Google Gemini 2.0 Flash")
    print("-" * 50)
    
    # Run streamlit
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port=8501"])
    except KeyboardInterrupt:
        print("\n👋 Demo stopped. Thanks for viewing!")
    except Exception as e:
        print(f"❌ Error running demo: {e}")

if __name__ == "__main__":
    main()