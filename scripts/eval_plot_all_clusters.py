import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "cache" / "evaluation"
OUT_DIR = EVAL_DIR / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(EVAL_DIR / "ga_evaluation_full.csv")
df_sorted = df.sort_values("n_customers")

# --- Scatter: improvement vs cluster size, all 36 points ---
plt.figure(figsize=(9, 5.5))
colors = ["#22c55e" if v >= 0 else "#ef4444" for v in df_sorted["improvement_over_baseline_pct"]]
plt.scatter(df_sorted["n_customers"], df_sorted["improvement_over_baseline_pct"], c=colors, s=60, alpha=0.8)
plt.axhline(0, color="#94a3b8", linewidth=1, linestyle="--")
plt.xlabel("Cluster size (number of customers)")
plt.ylabel("GA improvement over nearest-neighbor baseline (%)")
plt.title("GA vs. Baseline Across All 36 Clusters")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(OUT_DIR / "improvement_all_clusters_scatter.png", dpi=150)
plt.close()

# --- Histogram of improvement distribution ---
plt.figure(figsize=(8, 5))
plt.hist(df["improvement_over_baseline_pct"], bins=15, color="#2563eb", edgecolor="white")
plt.axvline(df["improvement_over_baseline_pct"].mean(), color="#f97316", linewidth=2,
            label=f"Mean: {df['improvement_over_baseline_pct'].mean():.2f}%")
plt.axvline(df["improvement_over_baseline_pct"].median(), color="#22c55e", linewidth=2,
            label=f"Median: {df['improvement_over_baseline_pct'].median():.2f}%")
plt.xlabel("Improvement over baseline (%)")
plt.ylabel("Number of clusters")
plt.title("Distribution of GA Improvement Across 36 Clusters")
plt.legend()
plt.grid(alpha=0.3, axis="y")
plt.tight_layout()
plt.savefig(OUT_DIR / "improvement_distribution.png", dpi=150)
plt.close()

print("Saved both plots to", OUT_DIR)
print(f"\nClusters where GA underperformed baseline: {(df['improvement_over_baseline_pct'] < 0).sum()} of {len(df)}")
print(f"Clusters with >10% improvement: {(df['improvement_over_baseline_pct'] > 10).sum()} of {len(df)}")