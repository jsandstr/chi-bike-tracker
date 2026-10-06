# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A public website tracking Chicago bike infrastructure: a street coverage map, a policy/legislation tracker, and planned construction projects. The approved plan, including phases and methodology, is at `~/.claude/plans/i-want-to-create-sequential-hennessy.md`.

**Current state:** early. Only the Python pipeline exists, and only its coverage stage (download, match, aggregate) with tests. There is no site, no map tiles, no policy or project ingestion, and no CI workflows yet. Sections below marked *(planned)* describe intended design, not existing code.

## Commands

All pipeline commands run from `pipeline/` and go through `uv` (the system `python3` may be unusable on this machine).

```bash
cd pipeline
uv sync                                   # install dependencies
uv run pytest                             # all tests
uv run pytest tests/test_coverage.py::test_best_facility_wins   # single test
uv run pipeline coverage                  # rebuild data/processed + data/build (add --refresh to re-download)
uv run ruff check . && uv run ruff format .
```

uv prints a harmless `Failed to patch the install name of the dynamic library` warning on every run.

## Architecture

```
Scheduled GitHub Actions (planned)
  ├─ pipeline/ (Python)  →  data/processed/*.json, PMTiles
  └─ opens a PR with data changes  →  human review/merge  →  deploy
site/ (planned: Astro + MapLibre + PMTiles, static, GitHub Pages)
```

The site is static with no server or database. The pipeline writes generated data into the repo, and **the pull request is the review queue**: scraped or AI-summarised content must not be published without passing through a reviewed PR.

### Data directories

- `data/raw/` — downloaded source datasets, git-ignored, cached. `socrata.load()` only re-downloads when `refresh=True` or the file is missing. The centerlines file is about 81 MB.
- `data/processed/` — generated outputs the site reads (`coverage.json`, ward and community area GeoJSON with stats). Committed.
- `data/build/` — git-ignored intermediates, currently `streets.geojson` (20 MB), the input for tippecanoe.
- `data/queue/` — generated project candidates awaiting human approval *(planned)*.
- `data/curated/` — hand-maintained records and overrides; the source of truth for projects. Never overwrite from the pipeline.

### Coverage calculation

`pipeline/src/pipeline/coverage/match.py` assigns a bike facility to each street centerline segment, because the city's Bike Routes and Street Center Lines datasets share no segment ID. A segment matches a route when the street names agree (`_same_street`, including `STREET_ALIASES` for city typos) **and** at least 60% of the segment lies within a 40 ft buffer of the route. The name check exists to stop short cross streets being swept up by the buffer.

- All geometry work is in `EPSG:3435` (Illinois State Plane East, US feet). `socrata.load()` reprojects on read, so lengths are feet and miles are `length / 5280`.
- Denominator is centerline classes `2`, `3`, `4` (arterial, collector, local). The class meanings are assumed from convention and not yet confirmed against the dataset's documentation.
- Two tiers are reported: any facility, and low-stress (`LOW_STRESS`: protected lanes and neighborhood greenways). When a segment matches several facility types, `FACILITY_RANK` order wins.
- Validate matcher changes against the city's own `mi_ctrline` totals per `displayrou`. The current matcher recovers 443.3 of 445.9 miles (99%).
- The centerline file extends past the city limits. `cli.coverage` drops segments whose midpoint is in no ward, so ward totals sum exactly to the citywide total. Community areas sum about 9 miles short of it; that gap is not yet explained.
- Segments are assigned to an area by midpoint, so a boundary street counts toward one side only.
- Off-street trails are not in the Bike Routes dataset and are not counted.

### Data sources

`pipeline/src/pipeline/sources/README.md` records verified dataset IDs, field names, row counts, and API quirks. Read it before touching a source, and update it when a source is verified or changes. Two things that are easy to get wrong:

- Bike Routes is `hvv9-38ut`; `3w5d-sru8` is only its map view and has no columns.
- City Clerk eLMS list results return `actions`, `sponsors`, and `attachments` as null; fetch `/matter/recordNumber/{recordNumber}` for those. Keyword search is noisy (mostly routine one-way street ordinances), so relevance needs classification, not just search.

### Policy and project ingestion *(planned)*

Keyword pre-filter, then Claude Haiku 4.5 for relevance classification and Claude Sonnet 5.5 for plain-language summaries, with pydantic-validated structured output and caching by content hash so unchanged items are not re-billed. Summaries are labelled as AI-generated on the site and always link the official record.
