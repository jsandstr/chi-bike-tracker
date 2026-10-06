import geopandas as gpd
from shapely.geometry import LineString, box

from pipeline.coverage import aggregate, match
from pipeline.sources.socrata import CRS_FEET


def _streets(rows):
    names, classes, geoms = zip(*rows)
    gdf = gpd.GeoDataFrame(
        {"street_nam": names, "class": classes}, geometry=list(geoms), crs=CRS_FEET
    )
    return match.bikeable_streets(gdf)


def _routes(rows):
    full, names, kinds, geoms = zip(*rows)
    return gpd.GeoDataFrame(
        {"street": full, "st_name": names, "displayrou": kinds}, geometry=list(geoms), crs=CRS_FEET
    )


MAIN = LineString([(0, 0), (1000, 0)])


def test_segment_on_route_matches():
    out = match.match_facilities(
        _streets([("MAIN", "2", MAIN)]), _routes([("MAIN ST", "MAIN", "Bike Lane", MAIN)])
    )
    assert out["facility"].tolist() == ["Bike Lane"]


def test_cross_street_and_parallel_street_do_not_match():
    streets = _streets(
        [
            ("CROSS", "4", LineString([(500, -30), (500, 30)])),  # inside the buffer
            ("MAIN", "4", LineString([(0, 400), (1000, 400)])),  # same name, a block away
        ]
    )
    out = match.match_facilities(streets, _routes([("MAIN ST", "MAIN", "Bike Lane", MAIN)]))
    assert out["facility"].tolist() == [None, None]


def test_partial_overlap_below_threshold_does_not_match():
    route = LineString([(0, 0), (400, 0)])
    out = match.match_facilities(
        _streets([("MAIN", "2", MAIN)]), _routes([("MAIN ST", "MAIN", "Bike Lane", route)])
    )
    assert out["facility"].tolist() == [None]


def test_best_facility_wins():
    routes = _routes(
        [
            ("MAIN ST", "MAIN", "Marked Shared Lane", MAIN),
            ("MAIN ST", "MAIN", "Protected Bike Lane", MAIN),
        ]
    )
    out = match.match_facilities(_streets([("MAIN", "2", MAIN)]), routes)
    assert out["facility"].tolist() == ["Protected Bike Lane"]


def test_aliased_and_truncated_names_match():
    streets = _streets([("DR MARTIN LUTHER KING JR", "2", MAIN), ("AVENUE L", "4", MAIN)])
    routes = _routes(
        [
            ("MARTIN LUTHER KING JR DR", "MARTIN LUTHER KING JR", "Bike Lane", MAIN),
            ("AVENUE L", "AVENUE", "Bike Lane", MAIN),
        ]
    )
    out = match.match_facilities(streets, routes)
    assert out["facility"].tolist() == ["Bike Lane", "Bike Lane"]


def test_non_street_classes_are_excluded():
    assert len(_streets([("I90", "1", MAIN), ("ALLEY", "5", MAIN), ("MAIN", "3", MAIN)])) == 1


def test_stats_and_area_totals():
    streets = _streets(
        [
            ("A", "2", LineString([(0, 100), (5280, 100)])),
            ("B", "2", LineString([(0, 200), (5280, 200)])),
            ("C", "2", LineString([(0, 6000), (10560, 6000)])),
        ]
    )
    streets["facility"] = ["Protected Bike Lane", "Bike Lane", None]
    city = aggregate.stats(streets)
    assert city["street_miles"] == 4.0
    assert city["any_pct"] == 50.0
    assert city["low_stress_pct"] == 25.0

    areas = gpd.GeoDataFrame(
        {"ward": ["1", "2"]},
        geometry=[box(-10, 0, 20000, 5000), box(-10, 5000, 20000, 9000)],
        crs=CRS_FEET,
    )
    tagged = aggregate.assign_areas(streets, areas, "ward", "ward")
    per_ward = aggregate.by_area(tagged, "ward")
    assert per_ward["1"]["any_pct"] == 100.0
    assert per_ward["2"]["any_pct"] == 0.0
    assert sum(w["street_miles"] for w in per_ward.values()) == city["street_miles"]
