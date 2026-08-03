"""Persist and resolve digital comic archives (CBZ/CBR) on disk."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from io import BytesIO
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from .. import db
from ..models import ComicFile, ReadingProgress
from . import page_cache
from .archives import (
    ArchiveError,
    format_for_filename,
    list_pages,
    mime_for_member,
    read_page,
    validate_upload,
)

logger = logging.getLogger(__name__)


def digital_root() -> Path:
    configured = current_app.config.get('DIGITAL_FOLDER')
    if configured:
        root = Path(configured)
    else:
        root = Path(current_app.instance_path) / 'digital'
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def resolve_digital_path(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    relative_path = relative_path.replace('\\', '/').lstrip('/')
    if '..' in relative_path.split('/'):
        return None
    root = digital_root()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def get_comic_file(comic) -> ComicFile | None:
    return ComicFile.query.filter_by(comic_id=comic.id, user_id=comic.user_id).first()


def delete_comic_file_row(comic_file: ComicFile | None) -> None:
    if comic_file is None:
        return
    page_cache.evict_comic_file(comic_file)
    path = resolve_digital_path(comic_file.storage_path)
    if path is not None:
        try:
            path.unlink(missing_ok=True)
            parent = path.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            logger.warning('Could not delete digital file %s', path, exc_info=True)
    db.session.delete(comic_file)


def delete_comic_digital_assets(comic) -> None:
    """Remove digital archive + reading progress for a comic."""
    comic_file = get_comic_file(comic)
    delete_comic_file_row(comic_file)
    ReadingProgress.query.filter_by(comic_id=comic.id, user_id=comic.user_id).delete(
        synchronize_session=False
    )
    # Best-effort: remove empty user/comic folder tree.
    try:
        comic_dir = digital_root() / str(comic.user_id) / str(comic.id)
        if comic_dir.is_dir():
            shutil.rmtree(comic_dir, ignore_errors=True)
    except OSError:
        logger.warning('Could not remove digital folder for comic %s', comic.id, exc_info=True)


def save_digital_file_for_comic(comic, file_storage) -> ComicFile:
    """Validate and store a CBZ/CBR for the comic (replaces any existing file)."""
    if comic.id is None:
        db.session.flush()
    if comic.id is None:
        raise RuntimeError('Comic must be saved before attaching a digital file.')

    raw, page_count, original_filename, archive_format = validate_upload(file_storage)
    safe_name = secure_filename(original_filename) or f'comic.{archive_format}'
    try:
        format_for_filename(safe_name)
    except ArchiveError:
        safe_name = f'{safe_name}.{archive_format}'

    relative = f'{comic.user_id}/{comic.id}/{safe_name}'
    root = digital_root()
    absolute = (root / relative).resolve()
    absolute.relative_to(root)
    absolute.parent.mkdir(parents=True, exist_ok=True)

    tmp = absolute.with_suffix(absolute.suffix + '.tmp')
    tmp.write_bytes(raw)
    os.replace(tmp, absolute)

    digest = hashlib.sha256(raw).hexdigest()
    existing = get_comic_file(comic)
    if existing is not None:
        page_cache.evict_comic_file(existing)
        old_path = resolve_digital_path(existing.storage_path)
        if old_path is not None and old_path != absolute:
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                logger.warning('Could not remove previous digital file %s', old_path, exc_info=True)
        comic_file = existing
    else:
        comic_file = ComicFile(comic_id=comic.id, user_id=comic.user_id)
        db.session.add(comic_file)

    comic_file.storage_path = relative.replace('\\', '/')
    comic_file.format = archive_format
    comic_file.original_filename = original_filename[:255]
    comic_file.page_count = page_count
    comic_file.file_size = len(raw)
    comic_file.content_hash = digest
    return comic_file


# Kept for callers written against the CBZ-only MVP.
save_cbz_for_comic = save_digital_file_for_comic


def archive_path_for(comic_file: ComicFile) -> Path:
    path = resolve_digital_path(comic_file.storage_path)
    if path is None:
        raise ArchiveError('Digital comic file is missing from disk.')
    return path


def page_members(comic_file: ComicFile) -> list[str]:
    """Cached page listing so each page view doesn't reopen the archive index."""
    cached = page_cache.get_members(comic_file)
    if cached is not None:
        return cached
    members = list_pages(archive_path_for(comic_file), comic_file.format)
    page_cache.set_members(comic_file, members)
    return members


def page_count_for(comic_file: ComicFile) -> int:
    if comic_file.page_count and comic_file.page_count > 0:
        return comic_file.page_count
    comic_file.page_count = len(page_members(comic_file))
    return comic_file.page_count


def load_page(comic_file: ComicFile, page_number: int) -> tuple[object, str, bool]:
    """
    Return (stream, mime, cache_hit) for a 1-based page.
    Extracted bytes are cached so repeat views skip archive decompression.
    """
    members = page_members(comic_file)
    if page_number < 1 or page_number > len(members):
        raise ArchiveError('Page number is out of range.')

    mime = mime_for_member(members[page_number - 1])
    stream = page_cache.get_page_stream(comic_file, page_number)
    if stream is not None:
        return stream, mime, True

    data, mime = read_page(
        archive_path_for(comic_file),
        page_number,
        comic_file.format,
        members=members,
    )
    try:
        page_cache.set_page(comic_file, page_number, data)
    except Exception:
        logger.warning('Could not cache page %s', page_number, exc_info=True)
    return BytesIO(data), mime, False
