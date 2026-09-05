"""Tests for the reader page cache, CBR handling, and continue-reading."""

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app import create_app, db
from app.models import Comic, ComicFile, ReadingProgress, User
from app.services import page_cache
from app.services.archives import (
    ArchiveError,
    ArchiveToolMissingError,
    format_for_filename,
    rar_support_available,
    validate_upload,
)


def _png_bytes(color='white', size=(30, 40)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, format='PNG')
    return buf.getvalue()


def _make_cbz(pages, name='sample.cbz'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for member, data in pages:
            zf.writestr(member, data)
    buf.seek(0)
    buf.filename = name
    return buf


@pytest.fixture
def cache_app(tmp_path):
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'DIGITAL_FOLDER': str(tmp_path / 'digital'),
        'COVERS_FOLDER': str(tmp_path / 'covers'),
        'READER_CACHE_DIR': str(tmp_path / 'reader_cache'),
        'READER_CACHE_SIZE_LIMIT': 8 * 1024 * 1024,
    })
    with application.app_context():
        db.create_all()
        yield application
        page_cache.reset_for_tests()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def cache_client(cache_app):
    return cache_app.test_client()


@pytest.fixture
def cache_user_id(cache_app):
    with cache_app.app_context():
        user = User(username='cachereader', email='cachereader@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess.clear()
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _comic_with_cbz(app, client, user_id, pages=3, title='Cached #1',
                    issue_number='1', series=None):
    with app.app_context():
        comic = Comic(
            title=title,
            series=series,
            issue_number=issue_number,
            publisher='Test',
            user_id=user_id,
        )
        db.session.add(comic)
        db.session.commit()
        comic_id = comic.id

    members = [
        (f'{i:03d}.png', _png_bytes(color=(10 * i, 20, 30)))
        for i in range(1, pages + 1)
    ]
    client.post(
        f'/reader/{comic_id}/upload',
        data={'digital_file': (_make_cbz(members), 'sample.cbz')},
        content_type='multipart/form-data',
    )
    return comic_id


class TestFormatDetection:
    def test_format_for_filename(self):
        assert format_for_filename('book.cbz') == 'cbz'
        assert format_for_filename('book.ZIP') == 'cbz'
        assert format_for_filename('book.cbr') == 'cbr'
        assert format_for_filename('book.RAR') == 'cbr'

    def test_rejects_other_extensions(self):
        with pytest.raises(ArchiveError):
            format_for_filename('notes.txt')
        with pytest.raises(ArchiveError):
            format_for_filename('book.pdf')


class TestCbrSupport:
    @pytest.mark.skipif(rar_support_available(), reason='A RAR tool is installed here')
    def test_cbr_upload_reports_missing_tool(self, cache_app, cache_client, cache_user_id):
        with cache_app.app_context():
            comic = Comic(
                title='Rar #1',
                issue_number='1',
                publisher='Test',
                user_id=cache_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login(cache_client, cache_user_id)
        resp = cache_client.post(
            f'/reader/{comic_id}/upload',
            data={'digital_file': (io.BytesIO(b'Rar!\x1a\x07\x00fake'), 'book.cbr')},
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b'unrar' in resp.data or b'rarfile' in resp.data
        with cache_app.app_context():
            assert ComicFile.query.filter_by(comic_id=comic_id).count() == 0

    @pytest.mark.skipif(rar_support_available(), reason='A RAR tool is installed here')
    def test_validate_upload_raises_tool_missing(self, cache_app):
        stream = io.BytesIO(b'Rar!\x1a\x07\x00fake')
        stream.filename = 'book.cbr'
        with cache_app.app_context():
            with pytest.raises(ArchiveToolMissingError):
                validate_upload(stream)


class TestPageCache:
    def test_second_request_is_served_from_cache(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id)

        first = cache_client.get(f'/reader/{comic_id}/page/1')
        assert first.status_code == 200
        assert first.headers['X-Page-Cache'] == 'miss'

        second = cache_client.get(f'/reader/{comic_id}/page/1')
        assert second.status_code == 200
        assert second.headers['X-Page-Cache'] == 'hit'
        assert second.data == first.data

    def test_cached_page_survives_archive_deletion(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id)

        warm = cache_client.get(f'/reader/{comic_id}/page/2')
        assert warm.status_code == 200

        # Remove the archive from disk; the cached page should still serve.
        with cache_app.app_context():
            comic_file = ComicFile.query.filter_by(comic_id=comic_id).one()
            Path(cache_app.config['DIGITAL_FOLDER'], comic_file.storage_path).unlink()

        cached = cache_client.get(f'/reader/{comic_id}/page/2')
        assert cached.status_code == 200
        assert cached.headers['X-Page-Cache'] == 'hit'
        assert cached.data == warm.data

    def test_etag_returns_304(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id)

        first = cache_client.get(f'/reader/{comic_id}/page/1')
        etag = first.headers.get('ETag')
        assert etag

        again = cache_client.get(
            f'/reader/{comic_id}/page/1',
            headers={'If-None-Match': etag},
        )
        assert again.status_code == 304

    def test_replacing_archive_evicts_cached_pages(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id)

        original = cache_client.get(f'/reader/{comic_id}/page/1')
        assert original.status_code == 200

        replacement = _make_cbz([('001.png', _png_bytes(color=(200, 5, 5)))])
        cache_client.post(
            f'/reader/{comic_id}/upload',
            data={'digital_file': (replacement, 'replacement.cbz')},
            content_type='multipart/form-data',
        )

        after = cache_client.get(f'/reader/{comic_id}/page/1')
        assert after.status_code == 200
        assert after.headers['X-Page-Cache'] == 'miss'
        assert after.data != original.data

        with cache_app.app_context():
            comic_file = ComicFile.query.filter_by(comic_id=comic_id).one()
            assert comic_file.page_count == 1
            assert comic_file.original_filename == 'replacement.cbz'

    def test_removing_file_evicts_cache_and_page_404s(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id)
        assert cache_client.get(f'/reader/{comic_id}/page/1').status_code == 200

        cache_client.post(f'/reader/{comic_id}/file')

        assert cache_client.get(f'/reader/{comic_id}/page/1').status_code == 404
        with cache_app.app_context():
            assert ComicFile.query.filter_by(comic_id=comic_id).count() == 0

    def test_cache_is_capped_by_size_limit(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id, pages=4)
        for page in range(1, 5):
            assert cache_client.get(f'/reader/{comic_id}/page/{page}').status_code == 200

        with cache_app.app_context():
            info = page_cache.stats()
            assert info['volume'] <= info['size_limit']
            assert info['count'] >= 1


class TestContinueReading:
    def test_dashboard_shows_in_progress_comic(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id, title='Halfway #7')

        cache_client.post(f'/reader/{comic_id}/progress', json={'page': 2})

        resp = cache_client.get('/dashboard')
        assert resp.status_code == 200
        assert b'Continue Reading' in resp.data
        assert b'Halfway #7' in resp.data
        assert b'Page 2 of 3' in resp.data

    def test_finished_comic_is_not_listed(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        comic_id = _comic_with_cbz(cache_app, cache_client, cache_user_id, title='Done #9')

        cache_client.post(f'/reader/{comic_id}/progress', json={'page': 3})

        resp = cache_client.get('/dashboard')
        assert resp.status_code == 200
        # Only comic has progress, and it is finished, so the whole panel is hidden.
        assert b'Continue Reading' not in resp.data
        with cache_app.app_context():
            progress = ReadingProgress.query.filter_by(comic_id=comic_id).one()
            assert progress.page_number == 3


class TestReadingQueue:
    def test_unread_and_next_issue_on_dashboard(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        current_id = _comic_with_cbz(
            cache_app, cache_client, cache_user_id,
            title='ASM #5', issue_number='5', series='Amazing Spider-Man',
        )
        next_id = _comic_with_cbz(
            cache_app, cache_client, cache_user_id,
            title='ASM #6', issue_number='6', series='Amazing Spider-Man',
        )
        unread_id = _comic_with_cbz(
            cache_app, cache_client, cache_user_id,
            title='Daredevil #1', issue_number='1', series='Daredevil',
        )

        cache_client.post(f'/reader/{current_id}/progress', json={'page': 2})

        resp = cache_client.get('/dashboard')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Continue Reading' in html
        assert 'ASM #5' in html
        assert 'Up Next' in html
        assert 'ASM #6' in html
        assert 'After Amazing Spider-Man #5' in html
        assert 'Unread Digital' in html
        assert 'Daredevil #1' in html
        assert f'/reader/{next_id}' in html
        assert f'/reader/{unread_id}' in html

    def test_finished_next_issue_is_skipped(self, cache_app, cache_client, cache_user_id):
        _login(cache_client, cache_user_id)
        current_id = _comic_with_cbz(
            cache_app, cache_client, cache_user_id,
            title='Run #1', issue_number='1', series='Run',
        )
        _comic_with_cbz(
            cache_app, cache_client, cache_user_id,
            title='Run #2', issue_number='2', series='Run', pages=2,
        )
        later_id = _comic_with_cbz(
            cache_app, cache_client, cache_user_id,
            title='Run #3', issue_number='3', series='Run',
        )

        with cache_app.app_context():
            mid = Comic.query.filter_by(user_id=cache_user_id, issue_number='2').one()
            mid_id = mid.id
        cache_client.post(f'/reader/{current_id}/progress', json={'page': 2})
        cache_client.post(f'/reader/{mid_id}/progress', json={'page': 2})

        resp = cache_client.get('/dashboard')
        html = resp.data.decode()
        assert 'Up Next' in html
        assert 'After Run #1' in html
        assert 'Run #3' in html
        assert f'/reader/{later_id}' in html
        up_next = html.split('Up Next', 1)[1].split('Recent Additions', 1)[0]
        assert 'Run #3' in up_next
        assert 'Run #2' not in up_next
