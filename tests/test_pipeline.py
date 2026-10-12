import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from roadworks import pipeline

ROOT = Path(__file__).resolve().parent.parent


def test_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_sample_data.py"),
                    "--seed", "1", "--out", str(raw)], check=True)

    qa = pipeline.run(date(2026, 10, 1), raw_dir=raw, out=tmp_path / "out")

    gj = json.loads((tmp_path / "out" / "segments.geojson").read_text())
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == qa["projects_out"] > 0
    assert gj["features"][0]["geometry"]["type"] == "LineString"
    assert any((tmp_path / "out" / "contractors").glob("*.xlsx"))
