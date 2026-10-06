"""Assign a bike facility type to each street centerline segment."""

import geopandas as gpd
import pandas as pd

# Highest-comfort facility wins when a segment matches more than one route.
FACILITY_RANK = [
    "Protected Bike Lane",
    "Neighborhood Greenway",
    "Buffered Bike Lane",
    "Bike Lane",
    "Marked Shared Lane",
]
LOW_STRESS = {"Protected Bike Lane", "Neighborhood Greenway"}

# Centerline classes that count as bikeable streets: arterial, collector, local.
BIKEABLE_CLASSES = {"2", "3", "4"}

# Bike route `st_name` values that are misspelled or formatted differently from
# the centerline `street_nam` for the same street.
STREET_ALIASES = {
    "MARTIN LUTHER KING JR": "DR MARTIN LUTHER KING JR",
    "EAST LAKE": "EASTLAKE",
    "BERWN": "BERWYN",
    "BLOOMINDALE": "BLOOMINGDALE",
}

BUFFER_FT = 40
MIN_OVERLAP = 0.6


def bikeable_streets(centerlines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    streets = centerlines[centerlines["class"].isin(BIKEABLE_CLASSES)].copy()
    streets["length_ft"] = streets.length
    return streets[streets["length_ft"] > 0]


def _same_street(segment_name: str | None, route_name: str | None, route_full: str | None) -> bool:
    # Unnamed segments and routes come through as NaN, not None.
    if not isinstance(segment_name, str):
        return False
    seg = segment_name.upper().strip()
    name = route_name.upper().strip() if isinstance(route_name, str) else ""
    if seg == STREET_ALIASES.get(name, name):
        return True
    # `st_name` is truncated for some streets ("AVENUE" for "AVENUE L"), so fall
    # back to finding the segment name as whole words in the route's full name.
    full = route_full.upper() if isinstance(route_full, str) else ""
    return f" {seg} " in f" {full} "


def match_facilities(streets: gpd.GeoDataFrame, bike_routes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add a `facility` column (None where the segment has no bikeway).

    A segment matches a route when they share a street name and at least
    MIN_OVERLAP of the segment lies within BUFFER_FT of the route. The name
    check stops short cross streets being swept up by the buffer.
    """
    routes = bike_routes[["street", "st_name", "displayrou", "geometry"]].copy()
    routes["geometry"] = routes.buffer(BUFFER_FT, cap_style="flat")
    routes["rank"] = routes["displayrou"].map(FACILITY_RANK.index)

    pairs = gpd.sjoin(
        streets[["street_nam", "length_ft", "geometry"]],
        routes,
        predicate="intersects",
    )
    pairs = pairs[
        [
            _same_street(seg, route, full)
            for seg, route, full in zip(pairs["street_nam"], pairs["st_name"], pairs["street"])
        ]
    ]
    route_geom = gpd.GeoSeries(
        routes.geometry.loc[pairs["index_right"]].values, index=pairs.index, crs=pairs.crs
    )
    pairs["overlap"] = (
        pairs.geometry.intersection(route_geom, align=False).length / pairs["length_ft"]
    )

    # A segment can be covered by two consecutive routes of the same type.
    by_type = pairs.groupby([pairs.index, "displayrou", "rank"])["overlap"].sum().reset_index()
    by_type = by_type[by_type["overlap"] >= MIN_OVERLAP].sort_values("rank")
    best = by_type.drop_duplicates("level_0").set_index("level_0")["displayrou"]

    out = streets.copy()
    out["facility"] = pd.Series(best).reindex(out.index).astype(object)
    out["facility"] = out["facility"].where(out["facility"].notna(), None)
    return out
