"""
Comics blueprint for Comic Book Collection Manager.
Handles comic book CRUD operations, search, and filtering.
"""

import os
import re
import requests
import time
from datetime import datetime
from io import BytesIO
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, jsonify, current_app, make_response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
from sqlalchemy import func
from . import db
from .models import Comic, ComicCover, Series, SeriesIssue
from .forms import ComicForm
from .services.bulk_add import bulk_add_single_issue, parse_issue_ranges
from .services.comicvine import (
    fetch_comicvine_issue_covers,
    lookup_covers_for_form,
    search_comicvine_volumes,
)
from .services.local_catalog import search_local_series_volumes
from .services.search_orchestrator import run_comic_search

comics_bp = Blueprint('comics', __name__)

SERIES_PER_PAGE = 50
COMICS_PER_PAGE = 36


def _parse_comicvine_issue_id(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_form_cover_updates(comic, form):
    """Apply cover image changes from the comic form POST data."""
    import base64
    import json

    fetched_cover_blob = request.form.get('fetched_cover_blob')
    fetched_cover_mime = request.form.get('fetched_cover_mime')
    additional_covers = request.form.get('additional_covers')
    covers_updated = request.form.get('covers_updated') == '1'

    if fetched_cover_blob:
        try:
            blob_data = base64.b64decode(fetched_cover_blob)
            comic.cover_image = blob_data
            comic.cover_image_mime = fetched_cover_mime or 'image/jpeg'
        except Exception as e:
            print(f"Error decoding BLOB data: {e}")
            flash('Error processing cover image. Please try again.', 'danger')
            return

        if covers_updated:
            if additional_covers and additional_covers.strip():
                try:
                    comic.set_additional_covers(json.loads(additional_covers))
                except (json.JSONDecodeError, TypeError):
                    pass
            else:
                comic.set_additional_covers([])
        elif additional_covers:
            try:
                comic.set_additional_covers(json.loads(additional_covers))
            except (json.JSONDecodeError, TypeError):
                pass
    elif form.cover_image.data and hasattr(form.cover_image.data, 'filename'):
        image_data = save_cover_image(form.cover_image.data)
        if image_data:
            comic.cover_image = image_data['blob_data']
            comic.cover_image_mime = image_data['mime_type']


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

    safe_target = _safe_redirect_target(target)
    if not safe_target:
        return url_for('comics.index', series=(comic.series or 'Unknown Series'))

    parsed = urlparse(safe_target)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query['series'] = comic.series or 'Unknown Series'
    # A prior series can have a different number of issue pages.
    query['comic_page'] = '1'
    return parsed.path + '?' + urlencode(query)


def _apply_comic_filters(query, search_query='', publisher_filter='',
                         condition_filter='', genre_filter='', wishlist_only=False):
    """Apply shared search/filter criteria to a Comic query."""
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
                Comic.isbn.ilike(ilike),
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
                         condition_filter='', genre_filter='', wishlist_only=False):
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
    )

    return query.group_by(series_name).order_by(series_name.asc())


def _comics_for_series_query(user_id, series_name, search_query='', publisher_filter='',
                             condition_filter='', genre_filter='', wishlist_only=False):
    """Return a Comic query scoped to one series with filters applied."""
    query = Comic.query.filter_by(user_id=user_id)
    query = _apply_comic_filters(
        query, search_query, publisher_filter,
        condition_filter, genre_filter, wishlist_only,
    )

    if series_name == 'Unknown Series':
        query = query.filter(db.or_(Comic.series.is_(None), func.trim(Comic.series) == ''))
    else:
        query = query.filter(Comic.series == series_name)

    return query


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
        'has_cover': comic.has_cover_image(),
        'cover_url': url_for('comics.serve_cover_image', id=comic.id),
        'show_url': url_for('comics.show', id=comic.id),
        'edit_url': url_for('comics.edit', id=comic.id),
        'duplicate_index': getattr(comic, 'duplicate_index', None),
        'duplicate_total': getattr(comic, 'duplicate_total', 1),
        'release_date': comic.release_date.strftime('%Y-%m-%d') if comic.release_date else None,
    }


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


@comics_bp.route('/comics/<int:id>/comicvine/refresh')
@login_required
def refresh_comicvine_metadata(id):
    """Re-fetch ComicVine metadata for an existing comic (edit form refresh)."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    if not api_key:
        return jsonify({
            'error': 'ComicVine API key is not configured. Add COMICVINE_API_KEY to your .env file.',
        }), 503

    try:
        from .services.comicvine import lookup_issue_metadata_for_refresh
        payload = lookup_issue_metadata_for_refresh(
            comicvine_issue_id=comic.comicvine_issue_id,
            series=comic.series or '',
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
        return jsonify(payload)
    except requests.RequestException as exc:
        return jsonify({'error': f'ComicVine refresh failed: {exc}'}), 502
    except Exception as exc:
        return jsonify({'error': f'ComicVine refresh failed: {exc}'}), 500


def save_cover_image(file):
    """Save uploaded cover image and return BLOB data and MIME type."""
    # Handle case where file is already a filename string (from edit form)
    if isinstance(file, str):
        # This is a legacy case - try to read the file and convert to BLOB
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], file)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    blob_data = f.read()
                
                # Determine MIME type based on file extension
                ext = os.path.splitext(file)[1].lower()
                mime_types = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp'
                }
                mime_type = mime_types.get(ext, 'image/jpeg')
                
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
            
            # Determine MIME type based on file extension
            ext = os.path.splitext(file.filename)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            print(f"File converted to BLOB: {file.filename} ({len(blob_data)} bytes)")
            return {'blob_data': blob_data, 'mime_type': mime_type}
            
        except Exception as e:
            print(f"Error converting file to BLOB: {e}")
            return None
    
    return None

@comics_bp.route('/comics')
@login_required
def index():
    """Display collection as a master-detail series browser."""
    search_query = request.args.get('search', '')
    publisher_filter = request.args.get('publisher', '')
    condition_filter = request.args.get('condition', '')
    genre_filter = request.args.get('genre', '')
    wishlist_only = request.args.get('wishlist', False, type=bool)
    sort_by = request.args.get('sort', 'title')
    series_page = request.args.get('series_page', 1, type=int)
    comic_page = request.args.get('comic_page', 1, type=int)
    selected_series = request.args.get('series', '')

    filter_kwargs = dict(
        search_query=search_query,
        publisher_filter=publisher_filter,
        condition_filter=condition_filter,
        genre_filter=genre_filter,
        wishlist_only=wishlist_only,
    )

    publishers = db.session.query(Comic.publisher).filter_by(
        user_id=current_user.id
    ).distinct().all()
    publishers = [pub[0] for pub in publishers if pub[0]]

    series_pagination = _filter_series_query(
        current_user.id, **filter_kwargs,
    ).paginate(page=series_page, per_page=SERIES_PER_PAGE, error_out=False)

    series_rows = [
        {'name': row.series_name, 'count': row.issue_count}
        for row in series_pagination.items
    ]

    total_comics = db.session.query(func.count(Comic.id)).filter(
        Comic.user_id == current_user.id,
    )
    total_comics = _apply_comic_filters(total_comics, **filter_kwargs).scalar() or 0

    selected_comics = None
    comics_pagination = None
    selected_series_name = None
    selected_series_count = 0

    if series_rows:
        series_names = [row['name'] for row in series_rows]
        if selected_series not in series_names:
            count_row = _filter_series_query(
                current_user.id, **filter_kwargs,
            ).filter(
                func.coalesce(
                    func.nullif(func.trim(Comic.series), ''),
                    'Unknown Series',
                ) == selected_series
            ).first()
            if not count_row:
                selected_series = series_names[0]

        selected_series_name = selected_series
        selected_series_count = next(
            (row['count'] for row in series_rows if row['name'] == selected_series_name),
            0,
        )
        if selected_series_count == 0:
            count_row = _filter_series_query(
                current_user.id, **filter_kwargs,
            ).filter(
                func.coalesce(
                    func.nullif(func.trim(Comic.series), ''),
                    'Unknown Series',
                ) == selected_series_name
            ).first()
            selected_series_count = count_row.issue_count if count_row else 0

        comics_query = _comics_for_series_query(
            current_user.id, selected_series_name, **filter_kwargs,
        )
        all_in_series = comics_query.all()
        all_in_series.sort(key=_issue_sort_key)
        _annotate_duplicates(all_in_series)

        total_in_series = len(all_in_series)
        start = (comic_page - 1) * COMICS_PER_PAGE
        end = start + COMICS_PER_PAGE
        page_comics = all_in_series[start:end]

        class SeriesComicPagination:
            def __init__(self, items, total, page, per_page):
                self.items = items
                self.total = total
                self.page = page
                self.per_page = per_page
                self.pages = max(1, (total + per_page - 1) // per_page)
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None

            def iter_pages(self, left_edge=1, right_edge=1, left_current=2, right_current=2):
                last = self.pages
                for num in range(1, last + 1):
                    if (
                        num <= left_edge
                        or num > last - right_edge
                        or abs(num - self.page) <= left_current
                        or abs(num - self.page) <= right_current
                    ):
                        yield num

        comics_pagination = SeriesComicPagination(
            page_comics, total_in_series, comic_page, COMICS_PER_PAGE,
        )
        selected_comics = page_comics

    class TotalComics:
        def __init__(self, total):
            self.total = total

    return render_template(
        'comics/index.html',
        title='My Comics',
        comics=TotalComics(total_comics),
        series_rows=series_rows,
        series_pagination=series_pagination,
        selected_series=selected_series_name,
        selected_series_count=selected_series_count,
        selected_comics=selected_comics,
        comics_pagination=comics_pagination,
        search_query=search_query,
        publisher_filter=publisher_filter,
        condition_filter=condition_filter,
        genre_filter=genre_filter,
        wishlist_only=wishlist_only,
        sort_by=sort_by,
        publishers=publishers,
        comics_per_page=COMICS_PER_PAGE,
    )


@comics_bp.route('/comics/series-issues')
@login_required
def series_issues():
    """JSON endpoint for comics in a selected series (AJAX grid refresh)."""
    series_name = request.args.get('series', '').strip()
    if not series_name:
        return jsonify({'error': 'Series name required'}), 400

    search_query = request.args.get('search', '')
    publisher_filter = request.args.get('publisher', '')
    condition_filter = request.args.get('condition', '')
    genre_filter = request.args.get('genre', '')
    wishlist_only = request.args.get('wishlist', False, type=bool)
    comic_page = request.args.get('comic_page', 1, type=int)

    filter_kwargs = dict(
        search_query=search_query,
        publisher_filter=publisher_filter,
        condition_filter=condition_filter,
        genre_filter=genre_filter,
        wishlist_only=wishlist_only,
    )

    comics_query = _comics_for_series_query(
        current_user.id, series_name, **filter_kwargs,
    )
    all_in_series = comics_query.all()
    all_in_series.sort(key=_issue_sort_key)
    _annotate_duplicates(all_in_series)

    total = len(all_in_series)
    start = (comic_page - 1) * COMICS_PER_PAGE
    end = start + COMICS_PER_PAGE
    page_comics = all_in_series[start:end]
    pages = max(1, (total + COMICS_PER_PAGE - 1) // COMICS_PER_PAGE)

    return jsonify({
        'series': series_name,
        'comics': [_serialize_comic_for_grid(c) for c in page_comics],
        'pagination': {
            'page': comic_page,
            'pages': pages,
            'total': total,
            'per_page': COMICS_PER_PAGE,
            'has_prev': comic_page > 1,
            'has_next': comic_page < pages,
            'prev_num': comic_page - 1 if comic_page > 1 else None,
            'next_num': comic_page + 1 if comic_page < pages else None,
        },
    })

@comics_bp.route('/comics/new', methods=['GET', 'POST'])
@login_required
def new():
    """Add a new comic to the collection."""
    form = ComicForm()
    series_options = Series.query.order_by(Series.name.asc(), Series.volume.asc()).all()
    
    if form.validate_on_submit():
        comic = Comic(
            title=form.title.data,  # Individual issue title (e.g., "Worldwide")
            series=form.series.data,  # Series name (e.g., "The Amazing Spider-Man")
            issue_title=form.title.data,  # Use title field for issue_title
            issue_number=form.issue_number.data,
            publisher=form.publisher.data,
            characters=form.characters.data,
            writer=form.writer.data,
            artist=form.artist.data,
            colorist=form.colorist.data,
            letterer=form.letterer.data,
            editor=form.editor.data,
            cover_artist=form.cover_artist.data,
            teams=form.teams.data,
            story_arc=form.story_arc.data,
            description=form.description.data,
            comicvine_issue_id=_parse_comicvine_issue_id(form.comicvine_issue_id.data),
            comicvine_url=(request.form.get('comicvine_url') or '').strip() or None,
            genre=form.genre.data,
            release_date=form.release_date.data,
            upc=form.upc.data,
            isbn=form.isbn.data,
            condition=form.condition.data,
            estimated_value=form.estimated_value.data or 0.0,
            notes=form.notes.data,
            is_wishlist=form.is_wishlist.data,
            user_id=current_user.id
        )
        
        _apply_form_cover_updates(comic, form)
        
        try:
            db.session.add(comic)
            db.session.commit()
            flash('Comic added successfully!', 'success')
            return redirect(url_for('comics.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding comic. Please try again.', 'danger')
    
    return render_template('comics/form.html', title='Add Comic', form=form, series_options=series_options, comic=None)

@comics_bp.route('/comics/<int:id>')
@login_required
def show(id):
    """Display a specific comic."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    collection_return_url = _collection_return_url(comic, request.args.get('next', ''))
    return render_template(
        'comics/show.html',
        title=comic.title,
        comic=comic,
        collection_return_url=collection_return_url,
    )

@comics_bp.route('/comics/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit an existing comic."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    collection_return_url = _collection_return_url(comic, request.args.get('next', ''))
    form = ComicForm(obj=comic)
    series_options = Series.query.order_by(Series.name.asc(), Series.volume.asc()).all()
    
    if form.validate_on_submit():
        comic.title = form.title.data  # Individual issue title (e.g., "Worldwide")
        comic.series = form.series.data  # Series name (e.g., "The Amazing Spider-Man")
        comic.issue_title = form.title.data  # Use title field for issue_title
        comic.issue_number = form.issue_number.data
        comic.publisher = form.publisher.data
        comic.characters = form.characters.data
        comic.writer = form.writer.data
        comic.artist = form.artist.data
        comic.colorist = form.colorist.data
        comic.letterer = form.letterer.data
        comic.editor = form.editor.data
        comic.cover_artist = form.cover_artist.data
        comic.teams = form.teams.data
        comic.story_arc = form.story_arc.data
        comic.description = form.description.data
        comic.comicvine_issue_id = _parse_comicvine_issue_id(form.comicvine_issue_id.data)
        if request.form.get('comicvine_url'):
            comic.comicvine_url = request.form.get('comicvine_url').strip() or None
        comic.genre = form.genre.data
        comic.release_date = form.release_date.data
        comic.upc = form.upc.data
        comic.isbn = form.isbn.data
        comic.condition = form.condition.data
        comic.estimated_value = form.estimated_value.data or 0.0
        comic.notes = form.notes.data
        comic.is_wishlist = form.is_wishlist.data
        
        _apply_form_cover_updates(comic, form)
        
        try:
            db.session.commit()
            flash('Comic updated successfully!', 'success')
            return redirect(url_for('comics.show', id=comic.id, next=collection_return_url))
        except Exception as e:
            db.session.rollback()
            flash('Error updating comic. Please try again.', 'danger')
    
    return render_template(
        'comics/form.html',
        title='Edit Comic',
        form=form,
        comic=comic,
        series_options=series_options,
        collection_return_url=collection_return_url,
    )


@comics_bp.route('/comics/<int:id>/covers', methods=['POST'])
@login_required
def save_cover_variant(id):
    """Store one cover variant at a time to avoid a large combined form POST."""
    import base64
    import binascii

    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    cover = payload.get('cover')

    if not isinstance(cover, dict) or not cover.get('blob_data'):
        return jsonify({'error': 'A cover image is required.'}), 400

    try:
        blob_data = base64.b64decode(cover['blob_data'], validate=True)
    except (ValueError, TypeError, binascii.Error):
        return jsonify({'error': 'The cover image data is invalid.'}), 400

    if not blob_data:
        return jsonify({'error': 'The cover image is empty.'}), 400

    mime_type = str(cover.get('mime_type') or 'image/jpeg')[:100]
    label = str(cover.get('label') or 'Cover')[:200]

    if payload.get('replace'):
        comic.cover_image = blob_data
        comic.cover_image_mime = mime_type
        comic.cover_variants.clear()
    else:
        try:
            position = int(payload.get('position'))
        except (TypeError, ValueError):
            return jsonify({'error': 'A cover position is required.'}), 400
        if position < 1:
            return jsonify({'error': 'The cover position is invalid.'}), 400

        variant = ComicCover.query.filter_by(comic_id=comic.id, position=position).first()
        if variant is None:
            variant = ComicCover(comic_id=comic.id, position=position)
            db.session.add(variant)
        variant.image_data = blob_data
        variant.mime_type = mime_type
        variant.label = label

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Could not save this cover image.'}), 500

    return jsonify({'success': True})


@comics_bp.route('/comics/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete a comic from the collection."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        # Since we're using BLOB storage, we don't need to delete files
        # The BLOB data will be automatically cleaned up when the record is deleted
        
        db.session.delete(comic)
        db.session.commit()
        flash('Comic deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting comic {id}: {e}")
        flash('Error deleting comic. Please try again.', 'danger')
    
    next_url = _safe_redirect_target(request.form.get('next'))
    return redirect(next_url or url_for('comics.index'))

@comics_bp.route('/comics/<int:id>/cover')
@login_required
def serve_cover_image(id):
    """Serve cover image from BLOB data."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    if not comic.cover_image:
        return jsonify({'error': 'No cover image found'}), 404

    response = make_response(BytesIO(comic.cover_image).read())
    response.headers.set('Content-Type', comic.cover_image_mime or 'image/jpeg')
    response.headers.set('Content-Disposition', 'inline')
    return response

@comics_bp.route('/comics/export')
@login_required
def export():
    """Export collection to CSV."""
    import csv
    from io import StringIO
    
    comics = Comic.query.filter_by(user_id=current_user.id, is_wishlist=False).all()
    
    si = StringIO()
    cw = csv.writer(si)
    
    # Write header
    cw.writerow(['Title', 'Issue Number', 'Publisher', 'Writer', 'Artist', 'Characters',
                 'Story Arc', 'Genre', 'Release Date', 'Condition', 'Estimated Value',
                 'Description', 'Notes'])
    
    # Write data
    for comic in comics:
        cw.writerow([
            comic.title,
            comic.issue_number,
            comic.publisher,
            comic.writer or '',
            comic.artist or '',
            comic.characters or '',
            comic.story_arc or '',
            comic.genre or '',
            comic.release_date.strftime('%Y-%m-%d') if comic.release_date else '',
            comic.condition or '',
            comic.estimated_value or 0.0,
            comic.description or '',
            comic.notes or ''
        ])
    
    output = si.getvalue()
    si.close()
    
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'comic_collection_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@comics_bp.route('/comics/wishlist')
@login_required
def wishlist():
    """Display wishlist items."""
    page = request.args.get('page', 1, type=int)
    wishlist_comics = Comic.query.filter_by(
        user_id=current_user.id, is_wishlist=True
    ).order_by(Comic.title, Comic.issue_number).paginate(
        page=page, per_page=12, error_out=False
    )
    
    return render_template('comics/wishlist.html',
                         title='Wishlist',
                         comics=wishlist_comics)

@comics_bp.route('/comics/bulk-add/parse', methods=['POST'])
@login_required
def bulk_add_parse():
    """Parse an issue-range string and return the expanded issue list."""
    data = request.get_json(silent=True) or {}
    ranges_text = (data.get('issue_ranges') or '').strip()
    if not ranges_text:
        return jsonify({'error': 'Enter issue ranges (e.g. 1-32 or 1-14, 16-22).'}), 400
    try:
        issues = parse_issue_ranges(ranges_text)
        return jsonify({'issues': issues, 'count': len(issues)})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


@comics_bp.route('/comics/bulk-add/issue', methods=['POST'])
@login_required
def bulk_add_issue():
    """Look up and add a single issue (used by bulk-add UI for progress feedback)."""
    data = request.get_json(silent=True) or {}
    series = (data.get('series') or '').strip()
    issue_number = (data.get('issue_number') or '').strip()
    start_year = data.get('start_year')
    volume_hint = (data.get('volume_hint') or '').strip() or None
    volume_id = data.get('volume_id')
    condition = (data.get('condition') or '').strip()
    skip_existing = data.get('skip_existing', True)

    if start_year not in (None, ''):
        try:
            start_year = int(start_year)
        except (TypeError, ValueError):
            return jsonify({'error': 'Start year must be a four-digit year.'}), 400
    else:
        start_year = None

    if volume_id not in (None, ''):
        try:
            volume_id = int(volume_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'Volume id must be a number.'}), 400
    else:
        volume_id = None

    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    result = bulk_add_single_issue(
        user_id=current_user.id,
        series=series,
        issue_number=issue_number,
        api_key=api_key,
        start_year=start_year,
        volume_hint=volume_hint,
        volume_id=volume_id,
        condition=condition,
        skip_existing=bool(skip_existing),
    )
    status_code = 503 if (
        result.get('status') == 'failed'
        and 'ComicVine API key' in result.get('error', '')
    ) else 200
    return jsonify(result), status_code


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
        headers = {
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Get the image data
        image_data = response.content
        
        # Determine MIME type from response headers or URL
        content_type = response.headers.get('content-type', 'image/jpeg')
        if 'image/' not in content_type:
            # Fallback to determining from URL
            if '.png' in image_url.lower():
                content_type = 'image/png'
            elif '.gif' in image_url.lower():
                content_type = 'image/gif'
            elif '.webp' in image_url.lower():
                content_type = 'image/webp'
            else:
                content_type = 'image/jpeg'
        
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
        
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to fetch image: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to process image: {str(e)}'}), 500

@comics_bp.route('/comics/fetch-multiple-covers', methods=['POST'])
@login_required
def fetch_multiple_covers():
    """Fetch multiple cover images from URLs and save them."""
    data = request.get_json()
    cover_images = data.get('cover_images', [])
    
    if not cover_images:
        return jsonify({'error': 'No cover images provided'}), 400
    
    downloaded_covers = []
    
    try:
        headers = {
            'User-Agent': 'ComicBookManager/1.0 (https://github.com/crench88/comicbook-manager; crench88@gmail.com) Python/3.x'
        }
        
        for i, cover_data in enumerate(cover_images):
            image_url = cover_data.get('url', '')
            size_label = cover_data.get('label', f'Cover {i+1}')
            
            if not image_url:
                continue
            
            try:
                response = requests.get(image_url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Generate filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_api_cover_{i+1}.jpg"
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                
                # Ensure upload directory exists
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                # Save the image
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                # Create thumbnail
                try:
                    with Image.open(filepath) as img:
                        # Convert to RGB if necessary
                        if img.mode in ('RGBA', 'LA', 'P'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                            img = background
                        
                        # Calculate new size maintaining aspect ratio
                        width, height = img.size
                        max_size = (300, 300)
                        scale = min(max_size[0] / width, max_size[1] / height)
                        new_size = (int(width * scale), int(height * scale))
                        
                        # Resize image
                        img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                        
                        # Create a white background of the target size
                        thumb = Image.new('RGB', max_size, (255, 255, 255))
                        
                        # Calculate position to center the image
                        x = (max_size[0] - new_size[0]) // 2
                        y = (max_size[1] - new_size[1]) // 2
                        
                        # Paste the resized image onto the background
                        thumb.paste(img_resized, (x, y))
                        
                        thumb_filename = f"thumb_{filename}"
                        thumb_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_filename)
                        thumb.save(thumb_filepath, 'JPEG', quality=85)
                except Exception as e:
                    print(f"Error creating thumbnail for {filename}: {e}")
                
                downloaded_covers.append({
                    'filename': filename,
                    'label': size_label,
                    'url': image_url
                })
                
            except Exception as e:
                print(f"Error downloading cover {i+1}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'covers': downloaded_covers,
            'message': f'Successfully downloaded {len(downloaded_covers)} cover images'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to download covers: {str(e)}'}), 500

@comics_bp.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """Serve uploaded cover images (legacy support)."""
    from flask import send_from_directory
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@comics_bp.route('/comics/ai-value-lookup', methods=['POST'])
@login_required
def ai_value_lookup():
    """AI-powered comic value estimation endpoint."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Extract comic information
        series = data.get('series', '').strip()
        title = data.get('title', '').strip()
        issue_number = data.get('issue_number', '').strip()
        publisher = data.get('publisher', '').strip()
        condition = data.get('condition', '').strip()
        upc = data.get('upc', '').strip()
        
        if not any([series, title, issue_number]):
            return jsonify({'success': False, 'error': 'At least series, title, or issue number is required'}), 400
        
        # Build search query for value estimation
        search_terms = []
        if series:
            search_terms.append(series)
        if title:
            search_terms.append(title)
        if issue_number:
            search_terms.append(f"#{issue_number}")
        
        search_query = " ".join(search_terms)
        
        # Use AI/Co-pilot to estimate value
        estimated_value = estimate_comic_value_ai(search_query, publisher, condition, upc=upc, title=title)
        
        if estimated_value:
            return jsonify({
                'success': True,
                'estimated_value': estimated_value,
                'confidence_level': 'High',
                'search_query': search_query
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not estimate value for this comic'
            }), 404
            
    except Exception as e:
        print(f"AI value lookup error: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while estimating the value'
        }), 500


def estimate_comic_value_ai(search_query, publisher, condition, upc=None, title=None):
    """
    AI-powered comic value estimation using market data and heuristics.
    This function simulates an AI/Co-pilot system that would analyze:
    - Current market prices from various sources
    - Rarity and demand factors
    - Condition impact on value
    - Historical sales data
    - Publisher and series popularity
    - UPC code for specific issue identification
    - Title for special issue recognition
    """
    try:
        # For now, we'll implement a basic heuristic-based estimation
        # In a real implementation, this would call an AI service or analyze market data
        
        # Enhanced base value ranges for different comic types
        base_values = {
            'marvel': {
                'spider-man': {'min': 15, 'max': 50},
                'amazing spider-man': {'min': 20, 'max': 60},
                'x-men': {'min': 12, 'max': 45},
                'uncanny x-men': {'min': 15, 'max': 55},
                'avengers': {'min': 10, 'max': 40},
                'iron man': {'min': 8, 'max': 35},
                'captain america': {'min': 10, 'max': 40},
                'thor': {'min': 8, 'max': 35},
                'hulk': {'min': 10, 'max': 40},
                'deadpool': {'min': 12, 'max': 45},
                'civil war': {'min': 15, 'max': 50},
                'fantastic four': {'min': 12, 'max': 45},
                'daredevil': {'min': 10, 'max': 40},
                'punisher': {'min': 8, 'max': 35},
                'wolverine': {'min': 12, 'max': 45},
                'default': {'min': 5, 'max': 25}
            },
            'dc': {
                'batman': {'min': 20, 'max': 60},
                'detective comics': {'min': 25, 'max': 70},
                'superman': {'min': 15, 'max': 50},
                'action comics': {'min': 20, 'max': 60},
                'justice league': {'min': 12, 'max': 45},
                'flash': {'min': 10, 'max': 40},
                'green lantern': {'min': 8, 'max': 35},
                'wonder woman': {'min': 10, 'max': 40},
                'aquaman': {'min': 8, 'max': 30},
                'default': {'min': 8, 'max': 30}
            },
            'image': {
                'spawn': {'min': 8, 'max': 35},
                'saga': {'min': 10, 'max': 40},
                'walking dead': {'min': 12, 'max': 45},
                'invincible': {'min': 8, 'max': 30},
                'default': {'min': 3, 'max': 20}
            },
            'dark horse': {
                'hellboy': {'min': 10, 'max': 40},
                'sin city': {'min': 8, 'max': 35},
                'default': {'min': 5, 'max': 25}
            },
            'boom': {'default': {'min': 3, 'max': 18}},
            'valiant': {'default': {'min': 5, 'max': 25}},
            'default': {'default': {'min': 5, 'max': 25}}
        }
        
        # Determine publisher and series
        search_lower = search_query.lower()
        publisher_lower = publisher.lower() if publisher else ''
        
        # Get base value range
        if publisher_lower in base_values:
            publisher_ranges = base_values[publisher_lower]
        else:
            publisher_ranges = base_values['default']
        
        # Determine series-specific range with enhanced matching
        series_range = None
        for series_name, range_data in publisher_ranges.items():
            if series_name in search_lower:
                series_range = range_data
                break
        
        # If no specific series found, try matching by title
        if not series_range and title:
            title_lower = title.lower()
            for series_name, range_data in publisher_ranges.items():
                if series_name in title_lower:
                    series_range = range_data
                    break
        
        if not series_range:
            series_range = publisher_ranges['default']
        
        # Enhanced condition multiplier with more granular values
        condition_multipliers = {
            'mint': 1.8,
            'near mint': 1.5,
            'very fine': 1.2,
            'fine': 1.0,
            'very good': 0.7,
            'good': 0.5,
            'fair': 0.3,
            'poor': 0.15
        }
        
        condition_lower = condition.lower() if condition else 'fine'
        multiplier = condition_multipliers.get(condition_lower, 1.0)
        
        # Extract issue number from search query or title
        issue_number = None
        import re
        
        # Look for issue numbers in search query
        issue_match = re.search(r'#(\d+)', search_query)
        if issue_match:
            issue_number = issue_match.group(1)
        
        # If not found in search query, look in title
        if not issue_number and title:
            issue_match = re.search(r'#(\d+)', title)
            if issue_match:
                issue_number = issue_match.group(1)
        
        # Apply issue number factors
        issue_factor = 1.0
        if issue_number:
            try:
                issue_num = int(issue_number)
                if issue_num == 1:
                    issue_factor = 1.8  # First issues are typically more valuable
                elif issue_num <= 5:
                    issue_factor = 1.4  # Very early issues
                elif issue_num <= 10:
                    issue_factor = 1.2  # Early issues
                elif issue_num == 100 or issue_num == 200 or issue_num == 300:
                    issue_factor = 1.3  # Milestone issues
                elif issue_num >= 100:
                    issue_factor = 1.1  # Other milestone issues
            except ValueError:
                pass
        
        # UPC code enhancement - certain UPCs might indicate special editions
        upc_factor = 1.0
        if upc:
            upc_str = str(upc)
            # Check for special UPC patterns (this would be enhanced with real UPC database)
            if len(upc_str) >= 12:
                # Some UPCs might indicate variant covers or special editions
                if upc_str.endswith('001'):  # Standard cover
                    upc_factor = 1.0
                elif upc_str.endswith('002'):  # Variant cover
                    upc_factor = 1.2
                elif upc_str.endswith('003'):  # Special variant
                    upc_factor = 1.3
        
        # Title-based enhancements
        title_factor = 1.0
        if title:
            title_lower = title.lower()
            # Special keywords that might indicate higher value
            special_keywords = ['first', 'origin', 'death', 'wedding', 'return', 'final', 'annual', 'special']
            for keyword in special_keywords:
                if keyword in title_lower:
                    title_factor = 1.2
                    break
        
        # Calculate estimated value using the MINIMUM of the range (as requested)
        base_value = series_range['min']  # Use minimum instead of average
        estimated_value = base_value * multiplier * issue_factor * upc_factor * title_factor
        
        # Add some randomness to simulate market variation (reduced for more conservative estimates)
        import random
        variation = random.uniform(0.9, 1.1)  # Reduced variation for more conservative estimates
        estimated_value *= variation
        
        # Round to 2 decimal places
        estimated_value = round(estimated_value, 2)
        
        # Ensure minimum value
        estimated_value = max(estimated_value, 1.0)
        
        print(f"🤖 AI Value Estimation: {search_query} -> ${estimated_value}")
        print(f"   Publisher: {publisher}, Condition: {condition}")
        print(f"   Base (min): ${base_value}, Multiplier: {multiplier}, Issue Factor: {issue_factor}")
        print(f"   UPC Factor: {upc_factor}, Title Factor: {title_factor}")
        print(f"   Range: ${series_range['min']} - ${series_range['max']}")
        
        return estimated_value
        
    except Exception as e:
        print(f"Error in AI value estimation: {e}")
        return None


