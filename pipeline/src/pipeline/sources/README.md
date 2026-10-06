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
