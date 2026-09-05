"""Compare owned issues to the SeriesIssue catalog for a collection series."""

from __future__ import annotations

import re

from flask import url_for

from .. import db
from ..models import Comic, Series, SeriesIssue
from .series_link import resolve_catalog_series


_INTEGER_RE = re.compile(r'^(\d+)$')
_LEADING_NUM_RE = re.compile(r'^(\d+(?:\.\d+)?)(.*)$')


def normalize_issue_number(value) -> str:
    """Normalize numeric issue labels (drop trailing .0)."""
    text = str(value or '').strip()
    if re.fullmatch(r'\d+\.0+', text):
        return str(int(float(text)))
    if re.fullmatch(r'0+\d+', text):
        return str(int(text))
    return text


def issue_sort_key(value: str) -> tuple:
    text = normalize_issue_number(value)
    match = _LEADING_NUM_RE.match(text)
    if match:
        return (float(match.group(1)), (match.group(2) or '').strip().lower())
    return (float('inf'), text.lower())


def collapse_issue_ranges(issues: list[str]) -> str:
    """Turn ['1', '2', '3', '5'] into '1-3, 5'. Non-integers stay standalone."""
    ranges: list[str] = []
    start_num = prev_num = None
    start_label = prev_label = None

    def flush():
        nonlocal start_num, prev_num, start_label, prev_label
        if start_num is None:
            return
        if start_num == prev_num:
            ranges.append(start_label)
        else:
            ranges.append(f'{start_label}-{prev_label}')
        start_num = prev_num = None
        start_label = prev_label = None

    for label in sorted((normalize_issue_number(i) for i in issues if i), key=issue_sort_key):
        match = _INTEGER_RE.fullmatch(label)
        if match is None:
            flush()
            ranges.append(label)
            continue
        number = int(match.group(1))
        if start_num is None:
            start_num = prev_num = number
            start_label = prev_label = label
        elif number == prev_num + 1:
            prev_num = number
            prev_label = label
        else:
            flush()
            start_num = prev_num = number
            start_label = prev_label = label
    flush()
    return ', '.join(ranges)


def _owned_issue_numbers(user_id: int, series_name: str) -> set[str]:
    from ..comics.helpers import _series_group_sql

    rows = (
        db.session.query(Comic.issue_number)
        .select_from(Comic)
        .outerjoin(Series, Comic.series_id == Series.id)
        .filter(
            Comic.user_id == user_id,
            Comic.is_wishlist.is_(False),
            _series_group_sql() == series_name,
        )
        .all()
    )
    return {normalize_issue_number(number) for (number,) in rows if number}


def catalog_gaps_for_series(user_id: int, series_name: str | None) -> dict:
    """
    Missing catalog issues for one collection series group.

    Wishlist copies do not count as owned. No catalog match or empty
    SeriesIssue list returns an empty gap payload.
    """
    empty = {
        'catalog_series_id': None,
        'catalog_name': None,
        'catalog_count': 0,
        'owned_count': 0,
        'missing': [],
        'missing_ranges': '',
    }
    name = (series_name or '').strip()
    if not name or name == 'Unknown Series':
        return empty

    catalog = resolve_catalog_series(name)
    if catalog is None:
        return empty

    catalog_numbers = {
        normalize_issue_number(issue.issue_number)
        for issue in SeriesIssue.query.filter_by(series_id=catalog.id).all()
        if issue.issue_number
    }
    if not catalog_numbers:
        return empty

    owned = _owned_issue_numbers(user_id, name)
    missing = sorted(catalog_numbers - owned, key=issue_sort_key)
    return {
        'catalog_series_id': catalog.id,
        'catalog_name': catalog.display_name,
        'catalog_count': len(catalog_numbers),
        'owned_count': len(catalog_numbers & owned),
        'missing': missing,
        'missing_ranges': collapse_issue_ranges(missing),
    }


def serialize_series_gaps(gaps: dict, series_name: str, preview_limit: int = 12) -> dict:
    """JSON / template payload, including a Bulk Add URL when issues are missing."""
    missing = list(gaps.get('missing') or [])
    preview = missing[:preview_limit]
    add_url = None
    if missing:
        add_url = url_for(
            'comics.new',
            tab='bulk',
            series=series_name,
            issues=gaps.get('missing_ranges') or ','.join(missing),
        )
    return {
        'catalog_series_id': gaps.get('catalog_series_id'),
        'catalog_name': gaps.get('catalog_name'),
        'catalog_count': gaps.get('catalog_count') or 0,
        'owned_count': gaps.get('owned_count') or 0,
        'missing': missing,
        'missing_preview': preview,
        'missing_more': max(0, len(missing) - len(preview)),
        'missing_ranges': gaps.get('missing_ranges') or '',
        'add_url': add_url,
    }
