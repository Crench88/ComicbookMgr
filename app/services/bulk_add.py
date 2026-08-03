"""
Bulk-add comics from issue ranges via ComicVine lookup.
"""

import re
from datetime import datetime

import requests

from ..models import Comic
from .series_link import apply_series_link
from .cover_storage import persist_primary_cover
from .. import db
from .comicvine import search_comicvine_api, COMICVINE_HEADERS, COMICVINE_TIMEOUT

_RANGE_PART_RE = re.compile(
    r'^\s*(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*$'
)
MAX_BULK_ISSUES = 100

_COVER_HEADERS = {
    **COMICVINE_HEADERS,
    'User-Agent': (
        'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager) Python/3.x'
    ),
}


def _issue_sort_key(value: str) -> tuple:
    text = (value or '').strip()
    match = re.match(r'(\d+(?:\.\d+)?)(.*)', text)
    if match:
        return (float(match.group(1)), match.group(2).lower())
    return (float('inf'), text.lower())


def _format_issue_number(value) -> str:
    """Normalize numeric issue labels (drop trailing .0)."""
    text = str(value).strip()
    if re.fullmatch(r'\d+\.0+', text):
        return str(int(float(text)))
    return text


def parse_issue_ranges(ranges_text: str) -> list[str]:
    """
    Parse issue range strings like '1-32' or '1-14, 16-22, 24-32' or '1, 3, 5'.
    Returns sorted, de-duplicated issue numbers as strings.
    """
    if not ranges_text or not ranges_text.strip():
        raise ValueError('Enter at least one issue or range.')

    issues = []
    seen = set()

    for part in ranges_text.split(','):
        part = part.strip()
        if not part:
            continue
        match = _RANGE_PART_RE.match(part)
        if not match:
            raise ValueError(f'Invalid range segment: "{part}"')

        start_raw, end_raw = match.group(1), match.group(2)
        if end_raw is None:
            values = [start_raw]
        else:
            start_num = float(start_raw)
            end_num = float(end_raw)
            if end_num < start_num:
                raise ValueError(f'Range end must be >= start in "{part}"')
            if start_num == int(start_num) and end_num == int(end_num):
                values = [str(i) for i in range(int(start_num), int(end_num) + 1)]
            else:
                step = 0.1 if '.' in start_raw or '.' in end_raw else 1.0
                current = start_num
                values = []
                while current <= end_num + 1e-9:
                    values.append(_format_issue_number(current))
                    current += step

        for value in values:
            normalized = _format_issue_number(value)
            if normalized not in seen:
                seen.add(normalized)
                issues.append(normalized)

    if not issues:
        raise ValueError('No issues found in the range text.')

    issues.sort(key=_issue_sort_key)
    if len(issues) > MAX_BULK_ISSUES:
        raise ValueError(
            f'Bulk add supports up to {MAX_BULK_ISSUES} issues per run '
            f'({len(issues)} requested). Split into smaller batches.'
        )
    return issues


def _parse_release_date(date_str: str):
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _download_cover(url: str):
    if not url:
        return None
    try:
        response = requests.get(
            url, headers=_COVER_HEADERS, timeout=COMICVINE_TIMEOUT,
        )
        response.raise_for_status()
        content_type = response.headers.get('content-type', 'image/jpeg')
        if 'image/' not in content_type:
            if '.png' in url.lower():
                content_type = 'image/png'
            elif '.webp' in url.lower():
                content_type = 'image/webp'
            else:
                content_type = 'image/jpeg'
        return response.content, content_type
    except requests.RequestException:
        return None


def _user_has_issue(user_id: int, series: str, issue_number: str) -> bool:
    return db.session.query(
        Comic.id
    ).filter_by(
        user_id=user_id,
        series=series,
        issue_number=issue_number,
    ).first() is not None


def lookup_issue_for_bulk(*, series: str, issue_number: str, api_key: str,
                          start_year=None, volume_hint=None,
                          volume_id=None) -> dict | None:
    """Find the best ComicVine match for one issue in a series."""
    if volume_id:
        results = search_comicvine_api(
            '',
            api_key,
            series_name=series.strip(),
            issue_number=issue_number.strip(),
            volume_id=int(volume_id),
        )
        return results[0] if results else None

    query_parts = [series.strip()]
    if start_year:
        query_parts.append(str(start_year))
    query_parts.append(f'#{issue_number}')
    query = ' '.join(query_parts)

    results = search_comicvine_api(
        query,
        api_key,
        series_name=series.strip(),
        issue_number=issue_number.strip(),
    )
    if not results:
        return None

    series_lower = series.strip().lower()
    issue_norm = issue_number.strip().lstrip('0') or '0'

    def _score(result):
        score = 0
        result_series = (result.get('series') or '').lower()
        result_issue = (result.get('issue_number') or '').strip().lstrip('0') or '0'
        if result_issue == issue_norm:
            score += 50
        if result_series == series_lower:
            score += 40
        elif series_lower in result_series:
            score += 20
        if start_year:
            year_str = str(start_year)
            vol_year = (result.get('volume_start_year') or '').strip()
            if vol_year == year_str:
                score += 30
        if volume_hint:
            hint = str(volume_hint).strip().lower()
            vol_name = result_series
            for pattern in (f'vol. {hint}', f'vol {hint}', f'volume {hint}', f'v{hint}'):
                if pattern in vol_name:
                    score += 25
                    break
        if result.get('cover_image_url'):
            score += 5
        return score

    results.sort(key=_score, reverse=True)
    return results[0]


def add_comic_from_search_result(*, result: dict, user_id: int, condition: str = '',
                                 notes: str = '', in_collection: bool = True,
                                 is_digital: bool = False) -> Comic:
    """Create a Comic row from a ComicVine search result, including cover download."""
    series_name = (result.get('series') or result.get('volume') or 'Unknown Series').strip()
    issue_number = (result.get('issue_number') or '').strip()
    title = (result.get('title') or result.get('issue_title') or series_name).strip()

    comic = Comic(
        title=title,
        series=series_name,
        issue_title=title,
        issue_number=issue_number or '?',
        publisher=(result.get('publisher') or 'Unknown').strip() or 'Unknown',
        characters=(result.get('characters') or '').strip() or None,
        **{
            field: (result.get(field) or '').strip() or None
            for field, _ in Comic.CREDIT_FIELDS
        },
        teams=(result.get('teams') or '').strip() or None,
        story_arc=(result.get('story_arc') or '').strip() or None,
        description=(result.get('description') or '').strip() or None,
        comicvine_issue_id=result.get('comicvine_id') or result.get('id'),
        comicvine_url=(result.get('comicvine_url') or '').strip() or None,
        genre=(result.get('genre') or 'Comic').strip() or 'Comic',
        release_date=_parse_release_date(result.get('release_date') or ''),
        upc=(result.get('upc') or '').strip() or None,
        condition=condition or None,
        notes=notes or None,
        user_id=user_id,
    )
    comic.apply_ownership(in_collection=in_collection, is_digital=is_digital)
    apply_series_link(
        comic,
        series_name,
        comicvine_volume_id=result.get('_volume_id') or result.get('comicvine_volume_id'),
        publisher=comic.publisher,
    )

    cover_url = result.get('cover_image_url') or ''
    if not cover_url and result.get('cover_images'):
        first = result['cover_images'][0]
        cover_url = first.get('url') or ''

    cover_data = _download_cover(cover_url)
    db.session.add(comic)
    db.session.flush()
    if cover_data:
        persist_primary_cover(comic, cover_data[0], cover_data[1])
    db.session.commit()
    return comic


def bulk_add_single_issue(*, user_id: int, series: str, issue_number: str,
                          api_key: str, start_year=None, volume_hint=None,
                          volume_id=None, condition: str = '', skip_existing: bool = True,
                          in_collection: bool = True, is_digital: bool = False) -> dict:
    """
    Look up and add one issue. Returns a status dict for the API response.
    """
    series = series.strip()
    issue_number = issue_number.strip()
    if not series:
        return {'status': 'failed', 'issue_number': issue_number, 'error': 'Series is required.'}
    if not issue_number:
        return {'status': 'failed', 'issue_number': issue_number, 'error': 'Issue number is required.'}
    if not api_key:
        return {
            'status': 'failed',
            'issue_number': issue_number,
            'error': 'ComicVine API key is not configured.',
        }

    result = lookup_issue_for_bulk(
        series=series,
        issue_number=issue_number,
        api_key=api_key,
        start_year=start_year,
        volume_hint=volume_hint,
        volume_id=volume_id,
    )
    if not result:
        return {
            'status': 'failed',
            'issue_number': issue_number,
            'error': f'No ComicVine match for {series} #{issue_number}.',
        }

    resolved_series = (result.get('series') or series).strip()
    resolved_issue = (result.get('issue_number') or issue_number).strip()

    if skip_existing and _user_has_issue(user_id, resolved_series, resolved_issue):
        return {
            'status': 'skipped',
            'issue_number': resolved_issue,
            'series': resolved_series,
            'title': result.get('title') or '',
            'reason': 'Already in your collection',
        }

    try:
        comic = add_comic_from_search_result(
            result=result,
            user_id=user_id,
            condition=condition,
            in_collection=in_collection,
            is_digital=is_digital,
        )
        return {
            'status': 'added',
            'issue_number': comic.issue_number,
            'series': comic.series,
            'title': comic.title,
            'comic_id': comic.id,
            'has_cover': comic.has_cover_image(),
        }
    except Exception as exc:
        db.session.rollback()
        return {
            'status': 'failed',
            'issue_number': issue_number,
            'error': str(exc),
        }
