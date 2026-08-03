"""Turn raw marketplace listings into usable comparable sales ("comps").

Keyword search returns plenty of noise: multi-issue lots, posters and figures,
facsimile reprints, and the wrong issue number entirely. Averaging that noise is
what makes naive price lookups useless, so every listing is screened first.
"""

from __future__ import annotations

import re

from .grades import parse_grade

_LOT_PATTERNS = (
    r'\blots?\b', r'\bbundle\b', r'\bset of\b', r'\bfull run\b', r'\bcomplete run\b',
    r'\bcomplete set\b', r'\bcollection\b', r'\bjob\s*lot\b', r'\byou pick\b',
    r'\bpick your\b', r'\bchoose your\b', r'\bissues?\s*#?\d+\s*[-–—]\s*#?\d+',
    r'\b\d+\s*(?:comic|issue|book)s?\b', r'\bmulti[\s-]?pack\b',
)
_REPRINT_PATTERNS = (
    r'\bfacsimile\b', r'\breprint\b', r'\breproduction\b', r'\bphotocopy\b',
    r'\bdigital\b', r'\bpdf\b', r'\bcustom\b', r'\bhomemade\b',
)
_MERCH_PATTERNS = (
    r'\bposter\b', r'\bt[\s-]?shirt\b', r'\bmug\b', r'\bfunko\b', r'\bfigure\b',
    r'\bstatue\b', r'\bdvd\b', r'\bblu[\s-]?ray\b', r'\btrading card\b',
    r'\bsketch card\b', r'\bmagnet\b', r'\bsticker\b', r'\bkeychain\b', r'\bpin\b',
    r'\bpuzzle\b', r'\blego\b', r'\bcostume\b', r'\bcosplay\b', r'\bbackpack\b',
    r'\bwall art\b', r'\bcanvas\b', r'\bframed print\b', r'\bcalendar\b',
    r'\bbobblehead\b', r'\bplush\b', r'\bcoin\b', r'\bbanknote\b',
)
# Signatures and remarks add a premium that has nothing to do with the book.
_PREMIUM_PATTERNS = (
    r'\bsigned\b', r'\bsignature series\b', r'\bautograph', r'\bremark(?:ed|s)?\b',
    r'\bsketch(?:ed)?\s+cover\b', r'\bcoa\b',
)
# Bound volumes and collected editions are a different product.
_COLLECTED_PATTERNS = (
    r'\bomnibus\b', r'\btrade paperback\b', r'\btpb\b', r'\bhardcover\b', r'\bhc\b',
    r'\bgraphic novel\b', r'\bepic collection\b', r'\bmasterworks\b',
)

_STOPWORDS = {'the', 'a', 'an', 'of', 'and', 'vol', 'volume', 'comics', 'comic'}


def _compile(patterns):
    return re.compile('|'.join(patterns), re.IGNORECASE)


_LOT_RE = _compile(_LOT_PATTERNS)
_REPRINT_RE = _compile(_REPRINT_PATTERNS)
_MERCH_RE = _compile(_MERCH_PATTERNS)
_PREMIUM_RE = _compile(_PREMIUM_PATTERNS)
_COLLECTED_RE = _compile(_COLLECTED_PATTERNS)

_HASHED_ISSUE_RE = re.compile(r'#\s*0*(\d+)')


def significant_tokens(text):
    tokens = re.findall(r"[a-z0-9']+", (text or '').lower())
    return [token for token in tokens if len(token) > 2 and token not in _STOPWORDS]


def series_matches(title, series, *, minimum_ratio=0.6):
    """Require most of the series name to appear in the listing title."""
    wanted = significant_tokens(series)
    if not wanted:
        return True
    haystack = set(significant_tokens(title))
    hits = sum(1 for token in wanted if token in haystack)
    needed = max(1, int(round(len(wanted) * minimum_ratio)))
    return hits >= needed


def issue_matches(title, issue_number):
    """Require the listing to be for the same issue number."""
    wanted = re.sub(r'\D', '', str(issue_number or ''))
    if not wanted:
        return True
    wanted_int = str(int(wanted))

    hashed = _HASHED_ISSUE_RE.findall(title or '')
    if hashed:
        return any(str(int(found)) == wanted_int for found in hashed)

    # No "#" in the title, so fall back to the number as a standalone token.
    return bool(re.search(rf'(?<![\w.#]){re.escape(wanted_int)}(?![\w.])', title or ''))


def rejection_reason(title, *, series, issue_number):
    """Why a listing cannot be used as a comp, or None when it is usable."""
    if not title:
        return 'no title'
    if _LOT_RE.search(title):
        return 'multi-issue lot'
    if _MERCH_RE.search(title):
        return 'not a comic'
    if _COLLECTED_RE.search(title):
        return 'collected edition'
    if _REPRINT_RE.search(title):
        return 'reprint or facsimile'
    if _PREMIUM_RE.search(title):
        return 'signed or remarked'
    if not series_matches(title, series):
        return 'different series'
    if not issue_matches(title, issue_number):
        return 'different issue'
    return None


def _price_of(summary):
    price = summary.get('price') or {}
    try:
        value = float(price.get('value'))
    except (TypeError, ValueError):
        return None, None
    if value <= 0:
        return None, None
    return value, price.get('currency')


def _looks_like_comic_category(summary):
    """Trust eBay's own categorisation when the response includes it."""
    categories = summary.get('categories')
    if not categories:
        return True
    names = ' '.join(str(item.get('categoryName') or '') for item in categories).lower()
    if not names.strip():
        return True
    return 'comic' in names or 'manga' in names


def build_comp(summary):
    """Flatten one eBay item summary into the fields pricing cares about."""
    price, currency = _price_of(summary)
    if price is None:
        return None

    title = summary.get('title') or ''
    grade = parse_grade(title)
    shipping = 0.0
    for option in summary.get('shippingOptions') or []:
        cost = (option.get('shippingCost') or {}).get('value')
        try:
            shipping = float(cost)
            break
        except (TypeError, ValueError):
            continue

    image = (summary.get('image') or {}).get('imageUrl') or ''
    if not image:
        thumbnails = summary.get('thumbnailImages') or []
        if thumbnails:
            image = thumbnails[0].get('imageUrl') or ''

    return {
        'item_id': summary.get('itemId') or '',
        'title': title,
        'price': price,
        'shipping': shipping,
        'total': round(price + shipping, 2),
        'currency': currency or '',
        'url': summary.get('itemWebUrl') or '',
        'image': image,
        'condition': summary.get('condition') or '',
        'grade': grade['grade'],
        'slabbed': grade['slabbed'],
        'grader': grade['grader'],
        'seller': (summary.get('seller') or {}).get('username') or '',
        'location': (summary.get('itemLocation') or {}).get('country') or '',
    }


def select_comps(summaries, *, series, issue_number, include_slabbed=False):
    """Screen listings and split them into usable comps and rejection counts."""
    kept = []
    rejected = {}

    for summary in summaries or []:
        comp = build_comp(summary)
        if comp is None:
            rejected['no price'] = rejected.get('no price', 0) + 1
            continue
        if not _looks_like_comic_category(summary):
            rejected['not a comic'] = rejected.get('not a comic', 0) + 1
            continue

        reason = rejection_reason(comp['title'], series=series, issue_number=issue_number)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        if comp['slabbed'] and not include_slabbed:
            rejected['graded slab'] = rejected.get('graded slab', 0) + 1
            continue

        kept.append(comp)

    return kept, rejected
