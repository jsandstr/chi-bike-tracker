"""Roll matched street segments up into coverage statistics."""

import geopandas as gpd

from pipeline.coverage.match import FACILITY_RANK, LOW_STRESS

FEET_PER_MILE = 5280


def stats(streets: gpd.GeoDataFrame) -> dict:
    miles = streets["length_ft"] / FEET_PER_MILE
    by_facility = miles.groupby(streets["facility"]).sum()
    total = float(miles.sum())
    any_miles = float(by_facility.sum())
    low_stress = float(by_facility.reindex(sorted(LOW_STRESS)).fillna(0).sum())
    return {
        "street_miles": round(total, 2),
        "any_miles": round(any_miles, 2),
        "low_stress_miles": round(low_stress, 2),
        "any_pct": round(100 * any_miles / total, 2) if total else 0.0,
        "low_stress_pct": round(100 * low_stress / total, 2) if total else 0.0,
        "by_facility": {f: round(float(by_facility.get(f, 0.0)), 2) for f in FACILITY_RANK},
    }


def assign_areas(
    streets: gpd.GeoDataFrame, areas: gpd.GeoDataFrame, id_col: str, out_col: str
) -> gpd.GeoDataFrame:
    """Tag each segment with the area containing its midpoint.

    Streets that form a boundary between two areas are counted in one of them,
    not split, so area totals always sum to the citywide total.
    """
    mid = gpd.GeoDataFrame(
        geometry=streets.geometry.interpolate(0.5, normalized=True), crs=streets.crs
    )
    joined = gpd.sjoin(mid, areas[[id_col, "geometry"]], predicate="within")
    out = streets.copy()
    out[out_col] = joined[~joined.index.duplicated()][id_col].reindex(out.index)
    return out


def by_area(streets: gpd.GeoDataFrame, col: str) -> dict[str, dict]:
    return {str(key): stats(group) for key, group in streets.groupby(col)}
