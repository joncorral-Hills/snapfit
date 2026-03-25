"""
Parametric STL generator for SnapFit tool wall holders.

Generates a form-fitting magnetic wall holder for a given tool using
numpy-stl to build triangle meshes directly — no OpenSCAD/CadQuery needed.

Holder anatomy
--------------
  Back plate   : (tool_width + WALL*2+PAD) × (tool_height + WALL*2+PAD) × BACK_THICK mm
  Side walls   : WALL thick, DEPTH mm deep on left/right of cradle
  Bottom floor : WALL thick, spans full width
  Front lip    : LIP_H mm tall strip at the front edge of the side walls
  Magnet slots : 2× Ø20 × 6 mm cylindrical recesses centred on back plate
                 at 1/3 and 2/3 of holder height
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from stl import mesh

if TYPE_CHECKING:
    from models import Tool

# ── Constants ────────────────────────────────────────────────────────────────
WALL: float = 8.0        # wall/back-plate thickness mm
PAD: float = 5.0         # clearance padding around tool body (each side)
DEPTH: float = 15.0      # how far the side walls extend forward from backplate
LIP_H: float = 12.0      # front lip height
MAGNET_D: float = 20.0   # neodymium disc magnet diameter mm
MAGNET_H: float = 6.0    # magnet depth mm (how deep the slot goes into back plate)
CYL_SEGS: int = 32       # polygon approximation segments for magnet cylinders

OUTPUT_DIR = Path(__file__).parent / "generated_stls"


# ── Primitive helpers ─────────────────────────────────────────────────────────

def _box_faces(x0: float, y0: float, z0: float,
               x1: float, y1: float, z1: float) -> np.ndarray:
    """Return 12 triangles (36 vertices) forming a solid box.
    Vertices are in (x,y,z) order; face normals point outward."""
    # 8 corners
    v = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],  # bottom face
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],  # top face
    ], dtype=np.float32)
    # 6 faces × 2 triangles each = 12 triangles
    face_indices = [
        # bottom (−Z)
        [0, 2, 1], [0, 3, 2],
        # top (+Z)
        [4, 5, 6], [4, 6, 7],
        # front (−Y)
        [0, 1, 5], [0, 5, 4],
        # back (+Y)
        [3, 6, 2], [3, 7, 6],
        # left (−X)
        [0, 4, 7], [0, 7, 3],
        # right (+X)
        [1, 2, 6], [1, 6, 5],
    ]
    tris = np.array([[v[i] for i in face] for face in face_indices], dtype=np.float32)
    return tris  # shape (12, 3, 3)


def _cylinder_faces(cx: float, cy: float,
                    z_bottom: float, z_top: float,
                    radius: float, segments: int = CYL_SEGS) -> np.ndarray:
    """Return triangle faces for a solid upright cylinder centred at (cx, cy)."""
    angles = [2 * math.pi * i / segments for i in range(segments)]
    tris = []
    for i in range(segments):
        a0, a1 = angles[i], angles[(i + 1) % segments]
        x0, y0 = cx + radius * math.cos(a0), cy + radius * math.sin(a0)
        x1, y1 = cx + radius * math.cos(a1), cy + radius * math.sin(a1)
        # Side quad → 2 tris
        tris.append([[x0, y0, z_bottom], [x1, y1, z_bottom], [x1, y1, z_top]])
        tris.append([[x0, y0, z_bottom], [x1, y1, z_top],    [x0, y0, z_top]])
        # Top cap
        tris.append([[cx, cy, z_top],    [x0, y0, z_top],    [x1, y1, z_top]])
        # Bottom cap
        tris.append([[cx, cy, z_bottom], [x1, y1, z_bottom], [x0, y0, z_bottom]])
    return np.array(tris, dtype=np.float32)


def _build_mesh(triangle_list: list[np.ndarray]) -> mesh.Mesh:
    """Concatenate triangle arrays and return a numpy-stl Mesh."""
    all_tris = np.vstack(triangle_list)  # shape (N, 3, 3)
    m = mesh.Mesh(np.zeros(len(all_tris), dtype=mesh.Mesh.dtype))
    for i, tri in enumerate(all_tris):
        m.vectors[i] = tri
    return m


# ── Main generator ────────────────────────────────────────────────────────────

def generate_holder(tool: "Tool") -> Path:
    """Generate a wall-holder STL for *tool* and save under OUTPUT_DIR.

    Returns the Path to the saved .stl file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Holder outer dimensions ───────────────────────────────────────────────
    # holder width/height are sized to the tool + padding + two walls
    h_width: float = tool.body_width_mm + 2 * (PAD + WALL)
    h_height: float = tool.body_height_mm + 2 * (PAD + WALL)
    h_depth: float = tool.body_depth_mm + DEPTH   # total front-to-back depth

    # coordinate system: X = width, Y = depth (into wall = +Y), Z = height
    # back plate sits at Y=0 → Y=WALL (thick slab against the wall)
    # cradle opens toward -Y (toward user)

    triangles: list[np.ndarray] = []

    # 1. Back plate (full width × full height, WALL thick)
    triangles.append(_box_faces(0, 0, 0, h_width, WALL, h_height))

    # 2. Left side wall
    triangles.append(_box_faces(0, WALL, 0, WALL, h_depth, h_height))

    # 3. Right side wall
    triangles.append(_box_faces(h_width - WALL, WALL, 0, h_width, h_depth, h_height))

    # 4. Bottom floor (inner span between side walls, back to front)
    triangles.append(_box_faces(WALL, WALL, 0, h_width - WALL, h_depth, WALL))

    # 5. Front lip (short retaining wall at cradle mouth, sits on the floor)
    #    Positioned at the front of the cradle (maximum Y), full inner width
    triangles.append(_box_faces(WALL, h_depth - WALL, 0,
                                h_width - WALL, h_depth, LIP_H))

    # 6. Magnet slots — cylindrical protrusions INTO the back plate
    #    We represent magnet slots as SOLID cylinders subtracted conceptually;
    #    for MVP we embed them as negative-space markers by recessing cylinders
    #    INTO the back plate surface (adding inverted cylinder geometry).
    #    Approach: leave a cylindrical void by NOT including those faces —
    #    for a printable MVP, we add raised cylinder bosses on the back so the
    #    slicer knows where to drill/place magnets.
    #
    #    NOTE: True boolean subtraction requires CSG. For MVP we instead
    #    generate solid BOSS cylinders on the back face that the user drills out,
    #    or mark with a dimple. A future CadQuery version will do real cutouts.
    #
    #    Magnet boss: raised 3 mm peg centred on back plate face (Y=0 side)
    cx = h_width / 2
    third = h_height / 3
    for cz in [third, 2 * third]:
        # Raised boss on exterior back face (protruding away from wall, at Y=0)
        triangles.append(
            _cylinder_faces(cx, 0, cz - MAGNET_D / 2, cz + MAGNET_D / 2,
                            MAGNET_D / 2, CYL_SEGS)
        )

    # ── Assemble and save ─────────────────────────────────────────────────────
    holder_mesh = _build_mesh(triangles)

    safe_brand = tool.brand.replace(" ", "_").lower()
    safe_model = tool.model_name.replace(" ", "_").replace("/", "-").lower()
    filename = f"{safe_brand}_{safe_model}.stl"
    out_path = OUTPUT_DIR / filename
    holder_mesh.save(str(out_path))
    return out_path


# ── Quick manual test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    from types import SimpleNamespace

    dummy_tool = SimpleNamespace(
        brand="DeWalt",
        model_name="DCD771 Drill-Driver",
        body_width_mm=78.0,
        body_depth_mm=215.0,
        body_height_mm=235.0,
        handle_diameter_mm=48.0,
        weight_kg=1.36,
    )
    path = generate_holder(dummy_tool)  # type: ignore[arg-type]
    print(f"STL saved → {path}")
    print(f"File size : {path.stat().st_size:,} bytes")
    # Validate with numpy-stl
    m = mesh.Mesh.from_file(str(path))
    print(f"Triangles : {len(m.vectors):,}")
    print(f"X range   : {m.vectors[:,:,0].min():.1f} → {m.vectors[:,:,0].max():.1f} mm")
    print(f"Y range   : {m.vectors[:,:,1].min():.1f} → {m.vectors[:,:,1].max():.1f} mm")
    print(f"Z range   : {m.vectors[:,:,2].min():.1f} → {m.vectors[:,:,2].max():.1f} mm")
