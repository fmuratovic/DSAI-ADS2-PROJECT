import json
import requests
import folium
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
SOLUTION_JSON = PROJECT_ROOT / "cache" / "vrp_solution.json"
OUT_HTML = PROJECT_ROOT / "apps" / "vrp_routes_osrm.html"

OSRM_URL = "http://localhost:5000"
DEPOT_LAT = 43.8563
DEPOT_LON = 18.4131

COLOR_PALETTE = [
    "red", "blue", "green", "purple", "orange", "darkred", "cadetblue",
    "darkgreen", "darkblue", "deeppink", "crimson", "indigo", "chocolate",
]


def osrm_route_coords(stops_latlon):
    """stops_latlon: ordered list of (lat, lon) the vehicle actually visits,
    starting and ending at the depot. Returns the real road-following
    coordinate list for the whole multi-stop route in one OSRM call."""
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in stops_latlon)
    url = f"{OSRM_URL}/route/v1/driving/{coord_str}?overview=full&geometries=geojson"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        print(f"  OSRM route error: {data.get('code')}")
        return []
    coords = data["routes"][0]["geometry"]["coordinates"]
    return [(lat, lon) for lon, lat in coords]  # geojson is [lon,lat] - flip for folium


def main():
    df = pd.read_csv(CUSTOMERS_PATH)
    with open(SOLUTION_JSON) as f:
        solution = json.load(f)

    m = folium.Map(
        location=[44.2, 17.8], zoom_start=8,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
    )
    folium.Marker([DEPOT_LAT, DEPOT_LON], popup="Depot (Sarajevo)",
                  icon=folium.Icon(color="black", icon="home")).add_to(m)

    for idx, cluster_result in enumerate(solution["clusters"]):
        cid = cluster_result["cluster"]
        routes = cluster_result["routes"]
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]

        sub = df[(df["cluster"] == cid) & (df["id"] != 0)].reset_index(drop=True)
        n = len(sub)
        print(f"[cluster {cid:03d}] drawing {len(routes)} route(s), {n} customers...")

        for v_idx, route in enumerate(routes):
            stop_latlon = [(DEPOT_LAT, DEPOT_LON)]
            for s in route[1:-1]:
                row = sub.iloc[s - 1]
                stop_latlon.append((row["lat"], row["lon"]))
            stop_latlon.append((DEPOT_LAT, DEPOT_LON))

            coords = osrm_route_coords(stop_latlon)
            if coords:
                folium.PolyLine(coords, color=color, weight=3, opacity=0.7,
                                 tooltip=f"Cluster {cid} - Vehicle {v_idx+1} ({len(route)-2} stops)").add_to(m)

        for i in range(n):
            folium.CircleMarker(
                [sub.loc[i, "lat"], sub.loc[i, "lon"]], radius=3, color=color,
                fill=True, fill_opacity=0.9,
                popup=f"Customer {sub.loc[i,'id']} ({sub.loc[i,'name']}) - cluster {cid}",
            ).add_to(m)

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(OUT_HTML))
    print(f"\nSaved map: {OUT_HTML}")


if __name__ == "__main__":
    main()