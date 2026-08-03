"""Decode UPC/EAN barcodes from comic cover image BLOBs.

Comic covers often print the barcode sideways in the trade-dress strip, and
ComicVine cover art is frequently too soft for the bars themselves to decode.
This module therefore:

1. Tries classic barcode decoding across rotations, crops, and preprocessings.
2. Falls back to OCR of the human-readable digits beside the bars when needed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PREFERRED_TYPES = {
    'UPCA',
    'UPC-A',
    'EAN13',
    'EAN-13',
    'EAN8',
    'EAN-8',
    'UPCE',
    'UPC-E',
    'ISBN13',
    'ISBN10',
}

# EAN-2 / EAN-5 supplements (issue/price codes) must not win over a real UPC.
_SUPPLEMENT_LENGTHS = {2, 5}

_DIGIT_RUN_RE = re.compile(r'\d{8,14}')
_NON_DIGIT_RE = re.compile(r'\D+')
_HYPHENATED_BODY_RE = re.compile(r'(\d{5})\s*-\s*(\d{5})')

# Number-system digit hints when OCR drops the leading UPC digit.
_PUBLISHER_NUMBER_SYSTEMS = (
    (re.compile(r'\bMARVEL\b', re.I), ('7', '0')),
    (re.compile(r'\bDC\b|\bDETECTIVE COMICS\b', re.I), ('7', '0')),
    (re.compile(r'\bIMAGE\b', re.I), ('7', '0')),
    (re.compile(r'\bDARK HORSE\b', re.I), ('7', '0')),
    (re.compile(r'\bIDW\b', re.I), ('7', '0')),
    (re.compile(r'\bBOOM\b', re.I), ('7', '0')),
)


class BarcodeDependenciesMissing(RuntimeError):
    """Raised when OpenCV / pyzbar are not installed or ZBar is unavailable."""


def _import_deps():
    try:
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401
        from pyzbar import pyzbar  # noqa: F401
    except ImportError as exc:
        raise BarcodeDependenciesMissing(
            'Barcode scanning requires opencv-python-headless and pyzbar. '
            'Install them with: pip install opencv-python-headless pyzbar'
        ) from exc
    return cv2, np, pyzbar


def upc_a_check_digit(body11: str) -> str:
    """Return the UPC-A check digit for an 11-digit body."""
    if len(body11) != 11 or not body11.isdigit():
        raise ValueError('UPC-A body must be 11 digits')
    digits = [int(ch) for ch in body11]
    total = sum(digits[0::2]) * 3 + sum(digits[1::2])
    return str((10 - (total % 10)) % 10)


def ean13_check_digit(body12: str) -> str:
    """Return the EAN-13 check digit for a 12-digit body."""
    if len(body12) != 12 or not body12.isdigit():
        raise ValueError('EAN-13 body must be 12 digits')
    digits = [int(ch) for ch in body12]
    total = sum(digits[0::2]) + sum(digits[1::2]) * 3
    return str((10 - (total % 10)) % 10)


def is_valid_upc_a(code: str) -> bool:
    if len(code) != 12 or not code.isdigit():
        return False
    return upc_a_check_digit(code[:11]) == code[-1]


def is_valid_ean13(code: str) -> bool:
    if len(code) != 13 or not code.isdigit():
        return False
    return ean13_check_digit(code[:12]) == code[-1]


def normalize_product_code(raw: str) -> str | None:
    """Turn a digit string into a validated UPC-A / EAN-13 when possible."""
    digits = ''.join(ch for ch in (raw or '') if ch.isdigit())
    if not digits or len(digits) in _SUPPLEMENT_LENGTHS:
        return None

    if len(digits) == 12:
        return digits if is_valid_upc_a(digits) else None
    if len(digits) == 13:
        if is_valid_ean13(digits):
            # UPC-A values are often returned as zero-padded EAN-13.
            if digits.startswith('0') and is_valid_upc_a(digits[1:]):
                return digits[1:]
            return digits
        return None
    if len(digits) == 11:
        candidate = digits + upc_a_check_digit(digits)
        return candidate if is_valid_upc_a(candidate) else None
    if len(digits) == 8:
        return digits
    return None


def _has_valid_product_code(codes: list[dict]) -> bool:
    for code in codes:
        normalized = normalize_product_code(code.get('data') or '')
        if normalized and (is_valid_upc_a(normalized) or is_valid_ean13(normalized)):
            return True
    return False


def _orientations(gray, cv2):
    yield '0', gray
    yield '90cw', cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)
    yield '180', cv2.rotate(gray, cv2.ROTATE_180)
    yield '90ccw', cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)


def _preprocess_variants(gray, cv2):
    variants = [('raw', gray)]
    try:
        variants.append(('equalize', cv2.equalizeHist(gray)))
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(('otsu', otsu))
        variants.append(('otsu_inv', cv2.bitwise_not(otsu)))
    except Exception:
        logger.debug('Cover barcode preprocessing fallback used', exc_info=True)
    return variants


def _with_quiet_zone(image, pad: int = 24):
    import cv2

    return cv2.copyMakeBorder(
        image, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255
    )


def _trade_dress_crops(image):
    """Yield likely UPC trade-dress strips from a comic cover."""
    height, width = image.shape[:2]
    yield 'full', image
    crops = [
        ('left', image[int(height * 0.22):int(height * 0.70), 0:max(1, int(width * 0.30))]),
        ('right', image[int(height * 0.22):int(height * 0.70), int(width * 0.70):width]),
        ('mid_left', image[int(height * 0.32):int(height * 0.60), 0:max(1, int(width * 0.20))]),
        ('gutter_left', image[int(height * 0.38):int(height * 0.58), 0:max(1, int(width * 0.12))]),
        ('gutter_right', image[int(height * 0.38):int(height * 0.58), int(width * 0.88):width]),
    ]
    for label, crop in crops:
        # Skip near-duplicates when the source is already a narrow strip/fixture.
        if crop.size and crop.shape[0] * crop.shape[1] < height * width * 0.95:
            yield label, crop


def _decode_pyzbar(image, pyzbar) -> list[Any]:
    try:
        return list(pyzbar.decode(_with_quiet_zone(image)) or [])
    except Exception as exc:
        raise BarcodeDependenciesMissing(
            'pyzbar could not decode images. On Windows, install the ZBar DLL '
            '(see README) and ensure it is on PATH.'
        ) from exc


def _decode_opencv(image, cv2) -> list[dict]:
    detector = getattr(getattr(cv2, 'barcode', None), 'BarcodeDetector', None)
    if detector is None:
        return []
    try:
        det = detector()
        ok = det.detectAndDecode(image)
    except Exception:
        logger.debug('OpenCV barcode detector failed', exc_info=True)
        return []

    infos = ()
    types = ()
    if isinstance(ok, tuple):
        if len(ok) >= 3 and isinstance(ok[1], (list, tuple)):
            infos = ok[1]
            types = ok[2] if isinstance(ok[2], (list, tuple)) else ()
        elif len(ok) >= 1 and isinstance(ok[0], (list, tuple)):
            infos = ok[0]
            types = ok[1] if len(ok) > 1 and isinstance(ok[1], (list, tuple)) else ()
        elif len(ok) >= 1 and isinstance(ok[0], str) and ok[0]:
            infos = (ok[0],)
            types = (ok[1],) if len(ok) > 1 else ()

    results = []
    for index, data in enumerate(infos or ()):
        text = str(data or '').strip()
        if not text:
            continue
        kind = str(types[index]) if index < len(types) else 'UNKNOWN'
        results.append({'data': text, 'type': kind})
    return results


def _append_code(codes: list[dict], seen: set[str], data: str, kind: str) -> bool:
    data = (data or '').strip()
    if not data or data in seen:
        return False
    seen.add(data)
    codes.append({'data': data, 'type': kind})
    normalized = normalize_product_code(data)
    return bool(
        normalized and (is_valid_upc_a(normalized) or is_valid_ean13(normalized))
    )


def _decode_barcode_region(crop, cv2, np, pyzbar, seen: set[str], codes: list[dict]) -> bool:
    """Fast barcode pass over one crop. Returns True when a valid UPC is found."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    for _orientation, oriented in _orientations(gray, cv2):
        for scale in (1.0, 2.0, 3.0):
            scaled = (
                oriented
                if scale == 1.0
                else cv2.resize(
                    oriented, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
                )
            )
            for _name, variant in _preprocess_variants(scaled, cv2):
                for item in _decode_pyzbar(variant, pyzbar):
                    data = item.data.decode('utf-8', errors='ignore').strip() if item.data else ''
                    kind = getattr(item, 'type', None) or 'UNKNOWN'
                    if isinstance(kind, bytes):
                        kind = kind.decode('utf-8', errors='ignore')
                    if _append_code(codes, seen, data, str(kind)):
                        return True
        for item in _decode_opencv(
            cv2.cvtColor(oriented, cv2.COLOR_GRAY2BGR)
            if len(oriented.shape) == 2
            else oriented,
            cv2,
        ):
            if _append_code(codes, seen, item['data'], item['type']):
                return True
    return False


def decode_barcodes_from_image_bytes(image_bytes: bytes) -> list[dict]:
    """
    Decode barcodes from raw image bytes.

    Returns a list of dicts: {'data': str, 'type': str}.
    """
    if not image_bytes:
        return []

    cv2, np, pyzbar = _import_deps()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return []

    seen: set[str] = set()
    codes: list[dict] = []

    # 1) Classic barcode decode on the full cover and trade-dress strips.
    for _label, crop in _trade_dress_crops(image):
        if _decode_barcode_region(crop, cv2, np, pyzbar, seen, codes):
            return codes

    # 2) OCR fallback for soft ComicVine art where only the digits are readable.
    for item in _ocr_product_codes(image, cv2):
        _append_code(codes, seen, item['data'], item['type'])
        if _has_valid_product_code(codes):
            break

    return codes


_OCR_ENGINE = None


def _ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is False:
        return None
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        _OCR_ENGINE = False
        return None
    _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _ocr_product_codes(image, cv2) -> list[dict]:
    """Read human-readable UPC digits from trade-dress strips via OCR."""
    engine = _ocr_engine()
    if engine is None:
        return []

    candidates: list[dict] = []
    seen: set[str] = set()

    # Prefer gutters and the full image (important for already-cropped strips).
    prioritized = list(_trade_dress_crops(image))
    prioritized.sort(
        key=lambda item: (
            0 if item[0] in ('gutter_left', 'gutter_right', 'full') else 1,
            0 if item[0] == 'full' else 1,
        )
    )

    for _label, crop in prioritized:
        for oriented in (
            crop,
            cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE),
            cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE),
        ):
            for scale in (2.0, 3.0, 1.0):
                sample = (
                    oriented
                    if scale == 1.0
                    else cv2.resize(
                        oriented, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
                    )
                )
                try:
                    result, _elapsed = engine(sample)
                except Exception:
                    logger.debug('OCR barcode fallback failed', exc_info=True)
                    continue
                texts = [row[1] for row in (result or []) if len(row) > 1]
                for code in _codes_from_ocr_texts(texts):
                    if code in seen:
                        continue
                    seen.add(code)
                    candidates.append({'data': code, 'type': 'OCR-UPC'})
                    if is_valid_upc_a(code) or is_valid_ean13(code):
                        return candidates
    return candidates


def _publisher_number_systems(texts: list[str]) -> tuple[str, ...]:
    blob = ' '.join(texts or [])
    for pattern, systems in _PUBLISHER_NUMBER_SYSTEMS:
        if pattern.search(blob):
            return systems
    return ('7', '0')


def _codes_from_ocr_texts(texts: list[str]) -> list[str]:
    """Extract plausible product codes from OCR text fragments.

    Fragments are scored individually. Digits from unrelated boxes (for example a
    UPC body and an EAN-5 supplement) are never concatenated.
    """
    found: list[str] = []
    seen: set[str] = set()
    ten_digit_bodies: list[str] = []
    lone_digits: list[str] = []

    def add(raw: str):
        normalized = normalize_product_code(raw)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        found.append(normalized)

    for text in texts or []:
        cleaned = (
            str(text)
            .replace('—', '-')
            .replace('–', '-')
            .replace('"', '')
            .replace("'", '')
            .replace('′', '')
        )
        # OCR sometimes injects a letter between the leading digit and body:
        # "7m59606-08512" -> keep the leading 7.
        cleaned = re.sub(r'(\d)[A-Za-z](\d)', r'\1\2', cleaned)

        for left, right in _HYPHENATED_BODY_RE.findall(cleaned):
            ten_digit_bodies.append(left + right)

        compact = _NON_DIGIT_RE.sub('', cleaned)
        if len(compact) == 1:
            lone_digits.append(compact)
        elif len(compact) == 10:
            ten_digit_bodies.append(compact)
        else:
            for match in _DIGIT_RUN_RE.findall(compact):
                add(match)
            if len(compact) == 11 and compact.isdigit():
                add(compact)

    # When OCR drops the number-system digit, rebuild UPC-A from the 10-digit body.
    prefixes = list(dict.fromkeys([*lone_digits, *_publisher_number_systems(texts)]))
    for body in ten_digit_bodies:
        if len(body) != 10 or not body.isdigit():
            continue
        for prefix in prefixes:
            add(prefix + body)

    found.sort(
        key=lambda code: (
            0 if is_valid_upc_a(code) or is_valid_ean13(code) else 1,
            0 if len(code) == 12 else 1,
            -len(code),
        )
    )
    return found


def pick_best_upc(codes: list[dict]) -> str | None:
    """Choose the best UPC/EAN candidate from decoded barcodes."""
    if not codes:
        return None

    preferred = []
    numeric = []
    for code in codes:
        raw = ''.join(ch for ch in (code.get('data') or '') if ch.isdigit())
        if not raw or len(raw) in _SUPPLEMENT_LENGTHS:
            continue
        normalized = normalize_product_code(raw)
        if not normalized:
            if len(raw) not in (8, 12, 13):
                continue
            normalized = raw
        kind = (code.get('type') or '').upper().replace('_', '-')
        entry = {
            'data': normalized,
            'type': kind,
            'valid': is_valid_upc_a(normalized) or is_valid_ean13(normalized),
        }
        numeric.append(entry)
        if (
            kind in _PREFERRED_TYPES
            or kind.startswith('OCR')
            or len(normalized) in (8, 12, 13)
        ):
            preferred.append(entry)

    pool = preferred or numeric
    if not pool:
        return None

    def sort_key(item):
        length = len(item['data'])
        preferred_rank = 0 if item['type'] in _PREFERRED_TYPES or item['type'].startswith('OCR') else 1
        valid_rank = 0 if item['valid'] else 1
        length_rank = {12: 0, 13: 1, 8: 2}.get(length, 3)
        return (valid_rank, preferred_rank, length_rank, length)

    pool.sort(key=sort_key)
    return pool[0]['data']


def scan_cover_image(image_bytes: bytes) -> dict:
    """
    High-level helper used by routes.

    Returns:
        {
          'codes': [...],
          'best': '012345678905' | None,
          'available': True/False,
          'error': optional str,
        }
    """
    try:
        codes = decode_barcodes_from_image_bytes(image_bytes)
    except BarcodeDependenciesMissing as exc:
        return {
            'codes': [],
            'best': None,
            'available': False,
            'error': str(exc),
        }
    except Exception as exc:
        logger.exception('Unexpected barcode decode failure')
        return {
            'codes': [],
            'best': None,
            'available': True,
            'error': f'Barcode scan failed: {exc}',
        }

    return {
        'codes': codes,
        'best': pick_best_upc(codes),
        'available': True,
        'error': None,
    }
