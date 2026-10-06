from pathlib import Path

import geopandas as gpd
import pytest
import yaml
from pydantic import ValidationError
from shapely.geometry import LineString

from pipeline.history import build, policies, snapshots
from pipeline.sources.socrata import CRS_FEET

FIXTURES = Path(__file__).parent / "fixtures"

DATES = ["2014-12", "2016-03", "2020-02", "2025-12"]


def _snapshot(date, any_miles, protected, greenway=0.0):
    by_facility = {
        "Protected Bike Lane": protected,
        "Neighborhood Greenway": greenway,
        "Buffered Bike Lane": 0.0,
        "Bike Lane": any_miles - protected - greenway,
        "Marked Shared Lane": 0.0,
    }
    return {
        "date": date,
        "any_miles": any_miles,
        "low_stress_miles": protected + greenway,
        "any_pct": any_miles / 10,
        "low_stress_pct": (protected + greenway) / 10,
        "by_facility": by_facility,
    }


SNAPS = [
    _snapshot("2014-12", 100.0, 5.0),
    _snapshot("2016-03", 150.0, 20.0),
    _snapshot("2020-02", 200.0, 30.0, greenway=2.0),
    _snapshot("2025-12", 400.0, 70.0, greenway=80.0),
]


def _policy(**overrides):
    raw = yaml.safe_load((FIXTURES / "example-plan.yaml").read_text())
    return policies.Policy.model_validate({**raw, **overrides})


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("EXISTING CYCLE TRACK", "Protected Bike Lane"),
        ("PROTECTED BIKE LANE", "Protected Bike Lane"),
        ("EXISTING BUFFERED BIKE LANE", "Buffered Bike Lane"),
        ("BIKE LANE", "Bike Lane"),
        ("EXISTING SHARED-LANE", "Marked Shared Lane"),
        ("EXISTING NEIGHBORHOOD GREENWAY", "Neighborhood Greenway"),
        ("Marked Shared Lane", "Marked Shared Lane"),
        ("RECOMMENDED BIKE ROUTE", None),
        ("EXISTING OFF-STREET TRAIL", None),
        ("ACCESS PATH", None),
        ("GREEN WAVE", None),
    ],
)
def test_normalise_label(raw, expected):
    assert snapshots.normalise_label(raw) == expected


def test_unknown_label_raises():
    with pytest.raises(ValueError, match="unknown bike route label"):
        snapshots.normalise_label("EXISTING SKY BRIDGE")


def test_normalise_drops_non_facilities_and_fills_matcher_columns():
    routes = gpd.GeoDataFrame(
        {
            "street": ["AVENUE  L", "MAIN ST", "MAIN ST"],
            "bikeroute": ["BIKE LANE", "ACCESS PATH", "CYCLE TRACK"],
            "status": ["EXISTING", "EXISTING", "PROPOSED"],
        },
        geometry=[LineString([(0, 0), (1, 0)])] * 3,
        crs=CRS_FEET,
    )
    out = snapshots.normalise(routes, "bikeroute")
    assert out["street"].tolist() == ["AVENUE L"]
    assert out["displayrou"].tolist() == ["Bike Lane"]
    assert out["st_name"].isna().all()


def test_years_between_and_growth_rate():
    assert build.years_between("2014-12", "2016-03") == pytest.approx(1 + 3 / 12)
    entries = [{**s, "miles_per_year": None} for s in SNAPS[:2]]
    build.add_growth_rates(entries)
    assert entries[0]["miles_per_year"] is None
    assert entries[1]["miles_per_year"]["any"] == 40.0


def test_window_between_snapshots():
    assert policies.window(DATES, "2017-01", "2021-06") == (1, 3, False)


def test_window_open_ended_runs_to_last_snapshot():
    assert policies.window(DATES, "2016-03", None) == (1, 3, False)


def test_window_start_before_first_snapshot_is_truncated():
    assert policies.window(DATES, "2011-05", "2016-03") == (0, 1, True)


def test_window_end_after_last_snapshot_uses_last():
    assert policies.window(DATES, "2020-02", "2026-12") == (2, 3, False)


def test_contribution_and_target_progress():
    record = policies.build_record(_policy(start="2020-02", end="2025-12"), SNAPS)
    assert record["contribution"]["any_miles"] == 200.0
    assert record["contribution"]["low_stress_miles"] == 118.0
    assert record["contribution"]["by_facility"]["Neighborhood Greenway"] == 78.0
    added, unmeasured = record["targets"]
    assert added["measured"] == 200.0
    assert added["progress"] == 1.0  # 200 of 50, clamped
    assert unmeasured["measured"] is None and unmeasured["progress"] is None


def test_total_metrics_use_the_end_snapshot():
    target = policies.Target(label="x", metric="protected_miles_total", value=140)
    assert policies.measure_target(target, SNAPS[0], SNAPS[3]) == (70.0, 0.5)
    low_stress = policies.Target(label="x", metric="low_stress_miles_total", value=300)
    assert policies.measure_target(low_stress, SNAPS[0], SNAPS[3]) == (150.0, 0.5)


def test_unmeasured_policy_has_no_contribution():
    record = policies.build_record(_policy(measure=False), SNAPS)
    assert record["contribution"] is None


def test_active_policies_sort_first_then_newest():
    old_active = _policy(id="a", start="2010-01")
    new_done = _policy(id="b", status="completed", start="2024-01", end="2025-01")
    older_done = _policy(id="c", status="completed", start="2015-01", end="2016-01")
    out = policies.build_all([older_done, new_done, old_active], SNAPS)
    assert [r["id"] for r in out] == ["a", "b", "c"]


def test_fixture_loads_and_id_must_match_filename(tmp_path):
    assert [p.id for p in policies.load_policies(FIXTURES)] == ["example-plan"]
    (tmp_path / "wrong-name.yaml").write_text((FIXTURES / "example-plan.yaml").read_text())
    with pytest.raises(ValueError, match="does not match the filename"):
        policies.load_policies(tmp_path)


def test_unknown_field_is_rejected():
    raw = yaml.safe_load((FIXTURES / "example-plan.yaml").read_text())
    with pytest.raises(ValidationError):
        policies.Policy.model_validate({**raw, "budget": 5})
    raw["targets"][0]["unit"] = "miles"
    with pytest.raises(ValidationError):
        policies.Policy.model_validate(raw)


def test_target_value_must_match_metric():
    with pytest.raises(ValidationError):
        policies.Target(label="x", metric="none", value=5)
    with pytest.raises(ValidationError):
        policies.Target(label="x", metric="any_miles_added")
