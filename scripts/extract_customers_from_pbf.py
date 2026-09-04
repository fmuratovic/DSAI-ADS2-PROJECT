import random
import pandas as pd
from pyrosm import OSM

PBF_PATH = r"C:\Users\Faris\Downloads\bosnia-herzegovina-260130.osm.pbf"
MAX_CUSTOMERS = 600          # set 300–600
RANDOM_SEED = 42

# Bounds filter (optional):
# If you truly want "whole BiH", leave this as None.
# If you want "more realistic distribution but still mostly Sarajevo",
# set bbox around Sarajevo.
BBOX = None  # example: (18.25, 43.80, 18.50, 43.93)  # (minx, miny, maxx, maxy)

def main():
    random.seed(RANDOM_SEED)

    osm = OSM(PBF_PATH, bounding_box=BBOX)

    # Pyrosm extracts OSM POIs fast
    # This returns a GeoDataFrame with geometry
    print("Extracting shops from PBF...")
    pois = osm.get_pois(custom_filter={"shop": True})

    if pois is None or len(pois) == 0:
        raise RuntimeError("No shop POIs found. Check your PBF path or filter.")

    # Some shops are points, some are polygons. Use representative_point for polygons.
    # representative_point is guaranteed inside geometry (better than centroid for weird shapes)
    geom = pois.geometry
    rep_points = geom.representative_point()

    pois["lat"] = rep_points.y
    pois["lon"] = rep_points.x

    # Clean name
    pois["name"] = pois.get("name", None)
    pois["name"] = pois["name"].fillna("")

    # Sample customers
    pois = pois.sample(n=min(MAX_CUSTOMERS, len(pois)), random_state=RANDOM_SEED).reset_index(drop=True)

    customers = []
    # IMPORTANT: keep index 0 as depot in your pipeline
    # For Bosnia-wide, choose a depot:
    # Option A: fixed Sarajevo depot coordinate
    # Option B: first sampled point as depot (less realistic)
    # Below: Sarajevo-ish depot placeholder (change to your real depot)
    depot = {
        "id": 0,
        "name": "DEPOT",
        "lat": 43.8563,
        "lon": 18.4131,
        "demand": 0,
        "tw_start": 0,
        "tw_end": 24 * 60
    }
    customers.append(depot)

    for i, row in pois.iterrows():
        cid = i + 1  # shift because depot is 0
        customers.append({
            "id": cid,
            "name": row["name"] if row["name"].strip() else f"Shop_{cid}",
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "demand": random.randint(1, 20),
            "tw_start": 8 * 60,
            "tw_end": 18 * 60
        })

    df = pd.DataFrame(customers)
    df.to_csv("customers_bosnia.csv", index=False)
    print(f"customers_bosnia.csv written with {len(df)} rows (incl depot).")

if __name__ == "__main__":
    main()
