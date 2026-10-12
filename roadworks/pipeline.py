"""
Pipeline: platform export + GIS sections -> validated, classified segments.

Outputs (in output/):
  segments.geojson            one feature per project, with section geometry
  summary.json                counts by contractor / sector / class
  contractors/<name>.xlsx     per-contractor workbook (active + next 30 days)
  report.md                   run report with data-quality checks

Usage: python -m roadworks.pipeline [--today 2026-10-01]
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from shapely import wkt
from shapely.geometry import mapping

from . import rules

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "output"


def load(raw_dir: Path = RAW) -> tuple[pd.DataFrame, pd.DataFrame]:
    gis = pd.read_csv(raw_dir / "gis_sections.csv", dtype=str, keep_default_na=False)
    prj = pd.read_csv(raw_dir / "platform_export.csv", dtype=str, keep_default_na=False,
                      parse_dates=["start_date", "end_date"])
    return gis, prj


def transform(gis: pd.DataFrame, prj: pd.DataFrame, today: date) -> tuple[pd.DataFrame, dict]:
    qa: dict[str, int] = {"projects_in": len(prj), "sections_in": len(gis)}

    # Data-quality checks
    bad_dates = prj["end_date"] < prj["start_date"]
    qa["invalid_date_ranges"] = int(bad_dates.sum())
    prj = prj[~bad_dates].copy()

    prj["is_sidewalk"] = prj["project_code"].map(rules.is_sidewalk)
    prj["duration_days"] = (prj["end_date"] - prj["start_date"]).dt.days
    prj["status"] = [rules.effective_status(s, d.date(), today)
                     for s, d in zip(prj["status"], prj["start_date"])]
    prj["has_permit"] = prj["permit_no"].str.strip() != ""
    prj["segment_class"] = [rules.classify(s, p) for s, p in zip(prj["status"], prj["has_permit"])]
    prj["duplicate_to_cancel"] = rules.flag_duplicates(prj, today)
    qa["duplicates_flagged"] = int(prj["duplicate_to_cancel"].sum())

    # Join to GIS (sidewalks are not tied to a GIS section)
    df = prj.merge(gis, how="left", left_on="ref_no", right_on="section_no", indicator=True)
    unmatched = (df["_merge"] == "left_only") & (~df["is_sidewalk"])
    qa["unmatched_ref_no"] = int(unmatched.sum())
    df = df[df["_merge"] == "both"].drop(columns="_merge")

    df["contractor"] = [rules.assign_contractor(c, s) for c, s in zip(df["gis_contractor"], df["sector"])]
    df["out_of_priority"] = df["priority_year"].isin(["", "Out_of_Priorities"])
    qa["projects_out"] = len(df)
    return df, qa


def to_geojson(df: pd.DataFrame) -> dict:
    cols = ["project_code", "ref_no", "project_type", "status", "segment_class", "contractor",
            "sector", "municipality", "district", "consultant", "permit_no",
            "duplicate_to_cancel", "out_of_priority"]
    feats = []
    for r in df.itertuples(index=False):
        props = {c: getattr(r, c) for c in cols}
        props["start_date"] = r.start_date.date().isoformat()
        props["end_date"] = r.end_date.date().isoformat()
        props["duplicate_to_cancel"] = bool(props["duplicate_to_cancel"])
        props["out_of_priority"] = bool(props["out_of_priority"])
        feats.append({"type": "Feature", "properties": props, "geometry": mapping(wkt.loads(r.wkt))})
    return {"type": "FeatureCollection", "features": feats}


def summarize(df: pd.DataFrame) -> dict:
    live = df[~df["duplicate_to_cancel"]]
    return {
        "by_class": live["segment_class"].value_counts().to_dict(),
        "by_status": live["status"].value_counts().to_dict(),
        "by_contractor": live.groupby(["contractor", "status"]).size().unstack(fill_value=0).to_dict("index"),
        "by_sector": live["sector"].value_counts().to_dict(),
    }


def write_contractor_workbooks(df: pd.DataFrame, today: date, out: Path) -> int:
    horizon = pd.Timestamp(today + timedelta(days=30))
    sel = df[(~df["duplicate_to_cancel"]) & (df["status"].isin(["Active", "Coordinated"]))
             & (df["start_date"] <= horizon)]
    cols = ["project_code", "ref_no", "project_type", "status", "start_date", "end_date",
            "sector", "municipality", "district", "permit_no", "consultant"]
    out.mkdir(parents=True, exist_ok=True)
    for name, grp in sel.groupby("contractor"):
        path = out / f"{name.replace(' ', '_')}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            grp.sort_values("start_date")[cols].to_excel(xw, sheet_name="Projects", index=False)
            grp["status"].value_counts().rename_axis("status").reset_index(name="count") \
               .to_excel(xw, sheet_name="Summary", index=False)
    return sel["contractor"].nunique()


def run(today: date, raw_dir: Path = RAW, out: Path = OUT) -> dict:
    gis, prj = load(raw_dir)
    df, qa = transform(gis, prj, today)
    out.mkdir(parents=True, exist_ok=True)
    (out / "segments.geojson").write_text(json.dumps(to_geojson(df)))
    summary = summarize(df)
    (out / "summary.json").write_text(json.dumps({"as_of": today.isoformat(), **summary}, indent=2))
    n_books = write_contractor_workbooks(df, today, out / "contractors")

    lines = [f"# Pipeline run — {today.isoformat()}", "", "## Data quality", ""]
    lines += [f"- {k.replace('_', ' ')}: **{v}**" for k, v in qa.items()]
    lines += ["", "## Classification", ""] + [f"- {k}: {v}" for k, v in summary["by_class"].items()]
    lines += ["", f"Contractor workbooks written: {n_books}"]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return qa


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", type=date.fromisoformat, default=date(2026, 10, 1))
    run(ap.parse_args().today)
