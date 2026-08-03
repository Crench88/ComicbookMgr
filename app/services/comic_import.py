"""Parse and validate comic collection CSV/JSON imports."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from io import StringIO

from .. import db
from ..models import Comic
from .series_link import apply_series_link

HEADER_ALIASES = {
    'title': {'title', 'issue title', 'issue_title', 'name'},
    'series': {'series', 'series name', 'series_name', 'volume'},
    'issue_number': {'issue number', 'issue_number', 'issue', 'issue #', 'number', '#'},
    'publisher': {'publisher'},
    'writer': {'writer', 'writers', 'writer(s)'},
    'artist': {'artist', 'artists', 'artist(s)'},
    'characters': {'characters', 'character'},
    'story_arc': {'story arc', 'story_arc', 'arc'},
    'genre': {'genre'},
    'release_date': {'release date', 'release_date', 'date', 'cover date', 'cover_date'},
    'condition': {'condition'},
    'estimated_value': {'estimated value', 'estimated_value', 'value', 'price'},
    'description': {'description', 'synopsis'},
    'notes': {'notes', 'note'},
    'upc': {'upc', 'upc code', 'barcode'},
    'is_wishlist': {'wishlist', 'is_wishlist', 'is wishlist'},
    'in_collection': {'in collection', 'in_collection', 'collection'},
    'is_digital': {'digital', 'is_digital', 'is digital'},
}

REQUIRED_FIELDS = ('series', 'issue_number', 'publisher')


def _norm_header(value: str) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def _map_headers(headers: list[str]) -> dict[str, str]:
    mapping = {}
    for header in headers:
        key = _norm_header(header)
        for field, aliases in HEADER_ALIASES.items():
            if key in aliases and field not in mapping.values():
                mapping[header] = field
                break
    return mapping


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or '').strip().lower()
    return text in {'1', 'true', 'yes', 'y', 'wishlist'}


def _parse_date(value):
    text = str(value or '').strip()
    if not text:
        return None, None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d', '%B %Y', '%b %Y', '%Y'):
        try:
            dt = datetime.strptime(text, fmt)
            if fmt in ('%B %Y', '%b %Y', '%Y'):
                dt = dt.replace(day=1)
            return dt.date(), None
        except ValueError:
            continue
    return None, f'Unrecognized date "{text}"'


def _parse_value(value):
    text = str(value or '').strip().replace('$', '').replace(',', '')
    if not text:
        return 0.0, None
    try:
        return float(text), None
    except ValueError:
        return 0.0, f'Invalid value "{value}"'


def _row_to_record(raw: dict, source_index: int) -> dict:
    errors = []
    record = {
        'source_index': source_index,
        'title': (raw.get('title') or '').strip(),
        'series': (raw.get('series') or '').strip(),
        'issue_number': str(raw.get('issue_number') or '').strip(),
        'publisher': (raw.get('publisher') or '').strip(),
        'writer': (raw.get('writer') or '').strip() or None,
        'artist': (raw.get('artist') or '').strip() or None,
        'characters': (raw.get('characters') or '').strip() or None,
        'story_arc': (raw.get('story_arc') or '').strip() or None,
        'genre': (raw.get('genre') or '').strip() or None,
        'condition': (raw.get('condition') or '').strip() or None,
        'description': (raw.get('description') or '').strip() or None,
        'notes': (raw.get('notes') or '').strip() or None,
        'upc': (raw.get('upc') or '').strip() or None,
        'is_wishlist': _parse_bool(raw.get('is_wishlist')),
        'in_collection': None,
        'is_digital': _parse_bool(raw.get('is_digital')),
        'release_date': None,
        'estimated_value': 0.0,
        'status': 'new',
        'errors': [],
        'existing_id': None,
    }

    if not record['series']:
        # Fall back to title-as-series for older exports that omit Series.
        if record['title']:
            record['series'] = record['title']
        else:
            errors.append('Series is required')
    if not record['issue_number']:
        errors.append('Issue Number is required')
    if not record['publisher']:
        errors.append('Publisher is required')
    if not record['title']:
        record['title'] = record['series'] or 'Untitled'

    release_date, date_error = _parse_date(raw.get('release_date'))
    if date_error:
        errors.append(date_error)
    record['release_date'] = release_date

    value, value_error = _parse_value(raw.get('estimated_value'))
    if value_error:
        errors.append(value_error)
    record['estimated_value'] = value

    # Prefer explicit ownership columns; fall back to legacy wishlist.
    if raw.get('in_collection') is not None and str(raw.get('in_collection')).strip() != '':
        record['in_collection'] = _parse_bool(raw.get('in_collection'))
    elif record['is_wishlist']:
        record['in_collection'] = False
    else:
        record['in_collection'] = True

    record['errors'] = errors
    if errors:
        record['status'] = 'invalid'
    return record


def parse_csv_text(text: str) -> list[dict]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError('CSV file has no header row.')
    mapping = _map_headers(list(reader.fieldnames))
    if 'issue_number' not in mapping.values() or 'publisher' not in mapping.values():
        raise ValueError(
            'CSV must include Issue Number and Publisher columns '
            '(Series is recommended; Title can stand in for Series).'
        )

    records = []
    for index, row in enumerate(reader, start=2):
        if not any((value or '').strip() for value in row.values()):
            continue
        normalized = {}
        for header, value in row.items():
            field = mapping.get(header)
            if field:
                normalized[field] = value
        records.append(_row_to_record(normalized, index))
    return records


def parse_json_text(text: str) -> list[dict]:
    payload = json.loads(text)
    if isinstance(payload, dict):
        payload = payload.get('comics') or payload.get('items') or payload.get('data') or []
    if not isinstance(payload, list):
        raise ValueError('JSON must be a list of comic objects.')

    records = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            records.append({
                'source_index': index,
                'status': 'invalid',
                'errors': ['Each JSON item must be an object'],
                'title': '',
                'series': '',
                'issue_number': '',
                'publisher': '',
            })
            continue
        normalized = {}
        for key, value in item.items():
            field = None
            key_norm = _norm_header(str(key))
            for candidate, aliases in HEADER_ALIASES.items():
                if key_norm == candidate or key_norm in aliases:
                    field = candidate
                    break
            if field:
                normalized[field] = value
        records.append(_row_to_record(normalized, index))
    return records


def annotate_duplicates(records: list[dict], user_id: int) -> list[dict]:
    existing = Comic.query.filter_by(user_id=user_id).all()
    by_key = {}
    for comic in existing:
        key = (
            (comic.series or '').strip().lower(),
            (comic.issue_number or '').strip().lower(),
            (comic.upc or '').strip(),
        )
        by_key.setdefault(key, comic)
        by_key.setdefault(
            ((comic.series or '').strip().lower(), (comic.issue_number or '').strip().lower(), ''),
            comic,
        )

    for record in records:
        if record.get('status') == 'invalid':
            continue
        key_upc = (
            record['series'].strip().lower(),
            record['issue_number'].strip().lower(),
            (record.get('upc') or '').strip(),
        )
        key = (
            record['series'].strip().lower(),
            record['issue_number'].strip().lower(),
            '',
        )
        match = by_key.get(key_upc) or by_key.get(key)
        if match:
            record['status'] = 'duplicate'
            record['existing_id'] = match.id
    return records


def import_records(records: list[dict], user_id: int, *, skip_duplicates: bool = True) -> dict:
    added = 0
    skipped = 0
    failed = 0

    for record in records:
        if record.get('status') == 'invalid':
            failed += 1
            continue
        if record.get('status') == 'duplicate' and skip_duplicates:
            skipped += 1
            continue

        comic = Comic(
            title=record['title'],
            series=record['series'],
            issue_title=record['title'],
            issue_number=record['issue_number'],
            publisher=record['publisher'],
            writer=record.get('writer'),
            artist=record.get('artist'),
            characters=record.get('characters'),
            story_arc=record.get('story_arc'),
            genre=record.get('genre'),
            release_date=record.get('release_date'),
            condition=record.get('condition'),
            estimated_value=record.get('estimated_value') or 0.0,
            description=record.get('description'),
            notes=record.get('notes'),
            upc=record.get('upc'),
            user_id=user_id,
        )
        comic.apply_ownership(
            in_collection=record.get('in_collection', True),
            is_digital=record.get('is_digital', False),
        )
        apply_series_link(comic, record['series'], publisher=record['publisher'])
        db.session.add(comic)
        added += 1

    db.session.commit()
    return {'added': added, 'skipped': skipped, 'failed': failed}
