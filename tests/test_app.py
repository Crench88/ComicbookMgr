"""
Unit tests for Comic Book Collection Manager.
"""

import pytest
from io import BytesIO
from unittest.mock import patch
from PIL import Image

from app import create_app, db
from app.models import User, Comic


def _test_png(color):
    buffer = BytesIO()
    Image.new('RGB', (2, 2), color).save(buffer, format='PNG')
    return buffer.getvalue()


PRIMARY_COVER_BYTES = _test_png('red')
ALTERNATE_COVER_BYTES = _test_png('blue')


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
def test_user_id(app):
    with app.app_context():
        user = User(username='testuser', email='test@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login_as(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)


class TestAuth:
    def test_register(self, client):
        response = client.post('/register', data={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Registration successful' in response.data

    def test_login(self, client, test_user_id):
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'password123',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Login successful' in response.data

    def test_invalid_login(self, client):
        response = client.post('/login', data={
            'username': 'wronguser',
            'password': 'wrongpassword',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Invalid username or password' in response.data


class TestComics:
    def test_add_comic(self, client, test_user_id):
        _login_as(client, test_user_id)
        response = client.post('/comics/new', data={
            'title': 'Amazing Spider-Man',
            'series': 'The Amazing Spider-Man',
            'issue_number': '1',
            'publisher': 'Marvel Comics',
            'characters': 'Spider-Man, Peter Parker',
            'genre': 'Superhero',
            'condition': 'Near Mint',
            'estimated_value': '50.00',
            'notes': 'First appearance of Spider-Man',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Comic added successfully' in response.data

    def test_add_comic_saves_and_shows_every_credit(self, client, test_user_id, app):
        _login_as(client, test_user_id)
        credits = {
            field: f'{label} Person' for field, label in Comic.CREDIT_FIELDS
        }
        response = client.post('/comics/new', data={
            'title': 'Credited',
            'series': 'Credit Test',
            'issue_number': '7',
            'publisher': 'Marvel Comics',
            **credits,
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            comic = Comic.query.filter_by(user_id=test_user_id, issue_number='7').one()
            for field, label in Comic.CREDIT_FIELDS:
                assert getattr(comic, field) == f'{label} Person'
            comic_id = comic.id

        page = client.get(f'/comics/{comic_id}').get_data(as_text=True)
        for field, label in Comic.CREDIT_FIELDS:
            assert f'<dt class="col-sm-3">{label}</dt>' in page
            assert f'{label} Person' in page

    def test_view_comics(self, client, test_user_id):
        _login_as(client, test_user_id)
        response = client.get('/comics')
        assert response.status_code == 200
        assert b'My Comics' in response.data

    def test_authenticated_nav_is_flattened(self, client, test_user_id):
        _login_as(client, test_user_id)
        html = client.get('/comics').get_data(as_text=True)
        assert 'nav-add-btn' in html
        assert 'Import Collection' in html
        assert 'Export Collection' in html
        assert '>Wishlist</a>' not in html
        assert 'Wishlist only' in html
        assert 'Open wishlist' in html
        assert '>Import</a>' not in html
        assert '>Export</a>' not in html
        assert '>Home</a>' not in html
        assert '>About</a>' in html

    def test_guest_nav_keeps_marketing_links(self, client):
        html = client.get('/').get_data(as_text=True)
        assert '>Home</a>' in html
        assert '>About</a>' in html
        assert 'nav-add-btn' not in html

    def test_comic_back_link_preserves_collection_series(self, client, test_user_id, app):
        with app.app_context():
            comic = Comic(
                title='Issue',
                series='Selected Series',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.get(
            f'/comics/{comic_id}',
            query_string={
                'next': '/comics?sort=title&series=Different+Series&comic_page=3&series_page=1',
            },
        )

        assert response.status_code == 200
        assert b'series=Selected+Series' in response.data
        assert b'series=Different+Series' not in response.data

    def test_series_grid_sorts_in_sql_and_defers_cover_blob(
            self, client, test_user_id, app):
        from sqlalchemy import inspect
        from app.comics.helpers import _comics_for_series_query

        with app.app_context():
            db.session.add_all([
                Comic(
                    title='Zulu',
                    series='Sorted Series',
                    issue_number='2',
                    publisher='Marvel Comics',
                    user_id=test_user_id,
                    cover_image=PRIMARY_COVER_BYTES,
                    cover_image_mime='image/png',
                ),
                Comic(
                    title='Alpha',
                    series='Sorted Series',
                    issue_number='1',
                    publisher='Marvel Comics',
                    user_id=test_user_id,
                ),
                Comic(
                    title='Beta',
                    series='Sorted Series',
                    issue_number='10',
                    publisher='Marvel Comics',
                    user_id=test_user_id,
                ),
            ])
            db.session.commit()
            db.session.expunge_all()

            comics = _comics_for_series_query(
                test_user_id,
                'Sorted Series',
                sort_by='title',
            ).all()
            assert [comic.title for comic in comics] == ['Alpha', 'Beta', 'Zulu']
            zulu = comics[2]
            assert 'cover_image' in inspect(zulu).unloaded
            assert zulu.has_cover_image() is True
            assert 'cover_image' in inspect(zulu).unloaded

            issue_sorted = _comics_for_series_query(
                test_user_id,
                'Sorted Series',
            ).all()
            assert [comic.issue_number for comic in issue_sorted] == ['1', '2', '10']

        _login_as(client, test_user_id)
        response = client.get(
            '/comics/series-issues',
            query_string={'series': 'Sorted Series', 'sort': 'title'},
        )
        assert response.status_code == 200
        assert [
            comic['title'] for comic in response.get_json()['comics']
        ] == ['Alpha', 'Beta', 'Zulu']


class TestDashboard:
    def test_dashboard_access(self, client, test_user_id):
        _login_as(client, test_user_id)
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'Dashboard' in response.data

    def test_dashboard_redirect(self, client):
        response = client.get('/dashboard', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data


class TestModels:
    def test_user_password_hashing(self, app):
        with app.app_context():
            user = User(username='hashuser', email='hash@example.com')
            user.set_password('password123')

            assert user.check_password('password123')
            assert not user.check_password('wrongpassword')

    def test_comic_creation(self, app, test_user_id):
        with app.app_context():
            comic = Comic(
                title='Amazing Spider-Man',
                series='The Amazing Spider-Man',
                issue_number='1',
                publisher='Marvel Comics',
                characters='Spider-Man, Peter Parker',
                genre='Superhero',
                condition='Near Mint',
                estimated_value=50.00,
                user_id=test_user_id,
            )

            db.session.add(comic)
            db.session.commit()

            assert comic.id is not None
            assert comic.title == 'Amazing Spider-Man'
            assert comic.get_formatted_value() == '$50.00'
            assert 'Spider-Man' in comic.get_characters_list()

    def test_comic_characters_methods(self, app, test_user_id):
        with app.app_context():
            comic = Comic(
                title='Test Comic',
                series='Test Series',
                issue_number='1',
                publisher='Test Publisher',
                user_id=test_user_id,
            )

            characters_list = ['Spider-Man', 'Mary Jane', 'Green Goblin']
            comic.set_characters_list(characters_list)

            assert comic.characters == 'Spider-Man, Mary Jane, Green Goblin'
            assert comic.get_characters_list() == characters_list


class TestBulkAdd:
    def test_parse_requires_login(self, client):
        response = client.post('/comics/bulk-add/parse', json={'issue_ranges': '1-3'})
        assert response.status_code == 302

    def test_parse_success(self, client, test_user_id):
        _login_as(client, test_user_id)
        response = client.post('/comics/bulk-add/parse', json={'issue_ranges': '1-3, 5'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['count'] == 4
        assert data['issues'] == ['1', '2', '3', '5']

    def test_bulk_add_issue_no_api_key(self, client, test_user_id):
        _login_as(client, test_user_id)
        response = client.post('/comics/bulk-add/issue', json={
            'series': 'ROM',
            'issue_number': '1',
        })
        assert response.status_code == 503
        assert response.get_json()['status'] == 'failed'

    @patch('app.services.bulk_add.lookup_issue_for_bulk')
    @patch('app.services.bulk_add._download_cover')
    def test_bulk_add_issue_success(self, mock_cover, mock_lookup, client, test_user_id, app):
        mock_lookup.return_value = {
            'series': 'ROM',
            'issue_number': '1',
            'title': 'The Fate of Gallifrey',
            'publisher': 'Marvel Comics',
            'characters': 'ROM',
            'genre': 'Comic',
            'release_date': '1979-12-01',
            'cover_image_url': 'https://example.com/cover.jpg',
        }
        mock_cover.return_value = (b'fake-image', 'image/jpeg')

        with app.app_context():
            app.config['COMICVINE_API_KEY'] = 'test-key'

        _login_as(client, test_user_id)
        response = client.post('/comics/bulk-add/issue', json={
            'series': 'ROM',
            'issue_number': '1',
            'start_year': 1979,
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'added'
        assert data['issue_number'] == '1'
        assert data['has_cover'] is True

    @patch('app.services.bulk_add.lookup_issue_for_bulk')
    def test_bulk_add_skips_duplicate(self, mock_lookup, client, test_user_id, app):
        mock_lookup.return_value = {
            'series': 'ROM',
            'issue_number': '2',
            'title': 'Issue Two',
            'publisher': 'Marvel Comics',
            'cover_image_url': '',
        }

        with app.app_context():
            app.config['COMICVINE_API_KEY'] = 'test-key'
            db.session.add(Comic(
                title='Issue Two',
                series='ROM',
                issue_number='2',
                publisher='Marvel Comics',
                user_id=test_user_id,
            ))
            db.session.commit()

        _login_as(client, test_user_id)
        response = client.post('/comics/bulk-add/issue', json={
            'series': 'ROM',
            'issue_number': '2',
            'skip_existing': True,
        })
        assert response.status_code == 200
        assert response.get_json()['status'] == 'skipped'


class TestEstimatedValueUpdate:
    def test_update_estimated_value(self, client, test_user_id, app):
        with app.app_context():
            comic = Comic(
                title='Powerless',
                series='Powerless',
                issue_number='1',
                publisher='Marvel',
                estimated_value=5.0,
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.post(
            f'/comics/{comic_id}/estimated-value',
            json={'estimated_value': 13.92},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['estimated_value'] == 13.92
        assert data['formatted_value'] == '$13.92'

        with app.app_context():
            assert Comic.query.get(comic_id).estimated_value == 13.92

    def test_update_estimated_value_rejects_invalid(self, client, test_user_id, app):
        with app.app_context():
            comic = Comic(
                title='Invalid Value',
                series='Test',
                issue_number='1',
                publisher='Test',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.post(
            f'/comics/{comic_id}/estimated-value',
            json={'estimated_value': 'nope'},
        )
        assert response.status_code == 400
        assert response.get_json()['success'] is False

    def test_show_page_includes_value_lookup(self, client, test_user_id, app):
        with app.app_context():
            comic = Comic(
                title='Powerless',
                series='Powerless',
                issue_number='1',
                publisher='Marvel',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        page = client.get(f'/comics/{comic_id}').get_data(as_text=True)
        assert 'id="showValueLookupBtn"' in page
        assert 'comic-enrich.js' in page
        assert 'Enrich comic' in page
        assert 'id="refreshComicVineShowBtn"' in page
        assert 'comic-show-facts' in page
        assert 'd-flex flex-wrap' in page
        assert 'Catalog &amp; record' in page or 'Catalog & record' in page
        assert 'Basic Information' not in page

    def test_show_page_keeps_long_description_and_splits_cover_list(self, client, test_user_id, app):
        story = (
            'Tony Stark is dead? Or is he? Who are his biological parents? '
            'The quest begins here!'
        )
        description = (
            f'{story} List of covers and their creators: Cover Name Creator(s) Variant A'
        )
        with app.app_context():
            comic = Comic(
                title='Powerless',
                series='Powerless',
                issue_number='2',
                publisher='Marvel',
                description=description,
                cover_artist='Adi Granov, Alex Maleev, Brian Stelfreeze',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        page = client.get(f'/comics/{comic_id}').get_data(as_text=True)
        assert 'The quest begins here!' in page
        assert 'Cover credits from ComicVine' in page
        assert 'comic-show-description' in page
        assert 'comic-show-credit-names' in page
        assert 'Adi Granov' in page
        assert 'syncDetailsHeight' not in page

    def test_add_form_includes_enrich_button(self, client, test_user_id):
        _login_as(client, test_user_id)
        page = client.get('/comics/new').get_data(as_text=True)
        assert 'id="enrichComicBtn"' in page
        assert 'comic-enrich.js' in page
        assert 'Enrich comic' in page


class TestDeleteComic:
    def test_delete_comic(self, client, test_user_id, app):
        with app.app_context():
            comic = Comic(
                title='Delete Me',
                series='Test Series',
                issue_number='99',
                publisher='Test Publisher',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.post(f'/comics/{comic_id}/delete', follow_redirects=True)
        assert response.status_code == 200
        assert b'Comic deleted successfully' in response.data

        with app.app_context():
            assert Comic.query.get(comic_id) is None

    def test_delete_redirects_to_next_url(self, client, test_user_id, app):
        with app.app_context():
            comic = Comic(
                title='Redirect Test',
                series='Alpha Series',
                issue_number='1',
                publisher='Test Publisher',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.post(
            f'/comics/{comic_id}/delete',
            data={'next': '/comics?series=Alpha%20Series&comic_page=2'},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert 'series=Alpha' in response.headers['Location']


class TestComicVineCoverLookup:
    @patch('app.comics.routes_search.lookup_covers_for_form')
    def test_covers_lookup_success(self, mock_lookup, client, test_user_id, app):
        mock_lookup.return_value = {
            'covers': [
                {'url': 'https://example.com/a.jpg', 'label': 'Regular Cover'},
                {'url': 'https://example.com/b.jpg', 'label': 'Variant Cover'},
            ],
            'best_match': {'title': 'Test Issue', 'comicvine_id': 123},
            'issue_count': 1,
        }
        app.config['COMICVINE_API_KEY'] = 'test-key'
        _login_as(client, test_user_id)
        response = client.get(
            '/comics/comicvine/covers/lookup?series_name=ROM&issue_number=1&title=Test',
        )
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['covers']) == 2

    def test_covers_lookup_requires_login(self, client):
        response = client.get('/comics/comicvine/covers/lookup?series_name=ROM&issue_number=1')
        assert response.status_code == 302

    @patch('app.comics.routes_search.search_comicvine_volumes')
    @patch('app.comics.routes_search.search_local_series_volumes')
    def test_volumes_lookup_success(self, mock_local, mock_cv, client, test_user_id, app):
        mock_local.return_value = [{
            'source': 'Series Catalog',
            'local_series_id': 1,
            'display_name': 'Batman Vol. 1',
            'start_year': '1940',
            'publisher': 'DC Comics',
        }]
        mock_cv.return_value = [{
            'source': 'ComicVine',
            'comicvine_volume_id': 796,
            'display_name': 'Batman',
            'start_year': '1940',
            'publisher': 'DC Comics',
        }]
        app.config['COMICVINE_API_KEY'] = 'test-key'
        _login_as(client, test_user_id)
        response = client.get('/comics/volumes/lookup?series=Batman&publisher=DC%20Comics')
        assert response.status_code == 200
        data = response.get_json()
        assert data['count'] >= 2


class TestComicVineRefresh:
    @patch('app.comics.routes_search.fetch_comicvine_issue_covers')
    @patch('app.comics.routes_search.lookup_issue_metadata_for_refresh')
    def test_refresh_metadata_success(self, mock_refresh, mock_covers, client, test_user_id, app):
        mock_refresh.return_value = {
            'metadata': {
                'title': 'Test Issue',
                'series': 'ROM',
                'issue_number': '1',
                'writer': 'Bill Mantlo',
                'artist': 'Sal Buscema',
                'comicvine_id': 12345,
            },
            'matched_by': 'comicvine_id',
        }
        mock_covers.return_value = [{
            'url': 'https://example.test/cover.jpg',
            'label': 'Regular Cover',
        }]
        app.config['COMICVINE_API_KEY'] = 'test-key'

        with app.app_context():
            comic = Comic(
                title='Test Issue',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                comicvine_issue_id=12345,
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.get(f'/comics/{comic_id}/comicvine/refresh')
        assert response.status_code == 200
        data = response.get_json()
        assert data['matched_by'] == 'comicvine_id'
        assert data['metadata']['writer'] == 'Bill Mantlo'
        assert data['covers'][0]['label'] == 'Regular Cover'

    def test_refresh_requires_login(self, client):
        response = client.get('/comics/1/comicvine/refresh')
        assert response.status_code == 302

    @patch('app.services.comicvine.lookup_issue_metadata_for_refresh')
    def test_refresh_not_found(self, mock_refresh, client, test_user_id, app):
        mock_refresh.return_value = {'error': 'No ComicVine match found for ROM #1.'}
        app.config['COMICVINE_API_KEY'] = 'test-key'

        with app.app_context():
            comic = Comic(
                title='Test Issue',
                series='ROM',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.get(f'/comics/{comic_id}/comicvine/refresh')
        assert response.status_code == 404


class TestComicCoverVariants:
    def test_save_cover_variant_stores_covers_individually(self, client, test_user_id, app):
        import base64

        with app.app_context():
            comic = Comic(
                title='Cover Test',
                series='Cover Series',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=test_user_id,
            )
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        primary = base64.b64encode(PRIMARY_COVER_BYTES).decode('utf-8')
        alternate = base64.b64encode(ALTERNATE_COVER_BYTES).decode('utf-8')

        response = client.post(f'/comics/{comic_id}/covers', json={
            'replace': True,
            'cover': {
                'blob_data': primary,
                'mime_type': 'image/jpeg',
                'label': 'Primary Cover',
            },
        })
        assert response.status_code == 200

        response = client.post(f'/comics/{comic_id}/covers', json={
            'replace': False,
            'position': 1,
            'cover': {
                'blob_data': alternate,
                'mime_type': 'image/jpeg',
                'label': 'Variant B',
            },
        })
        assert response.status_code == 200

        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.cover_image == PRIMARY_COVER_BYTES
            assert comic.get_additional_covers(include_blob=True)[0]['blob_data'] == alternate

    def test_set_primary_cover_promotes_variant(self, client, test_user_id, app):
        import base64

        alt_blob = base64.b64encode(ALTERNATE_COVER_BYTES).decode('utf-8')

        with app.app_context():
            comic = Comic(
                title='Cover Test',
                series='Cover Series',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=test_user_id,
                cover_image=PRIMARY_COVER_BYTES,
                cover_image_mime='image/png',
            )
            comic.set_additional_covers([{
                'blob_data': alt_blob,
                'mime_type': 'image/jpeg',
                'label': 'Variant B',
            }])
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id
            cover_id = comic.cover_variants[0].id

        _login_as(client, test_user_id)
        response = client.post(f'/comics/{comic_id}/covers/primary', json={
            'cover_id': cover_id,
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['covers'][0]['is_primary'] is True

        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.cover_image == ALTERNATE_COVER_BYTES
            assert len(comic.get_additional_covers()) == 1
            assert comic.get_additional_covers(include_blob=True)[0]['blob_data'] == base64.b64encode(PRIMARY_COVER_BYTES).decode('utf-8')

        response = client.get(f'/comics/{comic_id}/covers/{cover_id}/image')
        # After promotion the old cover id is gone; new alternate should still serve.
        assert response.status_code in (200, 404)

        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            new_alt_id = comic.cover_variants[0].id

        response = client.get(f'/comics/{comic_id}/covers/{new_alt_id}/image')
        assert response.status_code == 200
        assert response.data == PRIMARY_COVER_BYTES

        response = client.get(f'/comics/{comic_id}/cover/thumbnail')
        assert response.status_code == 200
        assert response.content_type == 'image/webp'
        with Image.open(BytesIO(response.data)) as thumbnail:
            assert thumbnail.format == 'WEBP'
            assert thumbnail.width <= 300
            assert thumbnail.height <= 400

    def test_edit_swap_primary_and_store_alternates(self, client, test_user_id, app):
        import base64

        primary_blob = base64.b64encode(PRIMARY_COVER_BYTES).decode('utf-8')
        alt_blob = base64.b64encode(ALTERNATE_COVER_BYTES).decode('utf-8')

        with app.app_context():
            comic = Comic(
                title='Cover Test',
                series='Cover Series',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=test_user_id,
                cover_image=PRIMARY_COVER_BYTES,
                cover_image_mime='image/png',
            )
            comic.set_additional_covers([{
                'blob_data': alt_blob,
                'mime_type': 'image/jpeg',
                'label': 'Variant B',
            }])
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.post(f'/comics/{comic_id}/edit', data={
            'title': 'Cover Test',
            'series': 'Cover Series',
            'issue_number': '1',
            'publisher': 'Marvel Comics',
            'condition': 'Near Mint',
            'estimated_value': '0',
            'is_wishlist': False,
            'covers_updated': '1',
            'fetched_cover_blob': alt_blob,
            'fetched_cover_mime': 'image/jpeg',
            'additional_covers': f'[{{"blob_data":"{primary_blob}","mime_type":"image/jpeg","label":"Primary Cover"}}]',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Comic updated successfully' in response.data

        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.cover_image == ALTERNATE_COVER_BYTES
            alternates = comic.get_additional_covers(include_blob=True)
            assert len(alternates) == 1
            assert alternates[0]['blob_data'] == primary_blob

    def test_edit_metadata_only_preserves_alternates(self, client, test_user_id, app):
        import base64

        alt_blob = base64.b64encode(ALTERNATE_COVER_BYTES).decode('utf-8')

        with app.app_context():
            comic = Comic(
                title='Cover Test',
                series='Cover Series',
                issue_number='1',
                publisher='Marvel Comics',
                user_id=test_user_id,
                cover_image=PRIMARY_COVER_BYTES,
                cover_image_mime='image/png',
            )
            comic.set_additional_covers([{
                'blob_data': alt_blob,
                'mime_type': 'image/jpeg',
                'label': 'Variant B',
            }])
            db.session.add(comic)
            db.session.commit()
            comic_id = comic.id

        _login_as(client, test_user_id)
        response = client.post(f'/comics/{comic_id}/edit', data={
            'title': 'Cover Test Updated',
            'series': 'Cover Series',
            'issue_number': '1',
            'publisher': 'Marvel Comics',
            'condition': 'Near Mint',
            'estimated_value': '0',
            'is_wishlist': False,
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            comic = db.session.get(Comic, comic_id)
            assert comic.title == 'Cover Test Updated'
            assert comic.cover_image == PRIMARY_COVER_BYTES
            assert len(comic.get_additional_covers()) == 1

