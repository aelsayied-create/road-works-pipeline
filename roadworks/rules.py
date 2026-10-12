"""
Business rules for road-works coordination, written as small pure functions
so they are easy to test (see tests/test_rules.py).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

SECTOR_DEFAULT_CONTRACTOR = {
    "North": "Contractor A",
    "South": "Contractor B",
    "East": "Contractor C",
    "West": "Contractor D",
    "Central": "Contractor E",
}
MIN_PLAUSIBLE_DAYS = 3


def is_sidewalk(project_code: str) -> bool:
    """Sidewalk projects are flagged by a trailing 'P' in the project code."""
    return str(project_code).strip().upper().endswith("P")


def effective_status(status: str, start: date, today: date) -> str:
    """A coordinated project whose start date has arrived counts as Active."""
    if status == "Coordinated" and start <= today:
        return "Active"
    return status


def classify(status: str, has_permit: bool) -> str:
    """
    Utilized : a permit exists, whatever the status
    Available: active/coordinated, no permit yet
    Wasted   : initially closed without ever getting a permit
    Cancelled: cancelled, no permit
    """
    if has_permit:
        return "Utilized"
    if status in ("Active", "Coordinated"):
        return "Available"
    if status == "Initially Closed":
        return "Wasted"
    return "Cancelled"


def assign_contractor(gis_contractor: str | None, sector: str) -> str:
    """Prefer the contractor recorded in GIS, else fall back to the sector default."""
    if isinstance(gis_contractor, str) and gis_contractor.strip():
        return gis_contractor.strip()
    return SECTOR_DEFAULT_CONTRACTOR.get(sector, "Unassigned")


def flag_duplicates(df: pd.DataFrame, today: date) -> pd.Series:
    """
    Among non-cancelled, non-sidewalk *coordinated* projects that share a ref_no,
    keep the one whose start date is nearest to today; flag the rest.
    If the nearest one has an implausibly short duration, keep the longest instead.
    Returns a boolean Series (True = duplicate to cancel).
    """
    dup = pd.Series(False, index=df.index)
    pool = df[(df["status"] == "Coordinated") & (~df["is_sidewalk"])]
    for _, grp in pool.groupby("ref_no"):
        if len(grp) < 2:
            continue
        dist = (grp["start_date"] - pd.Timestamp(today)).abs()
        keep = dist.idxmin()
        if grp.loc[keep, "duration_days"] < MIN_PLAUSIBLE_DAYS:
            keep = grp["duration_days"].idxmax()
        dup.loc[grp.index.drop(keep)] = True
    return dup
