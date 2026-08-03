"""Tests for collection import and autocomplete."""

import pytest

from app import create_app, db
from app.models import Comic, User
from app.services.comic_import import annotate_duplicates, parse_csv_text


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
        user = User(username='importer', email='importer@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


class TestComicImportParsing:
    def test_parse_csv_and_detect_duplicate(self, app, user_id):
        csv_text = (
            "Series,Title,Issue Number,Publisher\n"
            "ROM,ROM #1,1,Marvel Comics\n"
            "ROM,ROM #2,2,Marvel Comics\n"
        )
        with app.app_context():
            db.session.add(Comic(
                title='ROM #1',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user_id,
            ))
            db.session.commit()
            records = annotate_duplicates(parse_csv_text(csv_text), user_id)

        assert records[0]['status'] == 'duplicate'
        assert records[1]['status'] == 'new'


class TestImportRoute:
    def test_import_preview_and_confirm(self, client, app, user_id):
        _login(client, user_id)
        data = {
            'import_file': (
                __import__('io').BytesIO(
                    b"Series,Title,Issue Number,Publisher\n"
                    b"Iron Man,Iron Man #1,1,Marvel Comics\n"
                ),
                'comics.csv',
            )
        }
        response = client.post(
            '/comics/import',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'Import Preview' in response.data
        assert b'Iron Man' in response.data

        confirm = client.post(
            '/comics/import/preview',
            data={'skip_duplicates': '1'},
            follow_redirects=True,
        )
        assert confirm.status_code == 200
        with app.app_context():
            comic = Comic.query.filter_by(user_id=user_id, issue_number='1').first()
            assert comic is not None
            assert comic.series == 'Iron Man'


class TestAutocomplete:
    def test_autocomplete_requires_three_chars(self, client, user_id):
        _login(client, user_id)
        response = client.get('/comics/autocomplete?q=ro')
        assert response.status_code == 200
        assert response.get_json()['suggestions'] == []

    def test_autocomplete_returns_series_matches(self, client, app, user_id):
        with app.app_context():
            db.session.add(Comic(
                title='ROM #1',
                series='ROM Spaceknight',
                issue_number='1',
                publisher='Marvel Comics',
                writer='Bill Mantlo',
                user_id=user_id,
            ))
            db.session.commit()

        _login(client, user_id)
        response = client.get('/comics/autocomplete?q=rom')
        assert response.status_code == 200
        labels = [item['label'] for item in response.get_json()['suggestions']]
        assert any('ROM' in label for label in labels)
