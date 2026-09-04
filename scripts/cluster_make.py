import pandas as pd
from sklearn.cluster import KMeans
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = PROJECT_ROOT / "cache" / "customers.csv"
OUT_PATH = PROJECT_ROOT / "cache" / "customers_clustered.csv"

df = pd.read_csv(IN_PATH)

# Choose k based on target size
n = len(df)
target_cluster_size = 25  # aim 20-35
k = max(20, min(60, n // target_cluster_size))  # for 600 -> 24, capped 20-60
print(f"customers={n}  chosen_k={k}")

coords = df[["lat", "lon"]].to_numpy()
df["cluster"] = KMeans(n_clusters=k, random_state=0, n_init=10).fit_predict(coords)

sizes = df["cluster"].value_counts()
print("clusters:", sizes.size)
print("min/mean/max:", int(sizes.min()), round(sizes.mean(), 2), int(sizes.max()))
print("too_big(>40):", int((sizes > 40).sum()), " too_small(<5):", int((sizes < 5).sum()))

df.to_csv(OUT_PATH, index=False)
print("Saved:", OUT_PATH)
