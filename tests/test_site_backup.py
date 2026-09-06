"""Tests for the admin one-click site backup."""

import io
import re
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app import create_app, db
from app.models import Comic, User
from app.services.cover_storage import persist_primary_cover
from app.services.site_backup import create_site_backup, delete_backup_zip, safe_backup_path


def _jpeg_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (24, 32), (10, 20, 30)).save(buf, format='JPEG')
    return buf.getvalue()


@pytest.fixture
def app(tmp_path):
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'comicbook.db').replace('\\', '/'),
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'COVERS_FOLDER': str(tmp_path / 'covers'),
        'DIGITAL_FOLDER': str(tmp_path / 'digital'),
        'BACKUPS_FOLDER': str(tmp_path / 'backups'),
    })
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_ids(app):
    with app.app_context():
        admin = User(username='backupadmin', email='backup-admin@test.com', is_admin=True)
        admin.set_password('adminpass')
        regular = User(username='backupuser', email='backup-user@test.com', is_admin=False)
        regular.set_password('userpass')
        db.session.add_all([admin, regular])
        db.session.commit()
        return {'admin': admin.id, 'regular': regular.id}


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def test_backup_page_blocks_non_admin(client, user_ids):
    _login(client, user_ids['regular'])
    assert client.get('/admin/backup').status_code == 403


def test_backup_page_allows_admin(client, user_ids):
    _login(client, user_ids['admin'])
    page = client.get('/admin/backup')
    assert page.status_code == 200
    assert b'Create and download backup' in page.data
    assert b'instance/backups/' in page.data


def test_create_download_and_cleanup_leaves_production(client, app, user_ids, tmp_path):
    blob = _jpeg_bytes()
    digital_dir = Path(app.config['DIGITAL_FOLDER'])
    digital_dir.mkdir(parents=True, exist_ok=True)
    archive = digital_dir / 'issue1.cbz'
    archive.write_bytes(b'PK\x03\x04digital')

    with app.app_context():
        comic = Comic(
            title='Backup Comic',
            issue_number='1',
            publisher='Marvel',
            user_id=user_ids['admin'],
        )
        db.session.add(comic)
        db.session.flush()
        persist_primary_cover(comic, blob, 'image/jpeg')
        db.session.commit()
        live_db = Path(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        cover_path = Path(app.config['COVERS_FOLDER']) / comic.cover_image_path

    _login(client, user_ids['admin'])
    created = client.post('/admin/backup/create', json={})
    assert created.status_code == 200
    data = created.get_json()
    assert data['success'] is True
    filename = data['filename']
    assert filename.startswith('comicbook-backup-')
    assert 'comicbook.db' in data['included']
    assert any(item['filename'] == filename for item in data['leftover_backups'])

    downloaded = client.get(data['download_url'])
    assert downloaded.status_code == 200
    assert downloaded.content_type.startswith('application/zip')
    zip_bytes = downloaded.get_data()
    downloaded.close()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert 'MANIFEST.txt' in names
        assert 'comicbook.db' in names
        assert any(name.startswith('covers/') for name in names)
        assert any(name.endswith('issue1.cbz') for name in names)
        manifest = zf.read('MANIFEST.txt').decode()
        assert 'live file was not moved' in manifest

    assert live_db.is_file()
    assert cover_path.is_file()
    assert archive.is_file()

    cleaned = client.post('/admin/backup/cleanup', json={'filename': filename})
    assert cleaned.status_code == 200
    assert cleaned.get_json()['success'] is True
    with app.app_context():
        assert not safe_backup_path(filename).exists()
    assert live_db.is_file()
    assert cover_path.is_file()
    assert archive.is_file()


def test_cleanup_all_removes_temp_zips_only(client, app, user_ids):
    with app.app_context():
        comic = Comic(
            title='Cleanup All',
            issue_number='3',
            publisher='Marvel',
            user_id=user_ids['admin'],
        )
        db.session.add(comic)
        db.session.commit()

    _login(client, user_ids['admin'])
    first = client.post('/admin/backup/create', json={}).get_json()
    second = client.post('/admin/backup/create', json={}).get_json()
    live_db = Path(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))

    cleaned = client.post('/admin/backup/cleanup', json={'all': True})
    assert cleaned.status_code == 200
    data = cleaned.get_json()
    assert data['success'] is True
    assert data['leftover_backups'] == []
    with app.app_context():
        assert not safe_backup_path(first['filename']).exists()
        assert not safe_backup_path(second['filename']).exists()
    assert live_db.is_file()


def test_cleanup_rejects_path_escape(client, user_ids, app):
    _login(client, user_ids['admin'])
    response = client.post('/admin/backup/cleanup', json={'filename': '../comicbook.db'})
    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_non_admin_cannot_create_backup(client, user_ids):
    _login(client, user_ids['regular'])
    assert client.post('/admin/backup/create', json={}).status_code == 403


def test_json_backup_requires_csrf(tmp_path):
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'csrf.db').replace('\\', '/'),
        'WTF_CSRF_ENABLED': True,
        'SECRET_KEY': 'csrf-backup-secret',
        'BACKUPS_FOLDER': str(tmp_path / 'backups'),
        'COVERS_FOLDER': str(tmp_path / 'covers'),
        'DIGITAL_FOLDER': str(tmp_path / 'digital'),
    })
    with application.app_context():
        db.create_all()
        admin = User(username='csrfadmin', email='csrf-admin@test.com', is_admin=True)
        admin.set_password('adminpass')
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

        client = application.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_id)
            sess['_fresh'] = True

        assert client.post('/admin/backup/create', json={}).status_code == 400
        page = client.get('/admin/backup')
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
        created = client.post(
            '/admin/backup/create',
            json={},
            headers={'X-CSRFToken': token},
        )
        assert created.status_code == 200
        db.session.remove()
        db.drop_all()


def test_create_site_backup_helper(app, user_ids, tmp_path):
    with app.app_context():
        comic = Comic(
            title='Helper',
            issue_number='2',
            publisher='Marvel',
            user_id=user_ids['admin'],
        )
        db.session.add(comic)
        db.session.commit()
        payload = create_site_backup()
        path = safe_backup_path(payload['filename'])
        assert path.is_file()
        delete_backup_zip(payload['filename'])
        assert not path.exists()
