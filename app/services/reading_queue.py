"""Digital reading queues: continue, unread files, next issue in a series."""

from __future__ import annotations

from sqlalchemy.orm import defer, with_expression

from .. import db
from ..models import Comic, ComicFile, ReadingProgress, Series


def _cover_options():
    return (
        defer(Comic.cover_image),
        defer(Comic.additional_covers),
        with_expression(
            Comic.cover_available,
            db.or_(Comic.cover_image_path.isnot(None), Comic.cover_image.isnot(None)),
        ),
    )


def continue_reading_for_user(user_id: int, limit: int = 6):
    """In-progress digital comics, most recently updated first."""
    return (
        db.session.query(Comic, ReadingProgress.page_number, ComicFile.page_count)
        .join(
            ReadingProgress,
            db.and_(
                ReadingProgress.comic_id == Comic.id,
                ReadingProgress.user_id == user_id,
            ),
        )
        .join(ComicFile, ComicFile.comic_id == Comic.id)
        .filter(
            Comic.user_id == user_id,
            Comic.is_wishlist.is_(False),
            ReadingProgress.page_number < ComicFile.page_count,
        )
        .options(*_cover_options())
        .order_by(ReadingProgress.updated_at.desc())
        .limit(limit)
        .all()
    )


def unread_digital_for_user(user_id: int, limit: int = 6, exclude_ids: set[int] | None = None):
    """Digital files the user has not started (no reading progress)."""
    from ..comics.helpers import _series_group_sql

    query = (
        Comic.query.join(ComicFile, ComicFile.comic_id == Comic.id)
        .outerjoin(
            ReadingProgress,
            db.and_(
                ReadingProgress.comic_id == Comic.id,
                ReadingProgress.user_id == user_id,
            ),
        )
        .outerjoin(Series, Comic.series_id == Series.id)
        .filter(
            Comic.user_id == user_id,
            Comic.is_wishlist.is_(False),
            ReadingProgress.id.is_(None),
        )
        .options(*_cover_options())
        .order_by(_series_group_sql().asc(), Comic.issue_number.asc())
    )
    if exclude_ids:
        query = query.filter(~Comic.id.in_(exclude_ids))
    return query.limit(limit).all()


def _is_unfinished(comic: Comic, progress_by_comic: dict[int, int]) -> bool:
    comic_file = comic.digital_file
    if comic_file is None:
        return False
    page = progress_by_comic.get(comic.id)
    if page is None:
        return True
    return page < (comic_file.page_count or 0)


def next_digital_in_series(user_id: int, comic: Comic, exclude_ids: set[int] | None = None):
    """Next unfinished digital issue after ``comic`` in the same series group."""
    from ..comics.helpers import _issue_sort_key, _series_group_sql

    series_name = comic.series_label
    if not series_name or series_name == 'Unknown Series':
        return None

    siblings = (
        Comic.query.join(ComicFile, ComicFile.comic_id == Comic.id)
        .outerjoin(Series, Comic.series_id == Series.id)
        .filter(
            Comic.user_id == user_id,
            Comic.is_wishlist.is_(False),
            _series_group_sql() == series_name,
        )
        .options(*_cover_options())
        .all()
    )
    if not siblings:
        return None

    progress_rows = (
        db.session.query(ReadingProgress.comic_id, ReadingProgress.page_number)
        .filter(
            ReadingProgress.user_id == user_id,
            ReadingProgress.comic_id.in_([row.id for row in siblings]),
        )
        .all()
    )
    progress_by_comic = {comic_id: page for comic_id, page in progress_rows}
    current_key = _issue_sort_key(comic)
    skip = exclude_ids or set()

    candidates = []
    for sibling in siblings:
        if sibling.id == comic.id or sibling.id in skip:
            continue
        if _issue_sort_key(sibling) <= current_key:
            continue
        if not _is_unfinished(sibling, progress_by_comic):
            continue
        candidates.append(sibling)
    if not candidates:
        return None
    candidates.sort(key=_issue_sort_key)
    return candidates[0]


def dashboard_reading_queues(user_id: int, limit: int = 6) -> dict:
    continue_reading = continue_reading_for_user(user_id, limit=limit)
    continue_ids = {comic.id for comic, _page, _total in continue_reading}

    next_in_series = []
    claimed = set(continue_ids)
    for comic, _page, _total in continue_reading:
        nxt = next_digital_in_series(user_id, comic, exclude_ids=claimed)
        if nxt is None:
            continue
        next_in_series.append((comic, nxt))
        claimed.add(nxt.id)

    unread_digital = unread_digital_for_user(
        user_id, limit=limit, exclude_ids=claimed,
    )
    return {
        'continue_reading': continue_reading,
        'unread_digital': unread_digital,
        'next_in_series': next_in_series,
    }
