"""Filesystem cover storage with dual-read fallback to SQLite BLOBs."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from flask import current_app, request, send_file

from .. import db

logger = logging.getLogger(__name__)

_MIME_TO_EXT = {
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
}


def covers_root() -> Path:
    configured = current_app.config.get('COVERS_FOLDER')
    if configured:
        root = Path(configured)
    else:
        root = Path(current_app.instance_path) / 'covers'
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def keep_blob_copies() -> bool:
    """Whether to retain BLOB bytes after writing filesystem covers."""
    value = current_app.config.get('COVERS_KEEP_BLOB', True)
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _extension_for_mime(mime_type: str | None) -> str:
    return _MIME_TO_EXT.get((mime_type or '').lower(), '.jpg')


def _safe_resolve(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    relative_path = relative_path.replace('\\', '/').lstrip('/')
    if '..' in relative_path.split('/'):
        return None
    root = covers_root()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def delete_cover_file(relative_path: str | None) -> None:
    path = _safe_resolve(relative_path)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning('Could not delete cover file %s', path, exc_info=True)


def read_cover_bytes(relative_path: str | None = None, blob: bytes | None = None) -> bytes | None:
    path = _safe_resolve(relative_path)
    if path is not None:
        try:
            return path.read_bytes()
        except OSError:
            logger.warning('Could not read cover file %s', path, exc_info=True)
    if blob:
        return blob
    return None


def get_primary_cover_bytes(comic) -> bytes | None:
    return read_cover_bytes(getattr(comic, 'cover_image_path', None), getattr(comic, 'cover_image', None))


def get_variant_cover_bytes(cover) -> bytes | None:
    return read_cover_bytes(getattr(cover, 'image_path', None), getattr(cover, 'image_data', None))


def cover_version(relative_path: str | None = None, blob: bytes | None = None) -> str | None:
    """Short token that changes whenever the stored image changes.

    Cover URLs are otherwise stable, so without this a swapped cover keeps
    showing the browser's cached copy.
    """
    path = _safe_resolve(relative_path)
    if path is not None:
        try:
            stat = path.stat()
        except OSError:
            return None
        seed = f'{path.name}:{stat.st_mtime_ns}:{stat.st_size}'
        return hashlib.sha256(seed.encode()).hexdigest()[:12]
    if blob:
        return content_digest(blob)[:12]
    return None


def apply_cover_cache_headers(response):
    """Covers are per-user, and only versioned URLs are safe to cache."""
    if request and request.args.get('v'):
        response.headers['Cache-Control'] = 'private, max-age=31536000'
    else:
        response.headers['Cache-Control'] = 'private, no-cache'
    return response


def send_cover_response(relative_path: str | None, blob: bytes | None, mime_type: str | None):
    """Prefer zero-copy file send; fall back to in-memory BLOB response."""
    from ..comics.helpers import _cover_blob_response

    path = _safe_resolve(relative_path)
    if path is not None:
        response = send_file(
            path,
            mimetype=mime_type or 'image/jpeg',
            conditional=True,
        )
        return apply_cover_cache_headers(response)
    if blob:
        return _cover_blob_response(blob, mime_type)
    return None


def _write_bytes(relative_path: str, blob: bytes) -> str:
    relative_path = relative_path.replace('\\', '/')
    root = covers_root()
    absolute = (root / relative_path).resolve()
    absolute.relative_to(root)  # path traversal guard
    absolute.parent.mkdir(parents=True, exist_ok=True)
    # Names carry a content digest, so a same-size match is already these bytes.
    # Skipping the rewrite also avoids replacing a file Windows may hold open.
    try:
        if absolute.stat().st_size == len(blob):
            return relative_path
    except OSError:
        pass
    tmp = absolute.with_suffix(absolute.suffix + '.tmp')
    tmp.write_bytes(blob)
    os.replace(tmp, absolute)
    return relative_path


def ensure_comic_id(comic) -> int:
    if comic.id is None:
        db.session.flush()
    if comic.id is None:
        raise RuntimeError('Comic must be flushed before writing cover files.')
    return comic.id


def _versioned_name(stem: str, blob: bytes, mime_type: str | None) -> str:
    """Content-addressed filename, so a new image never overwrites the old one."""
    return f'{stem}_{content_digest(blob)[:12]}{_extension_for_mime(mime_type)}'


def persist_primary_cover(comic, blob: bytes, mime_type: str | None) -> str:
    """Write primary cover to disk and update comic path/BLOB fields."""
    comic_id = ensure_comic_id(comic)
    user_id = comic.user_id
    relative = f'{user_id}/{comic_id}/{_versioned_name("primary", blob, mime_type)}'

    old_path = getattr(comic, 'cover_image_path', None)
    _write_bytes(relative, blob)
    comic.cover_image_path = relative
    comic.cover_image_mime = mime_type or 'image/jpeg'
    if keep_blob_copies():
        comic.cover_image = blob
    else:
        comic.cover_image = None

    if old_path and old_path != relative:
        delete_cover_file(old_path)
    return relative


def persist_variant_cover(cover, blob: bytes, mime_type: str | None, *, user_id: int, comic_id: int) -> str:
    """Write alternate cover to disk and update variant path/BLOB fields."""
    if cover.id is None:
        db.session.flush()
    if cover.id is None:
        raise RuntimeError('Cover variant must be flushed before writing cover files.')

    relative = f'{user_id}/{comic_id}/{_versioned_name(f"variant_{cover.id}", blob, mime_type)}'
    old_path = getattr(cover, 'image_path', None)
    _write_bytes(relative, blob)
    cover.image_path = relative
    cover.mime_type = mime_type or 'image/jpeg'
    if keep_blob_copies():
        cover.image_data = blob
    else:
        cover.image_data = None

    if old_path and old_path != relative:
        delete_cover_file(old_path)
    return relative


def clear_primary_cover(comic) -> None:
    delete_cover_file(getattr(comic, 'cover_image_path', None))
    comic.cover_image_path = None
    comic.cover_image = None
    comic.cover_image_mime = None


def clear_variant_cover(cover) -> None:
    delete_cover_file(getattr(cover, 'image_path', None))
    cover.image_path = None
    cover.image_data = None


def migrate_comic_covers(comic, *, clear_blobs: bool = False) -> dict:
    """Extract BLOB covers for one comic onto disk. Returns counters."""
    stats = {'primary': 0, 'variants': 0}
    previous_keep = current_app.config.get('COVERS_KEEP_BLOB', True)
    if clear_blobs:
        current_app.config['COVERS_KEEP_BLOB'] = False
    try:
        if comic.cover_image and not comic.cover_image_path:
            persist_primary_cover(comic, comic.cover_image, comic.cover_image_mime)
            stats['primary'] = 1
        elif comic.cover_image and comic.cover_image_path and clear_blobs:
            comic.cover_image = None
            stats['primary'] = 1

        for variant in list(comic.cover_variants):
            if variant.image_data and not variant.image_path:
                persist_variant_cover(
                    variant,
                    variant.image_data,
                    variant.mime_type,
                    user_id=comic.user_id,
                    comic_id=comic.id,
                )
                stats['variants'] += 1
            elif variant.image_data and variant.image_path and clear_blobs:
                variant.image_data = None
                stats['variants'] += 1
    finally:
        current_app.config['COVERS_KEEP_BLOB'] = previous_keep
    return stats


def content_digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()
