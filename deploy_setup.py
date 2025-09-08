#!/usr/bin/env python3
"""
Deployment setup script for PythonAnywhere
Run this script on PythonAnywhere to set up your application
"""

import os
import sys
import subprocess
from pathlib import Path

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return None

def main():
    print("🚀 Setting up Comic Book Collection Manager for PythonAnywhere...")
    
    # Check if we're in the right directory
    if not Path("app").exists():
        print("❌ Error: app directory not found. Please run this script from the project root.")
        sys.exit(1)
    
    # Install dependencies
    print("\n📦 Installing dependencies...")
    run_command("pip install -r requirements.txt", "Installing Python packages")
    
    # Set up environment file
    print("\n🔧 Setting up environment configuration...")
    if not Path(".env").exists():
        if Path("env.production").exists():
            run_command("cp env.production .env", "Creating .env file from production template")
            print("⚠️  Please edit .env file with your actual configuration values")
        else:
            print("❌ env.production template not found")
    
    # Initialize database
    print("\n🗄️ Setting up database...")
    run_command("flask db init", "Initializing database")
    run_command("flask db migrate -m 'Initial migration'", "Creating initial migration")
    run_command("flask db upgrade", "Applying database migrations")
    
    # Create admin user
    print("\n👤 Creating admin user...")
    admin_script = """
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    # Check if admin user already exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print('✅ Admin user created successfully!')
        print('   Username: admin')
        print('   Password: admin123')
        print('   Email: admin@example.com')
    else:
        print('ℹ️  Admin user already exists')
"""
    
    with open("temp_admin_setup.py", "w") as f:
        f.write(admin_script)
    
    run_command("python temp_admin_setup.py", "Creating admin user")
    os.remove("temp_admin_setup.py")
    
    # Set up static files directory
    print("\n📁 Setting up static files...")
    static_dir = Path("app/static")
    if static_dir.exists():
        print(f"✅ Static files directory found: {static_dir}")
    else:
        print("❌ Static files directory not found")
    
    # Set up uploads directory
    uploads_dir = Path("instance/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    print(f"✅ Uploads directory created: {uploads_dir}")
    
    print("\n🎉 Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Edit .env file with your actual configuration")
    print("2. Update wsgi.py with your PythonAnywhere username")
    print("3. Configure your web app in PythonAnywhere dashboard")
    print("4. Set up static files mapping")
    print("5. Reload your web app")
    print("\n🔗 Your app will be available at: https://YOUR_USERNAME.pythonanywhere.com")

if __name__ == "__main__":
    main()
