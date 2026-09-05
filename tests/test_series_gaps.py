"""Owned vs catalog SeriesIssue gaps and Bulk Add hook."""

import pytest

from app import create_app, db
from app.models import Comic, Series, SeriesIssue, User
from app.services.series_gaps import (
    catalog_gaps_for_series,
    collapse_issue_ranges,
    normalize_issue_number,
    serialize_series_gaps,
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


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _catalog_with_issues(name='ROM', volume='1', numbers=('1', '2', '3', '4', '5')):
    series = Series(name=name, volume=volume, publisher='Marvel Comics')
    db.session.add(series)
    db.session.flush()
    for number in numbers:
        db.session.add(SeriesIssue(series_id=series.id, issue_number=number, title=f'#{number}'))
    return series


class TestIssueHelpers:
    def test_normalize_strips_trailing_point_zero(self):
        assert normalize_issue_number('1.0') == '1'
        assert normalize_issue_number('01') == '1'
        assert normalize_issue_number('1.5') == '1.5'

    def test_collapse_consecutive_integers(self):
        assert collapse_issue_ranges(['1', '2', '3', '5', '8', '9']) == '1-3, 5, 8-9'
        assert collapse_issue_ranges(['1.5', '2']) == '1.5, 2'


class TestCatalogGaps:
    def test_missing_owned_and_wishlist(self, app):
        with app.app_context():
            user = User(username='gapowner', email='gapowner@example.com')
            user.set_password('password123')
            other = User(username='other', email='other@example.com')
            other.set_password('password123')
            series = _catalog_with_issues()
            db.session.add_all([user, other])
            db.session.flush()
            db.session.add_all([
                Comic(
                    title='ROM #1',
                    series='ROM Vol. 1',
                    series_id=series.id,
                    issue_number='1',
                    publisher='Marvel Comics',
                    user_id=user.id,
                ),
                Comic(
                    title='ROM #3 wish',
                    series='ROM Vol. 1',
                    series_id=series.id,
                    issue_number='3',
                    publisher='Marvel Comics',
                    user_id=user.id,
                    is_wishlist=True,
                    in_collection=False,
                ),
                Comic(
                    title='ROM #4 other',
                    series='ROM Vol. 1',
                    series_id=series.id,
                    issue_number='4',
                    publisher='Marvel Comics',
                    user_id=other.id,
                ),
            ])
            db.session.commit()

            gaps = catalog_gaps_for_series(user.id, 'ROM Vol. 1')
            assert gaps['catalog_count'] == 5
            assert gaps['owned_count'] == 1
            assert gaps['missing'] == ['2', '3', '4', '5']
            assert gaps['missing_ranges'] == '2-5'

    def test_unknown_series_is_empty(self, app):
        with app.app_context():
            user = User(username='empty', email='empty@example.com')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
            gaps = catalog_gaps_for_series(user.id, 'Unknown Series')
            assert gaps['missing'] == []
            assert gaps['catalog_count'] == 0


class TestGapCollectionUi:
    def test_collection_header_and_bulk_add_link(self, client, app):
        with app.app_context():
            user = User(username='browser', email='browser@example.com')
            user.set_password('password123')
            series = _catalog_with_issues()
            db.session.add(user)
            db.session.flush()
            db.session.add(Comic(
                title='ROM #1',
                series='ROM Vol. 1',
                series_id=series.id,
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user.id,
            ))
            db.session.commit()
            user_id = user.id

        _login(client, user_id)
        response = client.get('/comics?series=ROM+Vol.+1')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'Missing 4 of 5 catalog issues' in html
        assert '#2' in html
        assert 'Add missing' in html
        assert 'tab=bulk' in html
        assert 'issues=2-5' in html

        ajax = client.get('/comics/series-issues?series=ROM+Vol.+1')
        assert ajax.status_code == 200
        payload = ajax.get_json()
        assert payload['gaps']['missing'] == ['2', '3', '4', '5']
        assert payload['gaps']['add_url']
        assert 'tab=bulk' in payload['gaps']['add_url']

    def test_add_form_prefills_bulk_tab(self, client, app):
        with app.app_context():
            user = User(username='adder', email='adder@example.com')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        _login(client, user_id)
        response = client.get('/comics/new?tab=bulk&series=ROM+Vol.+1&issues=2-5')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'bulkAddPanel' in html
        assert 'tab=bulk' in html or "addParams.get('tab')" in html


class TestWishlistIndex:
    def test_model_declares_user_wishlist_index(self):
        index_names = {index.name for index in Comic.__table__.indexes}
        assert 'ix_comic_user_id_is_wishlist' in index_names


def test_serialize_includes_add_url(app):
    with app.test_request_context():
        payload = serialize_series_gaps(
            {
                'catalog_series_id': 1,
                'catalog_name': 'ROM Vol. 1',
                'catalog_count': 3,
                'owned_count': 1,
                'missing': ['2', '3'],
                'missing_ranges': '2-3',
            },
            'ROM Vol. 1',
        )
        assert payload['add_url'].endswith('/comics/new?issues=2-3&series=ROM+Vol.+1&tab=bulk') or (
            'tab=bulk' in payload['add_url'] and 'issues=2-3' in payload['add_url']
        )
