---
name: pythonanywhere-deploy
description: Deploy ComicbookMgr to PythonAnywhere from deploy/pythonanywhere. Use when the user asks to ship, pull, reload, SFTP the database, run flask db upgrade, or update the hosted site.
---

# PythonAnywhere deploy

## Branch

Hosted site tracks `deploy/pythonanywhere`. Do not tell the user to pull `master`.

```bash
cd ~/ComicbookMgr
source venv/bin/activate
git pull origin deploy/pythonanywhere
```

Then **Web → Reload**. Install deps only when `requirements-pythonanywhere.txt` or `requirements.txt` changed:

```bash
pip install -r requirements-pythonanywhere.txt
```

WSGI entry is `pythonanywhere_wsgi.py`. If Flask CLI cannot find the app: `export FLASK_APP=pythonanywhere_wsgi:application`.

## Database

`flask db upgrade` only when this change added or altered SQLAlchemy columns/tables/indexes.

The `(user_id, is_wishlist)` index (`p6k1g2h3i4j5`) and `character_mention` plus `ix_comic_user_id` (`q7l2m3n4o5p6`) are schema changes — run `flask db upgrade` on PythonAnywhere. Still do **not** SFTP the live DB unless replacing the collection. The mentions migration backfills from existing `Comic.characters` text.

**Idle logoff and most UI work are not schema changes.** Do not SFTP `instance/comicbook.db` for those.

SFTP/upload the live DB only when the user explicitly wants to **replace** the hosted collection with the PC copy:

1. Local file: `instance/comicbook.db`
2. Files tab: `/home/USER/ComicbookMgr/instance/comicbook.db`
3. Upload matching `instance/covers/` if covers are filesystem-backed
4. `flask db upgrade` if the code expects newer columns
5. Web → Reload

Never commit `.env` or the live SQLite file as the deploy method.

Admin **Backup** builds a zip in `instance/backups/` (SQLite snapshot + `covers/` + `digital/`). Download it in the browser, then confirm cleanup — that deletes only the temp zip, never the live DB or cover folders. Do not leave old zips in `~/ComicbookMgr/instance/backups/` on the free disk quota.

## Env

Template: `env.pythonanywhere.example`. Idle window: `IDLE_TIMEOUT_SECONDS=1800` (optional; code defaults to 1800). `SECRET_KEY` must be set in production.

## After reload

Hit login, one collection page, and one admin page if roles changed. Check **Web → Error log** (newest lines at the bottom) if the site errors.

Full first-time setup: `PYTHONANYWHERE_DEPLOYMENT.md`.
