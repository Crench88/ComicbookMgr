#!/usr/bin/env python3
"""
Generate secure secret keys for Flask applications.
"""

import secrets
import sys

def generate_secret_key():
    """Generate a cryptographically secure secret key."""
    return secrets.token_hex(32)

def generate_urlsafe_key():
    """Generate a URL-safe secret key."""
    return secrets.token_urlsafe(32)

def main():
    """Main function to generate and display secret keys."""
    print("🔐 Flask Secret Key Generator")
    print("=" * 40)
    print()
    
    # Generate hex key (recommended)
    hex_key = generate_secret_key()
    print("📋 Hex Secret Key (Recommended):")
    print(f"SECRET_KEY={hex_key}")
    print()
    
    # Generate URL-safe key
    urlsafe_key = generate_urlsafe_key()
    print("📋 URL-Safe Secret Key:")
    print(f"SECRET_KEY={urlsafe_key}")
    print()
    
    print("⚠️  Security Notes:")
    print("- Use different keys for each environment (dev, staging, production)")
    print("- Never commit secret keys to version control")
    print("- Store keys securely using environment variables")
    print("- Rotate keys regularly in production")
    print()
    
    # Copy to clipboard if possible
    try:
        import pyperclip
        pyperclip.copy(hex_key)
        print("✅ Hex key copied to clipboard!")
    except ImportError:
        print("💡 Tip: Install pyperclip to copy keys to clipboard automatically")
        print("   pip install pyperclip")

if __name__ == "__main__":
    main()
