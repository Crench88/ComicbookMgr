"""Comic price estimation from live marketplace comparables."""

from __future__ import annotations

import os
from urllib.parse import quote_plus

from . import ebay
from .comps import select_comps
from .grades import (
    convert_price_between_grades,
    grade_for_condition,
    grade_label,
)
from .heuristic import heuristic_estimate
from .stats import confidence_for, summarize

# Raw listings that state no grade are treated as Very Fine, the middle of what
# sellers of unslabbed back issues typically offer.
ASSUMED_RAW_GRADE = 8.0

# Converting a price across a wide grade gap amplifies error: a beaten-up copy
# restated five grades higher becomes nonsense. Prefer comps near the target
# grade and only widen the net when too few remain.
PREFERRED_GRADE_WINDOW = 2.0
MIN_COMPS_IN_WINDOW = 4

_CONFIDENCE_LADDER = ('high', 'medium', 'low', 'very low')

# Asking prices sit above what books actually sell for. Applied to translate the
# median ask into a likely sale price; tune with PRICE_ASK_TO_SOLD_RATIO.
DEFAULT_ASK_TO_SOLD_RATIO = 0.8

SEARCH_LIMIT = 100
DEFAULT_COMP_LIMIT = 8


def _setting(name, default=''):
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            value = current_app.config.get(name)
            if value not in (None, ''):
                return value
    except Exception:  # pragma: no cover
        pass
    return os.environ.get(name, default)


def ask_to_sold_ratio():
    try:
        ratio = float(_setting('PRICE_ASK_TO_SOLD_RATIO', DEFAULT_ASK_TO_SOLD_RATIO))
    except (TypeError, ValueError):
        return DEFAULT_ASK_TO_SOLD_RATIO
    if not 0.2 <= ratio <= 1.0:
        return DEFAULT_ASK_TO_SOLD_RATIO
    return ratio


def build_query(series, issue_number, title=''):
    """Keyword query for a single issue."""
    series = (series or '').strip()
    issue_number = str(issue_number or '').strip()
    if not series:
        series = (title or '').strip()
    if not series:
        return ''
    if issue_number:
        return f'{series} #{issue_number}'
    return series


def browse_url(query, marketplace=None):
    """Human-facing search URL, so the estimate can be double-checked."""
    site = ebay.marketplace_details(marketplace)['site']
    return f'https://www.{site}/sch/i.html?_nkw={quote_plus(query)}'


def _adjust_comps(comps, target_grade):
    """Restate every comp as the equivalent price for the target grade."""
    adjusted = []
    for comp in comps:
        source_grade = comp['grade']
        assumed = source_grade is None
        if assumed:
            source_grade = ASSUMED_RAW_GRADE
        entry = dict(comp)
        entry['source_grade'] = source_grade
        entry['assumed_grade'] = assumed
        entry['adjusted'] = round(
            convert_price_between_grades(comp['total'], source_grade, target_grade), 2
        )
        adjusted.append(entry)
    return adjusted


def _comps_near_grade(comps, target_grade):
    """Keep comps graded close to the target, widening the net if too few."""
    near = [
        comp for comp in comps
        if abs(comp['source_grade'] - target_grade) <= PREFERRED_GRADE_WINDOW
    ]
    if len(near) >= MIN_COMPS_IN_WINDOW:
        return near, True
    return comps, False


def _downgrade_confidence(level):
    try:
        index = _CONFIDENCE_LADDER.index(level)
    except ValueError:
        return level
    return _CONFIDENCE_LADDER[min(index + 1, len(_CONFIDENCE_LADDER) - 1)]


def _heuristic_result(*, series, issue_number, publisher, condition, title, notes):
    estimate = heuristic_estimate(
        series=series,
        issue_number=issue_number,
        publisher=publisher,
        condition=condition,
        title=title,
    )
    grade = estimate['grade']
    return {
        'value': estimate['value'],
        'low': estimate['low'],
        'high': estimate['high'],
        'currency': ebay.marketplace_details()['currency'],
        'source': 'estimate',
        'source_label': 'Offline estimate',
        'marketplace': None,
        'condition': condition or '',
        'grade': grade,
        'grade_label': grade_label(grade),
        'basis': 'Typical back-issue prices for this publisher and series, not live listings.',
        'confidence': 'low',
        'confidence_note': 'No marketplace comparables were used.',
        'sample_size': 0,
        'comps': [],
        'slab_comps': [],
        'rejected': {},
        'query': build_query(series, issue_number, title),
        'search_url': '',
        'notes': notes,
    }


def estimate_market_value(
    *,
    series='',
    issue_number='',
    publisher='',
    condition='',
    title='',
    marketplace=None,
    comp_limit=DEFAULT_COMP_LIMIT,
    search_limit=SEARCH_LIMIT,
    use_cache=True,
):
    """Estimate what a comic is worth from active eBay listings.

    Falls back to an offline estimate when eBay is unconfigured, unreachable, or
    has nothing comparable. The result always states which of the two it is.
    """
    query = build_query(series, issue_number, title)
    if not query:
        return _heuristic_result(
            series=series,
            issue_number=issue_number,
            publisher=publisher,
            condition=condition,
            title=title,
            notes=['Add a series or title before estimating a value.'],
        )

    market = (marketplace or ebay.marketplace_id()).upper()
    details = ebay.marketplace_details(market)
    target_grade = grade_for_condition(condition)
    notes = []

    try:
        summaries = ebay.search_item_summaries(
            query,
            marketplace=market,
            limit=search_limit,
            category_id=_setting('EBAY_COMIC_CATEGORY_ID', '') or None,
            use_cache=use_cache,
        )
    except ebay.EbayCredentialsMissing:
        return _heuristic_result(
            series=series,
            issue_number=issue_number,
            publisher=publisher,
            condition=condition,
            title=title,
            notes=[
                'eBay is not configured, so this is an offline estimate. '
                'Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET for live prices.'
            ],
        )
    except ebay.EbayApiError as exc:
        return _heuristic_result(
            series=series,
            issue_number=issue_number,
            publisher=publisher,
            condition=condition,
            title=title,
            notes=[f'eBay lookup failed, so this is an offline estimate. {exc}'],
        )

    usable, rejected = select_comps(
        summaries, series=series or title, issue_number=issue_number, include_slabbed=True
    )
    raw_comps = [comp for comp in usable if not comp['slabbed']]
    slab_comps = [comp for comp in usable if comp['slabbed']]

    adjusted = _adjust_comps(raw_comps, target_grade)
    adjusted, grades_are_close = _comps_near_grade(adjusted, target_grade)
    summary = summarize([comp['adjusted'] for comp in adjusted])

    if not summary:
        notes.append(
            f'No comparable raw copies were listed on {details["site"]}, '
            'so this is an offline estimate.'
        )
        if slab_comps:
            notes.append(
                f'{len(slab_comps)} graded (slabbed) listing(s) were found but are '
                'priced too differently to use for a raw copy.'
            )
        result = _heuristic_result(
            series=series,
            issue_number=issue_number,
            publisher=publisher,
            condition=condition,
            title=title,
            notes=notes,
        )
        result['rejected'] = rejected
        result['search_url'] = browse_url(query, market)
        return result

    ratio = ask_to_sold_ratio()
    confidence, confidence_note = confidence_for(summary)

    comps_for_display = sorted(adjusted, key=lambda comp: comp['adjusted'])[:comp_limit]
    if any(comp['assumed_grade'] for comp in comps_for_display):
        notes.append(
            'Listings without a stated grade were treated as Very Fine (8.0).'
        )
    if not grades_are_close:
        confidence = _downgrade_confidence(confidence)
        notes.append(
            'Few copies were listed near your condition, so copies in quite '
            'different grades had to be used.'
        )
    if summary['discarded']:
        notes.append(
            f'{summary["discarded"]} outlier listing(s) were discarded before averaging.'
        )

    return {
        'value': round(summary['median'] * ratio, 2),
        'low': round(summary['low'] * ratio, 2),
        'high': round(summary['high'] * ratio, 2),
        'median_ask': round(summary['median'], 2),
        'currency': details['currency'],
        'source': 'ebay',
        'source_label': f'{details["site"]} active listings',
        'marketplace': market,
        'condition': condition or '',
        'grade': target_grade,
        'grade_label': grade_label(target_grade),
        'basis': (
            f'{summary["sample_size"]} active {details["site"]} listings, each adjusted to '
            f'{grade_label(target_grade)} and discounted to {int(ratio * 100)}% of the '
            'asking price to approximate a real sale.'
        ),
        'confidence': confidence,
        'confidence_note': confidence_note,
        'sample_size': summary['sample_size'],
        'comps': comps_for_display,
        'slab_comps': sorted(slab_comps, key=lambda comp: comp['total'])[:comp_limit],
        'rejected': rejected,
        'query': query,
        'search_url': browse_url(query, market),
        'notes': notes,
    }
