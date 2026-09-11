"""Runs the three-agent negotiation; supports batches, JSONL traces, and replay."""
import argparse
import json
import os
from datetime import datetime
from itertools import zip_longest

from dotenv import load_dotenv

load_dotenv()

MAX_ROUNDS = 4
VERBOSE = True


def load(name: str):
    with open(os.path.join("data", name), encoding="utf-8") as f:
        return json.load(f)


def trace(agent: str, decision: str, reason: str):
    if VERBOSE:
        print(f"  [{agent}] {decision}\n      {reason}")


class RunLog:
    """One JSONL file per run; one line per agent decision or guard event."""

    def __init__(self, path: str, run_id: str):
        self.run_id = run_id
        self.f = open(path, "w", encoding="utf-8")

    def event(self, rnd, agent, decision, reason,
              tool_input=None, tool_output=None, guard=None):
        self.f.write(json.dumps({
            "run_id": self.run_id, "round": rnd, "agent": agent,
            "decision": decision, "reason": reason,
            "tool_input": tool_input, "tool_output": tool_output, "guard": guard,
        }) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def emit(log, rnd, agent, decision, reason,
         tool_input=None, tool_output=None, guard=None):
    trace(agent, decision, reason)
    log.event(rnd, agent, decision, reason, tool_input, tool_output, guard)


def apply_guards(allocation: dict, caps: dict,
                 valid_buses: set, valid_hoods: set) -> tuple[dict, list]:
    """Deterministic guards: drop bad entries, enforce site caps."""
    guards, seen, unique = [], set(), []
    for a in allocation["assignments"]:
        if not isinstance(a, dict) or "bus_id" not in a or "neighborhood" not in a:
            guards.append({"type": "malformed_dropped", "entry": str(a)[:80]})
            continue
        if a["bus_id"] not in valid_buses or a["neighborhood"] not in valid_hoods:
            guards.append({"type": "unknown_dropped", "bus_id": a["bus_id"],
                           "neighborhood": a["neighborhood"]})
            continue
        if a["bus_id"] in seen:
            guards.append({"type": "duplicate_dropped", "bus_id": a["bus_id"],
                           "neighborhood": a["neighborhood"]})
            continue
        seen.add(a["bus_id"])
        unique.append(a)
    kept, counts = [], {}
    for a in unique:
        hood = a["neighborhood"]
        counts[hood] = counts.get(hood, 0) + 1
        if hood in caps and counts[hood] > caps[hood]:
            guards.append({"type": "cap_enforced", "bus_id": a["bus_id"],
                           "neighborhood": hood, "cap": caps[hood]})
            continue
        kept.append(a)
    allocation["assignments"] = kept
    return allocation, guards


def compute_violations(allocation: dict, neighborhoods: list, fleet: list) -> list:
    """Ground-truth capacity check: summed export kW per site vs grid tie-in."""
    export = {b["id"]: b["v2g_export_kw"] for b in fleet}
    ties = {h["name"]: h["grid_tie_in_kw"] for h in neighborhoods}
    load = {}
    for a in allocation["assignments"]:
        load[a["neighborhood"]] = load.get(a["neighborhood"], 0) + export[a["bus_id"]]
    rate = max(export.values())
    return [{"neighborhood": h, "load_kw": kw, "cap_kw": ties[h],
             "max_buses": ties[h] // rate}
            for h, kw in load.items() if kw > ties[h]]


def negotiate(agents, data, proposer, log):
    """One full negotiation.

    Returns (allocation, rounds, approved, rejected_r1, last_verdict,
    verdict_disagreements). The approve/reject decision is computed in code;
    the Utility model supplies reasoning text only.
    """
    emergency, fleet_agent, utility = agents
    neighborhoods, fleet, forecast = data
    fleet_view = [{k: v for k, v in h.items() if k != "grid_tie_in_kw"}
                  for h in neighborhoods]
    valid_buses = {b["id"] for b in fleet}
    valid_hoods = {h["name"] for h in neighborhoods}
    feedback, allocation, last, rejected_r1 = None, None, None, False
    reject_count, forced_caps, disagreements = {}, {}, 0

    for rnd in range(1, MAX_ROUNDS + 1):
        if VERBOSE:
            print(f"\n=== Round {rnd} ===")

        if proposer == "emergency":
            proposal = emergency.propose(forecast, neighborhoods, feedback)
            zones = ", ".join(z["neighborhood"] for z in proposal["priority_zones"])
            emit(log, rnd, emergency.name, f"proposed priority zones: {zones}",
                 proposal["summary"], {"feedback": feedback}, proposal)
            allocation = fleet_agent.allocate(fleet, proposal, feedback)
        else:  # fleet proposes first; Emergency reviews afterwards
            context = {"forecast": forecast, "neighborhoods": fleet_view}
            allocation = fleet_agent.allocate(fleet, context, feedback)

        allocation, guards = apply_guards(allocation, forced_caps,
                                          valid_buses, valid_hoods)
        emit(log, rnd, fleet_agent.name,
             f"allocated {len(allocation['assignments'])} buses",
             allocation["summary"], {"feedback": feedback}, allocation)
        for objection in allocation["objections"]:
            emit(log, rnd, fleet_agent.name, "PUSHBACK", objection)
        for g in guards:
            emit(log, rnd, "orchestrator", f"guard fired: {g['type']}",
                 json.dumps(g), guard=g)

        review = None
        if proposer == "fleet":
            review = emergency.propose(forecast, neighborhoods, json.dumps({
                "fleet_allocation": allocation["assignments"],
                "utility_rejections": (last or {}).get("rejections", []),
            }))
            zones = ", ".join(z["neighborhood"] for z in review["priority_zones"])
            emit(log, rnd, emergency.name,
                 f"reviewed allocation; vulnerability ranking: {zones}",
                 review["summary"], {"allocation": allocation["assignments"]}, review)

        verdict = utility.validate(allocation, neighborhoods, fleet)
        violations = compute_violations(allocation, neighborhoods, fleet)
        approved = not violations
        if approved != verdict["approved"]:
            disagreements += 1
            emit(log, rnd, "orchestrator",
                 f"verdict override: model said "
                 f"{'approve' if verdict['approved'] else 'reject'}, "
                 f"code computed {'approve' if approved else 'reject'}",
                 verdict["summary"],
                 guard={"type": "verdict_disagreement",
                        "model_approved": verdict["approved"],
                        "computed_approved": approved, "violations": violations})
        if approved:
            emit(log, rnd, utility.name, "APPROVED (computed)", verdict["summary"],
                 {"allocation": allocation["assignments"]}, verdict)
            return (allocation, rnd, True, rejected_r1,
                    {"summary": verdict["summary"], "rejections": []}, disagreements)
        if rnd == 1:
            rejected_r1 = True
        rejections = [
            {"neighborhood": v["neighborhood"], "max_buses": v["max_buses"],
             "reason": f"{v['load_kw']} kW allocated exceeds "
                       f"{v['cap_kw']} kW tie-in"}
            for v in violations]
        last = {"summary": verdict["summary"], "rejections": rejections}
        emit(log, rnd, utility.name, "REJECTED (computed)", verdict["summary"],
             {"allocation": allocation["assignments"]}, verdict)
        for r in rejections:
            emit(log, rnd, utility.name,
                 f"limit: {r['neighborhood']} max {r['max_buses']} buses", r["reason"])
            hood = r["neighborhood"]
            reject_count[hood] = reject_count.get(hood, 0) + 1
            if reject_count[hood] >= 2 and hood not in forced_caps:
                forced_caps[hood] = max(r["max_buses"], 0)
                emit(log, rnd, "orchestrator",
                     f"fallback: capping {hood} at {forced_caps[hood]} bus(es)",
                     "Fleet failed twice on this constraint; cap now applied in "
                     "code before validation",
                     guard={"type": "cap_armed", "neighborhood": hood,
                            "cap": forced_caps[hood]})
        feedback = json.dumps({
            "rejections": rejections,
            "emergency_review": review,
            "orchestrator_enforced_caps": forced_caps,
            "note": "Caps in orchestrator_enforced_caps are applied automatically "
                    "before validation. Do not exceed them; only fill the "
                    "remaining capacity elsewhere with remaining eligible buses.",
        })
    return allocation, MAX_ROUNDS, False, rejected_r1, last, disagreements


def build_plan(allocation, neighborhoods, fleet, forecast, rounds, status,
               last_rejection=None):
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
    plan = {
        "status": status,
        "storm": forecast["storm_name"],
        "storm_arrival": forecast["arrival_time"],
        "negotiation_rounds": rounds,
        "total_kwh_staged": sum(s["kwh_available"] for s in staging.values()),
        "total_critical_residents_covered": sum(
            s["critical_residents_covered"] for s in staging.values()),
        "staging": list(staging.values()),
    }
    if last_rejection:
        plan["last_rejection"] = last_rejection
    return plan


def summarize_lines(results, neighborhoods, title):
    n = len(results)
    approved = [r for r in results if r["approved"]]
    n_app = len(approved)
    lines = [f"=== {title}: summary over {n} runs ===",
             f"Approved: {n_app}/{n} | Unapproved: {n - n_app}/{n} "
             f"(excluded from coverage stats)",
             f"Utility rejected round 1: {sum(r['rejected_r1'] for r in results)}/{n} "
             f"| mean rounds: {sum(r['rounds'] for r in results) / n:.1f} "
             f"| mean kWh (approved): "
             + (f"{sum(r['total_kwh'] for r in approved) / n_app:.0f}"
                if n_app else "n/a"),
             f"verdict disagreements (model vs computed): "
             f"{sum(r.get('verdict_disagreements', 0) for r in results)}"]
    if not n_app:
        lines.append("No approved runs; skipping per-neighborhood table.")
        return lines
    by_vuln = sorted(neighborhoods, reverse=True,
                     key=lambda h: h["social_vulnerability_index"] * h["outage_risk"])
    vuln_rank = {h["name"]: i + 1 for i, h in enumerate(by_vuln)}
    stats = []
    for h in neighborhoods:
        runs = [r["per_hood"].get(h["name"], {"kwh": 0, "covered": 0, "buses": 0})
                for r in approved]
        mean_cov = sum(r["covered"] for r in runs) / n_app
        stats.append({
            "name": h["name"], "vuln": vuln_rank[h["name"]],
            "mean_kwh": sum(r["kwh"] for r in runs) / n_app, "mean_cov": mean_cov,
            "pct": 100 * mean_cov / h["critical_residents"],
            "zero": sum(1 for r in runs if r["buses"] == 0),
        })
    stats.sort(key=lambda s: s["mean_kwh"], reverse=True)
    header = (f"{'Neighborhood':<14}{'VulnRank':>9}{'CovRank':>8}{'MeanKWh':>9}"
              f"{'MeanCov':>9}{'Cov%':>7}{'ZeroBusRuns':>13}")
    lines += [header, "-" * len(header)]
    for i, s in enumerate(stats, 1):
        lines.append(f"{s['name']:<14}{s['vuln']:>9}{i:>8}{s['mean_kwh']:>9.0f}"
                     f"{s['mean_cov']:>9.0f}{s['pct']:>6.0f}%{s['zero']:>13}")
    return lines


def replay(path: str):
    last_run = last_round = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e["run_id"] != last_run:
                print(f"--- run {e['run_id']} ---")
                last_run, last_round = e["run_id"], None
            if e["round"] != last_round:
                print(f"\n=== Round {e['round']} ===")
                last_round = e["round"]
            print(f"  [{e['agent']}] {e['decision']}\n      {e['reason']}")


def run_batch(runs, proposer, agents, data, stamp):
    neighborhoods, fleet, forecast = data
    results, plan = [], None
    for i in range(runs):
        run_id = f"{stamp}-{proposer}-run{i + 1:02d}"
        log = RunLog(os.path.join("logs", run_id + ".jsonl"), run_id)
        try:
            (allocation, rounds, approved, rejected_r1, verdict,
             disagreements) = negotiate(agents, data, proposer, log)
        finally:
            log.close()
        plan = build_plan(
            allocation, neighborhoods, fleet, forecast, rounds,
            "approved" if approved else "unapproved",
            None if approved else verdict)
        results.append({
            "rounds": rounds, "approved": approved, "rejected_r1": rejected_r1,
            "verdict_disagreements": disagreements,
            "total_kwh": plan["total_kwh_staged"],
            "per_hood": {s["neighborhood"]: {
                "kwh": s["kwh_available"], "covered": s["critical_residents_covered"],
                "buses": len(s["buses"])} for s in plan["staging"]},
        })
        if runs > 1 or not VERBOSE:
            print(f"[{proposer}] run {i + 1}/{runs}: "
                  f"{'approved' if approved else 'UNAPPROVED'} in {rounds} round(s), "
                  f"{plan['total_kwh_staged']} kWh staged, "
                  f"{disagreements} verdict disagreement(s)")
        elif not approved:
            print(f"\nNo approval after {MAX_ROUNDS} rounds; writing plan "
                  f"with status=unapproved and the last rejection attached.")
    return results, plan


def main():
    global VERBOSE
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="number of simulations")
    parser.add_argument("--proposer", choices=["emergency", "fleet", "both"],
                        default="emergency", help="which agent proposes first")
    parser.add_argument("--replay", metavar="LOGFILE",
                        help="print a run's trace from a JSONL log; no API calls")
    args = parser.parse_args()

    if args.replay:
        replay(args.replay)
        return

    from agents.emergency_agent import EmergencyAgent
    from agents.fleet_agent import FleetAgent
    from agents.utility_agent import UtilityAgent

    VERBOSE = args.runs == 1 and args.proposer != "both"
    data = (load("neighborhoods.json"), load("fleet.json"), load("forecast.json"))
    agents = (EmergencyAgent(), FleetAgent(), UtilityAgent())
    os.makedirs("logs", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"Storm: {data[2]['storm_name']} arriving {data[2]['arrival_time']}")

    if args.proposer == "both":
        res_e, _ = run_batch(args.runs, "emergency", agents, data, stamp)
        res_f, plan = run_batch(args.runs, "fleet", agents, data, stamp)
        print()
        left = summarize_lines(res_e, data[0], "proposer=emergency")
        right = summarize_lines(res_f, data[0], "proposer=fleet")
        width = max(len(l) for l in left) + 2
        for l, r in zip_longest(left, right, fillvalue=""):
            print(f"{l:<{width}}| {r}")
    else:
        results, plan = run_batch(args.runs, args.proposer, agents, data, stamp)
        if args.runs > 1:
            print()
            print("\n".join(summarize_lines(results, data[0],
                                            f"proposer={args.proposer}")))

    with open(os.path.join("output", "staging_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    if args.runs == 1 and args.proposer != "both":
        print(f"\nWrote output/staging_plan.json ({plan['status']}): "
              f"{plan['total_kwh_staged']} kWh staged across "
              f"{len(plan['staging'])} sites, "
              f"{plan['total_critical_residents_covered']} critical residents covered.")


if __name__ == "__main__":
    main()
