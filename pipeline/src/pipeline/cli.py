"""Command line entry point: `uv run pipeline coverage`."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import shapely

from pipeline.coverage import aggregate, match
from pipeline.sources import socrata

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
BUILD = ROOT / "data" / "build"
PROCESSED = ROOT / "data" / "processed"

TILES = ROOT / "site" / "public" / "tiles" / "streets.pmtiles"

SIMPLIFY_FT = 50

BIKEWAY_MIN_ZOOM = 8
# Centerline class -> first zoom level the street is drawn at.
STREET_MIN_ZOOM = {"2": 9, "3": 11, "4": 12}


def _write_areas(areas, id_col, name_col, area_stats, path):
    out = gpd.GeoDataFrame(
        {"id": areas[id_col].astype(str), "name": areas[name_col].astype(str)},
        geometry=areas.simplify(SIMPLIFY_FT),
        crs=areas.crs,
    )
    for key in ("street_miles", "any_miles", "low_stress_miles", "any_pct", "low_stress_pct"):
        out[key] = [area_stats.get(str(i), {}).get(key, 0.0) for i in out["id"]]
    out.to_crs("EPSG:4326").to_file(path, driver="GeoJSON", COORDINATE_PRECISION=5)


def _write_tile_input(streets: gpd.GeoDataFrame, path: Path) -> None:
    """Write streets as GeoJSON with a per-feature minimum zoom for tippecanoe.

    Bikeways and arterials appear when zoomed out; local streets only once the
    map is close enough to tell them apart. Too large to commit.
    """
    out = streets.to_crs("EPSG:4326")
    name = (out["street_nam"].fillna("") + " " + out["street_typ"].fillna("")).str.strip()
    class_zoom = out["class"].map(STREET_MIN_ZOOM)
    min_zoom = class_zoom.where(out["facility"].isna(), BIKEWAY_MIN_ZOOM)
    with path.open("w") as f:
        for geom, street, facility, zoom in zip(out.geometry, name, out["facility"], min_zoom):
            props = {"name": street.title()}
            if isinstance(facility, str):
                props["facility"] = facility
            feature = {
                "type": "Feature",
                "properties": props,
                "tippecanoe": {"minzoom": int(zoom)},
                "geometry": shapely.geometry.mapping(shapely.set_precision(geom, 1e-6)),
            }
            f.write(json.dumps(feature, separators=(",", ":")) + "\n")


def tiles() -> None:
    source = BUILD / "streets.geojson"
    if not source.exists():
        raise SystemExit("data/build/streets.geojson is missing; run `pipeline coverage` first")
    TILES.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "tippecanoe",
            "--output",
            str(TILES),
            "--force",
            "--layer",
            "streets",
            "--minimum-zoom",
            str(BIKEWAY_MIN_ZOOM),
            "--maximum-zoom",
            "13",
            # Every street must survive; the default limits silently drop features.
            "--no-feature-limit",
            "--no-tile-size-limit",
            "--read-parallel",
            "--quiet",
            str(source),
        ],
        check=True,
    )
    print(f"wrote {TILES.relative_to(ROOT)} ({TILES.stat().st_size / 1e6:.1f} MB)")


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
    _write_tile_input(streets, BUILD / "streets.geojson")

    city = result["citywide"]
    print(
        f"{city['street_miles']} street miles | any facility {city['any_pct']}% "
        f"| low-stress {city['low_stress_pct']}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    parser.add_argument("command", choices=["coverage", "tiles"])
    parser.add_argument("--refresh", action="store_true", help="re-download source datasets")
    args = parser.parse_args()
    if args.command == "coverage":
        coverage(args.refresh)
    else:
        tiles()
