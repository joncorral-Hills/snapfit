"""
Parametric STL generator for SnapFit tool wall holders.

Supports four mounting systems:
  magnetic   — flat back plate + 2× neodymium magnet boss cylinders
  gridfinity — Gridfinity-compatible base (42mm grid, chamfered feet, stacking lip)
  multiboard — Multiboard-compatible back plate (25mm T-slot hole grid)
  opengrid   — OpenGrid-compatible back plate (50mm peg socket grid)

Holder anatomy (shared cradle):
  Back plate  : varies per mounting system
  Side walls  : WALL thick, DEPTH mm deep
  Bottom floor: WALL thick, full inner width
  Front lip   : LIP_CRADLE mm tall retaining strip at cradle mouth
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from stl import mesh

if TYPE_CHECKING:
    from models import Tool

# ── Shared cradle constants ───────────────────────────────────────────────────
WALL: float        = 8.0    # back plate / wall thickness mm
PAD: float         = 5.0    # clearance padding around tool body (each side)
DEPTH: float       = 15.0   # side wall depth (front-to-back)
LIP_CRADLE: float  = 12.0   # front retaining lip height

# ── Magnetic base constants ───────────────────────────────────────────────────
MAGNET_D: float    = 20.0   # neodymium disc diameter mm
MAGNET_H: float    = 6.0    # magnet slot depth mm
CYL_SEGS: int      = 32

# ── Gridfinity base constants ─────────────────────────────────────────────────
GF_GRID: float     = 42.0   # mm per Gridfinity unit
GF_LIP_H: float    = 2.6    # stacking lip height mm
GF_FOOT_H: float   = 4.4    # total foot height mm
GF_CHAMFER: float  = 0.8    # chamfer on top of foot mm
GF_FOOT_W: float   = 7.5    # foot plan outer width mm
GF_LIP_WALL: float = 1.8    # stacking lip ring wall thickness mm
GF_SLAB: float     = 2.0    # base slab thickness linking feet

# ── Multiboard base constants ─────────────────────────────────────────────────
MB_GRID: float     = 25.0   # Multiboard hole pitch mm
MB_HOLE_D: float   = 5.0    # T-slot hole diameter mm
MB_SLAB: float     = 3.0    # back plate thickness mm
MB_EDGE: float     = 12.5   # inset of first hole from edge mm

# ── OpenGrid base constants ───────────────────────────────────────────────────
OG_GRID: float     = 50.0   # OpenGrid peg pitch mm
OG_PEG_D: float    = 6.0    # peg socket diameter mm
OG_PEG_DEPTH: float= 4.0    # peg socket depth mm
OG_SLAB: float     = 3.0    # back plate thickness mm
OG_EDGE: float     = 25.0   # inset of first peg from edge mm

MountingSystem = Literal["magnetic", "gridfinity", "multiboard", "opengrid", "blank"]

OUTPUT_DIR = Path(__file__).parent / "generated_stls"


# ═══════════════════════════════════════════════════════════════════════════════
# Primitive helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _box_faces(x0: float, y0: float, z0: float,
               x1: float, y1: float, z1: float) -> np.ndarray:
    """12 triangles forming a solid axis-aligned box."""
    v = np.array([
        [x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
        [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1],
    ], dtype=np.float32)
    fi = [
        [0,2,1],[0,3,2], [4,5,6],[4,6,7],
        [0,1,5],[0,5,4], [3,6,2],[3,7,6],
        [0,4,7],[0,7,3], [1,2,6],[1,6,5],
    ]
    return np.array([[v[i] for i in f] for f in fi], dtype=np.float32)


def _cylinder_faces(cx: float, cy: float, z_bot: float, z_top: float,
                    radius: float, segs: int = CYL_SEGS) -> np.ndarray:
    """Solid upright cylinder centred at (cx, cy)."""
    angles = [2 * math.pi * i / segs for i in range(segs)]
    tris = []
    for i in range(segs):
        a0, a1 = angles[i], angles[(i + 1) % segs]
        x0, y0 = cx + radius * math.cos(a0), cy + radius * math.sin(a0)
        x1, y1 = cx + radius * math.cos(a1), cy + radius * math.sin(a1)
        tris.append([[x0,y0,z_bot],[x1,y1,z_bot],[x1,y1,z_top]])
        tris.append([[x0,y0,z_bot],[x1,y1,z_top],[x0,y0,z_top]])
        tris.append([[cx,cy,z_top],[x0,y0,z_top],[x1,y1,z_top]])
        tris.append([[cx,cy,z_bot],[x1,y1,z_bot],[x0,y0,z_bot]])
    return np.array(tris, dtype=np.float32)


def _build_mesh(triangle_list: list[np.ndarray]) -> mesh.Mesh:
    all_tris = np.vstack(triangle_list)
    m = mesh.Mesh(np.zeros(len(all_tris), dtype=mesh.Mesh.dtype))
    for i, tri in enumerate(all_tris):
        m.vectors[i] = tri
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# Shared cradle (walls, floor, lip) — same for all mounting systems
# ═══════════════════════════════════════════════════════════════════════════════

def _build_cradle(h_width: float, h_height: float,
                  h_depth: float, z_offset: float) -> list[np.ndarray]:
    """
    Build the tool cradle (side walls + floor + front lip) raised by z_offset.
    z_offset accounts for the base plate height (e.g. 7mm for Gridfinity).
    Back of cradle aligns to Y=0; cradle opens toward +Y.
    """
    tris: list[np.ndarray] = []

    zb = z_offset
    # Left side wall
    tris.append(_box_faces(0, 0, zb, WALL, h_depth, zb + h_height))
    # Right side wall
    tris.append(_box_faces(h_width - WALL, 0, zb, h_width, h_depth, zb + h_height))
    # Bottom floor
    tris.append(_box_faces(WALL, 0, zb, h_width - WALL, h_depth, zb + WALL))
    # Front lip
    tris.append(_box_faces(WALL, h_depth - WALL, zb,
                           h_width - WALL, h_depth, zb + LIP_CRADLE))
    return tris


# ═══════════════════════════════════════════════════════════════════════════════
# Back plate / base builders — one per mounting system
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. Magnetic ───────────────────────────────────────────────────────────────

def _build_back_magnetic(h_width: float, h_height: float) -> list[np.ndarray]:
    """Flat slab + 2× magnet boss cylinders on front face."""
    tris: list[np.ndarray] = []
    tris.append(_box_faces(0, 0, 0, h_width, WALL, h_height))
    cx = h_width / 2
    for cz in [h_height / 3, 2 * h_height / 3]:
        tris.append(_cylinder_faces(cx, 0, cz - MAGNET_D / 2, cz + MAGNET_D / 2,
                                    MAGNET_D / 2, CYL_SEGS))
    return tris


# ── 1b. Blank ─────────────────────────────────────────────────────────────────

def _build_back_blank(h_width: float, h_height: float) -> list[np.ndarray]:
    """Plain flat slab — no magnets, no grid features. Universal / wall-screw mount."""
    return [_box_faces(0, 0, 0, h_width, WALL, h_height)]


# ── 2. Gridfinity ─────────────────────────────────────────────────────────────

def _gf_chamfered_foot(cx: float, cy: float) -> list[np.ndarray]:
    """One Gridfinity foot: straight lower block + chamfered frustum top."""
    tris: list[np.ndarray] = []
    hw   = GF_FOOT_W / 2
    hwt  = (GF_FOOT_W - 2 * GF_CHAMFER) / 2
    z_s  = GF_FOOT_H - GF_CHAMFER   # top of straight section (3.6mm)

    # Straight lower block
    tris.append(_box_faces(cx - hw, cy - hw, 0, cx + hw, cy + hw, z_s))

    # Chamfered frustum top
    bx0, bx1 = cx - hw,  cx + hw
    by0, by1 = cy - hw,  cy + hw
    tx0, tx1 = cx - hwt, cx + hwt
    ty0, ty1 = cy - hwt, cy + hwt
    zb, zt = z_s, GF_FOOT_H

    # Bottom cap
    tris.append(np.array([
        [[bx0,by0,zb],[bx1,by1,zb],[bx1,by0,zb]],
        [[bx0,by0,zb],[bx0,by1,zb],[bx1,by1,zb]],
    ], dtype=np.float32))
    # Top cap
    tris.append(np.array([
        [[tx0,ty0,zt],[tx1,ty0,zt],[tx1,ty1,zt]],
        [[tx0,ty0,zt],[tx1,ty1,zt],[tx0,ty1,zt]],
    ], dtype=np.float32))
    # 4 tapered sides
    for (a,b,c,d) in [
        ([bx0,by0,zb],[bx1,by0,zb],[tx1,ty0,zt],[tx0,ty0,zt]),
        ([bx1,by1,zb],[bx0,by1,zb],[tx0,ty1,zt],[tx1,ty1,zt]),
        ([bx0,by1,zb],[bx0,by0,zb],[tx0,ty0,zt],[tx0,ty1,zt]),
        ([bx1,by0,zb],[bx1,by1,zb],[tx1,ty1,zt],[tx1,ty0,zt]),
    ]:
        tris.append(np.array([[a,b,c],[a,c,d]], dtype=np.float32))
    return tris


def _gf_stacking_lip(ox: float, oy: float) -> list[np.ndarray]:
    """Stacking lip frame for one 42×42mm Gridfinity cell."""
    zb, zt = GF_FOOT_H, GF_FOOT_H + GF_LIP_H
    w = GF_LIP_WALL
    return [
        _box_faces(ox,           oy,           zb, ox + GF_GRID,       oy + w,         zt),
        _box_faces(ox,           oy + GF_GRID - w, zb, ox + GF_GRID,   oy + GF_GRID,   zt),
        _box_faces(ox,           oy + w,       zb, ox + w,             oy + GF_GRID-w, zt),
        _box_faces(ox+GF_GRID-w, oy + w,       zb, ox + GF_GRID,       oy + GF_GRID-w, zt),
    ]


def _build_back_gridfinity(h_width: float, h_height: float) -> tuple[list[np.ndarray], float]:
    """
    Gridfinity base. Returns (triangle_list, z_offset) where z_offset is the
    height at which the cradle should start (top of stacking lip).
    """
    n_x = max(1, math.ceil(h_width  / GF_GRID))
    n_y = max(1, math.ceil(h_height / GF_GRID))
    tris: list[np.ndarray] = []

    # Base slab linking all feet
    tris.append(_box_faces(0, 0, 0, n_x * GF_GRID, n_y * GF_GRID, GF_SLAB))

    for gx in range(n_x):
        for gy in range(n_y):
            ox = gx * GF_GRID
            oy = gy * GF_GRID
            # 4 corner feet
            margin = GF_FOOT_W / 2
            for cx, cy in [
                (ox + margin,            oy + margin),
                (ox + GF_GRID - margin,  oy + margin),
                (ox + margin,            oy + GF_GRID - margin),
                (ox + GF_GRID - margin,  oy + GF_GRID - margin),
            ]:
                tris.extend(_gf_chamfered_foot(cx, cy))
            # Stacking lip
            tris.extend(_gf_stacking_lip(ox, oy))

    z_offset = GF_FOOT_H + GF_LIP_H  # 7.0mm
    return tris, z_offset


# ── 3. Multiboard ─────────────────────────────────────────────────────────────

def _build_back_multiboard(h_width: float, h_height: float) -> tuple[list[np.ndarray], float]:
    """
    Multiboard back plate: 3mm slab + raised boss dimples on 25mm grid.
    Bosses are Ø5mm × 1.5mm raised cylinders marking T-slot hole positions.
    (True T-slot cutouts require boolean CSG; bosses serve as drill guides.)
    """
    tris: list[np.ndarray] = []
    # Plain back slab
    tris.append(_box_faces(0, 0, 0, h_width, h_height, MB_SLAB))

    # Boss grid
    x = MB_EDGE
    while x <= h_width - MB_EDGE + 0.1:
        y = MB_EDGE
        while y <= h_height - MB_EDGE + 0.1:
            tris.append(_cylinder_faces(x, y, MB_SLAB, MB_SLAB + 1.5,
                                        MB_HOLE_D / 2, 16))
            y += MB_GRID
        x += MB_GRID

    return tris, MB_SLAB


# ── 4. OpenGrid ───────────────────────────────────────────────────────────────

def _build_back_opengrid(h_width: float, h_height: float) -> tuple[list[np.ndarray], float]:
    """
    OpenGrid back plate: 3mm slab + Ø6mm × 4mm deep peg socket bosses on 50mm grid.
    Bosses are raised cylinders to indicate peg positions.
    """
    tris: list[np.ndarray] = []
    tris.append(_box_faces(0, 0, 0, h_width, h_height, OG_SLAB))

    x = OG_EDGE
    while x <= h_width - OG_EDGE + 0.1:
        y = OG_EDGE
        while y <= h_height - OG_EDGE + 0.1:
            tris.append(_cylinder_faces(x, y, OG_SLAB, OG_SLAB + OG_PEG_DEPTH,
                                        OG_PEG_D / 2, 20))
            y += OG_GRID
        x += OG_GRID

    return tris, OG_SLAB


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def generate_holder(tool: "Tool",
                    mounting_system: MountingSystem = "magnetic") -> Path:
    """
    Generate a wall-holder STL for *tool* using *mounting_system*.
    Returns the Path to the saved .stl file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    h_width:  float = tool.body_width_mm  + 2 * (PAD + WALL)
    h_height: float = tool.body_height_mm + 2 * (PAD + WALL)
    h_depth:  float = tool.body_depth_mm  + DEPTH

    triangles: list[np.ndarray] = []

    if mounting_system == "gridfinity":
        base_tris, z_off = _build_back_gridfinity(h_width, h_height)
    elif mounting_system == "multiboard":
        base_tris, z_off = _build_back_multiboard(h_width, h_height)
    elif mounting_system == "opengrid":
        base_tris, z_off = _build_back_opengrid(h_width, h_height)
    elif mounting_system == "blank":
        base_tris = _build_back_blank(h_width, h_height)
        z_off = 0.0
    else:  # magnetic (default)
        base_tris = _build_back_magnetic(h_width, h_height)
        z_off = 0.0

    triangles.extend(base_tris)
    triangles.extend(_build_cradle(h_width, h_height, h_depth, z_off))

    holder_mesh = _build_mesh(triangles)

    safe_brand  = tool.brand.replace(" ", "_").lower()
    safe_model  = tool.model_name.replace(" ", "_").replace("/", "-").lower()
    filename    = f"{safe_brand}_{safe_model}_{mounting_system}.stl"
    out_path    = OUTPUT_DIR / filename
    holder_mesh.save(str(out_path))
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    from types import SimpleNamespace

    # Milwaukee 2801-20: body_width=165, body_height=197, body_depth=58
    tool = SimpleNamespace(
        brand="Milwaukee", model_name="2801-20 Compact Drill-Driver",
        body_width_mm=165.0, body_height_mm=197.0, body_depth_mm=58.0,
        handle_diameter_mm=38.0, weight_kg=1.13,
    )

    systems: list[MountingSystem] = ["magnetic", "gridfinity", "multiboard", "opengrid"]
    for sys in systems:
        path = generate_holder(tool, sys)  # type: ignore[arg-type]
        m = mesh.Mesh.from_file(str(path))
        xr = f"{m.vectors[:,:,0].min():.1f}→{m.vectors[:,:,0].max():.1f}"
        yr = f"{m.vectors[:,:,1].min():.1f}→{m.vectors[:,:,1].max():.1f}"
        zr = f"{m.vectors[:,:,2].min():.1f}→{m.vectors[:,:,2].max():.1f}"
        print(f"[{sys:12}] {len(m.vectors):5,} tris | X:{xr} Y:{yr} Z:{zr} | {path.name}")
