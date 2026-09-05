"""Indexed character mentions derived from Comic.characters."""

from __future__ import annotations

import re

from sqlalchemy import func

from .. import db
from ..models import CharacterMention, Comic


def parse_character_names(text: str | None) -> list[str]:
    """Split a comma/semicolon character string into unique names."""
    if not text:
        return []
    parts = re.split(r'[,;]', str(text))
    seen = set()
    names = []
    for part in parts:
        name = ' '.join(part.strip().split())
        if not name:
            continue
        name = name[:200]
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def sync_character_mentions(comic) -> list[CharacterMention]:
    """Replace mention rows from the comic's characters text."""
    if comic.id is None:
        db.session.flush()
    if comic.id is None:
        raise RuntimeError('Comic must be flushed before syncing character mentions.')

    names = parse_character_names(comic.characters)
    CharacterMention.query.filter_by(comic_id=comic.id).delete(synchronize_session=False)
    db.session.expire(comic, ['character_mentions'])

    created = []
    for name in names:
        mention = CharacterMention(
            user_id=comic.user_id,
            comic_id=comic.id,
            name=name,
        )
        db.session.add(mention)
        created.append(mention)
    return created


def top_characters_for_user(user_id: int, limit: int = 5) -> list[tuple[str, int]]:
    """Most frequent owned-collection character names for a user."""
    rows = (
        db.session.query(
            func.min(CharacterMention.name).label('name'),
            func.count(CharacterMention.id).label('count'),
        )
        .join(Comic, Comic.id == CharacterMention.comic_id)
        .filter(
            CharacterMention.user_id == user_id,
            Comic.user_id == user_id,
            Comic.is_wishlist.is_(False),
        )
        .group_by(func.lower(CharacterMention.name))
        .order_by(func.count(CharacterMention.id).desc(), func.min(CharacterMention.name).asc())
        .limit(limit)
        .all()
    )
    return [(row.name, row.count) for row in rows]
