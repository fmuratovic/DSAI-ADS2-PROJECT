import pandas as pd
import numpy as np
from sklearn.cluster import KMeans

IN_PATH  = "../cache/customers_clustered_final.csv"
OUT_PATH = "../cache/customers_clustered_final1.csv"

MAX_CLUSTER = 40
MIN_CLUSTER = 5
RANDOM_STATE = 0

df = pd.read_csv(IN_PATH)
coords = df[["lat","lon"]].to_numpy()

if "cluster" not in df.columns:
    raise ValueError("Missing 'cluster' column. Run cluster_make.py first.")

cluster_id = df["cluster"].astype(int).to_numpy().copy()
cluster_id.setflags(write=True)
next_cluster = cluster_id.max() + 1

def stats(tag):
    s = df["cluster"].value_counts()
    print(f"\n[{tag}] clusters={s.size} customers={int(s.sum())}")
    print(f"min/mean/max = {int(s.min())}/{s.mean():.2f}/{int(s.max())}")
    print(f"> {MAX_CLUSTER}: {(s>MAX_CLUSTER).sum()}   < {MIN_CLUSTER}: {(s<MIN_CLUSTER).sum()}")
    return s

stats("before split")

# --- Split large clusters ---
sizes = pd.Series(cluster_id).value_counts()
for cid, size in sizes.sort_values(ascending=False).items():
    if size <= MAX_CLUSTER:
        continue

    idx = np.where(cluster_id == cid)[0]
    subcoords = coords[idx]

    if size <= 60:
        parts = 2
    elif size <= 100:
        parts = 3
    else:
        parts = 4

    km = KMeans(n_clusters=parts, random_state=RANDOM_STATE, n_init=10)
    sublabels = km.fit_predict(subcoords)

    for p in range(1, parts):
        new_id = next_cluster
        next_cluster += 1
        cluster_id[idx[sublabels == p]] = new_id

df["cluster"] = cluster_id
stats("after split")

# --- Merge tiny clusters into nearest valid cluster centroid ---
while True:
    s = df["cluster"].value_counts()
    small_ids = s[s < MIN_CLUSTER].index.tolist()
    if not small_ids:
        break

    centroids = df.groupby("cluster")[["lat","lon"]].mean()
    valid_ids = s[s >= MIN_CLUSTER].index.to_numpy()
    valid_cent = centroids.loc[valid_ids].to_numpy()

    for cid in small_ids:
        pts = df.loc[df["cluster"] == cid, ["lat","lon"]].to_numpy()
        if len(pts) == 0:
            continue
        tiny_cent = pts.mean(axis=0, keepdims=True)
        d = ((valid_cent - tiny_cent) ** 2).sum(axis=1)
        nearest = int(valid_ids[int(np.argmin(d))])
        df.loc[df["cluster"] == cid, "cluster"] = nearest

stats("final")

df.to_csv(OUT_PATH, index=False)
print("\nSaved:", OUT_PATH)
