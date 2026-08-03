"""Tests for admin authorization."""

import pytest

from app import create_app, db
from app.models import User


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


def _login_as(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)


@pytest.fixture
def user_ids(app):
    with app.app_context():
        admin = User(username='adminuser', email='admin@test.com', is_admin=True)
        admin.set_password('adminpass')
        regular = User(username='regular', email='user@test.com', is_admin=False)
        regular.set_password('userpass')
        db.session.add_all([admin, regular])
        db.session.commit()
        return {'admin': admin.id, 'regular': regular.id}


def test_admin_route_blocks_non_admin(client, user_ids):
    _login_as(client, user_ids['regular'])
    response = client.get('/admin/series')
    assert response.status_code == 403


def test_admin_route_allows_admin(client, user_ids):
    _login_as(client, user_ids['admin'])
    response = client.get('/admin/series')
    assert response.status_code == 200


def test_admin_route_redirects_anonymous(client, app):
    response = client.get('/admin/series', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')


def test_manage_roles_allows_admin(client, user_ids):
    _login_as(client, user_ids['admin'])
    response = client.get('/admin/roles')
    assert response.status_code == 200
    assert b'Manage Roles' in response.data


def test_manage_roles_blocks_non_admin(client, user_ids):
    _login_as(client, user_ids['regular'])
    response = client.get('/admin/roles')
    assert response.status_code == 403


def test_toggle_admin_grants_and_revokes(client, user_ids, app):
    _login_as(client, user_ids['admin'])
    response = client.post(
        f"/admin/roles/{user_ids['regular']}/toggle-admin",
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_ids['regular'])
        assert user.is_admin is True

    response = client.post(
        f"/admin/roles/{user_ids['regular']}/toggle-admin",
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_ids['regular'])
        assert user.is_admin is False


def test_cannot_remove_own_admin(client, user_ids, app):
    _login_as(client, user_ids['admin'])
    response = client.post(
        f"/admin/roles/{user_ids['admin']}/toggle-admin",
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_ids['admin'])
        assert user.is_admin is True


def test_admin_can_reset_password(client, user_ids, app):
    _login_as(client, user_ids['admin'])
    response = client.post(
        f"/admin/roles/{user_ids['regular']}/reset-password",
        data={'password': 'newpass99', 'confirm_password': 'newpass99'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_ids['regular'])
        assert user.check_password('newpass99')


def test_reset_password_requires_match(client, user_ids, app):
    _login_as(client, user_ids['admin'])
    response = client.post(
        f"/admin/roles/{user_ids['regular']}/reset-password",
        data={'password': 'newpass99', 'confirm_password': 'different'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, user_ids['regular'])
        assert not user.check_password('newpass99')

