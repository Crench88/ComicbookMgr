"""Cover barcode scanning routes."""

from flask import jsonify, request
from flask_login import current_user, login_required

from .. import db
from ..models import Comic
from ..services.cover_barcode import scan_cover_image
from . import comics_bp


def _collect_cover_blobs(comic: Comic) -> list[tuple[str, bytes]]:
    """Return (label, bytes) for primary + alternate covers."""
    from ..services.cover_storage import get_primary_cover_bytes, get_variant_cover_bytes

    covers = []
    primary = get_primary_cover_bytes(comic)
    if primary:
        covers.append(('primary', primary))
    for variant in comic.cover_variants:
        data = get_variant_cover_bytes(variant)
        if data:
            covers.append((variant.label or f'cover-{variant.position}', data))
    return covers


@comics_bp.route('/comics/<int:id>/scan-barcode', methods=['POST'])
@login_required
def scan_cover_barcode(id):
    """
    Scan the comic's cover image(s) for a UPC/EAN barcode.

    JSON body (optional):
      {"overwrite": true}  -- replace an existing UPC when found
    """
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    overwrite = bool(payload.get('overwrite'))

    covers = _collect_cover_blobs(comic)
    if not covers:
        return jsonify({
            'success': False,
            'error': 'This comic has no cover image to scan.',
        }), 400

    last_error = None
    best = None
    all_codes = []
    scanned_label = None

    for label, blob in covers:
        result = scan_cover_image(blob)
        if result.get('error') and not result.get('available', True):
            return jsonify({
                'success': False,
                'error': result['error'],
                'dependency_missing': True,
            }), 503
        if result.get('error'):
            last_error = result['error']
        codes = result.get('codes') or []
        all_codes.extend(codes)
        if result.get('best'):
            best = result['best']
            scanned_label = label
            break

    if not best:
        return jsonify({
            'success': False,
            'error': last_error or 'No UPC/EAN barcode was found on the cover image(s).',
            'codes': all_codes,
        }), 404

    existing = (comic.upc or '').strip()
    if existing and existing != best and not overwrite:
        return jsonify({
            'success': False,
            'needs_confirmation': True,
            'upc': best,
            'existing_upc': existing,
            'codes': all_codes,
            'source_cover': scanned_label,
            'error': f'A barcode ({best}) was found, but this comic already has UPC {existing}.',
        }), 409

    comic.upc = best
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Barcode was found but could not be saved.',
            'upc': best,
        }), 500

    return jsonify({
        'success': True,
        'upc': best,
        'codes': all_codes,
        'source_cover': scanned_label,
        'overwrote': bool(existing and existing != best),
    })
