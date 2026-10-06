"""Command line entry point: `uv run pipeline coverage`."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from pipeline.coverage import aggregate, match
from pipeline.history import build as history_build
from pipeline.history import policies as policy_records
from pipeline.history import snapshots as snapshot_sources
from pipeline.sources import socrata

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
BUILD = ROOT / "data" / "build"
PROCESSED = ROOT / "data" / "processed"
POLICIES = ROOT / "data" / "curated" / "policies"

TILE_DIR = ROOT / "site" / "public" / "tiles"

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


def _feature(geom, props: dict, min_zoom: int | None = None) -> str:
    feature = {"type": "Feature", "properties": props}
    if min_zoom is not None:
        feature["tippecanoe"] = {"minzoom": min_zoom}
    feature["geometry"] = shapely.geometry.mapping(shapely.set_precision(geom, 1e-6))
    return json.dumps(feature, separators=(",", ":"))


def _street_names(streets: gpd.GeoDataFrame) -> pd.Series:
    name = (streets["street_nam"].fillna("") + " " + streets["street_typ"].fillna("")).str.strip()
    return name.str.title()


def _write_tile_input(streets: gpd.GeoDataFrame, path: Path) -> None:
    """Write streets as GeoJSON with a per-feature minimum zoom for tippecanoe.

    Bikeways and arterials appear when zoomed out; local streets only once the
    map is close enough to tell them apart. Too large to commit.
    """
    out = streets.to_crs("EPSG:4326")
    class_zoom = out["class"].map(STREET_MIN_ZOOM)
    min_zoom = class_zoom.where(out["facility"].isna(), BIKEWAY_MIN_ZOOM)
    with path.open("w") as f:
        for geom, name, facility, zoom in zip(
            out.geometry, _street_names(out), out["facility"], min_zoom
        ):
            props = {"name": name}
            if isinstance(facility, str):
                props["facility"] = facility
            f.write(_feature(geom, props, int(zoom)) + "\n")


def _write_history_input(segments: gpd.GeoDataFrame, path: Path) -> None:
    """Write segments with a facility in any snapshot; every feature shows from zoom 8."""
    out = segments.to_crs("EPSG:4326")
    cols = [c for c in out.columns if c.startswith("s") and c[1:].isdigit()]
    with path.open("w") as f:
        for i, (geom, name) in enumerate(zip(out.geometry, _street_names(out))):
            props = {"name": name}
            props.update({c: out[c].iloc[i] for c in cols if isinstance(out[c].iloc[i], str)})
            f.write(_feature(geom, props) + "\n")


def _build_tiles(source: Path, output: Path, layer: str) -> None:
    if not source.exists():
        raise SystemExit(
            f"{source.relative_to(ROOT)} is missing; run the stage that writes it first"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "tippecanoe",
            "--output",
            str(output),
            "--force",
            "--layer",
            layer,
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
    print(f"wrote {output.relative_to(ROOT)} ({output.stat().st_size / 1e6:.1f} MB)")


def tiles() -> None:
    _build_tiles(BUILD / "streets.geojson", TILE_DIR / "streets.pmtiles", "streets")
    if (BUILD / "history.geojson").exists():
        _build_tiles(BUILD / "history.geojson", TILE_DIR / "history.pmtiles", "history")


def _city_streets(centerlines: gpd.GeoDataFrame, wards: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Bikeable streets inside the city; wards define what is in Chicago."""
    streets = aggregate.assign_areas(match.bikeable_streets(centerlines), wards, "ward", "ward")
    return streets[streets["ward"].notna()]


def coverage(refresh: bool) -> None:
    centerlines = socrata.load(socrata.STREET_CENTERLINES, RAW, refresh)
    routes = socrata.load(socrata.BIKE_ROUTES, RAW, refresh)
    wards = socrata.load(socrata.WARDS, RAW, refresh)
    communities = socrata.load(socrata.COMMUNITY_AREAS, RAW, refresh)

    # The centerline file runs past the city limits, so drop streets in no ward.
    streets = match.match_facilities(_city_streets(centerlines, wards), routes)
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


def history(refresh: bool) -> None:
    centerlines = socrata.load(socrata.STREET_CENTERLINES, RAW, refresh)
    wards = socrata.load(socrata.WARDS, RAW, refresh)
    streets = _city_streets(centerlines, wards)

    entries, matched = [], []
    for i, snap in enumerate(snapshot_sources.SNAPSHOTS):
        routes = snapshot_sources.load(snap, RAW, refresh)
        result = match.match_facilities(streets, routes)
        matched.append(result)
        entries.append(history_build.snapshot_entry(f"s{i}", snap.date, "+".join(snap.ids), result))
        print(
            f"{snap.date}: {entries[-1]['any_miles']} mi any, {entries[-1]['low_stress_miles']} low-stress"
        )
    history_build.add_growth_rates(entries)

    policies = policy_records.load_policies(POLICIES) if POLICIES.exists() else []
    result = {
        "generated": datetime.now(UTC).date().isoformat(),
        "street_miles": round(streets["length_ft"].sum() / aggregate.FEET_PER_MILE, 2),
        "snapshots": entries,
    }
    PROCESSED.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "history.json").write_text(json.dumps(result, indent=2) + "\n")
    records = policy_records.build_all(policies, entries)
    (PROCESSED / "policies.json").write_text(json.dumps(records, indent=2) + "\n")
    segments = history_build.segments_with_facilities(streets, matched)
    _write_history_input(segments, BUILD / "history.geojson")
    print(f"{len(policies)} policies, {len(segments)} segments with a facility in any snapshot")


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    parser.add_argument("command", choices=["coverage", "history", "tiles"])
    parser.add_argument("--refresh", action="store_true", help="re-download source datasets")
    args = parser.parse_args()
    if args.command == "coverage":
        coverage(args.refresh)
    elif args.command == "history":
        history(args.refresh)
    else:
        tiles()
