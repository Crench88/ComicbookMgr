#!/usr/bin/env python3
"""
Test to verify if the referrer domain issue is causing Marvel API authentication failure.
"""

import hashlib
import time
import requests

def test_marvel_referrer_issue():
    """Test Marvel API with different referrer headers."""
    
    # Your Marvel API credentials
    public_key = "9e68878e26467b05952fd752d67b0f8c"
    private_key = "e6a5261e0f5f27d9d7eb1b9f8fbd2694ae469117"
    
    print("🔍 Testing Marvel API Referrer Domain Issue")
    print(f"🔑 Public Key: {public_key}")
    print(f"🔑 Private Key: {private_key[:10]}...")
    
    # Marvel API requires timestamp and hash
    timestamp = str(int(time.time()))
    hash_input = timestamp + private_key + public_key
    hash_value = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
    
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
    
    # Test 1: No referrer header (should fail)
    print("\n🧪 Test 1: No referrer header")
    headers1 = {
        'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
    }
    
    try:
        response1 = requests.get(search_url, params=params, headers=headers1, timeout=10)
        print(f"📡 Response Status: {response1.status_code}")
        if response1.status_code == 401:
            print("❌ Expected failure - no referrer domain whitelisted")
        else:
            print("✅ Unexpected success!")
    except Exception as e:
        print(f"❌ Request failed: {e}")
    
    # Test 2: With referrer header (should also fail without domain whitelist)
    print("\n🧪 Test 2: With referrer header")
    headers2 = {
        'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x',
        'Referer': 'http://127.0.0.1:5000'
    }
    
    try:
        response2 = requests.get(search_url, params=params, headers=headers2, timeout=10)
        print(f"📡 Response Status: {response2.status_code}")
        if response2.status_code == 401:
            print("❌ Expected failure - domain not whitelisted")
            print(f"📡 Response Text: {response2.text[:200]}...")
        else:
            print("✅ Success! Domain might be whitelisted")
    except Exception as e:
        print(f"❌ Request failed: {e}")
    
    print("\n📋 SOLUTION:")
    print("1. Go to https://developer.marvel.com")
    print("2. Log into your account")
    print("3. Find 'Authorized referrers' section")
    print("4. Add these domains:")
    print("   - 127.0.0.1")
    print("   - localhost")
    print("   - 127.0.0.1:5000")
    print("5. Save changes")
    print("6. Test again!")

if __name__ == '__main__':
    test_marvel_referrer_issue()
