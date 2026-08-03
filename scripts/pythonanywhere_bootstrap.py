#!/usr/bin/env python3
"""
One-time setup on PythonAnywhere after cloning the repo.

Usage (from the project root, with venv activated):

  python scripts/pythonanywhere_bootstrap.py \\
    --username admin \\
    --email you@example.com \\
    --password 'choose-a-strong-password'
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from dotenv import load_dotenv

    env_path = project_root / '.env'
    load_dotenv(env_path)

    parser = argparse.ArgumentParser(description='Bootstrap ComicbookMgr on PythonAnywhere')
    parser.add_argument('--username', default='admin')
    parser.add_argument('--email', required=True)
    parser.add_argument('--password', required=True)
    args = parser.parse_args()

    if env_path.exists():
        # Ignore comments; only flag real leftover path placeholders.
        for line in env_path.read_text(encoding='utf-8').splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if 'YOUR_USERNAME' in stripped:
                print(
                    'ERROR: .env still contains YOUR_USERNAME in a setting.\n'
                    'Recreate it from the template:\n'
                    '  cp env.pythonanywhere.example .env\n'
                    '  nano .env   # set SECRET_KEY (and API keys); keep relative paths'
                )
                return 1

    if os.environ.get('FLASK_ENV', '').lower() != 'production':
        print('Warning: FLASK_ENV is not production. Continuing anyway.')

    from app import create_app, db
    from app.models import User

    app = create_app()
    with app.app_context():
        for key in ('UPLOAD_FOLDER', 'COVERS_FOLDER', 'DIGITAL_FOLDER', 'READER_CACHE_DIR'):
            path = app.config.get(key)
            if path:
                Path(path).mkdir(parents=True, exist_ok=True)
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        cache_dir = app.config.get('CACHE_DIR')
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)

        from flask_migrate import upgrade

        upgrade()

        existing = User.query.filter_by(username=args.username).first()
        if existing:
            print(f'User {args.username!r} already exists — leaving password unchanged.')
        else:
            user = User(
                username=args.username,
                email=args.email,
                is_active=True,
                is_admin=True,
            )
            user.set_password(args.password)
            db.session.add(user)
            db.session.commit()
            print(f'Created admin user {args.username!r} ({args.email}).')

    print('Bootstrap complete. Reload the web app in the PythonAnywhere Web tab.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
