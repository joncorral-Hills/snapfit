"""
Parametric STL generator for SnapFit tool wall holders.

Mounting systems:
  gridfinity — Gridfinity cutout bin: silhouette cavity recessed DOWN from top surface
  magnetic   — wall-mount cradle, flat back + magnet bosses
  multiboard — wall-mount cradle, Multiboard 25mm T-slot back
  opengrid   — wall-mount cradle, OpenGrid 50mm peg back
  blank      — wall-mount cradle, plain flat back (universal)
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import TYPE_CHECKING, List, Literal, Optional, Tuple
import numpy as np
from stl import mesh

if TYPE_CHECKING:
    from models import Tool

# ── Shared cradle constants ───────────────────────────────────────────────────
WALL: float        = 8.0
PAD: float         = 5.0
DEPTH: float       = 15.0
LIP_CRADLE: float  = 12.0

# ── Magnetic ──────────────────────────────────────────────────────────────────
MAGNET_D: float    = 20.0
CYL_SEGS: int      = 32

# ── Gridfinity base ───────────────────────────────────────────────────────────
GF_GRID: float     = 42.0
GF_LIP_H: float    = 2.6
GF_FOOT_H: float   = 4.4
GF_CHAMFER: float  = 0.8
GF_FOOT_W: float   = 7.5
GF_LIP_WALL: float = 1.8
GF_SLAB: float     = 2.0

# ── Gridfinity cutout-bin ─────────────────────────────────────────────────────
GF_BIN_WALL: float   = 2.4   # outer wall thickness mm
GF_BIN_FLOOR: float  = 2.0   # solid floor below cavity mm
GF_Z_UNIT: float     = GF_FOOT_H + GF_LIP_H   # 7.0 mm vertical unit
CAVITY_TOL: float    = 0.8   # outward offset for clearance mm
CAVITY_DEPTH: float  = 14.0  # default cavity depth mm

# ── Multiboard ────────────────────────────────────────────────────────────────
MB_GRID: float = 25.0; MB_HOLE_D: float = 5.0
MB_SLAB: float = 3.0;  MB_EDGE: float  = 12.5

# ── OpenGrid ──────────────────────────────────────────────────────────────────
OG_GRID: float = 50.0; OG_PEG_D: float = 6.0
OG_PEG_DEPTH: float = 4.0; OG_SLAB: float = 3.0; OG_EDGE: float = 25.0

MountingSystem = Literal["magnetic", "gridfinity", "multiboard", "opengrid", "blank"]
OUTPUT_DIR = Path(__file__).parent / "generated_stls"


# ═══════════════════════════════════════════════════════════════════════════════
# Primitive helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _box_faces(x0: float, y0: float, z0: float,
               x1: float, y1: float, z1: float) -> np.ndarray:
    v = np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                  [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]], dtype=np.float32)
    fi = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
          [3,6,2],[3,7,6],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    return np.array([[v[i] for i in f] for f in fi], dtype=np.float32)


def _cylinder_faces(cx: float, cy: float, z_bot: float, z_top: float,
                    radius: float, segs: int = CYL_SEGS) -> np.ndarray:
    ang = [2*math.pi*i/segs for i in range(segs)]
    tris = []
    for i in range(segs):
        a0, a1 = ang[i], ang[(i+1) % segs]
        x0,y0 = cx+radius*math.cos(a0), cy+radius*math.sin(a0)
        x1,y1 = cx+radius*math.cos(a1), cy+radius*math.sin(a1)
        tris += [[[x0,y0,z_bot],[x1,y1,z_bot],[x1,y1,z_top]],
                 [[x0,y0,z_bot],[x1,y1,z_top],[x0,y0,z_top]],
                 [[cx,cy,z_top],[x0,y0,z_top],[x1,y1,z_top]],
                 [[cx,cy,z_bot],[x1,y1,z_bot],[x0,y0,z_bot]]]
    return np.array(tris, dtype=np.float32)


def _build_mesh(tris: List[np.ndarray]) -> mesh.Mesh:
    a = np.vstack(tris)
    m = mesh.Mesh(np.zeros(len(a), dtype=mesh.Mesh.dtype))
    for i, t in enumerate(a):
        m.vectors[i] = t
    return m


def _validate_stl(path: "Path") -> dict:
    """
    Quick watertight check on a saved STL file.
    Returns dict with is_valid, triangle_count, degenerate_count, open_edge_count.
    Samples up to 8 000 triangles for the edge-manifold test (fast enough for UI).
    """
    try:
        from collections import Counter
        m = mesh.Mesh.from_file(str(path))
        v0, v1, v2 = m.vectors[:,0], m.vectors[:,1], m.vectors[:,2]
        areas = 0.5 * np.linalg.norm(np.cross(v1-v0, v2-v0), axis=1)
        degenerate = int(np.sum(areas < 1e-6))

        sample = m.vectors[:min(8000, len(m.vectors))]
        edge_cnt: Counter = Counter()
        for tri in sample:
            for i in range(3):
                a = tuple(np.round(tri[i], 1))
                b = tuple(np.round(tri[(i+1)%3], 1))
                edge_cnt[(min(a,b), max(a,b))] += 1
        open_edges = sum(1 for v in edge_cnt.values() if v != 2)

        ok = degenerate == 0 and open_edges == 0
        return {
            "is_valid": ok,
            "triangle_count": len(m.vectors),
            "degenerate_count": degenerate,
            "open_edge_count": open_edges,
            "warning": None if ok else f"{degenerate} degenerate, {open_edges} open edges",
        }
    except Exception as exc:
        return {"is_valid": False, "warning": str(exc),
                "triangle_count": 0, "degenerate_count": 0, "open_edge_count": 0}


# ═══════════════════════════════════════════════════════════════════════════════
# Wall-mount cradle helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _build_cradle(h_width: float, h_height: float,
                  h_depth: float, z_offset: float) -> List[np.ndarray]:
    zb = z_offset
    return [
        _box_faces(0,            0,       zb, WALL,         h_depth, zb+h_height),
        _box_faces(h_width-WALL, 0,       zb, h_width,      h_depth, zb+h_height),
        _box_faces(WALL,         0,       zb, h_width-WALL, h_depth, zb+WALL),
        _box_faces(WALL, h_depth-WALL,    zb, h_width-WALL, h_depth, zb+LIP_CRADLE),
    ]


def _contour_to_mm_polygon(
    contour_points: List[List[float]],
    px_per_mm: float, bbox_x: float, bbox_y: float,
    pad: float = PAD,
) -> List[Tuple[float, float]]:
    pts = [(p[0]-bbox_x, p[1]-bbox_y) for p in contour_points]
    return [(x/px_per_mm+pad, y/px_per_mm+pad) for x, y in pts]


def _build_contour_cradle(
    polygon_mm: List[Tuple[float, float]],
    h_width: float, h_height: float, h_depth: float,
    z_offset: float, cavity_depth: float = 0.0,
) -> List[np.ndarray]:
    if cavity_depth == 0.0:
        cavity_depth = h_depth * 0.7
    tris: List[np.ndarray] = []
    zb, zt = z_offset, z_offset+cavity_depth
    n = len(polygon_mm)
    cx = sum(p[0] for p in polygon_mm)/n
    cy = sum(p[1] for p in polygon_mm)/n
    for i in range(n):
        x0,y0 = polygon_mm[i]; x1,y1 = polygon_mm[(i+1)%n]
        tris.append(np.array([[[x0,y0,zb],[x1,y1,zb],[x1,y1,zt]],
                               [[x0,y0,zb],[x1,y1,zt],[x0,y0,zt]]], dtype=np.float32))
        tris.append(np.array([[[cx,cy,zb],[x0,y0,zb],[x1,y1,zb]]], dtype=np.float32))
    tris.append(_box_faces(WALL, h_depth-WALL, zb, h_width-WALL, h_depth, zb+LIP_CRADLE))
    return tris


# ═══════════════════════════════════════════════════════════════════════════════
# 2-D polygon utilities (for Gridfinity cutout path)
# ═══════════════════════════════════════════════════════════════════════════════

def _signed_area(pts: List[Tuple[float, float]]) -> float:
    n = len(pts)
    return 0.5*sum(pts[i][0]*pts[(i+1)%n][1]-pts[(i+1)%n][0]*pts[i][1] for i in range(n))

def _ensure_ccw(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    return list(pts) if _signed_area(pts) > 0 else list(reversed(pts))

def _ensure_cw(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    return list(pts) if _signed_area(pts) < 0 else list(reversed(pts))

def _offset_polygon_outward(pts: List[Tuple[float, float]],
                             amount: float) -> List[Tuple[float, float]]:
    cx = sum(p[0] for p in pts)/len(pts)
    cy = sum(p[1] for p in pts)/len(pts)
    result = []
    for x, y in pts:
        d = math.hypot(x-cx, y-cy)
        result.append((x+amount*(x-cx)/d, y+amount*(y-cy)/d) if d > 1e-9 else (x, y))
    return result

def _center_polygon(pts: List[Tuple[float, float]],
                    W: float, D: float) -> List[Tuple[float, float]]:
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    dx = W/2-(min(xs)+max(xs))/2; dy = D/2-(min(ys)+max(ys))/2
    return [(x+dx, y+dy) for x, y in pts]

def _clamp_polygon(pts: List[Tuple[float, float]],
                   W: float, D: float, margin: float) -> List[Tuple[float, float]]:
    return [(max(margin, min(W-margin, x)), max(margin, min(D-margin, y))) for x, y in pts]


def _ear_clip(pts: List[Tuple[float, float]]) -> List[Tuple]:
    """O(n²) ear-clipping for simple polygon. Returns list of (a,b,c) point triples."""
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    def in_tri(p, a, b, c):
        d = cross(a,b,p), cross(b,c,p), cross(c,a,p)
        return not (min(d) < 0 and max(d) > 0)
    idx = list(range(len(pts))); result = []; budget = len(pts)**2
    while len(idx) > 3 and budget > 0:
        budget -= 1; found = False; m = len(idx)
        for i in range(m):
            pi, ni = (i-1)%m, (i+1)%m
            a, b, c = pts[idx[pi]], pts[idx[i]], pts[idx[ni]]
            if cross(a, b, c) <= 0: continue
            if all(not in_tri(pts[idx[j]], a, b, c) for j in range(m) if j not in (pi,i,ni)):
                result.append((a, b, c)); idx.pop(i); found = True; break
        if not found: break
    if len(idx) == 3:
        result.append((pts[idx[0]], pts[idx[1]], pts[idx[2]]))
    return result


def _triangulate_annular_top(W: float, D: float,
                              hole_pts: List[Tuple[float, float]],
                              z: float) -> List[np.ndarray]:
    """
    Top deck = outer CCW rectangle minus CCW inner polygon (cavity opening).
    Bridge technique: connect rightmost hole vertex to right edge of rect,
    forming a single simple polygon that can be ear-clipped.
    """
    outer = [(0.,0.), (W,0.), (W,D), (0.,D)]   # CCW rectangle
    hole  = _ensure_cw(hole_pts)                # hole CW in merged polygon

    hi = max(range(len(hole)), key=lambda i: hole[i][0])
    hx, hy = hole[hi]
    bridge = (W, max(0.0, min(D, hy)))          # hit point on right edge

    # Combined polygon: outer[0..1] + bridge_pt + hole[hi..] + hole[hi] + bridge_pt + outer[2..]
    n_h = len(hole)
    combined = list(outer[:2]) + [bridge]
    for k in range(n_h+1):
        combined.append(hole[(hi+k) % n_h])
    combined += [bridge] + list(outer[2:])
    combined = _ensure_ccw(combined)

    tris = []
    for a, b, c in _ear_clip(combined):
        tris.append(np.array([[[a[0],a[1],z],[b[0],b[1],z],[c[0],c[1],z]]], dtype=np.float32))
    return tris


# ═══════════════════════════════════════════════════════════════════════════════
# Gridfinity cutout bin
# ═══════════════════════════════════════════════════════════════════════════════

def _build_gridfinity_cutout_bin(
    n_x: int, n_y: int,
    cavity_poly: List[Tuple[float, float]],
    z_base: float,
    cavity_depth: float = CAVITY_DEPTH,
) -> List[np.ndarray]:
    """
    Solid Gridfinity bin with tool-silhouette cavity recessed from the top surface.

    Surfaces (no boolean ops — explicit mesh):
      4 outer walls  — solid rectangular exterior
      bin floor slab — solid slab above Gridfinity base, below cavity
      top deck       — annular face: outer rect minus cavity polygon opening
      cavity walls   — polygon perimeter extruded from cavity floor to top
      cavity floor   — flat floor at bottom of cavity (fan-triangulated)
    """
    W = n_x * GF_GRID
    D = n_y * GF_GRID
    # Round bin height up to nearest 7mm Gridfinity Z unit
    bin_h = GF_Z_UNIT * max(1, math.ceil((cavity_depth + GF_BIN_FLOOR) / GF_Z_UNIT))
    z_bot = z_base
    z_top = z_bot + bin_h
    z_cav = z_top - cavity_depth    # cavity floor

    tris: List[np.ndarray] = []

    # 4 outer walls
    tris += [
        _box_faces(0,            0,           z_bot, W,            GF_BIN_WALL, z_top),
        _box_faces(0,            D-GF_BIN_WALL, z_bot, W,          D,           z_top),
        _box_faces(0,            0,           z_bot, GF_BIN_WALL,  D,           z_top),
        _box_faces(W-GF_BIN_WALL, 0,          z_bot, W,            D,           z_top),
    ]

    # Bin floor: solid interior slab from z_bot up to cavity floor
    tris.append(_box_faces(GF_BIN_WALL, GF_BIN_WALL, z_bot,
                           W-GF_BIN_WALL, D-GF_BIN_WALL, z_cav))

    # Top deck: outer rect minus cavity polygon (annular face at z_top)
    poly_ccw = _ensure_ccw(cavity_poly)
    tris.extend(_triangulate_annular_top(W, D, poly_ccw, z_top))

    # Cavity walls (polygon perimeter, z_cav → z_top, normals face inward = outward from solid)
    n = len(poly_ccw)
    for i in range(n):
        x0, y0 = poly_ccw[i]
        x1, y1 = poly_ccw[(i+1) % n]
        tris.append(np.array([
            [[x0,y0,z_cav],[x1,y1,z_top],[x1,y1,z_cav]],
            [[x0,y0,z_cav],[x0,y0,z_top],[x1,y1,z_top]],
        ], dtype=np.float32))

    # Cavity floor (fan from centroid, normal points up into cavity)
    cx = sum(p[0] for p in poly_ccw) / n
    cy = sum(p[1] for p in poly_ccw) / n
    for i in range(n):
        x0,y0 = poly_ccw[i]; x1,y1 = poly_ccw[(i+1)%n]
        tris.append(np.array([[[cx,cy,z_cav],[x1,y1,z_cav],[x0,y0,z_cav]]], dtype=np.float32))

    return tris


def _default_rect_cavity(W: float, D: float) -> List[Tuple[float, float]]:
    """Fallback rectangular cavity centered in bin (used when no contour available)."""
    m = GF_BIN_WALL + 6.0
    return [(m,m), (W-m,m), (W-m,D-m), (m,D-m)]


def _build_cutout_bin(
    W: float,
    D: float,
    cavity_poly: List[Tuple[float, float]],
    z_base: float,
    cavity_depth: float = CAVITY_DEPTH,
) -> List[np.ndarray]:
    """
    Generalized solid rectangular cutout-bin for any mounting system.
    Identical geometry to _build_gridfinity_cutout_bin() but bin height is
    cavity_depth + GF_BIN_FLOOR (no Gridfinity Z-unit snapping).
    Surfaces: 4 outer walls, bin floor slab, annular top deck, cavity walls, cavity floor.
    """
    bin_h = cavity_depth + GF_BIN_FLOOR
    z_bot = z_base
    z_top = z_bot + bin_h
    z_cav = z_top - cavity_depth

    tris: List[np.ndarray] = []

    # 4 outer walls
    tris += [
        _box_faces(0,             0,            z_bot, W,             GF_BIN_WALL, z_top),
        _box_faces(0,             D-GF_BIN_WALL, z_bot, W,            D,           z_top),
        _box_faces(0,             0,            z_bot, GF_BIN_WALL,   D,           z_top),
        _box_faces(W-GF_BIN_WALL, 0,            z_bot, W,             D,           z_top),
    ]

    # Bin floor slab (z_bot → cavity floor)
    tris.append(_box_faces(GF_BIN_WALL, GF_BIN_WALL, z_bot,
                           W-GF_BIN_WALL, D-GF_BIN_WALL, z_cav))

    # Top deck: outer rect minus cavity polygon (annular face)
    poly_ccw = _ensure_ccw(cavity_poly)
    tris.extend(_triangulate_annular_top(W, D, poly_ccw, z_top))

    # Cavity walls
    n = len(poly_ccw)
    for i in range(n):
        x0, y0 = poly_ccw[i]
        x1, y1 = poly_ccw[(i+1) % n]
        tris.append(np.array([
            [[x0,y0,z_cav],[x1,y1,z_top],[x1,y1,z_cav]],
            [[x0,y0,z_cav],[x0,y0,z_top],[x1,y1,z_top]],
        ], dtype=np.float32))

    # Cavity floor (fan from centroid, normal up into cavity)
    cx = sum(p[0] for p in poly_ccw) / n
    cy = sum(p[1] for p in poly_ccw) / n
    for i in range(n):
        x0,y0 = poly_ccw[i]; x1,y1 = poly_ccw[(i+1)%n]
        tris.append(np.array([[[cx,cy,z_cav],[x1,y1,z_cav],[x0,y0,z_cav]]], dtype=np.float32))

    return tris


# ═══════════════════════════════════════════════════════════════════════════════
# Back plate builders — one per wall-mount system
# ═══════════════════════════════════════════════════════════════════════════════

def _build_back_magnetic(h_width: float, h_height: float) -> List[np.ndarray]:
    tris: List[np.ndarray] = [_box_faces(0,0,0,h_width,WALL,h_height)]
    cx = h_width / 2
    for cz in [h_height/3, 2*h_height/3]:
        tris.append(_cylinder_faces(cx, 0, cz-MAGNET_D/2, cz+MAGNET_D/2, MAGNET_D/2))
    return tris

def _build_back_blank(h_width: float, h_height: float) -> List[np.ndarray]:
    return [_box_faces(0,0,0,h_width,WALL,h_height)]

def _gf_chamfered_foot(cx: float, cy: float) -> List[np.ndarray]:
    hw = GF_FOOT_W/2; hwt = (GF_FOOT_W-2*GF_CHAMFER)/2; z_s = GF_FOOT_H-GF_CHAMFER
    tris: List[np.ndarray] = [_box_faces(cx-hw,cy-hw,0,cx+hw,cy+hw,z_s)]
    bx0,bx1,by0,by1 = cx-hw,cx+hw,cy-hw,cy+hw
    tx0,tx1,ty0,ty1 = cx-hwt,cx+hwt,cy-hwt,cy+hwt
    zb, zt = z_s, GF_FOOT_H
    tris.append(np.array([[[bx0,by0,zb],[bx1,by1,zb],[bx1,by0,zb]],
                           [[bx0,by0,zb],[bx0,by1,zb],[bx1,by1,zb]]], dtype=np.float32))
    tris.append(np.array([[[tx0,ty0,zt],[tx1,ty0,zt],[tx1,ty1,zt]],
                           [[tx0,ty0,zt],[tx1,ty1,zt],[tx0,ty1,zt]]], dtype=np.float32))
    for a,b,c,d in [([bx0,by0,zb],[bx1,by0,zb],[tx1,ty0,zt],[tx0,ty0,zt]),
                    ([bx1,by1,zb],[bx0,by1,zb],[tx0,ty1,zt],[tx1,ty1,zt]),
                    ([bx0,by1,zb],[bx0,by0,zb],[tx0,ty0,zt],[tx0,ty1,zt]),
                    ([bx1,by0,zb],[bx1,by1,zb],[tx1,ty1,zt],[tx1,ty0,zt])]:
        tris.append(np.array([[a,b,c],[a,c,d]], dtype=np.float32))
    return tris

def _gf_stacking_lip(ox: float, oy: float) -> List[np.ndarray]:
    zb,zt,w = GF_FOOT_H, GF_FOOT_H+GF_LIP_H, GF_LIP_WALL
    return [_box_faces(ox,oy,zb,ox+GF_GRID,oy+w,zt),
            _box_faces(ox,oy+GF_GRID-w,zb,ox+GF_GRID,oy+GF_GRID,zt),
            _box_faces(ox,oy+w,zb,ox+w,oy+GF_GRID-w,zt),
            _box_faces(ox+GF_GRID-w,oy+w,zb,ox+GF_GRID,oy+GF_GRID-w,zt)]

def _build_back_gridfinity(h_width: float,
                            h_height: float) -> Tuple[List[np.ndarray], float]:
    n_x = max(1, math.ceil(h_width/GF_GRID))
    n_y = max(1, math.ceil(h_height/GF_GRID))
    tris: List[np.ndarray] = [_box_faces(0,0,0,n_x*GF_GRID,n_y*GF_GRID,GF_SLAB)]
    for gx in range(n_x):
        for gy in range(n_y):
            ox,oy = gx*GF_GRID, gy*GF_GRID; m = GF_FOOT_W/2
            for cx,cy in [(ox+m,oy+m),(ox+GF_GRID-m,oy+m),
                          (ox+m,oy+GF_GRID-m),(ox+GF_GRID-m,oy+GF_GRID-m)]:
                tris.extend(_gf_chamfered_foot(cx,cy))
            tris.extend(_gf_stacking_lip(ox,oy))
    return tris, GF_FOOT_H + GF_LIP_H

def _build_back_multiboard(h_width: float,
                            h_height: float) -> Tuple[List[np.ndarray], float]:
    """Flat slab + T-slot boss pegs protruding from the BACK face (z < 0)."""
    tris: List[np.ndarray] = [_box_faces(0,0,0,h_width,h_height,MB_SLAB)]
    x = MB_EDGE
    while x <= h_width-MB_EDGE+0.1:
        y = MB_EDGE
        while y <= h_height-MB_EDGE+0.1:
            # Pegs protrude behind the slab to engage Multiboard T-slot holes
            tris.append(_cylinder_faces(x, y, -MB_HOLE_D/2, 0, MB_HOLE_D/2, 16))
            y += MB_GRID
        x += MB_GRID
    return tris, MB_SLAB

def _build_back_opengrid(h_width: float,
                          h_height: float) -> Tuple[List[np.ndarray], float]:
    """Flat slab + peg sockets protruding from the BACK face (z < 0)."""
    tris: List[np.ndarray] = [_box_faces(0,0,0,h_width,h_height,OG_SLAB)]
    x = OG_EDGE
    while x <= h_width-OG_EDGE+0.1:
        y = OG_EDGE
        while y <= h_height-OG_EDGE+0.1:
            # Pegs protrude behind the slab to engage OpenGrid wall panel holes
            tris.append(_cylinder_faces(x, y, -OG_PEG_DEPTH, 0, OG_PEG_D/2, 20))
            y += OG_GRID
        x += OG_GRID
    return tris, OG_SLAB


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def generate_holder(
    tool: "Tool",
    mounting_system: MountingSystem = "magnetic",
    contour_points: Optional[List[List[float]]] = None,
    px_per_mm: Optional[float] = None,
) -> Path:
    """
    Generate a holder STL for *tool*.

    Gridfinity  → cutout-bin: solid tray with cavity recessed DOWN from top surface
    All others  → wall-mount cradle: additive walls around the tool silhouette

    Pass contour_points + px_per_mm for silhouette-shaped geometry; omit for rectangle fallback.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    h_width  = tool.body_width_mm  + 2*(PAD+WALL)
    h_height = tool.body_height_mm + 2*(PAD+WALL)
    h_depth  = tool.body_depth_mm  + DEPTH
    triangles: List[np.ndarray] = []

    # ── GRIDFINITY: cutout-bin path ───────────────────────────────────────────
    if mounting_system == "gridfinity":
        n_x = max(1, math.ceil(h_width  / GF_GRID))
        n_y = max(1, math.ceil(h_height / GF_GRID))
        W, D = n_x*GF_GRID, n_y*GF_GRID

        base_tris, z_base = _build_back_gridfinity(W, D)
        triangles.extend(base_tris)

        if contour_points and px_per_mm:
            bbox_x = getattr(tool, "bbox_x", 0)
            bbox_y = getattr(tool, "bbox_y", 0)
            poly = _contour_to_mm_polygon(contour_points, px_per_mm, bbox_x, bbox_y)
            poly = _offset_polygon_outward(poly, CAVITY_TOL)
            poly = _center_polygon(poly, W, D)
            poly = _clamp_polygon(poly, W, D, GF_BIN_WALL + 1.5)
        else:
            poly = _default_rect_cavity(W, D)

        triangles.extend(_build_gridfinity_cutout_bin(n_x, n_y, poly, z_base))

    # ── ALL OTHER SYSTEMS: system-specific back plate + shared cutout bin ────────
    else:
        W, D = h_width, h_height
        if mounting_system == "multiboard":
            base_tris, z_off = _build_back_multiboard(W, D)
        elif mounting_system == "opengrid":
            base_tris, z_off = _build_back_opengrid(W, D)
        elif mounting_system == "blank":
            base_tris = _build_back_blank(W, D); z_off = WALL
        else:  # magnetic
            base_tris = _build_back_magnetic(W, D); z_off = WALL

        triangles.extend(base_tris)

        if contour_points and px_per_mm:
            bbox_x = getattr(tool, "bbox_x", 0)
            bbox_y = getattr(tool, "bbox_y", 0)
            poly = _contour_to_mm_polygon(contour_points, px_per_mm, bbox_x, bbox_y)
            poly = _offset_polygon_outward(poly, CAVITY_TOL)
            poly = _center_polygon(poly, W, D)
            poly = _clamp_polygon(poly, W, D, GF_BIN_WALL + 1.5)
        else:
            poly = _default_rect_cavity(W, D)

        triangles.extend(_build_cutout_bin(W, D, poly, z_off))

    holder_mesh = _build_mesh(triangles)
    safe_brand = tool.brand.replace(" ","_").lower()
    safe_model = tool.model_name.replace(" ","_").replace("/","-").lower()
    out_path = OUTPUT_DIR / f"{safe_brand}_{safe_model}_{mounting_system}.stl"
    holder_mesh.save(str(out_path))
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    from types import SimpleNamespace
    tool = SimpleNamespace(
        brand="Milwaukee", model_name="2801-20",
        body_width_mm=165.0, body_height_mm=197.0, body_depth_mm=58.0,
        bbox_x=0, bbox_y=0,
    )
    drill_pts = [[10,10],[155,10],[155,80],[120,80],[120,187],[55,187],[55,80],[10,80]]
    for ms in ["gridfinity","blank","magnetic","opengrid","multiboard"]:
        path = generate_holder(tool, ms, contour_points=drill_pts, px_per_mm=1.0)
        m = mesh.Mesh.from_file(str(path))
        print(f"[{ms:12}] {len(m.vectors):5,} tris | {path.name}")
