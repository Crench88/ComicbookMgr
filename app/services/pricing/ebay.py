"""Minimal eBay Browse API client used for comic price comparables.

Only the pieces needed for pricing are implemented: an application access token
(client credentials grant, no user consent needed) and keyword search of active
listings on a single marketplace, which defaults to eBay Canada.
"""

from __future__ import annotations

import base64
import os

import requests

from ..cache import cache_get, cache_set

PRODUCTION_HOST = 'https://api.ebay.com'
SANDBOX_HOST = 'https://api.sandbox.ebay.com'
APP_SCOPE = 'https://api.ebay.com/oauth/api_scope'
DEFAULT_MARKETPLACE = 'EBAY_CA'
REQUEST_TIMEOUT = 12

# Currency and delivery country per marketplace, so a Canadian marketplace does
# not silently return prices in another currency.
MARKETPLACES = {
    'EBAY_CA': {'currency': 'CAD', 'country': 'CA', 'site': 'ebay.ca'},
    'EBAY_US': {'currency': 'USD', 'country': 'US', 'site': 'ebay.com'},
    'EBAY_GB': {'currency': 'GBP', 'country': 'GB', 'site': 'ebay.co.uk'},
    'EBAY_AU': {'currency': 'AUD', 'country': 'AU', 'site': 'ebay.com.au'},
}

SEARCH_CACHE_TTL = 6 * 60 * 60


class EbayError(RuntimeError):
    """Base class for eBay lookup failures."""


class EbayCredentialsMissing(EbayError):
    """Raised when no eBay application keys are configured."""


class EbayApiError(EbayError):
    """Raised when eBay rejects or fails a request."""


def _setting(name, default=''):
    """Read a setting from Flask config when in an app context, else the env."""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            value = current_app.config.get(name)
            if value not in (None, ''):
                return value
    except Exception:  # pragma: no cover - Flask always importable in this app
        pass
    return os.environ.get(name, default)


def marketplace_id():
    value = str(_setting('EBAY_MARKETPLACE_ID', DEFAULT_MARKETPLACE) or '').strip().upper()
    return value or DEFAULT_MARKETPLACE


def marketplace_details(marketplace=None):
    key = (marketplace or marketplace_id()).upper()
    return MARKETPLACES.get(key, {'currency': 'CAD', 'country': 'CA', 'site': 'ebay.ca'})


def api_host():
    environment = str(_setting('EBAY_ENVIRONMENT', 'production') or '').strip().lower()
    return SANDBOX_HOST if environment == 'sandbox' else PRODUCTION_HOST


def credentials():
    client_id = str(_setting('EBAY_CLIENT_ID', '') or '').strip()
    client_secret = str(_setting('EBAY_CLIENT_SECRET', '') or '').strip()
    return client_id, client_secret


def credentials_available():
    client_id, client_secret = credentials()
    return bool(client_id and client_secret)


def _token_cache_key(client_id):
    # The token is scoped to the key pair and environment, never to a user.
    return ('ebay_app_token', api_host(), client_id[:12], len(client_id))


def access_token(force_refresh=False):
    """Fetch (and cache) an application access token."""
    client_id, client_secret = credentials()
    if not client_id or not client_secret:
        raise EbayCredentialsMissing(
            'eBay pricing needs EBAY_CLIENT_ID and EBAY_CLIENT_SECRET to be set.'
        )

    cache_key = _token_cache_key(client_id)
    if not force_refresh:
        cached = cache_get(cache_key)
        if cached:
            return cached

    basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    try:
        response = requests.post(
            f'{api_host()}/identity/v1/oauth2/token',
            headers={
                'Authorization': f'Basic {basic}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            data={'grant_type': 'client_credentials', 'scope': APP_SCOPE},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise EbayApiError(f'Could not reach eBay for a token: {exc}') from exc

    if response.status_code != 200:
        raise EbayApiError(
            f'eBay refused the application credentials (HTTP {response.status_code}).'
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise EbayApiError('eBay returned an unreadable token response.') from exc

    token = payload.get('access_token')
    if not token:
        raise EbayApiError('eBay returned no access token.')

    try:
        expires_in = int(payload.get('expires_in', 7200))
    except (TypeError, ValueError):
        expires_in = 7200
    cache_set(cache_key, token, ttl=max(60, expires_in - 120))
    return token


def _build_filter(marketplace, *, buying_options, condition_ids, price_range):
    details = marketplace_details(marketplace)
    parts = []
    if buying_options:
        parts.append('buyingOptions:{%s}' % '|'.join(buying_options))
    if condition_ids:
        parts.append('conditionIds:{%s}' % '|'.join(str(item) for item in condition_ids))
    if price_range:
        low, high = price_range
        parts.append(f'price:[{low}..{high}]')
        parts.append(f'priceCurrency:{details["currency"]}')
    # Only surface listings that can actually be bought from this marketplace.
    parts.append(f'deliveryCountry:{details["country"]}')
    return ','.join(parts)


def search_item_summaries(
    query,
    *,
    marketplace=None,
    limit=50,
    category_id=None,
    buying_options=('FIXED_PRICE',),
    condition_ids=None,
    price_range=None,
    sort=None,
    ttl=SEARCH_CACHE_TTL,
    use_cache=True,
):
    """Search active listings and return the raw item summary dicts."""
    query = (query or '').strip()
    if not query:
        return []

    market = (marketplace or marketplace_id()).upper()
    details = marketplace_details(market)
    limit = max(1, min(int(limit), 200))
    filter_value = _build_filter(
        market,
        buying_options=buying_options,
        condition_ids=condition_ids,
        price_range=price_range,
    )

    params = {'q': query, 'limit': str(limit), 'filter': filter_value}
    if category_id:
        params['category_ids'] = str(category_id)
    if sort:
        params['sort'] = sort

    cache_key = ('ebay_browse_search', market, sorted(params.items()))
    if use_cache:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    headers = {
        'Authorization': f'Bearer {access_token()}',
        'X-EBAY-C-MARKETPLACE-ID': market,
        'X-EBAY-C-ENDUSERCTX': f'contextualLocation=country={details["country"]}',
        'Accept': 'application/json',
    }
    url = f'{api_host()}/buy/browse/v1/item_summary/search'

    try:
        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 401:
            headers['Authorization'] = f'Bearer {access_token(force_refresh=True)}'
            response = requests.get(
                url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
            )
    except requests.RequestException as exc:
        raise EbayApiError(f'Could not reach the eBay Browse API: {exc}') from exc

    if response.status_code == 429:
        raise EbayApiError('eBay rate limit reached. Try again later.')
    if response.status_code != 200:
        raise EbayApiError(f'eBay search failed (HTTP {response.status_code}).')

    try:
        payload = response.json()
    except ValueError as exc:
        raise EbayApiError('eBay returned an unreadable search response.') from exc

    summaries = payload.get('itemSummaries') or []
    if use_cache:
        cache_set(cache_key, summaries, ttl=ttl)
    return summaries
