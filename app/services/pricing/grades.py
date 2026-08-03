"""Comic grade ladder and grade parsing from marketplace listing titles.

Prices are compared on the 10-point comic grading scale. A listing rarely states
a grade in a structured field, so grades are read out of the title, which is
where sellers put them ("CGC 9.8", "VF/NM", "Near Mint").
"""

from __future__ import annotations

import re

# The condition choices offered by the comic form, mapped onto the 10-point
# scale. These are midpoints: "Near Mint" covers 9.2-9.6 in practice.
CONDITION_GRADES = {
    'mint': 9.9,
    'near mint': 9.4,
    'very fine': 8.0,
    'fine': 6.0,
    'very good': 4.0,
    'good': 2.0,
    'fair': 1.5,
    'poor': 0.5,
}

# An unstated condition is treated as Very Fine rather than Near Mint, so a
# blank field cannot quietly inflate an estimate.
DEFAULT_CONDITION = 'very fine'

# Value of a grade relative to Near Mint (9.4 = 1.0). Back-issue prices fall off
# steeply below VF, which is why a single flat condition multiplier misprices
# low-grade copies so badly. Approximate and intentionally conservative.
_GRADE_VALUE_CURVE = (
    (9.8, 1.60),
    (9.6, 1.20),
    (9.4, 1.00),
    (9.0, 0.80),
    (8.5, 0.68),
    (8.0, 0.58),
    (7.0, 0.44),
    (6.0, 0.34),
    (5.0, 0.26),
    (4.0, 0.20),
    (3.0, 0.15),
    (2.0, 0.11),
    (1.5, 0.08),
    (1.0, 0.06),
    (0.5, 0.04),
)

_GRADER_PATTERN = re.compile(r'\b(cgc|cbcs|pgx|egs)\b', re.IGNORECASE)

# "CGC 9.8", "CBCS 9.6 SS", "graded 9.4"
_NUMERIC_GRADE_PATTERN = re.compile(
    r'\b(?:cgc|cbcs|pgx|egs|graded|grade)\b[^0-9]{0,12}(10(?:\.0)?|[0-9](?:\.[0-9])?)(?![\w.])',
    re.IGNORECASE,
)
# A bare "9.8" or "9.4" anywhere in the title, which sellers use for raw copies.
_BARE_GRADE_PATTERN = re.compile(r'(?<![\w.$#])(10\.0|[1-9]\.[0-9])(?![\w.%])')

# Letter grades, longest first so "VF/NM" wins over "VF" and "NM".
_LETTER_GRADES = (
    (r'nm\s*/\s*m\b|near\s*mint\s*/\s*mint\b', 9.8),
    (r'nm\s*\+|near\s*mint\s*\+', 9.6),
    (r'vf\s*/\s*nm|very\s*fine\s*/\s*near\s*mint', 9.0),
    (r'\bnm\b|near\s*mint', 9.4),
    # Only reached once the near-mint spellings above have been ruled out.
    (r'\bmint\b', 9.9),
    (r'vf\s*\+|very\s*fine\s*\+', 8.5),
    (r'fn\s*/\s*vf|fine\s*/\s*very\s*fine', 7.0),
    (r'\bvf\b|very\s*fine', 8.0),
    (r'vg\s*/\s*fn|very\s*good\s*/\s*fine', 5.0),
    (r'\bfn\b|\bfine\b', 6.0),
    (r'gd\s*/\s*vg|good\s*/\s*very\s*good', 3.0),
    (r'\bvg\b|very\s*good', 4.0),
    (r'\bgd\b|\bgood\b', 2.0),
    (r'\bfa\b|\bfr\b|\bfair\b', 1.5),
    (r'\bpr\b|\bpoor\b', 0.5),
)
_LETTER_GRADE_PATTERNS = tuple(
    (re.compile(pattern, re.IGNORECASE), grade) for pattern, grade in _LETTER_GRADES
)


def grade_for_condition(condition: str | None) -> float:
    """Numeric grade for one of the form's condition choices."""
    key = (condition or '').strip().lower()
    return CONDITION_GRADES.get(key, CONDITION_GRADES[DEFAULT_CONDITION])


def grade_value_factor(grade: float) -> float:
    """Relative market value of a grade, interpolated between curve points."""
    points = _GRADE_VALUE_CURVE
    if grade >= points[0][0]:
        return points[0][1]
    if grade <= points[-1][0]:
        return points[-1][1]
    for (high_grade, high_factor), (low_grade, low_factor) in zip(points, points[1:]):
        if low_grade <= grade <= high_grade:
            span = high_grade - low_grade
            if span <= 0:
                return low_factor
            ratio = (grade - low_grade) / span
            return low_factor + ratio * (high_factor - low_factor)
    return 1.0


def convert_price_between_grades(price: float, from_grade: float, to_grade: float) -> float:
    """Restate a price observed at one grade as the equivalent at another."""
    source = grade_value_factor(from_grade)
    if source <= 0:
        return price
    return price * (grade_value_factor(to_grade) / source)


def parse_grade(title: str) -> dict:
    """Read grade information out of a listing title.

    Returns the numeric grade (or None), whether the copy is professionally
    slabbed, the grading company, and how the grade was found.
    """
    text = title or ''
    grader_match = _GRADER_PATTERN.search(text)
    grader = grader_match.group(1).upper() if grader_match else None

    numeric = _NUMERIC_GRADE_PATTERN.search(text)
    if numeric:
        return {
            'grade': float(numeric.group(1)),
            'slabbed': grader is not None,
            'grader': grader,
            'source': 'numeric',
        }

    for pattern, grade in _LETTER_GRADE_PATTERNS:
        if pattern.search(text):
            return {
                'grade': grade,
                'slabbed': grader is not None,
                'grader': grader,
                'source': 'letter',
            }

    bare = _BARE_GRADE_PATTERN.search(text)
    if bare:
        return {
            'grade': float(bare.group(1)),
            'slabbed': grader is not None,
            'grader': grader,
            'source': 'bare',
        }

    return {
        'grade': None,
        'slabbed': grader is not None,
        'grader': grader,
        'source': None,
    }


def grade_label(grade: float | None) -> str:
    if grade is None:
        return 'ungraded'
    for pattern_grade, label in (
        (9.8, 'NM/M'), (9.6, 'NM+'), (9.4, 'NM'), (9.0, 'VF/NM'),
        (8.5, 'VF+'), (8.0, 'VF'), (7.0, 'FN/VF'), (6.0, 'FN'),
        (5.0, 'VG/FN'), (4.0, 'VG'), (3.0, 'GD/VG'), (2.0, 'GD'),
        (1.5, 'FR'), (0.5, 'PR'),
    ):
        if grade >= pattern_grade:
            return f'{grade:g} {label}'
    return f'{grade:g}'
