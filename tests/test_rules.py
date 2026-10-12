from datetime import date

import pandas as pd

from roadworks import rules

TODAY = date(2026, 10, 1)


def test_sidewalk_flag():
    assert rules.is_sidewalk("PRJ-26-00012P")
    assert not rules.is_sidewalk("PRJ-26-00012")


def test_coordinated_becomes_active_on_start():
    assert rules.effective_status("Coordinated", date(2026, 9, 30), TODAY) == "Active"
    assert rules.effective_status("Coordinated", date(2026, 10, 5), TODAY) == "Coordinated"


def test_classify():
    assert rules.classify("Initially Closed", True) == "Utilized"
    assert rules.classify("Active", False) == "Available"
    assert rules.classify("Initially Closed", False) == "Wasted"
    assert rules.classify("Cancelled", False) == "Cancelled"


def test_contractor_fallback():
    assert rules.assign_contractor("Contractor Z", "North") == "Contractor Z"
    assert rules.assign_contractor("", "South") == "Contractor B"
    assert rules.assign_contractor(None, "Nowhere") == "Unassigned"


def _frame(rows):
    df = pd.DataFrame(rows, columns=["ref_no", "status", "start_date", "duration_days", "is_sidewalk"])
    df["start_date"] = pd.to_datetime(df["start_date"])
    return df


def test_duplicates_keep_nearest_start():
    df = _frame([
        ["S1", "Coordinated", "2026-10-05", 30, False],
        ["S1", "Coordinated", "2026-11-20", 30, False],
    ])
    assert rules.flag_duplicates(df, TODAY).tolist() == [False, True]


def test_duplicates_skip_implausibly_short():
    df = _frame([
        ["S1", "Coordinated", "2026-10-05", 2, False],
        ["S1", "Coordinated", "2026-11-20", 45, False],
    ])
    assert rules.flag_duplicates(df, TODAY).tolist() == [True, False]


def test_sidewalks_never_duplicates():
    df = _frame([
        ["S1", "Coordinated", "2026-10-05", 30, True],
        ["S1", "Coordinated", "2026-11-20", 30, True],
    ])
    assert not rules.flag_duplicates(df, TODAY).any()
