"""Archived Bike Routes snapshots, normalised to the current dataset's schema."""

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from pipeline.coverage.match import FACILITY_RANK
from pipeline.sources import socrata


@dataclass(frozen=True)
class Snapshot:
    date: str  # YYYY-MM, the as-of date
    ids: tuple[str, ...]  # dataset parts, concatenated
    label_col: str


SNAPSHOTS = [
    Snapshot("2014-12", ("qbbe-eqz7",), "bikeroute"),
    Snapshot("2016-03", ("d6m3-6qzf", "s5am-iwmv"), "bikeroute"),
    Snapshot("2018-11", ("s72g-kd5k",), "bikeroute"),
    Snapshot("2020-02", ("auur-f9g5",), "bikeroute"),
    Snapshot("2021-01", ("ard8-rcb7",), "displayrou"),
    Snapshot("2021-11", ("8ec2-eaj2",), "displayrou"),
    Snapshot("2022-12", ("9saw-v2cz",), "displayrou"),
    Snapshot("2025-12", (socrata.BIKE_ROUTES,), "displayrou"),
]

# Every label the archives use, with "EXISTING " already stripped. None means the
# row is not an on-street facility and is dropped.
LABELS = {
    "PROTECTED BIKE LANE": "Protected Bike Lane",
    "CYCLE TRACK": "Protected Bike Lane",
    "BUFFERED BIKE LANE": "Buffered Bike Lane",
    "BIKE LANE": "Bike Lane",
    "SHARED-LANE": "Marked Shared Lane",
    "NEIGHBORHOOD GREENWAY": "Neighborhood Greenway",
    "RECOMMENDED BIKE ROUTE": None,
    "PROPOSED OFF-STREET TRAIL": None,
    "OFF-STREET TRAIL": None,
    "ACCESS PATH": None,
    # A signal-timing treatment on streets that already have a bikeway.
    "GREEN WAVE": None,
}
LABELS.update({name: name for name in FACILITY_RANK})
LABELS.update({name.upper(): name for name in FACILITY_RANK})


def normalise_label(raw: str) -> str | None:
    """Map an archived label to a canonical facility name, or None to drop the row.

    Unknown labels raise so a new snapshot format fails loudly.
    """
    label = raw.strip().upper().removeprefix("EXISTING ")
    if label not in LABELS:
        raise ValueError(f"unknown bike route label: {raw!r}")
    return LABELS[label]


def normalise(routes: gpd.GeoDataFrame, label_col: str) -> gpd.GeoDataFrame:
    """Return routes with the `street`, `st_name`, `displayrou` columns the matcher reads.

    Old snapshots have no `st_name`; the matcher then finds the centerline name
    as whole words in the full `street`.
    """
    if "status" in routes:
        routes = routes[routes["status"].str.upper() == "EXISTING"]
    out = routes.copy()
    out["displayrou"] = out[label_col].map(normalise_label)
    out = out[out["displayrou"].notna()]
    # The 2018 file has "AVENUE  L" with two spaces, which defeats the whole-word match.
    out["street"] = out["street"].str.split().str.join(" ")
    if "st_name" not in out:
        out["st_name"] = None
    return out[["street", "st_name", "displayrou", "geometry"]]


def load(snapshot: Snapshot, raw_dir, refresh: bool) -> gpd.GeoDataFrame:
    parts = [socrata.load(i, raw_dir, refresh) for i in snapshot.ids]
    routes = pd.concat(parts, ignore_index=True)
    return normalise(gpd.GeoDataFrame(routes, crs=socrata.CRS_FEET), snapshot.label_col)
