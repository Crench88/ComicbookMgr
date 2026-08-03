"""Security regression tests."""

import base64
import re
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

from app import create_app, db
from app.models import Comic, User
from app.services.safe_http import (
    UnsafeRemoteUrl,
    fetch_public_image,
    validate_public_http_url,
)


@pytest.fixture
def csrf_app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': True,
        'SECRET_KEY': 'csrf-test-secret',
    })
    with app.app_context():
        db.create_all()
        user = User(username='secureuser', email='secure@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        yield app, user.id
        db.session.remove()
        db.drop_all()


def _login_session(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)


def test_json_mutations_require_csrf(csrf_app):
    app, user_id = csrf_app
    client = app.test_client()
    _login_session(client, user_id)

    response = client.post('/comics/bulk-add/parse', json={'issue_ranges': '1-2'})
    assert response.status_code == 400

    page = client.get('/comics/new')
    token_match = re.search(
        rb'<meta name="csrf-token" content="([^"]+)"',
        page.data,
    )
    assert token_match

    response = client.post(
        '/comics/bulk-add/parse',
        json={'issue_ranges': '1-2'},
        headers={'X-CSRFToken': token_match.group(1).decode()},
    )
    assert response.status_code == 200
    assert response.get_json()['issues'] == ['1', '2']


@patch('app.services.safe_http.socket.getaddrinfo')
def test_cover_proxy_blocks_private_networks(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('127.0.0.1', 80)),
    ]

    with pytest.raises(UnsafeRemoteUrl):
        validate_public_http_url('http://internal.example/secret')


@patch('app.services.safe_http.requests.get')
@patch('app.services.safe_http.socket.getaddrinfo')
def test_cover_proxy_accepts_verified_image_with_wrong_content_type(
        mock_getaddrinfo, mock_get):
    buffer = BytesIO()
    Image.new('RGB', (2, 2), 'green').save(buffer, format='JPEG')
    image_bytes = buffer.getvalue()

    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('93.184.216.34', 443)),
    ]

    class FakeResponse:
        is_redirect = False
        is_permanent_redirect = False
        headers = {
            'content-type': 'application/octet-stream',
            'content-length': str(len(image_bytes)),
        }

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield image_bytes

        def close(self):
            return None

    mock_get.return_value = FakeResponse()

    downloaded, mime_type = fetch_public_image('https://example.com/cover')
    assert downloaded == image_bytes
    assert mime_type == 'image/jpeg'


def test_cover_upload_rejects_non_image_bytes(csrf_app):
    app, user_id = csrf_app
    client = app.test_client()

    with app.app_context():
        comic = Comic(
            title='Security Test',
            series='Security Series',
            issue_number='1',
            publisher='Test Publisher',
            user_id=user_id,
        )
        db.session.add(comic)
        db.session.commit()
        comic_id = comic.id

    _login_session(client, user_id)
    page = client.get(f'/comics/{comic_id}/edit')
    token = re.search(
        rb'<meta name="csrf-token" content="([^"]+)"',
        page.data,
    ).group(1).decode()

    response = client.post(
        f'/comics/{comic_id}/covers',
        json={
            'replace': True,
            'cover': {
                'blob_data': base64.b64encode(b'<script>alert(1)</script>').decode(),
                'mime_type': 'image/jpeg',
                'label': 'Not an image',
            },
        },
        headers={'X-CSRFToken': token},
    )

    assert response.status_code == 400
    assert 'valid supported image' in response.get_json()['error']
