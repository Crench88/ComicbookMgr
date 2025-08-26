#!/usr/bin/env python3
"""
Test to verify which domains work with Marvel API after whitelisting.
"""

import hashlib
import time
import requests

def test_marvel_domains():
    """Test Marvel API with different domain configurations."""
    
    # Your Marvel API credentials
    public_key = "9e68878e26467b05952fd752d67b0f8c"
    private_key = "e6a5261e0f5f27d9d7eb1b9f8fbd2694ae469117"
    
    print("🔍 Testing Marvel API with Different Domain Configurations")
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
    
    # Test different referrer headers
    test_configs = [
        {
            'name': 'No referrer header',
            'headers': {
                'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
            }
        },
        {
            'name': 'Referrer: 127.0.0.1',
            'headers': {
                'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x',
                'Referer': 'http://127.0.0.1'
            }
        },
        {
            'name': 'Referrer: localhost',
            'headers': {
                'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x',
                'Referer': 'http://localhost'
            }
        },
        {
            'name': 'Referrer: 10.0.0.101',
            'headers': {
                'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x',
                'Referer': 'http://10.0.0.101'
            }
        }
    ]
    
    for i, config in enumerate(test_configs, 1):
        print(f"\n🧪 Test {i}: {config['name']}")
        
        try:
            response = requests.get(search_url, params=params, headers=config['headers'], timeout=10)
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ SUCCESS! This configuration works!")
                data = response.json()
                if 'data' in data and 'results' in data['data']:
                    print(f"📚 Found {len(data['data']['results'])} results.")
                    for comic in data['data']['results'][:2]:  # Show first 2
                        print(f"  - {comic.get('title')} (Issue: {comic.get('issueNumber')})")
                break
            else:
                print(f"❌ Failed: {response.status_code}")
                if response.status_code == 401:
                    print(f"📡 Response: {response.text[:100]}...")
                    
        except Exception as e:
            print(f"❌ Request failed: {e}")
    
    print("\n📋 RECOMMENDED DOMAINS TO WHITELIST:")
    print("1. 127.0.0.1")
    print("2. localhost")
    print("3. 10.0.0.101")
    print("4. * (wildcard - allows all domains)")
    print("\n💡 Note: The colon (:) is not allowed in Marvel API domain whitelists.")

if __name__ == '__main__':
    test_marvel_domains()
