#!/usr/bin/env python3
"""
Script to add UPC API keys to the .env file.
"""

import os

def add_upc_api_keys():
    """Add UPC API keys to the .env file."""
    
    print("🔧 Adding UPC API Keys to .env file")
    print("=" * 40)
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("❌ .env file not found. Please run 'python create_env.py' first.")
        return False
    
    # Read current .env file
    try:
        with open('.env', 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading .env file: {e}")
        return False
    
    # Check if UPC keys are already configured
    if 'UPC_DATABASE_API_KEY=' in content and 'BARCODE_LOOKUP_API_KEY=' in content:
        print("✅ UPC API keys are already configured in .env file")
        return True
    
    print("📝 To get UPC API keys:")
    print("1. UPC Database: https://upcdatabase.org/api (free tier)")
    print("2. Barcode Lookup: https://barcodelookup.com/api (free tier)")
    print()
    
    # Get API keys from user
    upc_database_key = input("Enter your UPC Database API key (or press Enter to skip): ").strip()
    barcode_lookup_key = input("Enter your Barcode Lookup API key (or press Enter to skip): ").strip()
    
    # Update content
    lines = content.split('\n')
    new_lines = []
    
    for line in lines:
        if line.startswith('# UPC Database API Configuration'):
            new_lines.append(line)
            if upc_database_key:
                new_lines.append(f'UPC_DATABASE_API_KEY={upc_database_key}')
            else:
                new_lines.append('# UPC_DATABASE_API_KEY=your_upc_database_api_key_here')
        elif line.startswith('# Barcode Lookup API Configuration'):
            new_lines.append(line)
            if barcode_lookup_key:
                new_lines.append(f'BARCODE_LOOKUP_API_KEY={barcode_lookup_key}')
            else:
                new_lines.append('# BARCODE_LOOKUP_API_KEY=your_barcode_lookup_api_key_here')
        elif line.startswith('UPC_DATABASE_API_KEY=') or line.startswith('BARCODE_LOOKUP_API_KEY='):
            # Skip existing keys, we'll add them above
            continue
        else:
            new_lines.append(line)
    
    # Write updated content
    try:
        with open('.env', 'w') as f:
            f.write('\n'.join(new_lines))
        
        print("✅ .env file updated successfully!")
        
        if upc_database_key:
            print("✅ UPC Database API key added")
        if barcode_lookup_key:
            print("✅ Barcode Lookup API key added")
        
        print("\n🔄 Please restart your Flask application for the changes to take effect.")
        return True
        
    except Exception as e:
        print(f"❌ Error writing .env file: {e}")
        return False

def test_upc_apis():
    """Test the UPC APIs if keys are configured."""
    
    print("\n🧪 Testing UPC APIs...")
    print("=" * 30)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    upc_database_key = os.getenv('UPC_DATABASE_API_KEY', '')
    barcode_lookup_key = os.getenv('BARCODE_LOOKUP_API_KEY', '')
    
    test_upc = "75960608356500111"  # Your test UPC
    
    print(f"UPC Database API Key: {'✅ Configured' if upc_database_key else '❌ Not configured'}")
    print(f"Barcode Lookup API Key: {'✅ Configured' if barcode_lookup_key else '❌ Not configured'}")
    
    if upc_database_key or barcode_lookup_key:
        print(f"\n📊 Testing UPC: {test_upc}")
        print("💡 Start your Flask app and test the search functionality!")
    else:
        print("\n❌ No UPC API keys configured. Please add them first.")

if __name__ == '__main__':
    success = add_upc_api_keys()
    if success:
        test_upc_apis()
