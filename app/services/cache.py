"""Disk-backed cache shared across worker processes."""

import json
import os
import time
from threading import Lock

_cache = None
_cache_lock = Lock()


def _get_cache():
    global _cache
    if _cache is not None:
        return _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
        import diskcache

        cache_dir = os.environ.get('CACHE_DIR', os.path.join('instance', 'cache'))
        os.makedirs(cache_dir, exist_ok=True)
        try:
            size_limit = int(os.environ.get('CACHE_SIZE_LIMIT', 512 * 1024 * 1024))
        except (TypeError, ValueError):
            size_limit = 512 * 1024 * 1024
        _cache = diskcache.Cache(cache_dir, size_limit=size_limit)
        return _cache


def _serialize_key(key):
    if isinstance(key, (str, int, float, bool)) or key is None:
        return str(key)
    try:
        return json.dumps(key, sort_keys=True, default=str)
    except TypeError:
        return repr(key)


def cache_get(key):
    cache = _get_cache()
    item = cache.get(_serialize_key(key))
    if not item:
        return None
    expires_at, value = item
    if expires_at < time.time():
        cache.delete(_serialize_key(key))
        return None
    return value


def cache_set(key, value, ttl=300):
    cache = _get_cache()
    cache.set(_serialize_key(key), (time.time() + ttl, value), expire=ttl + 60)


def reset_cache_for_tests():
    """Clear the in-memory handle so tests can use an isolated cache directory."""
    global _cache
    with _cache_lock:
        if _cache is not None:
            _cache.close()
        _cache = None
