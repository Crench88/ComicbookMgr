"""Offline fallback estimate used when no marketplace comparables are available.

This is a lookup table of typical back-issue prices, not market data. It exists
only so the value field can be pre-filled when eBay is unreachable or has no
matching listings, and every result it produces is labelled as an estimate.
"""

from __future__ import annotations

import re

from .grades import grade_for_condition, grade_value_factor

# Typical asking range for a mid-run issue in Fine (6.0) condition, in CAD.
_BASE_RANGES = {
    'marvel': {
        'amazing spider-man': (20, 60),
        'uncanny x-men': (15, 55),
        'spider-man': (15, 50),
        'x-men': (12, 45),
        'avengers': (10, 40),
        'iron man': (8, 35),
        'captain america': (10, 40),
        'thor': (8, 35),
        'hulk': (10, 40),
        'deadpool': (12, 45),
        'civil war': (15, 50),
        'fantastic four': (12, 45),
        'daredevil': (10, 40),
        'punisher': (8, 35),
        'wolverine': (12, 45),
        'default': (5, 25),
    },
    'dc': {
        'detective comics': (25, 70),
        'action comics': (20, 60),
        'batman': (20, 60),
        'superman': (15, 50),
        'justice league': (12, 45),
        'flash': (10, 40),
        'green lantern': (8, 35),
        'wonder woman': (10, 40),
        'aquaman': (8, 30),
        'default': (8, 30),
    },
    'image': {
        'walking dead': (12, 45),
        'saga': (10, 40),
        'spawn': (8, 35),
        'invincible': (8, 30),
        'default': (3, 20),
    },
    'dark horse': {
        'hellboy': (10, 40),
        'sin city': (8, 35),
        'default': (5, 25),
    },
    'idw': {'default': (4, 20)},
    'boom': {'default': (3, 18)},
    'valiant': {'default': (5, 25)},
    'dynamite': {'default': (3, 18)},
    'archie': {'default': (4, 20)},
    'default': {'default': (5, 25)},
}

_FINE_GRADE = 6.0

_KEY_ISSUE_KEYWORDS = (
    'first appearance', 'origin', 'death of', 'wedding', 'debut', '1st appearance',
)


def _publisher_key(publisher):
    """Match a free-text publisher name such as "DC Comics" to a table key."""
    text = (publisher or '').lower()
    if not text:
        return 'default'
    tokens = set(re.findall(r"[a-z0-9']+", text))
    for key in _BASE_RANGES:
        if key == 'default':
            continue
        key_tokens = key.split()
        if all(token in tokens for token in key_tokens):
            return key
    return 'default'


def _series_range(publisher_key, *haystacks):
    ranges = _BASE_RANGES.get(publisher_key, _BASE_RANGES['default'])
    text = ' '.join(part.lower() for part in haystacks if part)
    # Longest series names first, so "amazing spider-man" beats "spider-man".
    for series_name in sorted(
        (name for name in ranges if name != 'default'), key=len, reverse=True
    ):
        if series_name in text:
            return ranges[series_name], series_name
    return ranges['default'], None


def _issue_factor(issue_number):
    digits = re.sub(r'\D', '', str(issue_number or ''))
    if not digits:
        return 1.0
    number = int(digits)
    if number == 1:
        return 1.8
    if number <= 5:
        return 1.4
    if number <= 10:
        return 1.2
    if number % 100 == 0:
        return 1.3
    return 1.0


def _title_factor(title):
    text = (title or '').lower()
    return 1.2 if any(keyword in text for keyword in _KEY_ISSUE_KEYWORDS) else 1.0


def heuristic_estimate(*, series='', issue_number='', publisher='', condition='', title=''):
    """A deterministic offline estimate with a low/median/high range."""
    publisher_key = _publisher_key(publisher)
    (low, high), matched_series = _series_range(publisher_key, series, title)

    grade = grade_for_condition(condition)
    grade_factor = grade_value_factor(grade) / grade_value_factor(_FINE_GRADE)
    factor = grade_factor * _issue_factor(issue_number) * _title_factor(title)

    low_value = max(1.0, round(low * factor, 2))
    high_value = max(low_value, round(high * factor, 2))
    # Stay at the conservative end of the range, as the UI has always promised.
    median_value = max(1.0, round((low_value * 2 + high_value) / 3, 2))

    return {
        'value': median_value,
        'low': low_value,
        'high': high_value,
        'grade': grade,
        'publisher_key': publisher_key,
        'series_key': matched_series,
    }
