
import pytest
from unittest.mock import patch

from app.services.bulk_add import parse_issue_ranges


class TestBulkAddVolumeLookup:
    @patch('app.services.bulk_add.search_comicvine_api')
    def test_lookup_issue_uses_volume_id(self, mock_search):
        mock_search.return_value = [{
            'series': 'Batman',
            'issue_number': '1',
            'title': 'The Legend of the Batman',
            'publisher': 'DC Comics',
        }]
        from app.services.bulk_add import lookup_issue_for_bulk
        result = lookup_issue_for_bulk(
            series='Batman',
            issue_number='1',
            api_key='fake-key',
            volume_id=796,
        )
        assert result['issue_number'] == '1'
        mock_search.assert_called_once_with(
            '',
            'fake-key',
            series_name='Batman',
            issue_number='1',
            volume_id=796,
        )

    def test_simple_range(self):
        assert parse_issue_ranges('1-5') == ['1', '2', '3', '4', '5']

    def test_gapped_ranges(self):
        assert parse_issue_ranges('1-3, 5, 7-9') == ['1', '2', '3', '5', '7', '8', '9']

    def test_rom_example(self):
        assert parse_issue_ranges('1-14, 16-22, 24-32') == (
            [str(i) for i in list(range(1, 15)) + list(range(16, 23)) + list(range(24, 33))]
        )

    def test_deduplicates(self):
        assert parse_issue_ranges('1-3, 3-5') == ['1', '2', '3', '4', '5']

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError, match='Invalid range'):
            parse_issue_ranges('abc')

    def test_reversed_range_raises(self):
        with pytest.raises(ValueError, match='end must be'):
            parse_issue_ranges('10-5')

    def test_max_limit_raises(self):
        with pytest.raises(ValueError, match='100 issues'):
            parse_issue_ranges('1-101')
