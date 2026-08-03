"""Robust summary statistics for noisy marketplace prices."""

from __future__ import annotations


def quantile(sorted_values, fraction):
    """Linear-interpolated quantile of an already sorted, non-empty sequence."""
    if not sorted_values:
        raise ValueError('quantile() needs at least one value')
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return float(sorted_values[lower]) * (1 - weight) + float(sorted_values[upper]) * weight


def median(values):
    return quantile(sorted(values), 0.5)


def trim_outliers(values, *, fence=1.5, min_keep=4):
    """Drop prices outside the interquartile fences.

    Comic listings include occasional wild asks (a $2 book listed at $900), and
    a plain average follows them. Below ``min_keep`` samples the quartiles are
    not meaningful, so everything is kept.
    """
    numbers = sorted(float(value) for value in values)
    if len(numbers) < min_keep:
        return numbers, []

    q1 = quantile(numbers, 0.25)
    q3 = quantile(numbers, 0.75)
    spread = q3 - q1
    low_fence = q1 - fence * spread
    high_fence = q3 + fence * spread

    kept = [value for value in numbers if low_fence <= value <= high_fence]
    dropped = [value for value in numbers if not low_fence <= value <= high_fence]
    if len(kept) < min_keep:
        return numbers, []
    return kept, dropped


def summarize(values, *, fence=1.5):
    """Median plus a reported range, after trimming outliers.

    The reported range is the 10th-90th percentile rather than the quartiles:
    quartiles of a handful of listings hug the median and imply a precision the
    data does not have. Quartiles are still returned for judging spread.
    """
    kept, dropped = trim_outliers(values, fence=fence)
    if not kept:
        return None

    return {
        'median': quantile(kept, 0.5),
        'low': quantile(kept, 0.10),
        'high': quantile(kept, 0.90),
        'q1': quantile(kept, 0.25),
        'q3': quantile(kept, 0.75),
        'minimum': kept[0],
        'maximum': kept[-1],
        'sample_size': len(kept),
        'discarded': len(dropped),
    }


def confidence_for(summary):
    """Grade the reliability of a summary from sample size and spread."""
    if not summary:
        return 'none', 'No comparable listings were found.'

    size = summary['sample_size']
    center = summary['median'] or 0
    spread_ratio = (summary['q3'] - summary['q1']) / center if center else 1.0

    if size >= 8 and spread_ratio <= 0.75:
        return 'high', f'{size} comparable listings that agree closely.'
    if size >= 5 and spread_ratio <= 1.5:
        return 'medium', f'{size} comparable listings with a moderate spread.'
    if size >= 3:
        return 'low', f'Only {size} comparable listings, and prices vary widely.'
    return 'very low', f'Just {size} comparable listing(s) found.'
