"""Local Series Catalog search."""

import re
from .. import db
from ..models import Series, SeriesIssue


def _parse_start_year(date_range: str) -> str:
    if not date_range:
        return ''
    match = re.search(r'\b(19\d{2}|20\d{2})\b', date_range)
    return match.group(1) if match else ''


def search_local_series_volumes(series_name: str, publisher: str = '') -> list:
    """Return Series Catalog entries that match a series name (for volume picking)."""
    series_name = (series_name or '').strip()
    if not series_name:
        return []

    query = db.session.query(
        Series,
        db.func.count(SeriesIssue.id).label('issue_count'),
    ).outerjoin(SeriesIssue, SeriesIssue.series_id == Series.id)
    query = query.filter(Series.name.ilike(f'%{series_name}%'))
    if publisher:
        query = query.filter(Series.publisher.ilike(f'%{publisher.strip()}%'))

    rows = query.group_by(Series.id).order_by(
        Series.name.asc(),
        Series.volume.asc(),
    ).limit(50).all()
    results = []
    for series, issue_count in rows:
        start_year = _parse_start_year(series.date_range or '')
        date_range_label = series.date_range or ''
        if not date_range_label and start_year:
            date_range_label = start_year
        results.append({
            'source': 'Series Catalog',
            'comicvine_volume_id': series.comicvine_volume_id,
            'local_series_id': series.id,
            'name': series.name,
            'display_name': series.display_name,
            'publisher': series.publisher or '',
            'start_year': start_year,
            'count_of_issues': issue_count,
            'volume_number': series.volume or '',
            'date_range_label': date_range_label,
        })
    return results


def search_local_database(query, series_name=None, issue_number=None, local_series_id=None):
    try:
        filters_applied = []
        issue_query = SeriesIssue.query.join(Series)

        if local_series_id:
            filters_applied.append(f"local_series_id={local_series_id}")
            issue_query = issue_query.filter(Series.id == int(local_series_id))
        elif series_name:
            filters_applied.append(f"series_name~{series_name}")
            series_filter = Series.name.ilike(f'%{series_name}%')
            lowered = series_name.lower()
            parsed_name = series_name
            parsed_volume = None
            vol_match = re.search(
                r'(.*?)(?:\s+[,-]?\s*)?(?:vol\.?|volume)\s*(\d+)\s*$',
                lowered, re.IGNORECASE,
            )
            if vol_match:
                parsed_name = vol_match.group(1).strip()
                parsed_volume = vol_match.group(2).strip()
            if parsed_volume:
                filters_applied.append(f"volume~{parsed_volume}")
                series_filter = db.and_(
                    Series.name.ilike(f'%{parsed_name}%'),
                    Series.volume.ilike(f'%{parsed_volume}%'),
                )
            issue_query = issue_query.filter(series_filter)

        if issue_number:
            filters_applied.append(f"issue_number~{issue_number}")
            issue_query = issue_query.filter(
                SeriesIssue.issue_number.ilike(f'%{issue_number}%')
            )

        cleaned_query = (query or '').strip()
        if cleaned_query:
            filters_applied.append(f"query~{cleaned_query}")
            ilike = f'%{cleaned_query}%'
            issue_query = issue_query.filter(
                db.or_(
                    SeriesIssue.issue_number.ilike(ilike),
                    SeriesIssue.title.ilike(ilike),
                    SeriesIssue.cover_date.ilike(ilike),
                    SeriesIssue.featured_characters.ilike(ilike),
                    SeriesIssue.writer.ilike(ilike),
                    SeriesIssue.artist.ilike(ilike),
                    SeriesIssue.story_arc.ilike(ilike),
                    Series.name.ilike(ilike),
                )
            )

        issues = issue_query.limit(50).all()
        results = []
        for issue in issues:
            series = issue.series
            description_parts = []
            if issue.writer:
                description_parts.append(f"Writer: {issue.writer}")
            if issue.artist:
                description_parts.append(f"Artist: {issue.artist}")
            if issue.story_arc:
                description_parts.append(f"Story Arc: {issue.story_arc}")

            result = {
                'id': f'series_issue_{issue.id}',
                'comicvine_id': issue.comicvine_issue_id,
                'title': issue.title or series.display_name,
                'issue_title': issue.title or '',
                'series': series.display_name,
                'issue_number': issue.issue_number,
                'publisher': series.publisher or '',
                'characters': issue.featured_characters or '',
                'writer': issue.writer or '',
                'artist': issue.artist or '',
                'story_arc': issue.story_arc or '',
                'writers': [w.strip() for w in (issue.writer or '').split(',') if w.strip()],
                'artists': [a.strip() for a in (issue.artist or '').split(',') if a.strip()],
                'genre': '',
                'release_date': issue.cover_date or '',
                'cover_date': issue.cover_date or '',
                'description': ' | '.join(description_parts) if description_parts else '',
                'cover_image_url': '',
                'cover_images': [],
                'volume': series.display_name,
                'volume_start_year': '',
                'upc': '',
                'series_id': series.id,
                'source': 'Series Catalog',
                'has_variants_endpoint': bool(issue.comicvine_issue_id),
            }
            results.append(result)
        return results
    except Exception:
        return []
