"""Tests for comic price estimation from marketplace comparables."""

from unittest.mock import patch

import pytest

from app import create_app, db
from app.models import User
from app.services.cache import reset_cache_for_tests
from app.services.pricing import ebay, service
from app.services.pricing.comps import (
    issue_matches,
    rejection_reason,
    select_comps,
    series_matches,
)
from app.services.pricing.grades import (
    convert_price_between_grades,
    grade_for_condition,
    grade_value_factor,
    parse_grade,
)
from app.services.pricing.heuristic import heuristic_estimate
from app.services.pricing.stats import summarize, trim_outliers


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Keep eBay tokens and search results out of the real cache directory."""
    monkeypatch.setenv('CACHE_DIR', str(tmp_path / 'cache'))
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def listing(title, price, **extra):
    summary = {
        'itemId': extra.get('item_id', f'v1|{abs(hash(title)) % 10**9}|0'),
        'title': title,
        'price': {'value': str(price), 'currency': extra.get('currency', 'CAD')},
        'itemWebUrl': extra.get('url', 'https://www.ebay.ca/itm/123'),
        'condition': extra.get('condition', 'Used'),
        'categories': extra.get('categories', [{'categoryId': '63', 'categoryName': 'Comics'}]),
    }
    if 'shipping' in extra:
        summary['shippingOptions'] = [
            {'shippingCost': {'value': str(extra['shipping']), 'currency': 'CAD'}}
        ]
    return summary


class TestGradeParsing:
    def test_reads_a_slabbed_grade_and_grader(self):
        parsed = parse_grade('Amazing Spider-Man #300 CGC 9.8 White Pages')
        assert parsed['grade'] == 9.8
        assert parsed['slabbed'] is True
        assert parsed['grader'] == 'CGC'

    def test_reads_letter_grades(self):
        assert parse_grade('Batman #423 VF/NM')['grade'] == 9.0
        assert parse_grade('Batman #423 Very Fine')['grade'] == 8.0
        assert parse_grade('Batman #423 VG')['grade'] == 4.0

    def test_near_mint_is_not_read_as_mint(self):
        assert parse_grade('X-Men #101 Near Mint')['grade'] == 9.4
        assert parse_grade('X-Men #101 NM')['grade'] == 9.4

    def test_raw_numeric_grade_is_not_treated_as_slabbed(self):
        parsed = parse_grade('Saga #1 9.4 gorgeous copy')
        assert parsed['grade'] == 9.4
        assert parsed['slabbed'] is False

    def test_ungraded_listing_reports_no_grade(self):
        parsed = parse_grade('Hellboy Seed of Destruction #1 Dark Horse 1994')
        assert parsed['grade'] is None
        assert parsed['slabbed'] is False

    def test_a_price_is_not_mistaken_for_a_grade(self):
        assert parse_grade('Spawn #1 $9.99 free shipping')['grade'] is None


class TestGradeConversion:
    def test_higher_grades_are_worth_more(self):
        assert grade_value_factor(9.8) > grade_value_factor(9.4) > grade_value_factor(4.0)

    def test_condition_names_map_to_the_ten_point_scale(self):
        assert grade_for_condition('Near Mint') == 9.4
        assert grade_for_condition('very good') == 4.0

    def test_a_blank_condition_is_treated_as_very_fine(self):
        assert grade_for_condition('') == 8.0
        assert grade_for_condition(None) == 8.0

    def test_converting_down_a_grade_lowers_the_price(self):
        low = convert_price_between_grades(100.0, 9.4, 4.0)
        assert 0 < low < 100

    def test_converting_to_the_same_grade_keeps_the_price(self):
        assert convert_price_between_grades(42.0, 8.0, 8.0) == pytest.approx(42.0)


class TestCompScreening:
    def test_issue_number_must_match(self):
        assert issue_matches('Batman #423 VF', '423')
        assert issue_matches('Batman 423 1988', '423')
        assert not issue_matches('Batman #424 VF', '423')

    def test_leading_zeroes_still_match(self):
        assert issue_matches('Batman #007', '7')

    def test_series_name_must_mostly_match(self):
        assert series_matches('Amazing Spider-Man #300', 'Amazing Spider-Man')
        assert not series_matches('Detective Comics #27', 'Amazing Spider-Man')

    @pytest.mark.parametrize(
        'title,reason',
        [
            ('Batman #423 lot of 12 comics', 'multi-issue lot'),
            ('Batman #423 poster print', 'not a comic'),
            ('Batman #423 facsimile edition', 'reprint or facsimile'),
            ('Batman #423 signed by Todd McFarlane', 'signed or remarked'),
            ('Batman Omnibus #423 hardcover', 'collected edition'),
            ('Superman #423', 'different series'),
            ('Batman #500', 'different issue'),
        ],
    )
    def test_unusable_listings_are_rejected(self, title, reason):
        assert rejection_reason(title, series='Batman', issue_number='423') == reason

    def test_a_clean_listing_is_accepted(self):
        assert rejection_reason('Batman #423 Marvel 1988 VF', series='Batman', issue_number='423') is None

    def test_slabbed_and_raw_are_separated(self):
        summaries = [
            listing('Batman #423 VF', 40),
            listing('Batman #423 CGC 9.6', 900),
        ]
        raw, _ = select_comps(summaries, series='Batman', issue_number='423')
        assert len(raw) == 1
        assert raw[0]['price'] == 40

        both, _ = select_comps(
            summaries, series='Batman', issue_number='423', include_slabbed=True
        )
        assert len(both) == 2

    def test_shipping_is_added_to_the_comparable_price(self):
        summaries = [listing('Batman #423 VF', 30, shipping=8.5)]
        comps, _ = select_comps(summaries, series='Batman', issue_number='423')
        assert comps[0]['total'] == 38.5

    def test_non_comic_categories_are_rejected(self):
        summaries = [
            listing(
                'Batman #423 model kit',
                25,
                categories=[{'categoryId': '220', 'categoryName': 'Toys & Hobbies'}],
            )
        ]
        comps, rejected = select_comps(summaries, series='Batman', issue_number='423')
        assert comps == []
        assert rejected == {'not a comic': 1}


class TestStatistics:
    def test_outliers_are_trimmed(self):
        kept, dropped = trim_outliers([10, 11, 12, 12, 13, 14, 900])
        assert 900 in dropped
        assert 900 not in kept

    def test_small_samples_are_kept_whole(self):
        kept, dropped = trim_outliers([10, 900])
        assert dropped == []
        assert kept == [10.0, 900.0]

    def test_summary_reports_a_median_and_range(self):
        summary = summarize([10, 12, 14, 16, 18, 20])
        assert summary['median'] == pytest.approx(15.0)
        assert summary['low'] < summary['median'] < summary['high']
        assert summary['sample_size'] == 6

    def test_no_values_means_no_summary(self):
        assert summarize([]) is None


class TestHeuristicFallback:
    def test_it_is_deterministic(self):
        first = heuristic_estimate(series='Batman', issue_number='423', publisher='DC Comics', condition='Fine')
        second = heuristic_estimate(series='Batman', issue_number='423', publisher='DC Comics', condition='Fine')
        assert first == second

    def test_publisher_names_with_extra_words_still_match(self):
        matched = heuristic_estimate(series='Batman', issue_number='423', publisher='DC Comics')
        unmatched = heuristic_estimate(series='Batman', issue_number='423', publisher='Nobody')
        assert matched['publisher_key'] == 'dc'
        assert matched['series_key'] == 'batman'
        assert unmatched['publisher_key'] == 'default'

    def test_longer_series_names_win(self):
        estimate = heuristic_estimate(
            series='Amazing Spider-Man', issue_number='300', publisher='Marvel Comics'
        )
        assert estimate['series_key'] == 'amazing spider-man'

    def test_worse_condition_is_worth_less(self):
        near_mint = heuristic_estimate(series='Batman', issue_number='423', publisher='DC', condition='Near Mint')
        poor = heuristic_estimate(series='Batman', issue_number='423', publisher='DC', condition='Poor')
        assert poor['value'] < near_mint['value']


class TestEbayClient:
    def test_canada_is_the_default_marketplace(self, monkeypatch):
        monkeypatch.delenv('EBAY_MARKETPLACE_ID', raising=False)
        assert ebay.marketplace_id() == 'EBAY_CA'
        details = ebay.marketplace_details('EBAY_CA')
        assert details['currency'] == 'CAD'
        assert details['site'] == 'ebay.ca'

    def test_missing_credentials_raise(self, monkeypatch):
        monkeypatch.delenv('EBAY_CLIENT_ID', raising=False)
        monkeypatch.delenv('EBAY_CLIENT_SECRET', raising=False)
        with pytest.raises(ebay.EbayCredentialsMissing):
            ebay.access_token()

    def test_the_token_is_cached_between_calls(self, monkeypatch):
        monkeypatch.setenv('EBAY_CLIENT_ID', 'client-id')
        monkeypatch.setenv('EBAY_CLIENT_SECRET', 'client-secret')

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {'access_token': 'token-abc', 'expires_in': 7200}

        with patch('app.services.pricing.ebay.requests.post', return_value=Response()) as post:
            assert ebay.access_token() == 'token-abc'
            assert ebay.access_token() == 'token-abc'
        assert post.call_count == 1

    def test_the_search_targets_canada(self, monkeypatch):
        monkeypatch.setenv('EBAY_CLIENT_ID', 'client-id')
        monkeypatch.setenv('EBAY_CLIENT_SECRET', 'client-secret')

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {'itemSummaries': [listing('Batman #423 VF', 30)]}

        with patch('app.services.pricing.ebay.access_token', return_value='token'), patch(
            'app.services.pricing.ebay.requests.get', return_value=Response()
        ) as get:
            summaries = ebay.search_item_summaries('Batman #423')

        assert len(summaries) == 1
        _, kwargs = get.call_args
        assert kwargs['headers']['X-EBAY-C-MARKETPLACE-ID'] == 'EBAY_CA'
        assert 'country=CA' in kwargs['headers']['X-EBAY-C-ENDUSERCTX']
        assert 'deliveryCountry:CA' in kwargs['params']['filter']
        assert 'FIXED_PRICE' in kwargs['params']['filter']

    def test_identical_searches_hit_the_cache(self, monkeypatch):
        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {'itemSummaries': [listing('Batman #423 VF', 30)]}

        with patch('app.services.pricing.ebay.access_token', return_value='token'), patch(
            'app.services.pricing.ebay.requests.get', return_value=Response()
        ) as get:
            ebay.search_item_summaries('Batman #423')
            ebay.search_item_summaries('Batman #423')
        assert get.call_count == 1


def fake_search(summaries):
    def _search(*args, **kwargs):
        return summaries

    return _search


class TestEstimateMarketValue:
    def test_it_prices_from_canadian_listings(self, monkeypatch):
        monkeypatch.setenv('EBAY_MARKETPLACE_ID', 'EBAY_CA')
        summaries = [
            listing('Batman #423 VF', 40),
            listing('Batman #423 Very Fine', 44),
            listing('Batman #423 VF+', 46),
            listing('Batman #423 VF', 42),
            listing('Batman #423 VF', 48),
            listing('Batman #423 lot of 20 comics', 300),
            listing('Batman #423 CGC 9.8', 1200),
            listing('Batman #424 VF', 39),
        ]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            estimate = service.estimate_market_value(
                series='Batman', issue_number='423', publisher='DC Comics', condition='Very Fine'
            )

        assert estimate['source'] == 'ebay'
        assert estimate['currency'] == 'CAD'
        assert estimate['marketplace'] == 'EBAY_CA'
        assert estimate['sample_size'] == 5
        assert estimate['low'] <= estimate['value'] <= estimate['high']
        assert 'ebay.ca' in estimate['search_url']
        # Every comp shown is the right issue, raw, and a single book.
        assert all('#423' in comp['title'] for comp in estimate['comps'])
        assert all(not comp['slabbed'] for comp in estimate['comps'])
        assert estimate['slab_comps'] and estimate['slab_comps'][0]['slabbed']

    def test_the_estimate_sits_below_the_asking_prices(self, monkeypatch):
        monkeypatch.setenv('PRICE_ASK_TO_SOLD_RATIO', '0.8')
        summaries = [listing(f'Batman #423 VF copy {index}', 50) for index in range(6)]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            estimate = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Very Fine'
            )
        assert estimate['median_ask'] == pytest.approx(50.0)
        assert estimate['value'] == pytest.approx(40.0)

    def test_condition_changes_the_estimate(self, monkeypatch):
        summaries = [listing(f'Batman #423 CGC-free raw NM copy {index}', 100) for index in range(6)]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            near_mint = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Near Mint'
            )
            very_good = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Very Good'
            )
        assert very_good['value'] < near_mint['value']

    def test_copies_in_a_far_off_grade_are_left_out(self):
        summaries = [
            listing('Batman #423 VF', 200),
            listing('Batman #423 VF+', 220),
            listing('Batman #423 Near Mint', 260),
            listing('Batman #423 FN/VF', 170),
            listing('Batman #423 PR poor reading copy', 12),
        ]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            estimate = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Very Fine'
            )
        assert estimate['sample_size'] == 4
        assert all('poor' not in comp['title'].lower() for comp in estimate['comps'])

    def test_far_off_grades_are_used_only_as_a_last_resort(self):
        summaries = [
            listing('Batman #423 CGC-free raw NM copy', 260),
            listing('Batman #423 Near Mint', 250),
            listing('Batman #423 NM+', 280),
            listing('Batman #423 Near Mint unread', 270),
        ]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            estimate = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Poor'
            )
        assert estimate['source'] == 'ebay'
        assert any('different grades' in note for note in estimate['notes'])
        assert estimate['confidence'] in ('low', 'very low')

    def test_confidence_reflects_the_sample(self, monkeypatch):
        many = [listing(f'Batman #423 VF copy {index}', 40 + index) for index in range(12)]
        few = [listing('Batman #423 VF', 40), listing('Batman #423 VF+', 300)]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(many)):
            confident = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Very Fine'
            )
        with patch.object(service.ebay, 'search_item_summaries', fake_search(few)):
            unsure = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Very Fine'
            )
        assert confident['confidence'] == 'high'
        assert unsure['confidence'] in ('low', 'very low')

    def test_missing_credentials_fall_back_to_an_offline_estimate(self, monkeypatch):
        monkeypatch.delenv('EBAY_CLIENT_ID', raising=False)
        monkeypatch.delenv('EBAY_CLIENT_SECRET', raising=False)
        estimate = service.estimate_market_value(
            series='Batman', issue_number='423', publisher='DC Comics', condition='Fine'
        )
        assert estimate['source'] == 'estimate'
        assert estimate['value'] > 0
        assert any('EBAY_CLIENT_ID' in note for note in estimate['notes'])

    def test_an_ebay_outage_falls_back_instead_of_failing(self):
        def explode(*args, **kwargs):
            raise ebay.EbayApiError('eBay search failed (HTTP 503).')

        with patch.object(service.ebay, 'search_item_summaries', explode):
            estimate = service.estimate_market_value(
                series='Batman', issue_number='423', publisher='DC Comics'
            )
        assert estimate['source'] == 'estimate'
        assert any('503' in note for note in estimate['notes'])

    def test_no_comparables_falls_back_and_says_so(self):
        summaries = [listing('Some Other Book #1 VF', 10)]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            estimate = service.estimate_market_value(
                series='Batman', issue_number='423', publisher='DC Comics'
            )
        assert estimate['source'] == 'estimate'
        assert estimate['search_url']
        assert estimate['rejected']

    def test_slab_only_results_do_not_price_a_raw_copy(self):
        summaries = [listing(f'Batman #423 CGC 9.{index}', 500 + index) for index in range(4)]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            estimate = service.estimate_market_value(
                series='Batman', issue_number='423', condition='Very Fine'
            )
        assert estimate['source'] == 'estimate'
        assert any('slabbed' in note for note in estimate['notes'])


@pytest.fixture
def pricing_app():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
    })
    with app.app_context():
        db.create_all()
        user = User(username='pricer', email='pricer@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        yield app, user_id
        db.session.remove()
        db.drop_all()


@pytest.fixture
def pricing_client(pricing_app):
    app, user_id = pricing_app
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
    return client


class TestValueLookupEndpoint:
    def test_it_returns_the_estimate_and_its_comparables(self, pricing_client):
        summaries = [listing(f'Batman #423 VF copy {index}', 40 + index) for index in range(6)]
        with patch.object(service.ebay, 'search_item_summaries', fake_search(summaries)):
            response = pricing_client.post(
                '/comics/ai-value-lookup',
                json={
                    'series': 'Batman',
                    'issue_number': '423',
                    'publisher': 'DC Comics',
                    'condition': 'Very Fine',
                },
            )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload['success'] is True
        estimate = payload['estimate']
        assert estimate['source'] == 'ebay'
        assert estimate['currency'] == 'CAD'
        assert estimate['comps']
        # The flat value is still there for anything reading the old contract.
        assert payload['estimated_value'] == estimate['value']

    def test_it_needs_something_to_search_for(self, pricing_client):
        response = pricing_client.post('/comics/ai-value-lookup', json={'publisher': 'DC'})
        assert response.status_code == 400
        assert response.get_json()['success'] is False

    def test_it_requires_a_login(self, pricing_app):
        app, _ = pricing_app
        response = app.test_client().post('/comics/ai-value-lookup', json={'series': 'Batman'})
        assert response.status_code in (301, 302, 401)
