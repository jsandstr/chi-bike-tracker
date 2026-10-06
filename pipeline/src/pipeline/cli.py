"""Command line entry point: `uv run pipeline coverage`."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd

from pipeline.coverage import aggregate, match
from pipeline.sources import socrata

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
BUILD = ROOT / "data" / "build"
PROCESSED = ROOT / "data" / "processed"

SIMPLIFY_FT = 50


def _write_areas(areas, id_col, name_col, area_stats, path):
    out = gpd.GeoDataFrame(
        {"id": areas[id_col].astype(str), "name": areas[name_col].astype(str)},
        geometry=areas.simplify(SIMPLIFY_FT),
        crs=areas.crs,
    )
    for key in ("street_miles", "any_miles", "low_stress_miles", "any_pct", "low_stress_pct"):
        out[key] = [area_stats.get(str(i), {}).get(key, 0.0) for i in out["id"]]
    out.to_crs("EPSG:4326").to_file(path, driver="GeoJSON", COORDINATE_PRECISION=5)


def coverage(refresh: bool) -> None:
    centerlines = socrata.load(socrata.STREET_CENTERLINES, RAW, refresh)
    routes = socrata.load(socrata.BIKE_ROUTES, RAW, refresh)
    wards = socrata.load(socrata.WARDS, RAW, refresh)
    communities = socrata.load(socrata.COMMUNITY_AREAS, RAW, refresh)

    streets = match.match_facilities(match.bikeable_streets(centerlines), routes)
    streets = aggregate.assign_areas(streets, wards, "ward", "ward")
    # The centerline file runs past the city limits; wards define what is in Chicago.
    streets = streets[streets["ward"].notna()]
    streets = aggregate.assign_areas(streets, communities, "area_numbe", "community_area")

    ward_stats = aggregate.by_area(streets, "ward")
    community_stats = aggregate.by_area(streets, "community_area")
    result = {
        "generated": datetime.now(UTC).date().isoformat(),
        "citywide": aggregate.stats(streets),
        "wards": ward_stats,
        "community_areas": community_stats,
    }

    PROCESSED.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "coverage.json").write_text(json.dumps(result, indent=2) + "\n")
    _write_areas(wards, "ward", "ward", ward_stats, PROCESSED / "wards.geojson")
    _write_areas(
        communities,
        "area_numbe",
        "community",
        community_stats,
        PROCESSED / "community_areas.geojson",
    )
    # Input for tippecanoe; too large to commit.
    cols = ["street_nam", "street_typ", "class", "facility", "ward", "community_area", "geometry"]
    streets[cols].to_crs("EPSG:4326").to_file(
        BUILD / "streets.geojson", driver="GeoJSON", COORDINATE_PRECISION=6
    )

    city = result["citywide"]
    print(
        f"{city['street_miles']} street miles | any facility {city['any_pct']}% "
        f"| low-stress {city['low_stress_pct']}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    parser.add_argument("command", choices=["coverage"])
    parser.add_argument("--refresh", action="store_true", help="re-download source datasets")
    args = parser.parse_args()
    if args.command == "coverage":
        coverage(args.refresh)
