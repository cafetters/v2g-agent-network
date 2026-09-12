# V2G Agent Network

## What this is

Three AI agents from different organizations — city emergency management, the
transit authority, and the electric utility — negotiate where to pre-position
idle electric bus batteries (vehicle-to-grid) near vulnerable Boston
neighborhoods ahead of a storm. Each agent is a role-prompted call to
`claude-sonnet-4-6` with forced tool use, and an orchestrator runs up to four
rounds of propose → allocate → validate until the utility approves a plan.

## What the first run taught me

The negotiation dynamics worked immediately — the utility correctly rejected a
120 kW allocation against East Boston's 100 kW tie-in in round one. What broke
was subtler: when the fleet agent ran out of eligible buses for the
lower-priority zones, it started **inventing bus IDs** (BEB-13 through BEB-21,
which don't exist) and **double-booking real buses** to multiple neighborhoods
rather than admitting it couldn't cover every zone. The plan never converged.

A prompt rule ("one zone per bus, real IDs only, leave zones unserved and say
so") mostly fixed the fleet agent — but on the next run the **utility agent
approved a plan containing a duplicate** it had caught and rejected in earlier
rounds. An LLM validator is a probabilistic check, and it missed the same bug
it had previously flagged.

The durable fix was a deterministic dedupe guard in the orchestrator that
drops repeat bus assignments before validation. The lesson: the constraint
moved from the model into the environment. Prompts shape behavior; code
guarantees invariants.

A later 10-run batch surfaced a third failure in the same family: the fleet
agent broke its own output contract, returning a bare string where its tool
schema required an object. The fix was schema enforcement — `strict: true`
on the tool definitions so the API guarantees conforming output — not
prompting.

A fourth, again under fleet-exhaustion pressure: the fleet agent emitted a
placeholder assignment whose `bus_id` was literally `"Hyde Park"` — a
neighborhood name where a bus ID belongs — and in another run the utility
rejected a plan its own reasoning text said was fine. The orchestrator now
drops unknown bus IDs and neighborhoods deterministically, and the utility's
approve/reject verdict is computed in code from tie-in capacities; the model
supplies reasoning text only, and every model-vs-computed disagreement is
logged.

## Who actually gets protected

My prediction, typed before running the batch:

> East Boston ranks first on vulnerability and lands near the bottom on
> coverage because its tie-in caps it at one bus.

Results over 10 runs (`python orchestrator.py --runs 10`):

```
Approved: 8/10 | Utility rejected round 1: 10/10 | mean rounds: 2.8 | mean kWh staged: 2625

Neighborhood   VulnRank CovRank  MeanKWh  MeanCov   Cov%  ZeroBusRuns
---------------------------------------------------------------------
Dorchester            2       1     1428      260   100%            0
Mattapan              3       2      636      180   100%            0
East Boston           1       3      446      210   100%            0
Roxbury               4       4      115       44    20%            8
Charlestown           6       5        0        0     0%           10
South Boston          7       6        0        0     0%           10
Hyde Park             5       7        0        0     0%           10
Back Bay              8       8        0        0     0%           10
```

The tie-in cap limited East Boston's depth of coverage rather than excluding
it: 2.1 kWh per critical resident versus Dorchester's 5.5. Mid-priority
neighborhoods got nothing because of fleet exhaustion, not grid limits. The
negotiation converged to the same plan in 9 of 10 runs.

### Proposer order comparison (pre-deterministic-verdict)

These runs used the older LLM-gated Utility verdict (before the approve/reject
decision moved into code), so they are not directly comparable to later
results; a like-with-like rerun on the current code is planned. The fleet
half was truncated at 3 of 10 runs when the API credit balance ran out
mid-batch — treat it as suggestive, not conclusive.

```
proposer=emergency (n=10): Approved 10/10 | mean rounds 2.5 | mean kWh 2597
Neighborhood   VulnRank CovRank  MeanKWh  MeanCov   Cov%  ZeroBusRuns
---------------------------------------------------------------------
Dorchester            2       1     1339      260   100%            0
Mattapan              3       2      694      180   100%            0
East Boston           1       3      418      210   100%            0
Roxbury               4       4      146       88    40%            6
Charlestown           6       5        0        0     0%           10
South Boston          7       6        0        0     0%           10
Hyde Park             5       7        0        0     0%           10
Back Bay              8       8        0        0     0%           10

proposer=fleet (n=3, TRUNCATED): Approved 3/3 | mean rounds 2.3 | mean kWh 2465
Neighborhood   VulnRank CovRank  MeanKWh  MeanCov   Cov%  ZeroBusRuns
---------------------------------------------------------------------
Dorchester            2       1      581      260   100%            0
Roxbury               4       2      524      220   100%            0
East Boston           1       3      418      210   100%            0
Mattapan              3       4      357      180   100%            0
Charlestown           6       5      252       60    67%            1
Hyde Park             5       6      230       93    67%            1
South Boston          7       7      103       37    33%            2
Back Bay              8       8        0        0     0%            3
```

The early signal, subject to the small fleet-half sample: fleet-first spreads
coverage wider but shallower — six or seven neighborhoods served instead of
three or four, with Dorchester's depth less than half — while East Boston's
one-bus cap binds identically under both orderings.

### Proposer order comparison (deterministic verdict — current code)

Full 10-and-10 rerun on the current code (20/20 approved, $1.31 total with
prompt caching):

```
proposer=emergency: mean rounds 2.0 | round-1 rejections 10/10 | mean kWh 2597
Neighborhood   VulnRank CovRank  MeanKWh  MeanCov   Cov%  ZeroBusRuns
---------------------------------------------------------------------
Dorchester            2       1     1076      260   100%            0
Mattapan              3       2      682      180   100%            0
Roxbury               4       3      420      220   100%            0
East Boston           1       4      418      210   100%            0
Charlestown           6       5        0        0     0%           10
South Boston          7       6        0        0     0%           10
Hyde Park             5       7        0        0     0%           10
Back Bay              8       8        0        0     0%           10

proposer=fleet: mean rounds 1.2 | round-1 rejections 2/10 | mean kWh 2559
Neighborhood   VulnRank CovRank  MeanKWh  MeanCov   Cov%  ZeroBusRuns
---------------------------------------------------------------------
Dorchester            2       1      814      260   100%            0
Roxbury               4       2      346      220   100%            0
Mattapan              3       3      345      180   100%            0
Charlestown           6       4      344       81    90%            1
East Boston           1       5      340      210   100%            0
Hyde Park             5       6      332      126    90%            1
South Boston          7       7       38       11    10%            9
Back Bay              8       8        0        0     0%           10
```

Scored with `scoring.score_plan()` (mean, min-max over the 10 approved runs
per proposer):

```
                      emergency-first          fleet-first
covered residents     870 (870-870)            1088 (960-1120)
kWh per critical      2.99 (2.99-2.99)         2.35 (2.31-2.36)
top-2 equity share    0.58 (0.47-0.61)         0.45 (0.44-0.51)
kWh Gini              0.61 (0.56-0.64)         0.39 (0.38-0.50)
service stranded      0                        0
```

The scores state the trade-off exactly: fleet-first covers 218 more critical
residents with a much more even spread (Gini 0.39 vs 0.61), while
emergency-first buys depth where vulnerability is highest — 27% more kWh per
critical resident, and 58% of staged energy in the top two vulnerability
ranks versus 45%. Neither ordering strands service. Fleet-first also
converges faster (1.2 rounds vs 2.0) because single-bus spreads are
grid-compliant from the start.

One caveat found in the logs: in 9 of 10 fleet-first runs the utility model
returned `approved: false` while its own per-site analysis found no
violations (its summary field was literally the word "placeholder") — the
computed verdict overrode it every time. Under the old LLM-gated verdict
those runs would have churned, so fleet-first's speed advantage exists
partly because approval is now computed in code.

## How to run it

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install anthropic python-dotenv
# put ANTHROPIC_API_KEY=sk-ant-... in .env
python orchestrator.py
```

The round-by-round trace prints to the console; the final plan is written to
`output/staging_plan.json`.

## Scenarios

Scenario data lives in `scenarios/<name>/`, four files each: `scenario.json`
(name, one-paragraph description, and what the scenario is designed to
stress), `neighborhoods.json`, `fleet.json`, and `forecast.json`. Select one
with `--scenario` (default `baseline-noreaster`); `--runs` and `--proposer`
work with any scenario, and the summary table prints the scenario name.

| Scenario | One change | Stresses |
|---|---|---|
| `baseline-noreaster` | — (original synthetic data) | One weak tie-in (East Boston) vs top vulnerability rank |
| `fleet-scarce` | Half the fleet in maintenance or under 30% charge | Fleet exhaustion: 4 eligible buses for 5+ zones |
| `grid-scarce` | Every tie-in cut to 60 kW (one bus per site) | The capacity cap everywhere; pure breadth allocation |

To add a scenario: create `scenarios/<name>/` with the same four files
(`scenario.json` needs `name`, `description`, `stresses`; the other three
follow the baseline's field layout), then run
`python orchestrator.py --scenario <name> --runs 10`. Change one pressure per
scenario so results stay attributable.

## What we could have done

A backtest against the three real Boston-area winter 2025-26 events from the
NOAA Storm Events Database (episodes 209121, 209918, 208283 — raw rows in
`data/raw/<event>/`), with real neighborhood SVI (CDC SVI 2022 aggregated by
`scripts/aggregate_svi.py`), fleet availability matching reported MBTA
service levels, and outage exposure from news reports — every URL and pull
date in `data/SOURCES.md`. Neighborhood-level outage counts are not public,
so exposure is SVI-allocated and labeled ESTIMATE except where sourced;
critical residents are 0.4% of real population (ESTIMATE); coverage hours
assume 0.3 kW per critical resident (both recorded in each `scenario.json`).
Grid tie-in capacity remains synthetic: distribution-level interconnection
data is not public. Five runs per proposer per event via
`scripts/backtest.py`; all 30 negotiations approved
(`output/backtest_report.json`).

| Event | Neighborhoods that lost power | Emergency-first covered | Fleet-first covered |
|---|---|---|---|
| Jan 25-27 snowstorm | East Boston (sourced) | 181/181, 7.7 h | 181/181, 7.1 h |
| Feb 22-23 blizzard | all 8 (ESTIMATE, 290K out statewide) | 912/1434 | 1337/1434 |
| Dec 19 windstorm | 3 coastal (ESTIMATE) | 145/405 (EB, 7.7 h) | **0/405** |

Three findings, every number traceable to `output/backtest_report.json`:

- **January**: both orderings pre-position a bus in East Boston — the one
  neighborhood with directly sourced outages — giving its estimated 181
  critical residents about 7 hours of coverage before landfall.
- **February**: with everyone exposed, breadth wins — fleet-first covers
  1,337 of 1,434 estimated critical residents versus 912 for
  emergency-first on identical staged energy (2,958 kWh) — though
  emergency-first buys longer coverage where vulnerability is highest
  (Mattapan 20.1 h vs 11.4 h).
- **December**: the failure case. With 6 of 12 buses in weekday service,
  fleet-first staged its few eligible buses in big inland neighborhoods and
  covered zero of the coastal neighborhoods that actually went dark, in all
  five runs; emergency-first reached East Boston in four of five. When the
  fleet is scarce, the vulnerability ranking upstream is what points the
  buses at the right neighborhoods.

## Heat wave: scarcity and stranding

The `boston-heatwave` scenario re-derives vulnerability from real CDC SVI
age-65+ and poverty fields (elderly-without-AC proxy, labeled estimate in
`scenario.json`), which reshuffles the map: Roxbury and Mattapan rank first
and second instead of East Boston. Outage risk is broad and flat (grid load,
not wind), and seven of twelve buses are on midday routes, leaving two
eligible idle buses. Ten runs per proposer, scored:

```
                      emergency-first          fleet-first
covered residents     2530 (2426-3470)         4464 (2426-8308)
kWh per critical      0.34 (0.27-0.38)         0.24 (0.11-0.33)
top-2 equity share    1.00 (1.00-1.00)         0.74 (0.00-1.00)
kWh Gini              0.87 (0.84-0.88)         0.86 (0.80-0.88)
service stranded      0 (0-0)                  0-1 (stranded in 2/10 runs)
```

Three results. First, scarcity swamps everything: with ~840 staged kWh for
thousands of heat-critical residents, depth collapses to a third of a kWh
per person — an order of magnitude below the storm scenarios — so V2G
staging under full daytime service is triage, not coverage. Second,
emergency-first is deterministic under scarcity (both buses to top-ranked
Roxbury, every run) while fleet-first is erratic — sometimes covering 8,300
residents across two sites, twice putting zero energy in the top two
vulnerability ranks. Third, the stranding rule held only when the Fleet
agent worked from a ranking: proposing on its own, it pulled an in-service
bus in two of ten runs — its own hard rule, broken under pressure and caught
by the `service_stranded` score, never by the negotiation itself.

## Architecture (five lines)

1. `scenarios/<name>/` holds JSON per scenario: neighborhoods, fleet, one storm forecast, and a scenario description.
2. Each agent in `agents/` is a class with a role system prompt and one decision tool; `tool_choice` forces a structured response.
3. `orchestrator.py` loops: Emergency proposes -> Fleet allocates -> Utility validates.
4. Rejections are serialized and fed back into the next round's prompts, and a deterministic guard drops duplicate bus assignments.
5. On approval (or round limit) the orchestrator computes kWh and coverage in plain Python and writes `output/staging_plan.json`.

## Known limitations and what I'd build next

- Agents are stateless between rounds; feedback is passed as text, not conversation history. Next: give each agent a running conversation so it remembers its own commitments.
- The utility's capacity arithmetic is done by the model; only the duplicate check is enforced in code. Next: recheck kW-vs-tie-in deterministically and let the model handle judgment calls only.
- No travel time, charging logistics, weather uncertainty, or cost modeling; data is synthetic and small. Next: real MBTA depot locations and a proper dispatch cost function.
- Convergence within 4 rounds is likely but not guaranteed; on failure the last unapproved allocation is written with a warning.

---

Built with Claude Code
