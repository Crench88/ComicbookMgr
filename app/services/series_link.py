"""Resolve and apply links between owned Comics and the admin Series catalog."""

from __future__ import annotations

import re

from .. import db
from ..models import Comic, Series

_VOLUME_SUFFIX_RE = re.compile(
    r'^(?P<name>.+?)\s+(?:Vol\.?|Volume)\s*(?P<volume>\d+)\s*$',
    re.IGNORECASE,
)


def _normalize(text: str | None) -> str:
    return ' '.join((text or '').strip().lower().split())


def _parse_volume_suffix(series_text: str) -> tuple[str, str | None]:
    """Split 'Amazing Spider-Man Vol. 1' into (name, volume)."""
    text = (series_text or '').strip()
    match = _VOLUME_SUFFIX_RE.match(text)
    if not match:
        return text, None
    return match.group('name').strip(), match.group('volume').strip()


def _series_volume_key(series: Series) -> str:
    volume = (series.volume or '').strip()
    digits = re.search(r'(\d+)', volume)
    return digits.group(1) if digits else _normalize(volume)


def resolve_catalog_series(
    series_text: str | None = None,
    *,
    catalog_series_id: int | None = None,
    comicvine_volume_id: int | None = None,
    publisher: str | None = None,
    series_rows: list[Series] | None = None,
) -> Series | None:
    """
    Find the best matching Series catalog row.

    Priority:
    1. Explicit catalog_series_id
    2. ComicVine volume id
    3. Exact display_name / name (+ volume) text match
    """
    if catalog_series_id not in (None, ''):
        try:
            series_id = int(catalog_series_id)
        except (TypeError, ValueError):
            series_id = None
        if series_id is not None:
            series = db.session.get(Series, series_id)
            if series is not None:
                return series

    rows = series_rows if series_rows is not None else Series.query.all()
    if not rows:
        return None

    if comicvine_volume_id not in (None, ''):
        try:
            volume_id = int(comicvine_volume_id)
        except (TypeError, ValueError):
            volume_id = None
        if volume_id is not None:
            for series in rows:
                if series.comicvine_volume_id == volume_id:
                    return series

    text = (series_text or '').strip()
    if not text:
        return None

    normalized_text = _normalize(text)
    parsed_name, parsed_volume = _parse_volume_suffix(text)
    normalized_name = _normalize(parsed_name)
    normalized_publisher = _normalize(publisher)

    # Exact display_name match
    display_matches = [
        series for series in rows
        if _normalize(series.display_name) == normalized_text
    ]
    if len(display_matches) == 1:
        return display_matches[0]
    if len(display_matches) > 1 and normalized_publisher:
        pub_matches = [
            series for series in display_matches
            if _normalize(series.publisher) == normalized_publisher
        ]
        if len(pub_matches) == 1:
            return pub_matches[0]

    # Name + volume match
    if parsed_volume:
        volume_matches = [
            series for series in rows
            if _normalize(series.name) == normalized_name
            and _series_volume_key(series) == parsed_volume
        ]
        if len(volume_matches) == 1:
            return volume_matches[0]
        if len(volume_matches) > 1 and normalized_publisher:
            pub_matches = [
                series for series in volume_matches
                if _normalize(series.publisher) == normalized_publisher
            ]
            if len(pub_matches) == 1:
                return pub_matches[0]

    # Exact bare name match when unique (or unique for publisher)
    name_matches = [
        series for series in rows
        if _normalize(series.name) == normalized_text
        or _normalize(series.name) == normalized_name
    ]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1 and normalized_publisher:
        pub_matches = [
            series for series in name_matches
            if _normalize(series.publisher) == normalized_publisher
        ]
        if len(pub_matches) == 1:
            return pub_matches[0]

    return None


def apply_series_link(
    comic: Comic,
    series_text: str | None = None,
    *,
    catalog_series_id: int | None = None,
    comicvine_volume_id: int | None = None,
    publisher: str | None = None,
    sync_series_text: bool = True,
    series_rows: list[Series] | None = None,
) -> Series | None:
    """
    Attach comic.series_id when a catalog match is found.

    Keeps comic.series free-text in sync with the canonical display name when
    linked, so existing series-browser grouping continues to work.
    """
    text = series_text if series_text is not None else comic.series
    text = (text or '').strip()
    publisher = publisher if publisher is not None else comic.publisher

    matched = resolve_catalog_series(
        text,
        catalog_series_id=catalog_series_id,
        comicvine_volume_id=comicvine_volume_id,
        publisher=publisher,
        series_rows=series_rows,
    )

    if matched is not None:
        comic.series_id = matched.id
        if sync_series_text:
            comic.series = matched.display_name
        return matched

    comic.series_id = None
    if series_text is not None:
        comic.series = text
    return None


def backfill_comic_series_links(*, sync_series_text: bool = True) -> dict:
    """Link existing comics to catalog Series rows. Returns match stats."""
    series_rows = Series.query.all()
    comics = Comic.query.filter(Comic.series_id.is_(None)).all()
    linked = 0
    unchanged = 0

    for comic in comics:
        matched = apply_series_link(
            comic,
            comic.series,
            comicvine_volume_id=None,
            publisher=comic.publisher,
            sync_series_text=sync_series_text,
            series_rows=series_rows,
        )
        if matched is not None:
            linked += 1
        else:
            unchanged += 1

    db.session.commit()
    return {
        'linked': linked,
        'unchanged': unchanged,
        'catalog_series': len(series_rows),
    }
