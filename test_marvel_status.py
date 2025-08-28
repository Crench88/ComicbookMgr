#!/usr/bin/env python3
"""
Test Marvel API configuration and connectivity
"""

import os
import hashlib
import time
import requests
from dotenv import load_dotenv

def test_marvel_api():
    """Test Marvel API configuration and connectivity."""
    
    # Load environment variables
    load_dotenv()
    
    # Get API keys
    api_key = os.environ.get('MARVEL_API_KEY')
    private_key = os.environ.get('MARVEL_PRIVATE_KEY')
    
    print("🔍 Marvel API Configuration Test")
    print("=" * 40)
    
    # Check if keys exist
    print(f"✅ API Key exists: {bool(api_key)}")
    print(f"✅ Private Key exists: {bool(private_key)}")
    
    if not api_key or not private_key:
        print("❌ Missing API keys. Check your .env file.")
        return False
    
    # Test API call
    try:
        # Marvel API requires timestamp and hash
        timestamp = str(int(time.time()))
        hash_input = timestamp + private_key + api_key
        hash_value = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
        
        search_url = "https://gateway.marvel.com/v1/public/comics"
        
        headers = {
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        
        params = {
            'apikey': api_key,
            'ts': timestamp,
            'hash': hash_value,
            'titleStartsWith': 'Spider-Man',
            'limit': 5,
            'format': 'comic',
            'formatType': 'comic'
        }
        
        print(f"🔍 Testing Marvel API with 'Spider-Man'...")
        print(f"🔍 API Key (first 10 chars): {api_key[:10]}...")
        print(f"🔍 Private Key (first 10 chars): {private_key[:10]}...")
        print(f"🔍 Timestamp: {timestamp}")
        print(f"🔍 Hash: {hash_value}")
        
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        
        print(f"📡 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'results' in data['data']:
                results = data['data']['results']
                print(f"✅ Marvel API working! Found {len(results)} results")
                for i, comic in enumerate(results[:3]):
                    print(f"   {i+1}. {comic.get('title', 'Unknown')}")
                return True
            else:
                print("❌ No results in response")
                return False
        elif response.status_code == 401:
            print("❌ Authentication failed (401)")
            print("📋 Check your API keys and domain whitelist")
            return False
        elif response.status_code == 409:
            print("❌ Missing required parameters (409)")
            return False
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"📋 Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ Marvel API test failed: {e}")
        return False

if __name__ == '__main__':
    test_marvel_api()
