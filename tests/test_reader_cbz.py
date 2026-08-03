"""Tests for CBZ digital reader MVP."""

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app import create_app, db
from app.models import Comic, ComicFile, ReadingProgress, User
from app.services.archives import list_cbz_pages, natural_sort_key


def _png_bytes(color='white', size=(40, 60)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, format='PNG')
    return buf.getvalue()


def _make_cbz(pages):
    """pages: list of (member_name, bytes)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in pages:
            zf.writestr(name, data)
    buf.seek(0)
    return buf


@pytest.fixture
def reader_app(tmp_path):
    digital = tmp_path / 'digital'
    digital.mkdir()
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'DIGITAL_FOLDER': str(digital),
        'COVERS_FOLDER': str(tmp_path / 'covers'),
    })
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def reader_client(reader_app):
    return reader_app.test_client()


@pytest.fixture
def reader_user_id(reader_app):
    with reader_app.app_context():
        user = User(username='reader', email='reader@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess.clear()
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _comic(app, user_id, title='Digital #1'):
    with app.app_context():
        comic = Comic(
            title=title,
            issue_number='1',
            publisher='Test',
            user_id=user_id,
        )
        db.session.add(comic)
        db.session.commit()
        return comic.id


class TestArchiveHelpers:
    def test_natural_sort(self):
        names = ['page10.png', 'page2.png', 'page1.png']
        assert sorted(names, key=natural_sort_key) == ['page1.png', 'page2.png', 'page10.png']

    def test_list_cbz_pages_skips_non_images(self, tmp_path):
        archive = tmp_path / 'sample.cbz'
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr('readme.txt', 'hello')
            zf.writestr('page2.png', _png_bytes('blue'))
            zf.writestr('page1.png', _png_bytes('red'))
            zf.writestr('__MACOSX/._page1.png', b'junk')
        pages = list_cbz_pages(archive)
        assert pages == ['page1.png', 'page2.png']


class TestReaderFlow:
    def test_upload_read_progress(self, reader_client, reader_app, reader_user_id):
        client = reader_client
        app = reader_app
        user_id = reader_user_id
        comic_id = _comic(app, user_id)
        _login(client, user_id)

        cbz = _make_cbz([
            ('003.png', _png_bytes('green')),
            ('001.png', _png_bytes('red')),
            ('002.png', _png_bytes('blue')),
        ])
        resp = client.post(
            f'/reader/{comic_id}/upload',
            data={'digital_file': (cbz, 'sample.cbz')},
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b'Read' in resp.data
        assert b'sample.cbz' in resp.data

        with app.app_context():
            comic_file = ComicFile.query.filter_by(comic_id=comic_id).one()
            assert comic_file.page_count == 3
            assert comic_file.format == 'cbz'
            assert Path(app.config['DIGITAL_FOLDER'], comic_file.storage_path).is_file()

        read_resp = client.get(f'/reader/{comic_id}')
        assert read_resp.status_code == 200
        # Element ids the reader JS binds to.
        for element_id in (b'readerShell', b'readerPageImage', b'readerSlider', b'spreadToggle'):
            assert element_id in read_resp.data

        page1 = client.get(f'/reader/{comic_id}/page/1')
        assert page1.status_code == 200
        assert page1.data == _png_bytes('red')

        page3 = client.get(f'/reader/{comic_id}/page/3')
        assert page3.status_code == 200
        assert page3.data == _png_bytes('green')

        progress_resp = client.post(
            f'/reader/{comic_id}/progress',
            json={'page': 2},
        )
        assert progress_resp.status_code == 200
        assert progress_resp.get_json()['page'] == 2

        with app.app_context():
            progress = ReadingProgress.query.filter_by(
                user_id=user_id,
                comic_id=comic_id,
            ).one()
            assert progress.page_number == 2
            comic = db.session.get(Comic, comic_id)
            assert comic.read_status == 'reading'

        client.post(f'/reader/{comic_id}/progress', json={'page': 3})
        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.read_status == 'read'

    def test_rejects_non_cbz(self, reader_client, reader_app, reader_user_id):
        client = reader_client
        app = reader_app
        user_id = reader_user_id
        comic_id = _comic(app, user_id, title='No File')
        _login(client, user_id)
        resp = client.post(
            f'/reader/{comic_id}/upload',
            data={'digital_file': (io.BytesIO(b'not-a-zip'), 'notes.txt')},
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b'Only .cbz' in resp.data or b'valid CBZ' in resp.data or b'CBZ' in resp.data

    def test_other_user_cannot_read(self, reader_client, reader_app, reader_user_id):
        from flask_login import login_user
        from werkzeug.exceptions import NotFound

        from app.reader.routes import _owned_comic

        client = reader_client
        app = reader_app
        user_id = reader_user_id
        comic_id = _comic(app, user_id)
        _login(client, user_id)
        cbz = _make_cbz([('1.png', _png_bytes())])
        client.post(
            f'/reader/{comic_id}/upload',
            data={'digital_file': (cbz, 'x.cbz')},
            content_type='multipart/form-data',
        )

        with app.app_context():
            other = User(username='other', email='other@example.com')
            other.set_password('password123')
            db.session.add(other)
            db.session.commit()
            other_id = other.id

        # Authorize via request context + login_user (avoids cross-test
        # Flask-Login session sticky state when the full suite runs).
        with app.test_request_context(f'/reader/{comic_id}'):
            other = db.session.get(User, other_id)
            login_user(other)
            with pytest.raises(NotFound):
                _owned_comic(comic_id)

    def test_delete_comic_removes_digital_file(self, reader_client, reader_app, reader_user_id):
        client = reader_client
        app = reader_app
        user_id = reader_user_id
        comic_id = _comic(app, user_id)
        _login(client, user_id)
        cbz = _make_cbz([('1.png', _png_bytes())])
        client.post(
            f'/reader/{comic_id}/upload',
            data={'digital_file': (cbz, 'gone.cbz')},
            content_type='multipart/form-data',
        )
        with app.app_context():
            storage = ComicFile.query.filter_by(comic_id=comic_id).one().storage_path
            absolute = Path(app.config['DIGITAL_FOLDER']) / storage
            assert absolute.is_file()

        client.post(f'/comics/{comic_id}/delete')
        with app.app_context():
            assert db.session.get(Comic, comic_id) is None
            assert ComicFile.query.filter_by(comic_id=comic_id).count() == 0
            assert not absolute.exists()
