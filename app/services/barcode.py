"""Barcode / UPC lookup services."""

import re
import requests

_BARCODE_RE = re.compile(r'^\d{10,20}$')


def extract_barcode(query: str) -> str | None:
    digits = ''.join(c for c in (query or '') if c.isdigit())
    if _BARCODE_RE.match(digits):
        return digits
    return None


def _parse_issue_from_title(title: str) -> str:
    if '#' in title:
        try:
            part = title.split('#', 1)[1].split()[0]
            if part:
                return part
        except (IndexError, AttributeError):
            pass
    return '1'


def search_upc_database_api(upc_code: str, api_key: str) -> list:
    if not api_key or not upc_code:
        return []
    url = f"https://api.upcdatabase.org/product/{upc_code}"
    try:
        response = requests.get(
            url,
            headers={
                'Authorization': f'Bearer {api_key}',
                'User-Agent': 'ComicBookManager/1.0',
            },
            timeout=10,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        if not (data.get('valid') and data.get('product')):
            return []
        product = data['product']
        title = product.get('title', '')
        publisher = product.get('brand') or product.get('manufacturer') or 'Unknown'
        return [{
            'id': f"upc_{upc_code}",
            'title': title,
            'issue_number': _parse_issue_from_title(title),
            'publisher': publisher,
            'characters': '',
            'genre': 'Comic Book',
            'release_date': '',
            'description': product.get('description', ''),
            'cover_image_url': product.get('image', ''),
            'volume': '',
            'series': title.split('#')[0].strip() if '#' in title else title,
            'upc': upc_code,
            'isbn': product.get('isbn', ''),
            'source': 'UPC Database',
            'cover_images': [],
            'has_variants_endpoint': False,
        }]
    except requests.RequestException:
        return []


def search_barcode_lookup_api(upc_code: str, api_key: str) -> list:
    if not api_key or not upc_code:
        return []
    try:
        response = requests.get(
            'https://api.barcodelookup.com/v3/products',
            params={'barcode': upc_code, 'key': api_key},
            headers={'User-Agent': 'ComicBookManager/1.0'},
            timeout=10,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        products = data.get('products') or []
        if not products:
            return []
        product = products[0]
        title = product.get('title', '')
        publisher = product.get('brand') or 'Unknown'
        return [{
            'id': f"barcode_{upc_code}",
            'title': title,
            'issue_number': _parse_issue_from_title(title),
            'publisher': publisher,
            'characters': '',
            'genre': 'Comic Book',
            'release_date': '',
            'description': product.get('description', ''),
            'cover_image_url': (product.get('images') or [''])[0],
            'volume': '',
            'series': title.split('#')[0].strip() if '#' in title else title,
            'upc': upc_code,
            'isbn': '',
            'source': 'Barcode Lookup',
            'cover_images': [],
            'has_variants_endpoint': False,
        }]
    except requests.RequestException:
        return []


def search_barcode(upc_code: str, upc_api_key: str, barcode_api_key: str) -> list:
    """Try UPC Database, then Barcode Lookup."""
    for fn, key in (
        (search_upc_database_api, upc_api_key),
        (search_barcode_lookup_api, barcode_api_key),
    ):
        if not key:
            continue
        results = fn(upc_code, key)
        if results:
            return results
    return []
