"""Search, ComicVine, cover-fetch, and value-estimate API routes."""

import time
from datetime import datetime

import requests
from flask import current_app, jsonify, request, url_for
from sqlalchemy import or_
from flask_login import current_user, login_required

from ..models import Comic
from .. import db
from ..services.comicvine import (
    fetch_comicvine_issue_covers,
    lookup_covers_for_form,
    lookup_issue_metadata_for_refresh,
    search_comicvine_volumes,
)
from ..services.local_catalog import search_local_series_volumes
from ..services.pricing import estimate_market_value
from ..services.safe_http import UnsafeRemoteUrl, fetch_public_image
from ..services.search_orchestrator import run_comic_search
from ..services.characters import sync_character_mentions
from ..services.series_link import apply_series_link
from . import comics_bp
from .helpers import _na_publishers_only_from_request


def _parse_release_date(value):
    text = (value or '').strip()
    if not text:
        return None
    for raw, fmt in (
        (text[:10], '%Y-%m-%d'),
        (text[:7], '%Y-%m'),
        (text[:4], '%Y'),
    ):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if fmt == '%Y':
            return datetime(parsed.year, 1, 1).date()
        if fmt == '%Y-%m':
            return datetime(parsed.year, parsed.month, 1).date()
        return parsed.date()
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).date()
    except ValueError:
        return None


def _apply_comicvine_metadata(comic, metadata):
    """Copy ComicVine metadata onto a comic without touching collection fields."""
    if not metadata:
        return

    title = (metadata.get('title') or metadata.get('issue_title') or '').strip()
    if title:
        comic.title = title[:200]

    series = (metadata.get('series') or metadata.get('volume') or '').strip()
    if series:
        comic.series = series[:200]

    issue_number = str(metadata.get('issue_number') or '').strip()
    if issue_number:
        comic.issue_number = issue_number[:50]

    publisher = (metadata.get('publisher') or '').strip()
    if publisher:
        comic.publisher = publisher[:100]

    genre = (metadata.get('genre') or '').strip()
    if genre:
        comic.genre = genre[:100]

    characters = (metadata.get('characters') or '').strip()
    if characters:
        comic.characters = characters

    for field, _label in Comic.CREDIT_FIELDS:
        value = metadata.get(field)
        if isinstance(value, list):
            value = ', '.join(str(item).strip() for item in value if str(item).strip())
        value = (value or '').strip()
        if value:
            setattr(comic, field, value)

    teams = (metadata.get('teams') or '').strip()
    if teams:
        comic.teams = teams

    story_arc = (metadata.get('story_arc') or '').strip()
    if story_arc:
        comic.story_arc = story_arc[:200]

    description = (metadata.get('description') or '').strip()
    if description:
        comic.description = description

    upc = (metadata.get('upc') or '').strip()
    if upc:
        comic.upc = upc[:50]

    comicvine_id = metadata.get('comicvine_id') or metadata.get('id')
    if comicvine_id:
        try:
            comic.comicvine_issue_id = int(comicvine_id)
        except (TypeError, ValueError):
            pass

    comicvine_url = (metadata.get('comicvine_url') or '').strip()
    if comicvine_url:
        comic.comicvine_url = comicvine_url[:500]

    release_date = _parse_release_date(metadata.get('release_date') or metadata.get('cover_date'))
    if release_date:
        comic.release_date = release_date

    volume_id = metadata.get('comicvine_volume_id') or metadata.get('_volume_id')
    if volume_id:
        apply_series_link(
            comic,
            series_text=comic.series,
            comicvine_volume_id=volume_id,
            publisher=comic.publisher,
        )

@comics_bp.route('/comics/comicvine/issue/<int:issue_id>/covers')
@login_required
def comicvine_issue_covers(issue_id):
    """Lazily fetch the cover gallery for a ComicVine issue."""
    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    covers = fetch_comicvine_issue_covers(issue_id, api_key)
    return jsonify({'covers': covers, 'issue_id': issue_id})


@comics_bp.route('/comics/comicvine/covers/lookup')
@login_required
def comicvine_covers_lookup():
    """Find ComicVine cover variants for the series/issue on the comic form."""
    series_name = request.args.get('series_name', '').strip()
    issue_number = request.args.get('issue_number', '').strip()
    title = request.args.get('title', '').strip()
    publisher = request.args.get('publisher', '').strip()

    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    if not api_key:
        return jsonify({
            'error': 'ComicVine API key is not configured. Add COMICVINE_API_KEY to your .env file.',
            'covers': [],
        }), 503

    try:
        payload = lookup_covers_for_form(
            series=series_name,
            issue_number=issue_number,
            title=title,
            publisher=publisher,
            api_key=api_key,
            na_publishers_only=_na_publishers_only_from_request(),
        )
        if payload.get('error') and not payload.get('covers'):
            return jsonify(payload), 404
        return jsonify(payload)
    except requests.RequestException as exc:
        return jsonify({'error': f'ComicVine lookup failed: {exc}', 'covers': []}), 502
    except Exception as exc:
        return jsonify({'error': f'ComicVine lookup failed: {exc}', 'covers': []}), 500


@comics_bp.route('/comics/<int:id>/comicvine/refresh', methods=['GET', 'POST'])
@login_required
def refresh_comicvine_metadata(id):
    """Re-fetch ComicVine metadata for an existing comic.

    GET returns metadata/covers for the edit form to preview.
    POST applies the metadata to the saved comic and reloads the show page.
    """
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    if not api_key:
        return jsonify({
            'error': 'ComicVine API key is not configured. Add COMICVINE_API_KEY to your .env file.',
        }), 503

    try:
        payload = lookup_issue_metadata_for_refresh(
            comicvine_issue_id=comic.comicvine_issue_id,
            series=comic.series_label if comic.series_label != 'Unknown Series' else '',
            issue_number=comic.issue_number or '',
            title=comic.title or comic.issue_title or '',
            publisher=comic.publisher or '',
            api_key=api_key,
            na_publishers_only=_na_publishers_only_from_request(),
            start_year=comic.release_date.year if comic.release_date else None,
        )
        if payload.get('error'):
            return jsonify(payload), 404

        # Use the exact issue matched during refresh so metadata and cover
        # variants always come from the same ComicVine record.
        metadata = payload.get('metadata') or {}
        issue_id = metadata.get('comicvine_id') or metadata.get('id') or comic.comicvine_issue_id
        if issue_id:
            try:
                payload['covers'] = fetch_comicvine_issue_covers(int(issue_id), api_key)
            except (requests.RequestException, TypeError, ValueError):
                # Metadata is still useful even when ComicVine's cover image
                # endpoint is unavailable.
                payload['covers'] = []

        if request.method == 'POST':
            _apply_comicvine_metadata(comic, metadata)
            sync_character_mentions(comic)
            db.session.commit()
            payload['success'] = True
            payload['applied'] = True
            payload['redirect_url'] = url_for('comics.show', id=comic.id)
            return jsonify(payload)

        return jsonify(payload)
    except requests.RequestException as exc:
        return jsonify({'error': f'ComicVine refresh failed: {exc}'}), 502
    except Exception as exc:
        current_app.logger.exception('ComicVine refresh failed: %s', exc)
        return jsonify({'error': f'ComicVine refresh failed: {exc}'}), 500

@comics_bp.route('/comics/volumes/lookup')
@login_required
def volumes_lookup():
    """List ComicVine and local catalog volumes for a series name (pick by year/volume)."""
    series = request.args.get('series', '').strip()
    year = request.args.get('year', type=int)
    publisher = request.args.get('publisher', '').strip()
    search_comicvine = request.args.get('comicvine', '1') == '1'
    search_local = request.args.get('local', '1') == '1'
    na_publishers_only = _na_publishers_only_from_request()

    if not series:
        return jsonify({'error': 'Enter a series name to browse volumes.'}), 400

    volumes = []
    if search_local:
        volumes.extend(search_local_series_volumes(series, publisher=publisher))

    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    if search_comicvine:
        if not api_key:
            if not volumes:
                return jsonify({
                    'error': 'ComicVine API key is not configured. Add COMICVINE_API_KEY to your .env file.',
                    'volumes': [],
                }), 503
        else:
            try:
                volumes.extend(search_comicvine_volumes(
                    series, api_key, year=year, publisher=publisher,
                    na_publishers_only=na_publishers_only,
                ))
            except requests.RequestException as exc:
                if not volumes:
                    return jsonify({'error': f'ComicVine volume lookup failed: {exc}', 'volumes': []}), 502

    if not volumes:
        return jsonify({'error': f'No volumes found for "{series}".', 'volumes': []}), 404

    def _sort_key(vol):
        year_val = vol.get('start_year') or ''
        year_num = int(year_val) if str(year_val).isdigit() else 9999
        return (year_num, vol.get('publisher', '').lower(), vol.get('display_name', '').lower())

    volumes.sort(key=_sort_key)
    return jsonify({'volumes': volumes, 'count': len(volumes)})


@comics_bp.route('/comics/search-api')
@login_required
def search_api():
    """Search for comics via ComicVine, barcode APIs, and the local Series Catalog."""
    query = request.args.get('q', '').strip()
    series_name = request.args.get('series_name', '').strip()
    issue_number = request.args.get('issue_number', '').strip()
    volume_id = request.args.get('volume_id', type=int)
    local_series_id = request.args.get('local_series_id', type=int)
    search_comicvine = request.args.get('comicvine', '1') == '1'
    search_local = request.args.get('local', '1') == '1'
    na_publishers_only = _na_publishers_only_from_request()

    if not any([query, series_name, issue_number, volume_id, local_series_id]):
        return jsonify({'error': 'Provide at least a query, series/issue, or selected volume'}), 400

    comicvine_key = current_app.config.get('COMICVINE_API_KEY', '')
    if search_comicvine and not comicvine_key:
        if not search_local:
            return jsonify({
                'error': 'ComicVine API key is not configured. Add COMICVINE_API_KEY to your .env file.',
                'results': [],
            }), 503
        search_comicvine = False

    try:
        started = time.perf_counter()
        results = run_comic_search(
            query=query,
            series_name=series_name,
            issue_number=issue_number,
            search_comicvine=search_comicvine,
            search_local=search_local,
            comicvine_api_key=comicvine_key,
            upc_api_key=current_app.config.get('UPC_DATABASE_API_KEY', ''),
            barcode_api_key=current_app.config.get('BARCODE_LOOKUP_API_KEY', ''),
            volume_id=volume_id,
            local_series_id=local_series_id,
            na_publishers_only=na_publishers_only,
        )
        payload = {'results': results}
        if current_app.debug:
            payload['elapsed_ms'] = round((time.perf_counter() - started) * 1000)
        return jsonify(payload)
    except requests.RequestException as exc:
        return jsonify({'error': f'Search failed: {exc}'}), 502
    except Exception as exc:
        return jsonify({'error': f'Search failed: {exc}'}), 500

@comics_bp.route('/comics/fetch-cover')
@login_required
def fetch_cover():
    """Fetch cover image from URL and return BLOB data."""
    image_url = request.args.get('url', '')
    if not image_url:
        return jsonify({'error': 'No image URL provided'}), 400
    
    try:
        image_data, content_type = fetch_public_image(image_url)
        
        # Convert to base64 for frontend transmission
        import base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        # Generate a unique identifier for the image
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_id = f"{timestamp}_api_cover"
        
        print(f"Fetched image: {image_id} ({len(image_data)} bytes, {content_type})")
        
        return jsonify({
            'image_id': image_id,
            'blob_data': base64_data,
            'mime_type': content_type,
            'size': len(image_data)
        })
        
    except UnsafeRemoteUrl as e:
        return jsonify({'error': str(e)}), 400
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to fetch image: {str(e)}'}), 502
    except Exception as e:
        return jsonify({'error': f'Failed to process image: {str(e)}'}), 500

@comics_bp.route('/comics/ai-value-lookup', methods=['POST'])
@login_required
def ai_value_lookup():
    """Estimate a comic's value from live marketplace comparables."""
    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        series = (data.get('series') or '').strip()
        title = (data.get('title') or '').strip()
        issue_number = (data.get('issue_number') or '').strip()
        publisher = (data.get('publisher') or '').strip()
        condition = (data.get('condition') or '').strip()

        if not any([series, title, issue_number]):
            return jsonify({'success': False, 'error': 'At least series, title, or issue number is required'}), 400

        estimate = estimate_market_value(
            series=series,
            issue_number=issue_number,
            publisher=publisher,
            condition=condition,
            title=title,
        )

        return jsonify({
            'success': True,
            # Kept for older callers that only read a single number.
            'estimated_value': estimate['value'],
            'confidence_level': estimate['confidence'].title(),
            'search_query': estimate['query'],
            'estimate': estimate,
        })

    except Exception as exc:
        current_app.logger.exception('Value lookup failed: %s', exc)
        return jsonify({
            'success': False,
            'error': 'An error occurred while estimating the value'
        }), 500


@comics_bp.route('/comics/autocomplete')
@login_required
def autocomplete():
    """Suggest titles, series, writers, and artists from the current user's collection."""
    query = (request.args.get('q') or '').strip()
    if len(query) < 3:
        return jsonify({'suggestions': []})

    ilike = f'%{query}%'
    rows = Comic.query.filter(
        Comic.user_id == current_user.id,
        or_(
            Comic.title.ilike(ilike),
            Comic.series.ilike(ilike),
            Comic.writer.ilike(ilike),
            Comic.artist.ilike(ilike),
        ),
    ).order_by(Comic.series.asc(), Comic.issue_number.asc()).limit(40).all()

    seen = set()
    suggestions = []
    for comic in rows:
        candidates = [
            ('series', comic.series),
            ('title', comic.title),
            ('writer', comic.writer),
            ('artist', comic.artist),
        ]
        for kind, value in candidates:
            text = (value or '').strip()
            if not text or query.lower() not in text.lower():
                continue
            # For multi-value credit fields, split on commas.
            parts = [text] if kind in ('series', 'title') else [
                part.strip() for part in text.split(',') if part.strip()
            ]
            for part in parts:
                if query.lower() not in part.lower():
                    continue
                key = (kind, part.lower())
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append({'label': part, 'type': kind})
                if len(suggestions) >= 12:
                    return jsonify({'suggestions': suggestions})
    return jsonify({'suggestions': suggestions})

