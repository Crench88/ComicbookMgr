"""Routes for digital archive upload and in-browser reading."""

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from .. import db
from ..models import Comic, ReadingProgress
from ..services.archives import ArchiveError, rar_support_error
from ..services.digital_files import (
    get_comic_file,
    delete_comic_file_row,
    load_page,
    page_count_for,
    save_digital_file_for_comic,
)
from ..services import page_cache
from ..services.panel_detect import detect_panels_from_bytes
from . import reader_bp


def _owned_comic(comic_id: int) -> Comic:
    return Comic.query.filter_by(id=comic_id, user_id=current_user.id).first_or_404()


def _get_or_create_progress(comic: Comic) -> ReadingProgress:
    progress = ReadingProgress.query.filter_by(
        user_id=current_user.id,
        comic_id=comic.id,
    ).first()
    if progress is None:
        progress = ReadingProgress(
            user_id=current_user.id,
            comic_id=comic.id,
            page_number=1,
        )
        db.session.add(progress)
    return progress


def _clamp_page(page_number: int, page_count: int) -> int:
    if page_count < 1:
        return 1
    return max(1, min(int(page_number), page_count))


@reader_bp.route('/<int:comic_id>/upload', methods=['POST'])
@login_required
def upload_file(comic_id):
    """Attach or replace a CBZ/CBR for a comic."""
    comic = _owned_comic(comic_id)
    file_storage = request.files.get('digital_file')
    if file_storage is None or not file_storage.filename:
        flash('Choose a CBZ or CBR file to upload.', 'warning')
        return redirect(url_for('comics.show', id=comic.id))

    try:
        save_digital_file_for_comic(comic, file_storage)
        comic.apply_ownership(is_digital=True)
        db.session.commit()
        flash('Digital file attached. You can read it now.', 'success')
    except ArchiveError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception:
        db.session.rollback()
        flash('Could not save the digital file. Please try again.', 'danger')

    return redirect(url_for('comics.show', id=comic.id))


@reader_bp.route('/<int:comic_id>/file', methods=['POST'])
@login_required
def delete_file(comic_id):
    """Remove the attached digital archive."""
    comic = _owned_comic(comic_id)
    comic_file = get_comic_file(comic)
    if comic_file is None:
        flash('No digital file to remove.', 'info')
        return redirect(url_for('comics.show', id=comic.id))

    try:
        delete_comic_file_row(comic_file)
        db.session.commit()
        flash('Digital file removed.', 'success')
    except Exception:
        db.session.rollback()
        flash('Could not remove the digital file.', 'danger')

    return redirect(url_for('comics.show', id=comic.id))


@reader_bp.route('/<int:comic_id>')
@login_required
def read(comic_id):
    """Full-page reader UI for an attached archive."""
    comic = _owned_comic(comic_id)
    comic_file = get_comic_file(comic)
    if comic_file is None:
        flash('Upload a CBZ or CBR before reading this comic.', 'warning')
        return redirect(url_for('comics.show', id=comic.id))

    try:
        page_count = page_count_for(comic_file)
    except ArchiveError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('comics.show', id=comic.id))

    progress = _get_or_create_progress(comic)
    page = request.args.get('page', type=int) or progress.page_number or 1
    page = _clamp_page(page, page_count)

    if comic.read_status == 'unread':
        comic.read_status = 'reading'
    progress.page_number = page
    if page >= page_count:
        comic.read_status = 'read'
    db.session.commit()

    return render_template(
        'reader/read.html',
        title=f'Read · {comic.title} #{comic.issue_number}',
        comic=comic,
        comic_file=comic_file,
        page=page,
        page_count=page_count,
    )


@reader_bp.route('/<int:comic_id>/page/<int:page_number>')
@login_required
def page_image(comic_id, page_number):
    """Serve one page image, extracting from the archive only on a cache miss."""
    comic = _owned_comic(comic_id)
    comic_file = get_comic_file(comic)
    if comic_file is None:
        abort(404)

    try:
        stream, mime, cache_hit = load_page(comic_file, page_number)
    except ArchiveError:
        abort(404)

    version = comic_file.content_hash or str(comic_file.updated_at)
    response = send_file(
        stream,
        mimetype=mime,
        download_name=f'page-{page_number}',
        max_age=3600,
        conditional=True,
        etag=f'{comic_file.id}-{version[:16]}-{page_number}',
        last_modified=comic_file.updated_at,
    )
    response.headers['X-Page-Cache'] = 'hit' if cache_hit else 'miss'
    return response


@reader_bp.route('/<int:comic_id>/page/<int:page_number>/panels')
@login_required
def page_panels(comic_id, page_number):
    """Return detected panel rectangles for guided zoom on a page."""
    comic = _owned_comic(comic_id)
    comic_file = get_comic_file(comic)
    if comic_file is None:
        abort(404)

    try:
        page_count = page_count_for(comic_file)
    except ArchiveError as exc:
        return jsonify({'error': str(exc)}), 400

    page_number = _clamp_page(page_number, page_count)
    cached = page_cache.get_panels(comic_file, page_number)
    if cached is not None:
        return jsonify({
            'page': page_number,
            'panels': cached,
            'count': len(cached),
            'cached': True,
        })

    try:
        stream, _mime, _hit = load_page(comic_file, page_number)
        image_bytes = stream.read()
    except ArchiveError:
        abort(404)

    try:
        panels = detect_panels_from_bytes(image_bytes)
    except RuntimeError as exc:
        return jsonify({'error': str(exc), 'panels': [{'x': 0, 'y': 0, 'w': 1, 'h': 1}]}), 503
    except Exception:
        current_app.logger.exception('Panel detection failed')
        panels = [{'x': 0.0, 'y': 0.0, 'w': 1.0, 'h': 1.0}]

    try:
        page_cache.set_panels(comic_file, page_number, panels)
    except Exception:
        pass

    return jsonify({
        'page': page_number,
        'panels': panels,
        'count': len(panels),
        'cached': False,
    })


@reader_bp.route('/<int:comic_id>/progress', methods=['POST'])
@login_required
def save_progress(comic_id):
    """Persist last-read page (JSON)."""
    comic = _owned_comic(comic_id)
    comic_file = get_comic_file(comic)
    if comic_file is None:
        return jsonify({'error': 'No digital file'}), 404

    payload = request.get_json(silent=True) or {}
    try:
        page = int(payload.get('page') or request.form.get('page') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid page'}), 400

    try:
        page_count = page_count_for(comic_file)
    except ArchiveError as exc:
        return jsonify({'error': str(exc)}), 400

    page = _clamp_page(page, page_count)
    progress = _get_or_create_progress(comic)
    progress.page_number = page

    if comic.read_status == 'unread':
        comic.read_status = 'reading'
    if page >= page_count:
        comic.read_status = 'read'

    db.session.commit()
    return jsonify({
        'ok': True,
        'page': page,
        'page_count': page_count,
        'read_status': comic.read_status,
    })
