#!/usr/bin/env python3
"""
Test script to verify Marvel API authentication.
"""

import hashlib
import time
import requests

def test_marvel_auth():
    """Test Marvel API authentication."""
    
    # Your Marvel API credentials
    public_key = "9e68878e26467b05952fd752d67b0f8c"
    private_key = "e6a5261e0f5f27d9d7eb1b9f8fbd2694ae469117"
    
    # Marvel API requires timestamp and hash
    timestamp = str(int(time.time()))
    
    # Create hash: timestamp + private_key + public_key
    # Try different hash input formats
    hash_input1 = timestamp + private_key + public_key
    hash_input2 = private_key + timestamp + public_key
    hash_input3 = timestamp + public_key + private_key
    
    hash_value1 = hashlib.md5(hash_input1.encode('utf-8')).hexdigest()
    hash_value2 = hashlib.md5(hash_input2.encode('utf-8')).hexdigest()
    hash_value3 = hashlib.md5(hash_input3.encode('utf-8')).hexdigest()
    
    print(f"🔍 Hash Input 1 (ts+private+public): {timestamp + '***' + public_key}")
    print(f"🔍 Hash Input 2 (private+ts+public): {private_key[:10] + '***' + public_key}")
    print(f"🔍 Hash Input 3 (ts+public+private): {timestamp + '***' + private_key[:10]}")
    print(f"🔍 Generated Hash 1: {hash_value1}")
    print(f"🔍 Generated Hash 2: {hash_value2}")
    print(f"🔍 Generated Hash 3: {hash_value3}")
    
    # Use the standard format (timestamp + private_key + public_key)
    hash_value = hash_value1
    
    print(f"🔍 Testing Marvel API Authentication")
    print(f"🔑 Public Key: {public_key}")
    print(f"🔑 Private Key: {private_key}")
    print(f"🔍 Timestamp: {timestamp}")
    print(f"🔍 Hash Input: {timestamp + '***' + public_key}")
    print(f"🔍 Generated Hash: {hash_value}")
    
    # Test API call
    search_url = "https://gateway.marvel.com/v1/public/comics"
    params = {
        'apikey': public_key,
        'ts': timestamp,
        'hash': hash_value,
        'titleStartsWith': 'Iron Man',
        'limit': 5,
        'format': 'comic',
        'formatType': 'comic'
    }
    
    headers = {
        'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
    }
    
    print(f"\n🔍 Making API request...")
    print(f"🔍 URL: {search_url}")
    print(f"🔍 Params: {params}")
    
    try:
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        print(f"📡 Response Status: {response.status_code}")
        print(f"📡 Response URL: {response.url}")
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'results' in data['data']:
                results = data['data']['results']
                print(f"✅ Authentication SUCCESSFUL!")
                print(f"📚 Found {len(results)} results")
                for i, comic in enumerate(results[:3]):
                    print(f"  {i+1}. {comic.get('title', 'Unknown')} #{comic.get('issueNumber', 'Unknown')}")
            else:
                print(f"❌ Unexpected response format: {data}")
        else:
            print(f"❌ Authentication FAILED!")
            print(f"📡 Response Text: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_marvel_auth()
