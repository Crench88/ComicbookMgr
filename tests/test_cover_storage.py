"""Tests for filesystem cover storage with BLOB fallback."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app import create_app, db
from app.models import Comic, ComicCover, User
from app.services.cover_storage import (
    get_primary_cover_bytes,
    migrate_comic_covers,
    persist_primary_cover,
    persist_variant_cover,
)


def _jpeg_bytes(color=(20, 40, 60), size=(32, 32)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, format='JPEG')
    return buf.getvalue()


@pytest.fixture
def app(tmp_path):
    covers = tmp_path / 'covers'
    covers.mkdir()
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'COVERS_FOLDER': str(covers),
        'COVERS_KEEP_BLOB': True,
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
def user_id(app):
    with app.app_context():
        user = User(username='coveruser', email='coveruser@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def test_persist_and_serve_primary_from_filesystem(client, app, user_id):
    blob = _jpeg_bytes()
    with app.app_context():
        comic = Comic(
            title='FS Cover',
            issue_number='1',
            publisher='Test',
            user_id=user_id,
        )
        db.session.add(comic)
        db.session.flush()
        persist_primary_cover(comic, blob, 'image/jpeg')
        db.session.commit()
        comic_id = comic.id
        rel = comic.cover_image_path
        covers_root = app.config['COVERS_FOLDER']

    assert rel
    assert (Path(covers_root) / rel).read_bytes() == blob

    with app.app_context():
        comic = db.session.get(Comic, comic_id)
        assert get_primary_cover_bytes(comic) == blob

    _login(client, user_id)
    resp = client.get(f'/comics/{comic_id}/cover')
    assert resp.status_code == 200
    assert resp.data == blob


def test_serve_falls_back_to_blob_when_path_missing(client, app, user_id):
    blob = _jpeg_bytes(color=(90, 10, 10))
    with app.app_context():
        comic = Comic(
            title='Blob Only',
            issue_number='2',
            publisher='Test',
            user_id=user_id,
            cover_image=blob,
            cover_image_mime='image/jpeg',
            cover_image_path=None,
        )
        db.session.add(comic)
        db.session.commit()
        comic_id = comic.id

    _login(client, user_id)
    resp = client.get(f'/comics/{comic_id}/cover')
    assert resp.status_code == 200
    assert resp.data == blob


def test_serve_prefers_filesystem_over_stale_blob(client, app, user_id):
    disk_blob = _jpeg_bytes(color=(1, 2, 3))
    stale_blob = _jpeg_bytes(color=(200, 200, 200))
    with app.app_context():
        comic = Comic(
            title='Prefer Disk',
            issue_number='3',
            publisher='Test',
            user_id=user_id,
            cover_image=stale_blob,
            cover_image_mime='image/jpeg',
        )
        db.session.add(comic)
        db.session.flush()
        persist_primary_cover(comic, disk_blob, 'image/jpeg')
        comic.cover_image = stale_blob
        db.session.commit()
        comic_id = comic.id

    _login(client, user_id)
    resp = client.get(f'/comics/{comic_id}/cover')
    assert resp.status_code == 200
    assert resp.data == disk_blob


def test_migrate_comic_covers_extracts_blobs(app, user_id):
    primary = _jpeg_bytes(color=(11, 22, 33))
    variant = _jpeg_bytes(color=(44, 55, 66))
    with app.app_context():
        comic = Comic(
            title='Migrate Me',
            issue_number='4',
            publisher='Test',
            user_id=user_id,
            cover_image=primary,
            cover_image_mime='image/jpeg',
        )
        db.session.add(comic)
        db.session.flush()
        db.session.add(ComicCover(
            comic_id=comic.id,
            image_data=variant,
            mime_type='image/jpeg',
            label='Variant A',
            position=1,
        ))
        db.session.commit()

        stats = migrate_comic_covers(comic, clear_blobs=False)
        db.session.commit()

        assert stats == {'primary': 1, 'variants': 1}
        assert comic.cover_image_path
        covers_root = Path(app.config['COVERS_FOLDER'])
        assert (covers_root / comic.cover_image_path).read_bytes() == primary
        assert comic.cover_image == primary
        assert comic.cover_variants[0].image_path
        assert (covers_root / comic.cover_variants[0].image_path).read_bytes() == variant


def _comic_with_variant(app, user_id, primary, variant):
    """Comic whose primary and one alternate cover both live on disk."""
    with app.app_context():
        comic = Comic(title='Switch Me', issue_number='11', publisher='Test', user_id=user_id)
        db.session.add(comic)
        db.session.flush()
        persist_primary_cover(comic, primary, 'image/jpeg')
        cover = ComicCover(comic_id=comic.id, label='Variant A', position=1)
        db.session.add(cover)
        db.session.flush()
        persist_variant_cover(cover, variant, 'image/jpeg', user_id=user_id, comic_id=comic.id)
        db.session.commit()
        return comic.id, cover.id


def test_set_primary_cover_serves_the_new_image(client, app, user_id):
    primary = _jpeg_bytes(color=(255, 0, 0))
    variant = _jpeg_bytes(color=(0, 0, 255))
    comic_id, cover_id = _comic_with_variant(app, user_id, primary, variant)
    _login(client, user_id)

    resp = client.post(f'/comics/{comic_id}/covers/primary', json={'cover_id': cover_id})
    assert resp.status_code == 200

    assert client.get(f'/comics/{comic_id}/cover').data == variant
    with app.app_context():
        comic = db.session.get(Comic, comic_id)
        demoted = comic.cover_variants[0]
        assert demoted.label == 'Previous Primary Cover'
        assert client.get(
            f'/comics/{comic_id}/covers/{demoted.id}/image'
        ).data == primary


def test_set_primary_cover_changes_the_cover_url(client, app, user_id):
    """A stable URL would leave the browser showing its cached copy."""
    primary = _jpeg_bytes(color=(255, 0, 0))
    variant = _jpeg_bytes(color=(0, 0, 255))
    comic_id, cover_id = _comic_with_variant(app, user_id, primary, variant)

    with app.app_context():
        before = db.session.get(Comic, comic_id).cover_version()

    _login(client, user_id)
    client.post(f'/comics/{comic_id}/covers/primary', json={'cover_id': cover_id})

    with app.app_context():
        after = db.session.get(Comic, comic_id).cover_version()
    assert before and after and before != after

    page = client.get(f'/comics/{comic_id}').get_data(as_text=True)
    assert f'/comics/{comic_id}/cover?v={after}' in page


def test_set_primary_cover_while_old_cover_is_being_served(client, app, user_id):
    """Windows cannot replace a file that is still open, so never overwrite one."""
    primary = _jpeg_bytes(color=(255, 0, 0))
    variant = _jpeg_bytes(color=(0, 0, 255))
    comic_id, cover_id = _comic_with_variant(app, user_id, primary, variant)
    _login(client, user_id)

    in_flight = client.get(f'/comics/{comic_id}/cover')
    assert in_flight.status_code == 200

    resp = client.post(f'/comics/{comic_id}/covers/primary', json={'cover_id': cover_id})
    assert resp.status_code == 200
    assert client.get(f'/comics/{comic_id}/cover').data == variant


def test_cover_cache_headers_require_a_version_to_be_cacheable(client, app, user_id):
    blob = _jpeg_bytes()
    with app.app_context():
        comic = Comic(title='Cache Me', issue_number='6', publisher='Test', user_id=user_id)
        db.session.add(comic)
        db.session.flush()
        persist_primary_cover(comic, blob, 'image/jpeg')
        db.session.commit()
        comic_id, version = comic.id, comic.cover_version()

    _login(client, user_id)
    assert client.get(f'/comics/{comic_id}/cover').headers['Cache-Control'] == 'private, no-cache'
    versioned = client.get(f'/comics/{comic_id}/cover?v={version}')
    assert versioned.headers['Cache-Control'] == 'private, max-age=31536000'


def test_has_cover_image_true_for_path_only(app, user_id):
    blob = _jpeg_bytes()
    with app.app_context():
        app.config['COVERS_KEEP_BLOB'] = False
        comic = Comic(
            title='Path Only',
            issue_number='5',
            publisher='Test',
            user_id=user_id,
        )
        db.session.add(comic)
        db.session.flush()
        persist_primary_cover(comic, blob, 'image/jpeg')
        db.session.commit()
        assert comic.cover_image is None
        assert comic.cover_image_path
        assert comic.has_cover_image()
