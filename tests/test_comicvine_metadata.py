import pytest
from unittest.mock import patch

from app.services.comicvine import (
    _extract_issue_description,
    _extract_person_credits,
    _format_issue_lightweight,
    _strip_html,
)


class TestComicVineMetadataExtraction:
    def test_strip_html(self):
        assert _strip_html('<p>Hello <strong>world</strong></p>') == 'Hello world'

    def test_extract_person_credits(self):
        result = {
            'person_credits': [
                {'name': 'Stan Lee', 'role': 'writer'},
                {'name': 'Steve Ditko', 'role': 'penciler'},
                {'name': 'Steve Ditko', 'role': 'inker'},
                {'name': 'Marie Severin', 'role': 'colorist'},
                {'name': 'Sam Rosen', 'role': 'letterer'},
                {'name': 'Stan Lee', 'role': 'editor'},
                {'name': 'Jack Kirby', 'role': 'cover'},
            ],
        }
        credits = _extract_person_credits(result)
        assert credits['writer'] == 'Stan Lee'
        assert credits['penciler'] == 'Steve Ditko'
        assert credits['inker'] == 'Steve Ditko'
        assert credits['colorist'] == 'Marie Severin'
        assert credits['letterer'] == 'Sam Rosen'
        assert credits['editor'] == 'Stan Lee'
        assert credits['cover_artist'] == 'Jack Kirby'

    def test_combined_roles_credit_the_person_under_each_one(self):
        """ComicVine returns every role a person held as one comma-joined string."""
        credits = _extract_person_credits({
            'person_credits': [
                {'name': 'Ernie Chan', 'role': 'penciler, inker, cover'},
                {'name': 'Tatjana Wood', 'role': 'colorist, cover'},
            ],
        })
        assert credits['penciler'] == 'Ernie Chan'
        assert credits['inker'] == 'Ernie Chan'
        assert credits['colorist'] == 'Tatjana Wood'
        assert credits['cover_artist'] == 'Ernie Chan, Tatjana Wood'

    def test_support_roles_are_captured(self):
        credits = _extract_person_credits({
            'person_credits': [
                {'name': 'Nick Lowe', 'role': 'editor'},
                {'name': 'Kaeden McGahey', 'role': 'editor, assistant'},
                {'name': 'Jay Bowen', 'role': 'designer'},
                {'name': 'Salena Mahina', 'role': 'production'},
                {'name': 'Stephen Paul', 'role': 'translator'},
            ],
        })
        assert credits['editor'] == 'Nick Lowe, Kaeden McGahey'
        assert credits['assistant_editor'] == 'Kaeden McGahey'
        assert credits['designer'] == 'Jay Bowen'
        assert credits['production'] == 'Salena Mahina'
        assert credits['translator'] == 'Stephen Paul'

    def test_unlabelled_and_unknown_roles_land_in_other(self):
        """Nobody should be dropped just because their role is not in the map."""
        credits = _extract_person_credits({
            'person_credits': [
                {'name': 'C.B. Cebulski', 'role': 'editor, other'},
                {'name': 'Some Reporter', 'role': 'journalist'},
                {'name': 'Future Role', 'role': 'hologram wrangler'},
                {'name': 'No Role At All', 'role': ''},
            ],
        })
        assert credits['other_credits'] == (
            'C.B. Cebulski, Some Reporter, Future Role, No Role At All'
        )
        assert credits['editor'] == 'C.B. Cebulski'

    def test_extract_issue_description_prefers_deck_and_full_text(self):
        result = {
            'deck': 'Spider-Man faces the Green Goblin.',
            'description': '<p>Extended <i>synopsis</i> with more detail.</p>',
        }
        text = _extract_issue_description(result)
        assert 'Spider-Man faces the Green Goblin.' in text
        assert 'Extended synopsis with more detail.' in text

    def test_format_issue_lightweight_includes_metadata(self):
        raw = {
            'id': 17616,
            'name': 'Spider-Man No More!',
            'issue_number': '50',
            'publisher': {'name': 'Marvel Comics'},
            'character_credits': [{'name': 'Spider-Man'}, {'name': 'Kingpin'}],
            'person_credits': [
                {'name': 'Stan Lee', 'role': 'writer'},
                {'name': 'John Romita', 'role': 'penciler'},
            ],
            'team_credits': [{'name': 'Daily Bugle'}],
            'story_arc_credits': [{'name': 'Spider-Man No More'}],
            'deck': 'Peter Parker quits being Spider-Man.',
            'description': '<p>Full issue description.</p>',
            'store_date': '1967-07-01',
            'cover_date': '1967-07-01',
            'site_detail_url': 'https://comicvine.gamespot.com/amazing-spider-man-50/4000-17616/',
            'image': {'medium_url': 'https://example.com/cover.jpg'},
            'volume': {'id': 123, 'name': 'The Amazing Spider-Man', 'start_year': '1963'},
        }
        formatted = _format_issue_lightweight(raw)
        assert formatted['writer'] == 'Stan Lee'
        assert formatted['penciler'] == 'John Romita'
        assert formatted['characters'] == 'Spider-Man, Kingpin'
        assert formatted['teams'] == 'Daily Bugle'
        assert formatted['story_arc'] == 'Spider-Man No More'
        assert formatted['comicvine_url'].endswith('/4000-17616/')
        assert 'Peter Parker quits' in formatted['description']


class TestLookupIssueMetadataForRefresh:
    @patch('app.services.comicvine.fetch_issue_by_id')
    def test_refresh_uses_stored_comicvine_id(self, mock_fetch):
        from app.services.comicvine import lookup_issue_metadata_for_refresh
        mock_fetch.return_value = {'id': 17616, 'title': 'Test', 'writer': 'Stan Lee'}
        result = lookup_issue_metadata_for_refresh(
            comicvine_issue_id=17616,
            series='Spider-Man',
            issue_number='50',
            api_key='fake-key',
        )
        assert result['matched_by'] == 'comicvine_id'
        mock_fetch.assert_called_once_with(17616, 'fake-key')

    @patch('app.services.comicvine.fetch_issue_by_id')
    @patch('app.services.comicvine.search_comicvine_api')
    def test_refresh_falls_back_to_search(self, mock_search, mock_fetch):
        from app.services.comicvine import lookup_issue_metadata_for_refresh
        mock_search.return_value = [{
            'id': 99,
            'comicvine_id': 99,
            'title': 'ROM #1',
            'issue_number': '1',
            'writer': 'Bill Mantlo',
        }]
        mock_fetch.return_value = {
            'id': 99,
            'comicvine_id': 99,
            'title': 'ROM #1',
            'issue_number': '1',
            'writer': 'Bill Mantlo',
            'artist': 'Sal Buscema',
        }
        result = lookup_issue_metadata_for_refresh(
            series='ROM',
            issue_number='1',
            publisher='Marvel Comics',
            api_key='fake-key',
        )
        assert result['matched_by'] == 'search'
        assert result['metadata']['writer'] == 'Bill Mantlo'
        mock_fetch.assert_called_once_with(99, 'fake-key')

