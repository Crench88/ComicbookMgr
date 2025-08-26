#!/usr/bin/env python3
"""
Setup script to create a local domain name for your Flask app.
This allows you to access your app without a port number.
"""

import os
import platform
import subprocess

def setup_hosts_file():
    """Add local domain entries to hosts file."""
    
    # Determine hosts file location based on OS
    if platform.system() == "Windows":
        hosts_file = r"C:\Windows\System32\drivers\etc\hosts"
    else:
        hosts_file = "/etc/hosts"
    
    # Domain entries to add
    domains = [
        "comicbook.local",
        "comics.local", 
        "localhost"
    ]
    
    print("🔧 Setting up local domain names...")
    print(f"📁 Hosts file: {hosts_file}")
    print()
    
    try:
        # Read current hosts file
        with open(hosts_file, 'r') as f:
            content = f.read()
        
        # Check if entries already exist
        entries_to_add = []
        for domain in domains:
            if f"127.0.0.1 {domain}" not in content:
                entries_to_add.append(f"127.0.0.1 {domain}")
        
        if entries_to_add:
            print("📝 Adding domain entries to hosts file...")
            with open(hosts_file, 'a') as f:
                f.write("\n# Comic Book Manager Local Domains\n")
                for entry in entries_to_add:
                    f.write(f"{entry}\n")
                    print(f"  ✅ Added: {entry}")
            
            print("\n🎉 Domain setup complete!")
            print("🌐 You can now access your app at:")
            for domain in domains:
                print(f"   - http://{domain}")
        else:
            print("✅ Domain entries already exist!")
            
    except PermissionError:
        print("❌ Permission denied. Run as administrator/sudo.")
        print("📝 Manual setup required:")
        print(f"   1. Open {hosts_file} as administrator")
        print("   2. Add these lines:")
        for domain in domains:
            print(f"      127.0.0.1 {domain}")
    except Exception as e:
        print(f"❌ Error setting up domains: {e}")

def create_startup_script():
    """Create a startup script that runs Flask on port 80."""
    
    script_content = """#!/usr/bin/env python3
# Comic Book Manager Startup Script
# Run this script to start your app on port 80

import os
import sys
from app import create_app

if __name__ == '__main__':
    print("🚀 Starting Comic Book Manager on port 80...")
    print("🌐 Access your app at: http://comicbook.local")
    print("📝 Press Ctrl+C to stop")
    print()
    
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=80)
"""
    
    try:
        with open('start_port80.py', 'w') as f:
            f.write(script_content)
        print("✅ Created startup script: start_port80.py")
        print("📝 Run: python start_port80.py (as administrator)")
    except Exception as e:
        print(f"❌ Error creating startup script: {e}")

def main():
    """Main setup function."""
    print("🔧 Comic Book Manager - Domain Setup")
    print("=" * 40)
    print()
    
    setup_hosts_file()
    print()
    create_startup_script()
    print()
    
    print("📋 Next Steps:")
    print("1. Run as administrator: python start_port80.py")
    print("2. Access your app at: http://comicbook.local")
    print("3. Update Marvel API whitelist to include: comicbook.local")
    print()
    print("🎉 No more port numbers in your URLs!")

if __name__ == '__main__':
    main()
