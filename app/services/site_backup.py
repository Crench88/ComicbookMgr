"""Admin one-click backup of the SQLite database, covers, and digital files."""

from __future__ import annotations

import re
import sqlite3
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

from .. import db

BACKUP_NAME_RE = re.compile(r'^comicbook-backup-\d{8}-\d{6}\.zip$')


class BackupError(ValueError):
    """Invalid backup filename or path."""


def backups_root() -> Path:
    configured = current_app.config.get('BACKUPS_FOLDER')
    if configured:
        root = Path(configured)
    else:
        root = Path(current_app.instance_path) / 'backups'
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def safe_backup_path(filename: str) -> Path:
    name = Path(filename or '').name
    if not BACKUP_NAME_RE.fullmatch(name):
        raise BackupError('Invalid backup filename.')
    root = backups_root()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise BackupError('Invalid backup filename.') from exc
    return path


def list_backup_zips() -> list[dict]:
    items = []
    for path in sorted(backups_root().glob('comicbook-backup-*.zip'), reverse=True):
        if not BACKUP_NAME_RE.fullmatch(path.name) or not path.is_file():
            continue
        items.append({
            'filename': path.name,
            'size_bytes': path.stat().st_size,
            'size_label': format_bytes(path.stat().st_size),
        })
    return items


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            if unit == 'B':
                return f'{int(value)} {unit}'
            return f'{value:.1f} {unit}'
        value /= 1024
    return f'{size} B'


def create_site_backup() -> dict:
    """Write a zip under instance/backups/. Does not modify production files."""
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    filename = f'comicbook-backup-{stamp}.zip'
    zip_path = safe_backup_path(filename)
    work = zip_path.with_suffix('.building')
    if work.exists():
        work.unlink()

    included = []
    snapshot = None
    try:
        snapshot = _snapshot_sqlite(zip_path.parent / f'.db-{stamp}.sqlite')
        cover_count = _count_files(_covers_dir())
        digital_count = _count_files(_digital_dir())
        manifest = _manifest_text(cover_count, digital_count)

        with zipfile.ZipFile(work, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('MANIFEST.txt', manifest)
            if snapshot and snapshot.is_file():
                zf.write(snapshot, 'comicbook.db')
                included.append('comicbook.db')
            covers = _add_tree(zf, _covers_dir(), 'covers')
            if covers:
                included.append(f'covers ({covers} file{"s" if covers != 1 else ""})')
            digital = _add_tree(zf, _digital_dir(), 'digital')
            if digital:
                included.append(f'digital ({digital} file{"s" if digital != 1 else ""})')

        work.replace(zip_path)
    except Exception:
        if work.exists():
            work.unlink()
        raise
    finally:
        if snapshot and snapshot.exists():
            snapshot.unlink()

    return {
        'filename': filename,
        'size_bytes': zip_path.stat().st_size,
        'size_label': format_bytes(zip_path.stat().st_size),
        'included': included,
    }


def delete_backup_zip(filename: str) -> str:
    """Delete one temp zip from the backups folder only."""
    path = safe_backup_path(filename)
    if not path.is_file():
        raise BackupError('That backup file is not on the server.')
    last_error = None
    for attempt in range(5):
        try:
            path.unlink()
            return path.name
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.15)
    raise BackupError('Could not delete the temporary zip; try again in a moment.') from last_error


def delete_all_backup_zips() -> int:
    removed = 0
    errors = []
    for item in list_backup_zips():
        try:
            delete_backup_zip(item['filename'])
            removed += 1
        except BackupError as exc:
            errors.append(str(exc))
    if errors and not removed:
        raise BackupError(errors[0])
    return removed


def _covers_dir() -> Path:
    return Path(current_app.config.get('COVERS_FOLDER') or (
        Path(current_app.instance_path) / 'covers'
    ))


def _digital_dir() -> Path:
    return Path(current_app.config.get('DIGITAL_FOLDER') or (
        Path(current_app.instance_path) / 'digital'
    ))


def _count_files(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for path in folder.rglob('*') if path.is_file())


def _add_tree(zf: zipfile.ZipFile, source: Path, arc_prefix: str) -> int:
    if not source.is_dir():
        return 0
    source = source.resolve()
    backup_root = backups_root()
    count = 0
    for path in source.rglob('*'):
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(backup_root)
        except ValueError:
            pass
        else:
            continue
        rel = path.relative_to(source).as_posix()
        zf.write(resolved, f'{arc_prefix}/{rel}')
        count += 1
    return count


def _sqlite_file_path() -> Path | None:
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return None
    if ':memory:' in uri:
        return None
    if uri.startswith('sqlite:////'):
        return Path('/' + uri[len('sqlite:////'):])
    if uri.startswith('sqlite:///'):
        return Path(uri[len('sqlite:///'):])
    return None


def _snapshot_sqlite(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    live = _sqlite_file_path()
    if live and live.is_file():
        source = sqlite3.connect(str(live.resolve()))
        try:
            source.execute('VACUUM INTO ?', (str(dest),))
        finally:
            source.close()
        return dest

    raw = db.engine.raw_connection()
    try:
        sqlite_conn = getattr(raw, 'driver_connection', raw)
        dest_conn = sqlite3.connect(str(dest))
        try:
            sqlite_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        raw.close()
    return dest


def _manifest_text(cover_count: int, digital_count: int) -> str:
    created = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    lines = [
        'ComicbookMgr site backup',
        f'Created: {created}',
        '',
        'Included:',
        '- comicbook.db (SQLite snapshot; live file was not moved)',
        f'- covers/ ({cover_count} files, including WebP thumbs)',
        f'- digital/ ({digital_count} CBZ/CBR archives)',
        '',
        'Not included (regenerable or secret):',
        '- instance/backups/ (these temporary zips)',
        '- instance/reader_cache/',
        '- instance/cache/',
        '- .env and SECRET_KEY',
        '',
        'Restore: copy comicbook.db over instance/comicbook.db, unzip',
        'covers/ into instance/covers/, digital/ into instance/digital/,',
        'then reload the web app. Do not delete those production folders',
        'when you only meant to remove this zip.',
    ]
    return '\n'.join(lines) + '\n'
