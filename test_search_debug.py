#!/usr/bin/env python3
"""
Debug script to see the actual response from the search API.
"""

import requests
import json

def debug_search_response():
    """Debug the search API response."""
    
    base_url = "http://127.0.0.1:5000"
    search_query = "Iron Man"
    
    print("🔍 Debugging Search API Response")
    print("=" * 50)
    
    params = {"q": search_query, "comicvine": "1", "marvel": "0", "local": "1"}
    
    try:
        response = requests.get(f"{base_url}/comics/search-api", params=params, timeout=10)
        
        print(f"📡 Status Code: {response.status_code}")
        print(f"📡 Response Headers: {dict(response.headers)}")
        print(f"📡 Response Text (first 500 chars): {response.text[:500]}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"✅ JSON parsed successfully: {type(data)}")
                print(f"📋 Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                print(f"📄 Raw response: {response.text}")
        else:
            print(f"❌ HTTP error: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

if __name__ == '__main__':
    debug_search_response()
