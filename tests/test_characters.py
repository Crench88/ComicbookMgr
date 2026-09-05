"""Tests for indexed character mentions and dashboard counts."""

import pytest

from app import create_app, db
from app.models import CharacterMention, Comic, User
from app.services.characters import (
    parse_character_names,
    sync_character_mentions,
    top_characters_for_user,
)


@pytest.fixture
def app():
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
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
        user = User(username='chars', email='chars@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _add_comic(user_id, *, characters, is_wishlist=False, title='ASM'):
    comic = Comic(
        title=title,
        issue_number='1',
        publisher='Marvel Comics',
        characters=characters,
        user_id=user_id,
        is_wishlist=is_wishlist,
    )
    db.session.add(comic)
    db.session.flush()
    sync_character_mentions(comic)
    db.session.commit()
    return comic


def test_parse_character_names():
    assert parse_character_names('Spider-Man, Mary Jane; spider-man, ') == [
        'Spider-Man',
        'Mary Jane',
    ]


def test_sync_character_mentions_replaces_rows(app, user_id):
    with app.app_context():
        comic = _add_comic(user_id, characters='Spider-Man, Wolverine')
        assert CharacterMention.query.filter_by(comic_id=comic.id).count() == 2

        comic.characters = 'Daredevil'
        sync_character_mentions(comic)
        db.session.commit()

        names = [row.name for row in CharacterMention.query.filter_by(comic_id=comic.id)]
        assert names == ['Daredevil']


def test_top_characters_skips_wishlist_and_groups_case(app, user_id):
    with app.app_context():
        _add_comic(user_id, characters='Spider-Man, Wolverine', title='Owned 1')
        _add_comic(user_id, characters='spider-man', title='Owned 2')
        _add_comic(
            user_id,
            characters='Doctor Doom',
            is_wishlist=True,
            title='Wanted',
        )

        top = top_characters_for_user(user_id)
        assert top[0][0].lower() == 'spider-man'
        assert top[0][1] == 2
        names = {name.lower() for name, _count in top}
        assert 'doctor doom' not in names


def test_create_comic_form_writes_mentions(client, app, user_id):
    _login(client, user_id)
    response = client.post('/comics/new', data={
        'title': 'ROM #1',
        'series': 'ROM',
        'issue_number': '1',
        'publisher': 'Marvel Comics',
        'characters': 'ROM, Spaceknight',
        'read_status': 'unread',
        'submit': 'Save Comic',
    }, follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        comic = Comic.query.filter_by(user_id=user_id, title='ROM #1').one()
        names = sorted(
            row.name for row in CharacterMention.query.filter_by(comic_id=comic.id)
        )
        assert names == ['ROM', 'Spaceknight']


def test_dashboard_lists_top_characters(client, app, user_id):
    with app.app_context():
        _add_comic(user_id, characters='Cyclops, Jean Grey')

    _login(client, user_id)
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert b'Cyclops' in response.data
    assert b'Jean Grey' in response.data
