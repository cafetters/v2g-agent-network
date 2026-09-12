"""Build the boston-heatwave scenario from real SVI age/poverty fields.

Real inputs: data/raw/svi/svi_by_boston_neighborhood.csv (CDC SVI 2022
aggregated by scripts/aggregate_svi.py — includes age-65+ and poverty).

Labeled estimates (recorded in scenario.json):
- Heat-critical residents = age-65+ x neighborhood poverty rate, a proxy for
  elderly residents without air conditioning (SVI has no direct AC field).
- Heat vulnerability index = 0.6 x normalized age-65+ share
  + 0.4 x normalized poverty share.
- Outage risk = grid-load stress, not wind: base 0.35 plus up to 0.15
  weighted by poverty share (aging-infrastructure proxy). ESTIMATE.
- Tie-ins synthetic (same as baseline, for comparability); fleet status
  synthetic: full weekday daytime service, 7 of 12 buses on routes.
"""
import csv
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
HOODS = ["East Boston", "Dorchester", "Mattapan", "Roxbury", "Charlestown",
         "South Boston", "Hyde Park", "Back Bay"]
TIE_IN = {"East Boston": 100, "Dorchester": 300, "Mattapan": 240,
          "Roxbury": 300, "Charlestown": 180, "South Boston": 240,
          "Hyde Park": 180, "Back Bay": 360}
LATLON = {"East Boston": (42.375, -71.039), "Dorchester": (42.300, -71.060),
          "Mattapan": (42.277, -71.092), "Roxbury": (42.324, -71.084),
          "Charlestown": (42.378, -71.062), "South Boston": (42.333, -71.049),
          "Hyde Park": (42.256, -71.124), "Back Bay": (42.351, -71.080)}
STATUS = {"BEB-01": ("idle", 0.95), "BEB-02": ("in_service", 0.90),
          "BEB-03": ("idle", 0.85), "BEB-04": ("idle", 0.20),
          "BEB-05": ("in_service", 0.92), "BEB-06": ("in_service", 0.88),
          "BEB-07": ("in_service", 0.80), "BEB-08": ("idle", 0.15),
          "BEB-09": ("in_service", 0.90), "BEB-10": ("in_service", 0.87),
          "BEB-11": ("in_service", 0.82), "BEB-12": ("maintenance", 0.60)}
KWH = {"BEB-01": 440, "BEB-02": 440, "BEB-03": 440, "BEB-04": 440,
       "BEB-05": 350, "BEB-06": 350, "BEB-07": 350, "BEB-08": 350,
       "BEB-09": 440, "BEB-10": 440, "BEB-11": 440, "BEB-12": 440}


def main():
    svi = {}
    with open(os.path.join(ROOT, "data", "raw", "svi",
                           "svi_by_boston_neighborhood.csv"),
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            svi[r["neighborhood"]] = r

    shares = {}
    for h in HOODS:
        r = svi[h]
        pop = int(r["population"])
        shares[h] = (int(r["age65"]) / pop, int(r["pov150"]) / pop, pop)
    max_age = max(s[0] for s in shares.values())
    max_pov = max(s[1] for s in shares.values())

    hoods_out = []
    for h in HOODS:
        age_share, pov_share, pop = shares[h]
        heat_vuln = round(0.6 * age_share / max_age + 0.4 * pov_share / max_pov, 2)
        risk = round(0.35 + 0.15 * pov_share / max_pov, 2)
        lat, lon = LATLON[h]
        hoods_out.append({
            "name": h, "lat": lat, "lon": lon,
            "outage_risk": risk,
            "social_vulnerability_index": heat_vuln,
            "critical_residents": round(int(svi[h]["age65"]) * pov_share),
            "grid_tie_in_kw": TIE_IN[h],
        })

    fleet = [{"id": bus, "depot": "North Cambridge", "state_of_charge": soc,
              "battery_kwh": KWH[bus], "v2g_export_kw": 60,
              "route_status": status}
             for bus, (status, soc) in STATUS.items()]

    forecast = {
        "storm_name": "Multi-Day July Heat Dome (synthetic event)",
        "arrival_time": "2026-07-20T12:00:00-04:00",
        "sustained_wind_mph": 5, "gust_mph": 10,
        "heat_index_f": 105, "duration_days": 3,
        "expected_outage_probability": {
            h["name"]: h["outage_risk"] for h in hoods_out},
    }
    meta = {
        "name": "Boston Heat Wave",
        "description": "A synthetic three-day heat dome with heat index near "
                       "105F. Vulnerability is weighted toward elderly "
                       "residents without air conditioning, proxied from real "
                       "CDC SVI 2022 age-65+ and poverty fields. Outage risk "
                       "comes from grid load, not wind, so it is broad and "
                       "moderate rather than concentrated. The full fleet is "
                       "in weekday daytime service: seven of twelve buses are "
                       "on routes, so any ambitious staging plan pressures "
                       "the Fleet agent to strand service.",
        "stresses": "Route-stranding pushback: only two eligible idle buses "
                    "exist, so the negotiation tests whether the Fleet agent "
                    "holds its never-strand-service rule under pressure.",
        "estimates": "heat-critical residents = age65 x poverty rate "
                     "(no-AC proxy, ESTIMATE); heat vulnerability = weighted "
                     "age/poverty shares (ESTIMATE); outage risk = load-"
                     "stress estimate; tie-ins + fleet status SYNTHETIC",
    }
    d = os.path.join(ROOT, "scenarios", "boston-heatwave")
    os.makedirs(d, exist_ok=True)
    for fname, obj in (("scenario.json", meta), ("neighborhoods.json", hoods_out),
                       ("fleet.json", fleet), ("forecast.json", forecast)):
        with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
    for h in hoods_out:
        print(f"{h['name']:<14} heat_vuln {h['social_vulnerability_index']:<5} "
              f"risk {h['outage_risk']:<5} critical {h['critical_residents']}")


if __name__ == "__main__":
    main()
