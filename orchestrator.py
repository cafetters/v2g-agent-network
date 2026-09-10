"""Runs the three-agent negotiation and writes the final staging plan."""
import json
import os

from dotenv import load_dotenv

from agents.emergency_agent import EmergencyAgent
from agents.fleet_agent import FleetAgent
from agents.utility_agent import UtilityAgent

load_dotenv()

MAX_ROUNDS = 4


def load(name: str):
    with open(os.path.join("data", name), encoding="utf-8") as f:
        return json.load(f)


def trace(agent: str, decision: str, reason: str):
    print(f"  [{agent}] {decision}\n      {reason}")


def dedupe(allocation: dict) -> dict:
    """Deterministic guard: a bus can serve one site only (first assignment wins)."""
    seen, unique = set(), []
    for a in allocation["assignments"]:
        if a["bus_id"] not in seen:
            seen.add(a["bus_id"])
            unique.append(a)
    if len(unique) < len(allocation["assignments"]):
        print(f"  [orchestrator] dropped "
              f"{len(allocation['assignments']) - len(unique)} duplicate bus assignment(s)")
    allocation["assignments"] = unique
    return allocation


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


def main():
    neighborhoods, fleet, forecast = (
        load("neighborhoods.json"), load("fleet.json"), load("forecast.json"))
    emergency, fleet_agent, utility = EmergencyAgent(), FleetAgent(), UtilityAgent()

    print(f"Storm: {forecast['storm_name']} arriving {forecast['arrival_time']}")
    feedback, allocation, verdict, rounds = None, None, None, 0

    for rnd in range(1, MAX_ROUNDS + 1):
        rounds = rnd
        print(f"\n=== Round {rnd} ===")

        proposal = emergency.propose(forecast, neighborhoods, feedback)
        zones = ", ".join(z["neighborhood"] for z in proposal["priority_zones"])
        trace(emergency.name, f"proposed priority zones: {zones}", proposal["summary"])

        allocation = dedupe(fleet_agent.allocate(fleet, proposal, feedback))
        n_buses = len(allocation["assignments"])
        trace(fleet_agent.name, f"allocated {n_buses} buses", allocation["summary"])
        for objection in allocation["objections"]:
            trace(fleet_agent.name, "PUSHBACK", objection)

        verdict = utility.validate(allocation, neighborhoods, fleet)
        if verdict["approved"]:
            trace(utility.name, "APPROVED", verdict["summary"])
            break
        trace(utility.name, "REJECTED", verdict["summary"])
        for r in verdict["rejections"]:
            trace(utility.name, f"limit: {r['neighborhood']} max {r['max_buses']} buses",
                  r["reason"])
        feedback = json.dumps(verdict["rejections"])
    else:
        print(f"\nNo approval after {MAX_ROUNDS} rounds; writing last allocation.")

    plan = build_plan(allocation, neighborhoods, fleet, forecast, rounds)
    os.makedirs("output", exist_ok=True)
    with open(os.path.join("output", "staging_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    print(f"\nWrote output/staging_plan.json: {plan['total_kwh_staged']} kWh staged "
          f"across {len(plan['staging'])} sites, "
          f"{plan['total_critical_residents_covered']} critical residents covered.")


if __name__ == "__main__":
    main()
