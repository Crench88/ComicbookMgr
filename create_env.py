#!/usr/bin/env python3
"""
Helper script to create the .env file with the ComicVine API key.
"""

import os

def create_env_file():
    """Create the .env file with the API key."""
    
    env_content = """# Comic Book Collection Manager - Environment Variables

# Flask Configuration
SECRET_KEY=dev-secret-key-change-this-in-production
FLASK_ENV=development
FLASK_DEBUG=True

# Database Configuration
DATABASE_URL=sqlite:///comicbook.db

# File Upload Configuration
MAX_CONTENT_LENGTH=16777216  # 16MB in bytes
UPLOAD_FOLDER=instance/uploads

# Security Configuration
WTF_CSRF_ENABLED=True
WTF_CSRF_SECRET_KEY=your-csrf-secret-key

# Comic Book API Configuration
COMICVINE_API_KEY=d10581ede81d1f417b10214a61be36f8eabcd783

# Marvel Comics API Configuration (Optional - Get free keys at https://developer.marvel.com/)
MARVEL_API_KEY=5c01fedd91fbe7626ee9f1d0c00e76c3
MARVEL_PRIVATE_KEY=83ed6f6a28cd2d677f1c3c7b105b7434e3c77c0a

# UPC Database API Configuration (Optional - Get free key at https://upcdatabase.org/api)
# UPC_DATABASE_API_KEY=your_upc_database_api_key_here

# Barcode Lookup API Configuration (Optional - Get free key at https://barcodelookup.com/api)
# BARCODE_LOOKUP_API_KEY=your_barcode_lookup_api_key_here

# Optional: PostgreSQL Configuration (for production)
# DATABASE_URL=postgresql://username:password@localhost/comicbook_db
"""
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ .env file created successfully!")
        print("📝 Your ComicVine and Marvel API keys have been configured.")
        print("🔄 Please restart your Flask application for the changes to take effect.")
        return True
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Creating .env file with your ComicVine API key...")
    success = create_env_file()
    
    if success:
        print("\n📋 Next steps:")
        print("1. Restart your Flask application")
        print("2. Try searching for 'Spider-Man' or 'Iron Man' with Marvel API selected")
        print("3. You should now see real comic book data from both ComicVine and Marvel!")
    else:
        print("\n❌ Please create the .env file manually with your API key.")
