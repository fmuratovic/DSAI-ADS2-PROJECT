import json
import random
import time
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
MATRIX_DIR = PROJECT_ROOT / "cache" / "cluster_distance_matrices_osrm"
OUT_JSON = PROJECT_ROOT / "cache" / "vrp_solution.json"

VEHICLE_CAPACITY = 250
MUTATION_RATE = 0.2
RANDOM_SEED = 42

random.seed(RANDOM_SEED)

df_all = pd.read_csv(CUSTOMERS_PATH)


def scaled_ga_params(n):
    """Bigger clusters get a bigger population/more generations; tiny ones run fast."""
    pop_size = int(min(60, max(20, n * 3)))
    generations = int(min(400, max(100, n * 10)))
    return pop_size, generations


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
    routes = split_routes(chromosome, demands, capacity)
    return total_distance(routes, dist)


def tournament_selection(pop, demands, capacity, dist):
    a, b = random.sample(pop, 2)
    fa = fitness(a, demands, capacity, dist)
    fb = fitness(b, demands, capacity, dist)
    return a if fa < fb else b


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


def run_ga(n_customers, demands, capacity, dist):
    pop_size, generations = scaled_ga_params(n_customers)
    base = list(range(1, n_customers + 1))

    population = []
    for _ in range(pop_size):
        c = base[:]
        random.shuffle(c)
        population.append(c)

    best = min(population, key=lambda c: fitness(c, demands, capacity, dist))

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

    return split_routes(best, demands, capacity)


def two_opt(route, dist):
    """Polish a single route (depot...depot) by reversing segments that shorten it."""
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


def solve_cluster(cluster_id):
    matrix_path = MATRIX_DIR / f"cluster_{cluster_id:03d}_distance_matrix.csv"
    if not matrix_path.exists():
        return None

    dist = pd.read_csv(matrix_path).values
    sub = df_all[(df_all["cluster"] == cluster_id) & (df_all["id"] != 0)].reset_index(drop=True)
    n = len(sub)
    demands = [0] + sub["demand"].tolist()

    t0 = time.time()
    routes = run_ga(n, demands, VEHICLE_CAPACITY, dist)
    routes = [two_opt(r, dist) for r in routes]
    elapsed = time.time() - t0

    return {
        "cluster": cluster_id,
        "n_customers": n,
        "n_vehicles": len(routes),
        "total_distance_km": round(total_distance(routes, dist), 2),
        "runtime_seconds": round(elapsed, 2),
        "routes": routes,  # local indices: 0 = depot, 1..n = this cluster's customers in matrix order
        "customer_ids": sub["id"].tolist(),  # maps local index (1..n) -> original customer id
    }


def main():
    matrix_files = sorted(MATRIX_DIR.glob("cluster_*_distance_matrix.csv"))
    cluster_ids = [int(f.stem.split("_")[1]) for f in matrix_files]

    results = []
    for cid in cluster_ids:
        print(f"Solving cluster {cid:03d}...")
        r = solve_cluster(cid)
        if r:
            print(f"  vehicles={r['n_vehicles']}  distance={r['total_distance_km']}km  "
                  f"time={r['runtime_seconds']}s")
            results.append(r)

    grand_total_km = sum(r["total_distance_km"] for r in results)
    grand_total_vehicles = sum(r["n_vehicles"] for r in results)

    with open(OUT_JSON, "w") as f:
        json.dump({
            "clusters": results,
            "grand_total_distance_km": round(grand_total_km, 2),
            "grand_total_vehicles": grand_total_vehicles,
        }, f, indent=2)

    print(f"\nDone. {len(results)} clusters solved.")
    print(f"Grand total distance: {grand_total_km:.2f} km")
    print(f"Grand total vehicles used: {grand_total_vehicles}")
    print(f"Saved: {OUT_JSON}")


if __name__ == "__main__":
    main()