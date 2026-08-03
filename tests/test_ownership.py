"""Tests for In Collection / Digital ownership sliders."""

import pytest

from app import create_app, db
from app.models import Comic, User


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
        user = User(username='owner', email='owner@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


class TestOwnershipTags:
    def test_in_collection_only(self, app, user_id):
        with app.app_context():
            comic = Comic(
                title='A', series='A', issue_number='1', publisher='Marvel',
                user_id=user_id,
            )
            comic.apply_ownership(in_collection=True, is_digital=False)
            assert [t['label'] for t in comic.ownership_status_tags()] == ['In Collection']
            assert comic.is_wishlist is False

    def test_in_collection_and_digital(self, app, user_id):
        with app.app_context():
            comic = Comic(
                title='A', series='A', issue_number='1', publisher='Marvel',
                user_id=user_id,
            )
            comic.apply_ownership(in_collection=True, is_digital=True)
            labels = [t['label'] for t in comic.ownership_status_tags()]
            assert labels == ['In Collection', 'Digital']
            assert comic.is_wishlist is False

    def test_digital_only(self, app, user_id):
        with app.app_context():
            comic = Comic(
                title='A', series='A', issue_number='1', publisher='Marvel',
                user_id=user_id,
            )
            comic.apply_ownership(in_collection=False, is_digital=True)
            assert [t['label'] for t in comic.ownership_status_tags()] == ['Digital only']
            assert comic.is_wishlist is False

    def test_wishlist_when_both_off(self, app, user_id):
        with app.app_context():
            comic = Comic(
                title='A', series='A', issue_number='1', publisher='Marvel',
                user_id=user_id,
            )
            comic.apply_ownership(in_collection=False, is_digital=False)
            assert [t['label'] for t in comic.ownership_status_tags()] == ['Wishlist']
            assert comic.is_wishlist is True


class TestOwnershipEndpoint:
    def test_update_ownership_on_show(self, client, app, user_id):
        with app.app_context():
            comic = Comic(
                title='Powerless', series='Powerless', issue_number='1',
                publisher='Marvel', user_id=user_id,
            )
            comic.apply_ownership(in_collection=True, is_digital=False)
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login(client, user_id)
        response = client.post(
            f'/comics/{comic_id}/ownership',
            json={'in_collection': False, 'is_digital': True},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['in_collection'] is False
        assert data['is_digital'] is True
        assert [t['label'] for t in data['tags']] == ['Digital only']

        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.in_collection is False
            assert comic.is_digital is True
            assert comic.is_wishlist is False

    def test_forms_include_ownership_sliders(self, client, user_id):
        _login(client, user_id)
        add_page = client.get('/comics/new').get_data(as_text=True)
        assert 'comicInCollection' in add_page or 'id="in_collection"' in add_page or 'In Collection' in add_page
        assert 'bulkInCollection' in add_page
        assert 'bulkIsDigital' in add_page
