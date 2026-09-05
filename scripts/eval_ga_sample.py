import json
import random
import time
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATRIX_DIR = PROJECT_ROOT / "cache" / "cluster_distance_matrices_osrm"
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
OUT_DIR = PROJECT_ROOT / "cache" / "evaluation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VEHICLE_CAPACITY = 80
MUTATION_RATE = 0.2
N_SEEDS = 10  # how many independent GA runs per cluster, for variance measurement


# ---------------------------------------------------------------
# Core GA machinery (same logic as vrp_solve_clusters.py)
# ---------------------------------------------------------------
def split_routes(chromosome, demands, capacity):
    routes = []
    route = [0]
    load = 0
    for c in chromosome:
        if load + demands[c] <= capacity:
            route.append(c)
            load += demands[c]
        else:
            route.append(0)
            routes.append(route)
            route = [0, c]
            load = demands[c]
    route.append(0)
    routes.append(route)
    return routes


def route_distance(route, dist):
    return sum(dist[route[i]][route[i + 1]] for i in range(len(route) - 1))


def total_distance(routes, dist):
    return sum(route_distance(r, dist) for r in routes)


def fitness(chromosome, demands, capacity, dist):
    return total_distance(split_routes(chromosome, demands, capacity), dist)


def tournament_selection(pop, demands, capacity, dist):
    a, b = random.sample(pop, 2)
    return a if fitness(a, demands, capacity, dist) < fitness(b, demands, capacity, dist) else b


def crossover(p1, p2):
    size = len(p1)
    a, b = sorted(random.sample(range(size), 2))
    child = [-1] * size
    child[a:b] = p1[a:b]
    fill = [x for x in p2 if x not in child]
    idx = 0
    for i in range(size):
        if child[i] == -1:
            child[i] = fill[idx]
            idx += 1
    return child


def mutate(chromosome):
    if random.random() < MUTATION_RATE:
        i, j = random.sample(range(len(chromosome)), 2)
        chromosome[i], chromosome[j] = chromosome[j], chromosome[i]


def two_opt(route, dist):
    improved = True
    best = route[:]
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                new_route = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                if route_distance(new_route, dist) < route_distance(best, dist):
                    best = new_route
                    improved = True
    return best


def run_ga_tracked(n_customers, demands, capacity, dist, pop_size, generations, seed):
    """Same as run_ga, but also returns the best-fitness-per-generation history,
    needed for the convergence plot."""
    random.seed(seed)
    base = list(range(1, n_customers + 1))
    population = []
    for _ in range(pop_size):
        c = base[:]
        random.shuffle(c)
        population.append(c)

    best = min(population, key=lambda c: fitness(c, demands, capacity, dist))
    history = [fitness(best, demands, capacity, dist)]

    for _ in range(generations):
        new_pop = [best]
        while len(new_pop) < pop_size:
            p1 = tournament_selection(population, demands, capacity, dist)
            p2 = tournament_selection(population, demands, capacity, dist)
            child = crossover(p1, p2)
            mutate(child)
            new_pop.append(child)
        population = new_pop
        current_best = min(population, key=lambda c: fitness(c, demands, capacity, dist))
        if fitness(current_best, demands, capacity, dist) < fitness(best, demands, capacity, dist):
            best = current_best
        history.append(fitness(best, demands, capacity, dist))

    return best, history


def nearest_neighbor_baseline(n_customers, dist):
    """Simple greedy baseline: always go to the nearest unvisited customer.
    No capacity awareness here on purpose - split_routes handles capacity
    afterward, same as it does for the GA's output, for a fair comparison."""
    unvisited = set(range(1, n_customers + 1))
    order = []
    current = 0
    while unvisited:
        nxt = min(unvisited, key=lambda j: dist[current][j])
        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    return order


def scaled_ga_params(n):
    pop_size = int(min(60, max(20, n * 3)))
    generations = int(min(400, max(100, n * 10)))
    return pop_size, generations


# ---------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------
def evaluate_cluster(cid, matrix_path, df):
    dist = pd.read_csv(matrix_path).values
    sub = df[(df["cluster"] == cid) & (df["id"] != 0)].reset_index(drop=True)
    n = len(sub)
    if n < 3:
        return None  # too small to be meaningful

    demands = [0] + sub["demand"].tolist()
    pop_size, generations = scaled_ga_params(n)

    print(f"\n[cluster {cid:03d}] n={n} pop_size={pop_size} generations={generations}")

    # --- GA runs across multiple seeds ---
    ga_finals = []
    ga_runtimes = []
    convergence_curves = []

    for seed in range(N_SEEDS):
        t0 = time.time()
        best, history = run_ga_tracked(n, demands, VEHICLE_CAPACITY, dist, pop_size, generations, seed)
        routes = split_routes(best, demands, VEHICLE_CAPACITY)
        routes = [two_opt(r, dist) for r in routes]
        final_dist = total_distance(routes, dist)
        elapsed = time.time() - t0

        ga_finals.append(final_dist)
        ga_runtimes.append(elapsed)
        convergence_curves.append(history)

    # --- Baseline: nearest-neighbor + 2-opt (deterministic, run once) ---
    nn_order = nearest_neighbor_baseline(n, dist)
    nn_routes = split_routes(nn_order, demands, VEHICLE_CAPACITY)
    nn_routes = [two_opt(r, dist) for r in nn_routes]
    nn_dist = total_distance(nn_routes, dist)

    result = {
        "cluster": cid,
        "n_customers": n,
        "ga_mean_km": float(np.mean(ga_finals)),
        "ga_std_km": float(np.std(ga_finals)),
        "ga_best_km": float(np.min(ga_finals)),
        "ga_worst_km": float(np.max(ga_finals)),
        "ga_mean_runtime_s": float(np.mean(ga_runtimes)),
        "nn_baseline_km": float(nn_dist),
        "improvement_over_baseline_pct": round(100 * (nn_dist - np.mean(ga_finals)) / nn_dist, 2),
    }

    # save one representative convergence curve (median run) for plotting later
    median_idx = int(np.argsort(ga_finals)[len(ga_finals) // 2])
    convergence_path = OUT_DIR / f"convergence_cluster_{cid:03d}.csv"
    pd.DataFrame({"generation": range(len(convergence_curves[median_idx])),
                  "best_fitness_km": convergence_curves[median_idx]}).to_csv(convergence_path, index=False)

    return result


def main():
    df = pd.read_csv(CUSTOMERS_PATH)
    matrix_files = sorted(MATRIX_DIR.glob("cluster_*_distance_matrix.csv"))

    # Pick a representative spread: smallest, a couple mid-sized, and the largest cluster,
    # rather than evaluating all 36 (N_SEEDS x 36 clusters would take a while).
    sizes = []
    for f in matrix_files:
        cid = int(f.stem.split("_")[1])
        n = len(df[(df["cluster"] == cid) & (df["id"] != 0)])
        sizes.append((cid, n, f))
    sizes.sort(key=lambda x: x[1])

    picks = [sizes[0], sizes[len(sizes) // 4], sizes[len(sizes) // 2],
             sizes[3 * len(sizes) // 4], sizes[-1]]

    results = []
    for cid, n, f in picks:
        r = evaluate_cluster(cid, f, df)
        if r:
            results.append(r)

    results_df = pd.DataFrame(results)
    results_df.to_csv(OUT_DIR / "ga_evaluation_summary.csv", index=False)

    print("\n=== EVALUATION SUMMARY ===")
    print(results_df.to_string(index=False))
    print(f"\nSaved: {OUT_DIR / 'ga_evaluation_summary.csv'}")
    print(f"Convergence curves saved per cluster in: {OUT_DIR}")


if __name__ == "__main__":
    main()