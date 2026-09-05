---
name: comic-ownership-covers
description: Enforce ComicbookMgr ownership filters, cover storage, and CSRF rules. Use when adding or changing comic queries, cover uploads, variants, JSON mutations, reader file access, or delete/edit routes.
---

# Comic ownership and covers

## Ownership

Every comic read or write is scoped to the signed-in user:

```python
comic = Comic.query.filter_by(id=comic_id, user_id=current_user.id).first_or_404()
```

Never `Comic.query.get(id)` or `db.session.get(Comic, id)` on a user-facing route. The same rule applies to `ComicFile`, `ComicCover`, and `ReadingProgress`.

Admin series catalog (`Series`, `SeriesIssue`) is global. User-owned comics are not.

## List queries

Defer BLOBs. Do not pull `cover_image` or `additional_covers` into grids:

```python
.query.options(
    defer(Comic.cover_image),
    defer(Comic.additional_covers),
    with_expression(
        Comic.cover_available,
        db.or_(Comic.cover_image_path.isnot(None), Comic.cover_image.isnot(None)),
    ),
)
```

Serve images through `comics.serve_cover_image` / `serve_cover_variant_image` (and their thumbnail routes) with `comic.cover_version()` / `cover.image_version()`. Use `list_cover_summaries()` or `get_additional_covers()` (Base64 is opt-in via `include_blob=True`). Do not embed Base64 in collection or show HTML.

`persist_primary_cover` / `persist_variant_cover` write a sibling `*_thumb.webp` (~300px). Thumbnail routes serve that file, generating it on first request if the cover predates the change. `delete_cover_file` removes the thumb with the cover.

## Writing covers

Use `app/services/cover_storage.py`:

- `persist_primary_cover` / `persist_variant_cover`
- `get_primary_cover_bytes` / `get_variant_cover_bytes` (filesystem first, BLOB fallback)
- Validate bytes with `_validated_cover_image` in `app/comics/helpers.py`

Do not write `comic.cover_image = raw_bytes` as the only store. Keep `COVERS_KEEP_BLOB` behavior; do not invent a third storage path. After `scripts/migrate_covers_to_filesystem.py` has run and URL-served covers look correct, `COVERS_KEEP_BLOB=false` is the planned production setting.

## CSRF

Browser JSON posts need `X-CSRFToken` from `<meta name="csrf-token">`. If a mutation accepts JSON, add a CSRF test. Logout is GET; other mutations are POST.

## Tests

Ownership regressions go in `tests/test_ownership.py`. Cover I/O goes in `tests/test_cover_storage.py`. Do not SFTP or commit `instance/comicbook.db` to "fix" a test.
