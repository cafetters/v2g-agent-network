"""Offline invariant tests for guards, verdict math, and scoring. No API.

Run: python scripts/selfcheck.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator import apply_guards, compute_violations  # noqa: E402
from scoring import gini, score_plan  # noqa: E402

HOODS = [
    {"name": "A", "grid_tie_in_kw": 100, "social_vulnerability_index": 0.9,
     "outage_risk": 0.9, "critical_residents": 100},
    {"name": "B", "grid_tie_in_kw": 300, "social_vulnerability_index": 0.5,
     "outage_risk": 0.5, "critical_residents": 200},
    {"name": "C", "grid_tie_in_kw": 60, "social_vulnerability_index": 0.1,
     "outage_risk": 0.1, "critical_residents": 50},
]
FLEET = [
    {"id": "X1", "v2g_export_kw": 60, "state_of_charge": 1.0,
     "battery_kwh": 400, "route_status": "idle"},
    {"id": "X2", "v2g_export_kw": 60, "state_of_charge": 0.5,
     "battery_kwh": 400, "route_status": "in_service"},
    {"id": "X3", "v2g_export_kw": 60, "state_of_charge": 0.8,
     "battery_kwh": 400, "route_status": "idle"},
]
BUSES = {b["id"] for b in FLEET}
NAMES = {h["name"] for h in HOODS}


def check_guards():
    alloc = {"assignments": [
        {"bus_id": "X1", "neighborhood": "A", "reason": "r"},
        {"bus_id": "X1", "neighborhood": "B", "reason": "duplicate"},
        {"bus_id": "GHOST", "neighborhood": "A", "reason": "phantom bus"},
        {"bus_id": "X2", "neighborhood": "Narnia", "reason": "phantom hood"},
        "not even a dict",
        {"bus_id": "X2", "neighborhood": "B", "reason": "ok"},
        {"bus_id": "X3", "neighborhood": "B", "reason": "over cap"},
    ]}
    alloc, guards = apply_guards(alloc, {"B": 1}, BUSES, NAMES)
    kept = [(a["bus_id"], a["neighborhood"]) for a in alloc["assignments"]]
    assert kept == [("X1", "A"), ("X2", "B")], kept
    types = sorted(g["type"] for g in guards)
    assert types == ["cap_enforced", "duplicate_dropped", "malformed_dropped",
                     "unknown_dropped", "unknown_dropped"], types


def check_verdict():
    ok = {"assignments": [{"bus_id": "X1", "neighborhood": "A"}]}
    assert compute_violations(ok, HOODS, FLEET) == []
    over = {"assignments": [{"bus_id": "X1", "neighborhood": "A"},
                            {"bus_id": "X3", "neighborhood": "A"}]}
    v = compute_violations(over, HOODS, FLEET)
    assert len(v) == 1 and v[0]["neighborhood"] == "A", v
    assert v[0]["load_kw"] == 120 and v[0]["cap_kw"] == 100
    assert v[0]["max_buses"] == 1


def check_scoring():
    assert gini([]) == 0.0 and gini([5, 5, 5]) == 0.0
    assert gini([0, 0, 0, 12]) > 0.7  # concentrated -> high inequality
    plan = {"staging": [
        {"neighborhood": "A", "critical_residents_covered": 100,
         "kwh_available": 400, "buses": [{"id": "X1"}]},
        {"neighborhood": "B", "critical_residents_covered": 200,
         "kwh_available": 200, "buses": [{"id": "X2"}]},
    ]}
    s = score_plan(plan, HOODS, FLEET)
    assert s["covered"] == 300
    assert s["kwh_per_critical"] == 2.0  # 600 kWh / 300 residents
    # top-2 by SVI x risk = A, B -> all staged kWh is in the top 2
    assert s["equity_top2_share"] == 1.0
    assert s["service_stranded"] == 1  # X2 is in_service
    empty = score_plan({"staging": []}, HOODS, FLEET)
    assert empty["covered"] == 0 and empty["kwh_per_critical"] == 0.0
    assert empty["equity_top2_share"] == 0.0 and empty["equity_gini"] == 0.0


if __name__ == "__main__":
    check_guards()
    check_verdict()
    check_scoring()
    print("selfcheck: all invariants hold")
