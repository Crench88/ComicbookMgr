"""Detect comic-page panels for guided reader zoom."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _import_cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            'Panel detection requires opencv-python-headless and numpy.'
        ) from exc
    return cv2, np


def _reading_order_key(panel: dict) -> tuple:
    """Top-to-bottom, then left-to-right within a rough row band."""
    return (round(panel['y'] * 20), panel['x'], panel['y'])


def _iou(a: dict, b: dict) -> float:
    ax2, ay2 = a['x'] + a['w'], a['y'] + a['h']
    bx2, by2 = b['x'] + b['w'], b['y'] + b['h']
    ix1, iy1 = max(a['x'], b['x']), max(a['y'], b['y'])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = a['w'] * a['h'] + b['w'] * b['h'] - inter
    return inter / union if union else 0.0


def _merge_overlapping(boxes: list[dict], iou_threshold: float = 0.55) -> list[dict]:
    if not boxes:
        return []
    remaining = sorted(boxes, key=lambda b: b['w'] * b['h'], reverse=True)
    kept = []
    while remaining:
        current = remaining.pop(0)
        kept.append(current)
        remaining = [b for b in remaining if _iou(current, b) < iou_threshold]
    return kept


def _boxes_from_mask(mask, width: int, height: int, cv2, *, min_frac: float = 0.02, max_frac: float = 0.72) -> list[dict]:
    page_area = float(width * height)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < page_area * min_frac or area > page_area * max_frac:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < width * 0.08 or h < height * 0.06:
            continue
        aspect = w / float(h)
        if aspect < 0.12 or aspect > 10.0:
            continue
        rect_area = float(w * h)
        if rect_area <= 0 or area / rect_area < 0.30:
            continue
        boxes.append({
            'x': x / width,
            'y': y / height,
            'w': w / width,
            'h': h / height,
        })
    return boxes


def _detect_by_gutter_dilation(blur, width: int, height: int, cv2) -> list[dict]:
    """
    Thicken near-white gutters until panels become separate connected components.

    This works well for Western comics with white page gutters.
    """
    best: list[dict] = []
    for thr in (230, 240, 248):
        _, light = cv2.threshold(blur, thr, 255, cv2.THRESH_BINARY)
        for k in (9, 15, 25):
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
            thick = cv2.dilate(light, kernel, iterations=1)
            panels_mask = cv2.bitwise_not(thick)
            boxes = _boxes_from_mask(panels_mask, width, height, cv2)
            boxes = _merge_overlapping(boxes)
            if len(boxes) > len(best):
                best = boxes
            # Prefer a clean 2–12 panel layout once found.
            if 2 <= len(boxes) <= 12:
                return sorted(boxes, key=_reading_order_key)
    return sorted(best, key=_reading_order_key)


def _detect_by_edges(blur, width: int, height: int, cv2, np) -> list[dict]:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    filled = edges.copy()
    mask = np.zeros((height + 2, width + 2), np.uint8)
    cv2.floodFill(filled, mask, (0, 0), 255)
    panel_mask = cv2.bitwise_not(filled)
    panel_mask = cv2.morphologyEx(panel_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    boxes = _boxes_from_mask(panel_mask, width, height, cv2)
    return sorted(_merge_overlapping(boxes), key=_reading_order_key)


def _clamp_boxes(boxes: list[dict]) -> list[dict]:
    cleaned = []
    for box in boxes:
        x = max(0.0, min(1.0, float(box['x'])))
        y = max(0.0, min(1.0, float(box['y'])))
        w = max(0.02, min(1.0 - x, float(box['w'])))
        h = max(0.02, min(1.0 - y, float(box['h'])))
        cleaned.append({
            'x': round(x, 4),
            'y': round(y, 4),
            'w': round(w, 4),
            'h': round(h, 4),
        })
    return cleaned


def detect_panels_from_bytes(image_bytes: bytes) -> list[dict]:
    """
    Return panel rectangles as normalized fractions of the page (0-1).

    Each item: {x, y, w, h} in reading order. Falls back to a single full-page
    panel when detection finds nothing useful.
    """
    cv2, np = _import_cv()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return [{'x': 0.0, 'y': 0.0, 'w': 1.0, 'h': 1.0}]

    height, width = image.shape[:2]
    if width < 32 or height < 32:
        return [{'x': 0.0, 'y': 0.0, 'w': 1.0, 'h': 1.0}]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    boxes = _detect_by_gutter_dilation(blur, width, height, cv2)
    if len(boxes) < 2:
        edge_boxes = _detect_by_edges(blur, width, height, cv2, np)
        if len(edge_boxes) > len(boxes):
            boxes = edge_boxes

    boxes = [b for b in boxes if b['w'] * b['h'] >= 0.02]
    boxes = _merge_overlapping(boxes)
    boxes.sort(key=_reading_order_key)

    if len(boxes) < 2:
        return [{'x': 0.0, 'y': 0.0, 'w': 1.0, 'h': 1.0}]

    return _clamp_boxes(boxes)
