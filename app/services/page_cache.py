"""Size-capped LRU disk cache for extracted reader pages."""

from __future__ import annotations

import os
from io import BytesIO
from threading import Lock

from flask import current_app

DEFAULT_SIZE_LIMIT = 512 * 1024 * 1024

_caches: dict[str, object] = {}
_caches_lock = Lock()


def _cache_settings() -> tuple[str, int]:
    directory = current_app.config.get('READER_CACHE_DIR')
    if not directory:
        directory = os.path.join(current_app.instance_path, 'reader_cache')
    limit = current_app.config.get('READER_CACHE_SIZE_LIMIT', DEFAULT_SIZE_LIMIT)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_SIZE_LIMIT
    return os.path.abspath(directory), limit


def _cache():
    """One diskcache handle per cache directory, shared across requests."""
    directory, size_limit = _cache_settings()
    existing = _caches.get(directory)
    if existing is not None:
        return existing
    with _caches_lock:
        existing = _caches.get(directory)
        if existing is not None:
            return existing
        import diskcache

        os.makedirs(directory, exist_ok=True)
        cache = diskcache.Cache(
            directory,
            size_limit=size_limit,
            eviction_policy='least-recently-used',
            tag_index=True,
        )
        _caches[directory] = cache
        return cache


def comic_file_tag(comic_file) -> str:
    """Eviction tag grouping every cached page of one archive."""
    return f'comic_file:{comic_file.id}'


def _version(comic_file) -> str:
    return comic_file.content_hash or (comic_file.storage_path or '')


def members_key(comic_file) -> str:
    return f'members:{comic_file.id}:{_version(comic_file)}'


def page_key(comic_file, page_number: int) -> str:
    return f'page:{comic_file.id}:{_version(comic_file)}:{page_number}'


def panels_key(comic_file, page_number: int) -> str:
    # Bump version when panel detection algorithm changes.
    return f'panels:v2:{comic_file.id}:{_version(comic_file)}:{page_number}'


def get_members(comic_file) -> list[str] | None:
    cached = _cache().get(members_key(comic_file))
    if isinstance(cached, list) and cached:
        return cached
    return None


def set_members(comic_file, members: list[str]) -> None:
    _cache().set(
        members_key(comic_file),
        list(members),
        tag=comic_file_tag(comic_file),
    )


def get_page_stream(comic_file, page_number: int):
    """Return a file-like object for a cached page, or None on a miss."""
    try:
        value = _cache().get(page_key(comic_file, page_number), read=True)
    except Exception:
        # A corrupt cache entry should never break reading.
        return None
    if value is None:
        return None
    # diskcache returns bytes for small values and a file handle for large ones.
    if isinstance(value, (bytes, bytearray)):
        return BytesIO(bytes(value))
    return value


def set_page(comic_file, page_number: int, data: bytes) -> None:
    _cache().set(
        page_key(comic_file, page_number),
        data,
        tag=comic_file_tag(comic_file),
    )


def get_panels(comic_file, page_number: int):
    value = _cache().get(panels_key(comic_file, page_number))
    if isinstance(value, list) and value:
        return value
    return None


def set_panels(comic_file, page_number: int, panels: list) -> None:
    _cache().set(
        panels_key(comic_file, page_number),
        list(panels),
        tag=comic_file_tag(comic_file),
    )


def evict_comic_file(comic_file) -> int:
    """Drop every cached page/listing for one archive."""
    cache = _cache()
    removed = cache.evict(comic_file_tag(comic_file))
    cache.expire()
    return removed or 0


def clear() -> None:
    _cache().clear()


def reset_for_tests() -> None:
    """Close cached handles so a new instance/config gets a fresh cache."""
    with _caches_lock:
        for cache in _caches.values():
            try:
                cache.close()
            except Exception:
                pass
        _caches.clear()


def stats() -> dict:
    cache = _cache()
    directory, size_limit = _cache_settings()
    return {
        'directory': directory,
        'size_limit': size_limit,
        'volume': cache.volume(),
        'count': len(cache),
    }
