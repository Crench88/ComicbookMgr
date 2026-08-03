"""Shared helpers and constants for the comics blueprint."""

import os
import re
from io import BytesIO

from flask import (
    current_app,
    flash,
    make_response,
    request,
    url_for,
)
from PIL import Image, ImageOps
from sqlalchemy import Float, case, cast, func
from sqlalchemy.orm import defer, with_expression
from werkzeug.utils import secure_filename

from .. import db
from ..models import Comic, ComicCover
from ..services.cache import cache_get, cache_set


SERIES_PER_PAGE = 50
COMICS_PER_PAGE = 36

ALLOWED_COVER_FORMATS = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'GIF': 'image/gif',
    'WEBP': 'image/webp',
}


def _validated_cover_image(blob_data):
    """Validate image bytes and return a canonical MIME type."""
    if not blob_data:
        raise ValueError('The cover image is empty.')
    try:
        with Image.open(BytesIO(blob_data)) as image:
            image.verify()
            mime_type = ALLOWED_COVER_FORMATS.get((image.format or '').upper())
    except (Image.UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError('The cover data is not a valid supported image.') from exc
    if not mime_type:
        raise ValueError('Only JPEG, PNG, GIF, and WebP covers are supported.')
    return mime_type


def _validated_additional_covers(covers):
    """Validate Base64 alternate covers and normalize their MIME types."""
    import base64
    import binascii

    validated = []
    for index, cover in enumerate(covers or [], start=1):
        if not isinstance(cover, dict):
            raise ValueError(f'Cover {index} is invalid.')
        try:
            blob_data = base64.b64decode(cover.get('blob_data', ''), validate=True)
            mime_type = _validated_cover_image(blob_data)
        except (ValueError, TypeError, binascii.Error) as exc:
            raise ValueError(f'Cover {index} is not a valid image.') from exc
        validated.append({
            'blob_data': base64.b64encode(blob_data).decode('ascii'),
            'mime_type': mime_type,
            'label': str(cover.get('label') or f'Cover {index}')[:200],
        })
    return validated


def _parse_comicvine_issue_id(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_form_cover_updates(comic, form):
    """Apply cover changes; return False when validation fails."""
    import base64
    import binascii
    import json

    fetched_cover_blob = request.form.get('fetched_cover_blob')
    fetched_cover_mime = request.form.get('fetched_cover_mime')
    additional_covers = request.form.get('additional_covers')
    covers_updated = request.form.get('covers_updated') == '1'

    from ..services.cover_storage import (
        get_primary_cover_bytes,
        persist_primary_cover,
        persist_variant_cover,
    )

    if fetched_cover_blob:
        try:
            blob_data = base64.b64decode(fetched_cover_blob, validate=True)
            fetched_cover_mime = _validated_cover_image(blob_data)
            if comic.id is None:
                db.session.add(comic)
            persist_primary_cover(comic, blob_data, fetched_cover_mime)
        except (ValueError, TypeError, binascii.Error) as exc:
            current_app.logger.warning('Rejected invalid cover form data: %s', exc)
            flash(str(exc) or 'Error processing cover image.', 'danger')
            return False

        try:
            if covers_updated:
                if additional_covers and additional_covers.strip():
                    comic.set_additional_covers(
                        _validated_additional_covers(json.loads(additional_covers))
                    )
                else:
                    comic.set_additional_covers([])
            elif additional_covers:
                comic.set_additional_covers(
                    _validated_additional_covers(json.loads(additional_covers))
                )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            current_app.logger.warning('Rejected invalid alternate cover data: %s', exc)
            flash('One or more alternate covers were invalid. Nothing was saved.', 'danger')
            return False
    elif form.cover_image.data and hasattr(form.cover_image.data, 'filename'):
        image_data = save_cover_image(form.cover_image.data)
        if not image_data:
            flash('The uploaded cover is not a valid supported image.', 'danger')
            return False
        previous = get_primary_cover_bytes(comic)
        if previous:
            next_position = max(
                (cover.position for cover in comic.cover_variants),
                default=0,
            ) + 1
            demoted = ComicCover(
                image_data=previous,
                mime_type=comic.cover_image_mime or 'image/jpeg',
                label='Previous Primary Cover',
                position=next_position,
            )
            comic.cover_variants.append(demoted)
            if comic.id is not None:
                persist_variant_cover(
                    demoted,
                    previous,
                    demoted.mime_type,
                    user_id=comic.user_id,
                    comic_id=comic.id,
                )
        if comic.id is None:
            db.session.add(comic)
        persist_primary_cover(comic, image_data['blob_data'], image_data['mime_type'])
    return True


def _na_publishers_only_from_request() -> bool:
    """Default True: limit ComicVine results to major North American publishers."""
    val = request.args.get('na_publishers_only', '1').strip().lower()
    return val not in ('0', 'false', 'no', 'off')

def _safe_redirect_target(target: str) -> str | None:
    """Return a same-origin relative redirect path, or None if unsafe."""
    if not target:
        return None
    from urllib.parse import urlparse, urljoin
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    if test_url.scheme not in ('', 'http', 'https'):
        return None
    if test_url.netloc and test_url.netloc != ref_url.netloc:
        return None
    if not test_url.path.startswith('/'):
        return None
    if '..' in test_url.path:
        return None
    return test_url.path + (f'?{test_url.query}' if test_url.query else '')


def _collection_return_url(comic, target: str = '') -> str:
    """Return a safe collection URL scoped to the comic's actual series."""
    from urllib.parse import parse_qsl, urlencode, urlparse

    series_name = comic.series_label
    safe_target = _safe_redirect_target(target)
    if not safe_target:
        return url_for('comics.index', series=series_name)

    parsed = urlparse(safe_target)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query['series'] = series_name
    # A prior series can have a different number of issue pages.
    query['comic_page'] = '1'
    # Drop a stale series sidebar page so index can open the page that
    # actually contains this comic's series.
    query.pop('series_page', None)
    return parsed.path + '?' + urlencode(query)


def _series_page_for_name(user_id, series_name, filter_kwargs):
    """Return the 1-based series sidebar page that contains series_name."""
    series_names = [
        row.series_name
        for row in _filter_series_query(user_id, **filter_kwargs).all()
    ]
    try:
        index = series_names.index(series_name)
    except ValueError:
        return 1
    return (index // SERIES_PER_PAGE) + 1


def _apply_comic_filters(query, search_query='', publisher_filter='',
                         condition_filter='', genre_filter='', wishlist_only=False,
                         tag_filter='', read_status_filter=''):
    """Apply shared search/filter criteria to a Comic query."""
    from ..models import Tag

    if search_query:
        ilike = f'%{search_query}%'
        query = query.filter(
            db.or_(
                Comic.title.ilike(ilike),
                Comic.series.ilike(ilike),
                Comic.issue_title.ilike(ilike),
                Comic.issue_number.ilike(ilike),
                Comic.characters.ilike(ilike),
                Comic.writer.ilike(ilike),
                Comic.artist.ilike(ilike),
                Comic.story_arc.ilike(ilike),
                Comic.description.ilike(ilike),
                Comic.publisher.ilike(ilike),
                Comic.upc.ilike(ilike),
            )
        )

    if publisher_filter:
        query = query.filter(Comic.publisher == publisher_filter)

    if condition_filter:
        query = query.filter(Comic.condition == condition_filter)

    if genre_filter:
        query = query.filter(Comic.genre.ilike(f'%{genre_filter}%'))

    if wishlist_only:
        query = query.filter(Comic.is_wishlist == True)

    if read_status_filter:
        query = query.filter(Comic.read_status == read_status_filter)

    if tag_filter:
        query = query.join(Comic.tags).filter(Tag.name == tag_filter).distinct()

    return query


def _series_label(comic_series):
    """Normalize series name for grouping and display."""
    if comic_series and str(comic_series).strip():
        return str(comic_series).strip()
    return 'Unknown Series'


def _issue_sort_key(comic):
    """Sort comics within a series by issue number (numeric first, then suffix)."""
    issue = (comic.issue_number or '').strip()
    if not issue:
        return (float('inf'), '', comic.title.lower())

    match = re.match(r'(\d+(?:\.\d+)?)\s*(.*)', issue)
    if match:
        numeric_part = float(match.group(1))
        suffix = (match.group(2) or '').strip().lower()
        return (numeric_part, suffix, comic.title.lower())

    return (float('inf'), issue.lower(), comic.title.lower())


def _annotate_duplicates(comics_list):
    """Attach duplicate_index / duplicate_total for copies of the same issue."""
    issue_counts = {}
    for comic in comics_list:
        key = (comic.issue_number, comic.title or '')
        issue_counts[key] = issue_counts.get(key, 0) + 1

    issue_occurrence = {}
    for comic in comics_list:
        key = (comic.issue_number, comic.title or '')
        total = issue_counts.get(key, 1)
        if total > 1:
            issue_occurrence[key] = issue_occurrence.get(key, 0) + 1
            comic.duplicate_index = issue_occurrence[key]
            comic.duplicate_total = total
        else:
            comic.duplicate_index = None
            comic.duplicate_total = 1


def _filter_series_query(user_id, search_query='', publisher_filter='',
                         condition_filter='', genre_filter='', wishlist_only=False,
                         tag_filter='', read_status_filter=''):
    """Return a query of (series_name, issue_count) rows for the filtered collection."""
    series_name = func.coalesce(
        func.nullif(func.trim(Comic.series), ''),
        'Unknown Series',
    ).label('series_name')

    query = db.session.query(
        series_name,
        func.count(Comic.id).label('issue_count'),
    ).filter(Comic.user_id == user_id)

    query = _apply_comic_filters(
        query, search_query, publisher_filter,
        condition_filter, genre_filter, wishlist_only,
        tag_filter, read_status_filter,
    )

    return query.group_by(series_name).order_by(series_name.asc())


def _comics_for_series_query(user_id, series_name, search_query='', publisher_filter='',
                             condition_filter='', genre_filter='', wishlist_only=False,
                             tag_filter='', read_status_filter='',
                             sort_by='issue_number'):
    """Return a Comic query scoped to one series with filters applied."""
    query = Comic.query.options(
        defer(Comic.cover_image),
        defer(Comic.additional_covers),
        with_expression(
            Comic.cover_available,
            db.or_(Comic.cover_image_path.isnot(None), Comic.cover_image.isnot(None)),
        ),
    ).filter_by(user_id=user_id)
    query = _apply_comic_filters(
        query, search_query, publisher_filter,
        condition_filter, genre_filter, wishlist_only,
        tag_filter, read_status_filter,
    )

    if series_name == 'Unknown Series':
        query = query.filter(db.or_(Comic.series.is_(None), func.trim(Comic.series) == ''))
    else:
        query = query.filter(func.trim(Comic.series) == series_name)

    issue_numeric = case(
        (Comic.issue_number.op('GLOB')('[0-9]*'), cast(Comic.issue_number, Float)),
        else_=999999999,
    )
    issue_order = (issue_numeric.asc(), func.lower(Comic.issue_number).asc())
    order_map = {
        'issue_number': (*issue_order, func.lower(Comic.title).asc()),
        'title': (func.lower(Comic.title).asc(), *issue_order),
        'publisher': (func.lower(Comic.publisher).asc(), *issue_order),
        'condition': (func.lower(Comic.condition).asc(), *issue_order),
        'estimated_value': (Comic.estimated_value.desc(), *issue_order),
        'date_added': (Comic.created_at.desc(), *issue_order),
    }
    return query.order_by(*order_map.get(sort_by, order_map['issue_number']))


def _serialize_comic_for_grid(comic):
    """JSON-friendly comic payload for the collection grid."""
    return {
        'id': comic.id,
        'title': comic.title,
        'issue_number': comic.issue_number,
        'publisher': comic.publisher or 'Unknown',
        'condition': comic.condition,
        'estimated_value': comic.get_formatted_value() if comic.estimated_value else None,
        'is_wishlist': comic.is_wishlist,
        'in_collection': bool(comic.in_collection),
        'is_digital': bool(comic.is_digital),
        'digital_active': comic.digital_active,
        'ownership_tags': comic.ownership_status_tags(),
        'has_cover': comic.has_cover_image(),
        'cover_url': url_for('comics.serve_cover_thumbnail', id=comic.id, v=comic.cover_version()),
        'show_url': url_for('comics.show', id=comic.id),
        'edit_url': url_for('comics.edit', id=comic.id),
        'duplicate_index': getattr(comic, 'duplicate_index', None),
        'duplicate_total': getattr(comic, 'duplicate_total', 1),
        'release_date': comic.release_date.strftime('%Y-%m-%d') if comic.release_date else None,
    }

def save_cover_image(file):
    """Save uploaded cover image and return BLOB data and MIME type."""
    # Handle case where file is already a filename string (from edit form)
    if isinstance(file, str):
        # This is a legacy case - try to read the file and convert to BLOB
        filepath = os.path.join(
            current_app.config['UPLOAD_FOLDER'],
            secure_filename(os.path.basename(file)),
        )
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    blob_data = f.read()
                mime_type = _validated_cover_image(blob_data)
                return {'blob_data': blob_data, 'mime_type': mime_type}
            except Exception as e:
                print(f"Error reading file {file}: {e}")
                return None
        return None
    
    # Handle case where file is a file object
    if file and hasattr(file, 'filename') and file.filename:
        try:
            # Read the file data
            file.seek(0)  # Reset file pointer
            blob_data = file.read()
            mime_type = _validated_cover_image(blob_data)
            
            print(f"File converted to BLOB: {file.filename} ({len(blob_data)} bytes)")
            return {'blob_data': blob_data, 'mime_type': mime_type}
            
        except Exception as e:
            print(f"Error converting file to BLOB: {e}")
            return None
    
    return None

def _cover_blob_response(image_data, mime_type):
    """Return an image response with private conditional caching."""
    import hashlib

    from ..services.cover_storage import apply_cover_cache_headers

    response = make_response(BytesIO(image_data).read())
    response.headers.set('Content-Type', mime_type or 'image/jpeg')
    response.headers.set('Content-Disposition', 'inline')
    response.headers.set('X-Content-Type-Options', 'nosniff')
    apply_cover_cache_headers(response)
    response.set_etag(hashlib.sha256(image_data).hexdigest())
    return response.make_conditional(request)


def _cover_thumbnail_response(image_data):
    """Return a cached, bandwidth-friendly JPEG cover thumbnail."""
    import hashlib

    digest = hashlib.sha256(image_data).hexdigest()
    cache_key = f'cover-thumb:{digest}:360x480:v1'
    thumbnail = cache_get(cache_key)

    if thumbnail is None:
        with Image.open(BytesIO(image_data)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((360, 480), Image.Resampling.LANCZOS)
            if image.mode not in ('RGB', 'L'):
                background = Image.new('RGB', image.size, 'white')
                if 'A' in image.getbands():
                    background.paste(image, mask=image.getchannel('A'))
                else:
                    background.paste(image)
                image = background
            elif image.mode == 'L':
                image = image.convert('RGB')

            output = BytesIO()
            image.save(output, format='JPEG', quality=82, optimize=True)
            thumbnail = output.getvalue()
        cache_set(cache_key, thumbnail, ttl=7 * 24 * 60 * 60)

    return _cover_blob_response(thumbnail, 'image/jpeg')
