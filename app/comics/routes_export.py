"""Collection export routes."""

from datetime import datetime
from io import StringIO

from flask import send_file
from flask_login import current_user, login_required
from sqlalchemy.orm import load_only

from ..models import Comic
from . import comics_bp


@comics_bp.route('/comics/export')
@login_required
def export():
    """Export collection to CSV."""
    import csv

    comics = Comic.query.options(load_only(
        Comic.title,
        Comic.series,
        Comic.issue_number,
        Comic.publisher,
        Comic.writer,
        Comic.artist,
        Comic.characters,
        Comic.story_arc,
        Comic.genre,
        Comic.release_date,
        Comic.condition,
        Comic.estimated_value,
        Comic.description,
        Comic.notes,
        Comic.upc,
        Comic.is_wishlist,
    )).filter_by(user_id=current_user.id).order_by(
        Comic.series.asc(), Comic.issue_number.asc()
    ).all()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow([
        'Series', 'Title', 'Issue Number', 'Publisher', 'Writer', 'Artist',
        'Characters', 'Story Arc', 'Genre', 'Release Date', 'Condition',
        'Estimated Value', 'Description', 'Notes', 'UPC', 'Wishlist',
    ])

    for comic in comics:
        cw.writerow([
            comic.series or '',
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
            comic.notes or '',
            comic.upc or '',
            'yes' if comic.is_wishlist else '',
        ])

    output = si.getvalue()
    si.close()

    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'comic_collection_{datetime.now().strftime("%Y%m%d")}.csv',
    )
