# Data sources

Verified 2026-10-06 against the live APIs.

## Chicago Data Portal (Socrata, `data.cityofchicago.org`)

| Dataset | ID | Rows | Last updated | Notes |
|---|---|---|---|---|
| Bike Routes | `hvv9-38ut` | 1,008 | 2025-12-16 | `3w5d-sru8` is only the map view of this; query `hvv9-38ut` |
| Street Center Lines | `pr57-gg9e` | 56,338 | 2021-06-11 | `6imu-meau` is the map view. Lengths (`shape_len`) are in feet |
| Wards (2023-) | `p293-wvbd` | 50 | 2022-06-15 | |
| Community Areas | `igwz-8jzy` | 77 | 2025-04-22 | |

GeoJSON export: `/resource/<id>.geojson?$limit=<n>` (default limit is 1,000).

### Bike Routes fields
`the_geom` (MultiLineString), `street`, `st_name`, `f_street`, `t_street`, `displayrou`,
`mi_ctrline` (centerline miles), `oneway_dir`, `br_oneway`, `br_ow_dir`, `contraflow`.

`displayrou` values and centerline miles: Bike Lane 138.5, Buffered Bike Lane 106.5,
Neighborhood Greenway 85.2, Protected Bike Lane 68.7, Marked Shared Lane 47.0 (446 total).
Off-street trails are not in this dataset.

There is no segment ID shared with Street Center Lines, so matching is spatial.

### Street Center Lines `class`
Counts: 1 = 1,869; 2 = 6,265; 3 = 6,959; 4 = 37,831; 5 = 78; 7 = 150; 9 = 1,157; 99 = 556;
E = 1,113; RIV = 351; S = 6. Meanings below are from the city's metadata convention and
still need confirming against the dataset's attached documentation:
1 expressway, 2 arterial, 3 collector, 4 local, 5 named alley, 7 tiered, 9 ramp,
99 unclassified, E extent line, RIV river, S sidewalk/path.

## Archived Bike Routes snapshots

Verified 2026-10-06. The current dataset has no install dates, so the history stage matches
older snapshots of the same data. `pipeline/history/snapshots.py` holds the list. All are
GeoJSON exports of `data.cityofchicago.org` datasets; the as-of month is our label, taken
from the portal's publish date.

| As-of | Dataset | Rows | Facility column | Other columns |
|---|---|---|---|---|
| 2014-12 | `qbbe-eqz7` | 957 | `bikeroute` | `type` (numeric code), `street`, `f_street`, `t_street` |
| 2016-03 | `d6m3-6qzf` + `s5am-iwmv` | 1,050 + 11 | `bikeroute` | same; the two parts are one dataset and are concatenated |
| 2018-11 | `s72g-kd5k` | 568 | `bikeroute` | `status` (all EXISTING), `type`, `shape_leng` |
| 2020-02 | `auur-f9g5` | 726 | `bikeroute` | `street`, `shape_leng` |
| 2021-01 | `ard8-rcb7` | 774 | `displayrou` | `street`, `shape_leng`, `objectid` |
| 2021-11 | `8ec2-eaj2` | 897 | `displayrou` | `st_name`, `pre_dir`, `st_type`, `mi_ctrline`, address ranges |
| 2022-12 | `9saw-v2cz` | 883 | `displayrou` | `pre_dir`, `mi_ctrline`; no `st_name` |
| 2025-12 | `hvv9-38ut` | 1,008 | `displayrou` | the current dataset |

Label vocabularies (before normalising):
- 2014 and 2016 prefix everything with `EXISTING `: `BIKE LANE`, `BUFFERED BIKE LANE`,
  `CYCLE TRACK`, `SHARED-LANE`, `NEIGHBORHOOD GREENWAY` (2016 only), `OFF-STREET TRAIL`;
  also `RECOMMENDED BIKE ROUTE`, `PROPOSED OFF-STREET TRAIL` and `ACCESS PATH`, which are dropped.
- 2018 drops the prefix and adds `GREEN WAVE` (one row; dropped).
- 2020 onward: `PROTECTED BIKE LANE` replaces `CYCLE TRACK`. 2022 has no trails or access paths.
- `CYCLE TRACK` is treated as `Protected Bike Lane`.

Quirks:
- Old snapshots have only the full `street` ("N HALSTED ST", "S DR MARTIN LUTHER KING JR DR W",
  or "DREXEL" with no suffix), no `st_name`; the matcher's whole-word fallback handles them.
- 2018 has `AVENUE  L` with two spaces; `normalise` collapses whitespace.
- Street renames defeat name matching: Conservatory Dr is `CENTRAL PARK` in the centerlines,
  `S US 41` in 2016 is Lake Shore Dr, and 2016 has the typo `CALIFONRIA`. Each is under 3 miles.
- Mileage moves between facility types across snapshots partly because the city relabelled
  routes (2016: Bike Lane to Buffered, 2021-01: Shared Lane and Bike Lane to Neighborhood
  Greenway), so per-facility deltas are not all new construction.
- 2016-03 to 2018-11 adds only about 11 route miles, which looks slow next to its neighbours;
  the 2018 file may be older than its label.

## City Clerk eLMS API (`api.chicityclerkelms.chicago.gov`, beta)

- `GET /matter?search=&filter=&sort=&top=&skip=` returns `{data: [...], meta: {count, pages}}`.
- `GET /matter/recordNumber/{recordNumber}` returns the full record with `actions`,
  `sponsors`, `attachments` (PDF URLs); these are null in list results.
- Useful fields: `recordNumber`, `title`, `type`, `status`, `subStatus`, `matterCategory`,
  `controllingBody`, `filingSponsor`, `introductionDate`, `finalActionDate`,
  `lastPublicationDate` (use for incremental fetches).
- `search=bicycle` returns 142 matters, mostly routine one-way street ordinances from the
  Committee on Pedestrian and Traffic Safety, so keyword search alone is too noisy.

## Not yet verified
LegiScan (Illinois bills), CDOT Complete Streets pages, CMAP TIP export.
