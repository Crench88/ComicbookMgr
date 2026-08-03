import pytest

from app.services.comicvine import lookup_covers_for_form, _upgrade_cover_url


class TestCoverHelpers:
    def test_upgrade_cover_url(self):
        url = 'https://comicvine.gamespot.com/a/uploads/scale_medium/1/2.jpg'
        assert 'scale_large' in _upgrade_cover_url(url)

    @pytest.mark.parametrize('ranges,expected_count', [
        ('1-3', 3),
        ('1-14, 16-22', 21),
    ])
    def test_parse_ranges_placeholder(self, ranges, expected_count):
        from app.services.bulk_add import parse_issue_ranges
        assert len(parse_issue_ranges(ranges)) == expected_count


class TestLookupCoversForForm:
    def test_missing_api_key(self):
        result = lookup_covers_for_form(series='ROM', issue_number='1', api_key='')
        assert result['covers'] == []
        assert 'API key' in result['error']

    def test_no_inputs(self):
        result = lookup_covers_for_form(series='', issue_number='', title='', api_key='fake-key')
        assert result['covers'] == []
