"""
image_analyzer.py — OpenCV tool silhouette analysis for SnapFit.

Pipeline
--------
1. Decode base64 image
2. Grayscale + Gaussian blur (noise reduction)
3. Auto-threshold Canny edge detection (Otsu-derived thresholds)
4. Morphological close to fill contour gaps
5. Find largest contour (assumed = tool silhouette)
6. Extract bounding box → convert px → mm via calibration factor
7. Simplify contour with Douglas-Peucker for frontend overlay
8. Compute confidence score based on fill ratio
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
# Morphological kernel for closing small gaps in tool outline
_MORPH_KERNEL = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
_MORPH_ITERS  = 2

# Confidence threshold below which we issue a warning
CONFIDENCE_WARN_THRESHOLD = 0.60

# Maximum number of simplified contour points returned to the client
MAX_CONTOUR_PTS = 120


# ── Public API ─────────────────────────────────────────────────────────────────

def analyze_tool_image(
    b64_image: str,
    known_dimension_mm: float,
    known_axis: str = "height",
) -> dict:
    """Analyse a base64-encoded image of a power tool and return dimensions in mm.

    Args:
        b64_image:           Base64-encoded image string (JPEG or PNG).
        known_dimension_mm:  One real-world dimension of the tool in mm, used
                             for pixel-to-mm calibration.
        known_axis:          Which axis the known dimension applies to:
                             "height" (default) or "width".

    Returns:
        dict with keys: width_mm, height_mm, depth_mm, contour_points,
                        bounding_box, confidence, warning.

    Raises:
        ValueError: if the image cannot be decoded or no contour is found.
    """
    img = _decode_image(b64_image)
    gray, blurred = _preprocess(img)
    edges = _detect_edges(blurred)
    closed = _close_edges(edges)

    contour, bbox = _largest_contour(closed)
    x, y, w, h = bbox

    # Calibration: derive px_per_mm from the known axis
    known_axis = known_axis.lower().strip()
    if known_axis == "width":
        px_per_mm = w / known_dimension_mm if known_dimension_mm else 1.0
    else:  # default: height
        px_per_mm = h / known_dimension_mm if known_dimension_mm else 1.0

    width_mm  = round(w / px_per_mm, 1)
    height_mm = round(h / px_per_mm, 1)

    confidence = _compute_confidence(contour, w, h, img.shape)
    warning = (
        "Low confidence — retake photo against a plain, high-contrast background."
        if confidence < CONFIDENCE_WARN_THRESHOLD
        else None
    )

    simplified = _simplify_contour(contour, max_pts=MAX_CONTOUR_PTS)

    return {
        "width_mm":      width_mm,
        "height_mm":     height_mm,
        "depth_mm":      None,          # can't capture depth from single 2D image
        "contour_points": simplified,
        "bounding_box":  {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
        "confidence":    round(float(confidence), 3),
        "warning":       warning,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _decode_image(b64_image: str) -> np.ndarray:
    """Decode a base64 string (with or without data-URL prefix) to a BGR ndarray."""
    # Strip optional data-URL prefix (e.g. "data:image/jpeg;base64,...")
    if "," in b64_image:
        b64_image = b64_image.split(",", 1)[1]
    try:
        raw = base64.b64decode(b64_image)
    except Exception as exc:
        raise ValueError(f"Invalid base64 data: {exc}") from exc

    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image — unsupported format or corrupt data.")
    return img


def _preprocess(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert to grayscale and apply Gaussian blur."""
    gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    return gray, blurred


def _detect_edges(blurred: np.ndarray) -> np.ndarray:
    """Auto-threshold Canny using Otsu's optimal single-threshold as a guide.

    Otsu gives the best single threshold for the blurred image. We use
    0.5× as the lower Canny threshold and 1.5× as the upper — a common
    heuristic that works well for high-contrast silhouettes.
    """
    otsu_thresh, _ = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )
    low  = 0.5 * otsu_thresh
    high = 1.5 * otsu_thresh
    return cv2.Canny(blurred, low, high)


def _close_edges(edges: np.ndarray) -> np.ndarray:
    """Morphological close to bridge small gaps in the detected outline."""
    return cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, _MORPH_KERNEL, iterations=_MORPH_ITERS
    )


def _largest_contour(
    binary: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Find the largest contour by area and return it with its bounding rect."""
    contours, _ = cv2.findContours(
        binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        raise ValueError(
            "No contours found. Ensure the tool is against a high-contrast background."
        )
    largest = max(contours, key=cv2.contourArea)
    bbox    = cv2.boundingRect(largest)
    return largest, bbox


def _compute_confidence(
    contour: np.ndarray,
    bbox_w: int,
    bbox_h: int,
    img_shape: tuple,
) -> float:
    """Confidence score (0–1) based on two signals:

    1. Fill ratio  — contour area ÷ bounding-box area.
       A compact, solid silhouette scores high; a noisy multi-fragment set scores low.
    2. Coverage    — bounding-box area ÷ image area.
       If the tool is too small (< 5% of frame) the measurement is unreliable.

    Final score = fill_ratio × coverage_penalty (clipped to [0,1]).
    """
    img_h, img_w = img_shape[:2]
    contour_area = cv2.contourArea(contour)
    bbox_area    = float(bbox_w * bbox_h) or 1.0
    img_area     = float(img_w * img_h) or 1.0

    fill_ratio     = min(contour_area / bbox_area, 1.0)
    coverage_ratio = bbox_area / img_area

    # Penalise if tool covers less than 5% or more than 95% of frame
    if coverage_ratio < 0.05 or coverage_ratio > 0.95:
        penalty = 0.5
    else:
        penalty = 1.0

    return float(np.clip(fill_ratio * penalty, 0.0, 1.0))


def _simplify_contour(contour: np.ndarray, max_pts: int = MAX_CONTOUR_PTS) -> list:
    """Douglas-Peucker simplification + cap at max_pts, returned as [[x,y], ...]."""
    perimeter = cv2.arcLength(contour, closed=True)
    epsilon   = 0.01 * perimeter  # 1% of perimeter
    simplified = cv2.approxPolyDP(contour, epsilon, closed=True)
    points = simplified.reshape(-1, 2).tolist()

    # If still too many points after DP, subsample evenly
    if len(points) > max_pts:
        step   = len(points) // max_pts
        points = points[::step][:max_pts]

    return [[int(p[0]), int(p[1])] for p in points]


def extract_polygon_points(
    b64_image: str,
    target_pts: int = 12,
) -> dict:
    """Return a simplified polygon outline of the largest object in the image.

    Uses adaptive Douglas-Peucker: increases epsilon until the contour is
    reduced to approximately *target_pts* control points (capped at 16).

    Points are returned as **fractions of image dimensions** (0.0–1.0) so
    the frontend can scale them to any display size without knowing the
    capture resolution.

    Returns:
        {
          "points":        [[x_pct, y_pct], ...],   # 0-1 fractions
          "confidence":    float,
          "bounding_box_pct": {"x","y","w","h"},     # all 0-1 fractions
          "image_width":   int,   # pixels (for reference)
          "image_height":  int,
          "warning":       str | None,
        }
    """
    img = _decode_image(b64_image)
    ih, iw = img.shape[:2]

    gray, blurred = _preprocess(img)
    edges  = _detect_edges(blurred)
    closed = _close_edges(edges)

    contour, bbox = _largest_contour(closed)
    x, y, w, h = bbox

    confidence = _compute_confidence(contour, w, h, img.shape)
    warning = (
        "Low confidence — retake photo against a plain, high-contrast background."
        if confidence < CONFIDENCE_WARN_THRESHOLD else None
    )

    # ── Adaptive RDP: increase epsilon until ≤ target_pts remain ─────────────
    target = max(4, min(target_pts, 16))
    perimeter = cv2.arcLength(contour, closed=True)
    epsilon   = 0.005 * perimeter  # start tight
    for _ in range(30):
        simplified = cv2.approxPolyDP(contour, epsilon, closed=True)
        if len(simplified) <= target:
            break
        epsilon *= 1.3
    else:
        # Hard cap: subsample evenly
        pts_arr = simplified.reshape(-1, 2)
        step = max(1, len(pts_arr) // target)
        simplified = pts_arr[::step][:target].reshape(-1, 1, 2)

    pts = simplified.reshape(-1, 2)
    points_pct = [[round(float(p[0]) / iw, 4), round(float(p[1]) / ih, 4)]
                  for p in pts]

    return {
        "points":    points_pct,
        "confidence": round(float(confidence), 3),
        "bounding_box_pct": {
            "x": round(x / iw, 4), "y": round(y / ih, 4),
            "w": round(w / iw, 4), "h": round(h / ih, 4),
        },
        "image_width":  iw,
        "image_height": ih,
        "warning": warning,
    }
