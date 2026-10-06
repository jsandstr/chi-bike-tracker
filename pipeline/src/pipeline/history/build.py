"""Match each archived snapshot to the street network and summarise the growth."""

from itertools import pairwise

import geopandas as gpd

from pipeline.coverage import aggregate


def years_between(start: str, end: str) -> float:
    """Years from one YYYY-MM date to another."""
    (y1, m1), (y2, m2) = ((int(p) for p in d.split("-")) for d in (start, end))
    return (y2 - y1) + (m2 - m1) / 12


def snapshot_entry(key: str, date: str, source: str, streets: gpd.GeoDataFrame) -> dict:
    stats = aggregate.stats(streets)
    return {
        "key": key,
        "date": date,
        "source": source,
        **{k: stats[k] for k in ("any_miles", "low_stress_miles", "any_pct", "low_stress_pct")},
        "by_facility": stats["by_facility"],
        "miles_per_year": None,
    }


def add_growth_rates(entries: list[dict]) -> None:
    for prev, cur in pairwise(entries):
        years = years_between(prev["date"], cur["date"])
        cur["miles_per_year"] = {
            kind: round((cur[f"{kind}_miles"] - prev[f"{kind}_miles"]) / years, 2)
            for kind in ("any", "low_stress")
        }


def segments_with_facilities(
    streets: gpd.GeoDataFrame, matched: list[gpd.GeoDataFrame]
) -> gpd.GeoDataFrame:
    """Streets that had a facility in any snapshot, with columns s0..sN holding it."""
    out = streets[["street_nam", "street_typ", "geometry"]].copy()
    for i, snap in enumerate(matched):
        out[f"s{i}"] = snap["facility"]
    cols = [f"s{i}" for i in range(len(matched))]
    return out[out[cols].notna().any(axis=1)]
