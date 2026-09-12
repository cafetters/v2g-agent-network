# Data sources

Every raw file under `data/raw/` traces to a URL and pull date listed here.
Fields that could not be sourced are synthetic and labeled as such where used.

## NOAA Storm Events Database (pulled 2026-09-12)

- Bulk CSVs: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
  - `StormEvents_details-ftp_v1.0_d2025_c20260819.csv.gz`
  - `StormEvents_details-ftp_v1.0_d2026_c20260910.csv.gz`
  - Saved unmodified in `data/raw/noaa-storm-events/`.
- Selection: all MASSACHUSETTS rows for winter event types, Suffolk County /
  Boston zones, Nov 2025 - Mar 2026. The two heaviest snow events and one
  smaller disruption from that query:
  - `data/raw/jan26-snowstorm/noaa_episode_209121.csv` — Heavy Snow,
    Jan 25-27 2026, 18-23 in (23.2 in at Logan). 22 MA rows.
  - `data/raw/feb26-blizzard/noaa_episode_209918.csv` — Blizzard,
    Feb 22-23 2026, blizzard conditions at Logan 06:20-12:40 EST. 23 MA rows.
  - `data/raw/dec25-windstorm/noaa_episode_208283.csv` — High Wind,
    Dec 19 2025, gusts 50-60 mph, 64 mph at Logan. 10 MA rows.

## Outage reports (news; no search-indexed DPU filing found) (pulled 2026-09-12)

- Jan 26 storm: WBUR (statewide 2,000+ -> 317 by 8 AM) and Axios Boston
  (East Boston: "hundreds" out briefly — **fetch blocked, HTTP 403; cited from
  search snippet**). Notes: `data/raw/jan26-snowstorm/outages_transit_notes.txt`
- Feb 22-24 blizzard: CBS Boston (statewide peak 290,000; Eversource 230,000+,
  National Grid 17,000+), NBC Boston (restoration by Fri 2/27), Wikipedia
  (Northeast 650,000+). Notes: `data/raw/feb26-blizzard/outages_sources.txt`
  and `outages_cbs_boston.txt`
- A DPU post-storm filing may exist at eeaonline.eea.state.ma.us/DPU/Fileroom
  but is not fetchable/searchable here; news numbers used instead, as
  specified. **No neighborhood-level outage counts exist in any fetched
  source — neighborhood exposure is allocated from county/municipal counts by
  SVI weight and labeled ESTIMATE wherever used.**

## CDC/ATSDR SVI 2022, tract level (pulled 2026-09-12)

- `data/raw/svi/svi2022_massachusetts_tracts.csv` from
  https://svi.cdc.gov/Documents/Data/2022/csv/states/Massachusetts.csv
- Aggregated to Boston neighborhoods (population-weighted RPL_THEMES, plus
  age-65+, no-vehicle households, poverty, uninsured) by
  `scripts/aggregate_svi.py` -> `data/raw/svi/svi_by_boston_neighborhood.csv`

## Analyze Boston boundaries (pulled 2026-09-12)

- Neighborhoods-by-2020-tracts GeoJSON and 2020 census tracts CSV from
  data.boston.gov (resource URLs in the files' notes; datasets
  "Boston Neighborhood Boundaries Approximated by 2020 Census Tracts" and
  "Census Tracts Boston 2020"). Saved under `data/raw/boundaries/`.
- Tract -> neighborhood assignment by point-in-polygon on Census internal
  points (`scripts/aggregate_svi.py`) ->
  `data/raw/boundaries/tract_to_neighborhood.csv` (206 tracts, 24 hoods).

## MBTA (pulled 2026-09-12)

- Fleet: 12 battery-electric buses in service; 80 on order; electrified
  depots North Cambridge (32) and Quincy (2027, 120). Streetsblog MA
  2026-07-06. Notes + service-impact sources (MBTA news pages, Streetsblog,
  Somerville Times, GBH): `data/raw/mbta/fleet_and_service_notes.txt`

## Synthetic fields (by design)

- Grid tie-in capacity per neighborhood: **synthetic** — distribution-level
  interconnection data is not public (stated in README).
- Critical-resident counts: derived estimates from SVI fields, labeled where
  used.
- Bus state-of-charge and route status at storm time: synthetic.
