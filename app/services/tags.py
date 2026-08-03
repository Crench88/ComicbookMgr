"""Helpers for comic tags and read status."""

from __future__ import annotations

import re

from .. import db
from ..models import Tag

READ_STATUS_CHOICES = (
    ('unread', 'Unread'),
    ('reading', 'Reading'),
    ('read', 'Read'),
)

_VALID_STATUS = {key for key, _ in READ_STATUS_CHOICES}


def normalize_read_status(value: str | None) -> str:
    status = (value or 'unread').strip().lower()
    return status if status in _VALID_STATUS else 'unread'


def parse_tag_names(text: str | None) -> list[str]:
    """Split a comma/semicolon separated tag string into unique names."""
    if not text:
        return []
    parts = re.split(r'[,;]', str(text))
    seen = set()
    names = []
    for part in parts:
        name = ' '.join(part.strip().split())
        if not name:
            continue
        name = name[:80]
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def sync_comic_tags(comic, tags_text: str | None, user_id: int) -> list[Tag]:
    """Replace comic tags from free-text input, creating Tag rows as needed."""
    names = parse_tag_names(tags_text)
    if not names:
        comic.tags = []
        return []

    existing = {
        tag.name.lower(): tag
        for tag in Tag.query.filter_by(user_id=user_id).all()
    }
    resolved = []
    for name in names:
        tag = existing.get(name.lower())
        if tag is None:
            tag = Tag(user_id=user_id, name=name)
            db.session.add(tag)
            existing[name.lower()] = tag
        resolved.append(tag)

    comic.tags = resolved
    return resolved
