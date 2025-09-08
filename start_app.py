#!/usr/bin/env python3
"""
Simple startup script for Comic Book Collection Manager.
This script provides an easy way to start the application with proper configuration.
"""

import os
import sys
from pathlib import Path

def check_requirements():
    """Check if all required packages are installed."""
    required_packages = [
        'flask', 'flask_login', 'flask_mail', 'flask_migrate', 
        'flask_sqlalchemy', 'flask_wtf', 'wtforms', 'werkzeug',
        'pillow', 'python_dotenv', 'email_validator', 'requests'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n💡 Install missing packages with:")
        print("   pip install -r requirements.txt")
        return False
    
    return True

def check_env_file():
    """Check if .env file exists."""
    env_file = Path('.env')
    if not env_file.exists():
        print("⚠️  .env file not found!")
        print("💡 Copy env.example to .env and configure your settings:")
        print("   copy env.example .env")
        return False
    return True

def main():
    """Main startup function."""
    print("🚀 Starting Comic Book Collection Manager...")
    print("=" * 50)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Check environment file
    if not check_env_file():
        print("\n⚠️  Continuing without .env file (using defaults)...")
    
    print("✅ All checks passed!")
    print("\n🌐 Starting application...")
    print("📱 Open your browser and go to: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop the application")
    print("=" * 50)
    
    # Import and start the application
    try:
        from app import create_app
        app = create_app()
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
