import requests
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
OUT_DIR = PROJECT_ROOT / "cache" / "cluster_distance_matrices_osrm"

OSRM_URL = "http://localhost:5000"
DEPOT_LAT = 43.8563
DEPOT_LON = 18.4131

OUT_DIR.mkdir(parents=True, exist_ok=True)


def osrm_table(coords):
    """coords: list of (lat, lon) tuples, index 0 assumed to be the depot.
    Returns an NxN matrix of real driving distances in km using OSRM's /table endpoint
    (one HTTP call computes the whole matrix at once - much faster than N separate calls)."""
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"{OSRM_URL}/table/v1/driving/{coord_str}?annotations=distance"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM table error: {data.get('code')}")
    distances_m = np.array(data["distances"], dtype=np.float64)
    return distances_m / 1000.0  # meters -> km


df = pd.read_csv(CUSTOMERS_PATH)
clusters = sorted(df["cluster"].unique())
print(f"Total customers: {len(df)}  clusters: {len(clusters)}")

summary = []

for c in clusters:
    sub = df[(df["cluster"] == c) & (df["id"] != 0)].reset_index(drop=True)
    n = len(sub)

    out_path = OUT_DIR / f"cluster_{int(c):03d}_distance_matrix.csv"
    if out_path.exists():
        print(f"[cluster {int(c):03d}] exists -> skip ({n} customers)")
        continue

    print(f"[cluster {int(c):03d}] customers={n} - querying OSRM...")

    coords = [(DEPOT_LAT, DEPOT_LON)] + list(zip(sub["lat"], sub["lon"]))

    try:
        dist = osrm_table(coords)
    except Exception as e:
        print(f"  FAILED: {e}")
        continue

    pd.DataFrame(dist).to_csv(out_path, index=False)
    print(f"  saved -> {out_path}")

    summary.append({"cluster": int(c), "n_customers": n})

pd.DataFrame(summary).to_csv(OUT_DIR / "_cluster_summary.csv", index=False)
print("\nDone.")