#!/usr/bin/env python3
"""
Script to help identify what domain needs to be whitelisted for Marvel API.
"""

import socket
import requests

def get_local_ip():
    """Get the local IP address."""
    try:
        # Get local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def check_marvel_domain_requirements():
    """Check what domain information is needed for Marvel API."""
    
    local_ip = get_local_ip()
    
    print("🔍 Marvel API Domain Whitelisting Information")
    print("=" * 50)
    print(f"📍 Your local IP address: {local_ip}")
    print(f"📍 Localhost: localhost")
    print(f"📍 Loopback: 127.0.0.1")
    print()
    print("📋 Current whitelisted domains in your Marvel account:")
    print("   - developer.marvel.com")
    print("   - 127.0.0.1")
    print("   - localhost")
    print("   - 10.0.0.101")
    print()
    print("🔧 To fix the 'InvalidCredentials' error, try adding these domains:")
    print(f"   - {local_ip}")
    print("   - 127.0.0.1:5000 (if testing from Flask)")
    print("   - localhost:5000 (if testing from Flask)")
    print()
    print("📝 Instructions:")
    print("1. Go to https://developer.marvel.com/account")
    print("2. Click 'Add a new referrer'")
    print("3. Add the domains listed above (one at a time)")
    print("4. Wait a few minutes for changes to take effect")
    print("5. Test again")
    print()
    print("⚠️  Note: Marvel API may take a few minutes to recognize new whitelisted domains.")

if __name__ == "__main__":
    check_marvel_domain_requirements()
