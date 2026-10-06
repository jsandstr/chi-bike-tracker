"""Hand-maintained policy records and how much coverage grew while each was in force."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from pipeline.coverage.match import LOW_STRESS

# ISO months sort correctly as strings.
Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]

PROTECTED = "Protected Bike Lane"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reported(_Strict):
    value: float
    as_of: Month
    source: str | None = None


class Target(_Strict):
    label: str
    metric: Literal[
        "any_miles_added",
        "low_stress_miles_added",
        "protected_miles_added",
        "any_miles_total",
        "low_stress_miles_total",
        "protected_miles_total",
        "none",
    ]
    value: float | None = None
    reported: Reported | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _value_matches_metric(self):
        if (self.metric == "none") != (self.value is None):
            raise ValueError("value must be set exactly when metric is not 'none'")
        return self


class Source(_Strict):
    title: str
    url: str


class Policy(_Strict):
    id: str
    name: str
    kind: Literal["plan", "program", "ordinance", "pledge"]
    jurisdiction: str
    status: Literal["active", "completed", "expired", "failed"]
    start: Month
    end: Month | None = None
    summary: str
    measure: bool
    targets: list[Target] = []
    sources: list[Source] = []

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end is not None and self.end < self.start:
            raise ValueError("end is before start")
        return self


def load_policies(directory: Path) -> list[Policy]:
    policies = []
    for path in sorted(directory.glob("*.yaml")):
        policy = Policy.model_validate(yaml.safe_load(path.read_text()))
        if policy.id != path.stem:
            raise ValueError(f"{path.name}: id {policy.id!r} does not match the filename")
        policies.append(policy)
    return policies


def window(dates: list[str], start: str, end: str | None) -> tuple[int, int, bool]:
    """Indexes of the snapshots bracketing a policy, and whether the start was cut off.

    Runs from the latest snapshot at or before `start` to the earliest at or
    after `end`; an open or too-late `end` runs to the last snapshot.
    """
    before = [i for i, d in enumerate(dates) if d <= start]
    first = before[-1] if before else 0
    last = len(dates) - 1
    if end is not None:
        after = [i for i, d in enumerate(dates) if d >= end]
        last = after[0] if after else last
    return first, last, not before


def _miles(snapshot: dict, metric: str) -> float:
    kind = metric.rsplit("_miles", 1)[0]
    if kind == "protected":
        return snapshot["by_facility"][PROTECTED]
    if kind == "low_stress":
        return sum(snapshot["by_facility"][f] for f in LOW_STRESS)
    return sum(snapshot["by_facility"].values())


def contribution(first: dict, last: dict, truncated: bool) -> dict:
    return {
        "from": first["date"],
        "to": last["date"],
        "truncated": truncated,
        "any_miles": round(last["any_miles"] - first["any_miles"], 2),
        "low_stress_miles": round(last["low_stress_miles"] - first["low_stress_miles"], 2),
        "any_pct_points": round(last["any_pct"] - first["any_pct"], 2),
        "by_facility": {
            f: round(last["by_facility"][f] - first["by_facility"][f], 2)
            for f in last["by_facility"]
        },
    }


def measure_target(target: Target, first: dict, last: dict) -> tuple[float | None, float | None]:
    """Miles the snapshots show for a target, and progress toward it clamped to 0..1."""
    if target.metric == "none":
        return None, None
    if target.metric.endswith("_added"):
        measured = _miles(last, target.metric) - _miles(first, target.metric)
    else:
        measured = _miles(last, target.metric)
    return round(measured, 2), round(min(max(measured / target.value, 0.0), 1.0), 3)


def build_record(policy: Policy, snapshots: list[dict]) -> dict:
    record = policy.model_dump(mode="json")
    for target in record["targets"]:
        target["measured"] = target["progress"] = None
    record["contribution"] = None
    if not policy.measure:
        return record
    first, last, truncated = window([s["date"] for s in snapshots], policy.start, policy.end)
    record["contribution"] = contribution(snapshots[first], snapshots[last], truncated)
    for target, raw in zip(policy.targets, record["targets"]):
        raw["measured"], raw["progress"] = measure_target(target, snapshots[first], snapshots[last])
    return record


def build_all(policies: list[Policy], snapshots: list[dict]) -> list[dict]:
    ordered = sorted(policies, key=lambda p: p.start, reverse=True)
    ordered.sort(key=lambda p: p.status != "active")  # stable: active first
    return [build_record(p, snapshots) for p in ordered]
