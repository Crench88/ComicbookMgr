"""Tests for catalog Series <-> Comic linkage."""

import pytest

from app import create_app, db
from app.models import Comic, ComicFile, Series, User
from app.services.series_link import (
    apply_series_link,
    resolve_catalog_series,
    sync_owned_comics_series_text,
)


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


class TestSeriesGroupingUsesCatalogName:
    def test_stale_free_text_groups_under_catalog_display_name(self, client, app):
        with app.app_context():
            user = User(username='reader', email='reader@example.com')
            user.set_password('password123')
            series = Series(name='ROM', volume='1', publisher='Marvel Comics')
            db.session.add_all([user, series])
            db.session.flush()
            comic = Comic(
                title='ROM #1',
                series='ROM',
                series_id=series.id,
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user.id,
            )
            db.session.add(comic)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

        response = client.get('/comics?series=ROM+Vol.+1')
        assert response.status_code == 200
        html = response.data.decode()
        assert 'ROM Vol. 1' in html
        assert 'series-list-item' in html

    def test_rename_updates_owned_comic_series_text(self, app):
        with app.app_context():
            user = User(username='owner2', email='owner2@example.com')
            user.set_password('password123')
            series = Series(name='ROM', volume='1', publisher='Marvel Comics')
            db.session.add_all([user, series])
            db.session.flush()
            comic = Comic(
                title='ROM #1',
                series='ROM',
                series_id=series.id,
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user.id,
            )
            db.session.add(comic)
            db.session.commit()

            series.volume = '2'
            updated = sync_owned_comics_series_text(series)
            db.session.commit()

            assert updated == 1
            assert db.session.get(Comic, comic.id).series == 'ROM Vol. 2'


class TestFormAndShowLayout:
    def test_add_form_has_wizard_steps(self, client, app):
        with app.app_context():
            user = User(username='adder', email='adder@example.com')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

        page = client.get('/comics/new')
        assert page.status_code == 200
        assert b'data-comic-form-wizard' in page.data
        assert b'1. Identify' in page.data
        assert b'3. Covers' in page.data

    def test_show_read_is_primary_when_digital_file_exists(self, client, app):
        with app.app_context():
            user = User(username='viewer', email='viewer@example.com', is_admin=True)
            user.set_password('password123')
            db.session.add(user)
            db.session.flush()
            comic = Comic(
                title='ROM #1',
                series='ROM Vol. 1',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=user.id,
                is_digital=True,
            )
            db.session.add(comic)
            db.session.flush()
            db.session.add(ComicFile(
                comic_id=comic.id,
                user_id=user.id,
                storage_path='digital/test.cbz',
                format='cbz',
                original_filename='test.cbz',
                page_count=22,
                file_size=1024,
            ))
            db.session.commit()
            user_id = user.id
            comic_id = comic.id

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

        page = client.get(f'/comics/{comic_id}')
        assert page.status_code == 200
        html = page.data.decode()
        assert 'btn btn-primary' in html
        assert '> Read' in html or 'Read' in html
        nav = client.get('/comics')
        assert b'Series List' in nav.data
        assert nav.data.find(b'Series List') < nav.data.find(b'Comic Admin')
