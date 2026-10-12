"""
Load output/segments.geojson into a PostGIS table.

Usage: DATABASE_URL=postgresql://user:pass@host:5432/db python -m roadworks.load_postgis
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent

DDL = """
CREATE EXTENSION IF NOT EXISTS postgis;
DROP TABLE IF EXISTS segments;
CREATE TABLE segments (
    project_code        text PRIMARY KEY,
    ref_no              text NOT NULL,
    project_type        text,
    status              text,
    segment_class       text,
    contractor          text,
    sector              text,
    municipality        text,
    district            text,
    consultant          text,
    permit_no           text,
    start_date          date,
    end_date            date,
    duplicate_to_cancel boolean,
    out_of_priority     boolean,
    geom                geometry(LineString, 4326) NOT NULL
);
"""
INDEXES = """
CREATE INDEX segments_geom_idx ON segments USING GIST (geom);
CREATE INDEX segments_contractor_idx ON segments (contractor);
CREATE INDEX segments_status_idx ON segments (status);
ANALYZE segments;
"""
COLS = ["project_code", "ref_no", "project_type", "status", "segment_class", "contractor",
        "sector", "municipality", "district", "consultant", "permit_no", "start_date",
        "end_date", "duplicate_to_cancel", "out_of_priority"]


def main(geojson_path: Path = ROOT / "output" / "segments.geojson") -> None:
    fc = json.loads(geojson_path.read_text())
    sql = (f"INSERT INTO segments ({', '.join(COLS)}, geom) VALUES "
           f"({', '.join(['%s'] * len(COLS))}, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))")
    rows = [[f["properties"][c] for c in COLS] + [json.dumps(f["geometry"])] for f in fc["features"]]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(DDL)
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.execute(INDEXES)
    print(f"Loaded {len(rows)} segments into PostGIS")


if __name__ == "__main__":
    main()
