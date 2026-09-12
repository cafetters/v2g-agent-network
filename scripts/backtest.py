"""Backtest mode: run negotiations against the real-event scenarios.

For each event and each proposer, runs N negotiations, then reports via
score_plan(): how many critical residents in neighborhoods that actually lost
power (per scenario.json backtest metadata) would have had staged battery
capacity nearby, and for how many hours given the staged kWh at the assumed
critical load (kW per resident, from scenario.json). Writes
output/backtest_report.json.

Usage: python scripts/backtest.py [--runs-per-proposer 5]
"""
import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(ROOT))
os.chdir(os.path.abspath(ROOT))

import orchestrator  # noqa: E402
from agents.emergency_agent import EmergencyAgent  # noqa: E402
from agents.fleet_agent import FleetAgent  # noqa: E402
from agents.utility_agent import UtilityAgent  # noqa: E402

EVENTS = ["jan26-snowstorm", "feb26-blizzard", "dec25-windstorm"]


def backtest_event(scenario, runs_per_proposer, stamp):
    meta = orchestrator.load(scenario, "scenario.json")
    data = (orchestrator.load(scenario, "neighborhoods.json"),
            orchestrator.load(scenario, "fleet.json"),
            orchestrator.load(scenario, "forecast.json"))
    observed = set(meta["backtest"]["observed_outage_neighborhoods"])
    load_kw = meta["backtest"]["critical_load_kw_per_resident"]
    crit = {h["name"]: h["critical_residents"] for h in data[0]}
    event_report = {"scenario": scenario, "name": meta["name"],
                    "observed_outage_neighborhoods": sorted(observed),
                    "observed_outage_label":
                        meta["backtest"]["observed_outage_label"],
                    "critical_load_kw_per_resident": load_kw, "proposers": {}}

    for proposer in ("emergency", "fleet"):
        agents = (EmergencyAgent(data[2], data[0]), FleetAgent(data[1]),
                  UtilityAgent(data[0], data[1]))
        results, _ = orchestrator.run_batch(
            runs_per_proposer, proposer, agents, data, stamp, scenario)
        approved = [r for r in results if r["approved"]]
        per_run = []
        for r in approved:
            cov_res = kwh = 0
            hood_hours = {}
            for hood, info in r["per_hood"].items():
                if hood in observed and info["buses"] > 0:
                    cov_res += crit[hood]
                    kwh += info["kwh"]
                    hood_hours[hood] = round(
                        info["kwh"] / (crit[hood] * load_kw), 1)
            per_run.append({"covered_in_observed": cov_res,
                            "kwh_in_observed": kwh,
                            "hours_by_neighborhood": hood_hours,
                            "scores": r["scores"]})
        n = len(per_run)
        mean = lambda key: round(sum(p[key] for p in per_run) / n, 1) if n else 0
        event_report["proposers"][proposer] = {
            "runs": runs_per_proposer, "approved": n,
            "mean_covered_in_observed": mean("covered_in_observed"),
            "mean_kwh_in_observed": mean("kwh_in_observed"),
            "total_critical_in_observed": sum(crit[h] for h in observed),
            "per_run": per_run,
        }
        print(f"[{scenario}/{proposer}] approved {n}/{runs_per_proposer}, "
              f"mean covered-in-observed "
              f"{event_report['proposers'][proposer]['mean_covered_in_observed']}"
              f"/{event_report['proposers'][proposer]['total_critical_in_observed']}, "
              f"mean kWh in observed {mean('kwh_in_observed')}")
    return event_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-per-proposer", type=int, default=5)
    args = parser.parse_args()
    orchestrator.VERBOSE = False
    os.makedirs("logs", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = {"generated": stamp,
              "runs_per_proposer": args.runs_per_proposer, "events": []}
    for scenario in EVENTS:
        print(f"\n=== {scenario} ===")
        report["events"].append(
            backtest_event(scenario, args.runs_per_proposer, stamp))
    with open(os.path.join("output", "backtest_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("\nwrote output/backtest_report.json")


if __name__ == "__main__":
    main()
