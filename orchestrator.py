"""Runs the three-agent negotiation; supports repeated runs with a summary."""
import argparse
import json
import os

from dotenv import load_dotenv

from agents.emergency_agent import EmergencyAgent
from agents.fleet_agent import FleetAgent
from agents.utility_agent import UtilityAgent

load_dotenv()

MAX_ROUNDS = 4
VERBOSE = True


def load(name: str):
    with open(os.path.join("data", name), encoding="utf-8") as f:
        return json.load(f)


def trace(agent: str, decision: str, reason: str):
    if VERBOSE:
        print(f"  [{agent}] {decision}\n      {reason}")


def dedupe(allocation: dict) -> dict:
    """Deterministic guard: a bus can serve one site only (first assignment wins)."""
    seen, unique = set(), []
    for a in allocation["assignments"]:
        if not isinstance(a, dict) or "bus_id" not in a:
            continue
        if a["bus_id"] not in seen:
            seen.add(a["bus_id"])
            unique.append(a)
    dropped = len(allocation["assignments"]) - len(unique)
    if dropped:
        trace("orchestrator", f"dropped {dropped} duplicate bus assignment(s)", "")
    allocation["assignments"] = unique
    return allocation


def negotiate(emergency, fleet_agent, utility, neighborhoods, fleet, forecast):
    """One full negotiation. Returns (allocation, rounds, approved, rejected_r1)."""
    feedback, allocation, rejected_r1 = None, None, False
    for rnd in range(1, MAX_ROUNDS + 1):
        if VERBOSE:
            print(f"\n=== Round {rnd} ===")

        proposal = emergency.propose(forecast, neighborhoods, feedback)
        zones = ", ".join(z["neighborhood"] for z in proposal["priority_zones"])
        trace(emergency.name, f"proposed priority zones: {zones}", proposal["summary"])

        allocation = dedupe(fleet_agent.allocate(fleet, proposal, feedback))
        trace(fleet_agent.name, f"allocated {len(allocation['assignments'])} buses",
              allocation["summary"])
        for objection in allocation["objections"]:
            trace(fleet_agent.name, "PUSHBACK", objection)

        verdict = utility.validate(allocation, neighborhoods, fleet)
        if verdict["approved"]:
            trace(utility.name, "APPROVED", verdict["summary"])
            return allocation, rnd, True, rejected_r1
        if rnd == 1:
            rejected_r1 = True
        trace(utility.name, "REJECTED", verdict["summary"])
        for r in verdict["rejections"]:
            trace(utility.name, f"limit: {r['neighborhood']} max {r['max_buses']} buses",
                  r["reason"])
        feedback = json.dumps(verdict["rejections"])
    return allocation, MAX_ROUNDS, False, rejected_r1


def build_plan(allocation, neighborhoods, fleet, forecast, rounds):
    hoods = {n["name"]: n for n in neighborhoods}
    buses = {b["id"]: b for b in fleet}
    staging = {}
    for a in allocation["assignments"]:
        bus, hood = buses.get(a["bus_id"]), hoods.get(a["neighborhood"])
        if not bus or not hood:
            continue
        site = staging.setdefault(a["neighborhood"], {
            "neighborhood": hood["name"], "lat": hood["lat"], "lon": hood["lon"],
            "grid_tie_in_kw": hood["grid_tie_in_kw"],
            "critical_residents_covered": hood["critical_residents"],
            "buses": [], "kwh_available": 0,
        })
        site["buses"].append({"id": bus["id"], "state_of_charge": bus["state_of_charge"],
                              "battery_kwh": bus["battery_kwh"]})
        site["kwh_available"] += round(bus["state_of_charge"] * bus["battery_kwh"])
    return {
        "storm": forecast["storm_name"],
        "storm_arrival": forecast["arrival_time"],
        "negotiation_rounds": rounds,
        "total_kwh_staged": sum(s["kwh_available"] for s in staging.values()),
        "total_critical_residents_covered": sum(
            s["critical_residents_covered"] for s in staging.values()),
        "staging": list(staging.values()),
    }


def summarize(results, neighborhoods):
    n = len(results)
    by_vuln = sorted(neighborhoods, reverse=True,
                     key=lambda h: h["social_vulnerability_index"] * h["outage_risk"])
    vuln_rank = {h["name"]: i + 1 for i, h in enumerate(by_vuln)}
    stats = []
    for h in neighborhoods:
        runs = [r["per_hood"].get(h["name"], {"kwh": 0, "covered": 0, "buses": 0})
                for r in results]
        mean_cov = sum(r["covered"] for r in runs) / n
        stats.append({
            "name": h["name"], "vuln": vuln_rank[h["name"]],
            "mean_kwh": sum(r["kwh"] for r in runs) / n, "mean_cov": mean_cov,
            "pct": 100 * mean_cov / h["critical_residents"],
            "zero": sum(1 for r in runs if r["buses"] == 0),
        })
    stats.sort(key=lambda s: s["mean_kwh"], reverse=True)

    print(f"\n=== Summary over {n} runs ===")
    print(f"Approved: {sum(r['approved'] for r in results)}/{n} | "
          f"Utility rejected round 1: {sum(r['rejected_r1'] for r in results)}/{n} | "
          f"mean rounds: {sum(r['rounds'] for r in results) / n:.1f} | "
          f"mean kWh staged: {sum(r['total_kwh'] for r in results) / n:.0f}")
    header = (f"{'Neighborhood':<14}{'VulnRank':>9}{'CovRank':>8}{'MeanKWh':>9}"
              f"{'MeanCov':>9}{'Cov%':>7}{'ZeroBusRuns':>13}")
    print(header)
    print("-" * len(header))
    for i, s in enumerate(stats, 1):
        print(f"{s['name']:<14}{s['vuln']:>9}{i:>8}{s['mean_kwh']:>9.0f}"
              f"{s['mean_cov']:>9.0f}{s['pct']:>6.0f}%{s['zero']:>13}")


def main():
    global VERBOSE
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="number of simulations")
    args = parser.parse_args()
    VERBOSE = args.runs == 1

    neighborhoods, fleet, forecast = (
        load("neighborhoods.json"), load("fleet.json"), load("forecast.json"))
    emergency, fleet_agent, utility = EmergencyAgent(), FleetAgent(), UtilityAgent()
    print(f"Storm: {forecast['storm_name']} arriving {forecast['arrival_time']}")

    results, plan = [], None
    for i in range(args.runs):
        allocation, rounds, approved, rejected_r1 = negotiate(
            emergency, fleet_agent, utility, neighborhoods, fleet, forecast)
        plan = build_plan(allocation, neighborhoods, fleet, forecast, rounds)
        results.append({
            "rounds": rounds, "approved": approved, "rejected_r1": rejected_r1,
            "total_kwh": plan["total_kwh_staged"],
            "per_hood": {s["neighborhood"]: {
                "kwh": s["kwh_available"], "covered": s["critical_residents_covered"],
                "buses": len(s["buses"])} for s in plan["staging"]},
        })
        if args.runs > 1:
            print(f"run {i + 1}/{args.runs}: "
                  f"{'approved' if approved else 'NO APPROVAL'} in {rounds} round(s), "
                  f"{plan['total_kwh_staged']} kWh staged")
        elif not approved:
            print(f"\nNo approval after {MAX_ROUNDS} rounds; writing last allocation.")

    os.makedirs("output", exist_ok=True)
    with open(os.path.join("output", "staging_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    if args.runs > 1:
        summarize(results, neighborhoods)
    else:
        print(f"\nWrote output/staging_plan.json: {plan['total_kwh_staged']} kWh staged "
              f"across {len(plan['staging'])} sites, "
              f"{plan['total_critical_residents_covered']} critical residents covered.")


if __name__ == "__main__":
    main()
