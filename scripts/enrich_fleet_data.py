import json
import random
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOLUTION_JSON = PROJECT_ROOT / "cache" / "vrp_solution.json"
MATRIX_DIR = PROJECT_ROOT / "cache" / "cluster_distance_matrices_osrm"
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
OUT_JSON = PROJECT_ROOT / "cache" / "fleet_dashboard_data.json"

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ---------------------------------------------------------------
# ASSUMPTIONS - all fictional/estimated, clearly labeled for the report.
# With OSRM, real driving distance per route is known exactly; average
# speed is still an assumption used only to estimate driving TIME.
# ---------------------------------------------------------------
AVERAGE_SPEED_KMH = 55    # blended estimate across highway + local roads
SERVICE_TIME_PER_STOP_MIN = 10   # loading/unloading time per customer
WORKDAY_HOURS = 9         # after this, a vehicle needs an overnight stay
DEPARTURE_TIME = "07:00"

FUEL_PRICE_PER_LITER_BAM = 2.35   # Bosnian Convertible Mark, approx diesel price
DRIVER_WAGE_PER_HOUR_BAM = 8.0
CO2_KG_PER_LITER_DIESEL = 2.68

VEHICLE_TYPES = [
    {"mark": "Fiat Ducato",       "capacity": 100, "consumption_l_100km": 8.5},
    {"mark": "Renault Master",    "capacity": 110, "consumption_l_100km": 8.8},
    {"mark": "Ford Transit",      "capacity": 115, "consumption_l_100km": 9.2},
    {"mark": "Mercedes Sprinter", "capacity": 120, "consumption_l_100km": 9.5},
    {"mark": "VW Crafter",        "capacity": 130, "consumption_l_100km": 9.0},
    {"mark": "Iveco Daily",       "capacity": 150, "consumption_l_100km": 10.5},
    {"mark": "MAN TGL",           "capacity": 400, "consumption_l_100km": 18.0},
    {"mark": "DAF LF",            "capacity": 450, "consumption_l_100km": 19.5},
]

CANTON_LETTERS = "ABCDEFGHJKLMNPTZ"  # stylized, not an official plate spec

used_plates = set()


def generate_plate():
    while True:
        plate = f"{random.randint(100,999)}-{random.choice(CANTON_LETTERS)}-{random.randint(100,999)}"
        if plate not in used_plates:
            used_plates.add(plate)
            return plate


def pick_vehicle(load_demand):
    eligible = [v for v in VEHICLE_TYPES if v["capacity"] >= load_demand]
    if not eligible:
        eligible = [max(VEHICLE_TYPES, key=lambda v: v["capacity"])]  # fallback: biggest available
    return random.choice(eligible)


def main():
    with open(SOLUTION_JSON) as f:
        solution = json.load(f)

    df_customers = pd.read_csv(CUSTOMERS_PATH)

    vehicles = []

    for cluster_result in solution["clusters"]:
        cid = cluster_result["cluster"]
        routes = cluster_result["routes"]
        customer_ids = cluster_result["customer_ids"]

        matrix_path = MATRIX_DIR / f"cluster_{cid:03d}_distance_matrix.csv"
        if not matrix_path.exists():
            print(f"[cluster {cid:03d}] SKIP - no OSRM distance matrix found")
            continue
        dist_matrix = pd.read_csv(matrix_path).values

        sub = df_customers[(df_customers["cluster"] == cid) & (df_customers["id"] != 0)]
        demand_lookup = dict(zip(range(1, len(customer_ids) + 1), sub["demand"].tolist()))

        for v_idx, route in enumerate(routes):
            stops = route[1:-1]  # exclude depot at both ends
            n_stops = len(stops)
            total_demand = sum(demand_lookup.get(s, 0) for s in stops)

            # Real driving distance, summed directly from the OSRM matrix - no more
            # artificial backbone/local split or per-cluster averaging.
            route_km = sum(
                dist_matrix[route[i]][route[i + 1]] for i in range(len(route) - 1)
            )

            vehicle = pick_vehicle(total_demand)

            driving_time_h = route_km / AVERAGE_SPEED_KMH
            service_time_h = (n_stops * SERVICE_TIME_PER_STOP_MIN) / 60.0
            total_time_h = driving_time_h + service_time_h

            fuel_liters = route_km * vehicle["consumption_l_100km"] / 100.0
            fuel_cost_bam = fuel_liters * FUEL_PRICE_PER_LITER_BAM
            wage_cost_bam = total_time_h * DRIVER_WAGE_PER_HOUR_BAM
            total_cost_bam = fuel_cost_bam + wage_cost_bam

            co2_kg = fuel_liters * CO2_KG_PER_LITER_DIESEL

            load_utilization_pct = round(100 * total_demand / vehicle["capacity"], 1)
            needs_overnight = bool(total_time_h > WORKDAY_HOURS)

            dep = datetime.strptime(DEPARTURE_TIME, "%H:%M")
            ret = dep + timedelta(hours=total_time_h)
            return_str = ret.strftime("%H:%M") if ret.day == dep.day else f"+1 day {ret.strftime('%H:%M')}"

            vehicles.append({
                "plate": generate_plate(),
                "mark": vehicle["mark"],
                "capacity": vehicle["capacity"],
                "cluster": cid,
                "vehicle_number_in_cluster": v_idx + 1,
                "n_customers": n_stops,
                "total_demand": total_demand,
                "load_utilization_pct": load_utilization_pct,
                "route_distance_km": round(route_km, 2),
                "driving_time_hours": round(driving_time_h, 2),
                "service_time_hours": round(service_time_h, 2),
                "total_time_hours": round(total_time_h, 2),
                "fuel_liters": round(fuel_liters, 2),
                "fuel_cost_bam": round(fuel_cost_bam, 2),
                "wage_cost_bam": round(wage_cost_bam, 2),
                "total_cost_bam": round(total_cost_bam, 2),
                "co2_kg": round(co2_kg, 2),
                "needs_overnight": needs_overnight,
                "departure_time": DEPARTURE_TIME,
                "estimated_return": return_str,
            })

    with open(OUT_JSON, "w") as f:
        json.dump({"vehicles": vehicles, "generated_assumptions": {
            "average_speed_kmh": AVERAGE_SPEED_KMH,
            "service_time_per_stop_min": SERVICE_TIME_PER_STOP_MIN,
            "workday_hours": WORKDAY_HOURS,
            "fuel_price_per_liter_bam": FUEL_PRICE_PER_LITER_BAM,
            "driver_wage_per_hour_bam": DRIVER_WAGE_PER_HOUR_BAM,
        }}, f, indent=2)

    print(f"Generated fleet data for {len(vehicles)} vehicles.")
    print(f"Total distance: {sum(v['route_distance_km'] for v in vehicles):,.1f} km")
    print(f"Total fuel: {sum(v['fuel_liters'] for v in vehicles):.1f} L")
    print(f"Total cost: {sum(v['total_cost_bam'] for v in vehicles):.2f} BAM")
    print(f"Vehicles needing overnight stay: {sum(v['needs_overnight'] for v in vehicles)}")
    print(f"Saved: {OUT_JSON}")


if __name__ == "__main__":
    main()