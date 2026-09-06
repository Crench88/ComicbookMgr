---
name: flask-ui-verify
description: Verify ComicbookMgr UI changes across collection, dashboard, form, show, and reader. Use when editing templates, style.css, script.js, or any state shared between those pages.
---

# Flask UI verify

A screenshot of one page is not done. Walk the flow a user would.

## Shared state

If you change how a comic is saved, filtered, or returned:

1. My Comics (`comics.index`) — series sidebar, cover grid, filters, return `next`
2. Wishlist (`comics.wishlist`) if ownership/wishlist flags changed
3. Dashboard — counts, top characters (from `character_mention`), recent covers, Continue Reading, Up Next, Unread Digital
4. Show + Edit — same comic, same cover version, back-to-collection URL
5. Reader if digital file or progress changed

`_collection_return_url` / `next` must survive add, edit, delete, and cover AJAX.

`comics.index` must pass every filter the template reads: `search_query`, publisher/condition/genre, `tag_filter`, `read_status_filter`, `available_tags`, `wishlist_only`, `sort_by`, `series_gaps`. Sidebar grouping uses `_series_group_sql()` (catalog `display_name`, then `Comic.series`). Keep `apply_series_link` / `sync_owned_comics_series_text` writing the same label onto `Comic.series`. Gap banners compare the current user's owned (non-wishlist) issues to `SeriesIssue`; **Add missing** opens Bulk Add with `?tab=bulk&series=&issues=`.

## Layout

- Desktop: collection is sidebar + grid. Do not break `--collection-sidebar-top` or the sticky filter bar.
- Check a ~375px width when the change touches nav, filters, or the series list.
- Themes: light and dark tokens live in `app/static/css/style.css`. Prefer tokens, not raw Bootstrap blues.
- Authenticated nav is Dashboard, My Comics, Add, and admin items. Wishlist is a My Comics filter (`Wishlist only` + Open wishlist), not a top-level item. Import/Export live in the account menu only. Admin **Backup** is under Comic Admin; cleanup must never remove `instance/comicbook.db` or `instance/covers/`.
- Show page leads with cover, read/edit, credits, and variants. UPC, ownership sliders, ComicVine IDs, and dates stay in `comic-show-disclosure` details.

## Forms and JS

JSON fetch needs `X-CSRFToken`. After idle timeout, authenticated pages redirect to login — do not add a second remember-me cookie.

Cover variants and ComicVine search live in `app/templates/comics/partials/_form_scripts.html`. Keep series/issue/volume hidden fields (`catalogSeriesId`, `comicvineVolumeId`, `comicvineIssueId`) wired.

## How to verify

Prefer the browser tools against the running Flask app. If they are unavailable, use the test client plus a targeted pytest module (`tests/test_app.py`, `tests/test_ownership.py`, `tests/test_cover_storage.py`). Say what you could not click.
