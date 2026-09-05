---
name: comicvine-credits-series
description: Keep ComicVine credits, series linking, and issue metadata in sync with ComicbookMgr models. Use when changing ComicVine import, bulk add, credit fields, series/volume pickers, or catalog SeriesIssue data.
---

# ComicVine credits and series

## Credits

`Comic.CREDIT_FIELDS` in `app/models.py` is the single list of creator columns. Add a credit in that tuple first, then the form field, then ComicVine mapping in `app/services/comicvine.py`. Do not add a one-off writer/artist field on a template.

`artist` is only ComicVine's literal `artist` role. Pencilers and inkers have their own columns. Unmapped roles go in `other_credits`.

## Series vs issue

- `series` — free-text label for grouping
- `series_id` — FK to catalog `Series`
- `issue_title` — story title
- `title` — display title (often `Series: IssueTitle #N`)

Link through `app/services/series_link.py` (`apply_series_link`). Do not set `series_id` from an unsanitized form int without resolving the `Series` row.

The collection sidebar groups on the free-text `Comic.series` column. `comic.series_label` prefers `catalog_series.display_name`. After linking, keep `Comic.series` in sync with the catalog display name or the sidebar and Back-to-collection URL will disagree.

## Catalog

`Series` + `SeriesIssue` are the canonical run. Owned comics may point at a series but can also exist unmatched. Gap reports should compare `SeriesIssue.issue_number` to the current user's comics for that `series_id`, still filtered by `user_id`.

ComicVine volume id lives on `Series.comicvine_volume_id`. Issue id lives on `Comic.comicvine_issue_id` and `SeriesIssue.comicvine_issue_id`.

## Characters

`Comic.characters` stays a comma-separated text field. `sync_character_mentions(comic)` writes `character_mention` rows used by the dashboard. Call it after any write that changes `characters` (form save, ComicVine refresh, bulk add, CSV import). Do not count characters by splitting the text column in Python.

## Covers from ComicVine

Download through `app/services/safe_http.py` (`fetch_public_image`). Never `requests.get` a cover URL directly. Persist with `cover_storage`, not by stuffing a BLOB into the form only.

## Tests

Metadata: `tests/test_comicvine_metadata.py`. Covers: `tests/test_comicvine_covers.py`. Volume search: `tests/test_volume_search.py`. Series link: `tests/test_series_link.py`.
