from fastapi.testclient import TestClient

from api import main
from roadworks import pipeline
from datetime import date

pipeline.run(date(2026, 10, 1))  # make sure output/segments.geojson exists
client = TestClient(main.app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_filter_by_contractor():
    r = client.get("/segments", params={"contractor": "Contractor A", "limit": 50}).json()
    assert r["count"] > 0
    assert all(f["properties"]["contractor"] == "Contractor A" for f in r["features"])
    assert all(not f["properties"]["duplicate_to_cancel"] for f in r["features"])


def test_bbox_and_bad_bbox():
    ok = client.get("/segments", params={"bbox": "46.5,24.5,46.9,24.9"})
    assert ok.status_code == 200 and ok.json()["count"] > 0
    assert client.get("/segments", params={"bbox": "1,2,3"}).status_code == 400


def test_get_one_and_404():
    code = client.get("/segments", params={"limit": 1}).json()["features"][0]["properties"]["project_code"]
    assert client.get(f"/segments/{code}").json()["properties"]["project_code"] == code
    assert client.get("/segments/NOPE").status_code == 404


def test_stats():
    s = client.get("/stats").json()
    assert s["total"] == sum(sum(v.values()) for v in s["by_contractor"].values())
