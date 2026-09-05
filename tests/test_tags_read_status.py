"""Tests for comic tags and read status."""

import pytest

from app import create_app, db
from app.models import Comic, Tag, User
from app.services.tags import normalize_read_status, parse_tag_names, sync_comic_tags


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
        user = User(username='tagger', email='tagger@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


class TestTagHelpers:
    def test_parse_tag_names(self):
        assert parse_tag_names('key-issue, Bronze Age; signed, key-issue') == [
            'key-issue', 'Bronze Age', 'signed'
        ]

    def test_normalize_read_status(self):
        assert normalize_read_status('READING') == 'reading'
        assert normalize_read_status('nope') == 'unread'


class TestTagPersistence:
    def test_sync_comic_tags(self, app, user_id):
        with app.app_context():
            comic = Comic(
                title='ROM #1',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user_id,
            )
            db.session.add(comic)
            db.session.flush()
            sync_comic_tags(comic, 'key-issue, bronze-age', user_id)
            db.session.commit()

            comic = db.session.get(Comic, comic.id)
            assert comic.get_tags_text() == 'bronze-age, key-issue'
            assert Tag.query.filter_by(user_id=user_id).count() == 2


class TestComicFormTagsAndStatus:
    def test_create_comic_with_tags_and_status(self, client, app, user_id):
        _login(client, user_id)
        response = client.post('/comics/new', data={
            'title': 'ROM #1',
            'series': 'ROM',
            'issue_number': '1',
            'publisher': 'Marvel Comics',
            'tags': 'key-issue, signed',
            'read_status': 'reading',
            'submit': 'Save Comic',
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            comic = Comic.query.filter_by(user_id=user_id, issue_number='1').first()
            assert comic is not None
            assert comic.read_status == 'reading'
            assert {tag.name for tag in comic.tags} == {'key-issue', 'signed'}

    def test_filter_index_by_tag_and_status(self, client, app, user_id):
        with app.app_context():
            comic = Comic(
                title='ROM #1',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                read_status='read',
                user_id=user_id,
            )
            other = Comic(
                title='ROM #2',
                series='ROM',
                issue_number='2',
                publisher='Marvel Comics',
                read_status='unread',
                user_id=user_id,
            )
            db.session.add_all([comic, other])
            db.session.flush()
            sync_comic_tags(comic, 'key-issue', user_id)
            db.session.commit()

        _login(client, user_id)
        response = client.get('/comics?tag=key-issue&read_status=read&series=ROM')
        assert response.status_code == 200
        assert b'ROM #1' in response.data or b'#1' in response.data
        html = response.data.decode()
        assert 'value="key-issue"' in html
        assert 'selected' in html
        assert 'value="read"' in html
