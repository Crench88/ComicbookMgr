"""Tests for comic search parsing and orchestration."""

from unittest.mock import patch

import pytest

from app.services import comicvine as comicvine_module
from app.services.comicvine import (
    parse_query,
    parse_comicvine_issue_id,
    parse_comicvine_volume_id,
    compose_search_query,
    normalize_issue_number,
    _score_volume,
)
from app.services.barcode import extract_barcode
from app.services.search_orchestrator import (
    deduplicate_results,
    rank_results,
    run_comic_search,
)
from app.services.cache import cache_set, cache_get, reset_cache_for_tests


class TestParseQuery:
    def test_star_wars_with_year_and_issue(self):
        parsed = parse_query('Star Wars 1977 #1')
        assert parsed['series'] == 'Star Wars'
        assert parsed['issue'] == '1'
        assert parsed['year'] == 1977

    def test_volume_hint(self):
        parsed = parse_query('Amazing Spider-Man Vol 2 #15')
        assert parsed['series'] == 'Amazing Spider-Man'
        assert parsed['volume_hint'] == '2'
        assert parsed['issue'] == '15'

    def test_comicvine_url(self):
        url = 'https://comicvine.gamespot.com/star-wars-1-star-wars/4000-17616/'
        assert parse_comicvine_issue_id(url) == 17616

    def test_volume_url(self):
        url = 'https://comicvine.gamespot.com/star-wars/4050-2914/'
        assert parse_comicvine_volume_id(url) == 2914


class TestComposeQuery:
    def test_from_series_and_issue_filters(self):
        q = compose_search_query('', 'Star Wars', '1')
        assert q == 'Star Wars #1'


class TestBarcode:
    def test_extracts_digits(self):
        assert extract_barcode('75960607800100111') == '75960607800100111'
        assert extract_barcode('Star Wars') is None


class TestBarcodeSearchPath:
    """ComicVine exposes no UPC field; asking it to filter by one returned junk."""

    def test_issue_fields_never_request_upc(self):
        assert 'upc' not in comicvine_module._ISSUE_FIELDS

    def test_comicvine_upc_helper_is_gone(self):
        assert not hasattr(comicvine_module, 'search_comicvine_by_upc')

    @patch('app.services.search_orchestrator.local_catalog.search_local_database')
    @patch('app.services.search_orchestrator.comicvine.search_comicvine_api')
    @patch('app.services.search_orchestrator.barcode.search_barcode')
    def test_barcode_hit_skips_comicvine(self, mock_barcode, mock_cv, mock_local):
        mock_barcode.return_value = [{
            'title': 'Star Wars #1',
            'series': 'Star Wars',
            'issue_number': '1',
            'publisher': 'Marvel',
            'upc': '75960607800100111',
            'source': 'UPC Database',
        }]
        mock_cv.return_value = []
        mock_local.return_value = []

        results = run_comic_search(
            query='75960607800100111',
            comicvine_api_key='key',
            upc_api_key='upc-key',
        )

        assert [r['source'] for r in results] == ['UPC Database']
        mock_barcode.assert_called_once()
        mock_cv.assert_not_called()

    @patch('app.services.search_orchestrator.local_catalog.search_local_database')
    @patch('app.services.search_orchestrator.comicvine.search_comicvine_api')
    @patch('app.services.search_orchestrator.barcode.search_barcode')
    def test_barcode_miss_falls_through_to_normal_search(self, mock_barcode, mock_cv, mock_local):
        mock_barcode.return_value = []
        mock_cv.return_value = [{
            'title': 'Star Wars #1',
            'series': 'Star Wars',
            'issue_number': '1',
            'publisher': 'Marvel',
            'source': 'ComicVine',
            'comicvine_id': 17616,
        }]
        mock_local.return_value = []

        results = run_comic_search(
            query='75960607800100111',
            comicvine_api_key='key',
            upc_api_key='upc-key',
        )

        # Previously the bogus ComicVine UPC filter always returned rows here,
        # short-circuiting before the real search ever ran.
        mock_cv.assert_called_once()
        assert [r['comicvine_id'] for r in results] == [17616]


class TestDedup:
    def test_dedupes_by_comicvine_id(self):
        results = [
            {'comicvine_id': 17616, 'source': 'ComicVine', 'series': 'Star Wars', 'issue_number': '1'},
            {'comicvine_id': 17616, 'source': 'ComicVine', 'series': 'Star Wars', 'issue_number': '1'},
        ]
        assert len(deduplicate_results(results)) == 1

    def test_local_catalog_ranked_first(self):
        results = [
            {'source': 'ComicVine', 'series': 'Star Wars', 'issue_number': '1', 'volume_start_year': '1977'},
            {'source': 'Series Catalog', 'series': 'Star Wars', 'issue_number': '1'},
        ]
        ranked = rank_results(results, query='Star Wars 1977 #1')
        assert ranked[0]['source'] == 'Series Catalog'


class TestIssueNormalization:
    def test_strips_leading_zeros(self):
        assert normalize_issue_number('001') == '1'
        assert normalize_issue_number('1') == '1'


class TestVolumeScoring:
    def test_volume_hint_boosts_matching_volume(self):
        vol = {'name': 'Amazing Spider-Man Vol. 2', 'aliases': '', 'start_year': '2003'}
        score_with_hint = _score_volume(vol, 'amazing spider-man', None, volume_hint='2')
        score_without = _score_volume(vol, 'amazing spider-man', None)
        assert score_with_hint > score_without


class TestSharedCache:
    def test_cache_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv('CACHE_DIR', str(tmp_path / 'cache'))
        reset_cache_for_tests()
        cache_set('test-key', {'value': 42}, ttl=60)
        assert cache_get('test-key') == {'value': 42}
        reset_cache_for_tests()
