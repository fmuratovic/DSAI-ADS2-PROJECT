import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no display needed, just save files
import matplotlib.pyplot as plt
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "cache" / "evaluation"
OUT_DIR = EVAL_DIR / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

summary = pd.read_csv(EVAL_DIR / "ga_evaluation_summary.csv")

# --- Individual convergence plot per cluster ---
convergence_files = sorted(EVAL_DIR.glob("convergence_cluster_*.csv"))

for f in convergence_files:
    cid = int(f.stem.split("_")[-1])
    df = pd.read_csv(f)
    n_customers = int(summary[summary["cluster"] == cid]["n_customers"].iloc[0])

    plt.figure(figsize=(7, 4.5))
    plt.plot(df["generation"], df["best_fitness_km"], color="#2563eb", linewidth=2)
    plt.xlabel("Generation")
    plt.ylabel("Best route distance (km)")
    plt.title(f"GA Convergence - Cluster {cid:03d} ({n_customers} customers)")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    out_path = OUT_DIR / f"convergence_cluster_{cid:03d}.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")

# --- Combined plot: all clusters normalized to see convergence SHAPE together ---
plt.figure(figsize=(8, 5))
colors = ["#ef4444", "#f97316", "#22c55e", "#2563eb", "#a855f7"]

for i, f in enumerate(convergence_files):
    cid = int(f.stem.split("_")[-1])
    df = pd.read_csv(f)
    n_customers = int(summary[summary["cluster"] == cid]["n_customers"].iloc[0])

    # normalize to % of starting distance, so different-scale clusters are comparable on one chart
    normalized = 100 * df["best_fitness_km"] / df["best_fitness_km"].iloc[0]
    plt.plot(df["generation"], normalized, label=f"Cluster {cid:03d} (n={n_customers})",
              color=colors[i % len(colors)], linewidth=2)

plt.xlabel("Generation")
plt.ylabel("Best distance (% of generation-0 starting distance)")
plt.title("GA Convergence Across Cluster Sizes")
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
combined_path = OUT_DIR / "convergence_combined.png"
plt.savefig(combined_path, dpi=150)
plt.close()
print(f"Saved: {combined_path}")

# --- Bar chart: GA vs baseline improvement across cluster sizes ---
plt.figure(figsize=(7, 4.5))
plt.bar(summary["n_customers"].astype(str), summary["improvement_over_baseline_pct"],
        color="#2563eb")
plt.xlabel("Cluster size (number of customers)")
plt.ylabel("GA improvement over nearest-neighbor baseline (%)")
plt.title("GA Advantage Grows With Problem Size")
plt.grid(alpha=0.3, axis="y")
plt.tight_layout()
bar_path = OUT_DIR / "improvement_vs_size.png"
plt.savefig(bar_path, dpi=150)
plt.close()
print(f"Saved: {bar_path}")

print("\nAll plots saved to:", OUT_DIR)