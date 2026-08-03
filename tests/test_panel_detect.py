"""Tests for comic panel detection used by guided reader zoom."""

import io
import zipfile
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app import create_app, db
from app.models import Comic, User
from app.services.page_cache import reset_for_tests
from app.services.panel_detect import detect_panels_from_bytes


def _page_with_four_panels() -> bytes:
    """White gutters separating four dark rectangular panels."""
    image = Image.new('RGB', (800, 1200), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    panels = [
        (40, 40, 370, 560),
        (430, 40, 760, 560),
        (40, 640, 370, 1160),
        (430, 640, 760, 1160),
    ]
    for box in panels:
        draw.rectangle(box, fill=(20, 20, 20), outline=(0, 0, 0), width=4)
        draw.rectangle(
            (box[0] + 20, box[1] + 20, box[2] - 20, box[3] - 20),
            fill=(60, 90, 140),
        )
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _make_cbz(pages):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in pages:
            zf.writestr(name, data)
    buf.seek(0)
    return buf


@pytest.fixture
def panel_app(tmp_path, monkeypatch):
    monkeypatch.setenv('CACHE_DIR', str(tmp_path / 'cache'))
    reset_for_tests()
    digital = tmp_path / 'digital'
    digital.mkdir()
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'DIGITAL_FOLDER': str(digital),
        'COVERS_FOLDER': str(tmp_path / 'covers'),
        'READER_CACHE_DIR': str(tmp_path / 'reader_cache'),
    })
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
    reset_for_tests()


@pytest.fixture
def panel_client(panel_app):
    return panel_app.test_client()


@pytest.fixture
def panel_user_id(panel_app):
    with panel_app.app_context():
        user = User(username='paneluser', email='panel@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess.clear()
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def test_detects_multiple_panels_in_reading_order():
    panels = detect_panels_from_bytes(_page_with_four_panels())
    assert len(panels) >= 2
    assert panels[0]['y'] <= panels[-1]['y']
    for panel in panels:
        assert 0 <= panel['x'] < 1
        assert 0 <= panel['y'] < 1
        assert panel['w'] > 0.05
        assert panel['h'] > 0.05
        assert panel['x'] + panel['w'] <= 1.01
        assert panel['y'] + panel['h'] <= 1.01


def test_blankish_page_falls_back_to_full_page():
    image = Image.new('RGB', (400, 600), (245, 245, 245))
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    panels = detect_panels_from_bytes(buffer.getvalue())
    assert panels == [{'x': 0.0, 'y': 0.0, 'w': 1.0, 'h': 1.0}]


def test_panels_endpoint(panel_client, panel_app, panel_user_id):
    with panel_app.app_context():
        comic = Comic(
            title='Panel Test',
            issue_number='1',
            publisher='Test',
            user_id=panel_user_id,
        )
        db.session.add(comic)
        db.session.commit()
        comic_id = comic.id

    _login(panel_client, panel_user_id)
    cbz = _make_cbz([('001.png', _page_with_four_panels())])
    upload = panel_client.post(
        f'/reader/{comic_id}/upload',
        data={'digital_file': (cbz, 'panels.cbz')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    assert upload.status_code == 200

    response = panel_client.get(f'/reader/{comic_id}/page/1/panels')
    assert response.status_code == 200
    data = response.get_json()
    assert data['page'] == 1
    assert data['count'] >= 1
    assert isinstance(data['panels'], list)
    assert 'x' in data['panels'][0]

    page = panel_client.get(f'/reader/{comic_id}?page=1')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'panelModeToggle' in html
    assert 'readerPanelFocus' in html
