import osmnx as ox
import pandas as pd
import random

OSM_FILE = "bugojno.osm"
MAX_CUSTOMERS = 300

print("Loading OSM file...")
G = ox.graph_from_xml(OSM_FILE)

print("Extracting shops...")
gdf = ox.features_from_xml(
    OSM_FILE,
    tags={"shop": True}
)

gdf = gdf[["name", "geometry"]].dropna()
gdf["lat"] = gdf.geometry.centroid.y
gdf["lon"] = gdf.geometry.centroid.x

gdf = gdf.sample(
    n=min(MAX_CUSTOMERS, len(gdf)),
    random_state=42
).reset_index(drop=True)

customers = []
for i, row in gdf.iterrows():
    customers.append({
        "id": i,
        "name": row["name"] if row["name"] else f"Shop_{i}",
        "lat": row["lat"],
        "lon": row["lon"],
        "demand": random.randint(1, 20),
        "tw_start": 8 * 60,
        "tw_end": 18 * 60
    })

df = pd.DataFrame(customers)
df.to_csv("customers.csv", index=False)

print("customers.csv created successfully")
