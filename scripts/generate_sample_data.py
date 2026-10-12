"""
Generate SYNTHETIC input data that mimics two real-world exports:

  data/raw/gis_sections.csv     road sections from a GIS (geometry as WKT)
  data/raw/platform_export.csv  road-works projects from a permits/tracking platform

No real data is used. Sectors, districts and contractors are fictional.
Usage: python scripts/generate_sample_data.py [--seed 7]
"""
import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

CENTER = (46.68, 24.71)  # lon, lat — map extent only; data is synthetic
SECTORS = {
    #  name      (dx, dy) offset of sector centre in degrees
    "North":   (0.00, 0.09),
    "South":   (0.00, -0.09),
    "East":    (0.10, 0.00),
    "West":    (-0.10, 0.00),
    "Central": (0.00, 0.00),
}
CONTRACTORS = ["Contractor A", "Contractor B", "Contractor C", "Contractor D", "Contractor E"]
SECTOR_DEFAULT = dict(zip(SECTORS, CONTRACTORS))
CONSULTANTS = ["Consultant X", "Consultant Y", "Consultant Z"]


def line_wkt(rnd: random.Random, cx: float, cy: float) -> str:
    """A short, slightly bent road segment near (cx, cy)."""
    x, y = cx + rnd.uniform(-0.04, 0.04), cy + rnd.uniform(-0.035, 0.035)
    pts = [(x, y)]
    horizontal = rnd.random() < 0.5
    for _ in range(rnd.randint(2, 4)):
        step = rnd.uniform(0.002, 0.006)
        if horizontal:
            x += step; y += rnd.uniform(-0.0006, 0.0006)
        else:
            y += step; x += rnd.uniform(-0.0006, 0.0006)
        pts.append((x, y))
    return "LINESTRING(" + ", ".join(f"{a:.6f} {b:.6f}" for a, b in pts) + ")"


def main(seed: int, out: Path = RAW) -> None:
    rnd = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    today = date(2026, 10, 1)

    sections = []
    n = 1
    for sector, (dx, dy) in SECTORS.items():
        cx, cy = CENTER[0] + dx, CENTER[1] + dy
        munis = [f"{sector} Municipality {i}" for i in (1, 2)]
        for _ in range(70):
            muni = rnd.choice(munis)
            sections.append({
                "section_no": f"S{n:05d}",
                "ref_type": rnd.choices(["SECTION", "INTERSECTION"], [0.85, 0.15])[0],
                "sector": sector,
                "municipality": muni,
                "district": f"{muni.split()[0]}-D{rnd.randint(1, 6):02d}",
                "gis_contractor": SECTOR_DEFAULT[sector] if rnd.random() < 0.7 else "",
                "priority_year": rnd.choice(["2026", "2026", "2027", ""]),
                "wkt": line_wkt(rnd, cx, cy),
            })
            n += 1

    projects = []
    p = 1
    for s in sections:
        k = rnd.choices([0, 1, 2], [0.25, 0.6, 0.15])[0]  # some sections get duplicates
        for _ in range(k):
            start = today + timedelta(days=rnd.randint(-60, 75))
            dur = rnd.choice([2, 14, 21, 30, 45, 60])
            status = rnd.choices(["Active", "Coordinated", "Initially Closed", "Cancelled"],
                                 [0.35, 0.4, 0.15, 0.10])[0]
            sidewalk = rnd.random() < 0.08
            projects.append({
                "project_code": f"PRJ-26-{p:05d}{'P' if sidewalk else ''}",
                "ref_no": s["section_no"],
                "project_type": "Sidewalk" if sidewalk else "Asphalt",
                "status": status,
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=dur)).isoformat(),
                "permit_no": f"PRM-{rnd.randint(10000, 99999)}" if rnd.random() < 0.45 else "",
                "consultant": rnd.choice(CONSULTANTS),
            })
            p += 1
        if k == 2 and rnd.random() < 0.5:
            # re-coordinated section: two future coordinated projects on one ref
            for pr in projects[-2:]:
                pr["status"] = "Coordinated"
                pr["project_code"] = pr["project_code"].rstrip("P")
                pr["project_type"] = "Asphalt"
                d = today + timedelta(days=rnd.randint(3, 75))
                pr["start_date"] = d.isoformat()
                pr["end_date"] = (d + timedelta(days=rnd.choice([2, 21, 30]))).isoformat()

    # A few realistic data-quality problems for the pipeline to catch
    projects[5]["end_date"] = "2026-01-01"            # end before start
    projects[9]["ref_no"] = "S99999"                  # section not in GIS

    for name, rows in [("gis_sections.csv", sections), ("platform_export.csv", projects)]:
        with (out / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
    print(f"Generated {len(sections)} sections and {len(projects)} projects in {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=RAW)
    a = ap.parse_args()
    main(a.seed, a.out)
