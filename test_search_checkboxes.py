#!/usr/bin/env python3
"""
Test script to verify the new search checkbox functionality.
"""

import requests
import json

def test_search_checkboxes():
    """Test the search API with different checkbox combinations."""
    
    base_url = "http://127.0.0.1:5000"
    search_query = "Iron Man"
    
    print("🔍 Testing Search Checkbox Functionality")
    print("=" * 50)
    
    # Test cases
    test_cases = [
        {
            "name": "ComicVine Only",
            "params": {"q": search_query, "comicvine": "1", "marvel": "0", "local": "0"}
        },
        {
            "name": "Marvel Only",
            "params": {"q": search_query, "comicvine": "0", "marvel": "1", "local": "0"}
        },
        {
            "name": "Local Only",
            "params": {"q": search_query, "comicvine": "0", "marvel": "0", "local": "1"}
        },
        {
            "name": "ComicVine + Local",
            "params": {"q": search_query, "comicvine": "1", "marvel": "0", "local": "1"}
        },
        {
            "name": "All Sources",
            "params": {"q": search_query, "comicvine": "1", "marvel": "1", "local": "1"}
        }
    ]
    
    for test_case in test_cases:
        print(f"\n🧪 Testing: {test_case['name']}")
        print(f"📋 Parameters: {test_case['params']}")
        
        try:
            response = requests.get(f"{base_url}/comics/search-api", params=test_case['params'], timeout=10)
            
            print(f"📡 Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if 'results' in data:
                    print(f"✅ Found {len(data['results'])} results")
                    if data['results']:
                        print(f"📖 First result: {data['results'][0].get('title', 'Unknown')} #{data['results'][0].get('issue_number', 'Unknown')}")
                else:
                    print("❌ No results in response")
            else:
                print(f"❌ Error: {response.text[:200]}...")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Search checkbox testing completed!")

if __name__ == '__main__':
    test_search_checkboxes()
