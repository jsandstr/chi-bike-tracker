"""Download datasets from the Chicago Data Portal as GeoDataFrames."""

from pathlib import Path

import geopandas as gpd
import httpx

PORTAL = "https://data.cityofchicago.org"

BIKE_ROUTES = "hvv9-38ut"
STREET_CENTERLINES = "pr57-gg9e"
WARDS = "p293-wvbd"
COMMUNITY_AREAS = "igwz-8jzy"

# Illinois State Plane East (US feet); used for all length and distance work.
CRS_FEET = "EPSG:3435"


def download(dataset_id: str, dest: Path, limit: int = 200_000) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{PORTAL}/resource/{dataset_id}.geojson"
    with httpx.stream("GET", url, params={"$limit": limit}, timeout=300) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return dest


def load(dataset_id: str, raw_dir: Path, refresh: bool = False) -> gpd.GeoDataFrame:
    path = raw_dir / f"{dataset_id}.geojson"
    if refresh or not path.exists():
        download(dataset_id, path)
    return gpd.read_file(path).to_crs(CRS_FEET)
