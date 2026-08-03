"""CSV/JSON collection import routes."""

import json

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf

from ..services.comic_import import (
    annotate_duplicates,
    import_records,
    parse_csv_text,
    parse_json_text,
)
from . import comics_bp

_SESSION_KEY = 'comic_import_preview'


@comics_bp.route('/comics/import', methods=['GET', 'POST'])
@login_required
def import_comics():
    """Upload a CSV/JSON collection file for preview."""
    if request.method == 'GET':
        session.pop(_SESSION_KEY, None)
        return render_template('comics/import.html', csrf_token=generate_csrf())

    upload = request.files.get('import_file')
    if upload is None or not upload.filename:
        flash('Choose a CSV or JSON file to import.', 'danger')
        return redirect(url_for('comics.import_comics'))

    filename = upload.filename.lower()
    try:
        text = upload.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        flash('Could not read the file as UTF-8 text.', 'danger')
        return redirect(url_for('comics.import_comics'))

    try:
        if filename.endswith('.json'):
            records = parse_json_text(text)
        elif filename.endswith('.csv'):
            records = parse_csv_text(text)
        else:
            flash('Unsupported file type. Use .csv or .json.', 'danger')
            return redirect(url_for('comics.import_comics'))
    except (ValueError, json.JSONDecodeError) as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('comics.import_comics'))

    if not records:
        flash('No comic rows were found in that file.', 'warning')
        return redirect(url_for('comics.import_comics'))

    records = annotate_duplicates(records, current_user.id)
    # Store a JSON-safe copy (dates as ISO strings).
    serializable = []
    for record in records:
        item = dict(record)
        if item.get('release_date') is not None:
            item['release_date'] = item['release_date'].isoformat()
        serializable.append(item)
    session[_SESSION_KEY] = serializable

    return redirect(url_for('comics.import_preview'))


@comics_bp.route('/comics/import/preview', methods=['GET', 'POST'])
@login_required
def import_preview():
    """Review validated rows and confirm import."""
    records = session.get(_SESSION_KEY)
    if not records:
        flash('Upload a file to preview first.', 'warning')
        return redirect(url_for('comics.import_comics'))

    if request.method == 'POST':
        skip_duplicates = request.form.get('skip_duplicates', '1') == '1'
        # Rehydrate date objects
        hydrated = []
        for record in records:
            item = dict(record)
            date_text = item.get('release_date')
            if date_text:
                from datetime import date
                item['release_date'] = date.fromisoformat(date_text)
            else:
                item['release_date'] = None
            hydrated.append(item)

        result = import_records(
            hydrated,
            current_user.id,
            skip_duplicates=skip_duplicates,
        )
        session.pop(_SESSION_KEY, None)
        flash(
            f"Import complete: {result['added']} added, "
            f"{result['skipped']} skipped, {result['failed']} failed.",
            'success' if result['added'] else 'info',
        )
        return redirect(url_for('comics.index'))

    counts = {
        'total': len(records),
        'new': sum(1 for r in records if r.get('status') == 'new'),
        'duplicate': sum(1 for r in records if r.get('status') == 'duplicate'),
        'invalid': sum(1 for r in records if r.get('status') == 'invalid'),
    }
    return render_template(
        'comics/import_preview.html',
        records=records,
        counts=counts,
        csrf_token=generate_csrf(),
    )
