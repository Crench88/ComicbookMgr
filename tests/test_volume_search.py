import pytest
from unittest.mock import patch

from app.services.comicvine import (
    is_north_american_publisher,
    publisher_matches_filter,
    search_comicvine_volumes,
    search_comicvine_issues_in_volume,
    search_comicvine_api,
)


class TestNorthAmericanPublisherFilter:
    def test_na_publishers_allowed(self):
        assert is_north_american_publisher('Marvel Comics')
        assert is_north_american_publisher('DC Comics')
        assert is_north_american_publisher('Image Comics')
        assert is_north_american_publisher('Dark Horse Comics')
        assert is_north_american_publisher('IDW Publishing')

    def test_foreign_publishers_excluded(self):
        assert not is_north_american_publisher('Panini Comics')
        assert not is_north_american_publisher('Editorial Novaro')
        assert not is_north_american_publisher('ECC Ediciones')
        assert not is_north_american_publisher('Marvel UK')

    def test_explicit_publisher_overrides_na_filter(self):
        assert publisher_matches_filter(
            'Panini Comics',
            explicit_publisher='Panini',
            na_only=True,
        )
        assert not publisher_matches_filter(
            'Panini Comics',
            explicit_publisher='',
            na_only=True,
        )


class TestVolumeSearch:
    @patch('app.services.comicvine._cv_get')
    def test_search_comicvine_volumes_filters_publisher(self, mock_cv_get):
        mock_cv_get.return_value = {
            'results': [
                {
                    'id': 796,
                    'name': 'Batman',
                    'start_year': '1940',
                    'count_of_issues': 716,
                    'publisher': {'name': 'DC Comics'},
                },
                {
                    'id': 126840,
                    'name': 'Batman',
                    'start_year': '1954',
                    'count_of_issues': 100,
                    'publisher': {'name': 'Editorial Novaro'},
                },
            ],
        }
        volumes = search_comicvine_volumes('Batman', 'fake-key', publisher='DC Comics')
        assert len(volumes) == 1
        assert volumes[0]['comicvine_volume_id'] == 796
        assert volumes[0]['start_year'] == '1940'

    @patch('app.services.comicvine._cv_get')
    def test_search_comicvine_volumes_excludes_foreign_by_default(self, mock_cv_get):
        mock_cv_get.return_value = {
            'results': [
                {
                    'id': 796,
                    'name': 'Batman',
                    'start_year': '1940',
                    'count_of_issues': 716,
                    'publisher': {'name': 'DC Comics'},
                },
                {
                    'id': 126840,
                    'name': 'Batman',
                    'start_year': '1954',
                    'count_of_issues': 100,
                    'publisher': {'name': 'Editorial Novaro'},
                },
            ],
        }
        volumes = search_comicvine_volumes('Batman', 'fake-key')
        assert len(volumes) == 1
        assert volumes[0]['publisher'] == 'DC Comics'

    @patch('app.services.comicvine._enrich_with_volume_meta')
    @patch('app.services.comicvine._fetch_issues_for_one_volume')
    def test_search_issues_in_volume(self, mock_fetch, mock_enrich):
        mock_fetch.return_value = [{
            'id': 123,
            'name': 'Test Issue',
            'issue_number': '1',
            'publisher': {'name': 'Marvel'},
            'image': {'medium_url': 'https://example.com/cover.jpg'},
            'volume': {'id': 999, 'name': 'Test Series', 'start_year': '1963'},
        }]
        results = search_comicvine_issues_in_volume(999, 'fake-key', issue_number='1')
        assert len(results) == 1
        assert results[0]['issue_number'] == '1'

    @patch('app.services.comicvine._enrich_with_volume_meta')
    @patch('app.services.comicvine._fetch_issues_for_volumes')
    @patch('app.services.comicvine._find_volume_ids')
    def test_search_keeps_issues_after_publisher_enrich(self, mock_find, mock_fetch, mock_enrich):
        mock_find.return_value = [2914]
        mock_fetch.return_value = [{
            'id': 19312,
            'name': 'Deathgame',
            'issue_number': '20',
            'volume': {'id': 2914, 'name': 'Star Wars'},
        }]

        def _enrich(results, api_key):
            for r in results:
                r['publisher'] = 'Marvel Comics'

        mock_enrich.side_effect = _enrich

        results = search_comicvine_api(
            'Star Wars #20',
            'fake-key',
            na_publishers_only=True,
        )
        assert len(results) == 1
        assert results[0]['publisher'] == 'Marvel Comics'

    @patch('app.services.comicvine._enrich_with_volume_meta')
    @patch('app.services.comicvine._freetext_issue_search')
    @patch('app.services.comicvine._find_volume_ids')
    def test_search_api_filters_non_na_issues(self, mock_find_vols, mock_freetext, mock_enrich):
        mock_find_vols.return_value = []
        mock_freetext.return_value = [
            {
                'id': 1,
                'name': 'Amazing Spider-Man #1',
                'issue_number': '1',
                'publisher': {'name': 'Marvel Comics'},
                'image': {'medium_url': 'https://example.com/marvel.jpg'},
                'volume': {'id': 100, 'name': 'Amazing Spider-Man', 'start_year': '1963'},
            },
            {
                'id': 2,
                'name': 'Amazing Spider-Man #1',
                'issue_number': '1',
                'publisher': {'name': 'Panini Comics'},
                'image': {'medium_url': 'https://example.com/panini.jpg'},
                'volume': {'id': 200, 'name': 'Amazing Spider-Man', 'start_year': '2012'},
            },
        ]
        results = search_comicvine_api(
            'Amazing Spider-Man #1',
            'fake-key',
            na_publishers_only=True,
        )
        assert len(results) == 1
        assert results[0]['publisher'] == 'Marvel Comics'
