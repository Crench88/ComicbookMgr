"""Cover image upload, serving, and variant management routes."""

from flask import jsonify, request, url_for
from flask_login import current_user, login_required
from .. import db
from ..models import Comic, ComicCover
from ..services.cover_storage import (
    clear_variant_cover,
    get_primary_cover_bytes,
    get_variant_cover_bytes,
    persist_primary_cover,
    persist_variant_cover,
    send_cover_response,
)
from . import comics_bp
from .helpers import (
    _cover_thumbnail_response,
    _validated_cover_image,
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

    try:
        mime_type = _validated_cover_image(blob_data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    label = str(cover.get('label') or 'Cover')[:200]

    if payload.get('replace'):
        for existing in list(comic.cover_variants):
            clear_variant_cover(existing)
        comic.cover_variants.clear()
        comic.additional_covers = None
        persist_primary_cover(comic, blob_data, mime_type)
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
        variant.label = label
        persist_variant_cover(
            variant,
            blob_data,
            mime_type,
            user_id=comic.user_id,
            comic_id=comic.id,
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Could not save this cover image.'}), 500

    return jsonify({'success': True})


@comics_bp.route('/comics/<int:id>/cover')
@login_required
def serve_cover_image(id):
    """Serve primary cover from filesystem (preferred) or legacy BLOB."""
    from sqlalchemy.orm import defer, load_only

    comic = Comic.query.options(
        load_only(
            Comic.id,
            Comic.user_id,
            Comic.cover_image_path,
            Comic.cover_image_mime,
        ),
        defer(Comic.cover_image),
    ).filter_by(id=id, user_id=current_user.id).first_or_404()

    response = send_cover_response(comic.cover_image_path, None, comic.cover_image_mime)
    if response is None:
        comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
        response = send_cover_response(
            comic.cover_image_path,
            comic.cover_image,
            comic.cover_image_mime,
        )
    if response is None:
        return jsonify({'error': 'No cover image found'}), 404
    return response


@comics_bp.route('/comics/<int:id>/cover/thumbnail')
@login_required
def serve_cover_thumbnail(id):
    """Serve a cached thumbnail of the primary cover."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    image_data = get_primary_cover_bytes(comic)
    if not image_data:
        return jsonify({'error': 'No cover image found'}), 404
    return _cover_thumbnail_response(image_data, relative_path=comic.cover_image_path)


@comics_bp.route('/comics/<int:id>/covers/<int:cover_id>/image')
@login_required
def serve_cover_variant_image(id, cover_id):
    """Serve one alternate cover image without embedding Base64 in HTML."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    cover = ComicCover.query.filter_by(id=cover_id, comic_id=comic.id).first_or_404()

    response = send_cover_response(cover.image_path, cover.image_data, cover.mime_type)
    if response is None:
        return jsonify({'error': 'No cover image found'}), 404
    return response


@comics_bp.route('/comics/<int:id>/covers/<int:cover_id>/thumbnail')
@login_required
def serve_cover_variant_thumbnail(id, cover_id):
    """Serve a cached thumbnail of an alternate cover."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    cover = ComicCover.query.filter_by(id=cover_id, comic_id=comic.id).first_or_404()
    image_data = get_variant_cover_bytes(cover)
    if not image_data:
        return jsonify({'error': 'No cover image found'}), 404
    return _cover_thumbnail_response(image_data, relative_path=cover.image_path)


@comics_bp.route('/comics/<int:id>/covers/primary', methods=['POST'])
@login_required
def set_primary_cover(id):
    """Promote an alternate cover to primary without a large form POST."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    payload = request.get_json(silent=True) or {}

    try:
        cover_id = int(payload.get('cover_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'A cover id is required.'}), 400

    if not comic.set_primary_cover_variant(cover_id):
        return jsonify({'error': 'That cover variant was not found.'}), 404

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Could not update the primary cover.'}), 500

    return jsonify({
        'success': True,
        'covers': [
            {
                'id': cover['id'],
                'is_primary': cover['is_primary'],
                'label': cover['label'],
                'url': (
                    url_for(
                        'comics.serve_cover_thumbnail',
                        id=comic.id,
                        v=cover['version'],
                    )
                    if cover['is_primary']
                    else url_for(
                        'comics.serve_cover_variant_thumbnail',
                        id=comic.id,
                        cover_id=cover['id'],
                        v=cover['version'],
                    )
                ),
            }
            for cover in comic.list_cover_summaries()
        ],
    })
