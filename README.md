## Setup & How to Run

This project requires raw OpenStreetMap data and a local OSRM routing server, neither of which are included in this repository (too large for git). Follow these steps in order on a fresh clone.

### 1. Prerequisites

- Python 3.12+ with a virtual environment
- Docker
- `osmium-tool` (`sudo apt install osmium-tool` on Ubuntu/Debian)

### 2. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Download raw map data

Download the Bosnia and Herzegovina extract from Geofabrik:
```bash
mkdir -p data
wget -O data/bosnia.osm.pbf https://download.geofabrik.de/europe/bosnia-herzegovina-latest.osm.pbf
```

Extract a roads-only subset (used by earlier pipeline stages / reference):
```bash
osmium tags-filter data/bosnia.osm.pbf w/highway -o data/bosnia_roads_only.osm.pbf
```

### 4. Set up the OSRM routing server (Docker)

This preprocesses the road network once and serves real driving-distance/routing queries locally — no API key, no internet dependency after setup.

```bash
mkdir -p osrm/bih
cp data/bosnia.osm.pbf osrm/bih/bosnia-latest.osm.pbf
cd osrm/bih

docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-extract -p /opt/car.lua /data/bosnia-latest.osm.pbf
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-partition /data/bosnia-latest.osrm
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-customize /data/bosnia-latest.osrm

docker run -d --name osrm-server -p 5000:5000 -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-routed --algorithm mld /data/bosnia-latest.osrm
cd ../..
```

Verify it's running:
```bash
curl "http://localhost:5000/route/v1/driving/18.4131,43.8563;17.9036,44.1830?overview=false"
```
You should get back a JSON response with `"code":"Ok"`.

**The OSRM server must be running (`docker ps` should show `osrm-server` as `Up`) before running any of the routing/distance-matrix scripts below.** If your machine restarts, restart the container with:
```bash
docker start osrm-server
```

### 5. Run the pipeline, in order

```bash
cd scripts

# Extract customer (shop) locations from OSM data
python3 extract_customers_from_pbf.py

# Cluster customers into manageable regional groups
python3 cluster_make.py
python3 cluster_refine.py

# Compute real driving-distance matrices per cluster via OSRM
python3 build_cluster_distance_matrices_osrm.py

# Solve each cluster's vehicle routing problem with a Genetic Algorithm
python3 vrp_solve_clusters.py

# Export real road-following route geometry for visualization
python3 export_route_coords_osrm.py

# Generate the interactive route map
python3 vrp_routes_clustered_osrm.py

# Generate fleet inspection data (vehicles, fuel, cost, timing estimates)
python3 enrich_fleet_data.py

# Generate the combined map + dashboard
python3 generate_combined_dashboard.py
```

### 6. View the results

```bash
xdg-open ../apps/fleet_map_dashboard.html    # combined map + fleet table
xdg-open ../apps/vrp_routes_osrm.html         # standalone route map
```

### Architecture overview
