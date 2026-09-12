"""Outcome scoring for staging plans. Pure functions, no API calls."""


def gini(values: list) -> float:
    """Gini coefficient across neighborhoods (0 = perfectly equal kWh)."""
    vals = sorted(v for v in values if v >= 0)
    n, total = len(vals), sum(vals)
    if n == 0 or total == 0:
        return 0.0
    cum = sum(i * v for i, v in enumerate(vals, 1))
    return (2 * cum) / (n * total) - (n + 1) / n


def score_plan(plan: dict, neighborhoods: list, fleet: list) -> dict:
    """Score a staging plan against its scenario data.

    Returns:
      covered            critical residents in neighborhoods with staged buses
      kwh_per_critical   staged kWh per covered critical resident
      equity_top2_share  share of staged kWh in the two highest
                         vulnerability-ranked neighborhoods (SVI x outage risk)
      equity_gini        Gini of staged kWh across ALL neighborhoods
      service_stranded   staged buses that were in_service in the scenario data
    """
    by_vuln = sorted(neighborhoods, reverse=True,
                     key=lambda h: h["social_vulnerability_index"] * h["outage_risk"])
    top2 = {h["name"] for h in by_vuln[:2]}
    status = {b["id"]: b["route_status"] for b in fleet}
    site_kwh = {h["name"]: 0 for h in neighborhoods}
    covered = stranded = 0
    for s in plan["staging"]:
        site_kwh[s["neighborhood"]] = s["kwh_available"]
        covered += s["critical_residents_covered"]
        stranded += sum(1 for b in s["buses"] if status.get(b["id"]) == "in_service")
    total = sum(site_kwh.values())
    return {
        "covered": covered,
        "kwh_per_critical": round(total / covered, 2) if covered else 0.0,
        "equity_top2_share": round(sum(site_kwh[h] for h in top2) / total, 3)
        if total else 0.0,
        "equity_gini": round(gini(list(site_kwh.values())), 3),
        "service_stranded": stranded,
    }
