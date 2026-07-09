"""
ComicVine API client — fast structured search with caching and rate limiting.
"""

import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from .cache import cache_get, cache_set

COMICVINE_BASE_URL = "https://comicvine.gamespot.com/api"
COMICVINE_HEADERS = {
    'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager) Python/3.x'
}
COMICVINE_TIMEOUT = 8
MAX_SEARCH_RESULTS = 10

_ISSUE_PREFIX = '4000-'
_VOLUME_PREFIX = '4050-'

_ISSUE_FIELDS = (
    'id,name,issue_number,publisher,character_credits,person_credits,'
    'team_credits,story_arc_credits,deck,description,'
    'store_date,cover_date,image,volume,upc,site_detail_url'
)
_VOLUME_FIELDS = 'id,name,aliases,publisher,start_year,count_of_issues'

_CV_CACHE_TTL_SECONDS = 300
_CV_COVER_TTL_SECONDS = 3600
_cv_rate_lock = Lock()
_cv_last_request_at = 0.0
_CV_MIN_INTERVAL = 1.05  # ComicVine ~1 req/sec per IP

# Major North American English-language comic publishers on ComicVine.
_NA_PUBLISHER_MARKERS = (
    'marvel comics', 'marvel knights', 'marvel enterprises', 'marvel',
    'dc comics', 'dc entertainment', 'dc',
    'image comics', 'image',
    'dark horse comics', 'dark horse',
    'idw publishing', 'idw',
    'boom! studios', 'boom studios', 'boom!',
    'valiant entertainment', 'valiant comics', 'valiant',
    'dynamite entertainment', 'dynamite',
    'archie comics', 'archie',
    'oni press', 'oni ',
    'aftershock comics', 'aftershock',
    'vault comics', 'vault ',
    'top cow productions', 'top cow',
    'vertigo', 'wildstorm', 'milestone comics', 'milestone',
    'skybound', 'shadowline', 'avatar press',
    'black mask studios', 'black mask',
    'scout comics', 'mad cave studios',
    'antarctic press', 'action lab entertainment', 'action lab',
    'alterna comics', 'ahoy comics', 'heavy metal',
)

_NON_NA_PUBLISHER_MARKERS = (
    'panini', 'novaro', 'ecc ediciones', 'ecc ', 'titan comics', 'titan books',
    'egmont', 'editorial novaro', 'grupo editorial', 'editorial televisa',
    'les éditions', 'les editions', 'hachette', 'delcourt', 'glenat', 'glénat',
    'semic', 'urban comics', 'carlsen', 'strip art', 'planet manga',
    'feltrinelli', 'soleil', 'marvel uk', 'panini uk', 'panini verlag',
    'panini comics', 'universo', 'el universo', 'vid', 'norma editorial',
    'astiberri', 'planeta deagostini', 'star comics', 'rw edizioni',
)


def is_north_american_publisher(publisher_name: str) -> bool:
    """Return True when a ComicVine publisher is a major North American imprint."""
    lower = (publisher_name or '').strip().lower()
    if not lower:
        return False
    for marker in _NON_NA_PUBLISHER_MARKERS:
        if marker in lower:
            return False
    for marker in _NA_PUBLISHER_MARKERS:
        if lower == marker or lower.startswith(f'{marker} ') or marker in lower:
            return True
    return False


def publisher_matches_filter(publisher_name: str, *, explicit_publisher: str = '',
                             na_only: bool = True) -> bool:
    """Apply explicit publisher filter, otherwise default to North American only."""
    pub_name = (publisher_name or '').strip()
    explicit = (explicit_publisher or '').strip()
    if explicit:
        return explicit.lower() in pub_name.lower()
    if na_only:
        return is_north_american_publisher(pub_name)
    return True

def _cache_get(key):
    return cache_get(key)


def _cache_set(key, value, ttl=_CV_CACHE_TTL_SECONDS):
    cache_set(key, value, ttl=ttl)


def _rate_limit_wait():
    global _cv_last_request_at
    with _cv_rate_lock:
        elapsed = time.time() - _cv_last_request_at
        if elapsed < _CV_MIN_INTERVAL:
            time.sleep(_CV_MIN_INTERVAL - elapsed)
        _cv_last_request_at = time.time()


def _cv_get(path, params, api_key, ttl=_CV_CACHE_TTL_SECONDS):
    full_params = {**params, 'api_key': api_key, 'format': 'json'}
    cache_key = (path, tuple(sorted(full_params.items())))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    _rate_limit_wait()
    url = f"{COMICVINE_BASE_URL}/{path.lstrip('/')}"
    response = requests.get(
        url, params=full_params, headers=COMICVINE_HEADERS, timeout=COMICVINE_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    _cache_set(cache_key, data, ttl)
    return data


def normalize_issue_number(value: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    if not value.isdigit():
        return value.lower()
    normalized = value.lstrip('0')
    return normalized if normalized else '0'


_ISSUE_ID_PATTERNS = [
    re.compile(r'comicvine\.gamespot\.com/[^\s?#]*?/4000-(\d+)', re.IGNORECASE),
    re.compile(r'\b4000-(\d+)\b'),
    re.compile(r'^\s*cv:?(\d+)\s*$', re.IGNORECASE),
]

_VOLUME_ID_PATTERNS = [
    re.compile(r'comicvine\.gamespot\.com/[^\s?#]*?/4050-(\d+)', re.IGNORECASE),
    re.compile(r'\b4050-(\d+)\b'),
]

_ISSUE_TRAILING_RE = re.compile(r'#?\s*(\d+(?:\.\d+)?)\s*$')
_YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')
_VOLUME_HINT_RE = re.compile(r'(?:^|\s)(?:vol\.?|volume)\s*(\d+)\b', re.IGNORECASE)
_BARCODE_RE = re.compile(r'^\d{10,20}$')


def parse_comicvine_issue_id(query: str):
    if not query:
        return None
    for pat in _ISSUE_ID_PATTERNS:
        m = pat.search(query)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                continue
    return None


def parse_comicvine_volume_id(query: str):
    if not query:
        return None
    for pat in _VOLUME_ID_PATTERNS:
        m = pat.search(query)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                continue
    return None


def extract_barcode(query: str) -> str | None:
    digits = ''.join(c for c in (query or '') if c.isdigit())
    if _BARCODE_RE.match(digits):
        return digits
    return None


def compose_search_query(query='', series_name='', issue_number='') -> str:
    query = (query or '').strip()
    if query:
        return query
    parts = []
    if series_name:
        parts.append(series_name.strip())
    if issue_number:
        parts.append(f"#{issue_number.strip()}")
    return ' '.join(parts)


def parse_query(query: str) -> dict:
    text = (query or '').strip()
    issue = year = volume_hint = None
    if not text:
        return {'series': '', 'issue': None, 'year': None,
                'volume_hint': None, 'raw': ''}

    m = _ISSUE_TRAILING_RE.search(text)
    if m:
        issue = m.group(1)
        text = text[:m.start()].rstrip()

    m = _VOLUME_HINT_RE.search(text)
    if m:
        volume_hint = m.group(1)
        text = (text[:m.start()] + ' ' + text[m.end():]).strip()

    m = _YEAR_RE.search(text)
    if m:
        year = int(m.group(1))
        text = (text[:m.start()] + ' ' + text[m.end():]).strip()

    series = re.sub(r'\s+', ' ', text).strip()
    return {
        'series': series,
        'issue': issue,
        'year': year,
        'volume_hint': volume_hint,
        'raw': (query or '').strip(),
    }


def _strip_html(text: str) -> str:
    if not text:
        return ''
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', cleaned).strip()


def _join_credit_names(credits: list, key: str = 'name') -> str:
    names = []
    for item in credits or []:
        name = (item.get(key) or '').strip()
        if name and name not in names:
            names.append(name)
    return ', '.join(names)


_PERSON_ROLE_BUCKETS = {
    'writer': 'writers',
    'co-writer': 'writers',
    'script': 'writers',
    'plot': 'writers',
    'artist': 'artists',
    'penciler': 'artists',
    'penciller': 'artists',
    'inker': 'inkers',
    'colorist': 'colorists',
    'letterer': 'letterers',
    'editor': 'editors',
    'cover': 'cover_artists',
    'cover artist': 'cover_artists',
    'cover inks': 'cover_artists',
    'cover colors': 'cover_artists',
}


def _extract_person_credits(result: dict) -> dict:
    """Group ComicVine person_credits by creative role."""
    buckets = {key: [] for key in {
        'writers', 'artists', 'inkers', 'colorists', 'letterers', 'editors', 'cover_artists',
    }}

    for person in result.get('person_credits') or []:
        name = (person.get('name') or '').strip()
        if not name:
            continue
        role = (person.get('role') or '').strip().lower()
        bucket = _PERSON_ROLE_BUCKETS.get(role)
        if bucket and name not in buckets[bucket]:
            buckets[bucket].append(name)

    visual_artists = []
    for key in ('artists', 'inkers'):
        for name in buckets[key]:
            if name not in visual_artists:
                visual_artists.append(name)

    def _join(bucket_key: str) -> str:
        return ', '.join(buckets[bucket_key])

    return {
        'writers': buckets['writers'],
        'artists': visual_artists,
        'inkers': buckets['inkers'],
        'colorists': buckets['colorists'],
        'letterers': buckets['letterers'],
        'editors': buckets['editors'],
        'cover_artists': buckets['cover_artists'],
        'writer': _join('writers'),
        'artist': ', '.join(visual_artists),
        'colorist': _join('colorists'),
        'letterer': _join('letterers'),
        'editor': _join('editors'),
        'cover_artist': _join('cover_artists'),
    }


def _extract_issue_description(result: dict) -> str:
    deck = (result.get('deck') or '').strip()
    full_text = _strip_html(result.get('description') or '')
    if deck and full_text and full_text != deck:
        combined = f'{deck}\n\n{full_text}'
    else:
        combined = deck or full_text
    return combined[:5000]


def _format_issue_lightweight(result: dict, series_hint: str = '') -> dict | None:
    if not result or not result.get('id'):
        return None

    volume_info = result.get('volume') or {}
    volume_name = ''
    volume_id = None
    volume_start_year = ''
    if isinstance(volume_info, dict):
        volume_name = (volume_info.get('name') or '').strip()
        volume_id = volume_info.get('id')
        volume_start_year = (volume_info.get('start_year') or '').strip()

    publisher_name = ''
    publisher_data = result.get('publisher')
    if isinstance(publisher_data, dict):
        publisher_name = publisher_data.get('name', '') or ''

    characters = ''
    character_credits = result.get('character_credits') or []
    if character_credits:
        characters = ', '.join(
            c.get('name', '').strip() for c in character_credits if c.get('name')
        )

    image_data = result.get('image') or {}
    primary_url = ''
    if isinstance(image_data, dict):
        primary_url = (
            image_data.get('medium_url')
            or image_data.get('super_url')
            or image_data.get('original_url')
            or ''
        )

    issue_number = (result.get('issue_number') or '').strip()
    issue_name = (result.get('name') or '').strip()
    series_display = volume_name or series_hint or 'Unknown Series'
    people = _extract_person_credits(result)
    teams = _join_credit_names(result.get('team_credits') or [])
    story_arc = _join_credit_names(result.get('story_arc_credits') or [])

    return {
        'id': result.get('id'),
        'comicvine_id': result.get('id'),
        'title': issue_name or volume_name or 'Unknown Title',
        'series': series_display,
        'issue_title': issue_name or '',
        'issue_number': issue_number,
        'publisher': publisher_name,
        'characters': characters,
        'genre': 'Comic',
        'release_date': result.get('store_date') or result.get('cover_date') or '',
        'cover_date': result.get('cover_date') or '',
        'description': _extract_issue_description(result),
        'writer': people['writer'],
        'artist': people['artist'],
        'colorist': people['colorist'],
        'letterer': people['letterer'],
        'editor': people['editor'],
        'cover_artist': people['cover_artist'],
        'teams': teams,
        'story_arc': story_arc,
        'writers': people['writers'],
        'artists': people['artists'],
        'cover_image_url': primary_url,
        'cover_images': [],
        'volume': volume_name,
        'volume_start_year': volume_start_year,
        '_volume_id': volume_id,
        'upc': result.get('upc') or '',
        'isbn': '',
        'comicvine_url': (result.get('site_detail_url') or '').strip(),
        'source': 'ComicVine',
        'has_variants_endpoint': True,
    }


def fetch_issue_by_id(issue_id: int, api_key: str):
    try:
        data = _cv_get(
            f"issue/{_ISSUE_PREFIX}{issue_id}/",
            {'field_list': _ISSUE_FIELDS},
            api_key,
        )
    except requests.RequestException:
        return None
    formatted = _format_issue_lightweight(data.get('results') or {})
    if formatted:
        _enrich_with_volume_meta([formatted], api_key)
    return formatted


def _score_volume(vol: dict, series_lower: str, year, volume_hint=None) -> int:
    name = (vol.get('name') or '').lower()
    aliases = (vol.get('aliases') or '').lower()
    start_year = (vol.get('start_year') or '').strip()
    score = 0
    if not series_lower:
        return score
    if name == series_lower:
        score += 100
    elif series_lower in name:
        score += 40
    if series_lower in aliases:
        score += 25
    if year and start_year == str(year):
        score += 60
    elif year and start_year.isdigit() and abs(int(start_year) - year) <= 1:
        score += 20
    if volume_hint:
        hint = str(volume_hint).strip()
        vol_patterns = (
            f'vol. {hint}',
            f'vol {hint}',
            f'volume {hint}',
            f'v{hint}',
        )
        if any(p in name or p in aliases for p in vol_patterns):
            score += 45
    return score


def _find_volume_ids(series: str, year, api_key: str, limit: int = 5,
                     volume_hint=None, explicit_publisher: str = '',
                     na_publishers_only: bool = True) -> list:
    if not series:
        return []
    try:
        data = _cv_get(
            'search/',
            {
                'query': series,
                'resources': 'volume',
                'field_list': _VOLUME_FIELDS,
                'limit': 30,
            },
            api_key,
        )
    except requests.RequestException:
        return []
    candidates = data.get('results') or []
    series_lower = series.lower()
    scored = []
    for vol in candidates:
        if not publisher_matches_filter(
            _publisher_name(vol),
            explicit_publisher=explicit_publisher,
            na_only=na_publishers_only,
        ):
            continue
        score = _score_volume(vol, series_lower, year, volume_hint)
        if score > 0:
            scored.append((vol, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [vol.get('id') for vol, _ in scored[:limit] if vol.get('id')]


def _publisher_name(volume: dict) -> str:
    publisher = volume.get('publisher') or {}
    if isinstance(publisher, dict):
        return (publisher.get('name') or '').strip()
    return ''


def _format_volume_for_picker(volume: dict, score: int = 0) -> dict:
    name = (volume.get('name') or '').strip()
    start_year = (volume.get('start_year') or '').strip()
    count = volume.get('count_of_issues') or 0
    publisher = _publisher_name(volume)
    vol_match = _VOLUME_HINT_RE.search(name)
    volume_number = vol_match.group(1) if vol_match else ''

    parts = []
    if start_year:
        parts.append(start_year)
    if count:
        parts.append(f'{count} issues')
    date_range_label = ' · '.join(parts) if parts else 'Year unknown'

    return {
        'source': 'ComicVine',
        'comicvine_volume_id': volume.get('id'),
        'local_series_id': None,
        'name': name,
        'display_name': name,
        'publisher': publisher,
        'start_year': start_year,
        'count_of_issues': count,
        'volume_number': volume_number,
        'date_range_label': date_range_label,
        'score': score,
    }


def search_comicvine_volumes(query: str, api_key: str, *, year=None,
                             publisher: str = '', limit: int = 50,
                             na_publishers_only: bool = True) -> list:
    """Return ComicVine volumes matching a series name, sorted by relevance and year."""
    query = (query or '').strip()
    if not query or not api_key:
        return []

    try:
        data = _cv_get(
            'search/',
            {
                'query': query,
                'resources': 'volume',
                'field_list': _VOLUME_FIELDS,
                'limit': 100,
            },
            api_key,
        )
    except requests.RequestException:
        return []

    series_lower = query.lower()
    formatted = []

    for vol in data.get('results') or []:
        pub_name = _publisher_name(vol)
        if not publisher_matches_filter(
            pub_name,
            explicit_publisher=publisher,
            na_only=na_publishers_only,
        ):
            continue
        score = _score_volume(vol, series_lower, year)
        if score <= 0:
            continue
        item = _format_volume_for_picker(vol, score)
        formatted.append(item)

    formatted.sort(key=lambda v: (
        -v.get('score', 0),
        int(v['start_year']) if str(v.get('start_year', '')).isdigit() else 9999,
        v.get('name', '').lower(),
    ))

    seen_ids = set()
    unique = []
    for item in formatted:
        vid = item.get('comicvine_volume_id')
        if vid in seen_ids:
            continue
        seen_ids.add(vid)
        item = {k: v for k, v in item.items() if k != 'score'}
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def search_comicvine_issues_in_volume(volume_id: int, api_key: str,
                                      issue_number: str = '',
                                      query: str = '') -> list:
    """Return issues scoped to a single ComicVine volume."""
    if not volume_id or not api_key:
        return []

    parsed = parse_query(query) if query else {'issue': None, 'series': '', 'raw': ''}
    issue_filter = (issue_number or parsed.get('issue') or '').strip()
    issue_norm = normalize_issue_number(issue_filter) if issue_filter else ''

    raw_issues = _fetch_issues_for_one_volume(int(volume_id), issue_filter, api_key)
    results = []
    seen_ids = set()

    for raw in raw_issues:
        formatted = _format_issue_lightweight(raw)
        if not formatted:
            continue
        rid = formatted.get('id')
        if rid in seen_ids:
            continue
        if issue_norm and normalize_issue_number(formatted.get('issue_number') or '') != issue_norm:
            continue
        seen_ids.add(rid)
        results.append(formatted)

    if not results and query and not issue_filter:
        for raw in _freetext_issue_search(query, api_key, limit=20):
            formatted = _format_issue_lightweight(raw, parsed.get('series', ''))
            if not formatted:
                continue
            if formatted.get('_volume_id') != int(volume_id):
                vol_info = raw.get('volume') or {}
                vol_id = vol_info.get('id') if isinstance(vol_info, dict) else None
                if vol_id != int(volume_id):
                    continue
            rid = formatted.get('id')
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            results.append(formatted)

    _enrich_with_volume_meta(results, api_key)
    return results[:MAX_SEARCH_RESULTS + 10]


def _fetch_issues_for_one_volume(volume_id, issue_number: str, api_key: str) -> list:
    filter_value = f"volume:{volume_id}"
    if issue_number:
        filter_value = f"{filter_value},issue_number:{issue_number}"
    try:
        data = _cv_get(
            'issues/',
            {'filter': filter_value, 'field_list': _ISSUE_FIELDS, 'limit': 20},
            api_key,
        )
    except requests.RequestException:
        return []
    return data.get('results') or []


def _fetch_issues_for_volumes(volume_ids: list, issue_number: str, api_key: str) -> list:
    if not volume_ids:
        return []
    if len(volume_ids) == 1:
        return _fetch_issues_for_one_volume(volume_ids[0], issue_number, api_key)
    issues = []
    with ThreadPoolExecutor(max_workers=min(5, len(volume_ids))) as pool:
        for batch in pool.map(
            lambda vid: _fetch_issues_for_one_volume(vid, issue_number, api_key),
            volume_ids,
        ):
            issues.extend(batch)
    return issues


def _fetch_volume_meta(volume_id, api_key: str) -> dict:
    if not volume_id or not api_key:
        return {}
    try:
        data = _cv_get(
            f"volume/{_VOLUME_PREFIX}{volume_id}/",
            {'field_list': 'id,name,start_year,publisher'},
            api_key,
            ttl=_CV_COVER_TTL_SECONDS,
        )
    except requests.RequestException:
        return {}
    result = data.get('results') or {}
    publisher = result.get('publisher') or {}
    return {
        'name': (result.get('name') or '').strip(),
        'start_year': (result.get('start_year') or '').strip(),
        'publisher_name': (publisher.get('name') or '').strip() if isinstance(publisher, dict) else '',
    }


def _enrich_with_volume_meta(results: list, api_key: str) -> None:
    if not results or not api_key:
        return
    needed = {}
    for r in results:
        if r.get('volume_start_year') and r.get('publisher'):
            continue
        vid = r.get('_volume_id')
        if vid:
            needed.setdefault(vid, []).append(r)
    if not needed:
        return
    with ThreadPoolExecutor(max_workers=min(5, len(needed))) as pool:
        meta_by_vid = dict(zip(
            needed.keys(),
            pool.map(lambda vid: _fetch_volume_meta(vid, api_key), needed.keys()),
        ))
    for vid, rs in needed.items():
        meta = meta_by_vid.get(vid) or {}
        for r in rs:
            if not r.get('volume_start_year'):
                r['volume_start_year'] = meta.get('start_year', '')
            if not r.get('publisher'):
                r['publisher'] = meta.get('publisher_name', '')
            if not r.get('series') or r.get('series') == 'Unknown Series':
                if meta.get('name'):
                    r['series'] = meta['name']
                    r['volume'] = meta['name']


def _freetext_issue_search(query: str, api_key: str, limit: int = 20) -> list:
    if not query:
        return []
    try:
        data = _cv_get(
            'search/',
            {
                'query': query,
                'resources': 'issue',
                'field_list': _ISSUE_FIELDS,
                'limit': limit,
            },
            api_key,
        )
    except requests.RequestException:
        return []
    return data.get('results') or []


def search_comicvine_by_upc(upc: str, api_key: str) -> list:
    if not api_key or not upc:
        return []
    try:
        data = _cv_get(
            'issues/',
            {'filter': f'upc:{upc}', 'field_list': _ISSUE_FIELDS, 'limit': 5},
            api_key,
        )
    except requests.RequestException:
        return []
    results = []
    for raw in data.get('results') or []:
        formatted = _format_issue_lightweight(raw)
        if formatted:
            results.append(formatted)
    if results:
        _enrich_with_volume_meta(results, api_key)
    return results


def search_comicvine_api(query: str, api_key: str,
                         series_name: str = '', issue_number: str = '',
                         volume_id: int | None = None,
                         na_publishers_only: bool = True) -> list:
    if not api_key:
        return []

    if volume_id:
        return search_comicvine_issues_in_volume(
            int(volume_id), api_key,
            issue_number=issue_number,
            query=compose_search_query(query, series_name, issue_number),
        )

    query = compose_search_query(query, series_name, issue_number)
    if not query:
        return []

    issue_id = parse_comicvine_issue_id(query)
    if issue_id:
        formatted = fetch_issue_by_id(issue_id, api_key)
        return [formatted] if formatted else []

    parsed = parse_query(query)
    results = []
    seen_ids = set()
    issue_norm = normalize_issue_number(parsed['issue']) if parsed['issue'] else ''

    def _push(raw_issue):
        formatted = _format_issue_lightweight(raw_issue, parsed['series'])
        if not formatted:
            return
        rid = formatted['id']
        if rid in seen_ids:
            return
        if issue_norm and normalize_issue_number(formatted['issue_number']) != issue_norm:
            return
        seen_ids.add(rid)
        results.append(formatted)

    if parsed['series'] and parsed['issue']:
        volume_ids = _find_volume_ids(
            parsed['series'], parsed['year'], api_key, limit=5,
            volume_hint=parsed.get('volume_hint'),
            na_publishers_only=na_publishers_only,
        )
        if volume_ids:
            for issue in _fetch_issues_for_volumes(volume_ids, parsed['issue'], api_key):
                _push(issue)

    if not results:
        for issue in _freetext_issue_search(parsed['raw'] or parsed['series'], api_key, limit=20):
            _push(issue)

    _enrich_with_volume_meta(results, api_key)

    if na_publishers_only:
        results = [
            r for r in results
            if publisher_matches_filter(r.get('publisher', ''), na_only=True)
        ]

    parsed_series_lower = parsed['series'].lower()
    parsed_year = parsed['year']

    def _rank(r):
        start_year = r.get('volume_start_year') or ''
        year_match = 0
        if parsed_year and start_year == str(parsed_year):
            year_match = 2
        elif parsed_year and start_year.isdigit() and abs(int(start_year) - parsed_year) <= 1:
            year_match = 1
        series_low = (r.get('series') or '').lower()
        name_match = 0
        if parsed_series_lower and parsed_series_lower == series_low:
            name_match = 2
        elif parsed_series_lower and parsed_series_lower in series_low:
            name_match = 1
        return (-year_match, -name_match)

    results.sort(key=_rank)
    return results[:MAX_SEARCH_RESULTS]


def _upgrade_cover_url(url: str) -> str:
    """Prefer a higher-resolution ComicVine CDN URL when available."""
    if not url:
        return url
    for old, new in (
        ('scale_small', 'scale_large'),
        ('scale_medium', 'scale_large'),
        ('scale_avatar', 'scale_large'),
        ('square_avatar', 'scale_large'),
        ('square_small', 'scale_large'),
    ):
        if old in url:
            return url.replace(old, new)
    return url


def _score_result_for_form(result: dict, series: str, issue_number: str,
                           title: str = '', publisher: str = '') -> int:
    score = 0
    series_lower = (series or '').strip().lower()
    issue_norm = normalize_issue_number(issue_number)
    title_lower = (title or '').strip().lower()
    publisher_lower = (publisher or '').strip().lower()

    result_series = (result.get('series') or '').lower()
    result_issue = normalize_issue_number(result.get('issue_number') or '')
    result_title = (result.get('title') or result.get('issue_title') or '').lower()
    result_publisher = (result.get('publisher') or '').lower()

    if issue_norm and result_issue == issue_norm:
        score += 50
    if series_lower and result_series == series_lower:
        score += 40
    elif series_lower and series_lower in result_series:
        score += 20
    if title_lower and title_lower == result_title:
        score += 35
    elif title_lower and len(title_lower) >= 4 and title_lower in result_title:
        score += 25
    elif title_lower and len(title_lower) >= 4 and result_title in title_lower:
        score += 15
    if publisher_lower and publisher_lower == result_publisher:
        score += 20
    elif publisher_lower and publisher_lower in result_publisher:
        score += 10
    if result.get('cover_image_url'):
        score += 3
    return score


def lookup_issue_metadata_for_refresh(*, comicvine_issue_id=None, series='',
                                       issue_number='', title='', publisher='',
                                       api_key='', na_publishers_only=True,
                                       start_year=None) -> dict:
    """Look up ComicVine metadata for refreshing an existing comic on the edit form."""
    if not api_key:
        return {'error': 'ComicVine API key is not configured.'}

    series = (series or '').strip()
    issue_number = (issue_number or '').strip()
    title = (title or '').strip()

    if comicvine_issue_id:
        result = fetch_issue_by_id(int(comicvine_issue_id), api_key)
        if result:
            return {'metadata': result, 'matched_by': 'comicvine_id'}

    if not series and not issue_number:
        return {
            'error': (
                'No ComicVine issue id is stored for this comic. '
                'Use Search to link an issue, or ensure series and issue number are set.'
            ),
        }

    query_hint = compose_search_query('', series, issue_number)
    if start_year and issue_number:
        query_hint = f'{series} {start_year} #{issue_number}'.strip()
    elif start_year:
        query_hint = f'{series} {start_year}'.strip()

    results = search_comicvine_api(
        query_hint,
        api_key,
        series_name=series,
        issue_number=issue_number,
        na_publishers_only=na_publishers_only,
    )
    if not results and title:
        title_query = f'{series} {title} #{issue_number}'.strip()
        if start_year:
            title_query = f'{series} {start_year} {title} #{issue_number}'.strip()
        results = search_comicvine_api(
            title_query,
            api_key,
            series_name=series,
            issue_number=issue_number,
            na_publishers_only=na_publishers_only,
        )
    if not results:
        label = f'{series} #{issue_number}'.strip() if series else f'issue #{issue_number}'
        return {'error': f'No ComicVine match found for {label}.'}

    ranked = sorted(
        results,
        key=lambda r: _score_result_for_form(r, series, issue_number, title, publisher),
        reverse=True,
    )
    best = ranked[0]
    issue_id = best.get('comicvine_id') or best.get('id')
    if issue_id:
        full = fetch_issue_by_id(int(issue_id), api_key)
        if full:
            return {'metadata': full, 'matched_by': 'search'}
    return {'metadata': best, 'matched_by': 'search'}


def lookup_covers_for_form(*, series: str, issue_number: str, title: str = '',
                           publisher: str = '', api_key: str = '',
                           max_issues: int = 3,
                           na_publishers_only: bool = True) -> dict:
    """
    Find ComicVine issues matching the form fields and return merged cover options.
    Pulls variants from the best-matching issue(s), not just the first search hit.
    """
    series = (series or '').strip()
    issue_number = (issue_number or '').strip()
    if not api_key:
        return {'covers': [], 'error': 'ComicVine API key is not configured.'}
    if not series and not issue_number and not title:
        return {'covers': [], 'error': 'Enter at least series, issue, or title.'}

    results = search_comicvine_api(
        '',
        api_key,
        series_name=series,
        issue_number=issue_number,
        na_publishers_only=na_publishers_only,
    )
    if not results and title:
        results = search_comicvine_api(
            f'{series} {title} #{issue_number}'.strip(),
            api_key,
            series_name=series,
            issue_number=issue_number,
            na_publishers_only=na_publishers_only,
        )
    if not results:
        return {'covers': [], 'error': 'No matching ComicVine issues found.'}

    ranked = sorted(
        results,
        key=lambda r: _score_result_for_form(r, series, issue_number, title, publisher),
        reverse=True,
    )
    top_score = _score_result_for_form(ranked[0], series, issue_number, title, publisher)
    issue_norm = normalize_issue_number(issue_number)
    issue_candidates = []
    for candidate in ranked:
        if len(issue_candidates) >= max_issues:
            break
        if not publisher_matches_filter(
            candidate.get('publisher', ''),
            explicit_publisher=publisher,
            na_only=na_publishers_only,
        ):
            continue
        candidate_score = _score_result_for_form(
            candidate, series, issue_number, title, publisher,
        )
        if candidate_score < max(35, top_score - 40):
            continue
        if issue_norm:
            candidate_issue = normalize_issue_number(candidate.get('issue_number') or '')
            if candidate_issue != issue_norm:
                continue
        issue_candidates.append(candidate)
    if not issue_candidates:
        issue_candidates = [ranked[0]]

    merged_covers = []
    seen_urls = set()
    multi_source = len(issue_candidates) > 1

    for result in issue_candidates:
        issue_id = result.get('comicvine_id')
        if not issue_id:
            continue
        issue_label = (result.get('title') or result.get('series') or 'Issue').strip()
        for cover in fetch_comicvine_issue_covers(issue_id, api_key):
            url = _upgrade_cover_url(cover.get('url') or '')
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            label = (cover.get('label') or 'Cover').strip()
            if multi_source:
                label = f'{label} — {issue_label}'
            merged_covers.append({
                'url': url,
                'label': label,
                'size': cover.get('size') or 'large',
                'comicvine_id': issue_id,
            })

    if not merged_covers:
        return {
            'covers': [],
            'error': 'No cover images found on ComicVine for this issue.',
            'best_match': ranked[0],
        }

    return {
        'covers': merged_covers,
        'best_match': ranked[0],
        'issue_count': len(issue_candidates),
    }


def fetch_comicvine_issue_covers(issue_id: int, api_key: str) -> list:
    cache_key = ('issue_covers', int(issue_id))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    covers = []
    seen = set()

    def _add(url, label):
        if not url or url in seen:
            return
        seen.add(url)
        covers.append({
            'url': _upgrade_cover_url(url),
            'label': label or 'Cover',
            'size': 'medium',
        })

    if api_key:
        try:
            data = _cv_get(
                f"issue/{_ISSUE_PREFIX}{issue_id}/",
                {'field_list': 'id,name,issue_number,image,associated_images,volume'},
                api_key,
                ttl=_CV_COVER_TTL_SECONDS,
            )
            result = data.get('results') or {}
            primary = result.get('image') or {}
            _add(
                primary.get('medium_url') or primary.get('super_url')
                or primary.get('original_url') or '',
                'Regular Cover',
            )
            for assoc in (result.get('associated_images') or []):
                caption = (assoc.get('caption') or '').strip() or f'Variant Cover {len(covers)}'
                _add(assoc.get('original_url') or assoc.get('image') or '', caption)
        except requests.RequestException:
            pass

    if len(covers) <= 1:
        for cov in _scrape_issue_page_covers(issue_id):
            _add(cov['url'], cov['label'])

    _cache_set(cache_key, covers, ttl=_CV_COVER_TTL_SECONDS)
    return covers


def _scrape_issue_page_covers(issue_id: int) -> list:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    web_url = f"https://comicvine.gamespot.com/issue/{_ISSUE_PREFIX}{issue_id}/"
    try:
        response = requests.get(
            web_url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; ComicBookManager/1.0)'},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    found = []
    seen = set()
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        if 'comicvine.gamespot.com/a/uploads/' not in src:
            continue
        if any(skip in src for skip in ('avatar', 'square_small', 'square_avatars')):
            continue
        if src in seen:
            continue
        seen.add(src)
        label = (img.get('alt') or '').strip() or f'Cover {len(found) + 1}'
        found.append({'url': src, 'label': label})
        if len(found) >= 20:
            break
    return found


def fetch_volume_issues_for_import(volume_id: int, api_key: str, offset: int = 0,
                                   limit: int = 100) -> tuple[list, int]:
    """Return (issue dicts, total_count) for admin catalog import."""
    try:
        data = _cv_get(
            'issues/',
            {
                'filter': f'volume:{volume_id}',
                'field_list': _ISSUE_FIELDS,
                'limit': limit,
                'offset': offset,
                'sort': 'issue_number:asc',
            },
            api_key,
            ttl=_CV_COVER_TTL_SECONDS,
        )
    except requests.RequestException:
        return [], 0
    raw_issues = data.get('results') or []
    formatted = []
    for raw in raw_issues:
        item = _format_issue_lightweight(raw)
        if item:
            formatted.append(item)
    if formatted:
        _enrich_with_volume_meta(formatted, api_key)
    total = data.get('number_of_total_results') or len(formatted)
    return formatted, total


def fetch_volume_detail(volume_id: int, api_key: str) -> dict:
    return _fetch_volume_meta(volume_id, api_key)
