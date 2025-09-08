#!/usr/bin/env python3
"""
Setup script for Comic Book Collection Manager
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def run_command(command, description):
    """Run a command and handle errors."""
    print(f"Running: {description}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return False

def create_env_file():
    """Create .env file from template."""
    env_example = Path("env.example")
    env_file = Path(".env")
    
    if env_file.exists():
        print("✓ .env file already exists")
        return True
    
    if env_example.exists():
        print("Creating .env file from template...")
        shutil.copy(env_example, env_file)
        print("✓ .env file created")
        print("⚠️  Please update the SECRET_KEY in .env file")
        return True
    else:
        print("✗ env.example not found")
        return False

def create_directories():
    """Create necessary directories."""
    directories = [
        "instance",
        "instance/uploads",
        "static/uploads"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {directory}")

def main():
    """Main setup function."""
    print("🚀 Setting up Comic Book Collection Manager")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("✗ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Create virtual environment
    if not Path("venv").exists():
        print("Creating virtual environment...")
        if not run_command("python -m venv venv", "Creating virtual environment"):
            sys.exit(1)
    else:
        print("✓ Virtual environment already exists")
    
    # Determine activation command
    if os.name == 'nt':  # Windows
        activate_cmd = "venv\\Scripts\\activate"
        pip_cmd = "venv\\Scripts\\pip"
    else:  # Unix/Linux/macOS
        activate_cmd = "source venv/bin/activate"
        pip_cmd = "venv/bin/pip"
    
    # Install dependencies
    if not run_command(f"{pip_cmd} install -r requirements.txt", "Installing dependencies"):
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Create .env file
    if not create_env_file():
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Activate the virtual environment:")
    if os.name == 'nt':
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    print("2. Update the SECRET_KEY in .env file")
    print("3. Run the application:")
    print("   python app.py")
    print("4. Open http://localhost:5000 in your browser")
    print("\nHappy collecting! 🦸‍♂️📚")

if __name__ == "__main__":
    main()
