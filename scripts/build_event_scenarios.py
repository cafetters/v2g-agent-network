"""Build backtest scenarios for the three winter 2025-26 events.

Real inputs (data/SOURCES.md): NOAA episode CSVs (storm parameters), CDC SVI
2022 aggregated to neighborhoods (scripts/aggregate_svi.py output), news
outage reports, MBTA fleet facts (12 BEBs in service as of 2026-07).

Labeled estimates / synthetic fields, stated in each scenario.json:
- critical_residents = 0.4% of tract-aggregated population (proxy for home
  dialysis + oxygen-dependent; ESTIMATE)
- outage_risk = event base rate allocated across neighborhoods by SVI weight
  (no neighborhood-level outage data is public; ESTIMATE)
- grid_tie_in_kw = synthetic (distribution interconnection data not public);
  same values as the baseline scenario for comparability
- bus state_of_charge / route_status at storm time = synthetic
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
# per-event: (base outage rate, coastal bump hoods, arrival, wind mph, gust)
EVENTS = {
    "jan26-snowstorm": {
        "name": "January 2026 Snowstorm (backtest)",
        "arrival": "2026-01-25T10:00:00-05:00", "wind": 30, "gust": 45,
        "base_rate": 0.08, "coastal_bump": {"East Boston": 0.25},
        "observed_outages": ["East Boston"],
        "observed_label": "sourced: Axios via search snippet (hundreds out in "
                          "East Boston); statewide outages minimal (WBUR)",
        "description": "Heavy snow Jan 25-27 2026: 18-23 inches in Suffolk "
                       "County, 23.2 at Logan (NOAA episode 209121). Grid "
                       "largely held; brief outages in East Boston. MBTA on "
                       "reduced schedules, Mattapan trolley shuttle-bused.",
        "in_service": ["BEB-07", "BEB-11"], "maintenance": ["BEB-12"],
    },
    "feb26-blizzard": {
        "name": "February 2026 Blizzard (backtest)",
        "arrival": "2026-02-22T20:00:00-05:00", "wind": 45, "gust": 70,
        "base_rate": 0.50, "coastal_bump": {"East Boston": 0.15,
                                            "South Boston": 0.10,
                                            "Charlestown": 0.10},
        "observed_outages": HOODS,
        "observed_label": "ESTIMATE: statewide peak 290,000 out (CBS Boston); "
                          "no neighborhood counts public - exposure allocated "
                          "across all neighborhoods by SVI weight",
        "description": "Blizzard Feb 22-23 2026 (NOAA episode 209918): "
                       "blizzard conditions at Logan, statewide outage peak "
                       "290,000 customers, restoration 3-5 days in hardest-hit "
                       "areas. MBTA on Sunday-level schedules two days.",
        "in_service": ["BEB-07"], "maintenance": ["BEB-12"],
    },
    "dec25-windstorm": {
        "name": "December 2025 Windstorm (backtest)",
        "arrival": "2025-12-19T09:00:00-05:00", "wind": 40, "gust": 64,
        "base_rate": 0.15, "coastal_bump": {"East Boston": 0.10,
                                            "South Boston": 0.05,
                                            "Charlestown": 0.05},
        "observed_outages": ["East Boston", "Charlestown", "South Boston"],
        "observed_label": "ESTIMATE: wind event, gust 64 mph at Logan (NOAA "
                          "episode 208283); coastal exposure assumed, no "
                          "neighborhood outage data found",
        "description": "High wind Dec 19 2025 (NOAA episode 208283): gusts "
                       "50-60 mph, 64 mph at Logan. Minor disruption case; "
                       "transit assumed near-normal (no suspension found).",
        "in_service": ["BEB-02", "BEB-05", "BEB-07", "BEB-09", "BEB-11",
                       "BEB-12"], "maintenance": [],
    },
}
SOC = {"BEB-01": 0.95, "BEB-02": 0.90, "BEB-03": 0.85, "BEB-04": 0.20,
       "BEB-05": 0.92, "BEB-06": 0.88, "BEB-07": 0.80, "BEB-08": 0.15,
       "BEB-09": 0.90, "BEB-10": 0.87, "BEB-11": 0.82, "BEB-12": 0.60}
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

    for scen_id, ev in EVENTS.items():
        hoods_out = []
        for h in HOODS:
            row = svi[h]
            pop = int(row["population"])
            svi_val = float(row["svi_popweighted"])
            risk = min(round(ev["base_rate"] * (0.6 + svi_val)
                             + ev["coastal_bump"].get(h, 0), 2), 0.95)
            lat, lon = LATLON[h]
            hoods_out.append({
                "name": h, "lat": lat, "lon": lon,
                "outage_risk": risk,
                "social_vulnerability_index": svi_val,
                "critical_residents": round(pop * 0.004),
                "grid_tie_in_kw": TIE_IN[h],
            })
        fleet = []
        for bus, soc in SOC.items():
            status = ("in_service" if bus in ev["in_service"] else
                      "maintenance" if bus in ev["maintenance"] else "idle")
            fleet.append({"id": bus, "depot": "North Cambridge",
                          "state_of_charge": soc, "battery_kwh": KWH[bus],
                          "v2g_export_kw": 60, "route_status": status})
        forecast = {
            "storm_name": ev["name"], "arrival_time": ev["arrival"],
            "sustained_wind_mph": ev["wind"], "gust_mph": ev["gust"],
            "expected_outage_probability": {
                h["name"]: h["outage_risk"] for h in hoods_out},
        }
        meta = {
            "name": ev["name"], "description": ev["description"],
            "stresses": "Backtest against the real event; see data/SOURCES.md",
            "backtest": {
                "observed_outage_neighborhoods": ev["observed_outages"],
                "observed_outage_label": ev["observed_label"],
                "critical_load_kw_per_resident": 0.3,
                "estimates": "critical_residents = 0.4% of population "
                             "(ESTIMATE); outage_risk SVI-allocated "
                             "(ESTIMATE); tie-ins + SoC/status SYNTHETIC",
            },
        }
        d = os.path.join(ROOT, "scenarios", scen_id)
        os.makedirs(d, exist_ok=True)
        for fname, obj in (("scenario.json", meta),
                           ("neighborhoods.json", hoods_out),
                           ("fleet.json", fleet), ("forecast.json", forecast)):
            with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2)
        print(f"{scen_id}: risks " + ", ".join(
            f"{h['name']} {h['outage_risk']}" for h in hoods_out[:4]) + " ...")


if __name__ == "__main__":
    main()
