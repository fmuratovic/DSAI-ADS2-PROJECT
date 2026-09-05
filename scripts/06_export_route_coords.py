import json
import requests
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
SOLUTION_JSON = PROJECT_ROOT / "cache" / "vrp_solution.json"
OUT_JSON = PROJECT_ROOT / "cache" / "route_coords.json"

OSRM_URL = "http://localhost:5000"
DEPOT_LAT = 43.8563
DEPOT_LON = 18.4131


def osrm_route_coords(stops_latlon):
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in stops_latlon)
    url = f"{OSRM_URL}/route/v1/driving/{coord_str}?overview=full&geometries=geojson"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        print(f"  OSRM route error: {data.get('code')}")
        return []
    coords = data["routes"][0]["geometry"]["coordinates"]
    return [[lat, lon] for lon, lat in coords]


def main():
    df = pd.read_csv(CUSTOMERS_PATH)
    with open(SOLUTION_JSON) as f:
        solution = json.load(f)

    out = {}
    for cluster_result in solution["clusters"]:
        cid = cluster_result["cluster"]
        routes = cluster_result["routes"]
        sub = df[(df["cluster"] == cid) & (df["id"] != 0)].reset_index(drop=True)

        print(f"[cluster {cid:03d}] exporting {len(routes)} route(s)...")

        for v_idx, route in enumerate(routes):
            stop_latlon = [(DEPOT_LAT, DEPOT_LON)]
            for s in route[1:-1]:
                row = sub.iloc[s - 1]
                stop_latlon.append((row["lat"], row["lon"]))
            stop_latlon.append((DEPOT_LAT, DEPOT_LON))

            coords = osrm_route_coords(stop_latlon)
            key = f"{cid}_{v_idx+1}"
            out[key] = coords

    with open(OUT_JSON, "w") as f:
        json.dump(out, f)
    print(f"Saved {len(out)} route paths to {OUT_JSON}")


if __name__ == "__main__":
    main()