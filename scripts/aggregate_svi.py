"""Aggregate CDC SVI 2022 tract data to Boston neighborhoods.

Inputs (see data/SOURCES.md for URLs and pull dates):
  data/raw/svi/svi2022_massachusetts_tracts.csv          CDC/ATSDR SVI 2022
  data/raw/boundaries/census_tracts_boston_2020.csv      Analyze Boston tracts
  data/raw/boundaries/boston_neighborhoods_by_2020_tracts.geojson

Method: each Boston tract's Census internal point is assigned to the
neighborhood polygon containing it (ray-casting, pure python). SVI fields are
aggregated population-weighted. Outputs:
  data/raw/boundaries/tract_to_neighborhood.csv
  data/raw/svi/svi_by_boston_neighborhood.csv
"""
import csv
import json
import os

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def point_in_ring(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            if lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def point_in_geom(lon, lat, geom):
    polys = geom["coordinates"]
    if geom["type"] == "Polygon":
        polys = [polys]
    for poly in polys:
        if point_in_ring(lon, lat, poly[0]) and not any(
                point_in_ring(lon, lat, hole) for hole in poly[1:]):
            return True
    return False


def main():
    with open(os.path.join(RAW, "boundaries",
                           "boston_neighborhoods_by_2020_tracts.geojson"),
              encoding="utf-8") as f:
        hoods = [(feat["properties"]["neighborhood"], feat["geometry"])
                 for feat in json.load(f)["features"]]

    assignments = {}
    with open(os.path.join(RAW, "boundaries", "census_tracts_boston_2020.csv"),
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            lon, lat = float(r["intptlon20"]), float(r["intptlat20"])
            for name, geom in hoods:
                if point_in_geom(lon, lat, geom):
                    assignments[r["geoid20"]] = name
                    break

    with open(os.path.join(RAW, "boundaries", "tract_to_neighborhood.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["geoid20", "neighborhood"])
        for g, n in sorted(assignments.items()):
            w.writerow([g, n])

    # population-weighted aggregation of SVI fields per neighborhood
    fields = ["E_TOTPOP", "E_AGE65", "E_NOVEH", "E_POV150", "E_UNINSUR"]
    agg = {}
    with open(os.path.join(RAW, "svi", "svi2022_massachusetts_tracts.csv"),
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            hood = assignments.get(r["FIPS"])
            if not hood:
                continue
            a = agg.setdefault(hood, {k: 0.0 for k in fields}
                               | {"svi_weighted": 0.0, "tracts": 0})
            pop = max(float(r["E_TOTPOP"]), 0)
            svi = float(r["RPL_THEMES"])
            if svi >= 0:  # -999 = not ranked
                a["svi_weighted"] += svi * pop
            for k in fields:
                v = float(r[k])
                a[k] += v if v >= 0 else 0
            a["tracts"] += 1

    out = os.path.join(RAW, "svi", "svi_by_boston_neighborhood.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["neighborhood", "tracts", "population", "svi_popweighted",
                    "age65", "no_vehicle_hh", "pov150", "uninsured"])
        for hood in sorted(agg):
            a = agg[hood]
            w.writerow([hood, a["tracts"], int(a["E_TOTPOP"]),
                        round(a["svi_weighted"] / a["E_TOTPOP"], 3)
                        if a["E_TOTPOP"] else "",
                        int(a["E_AGE65"]), int(a["E_NOVEH"]),
                        int(a["E_POV150"]), int(a["E_UNINSUR"])])
    print(f"assigned {len(assignments)} tracts to {len(agg)} neighborhoods")
    print("wrote", out)


if __name__ == "__main__":
    main()
