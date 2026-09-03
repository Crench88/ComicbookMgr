"""Idle session timeout applies to every authenticated user, including admins."""

import time

import pytest

from app import create_app, db
from app.models import User
from app.session_timeout import LAST_ACTIVITY_KEY


@pytest.fixture
def app():
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'idle-test-secret',
        'IDLE_TIMEOUT_SECONDS': 30 * 60,
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
def user_ids(app):
    with app.app_context():
        regular = User(username='idleuser', email='idle@example.com', is_admin=False)
        regular.set_password('password123')
        admin = User(username='idleadmin', email='idleadmin@example.com', is_admin=True)
        admin.set_password('adminpass')
        inactive = User(
            username='inactive',
            email='inactive@example.com',
            is_admin=False,
            is_active=False,
        )
        inactive.set_password('password123')
        db.session.add_all([regular, admin, inactive])
        db.session.commit()
        return {
            'regular': regular.id,
            'admin': admin.id,
            'inactive': inactive.id,
        }


def _login_as(client, user_id, last_activity=None):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        if last_activity is not None:
            sess[LAST_ACTIVITY_KEY] = last_activity


def test_login_starts_sliding_idle_session(client, user_ids):
    response = client.post('/login', data={
        'username': 'idleuser',
        'password': 'password123',
    }, follow_redirects=False)

    assert response.status_code == 302
    assert 'remember_token' not in response.headers.get('Set-Cookie', '')
    with client.session_transaction() as sess:
        assert sess.get('_user_id') == str(user_ids['regular'])
        assert sess.permanent is True
        assert LAST_ACTIVITY_KEY in sess


def test_inactive_account_cannot_log_in(client, user_ids):
    response = client.post('/login', data={
        'username': 'inactive',
        'password': 'password123',
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'deactivated' in response.data
    with client.session_transaction() as sess:
        assert '_user_id' not in sess


def test_active_session_stays_logged_in(client, user_ids):
    _login_as(client, user_ids['regular'], last_activity=time.time() - 5 * 60)
    response = client.get('/dashboard')
    assert response.status_code == 200


def test_idle_timeout_logs_out_regular_user(client, user_ids):
    _login_as(client, user_ids['regular'], last_activity=time.time() - 31 * 60)
    response = client.get('/dashboard', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')
    with client.session_transaction() as sess:
        assert '_user_id' not in sess
        assert LAST_ACTIVITY_KEY not in sess


def test_idle_timeout_logs_out_admin_user(client, user_ids):
    _login_as(client, user_ids['admin'], last_activity=time.time() - 31 * 60)
    response = client.get('/admin/roles', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')
    with client.session_transaction() as sess:
        assert '_user_id' not in sess
        assert LAST_ACTIVITY_KEY not in sess


def test_idle_timeout_returns_json_401(client, user_ids):
    _login_as(client, user_ids['regular'], last_activity=time.time() - 31 * 60)
    response = client.get(
        '/dashboard',
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 401
    assert response.get_json()['error'] == 'Session expired due to inactivity'


def test_session_just_inside_idle_window_stays_logged_in(client, user_ids):
    _login_as(client, user_ids['admin'], last_activity=time.time() - (30 * 60 - 5))
    response = client.get('/admin/series')
    assert response.status_code == 200


def test_missing_last_activity_is_treated_as_fresh(client, user_ids):
    _login_as(client, user_ids['regular'])
    response = client.get('/dashboard')
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert LAST_ACTIVITY_KEY in sess
