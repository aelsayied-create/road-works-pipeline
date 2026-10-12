# Road Works Data Pipeline & REST API

A Python pipeline that merges a **road-works tracking export** with **GIS road sections**, applies coordination rules, checks data quality, and publishes the result as **GeoJSON, per-contractor Excel workbooks, a PostGIS table and a REST API**, all packaged with Docker and tested in CI.

> ⚠️ **Synthetic data.** `scripts/generate_sample_data.py` creates fictional sections, projects and contractors. The workflow mirrors real municipal road-works coordination, without exposing any client data.

> 💼 **About my production work.** This repo is a public sample. My real production dashboards for Riyadh Municipality run on Netlify behind password protection, because they belong to my employer. I can demonstrate them live during an interview.

The companion front end is `road-works-dashboard`.

## What it does
```
data/raw/platform_export.csv ─┐
                              ├─► validate ─► apply rules ─► join on ref_no ─► outputs
data/raw/gis_sections.csv ────┘                                               │
                                                                              ├─ output/segments.geojson
                                                                              ├─ output/contractors/*.xlsx
                                                                              ├─ output/summary.json, report.md
                                                                              └─ PostGIS ─► FastAPI REST API
```

**Rules** (`roadworks/rules.py`, unit-tested):
- A *coordinated* project whose start date has arrived counts as **Active**
- Classification: permit → **Utilized**; active/coordinated without permit → **Available**; initially closed without permit → **Wasted**
- **Duplicates**: coordinated projects on the same section → keep the nearest start date (or the longest if the nearest is implausibly short), flag the rest for cancellation
- **Contractor**: use the GIS value when present, else the sector's default
- Sidewalk projects (code ending in `P`) are excluded from duplicate checks

**Data-quality checks**: invalid date ranges, references missing from GIS, duplicates. Each run writes a report.

## Quick start
```bash
pip install -r requirements.txt
python scripts/generate_sample_data.py      # synthetic inputs
python -m roadworks.pipeline                # → output/
uvicorn api.main:app --reload               # → http://localhost:8000/docs
python -m pytest                            # 13 tests
```

## Full stack with Docker (PostGIS + API)
```bash
docker compose up --build
# API:  http://localhost:8000/docs
# DB :  postgresql://roadworks:roadworks@localhost:5432/roadworks
```

## REST API
| Endpoint | Description |
|---|---|
| `GET /health` | Status and active backend (`postgis` or `file`) |
| `GET /segments` | GeoJSON; filters `contractor`, `sector`, `status`, `segment_class`, `municipality`, `bbox=minLon,minLat,maxLon,maxLat`, `include_duplicates`, `limit` |
| `GET /segments/{project_code}` | One segment |
| `GET /stats` | Counts by contractor and status |

Example: `/segments?contractor=Contractor%20A&bbox=46.6,24.6,46.8,24.8`

The API uses **PostGIS** when `DATABASE_URL` is set (spatial index, `ST_MakeEnvelope` bbox queries, `ST_AsGeoJSON`) and falls back to the pipeline's GeoJSON file otherwise.

## CI (GitHub Actions)
1. Unit and API tests
2. Integration test against a real **PostGIS** service container
3. Docker image build and smoke test

## Project layout
```
roadworks/rules.py         business rules (pure functions)
roadworks/pipeline.py      load → validate → transform → outputs
roadworks/load_postgis.py  load GeoJSON into PostGIS with spatial index
api/main.py                FastAPI app, PostGIS or file backend
scripts/                   synthetic data generator
tests/                     pytest suite
Dockerfile, docker-compose.yml, .github/workflows/ci.yml
```

## Tech
Python 3.12 · pandas · Shapely · FastAPI · PostgreSQL/PostGIS · psycopg 3 · Docker · GitHub Actions

## Author
**Amna Abdein** — GIS Engineer & Geospatial Web Developer
