"""Tests for cover barcode scanning."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app import create_app, db
from app.models import Comic, User
from app.services.cover_barcode import (
    _codes_from_ocr_texts,
    is_valid_upc_a,
    normalize_product_code,
    pick_best_upc,
    scan_cover_image,
    upc_a_check_digit,
)

FIXTURE_DIR = Path(__file__).parent / 'fixtures'
CIVIL_WAR_STRIP = FIXTURE_DIR / 'civil_war_ii_upc_strip.png'


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_id(app):
    with app.app_context():
        user = User(username='scanner', email='scanner@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _png_bytes(color='white'):
    buf = BytesIO()
    Image.new('RGB', (120, 80), color).save(buf, format='PNG')
    return buf.getvalue()


class TestUpcValidation:
    def test_check_digit_for_known_marvel_upc(self):
        assert upc_a_check_digit('75960608512') == '5'
        assert is_valid_upc_a('759606085125')

    def test_normalize_appends_missing_check_digit(self):
        assert normalize_product_code('75960608512') == '759606085125'

    def test_normalize_strips_ean13_leading_zero_to_upc(self):
        assert normalize_product_code('0759606085125') == '759606085125'

    def test_normalize_rejects_garbage_joined_with_supplement(self):
        assert normalize_product_code('596060851200211') is None


class TestOcrDigitParsing:
    def test_rebuilds_upc_when_leading_digit_is_missing(self):
        codes = _codes_from_ocr_texts(['59606-08512', 'MARVEL', '00211'])
        assert '759606085125' in codes
        assert '00211' not in codes

    def test_keeps_leading_digit_stuck_to_body(self):
        codes = _codes_from_ocr_texts(['7m59606-08512', '00211'])
        assert codes[0] == '759606085125'


class TestPickBestUpc:
    def test_prefers_upc_a(self):
        best = pick_best_upc([
            {'data': 'https://example.com', 'type': 'QRCODE'},
            {'data': '9781234567897', 'type': 'EAN13'},
            {'data': '012345678905', 'type': 'UPCA'},
        ])
        assert best == '012345678905'

    def test_ignores_ean5_supplement(self):
        best = pick_best_upc([
            {'data': '00211', 'type': 'EAN5'},
            {'data': '759606085125', 'type': 'OCR-UPC'},
        ])
        assert best == '759606085125'


class TestScanCoverImage:
    @patch('app.services.cover_barcode.decode_barcodes_from_image_bytes')
    def test_scan_cover_image_returns_best(self, mock_decode):
        mock_decode.return_value = [{'data': '012345678905', 'type': 'UPCA'}]
        result = scan_cover_image(b'fake-bytes')
        assert result['best'] == '012345678905'
        assert result['available'] is True

    @pytest.mark.skipif(not CIVIL_WAR_STRIP.exists(), reason='fixture missing')
    def test_reads_vertical_upc_digits_from_comic_trade_dress(self):
        result = scan_cover_image(CIVIL_WAR_STRIP.read_bytes())
        assert result['best'] == '759606085125'
        assert is_valid_upc_a(result['best'])


class TestScanRoute:
    @patch('app.comics.routes_barcode.scan_cover_image')
    def test_scan_saves_upc(self, mock_scan, client, app, user_id):
        mock_scan.return_value = {
            'codes': [{'data': '012345678905', 'type': 'UPCA'}],
            'best': '012345678905',
            'available': True,
            'error': None,
        }
        with app.app_context():
            comic = Comic(
                title='ROM #1',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                cover_image=_png_bytes(),
                cover_image_mime='image/png',
                user_id=user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login(client, user_id)
        response = client.post(
            f'/comics/{comic_id}/scan-barcode',
            json={'overwrite': False},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['upc'] == '012345678905'

        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.upc == '012345678905'

    @patch('app.comics.routes_barcode.scan_cover_image')
    def test_scan_requires_confirmation_when_upc_exists(self, mock_scan, client, app, user_id):
        mock_scan.return_value = {
            'codes': [{'data': '012345678905', 'type': 'UPCA'}],
            'best': '012345678905',
            'available': True,
            'error': None,
        }
        with app.app_context():
            comic = Comic(
                title='ROM #1',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                upc='999999999999',
                cover_image=_png_bytes(),
                cover_image_mime='image/png',
                user_id=user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login(client, user_id)
        response = client.post(f'/comics/{comic_id}/scan-barcode', json={})
        assert response.status_code == 409
        assert response.get_json()['needs_confirmation'] is True

        response = client.post(
            f'/comics/{comic_id}/scan-barcode',
            json={'overwrite': True},
        )
        assert response.status_code == 200
        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.upc == '012345678905'

    def test_scan_without_cover_returns_400(self, client, app, user_id):
        with app.app_context():
            comic = Comic(
                title='ROM #1',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login(client, user_id)
        response = client.post(f'/comics/{comic_id}/scan-barcode', json={})
        assert response.status_code == 400
