#!/usr/bin/env python3
"""
Final test script to verify Marvel API authentication using official documentation.
Based on: https://developer.marvel.com/documentation/authorization
"""

import hashlib
import time
import requests

def test_marvel_auth_final():
    """Test Marvel API authentication using official documentation method."""
    
    # Your Marvel API credentials
    public_key = "9e68878e26467b05952fd752d67b0f8c"
    private_key = "e6a5261e0f5f27d9d7eb1b9f8fbd2694ae469117"
    
    print("🔍 Testing Marvel API Authentication (Official Method)")
    print("📋 Based on: https://developer.marvel.com/documentation/authorization")
    print(f"🔑 Public Key: {public_key}")
    print(f"🔑 Private Key: {private_key[:10]}...")
    
    # Marvel API requires timestamp and hash
    # According to docs: hash = md5(ts + privateKey + publicKey)
    timestamp = str(int(time.time()))
    hash_input = timestamp + private_key + public_key
    hash_value = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
    
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
        elif response.status_code == 401:
            print(f"❌ Authentication FAILED!")
            print(f"📡 Response Text: {response.text[:500]}")
            print(f"\n📋 Possible issues:")
            print(f"   - API key is invalid or expired")
            print(f"   - Private key is incorrect")
            print(f"   - Account may need verification")
            print(f"   - Rate limit exceeded")
        elif response.status_code == 409:
            print(f"❌ Missing required parameters!")
            print(f"📡 Response Text: {response.text[:500]}")
            print(f"📋 Required: apikey, ts, hash for server-side applications")
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"📡 Response Text: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_marvel_auth_final()
