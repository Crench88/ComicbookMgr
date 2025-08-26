#!/usr/bin/env python3
"""
Simple test to check if Marvel API key is valid.
"""

import requests

def test_marvel_key():
    """Test if Marvel API key is valid."""
    
    # Your Marvel API credentials
    public_key = "9e68878e26467b05952fd752d67b0f8c"
    
    # Try a simple request without authentication first
    search_url = "https://gateway.marvel.com/v1/public/comics"
    params = {
        'apikey': public_key,
        'limit': 1
    }
    
    headers = {
        'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
    }
    
    print(f"🔍 Testing Marvel API Key: {public_key}")
    print(f"🔍 URL: {search_url}")
    print(f"🔍 Params: {params}")
    
    try:
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        print(f"📡 Response Status: {response.status_code}")
        print(f"📡 Response URL: {response.url}")
        
        if response.status_code == 200:
            print(f"✅ API Key is VALID!")
            data = response.json()
            print(f"📡 Response: {data}")
        else:
            print(f"❌ API Key is INVALID!")
            print(f"📡 Response Text: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_marvel_key()
