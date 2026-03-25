"""Seed the SnapFit database with 10 starter tools."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database import engine, SessionLocal
from models import Base, Tool

# Dimensions sourced from manufacturer spec sheets and commonly published measurements.
# All values in millimetres except weight_kg.
STARTER_TOOLS: list[dict] = [
    # ── DeWalt 20V MAX ──────────────────────────────────────────────────────────
    {
        "brand": "DeWalt",
        "model_name": "DCD771 Drill/Driver",
        "tool_type": "Drill/Driver",
        "body_width_mm": 78.0,
        "body_depth_mm": 215.0,
        "body_height_mm": 235.0,
        "handle_diameter_mm": 48.0,
        "weight_kg": 1.36,
    },
    {
        "brand": "DeWalt",
        "model_name": "DCF887 Impact Driver",
        "tool_type": "Impact Driver",
        "body_width_mm": 78.0,
        "body_depth_mm": 149.0,
        "body_height_mm": 218.0,
        "handle_diameter_mm": 46.0,
        "weight_kg": 1.06,
    },
    {
        "brand": "DeWalt",
        "model_name": "DCS391 Circular Saw",
        "tool_type": "Circular Saw",
        "body_width_mm": 290.0,
        "body_depth_mm": 355.0,
        "body_height_mm": 230.0,
        "handle_diameter_mm": 60.0,
        "weight_kg": 2.95,
    },
    # ── Milwaukee M18 ───────────────────────────────────────────────────────────
    {
        "brand": "Milwaukee",
        "model_name": "M18 2801-20 Drill/Driver",
        "tool_type": "Drill/Driver",
        "body_width_mm": 80.0,
        "body_depth_mm": 200.0,
        "body_height_mm": 228.0,
        "handle_diameter_mm": 49.0,
        "weight_kg": 1.57,
    },
    {
        "brand": "Milwaukee",
        "model_name": "M18 2853-20 Impact Driver",
        "tool_type": "Impact Driver",
        "body_width_mm": 81.0,
        "body_depth_mm": 148.0,
        "body_height_mm": 215.0,
        "handle_diameter_mm": 47.0,
        "weight_kg": 1.42,
    },
    {
        "brand": "Milwaukee",
        "model_name": "M18 6390-20 Circular Saw",
        "tool_type": "Circular Saw",
        "body_width_mm": 295.0,
        "body_depth_mm": 370.0,
        "body_height_mm": 240.0,
        "handle_diameter_mm": 62.0,
        "weight_kg": 3.17,
    },
    {
        "brand": "Milwaukee",
        "model_name": "M18 2767-20 Impact Wrench",
        "tool_type": "Impact Wrench",
        "body_width_mm": 90.0,
        "body_depth_mm": 185.0,
        "body_height_mm": 250.0,
        "handle_diameter_mm": 52.0,
        "weight_kg": 2.40,
    },
    # ── Ryobi ONE+ ──────────────────────────────────────────────────────────────
    {
        "brand": "Ryobi",
        "model_name": "PCL206K1 Drill/Driver",
        "tool_type": "Drill/Driver",
        "body_width_mm": 76.0,
        "body_depth_mm": 195.0,
        "body_height_mm": 220.0,
        "handle_diameter_mm": 46.0,
        "weight_kg": 1.13,
    },
    {
        "brand": "Ryobi",
        "model_name": "PCL235B Impact Driver",
        "tool_type": "Impact Driver",
        "body_width_mm": 76.0,
        "body_depth_mm": 140.0,
        "body_height_mm": 210.0,
        "handle_diameter_mm": 44.0,
        "weight_kg": 1.04,
    },
    {
        "brand": "Ryobi",
        "model_name": "PBLCS300B Circular Saw",
        "tool_type": "Circular Saw",
        "body_width_mm": 285.0,
        "body_depth_mm": 350.0,
        "body_height_mm": 225.0,
        "handle_diameter_mm": 58.0,
        "weight_kg": 2.67,
    },
]


def seed() -> None:
    """Create tables and insert starter tools (idempotent — skips if already seeded)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(Tool).count()
        if existing > 0:
            print(f"DB already has {existing} tools — skipping seed.")
            return
        for data in STARTER_TOOLS:
            db.add(Tool(**data))
        db.commit()
        print(f"Seeded {len(STARTER_TOOLS)} tools successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
