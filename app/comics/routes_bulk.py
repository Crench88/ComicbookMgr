"""Bulk-add API routes."""

from flask import current_app, jsonify, request
from flask_login import current_user, login_required

from ..services.bulk_add import bulk_add_single_issue, parse_issue_ranges
from . import comics_bp

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
    in_collection = bool(data.get('in_collection', True))
    is_digital = bool(data.get('is_digital', False))

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
        in_collection=in_collection,
        is_digital=is_digital,
    )
    status_code = 503 if (
        result.get('status') == 'failed'
        and 'ComicVine API key' in result.get('error', '')
    ) else 200
    return jsonify(result), status_code
