# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A public website tracking Chicago bike infrastructure: a street coverage map, a policy/legislation tracker, and planned construction projects. The approved plan, including phases and methodology, is at `~/.claude/plans/i-want-to-create-sequential-hennessy.md`.

**Current state:** early. The pipeline's coverage stage (download, match, aggregate, tiles), a history stage (snapshots, policies) and and a two-page Astro site (coverage map, policies with a timelapse) exist. `.github/workflows/deploy.yml` deploys the site to GitHub Pages on pushes to main. There is no policy or project ingestion and no scheduled data workflow yet. Sections below marked *(planned)* describe intended design, not existing code.

## Commands

All pipeline commands run from `pipeline/` and go through `uv` (the system `python3` may be unusable on this machine).

```bash
cd pipeline
uv sync                                   # install dependencies
uv run pytest                             # all tests
uv run pytest tests/test_coverage.py::test_best_facility_wins   # single test
uv run pipeline coverage                  # rebuild data/processed + data/build (add --refresh to re-download)
uv run pipeline history                   # rebuild history.json, policies.json and data/build/history.geojson
uv run ruff check . && uv run ruff format .
```

`pipeline tiles` needs `tippecanoe` on the PATH (`brew install tippecanoe`) and writes `site/public/tiles/streets.pmtiles` and `history.pmtiles` (the latter once `pipeline history` has run), which are committed. Run it after `pipeline coverage` and `pipeline history`:

```bash
uv run pipeline tiles
```

Site commands run from `site/`:

```bash
npm install
npm run dev        # http://localhost:4321/chi-bike-tracker/ (the base path is required)
npm run build      # astro check (type-check) then build to dist/
```

`astro dev` runs detached; stop it with `npx astro dev stop`. After changing `astro.config.mjs`, stop it and delete `site/node_modules/.vite` or the browser gets "Outdated Optimize Dep" 504s.

uv prints a harmless `Failed to patch the install name of the dynamic library` warning on every run.

## Architecture

```
Scheduled GitHub Actions (planned)
  ├─ pipeline/ (Python)  →  data/processed/*.json, PMTiles
  └─ opens a PR with data changes  →  human review/merge  →  deploy
site/ (Astro + MapLibre + PMTiles, static; GitHub Pages deploy planned)
```

The site is static with no server or database. The pipeline writes generated data into the repo, and **the pull request is the review queue**: scraped or AI-summarised content must not be published without passing through a reviewed PR.

### Data directories

- `data/raw/` — downloaded source datasets, git-ignored, cached. `socrata.load()` only re-downloads when `refresh=True` or the file is missing. The centerlines file is about 81 MB.
- `data/processed/` — generated outputs the site reads (`coverage.json`, ward and community area GeoJSON with stats, `history.json`, `policies.json`). Committed.
- `data/build/` — git-ignored intermediates, `streets.geojson` (20 MB) and `history.geojson`, the inputs for tippecanoe.
- `data/queue/` — generated project candidates awaiting human approval *(planned)*.
- `data/curated/` — hand-maintained records and overrides; the source of truth for projects and for policies (`policies/*.yaml`, validated by `pipeline/history/policies.py`, unknown fields rejected). Never overwrite from the pipeline.

### Coverage calculation

`pipeline/src/pipeline/coverage/match.py` assigns a bike facility to each street centerline segment, because the city's Bike Routes and Street Center Lines datasets share no segment ID. A segment matches a route when the street names agree (`_same_street`, including `STREET_ALIASES` for city typos) **and** at least 60% of the segment lies within a 40 ft buffer of the route. The name check exists to stop short cross streets being swept up by the buffer.

- All geometry work is in `EPSG:3435` (Illinois State Plane East, US feet). `socrata.load()` reprojects on read, so lengths are feet and miles are `length / 5280`.
- Denominator is centerline classes `2`, `3`, `4` (arterial, collector, local). The class meanings are assumed from convention and not yet confirmed against the dataset's documentation.
- Two tiers are reported: any facility, and low-stress (`LOW_STRESS`: protected lanes and neighborhood greenways). When a segment matches several facility types, `FACILITY_RANK` order wins.
- Validate matcher changes against the city's own `mi_ctrline` totals per `displayrou`. The current matcher recovers 443.3 of 445.9 miles (99%).
- The centerline file extends past the city limits. `cli.coverage` drops segments whose midpoint is in no ward, so ward totals sum exactly to the citywide total. Community areas sum about 9 miles short of it; that gap is not yet explained.
- Segments are assigned to an area by midpoint, so a boundary street counts toward one side only.
- Off-street trails are not in the Bike Routes dataset and are not counted.

### Site

`site/src/pages/index.astro` renders the summary panel at build time from `data/processed/coverage.json`; `site/src/scripts/map.ts` owns the map and everything that reacts to the three controls (measure, map colouring, ward/community ranking). The ward and community GeoJSON are imported with `?url` and fetched in the browser.

- `site/src/facilities.ts` is the single place for facility names, colours and choropleth breaks. Names must match `FACILITY_RANK` in the pipeline. The five line colours were validated together for colour-blind separation; do not change one in isolation.
- MapLibre 6 has no default export and cannot locate its worker after bundling, hence `import * as maplibregl`, the `?worker&url` import with `setWorkerUrl`, and `worker.format: "es"` in the Astro config.
- Tiles carry only `name` and `facility` per street. Each feature gets a tippecanoe `minzoom` (bikeways 8, arterials 9, collectors 11, local 12) in `cli._write_tile_input`.
- The basemap is OpenFreeMap's hosted Positron style; the page is light-mode only.
- `site/src/layouts/Base.astro` holds the head, fonts and global CSS; `components/Masthead.astro` is the four-star masthead plus the nav (`current` marks the page, links use `BASE_URL`). `scripts/basemap.ts` is the shared MapLibre setup (worker URL, pmtiles protocol, `createMap`, `tileUrl`); `facilities.ts` also holds `facilityStops` (map colours per measure) and the Chicago bounds. `format.ts` has number and `YYYY-MM` helpers, and `data.ts` types and imports `history.json` and `policies.json`.
- `site/src/pages/policies.astro` is a normal scrolling page: timelapse, current and past policy rows, a coverage-contribution comparison, and method notes. The chart is plain HTML and CSS rendered at build time with percentage positions (so text stays full size on phones), both measures drawn and one shown by CSS on `[data-measure]`. X positions come from `timeScale` (calendar months), never the snapshot index. `scripts/timelapse.ts` owns the map frame (`has s<i>` filter, colours from `s<i>`), the measure toggle, play/pause (hidden under `prefers-reduced-motion`), and the slider, which snaps to the nearest snapshot. It still runs the chart if WebGL is unavailable. Styles are in `styles/policies.css`.

### History and policies

`pipeline history` matches archived Bike Routes snapshots (2014-12 to 2025-12, IDs in `history/snapshots.py` and `sources/README.md`) with the same `match_facilities` against the same ward-filtered centerlines, so every snapshot shares one denominator and the 2025-12 snapshot equals `coverage.json`. Each snapshot's labels are normalised to the five canonical facility names; an unknown label raises, so a new snapshot format fails loudly. Old snapshots have no `st_name`, so the matcher's whole-word fallback on `street` does the name check. Recovery is 94 to 100% of the snapshot's own route length; what is missed is mostly renamed streets.

`history.json` holds miles and percentages per snapshot. `history.pmtiles` (layer `history`) has every segment that had a facility in any snapshot, with `s0`..`s7` giving its facility at each snapshot.

A policy's contribution in `policies.json` is attributed by time window: from the latest snapshot at or before its start to the earliest at or after its end (the last snapshot if it is ongoing). This is an approximation, since everything built in the window is credited to the policy, whatever its cause, and snapshot dates are only as precise as the portal's publish dates. `truncated` marks policies that start before the first snapshot. Facility relabelling by the city also shows up as change.

### Data sources

`pipeline/src/pipeline/sources/README.md` records verified dataset IDs, field names, row counts, and API quirks. Read it before touching a source, and update it when a source is verified or changes. Two things that are easy to get wrong:

- Bike Routes is `hvv9-38ut`; `3w5d-sru8` is only its map view and has no columns.
- City Clerk eLMS list results return `actions`, `sponsors`, and `attachments` as null; fetch `/matter/recordNumber/{recordNumber}` for those. Keyword search is noisy (mostly routine one-way street ordinances), so relevance needs classification, not just search.

### Policy and project ingestion *(planned)*

Keyword pre-filter, then Claude Haiku 4.5 for relevance classification and Claude Sonnet 5.5 for plain-language summaries, with pydantic-validated structured output and caching by content hash so unchanged items are not re-billed. Summaries are labelled as AI-generated on the site and always link the official record.
