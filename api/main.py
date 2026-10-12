"""
REST API for road-works segments (FastAPI).

Backends:
  - PostGIS, when DATABASE_URL is set (production / docker compose)
  - the pipeline's GeoJSON file otherwise (local dev, tests)

Run: uvicorn api.main:app --reload     → docs at http://localhost:8000/docs
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
GEOJSON = Path(os.getenv("SEGMENTS_GEOJSON", ROOT / "output" / "segments.geojson"))
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="Road Works Segments API", version="1.0.0",
              description="Query road-works segments as GeoJSON. Synthetic sample data.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

FILTERS = ("contractor", "sector", "status", "segment_class", "municipality")


# ---------------------------------------------------------------- backends
class FileBackend:
    def __init__(self, path: Path):
        self.features = json.loads(path.read_text())["features"]

    def query(self, filters: dict, bbox: Optional[list[float]], include_duplicates: bool, limit: int):
        out = []
        for f in self.features:
            p = f["properties"]
            if not include_duplicates and p["duplicate_to_cancel"]:
                continue
            if any(v is not None and p.get(k) != v for k, v in filters.items()):
                continue
            if bbox and not _intersects_bbox(f["geometry"]["coordinates"], bbox):
                continue
            out.append(f)
            if len(out) >= limit:
                break
        return out

    def get(self, code: str):
        return next((f for f in self.features if f["properties"]["project_code"] == code), None)


class PostGISBackend:
    COLS = ("project_code, ref_no, project_type, status, segment_class, contractor, sector, "
            "municipality, district, consultant, permit_no, start_date::text, end_date::text, "
            "duplicate_to_cancel, out_of_priority")

    def __init__(self, url: str):
        import psycopg  # imported lazily so the file backend has no DB dependency
        self.psycopg = psycopg
        self.url = url

    def _rows(self, where: str, params: list, limit: int):
        sql = (f"SELECT {self.COLS}, ST_AsGeoJSON(geom) FROM segments {where} "
               f"ORDER BY start_date LIMIT %s")
        with self.psycopg.connect(self.url) as conn:
            cur = conn.execute(sql, params + [limit])
            names = [d.name for d in cur.description]
            return [_row_to_feature(dict(zip(names, r))) for r in cur.fetchall()]

    def query(self, filters, bbox, include_duplicates, limit):
        clauses, params = [], []
        for k, v in filters.items():          # keys come from the FILTERS whitelist
            if v is not None:
                clauses.append(f"{k} = %s"); params.append(v)
        if not include_duplicates:
            clauses.append("NOT duplicate_to_cancel")
        if bbox:
            clauses.append("geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)"); params += bbox
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return self._rows(where, params, limit)

    def get(self, code):
        rows = self._rows("WHERE project_code = %s", [code], 1)
        return rows[0] if rows else None


def _row_to_feature(r: dict) -> dict:
    geom = json.loads(r.pop("st_asgeojson"))
    return {"type": "Feature", "properties": r, "geometry": geom}


def _intersects_bbox(coords, bbox) -> bool:
    minx, miny, maxx, maxy = bbox
    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
    return not (max(xs) < minx or min(xs) > maxx or max(ys) < miny or min(ys) > maxy)


_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = PostGISBackend(DATABASE_URL) if DATABASE_URL else FileBackend(GEOJSON)
    return _backend


# ---------------------------------------------------------------- routes
@app.get("/health")
def health():
    return {"status": "ok", "backend": "postgis" if DATABASE_URL else "file"}


@app.get("/segments", summary="Query segments as a GeoJSON FeatureCollection")
def segments(
    contractor: Optional[str] = None,
    sector: Optional[str] = None,
    status: Optional[str] = Query(None, description="Active, Coordinated, Initially Closed, Cancelled"),
    segment_class: Optional[str] = Query(None, description="Utilized, Available, Wasted, Cancelled"),
    municipality: Optional[str] = None,
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    include_duplicates: bool = False,
    limit: int = Query(1000, ge=1, le=5000),
):
    box = None
    if bbox:
        try:
            box = [float(v) for v in bbox.split(",")]
            assert len(box) == 4
        except (ValueError, AssertionError):
            raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat")
    filters = dict(zip(FILTERS, (contractor, sector, status, segment_class, municipality)))
    feats = backend().query(filters, box, include_duplicates, limit)
    return {"type": "FeatureCollection", "count": len(feats), "features": feats}


@app.get("/segments/{project_code}", summary="One segment by project code")
def segment(project_code: str):
    f = backend().get(project_code)
    if not f:
        raise HTTPException(404, "Project not found")
    return f


@app.get("/stats", summary="Counts by contractor and status (duplicates excluded)")
def stats():
    feats = backend().query({}, None, False, 100000)
    by = Counter((f["properties"]["contractor"], f["properties"]["status"]) for f in feats)
    out: dict = {}
    for (c, s), n in sorted(by.items()):
        out.setdefault(c, {})[s] = n
    return {"total": len(feats), "by_contractor": out}
