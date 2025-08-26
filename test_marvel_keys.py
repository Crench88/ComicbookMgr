#!/usr/bin/env python3
"""
Simple test to verify if the current Marvel API keys work.
"""

import hashlib
import time
import requests

def test_current_marvel_keys():
    """Test the current Marvel API keys."""
    
    # Your current Marvel API credentials
    public_key = "9e68878e26467b05952fd752d67b0f8c"
    private_key = "e6a5261e0f5f27d9d7eb1b9f8fbd2694ae469117"
    
    print("🔍 Testing Current Marvel API Keys")
    print(f"🔑 Public Key: {public_key}")
    print(f"🔑 Private Key: {private_key[:10]}...")
    
    # Marvel API requires timestamp and hash
    timestamp = str(int(time.time()))
    hash_input = timestamp + private_key + public_key
    hash_value = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
    
    print(f"🔍 Timestamp: {timestamp}")
    print(f"🔍 Hash Input: {timestamp + '***' + public_key}")
    print(f"🔍 Generated Hash: {hash_value}")
    
    search_url = "https://gateway.marvel.com/v1/public/comics"
    
    headers = {
        'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
    }
    
    params = {
        'apikey': public_key,
        'ts': timestamp,
        'hash': hash_value,
        'titleStartsWith': 'Iron Man',
        'limit': 5,
        'format': 'comic',
        'formatType': 'comic'
    }
    
    print(f"\n🔍 Making API request...")
    print(f"🔍 URL: {search_url}")
    print(f"🔍 Params: {params}")
    
    try:
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        print(f"\n📡 Response Status: {response.status_code}")
        print(f"📡 Response URL: {response.url}")
        
        if response.status_code == 200:
            print("✅ SUCCESS! Marvel API keys are working!")
            data = response.json()
            if 'data' in data and 'results' in data['data']:
                print(f"📚 Found {len(data['data']['results'])} results.")
                for comic in data['data']['results'][:3]:  # Show first 3
                    print(f"  - {comic.get('title')} (Issue: {comic.get('issueNumber')})")
            else:
                print("No results found in data.")
        else:
            print("❌ FAILED!")
            print(f"📡 Response Text: {response.text[:500]}...")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

if __name__ == '__main__':
    test_current_marvel_keys()
