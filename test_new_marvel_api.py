#!/usr/bin/env python3
"""
Test script to verify the new Marvel API credentials are working.
"""

import os
import requests
import hashlib
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_marvel_api():
    """Test the Marvel API with the new credentials."""
    
    # Get API keys from environment
    api_key = os.getenv('MARVEL_API_KEY')
    private_key = os.getenv('MARVEL_PRIVATE_KEY')
    
    print("🔧 Testing Marvel API with new credentials...")
    print(f"🔑 Public Key: {api_key[:10]}..." if api_key else "❌ No public key found")
    print(f"🔑 Private Key: {private_key[:10]}..." if private_key else "❌ No private key found")
    
    if not api_key or not private_key:
        print("❌ Marvel API keys not found in .env file")
        return False
    
    # Marvel API requires timestamp and hash
    timestamp = str(int(time.time()))
    hash_input = timestamp + private_key + api_key
    hash_value = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
    
    search_url = "https://gateway.marvel.com/v1/public/comics"
    
    try:
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
        
        print(f"🔍 Testing search for 'Spider-Man'...")
        print(f"🔍 Hash Input: {timestamp + '***' + api_key}")
        print(f"🔍 Generated Hash: {hash_value}")
        
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        print(f"📡 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'results' in data['data']:
                results = data['data']['results']
                print(f"✅ Success! Found {len(results)} Spider-Man comics")
                
                for i, comic in enumerate(results[:3], 1):
                    title = comic.get('title', 'Unknown')
                    issue = comic.get('issueNumber', 'Unknown')
                    print(f"  {i}. {title} #{issue}")
                
                return True
            else:
                print("❌ No results found in response")
                return False
        elif response.status_code == 401:
            print("❌ Authentication failed - check your API keys")
            print(f"🔍 Response: {response.text[:200]}...")
            return False
        else:
            print(f"❌ API request failed with status {response.status_code}")
            print(f"🔍 Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Marvel API: {e}")
        return False

if __name__ == "__main__":
    success = test_marvel_api()
    
    if success:
        print("\n🎉 Marvel API is working correctly!")
        print("📝 You can now use Marvel API searches in your comic book manager.")
    else:
        print("\n❌ Marvel API test failed.")
        print("📝 Please check your API keys and domain whitelisting.")
