"""
Extract comic cover BLOBs onto the filesystem.

Usage:
    python scripts/migrate_covers_to_filesystem.py
    python scripts/migrate_covers_to_filesystem.py --clear-blobs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app, db
from app.models import Comic
from app.services.cover_storage import migrate_comic_covers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--clear-blobs',
        action='store_true',
        help='Remove SQLite BLOB copies after files are written (saves DB size).',
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        comics = Comic.query.order_by(Comic.id.asc()).all()
        primary = variants = 0
        for comic in comics:
            stats = migrate_comic_covers(comic, clear_blobs=args.clear_blobs)
            primary += stats['primary']
            variants += stats['variants']
        db.session.commit()
        print(
            f'Migrated covers for {len(comics)} comic(s): '
            f'{primary} primary, {variants} variant file(s).'
        )
        if args.clear_blobs:
            print('BLOB copies cleared where filesystem paths exist.')


if __name__ == '__main__':
    main()
