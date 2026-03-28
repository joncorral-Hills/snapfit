"""
seed_tools.py — SnapFit tool database seeder
─────────────────────────────────────────────
1. Adds missing columns (line, model_number, notes) via ALTER TABLE migration
2. Inserts 21 tools, skipping duplicates by model_number
3. Prints inserted / skipped summary
4. Shows first 5 rows + total count
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "snapfit.db")

TOOLS = [
    {"brand":"DeWalt","line":"20V MAX","model_name":"DCD777 Compact Drill/Driver","model_number":"DCD777","tool_type":"drill","body_width_mm":198,"body_height_mm":247,"body_depth_mm":76,"handle_diameter_mm":38,"weight_kg":1.18,"notes":"Width 7.8in, Height 9.71in estimated. Weight 2.6 lbs."},
    {"brand":"DeWalt","line":"20V MAX ATOMIC","model_name":"DCD708 Compact Drill/Driver","model_number":"DCD708","tool_type":"drill","body_width_mm":160,"body_height_mm":201,"body_depth_mm":72,"handle_diameter_mm":36,"weight_kg":1.09,"notes":"6.3in front-to-back, 7.9in height. Weight 2.4 lbs."},
    {"brand":"DeWalt","line":"20V MAX XR","model_name":"DCF887 Impact Driver","model_number":"DCF887","tool_type":"impact_driver","body_width_mm":130,"body_height_mm":185,"body_depth_mm":64,"handle_diameter_mm":36,"weight_kg":1.27,"notes":"5.1in length. Weight approx 2.8 lbs. Estimate."},
    {"brand":"DeWalt","line":"20V MAX ATOMIC","model_name":"DCF809 Compact Impact Driver","model_number":"DCF809","tool_type":"impact_driver","body_width_mm":119,"body_height_mm":178,"body_depth_mm":60,"handle_diameter_mm":35,"weight_kg":0.95,"notes":"Lightweight at 2.1 lbs. Compact ATOMIC series."},
    {"brand":"DeWalt","line":"20V MAX","model_name":"DCS391 Circular Saw","model_number":"DCS391","tool_type":"circular_saw","body_width_mm":330,"body_height_mm":241,"body_depth_mm":203,"handle_diameter_mm":45,"weight_kg":1.99,"notes":"6.5in blade. Approx 13x9.5x8in. Weight 4.4 lbs. Estimate."},
    {"brand":"DeWalt","line":"20V MAX XR","model_name":"DCS367 Reciprocating Saw","model_number":"DCS367","tool_type":"reciprocating_saw","body_width_mm":419,"body_height_mm":203,"body_depth_mm":114,"handle_diameter_mm":44,"weight_kg":1.81,"notes":"Compact recip saw. Approx 16.5x8x4.5in. Weight 4.0 lbs. Estimate."},
    {"brand":"DeWalt","line":"20V MAX","model_name":"DCS331 Jigsaw","model_number":"DCS331","tool_type":"jigsaw","body_width_mm":292,"body_height_mm":229,"body_depth_mm":114,"handle_diameter_mm":42,"weight_kg":1.81,"notes":"Approx 11.5x9x4.5in. Weight 4.0 lbs. Estimate."},
    {"brand":"DeWalt","line":"20V MAX XR","model_name":"DCG412 Angle Grinder","model_number":"DCG412","tool_type":"angle_grinder","body_width_mm":343,"body_height_mm":140,"body_depth_mm":102,"handle_diameter_mm":38,"weight_kg":1.99,"notes":"4.5in disc. Approx 13.5x5.5x4in. Weight 4.4 lbs. Estimate."},
    {"brand":"Milwaukee","line":"M18","model_name":"2801-20 Compact Drill/Driver","model_number":"2801-20","tool_type":"drill","body_width_mm":165,"body_height_mm":197,"body_depth_mm":58,"handle_diameter_mm":38,"weight_kg":1.13,"notes":"Length 6.5in, Height 7.75in, Width 2.3in. Weight 2.5 lbs. Official specs."},
    {"brand":"Milwaukee","line":"M18","model_name":"2850-20 Compact Impact Driver","model_number":"2850-20","tool_type":"impact_driver","body_width_mm":130,"body_height_mm":178,"body_depth_mm":57,"handle_diameter_mm":36,"weight_kg":1.0,"notes":"Length 5.1in, Width 2.25in. Weight approx 2.2 lbs. Official specs."},
    {"brand":"Milwaukee","line":"M18 FUEL","model_name":"2730-20 Circular Saw","model_number":"2730-20","tool_type":"circular_saw","body_width_mm":330,"body_height_mm":241,"body_depth_mm":191,"handle_diameter_mm":45,"weight_kg":2.04,"notes":"6.5in blade. Approx 13x9.5x7.5in. Weight 4.5 lbs. Estimate."},
    {"brand":"Milwaukee","line":"M18 FUEL","model_name":"2720-20 Reciprocating Saw","model_number":"2720-20","tool_type":"reciprocating_saw","body_width_mm":406,"body_height_mm":216,"body_depth_mm":114,"handle_diameter_mm":44,"weight_kg":1.99,"notes":"Approx 16x8.5x4.5in. Weight 4.4 lbs. Estimate."},
    {"brand":"Milwaukee","line":"M18","model_name":"2680-20 Angle Grinder","model_number":"2680-20","tool_type":"angle_grinder","body_width_mm":318,"body_height_mm":140,"body_depth_mm":102,"handle_diameter_mm":38,"weight_kg":1.81,"notes":"4.5in disc. Approx 12.5x5.5x4in. Weight 4.0 lbs. Estimate."},
    {"brand":"Milwaukee","line":"M18 FUEL","model_name":"2737-20 D-Handle Jigsaw","model_number":"2737-20","tool_type":"jigsaw","body_width_mm":292,"body_height_mm":241,"body_depth_mm":114,"handle_diameter_mm":42,"weight_kg":1.99,"notes":"D-handle jigsaw. Approx 11.5x9.5x4.5in. Weight 4.4 lbs. Estimate."},
    {"brand":"Milwaukee","line":"M18","model_name":"2803-20 Compact Drill/Driver","model_number":"2803-20","tool_type":"drill","body_width_mm":152,"body_height_mm":190,"body_depth_mm":57,"handle_diameter_mm":37,"weight_kg":1.04,"notes":"Compact version. Approx 6x7.5x2.25in. Weight 2.3 lbs. Estimate."},
    {"brand":"Milwaukee","line":"M18 FUEL","model_name":"2853-20 Impact Driver","model_number":"2853-20","tool_type":"impact_driver","body_width_mm":130,"body_height_mm":185,"body_depth_mm":57,"handle_diameter_mm":36,"weight_kg":1.04,"notes":"FUEL impact. Approx 5.1x7.3x2.25in. Weight 2.3 lbs. Estimate."},
    {"brand":"Ryobi","line":"ONE+ HP 18V","model_name":"PSBDD01 Compact Drill/Driver","model_number":"PSBDD01","tool_type":"drill","body_width_mm":152,"body_height_mm":190,"body_depth_mm":64,"handle_diameter_mm":36,"weight_kg":0.91,"notes":"Compact brushless. Approx 6x7.5x2.5in. Weight approx 2.0 lbs. Estimate."},
    {"brand":"Ryobi","line":"ONE+ HP 18V","model_name":"PSBID01 Compact Impact Driver","model_number":"PSBID01","tool_type":"impact_driver","body_width_mm":119,"body_height_mm":178,"body_depth_mm":57,"handle_diameter_mm":35,"weight_kg":0.86,"notes":"Compact brushless impact. Approx 4.7x7x2.25in. Weight approx 1.9 lbs. Estimate."},
    {"brand":"Ryobi","line":"ONE+ HP 18V","model_name":"PSBCS02 Compact Circular Saw","model_number":"PSBCS02","tool_type":"circular_saw","body_width_mm":292,"body_height_mm":216,"body_depth_mm":165,"handle_diameter_mm":42,"weight_kg":1.59,"notes":"6.5in blade compact saw. Approx 11.5x8.5x6.5in. Weight 3.5 lbs. Estimate."},
    {"brand":"Ryobi","line":"ONE+ HP 18V","model_name":"PSBRS01 Reciprocating Saw","model_number":"PSBRS01","tool_type":"reciprocating_saw","body_width_mm":368,"body_height_mm":191,"body_depth_mm":102,"handle_diameter_mm":42,"weight_kg":1.59,"notes":"Approx 14.5x7.5x4in. Weight 3.5 lbs. Estimate."},
    {"brand":"Ryobi","line":"ONE+ HP 18V","model_name":"PCL525 Jigsaw","model_number":"PCL525","tool_type":"jigsaw","body_width_mm":254,"body_height_mm":216,"body_depth_mm":102,"handle_diameter_mm":40,"weight_kg":1.36,"notes":"Approx 10x8.5x4in. Weight 3.0 lbs. Estimate."},
]


def get_existing_columns(cur):
    cur.execute("PRAGMA table_info(tools)")
    return {row[1] for row in cur.fetchall()}


def run_migration(cur, existing_cols):
    migrations = [
        ("line",         "VARCHAR(64)  DEFAULT ''"),
        ("model_number", "VARCHAR(32)  DEFAULT ''"),
        ("notes",        "TEXT         DEFAULT ''"),
    ]
    added = []
    for col, typedef in migrations:
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE tools ADD COLUMN {col} {typedef}")
            added.append(col)
    return added


def seed(con, cur):
    # Build set of existing model_numbers for duplicate check
    cur.execute("SELECT model_number FROM tools WHERE model_number IS NOT NULL AND model_number != ''")
    existing = {row[0] for row in cur.fetchall()}

    inserted = skipped = 0
    for t in TOOLS:
        mn = t["model_number"]
        if mn in existing:
            print(f"  SKIP  {mn} — already in DB")
            skipped += 1
            continue
        cur.execute(
            """INSERT INTO tools
               (brand, line, model_name, model_number, tool_type,
                body_width_mm, body_height_mm, body_depth_mm,
                handle_diameter_mm, weight_kg, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t["brand"], t.get("line", ""), t["model_name"], mn, t["tool_type"],
                t["body_width_mm"], t["body_height_mm"], t["body_depth_mm"],
                t["handle_diameter_mm"], t["weight_kg"], t.get("notes", ""),
            ),
        )
        existing.add(mn)
        print(f"  INSERT {mn} — {t['brand']} {t['model_name']}")
        inserted += 1

    con.commit()
    return inserted, skipped


def verify(cur):
    cur.execute("SELECT COUNT(*) FROM tools")
    total = cur.fetchone()[0]
    cur.execute(
        "SELECT id, brand, model_number, model_name, tool_type FROM tools ORDER BY id LIMIT 5"
    )
    rows = cur.fetchall()
    return total, rows


def main():
    print(f"\n{'─'*60}")
    print(f"  SnapFit DB Seeder")
    print(f"  DB: {DB_PATH}")
    print(f"{'─'*60}\n")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 1. Migration
    existing_cols = get_existing_columns(cur)
    added = run_migration(cur, existing_cols)
    con.commit()
    if added:
        print(f"✅ Migration: added columns → {', '.join(added)}\n")
    else:
        print("✅ Migration: schema already up to date\n")

    # 2. Seed
    print("Seeding tools:")
    inserted, skipped = seed(con, cur)

    # 3. Summary
    print(f"\n{'─'*60}")
    print(f"  Inserted : {inserted}")
    print(f"  Skipped  : {skipped}")
    print(f"  Total    : {inserted + skipped}")

    # 4. Verify
    total, rows = verify(cur)
    print(f"\n{'─'*60}")
    print(f"  Total rows in DB: {total}")
    print(f"\n  First 5 rows:")
    print(f"  {'ID':<4} {'Brand':<12} {'Model #':<12} {'Name':<36} Type")
    print(f"  {'─'*80}")
    for r in rows:
        print(f"  {r[0]:<4} {r[1]:<12} {r[2]:<12} {r[3]:<36} {r[4]}")
    print(f"{'─'*60}\n")

    con.close()


if __name__ == "__main__":
    main()
