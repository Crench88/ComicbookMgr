"""Tests for catalog Series <-> Comic linkage."""

import pytest

from app import create_app, db
from app.models import Comic, Series, User
from app.services.series_link import apply_series_link, resolve_catalog_series


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


class TestResolveCatalogSeries:
    def test_matches_display_name(self, app):
        with app.app_context():
            series = Series(name='ROM', volume='1', publisher='Marvel Comics')
            db.session.add(series)
            db.session.commit()

            matched = resolve_catalog_series('ROM Vol. 1', publisher='Marvel Comics')
            assert matched is not None
            assert matched.id == series.id

    def test_matches_comicvine_volume_id(self, app):
        with app.app_context():
            series = Series(
                name='Batman',
                volume='1',
                publisher='DC Comics',
                comicvine_volume_id=796,
            )
            db.session.add(series)
            db.session.commit()

            matched = resolve_catalog_series('Something Else', comicvine_volume_id=796)
            assert matched is not None
            assert matched.id == series.id

    def test_ambiguous_name_without_volume_does_not_match(self, app):
        with app.app_context():
            db.session.add_all([
                Series(name='Batman', volume='1', publisher='DC Comics'),
                Series(name='Batman', volume='2', publisher='DC Comics'),
            ])
            db.session.commit()

            assert resolve_catalog_series('Batman', publisher='DC Comics') is None


class TestApplySeriesLink:
    def test_sets_series_id_and_syncs_text(self, app):
        with app.app_context():
            user = User(username='owner', email='owner@example.com')
            user.set_password('password123')
            series = Series(name='ROM', volume='1', publisher='Marvel Comics')
            db.session.add_all([user, series])
            db.session.commit()

            comic = Comic(
                title='ROM #1',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user.id,
            )
            matched = apply_series_link(comic, 'ROM Vol. 1', publisher='Marvel Comics')
            db.session.add(comic)
            db.session.commit()

            assert matched is not None
            assert comic.series_id == series.id
            assert comic.series == 'ROM Vol. 1'
            assert comic.series_label == 'ROM Vol. 1'


class TestComicCreateLinksSeries:
    def test_new_comic_links_catalog_series(self, client, app):
        with app.app_context():
            user = User(username='creator', email='creator@example.com')
            user.set_password('password123')
            series = Series(name='ROM', volume='1', publisher='Marvel Comics')
            db.session.add_all([user, series])
            db.session.commit()
            user_id = user.id
            series_id = series.id

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

        response = client.post('/comics/new', data={
            'title': 'ROM #1',
            'series': 'ROM Vol. 1',
            'issue_number': '1',
            'publisher': 'Marvel Comics',
            'catalog_series_id': str(series_id),
            'submit': 'Save Comic',
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            comic = Comic.query.filter_by(user_id=user_id, issue_number='1').first()
            assert comic is not None
            assert comic.series_id == series_id
            assert comic.series == 'ROM Vol. 1'
