"""
tests/test_analyzer.py — Synthetic image tests for image_analyzer.

Generates a known rectangle on a black background (no real photo needed),
encodes it to base64, and verifies the analyzer returns sensible dimensions.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import cv2
import numpy as np

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))
from image_analyzer import analyze_tool_image, CONFIDENCE_WARN_THRESHOLD

# ── Test helpers ──────────────────────────────────────────────────────────────

def make_b64_image(
    canvas_w: int = 600,
    canvas_h: int = 800,
    rect_x: int = 200,
    rect_y: int = 200,
    rect_w: int = 200,
    rect_h: int = 400,
    noise: bool = False,
) -> str:
    """Create a white rectangle on a black BGR canvas and return as base64 JPEG."""
    img = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    cv2.rectangle(img, (rect_x, rect_y), (rect_x + rect_w, rect_y + rect_h),
                  (255, 255, 255), -1)
    if noise:
        # Sprinkle random pixels to simulate a real photo
        noise_arr = np.random.randint(0, 30, img.shape, dtype=np.uint8)
        img = cv2.add(img, noise_arr)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return base64.b64encode(buf.tobytes()).decode()


def pct_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / expected * 100


# ── Tests ─────────────────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results: list[tuple[str, str]] = []

def check(name: str, cond: bool, detail: str = "") -> None:
    label = PASS if cond else FAIL
    msg   = f"{label}  {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    results.append((name, label))


# Test 1 — Basic synthetic: 200×400 px rectangle, calibrated on height=200mm
print("\n── Test 1: basic clean rectangle ──")
b64 = make_b64_image(rect_w=200, rect_h=400)
res = analyze_tool_image(b64, known_dimension_mm=200.0, known_axis="height")

# Height calibration: 400px == 200mm → 1px = 0.5mm → width should be ~100mm
check("height_mm within ±5%", pct_error(res["height_mm"], 200.0) <= 5.0,
      f"got {res['height_mm']}")
check("width_mm within ±5%", pct_error(res["width_mm"], 100.0) <= 5.0,
      f"got {res['width_mm']}")
check("confidence >= threshold", res["confidence"] >= CONFIDENCE_WARN_THRESHOLD,
      f"got {res['confidence']:.3f}")
check("contour_points is list of [x,y]",
      isinstance(res["contour_points"], list) and len(res["contour_points"]) > 0
      and isinstance(res["contour_points"][0], list),
      f"got {len(res['contour_points'])} pts")
check("depth_mm is None", res["depth_mm"] is None)
check("bounding_box keys present",
      all(k in res["bounding_box"] for k in ("x", "y", "w", "h")))

# Test 2 — Width-axis calibration
print("\n── Test 2: calibrate by width ──")
b64 = make_b64_image(rect_w=200, rect_h=400)
res2 = analyze_tool_image(b64, known_dimension_mm=100.0, known_axis="width")
# 200px == 100mm → 1px = 0.5mm → height should be ~200mm
check("height_mm via width-cal within ±5%", pct_error(res2["height_mm"], 200.0) <= 5.0,
      f"got {res2['height_mm']}")

# Test 3 — Noisy image still detects contour
print("\n── Test 3: noisy image ──")
b64_noisy = make_b64_image(noise=True)
res3 = analyze_tool_image(b64_noisy, known_dimension_mm=200.0)
check("noisy: contour_points non-empty",
      isinstance(res3["contour_points"], list) and len(res3["contour_points"]) > 0)
check("noisy: height_mm > 0", res3["height_mm"] > 0)
check("noisy: width_mm > 0",  res3["width_mm"]  > 0)

# Test 4 — No-contour image → ValueError
print("\n── Test 4: all-black image raises ValueError ──")
all_black = np.zeros((400, 300, 3), dtype=np.uint8)
_, buf = cv2.imencode(".jpg", all_black)
b64_black = base64.b64encode(buf.tobytes()).decode()
try:
    analyze_tool_image(b64_black, 200.0)
    check("raises ValueError on blank", False, "no exception")
except ValueError:
    check("raises ValueError on blank", True)

# Test 5 — data-URL prefix stripped correctly
print("\n── Test 5: data-URL prefix handled ──")
b64_clean = make_b64_image()
b64_with_prefix = f"data:image/jpeg;base64,{b64_clean}"
res5 = analyze_tool_image(b64_with_prefix, 200.0)
check("data-URL prefix accepted", res5["height_mm"] > 0,
      f"got {res5['height_mm']}")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
passed  = sum(1 for _, r in results if r == PASS)
total   = len(results)
print(f"Results: {passed}/{total} passed")
if passed < total:
    sys.exit(1)
