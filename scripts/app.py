from flask import Flask, jsonify, request, Response
import pandas as pd
import requests
import webbrowser
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
OSRM_URL = "http://localhost:5000"
DEPOT_LAT = 43.8563
DEPOT_LON = 18.4131
DEFAULT_CAPACITY = 80
DEFAULT_MAX_KM = 150

app = Flask(__name__)

df = pd.read_csv(CUSTOMERS_PATH)
df = df[df["id"] != 0].reset_index(drop=True)
CUSTOMERS = df.to_dict("records")
CUSTOMERS_BY_ID = {int(c["id"]): c for c in CUSTOMERS}


def osrm_table(coords):
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"{OSRM_URL}/table/v1/driving/{coord_str}?annotations=distance"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("code"))
    return data["distances"]


def osrm_route(coords):
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"{OSRM_URL}/route/v1/driving/{coord_str}?overview=full&geometries=geojson"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("code"))
    route = data["routes"][0]
    coords_geo = route["geometry"]["coordinates"]
    latlon = [[lat, lon] for lon, lat in coords_geo]
    return latlon, route["distance"] / 1000.0, route["duration"] / 60.0


def nearest_neighbor_order(dist, n):
    unvisited = set(range(1, n + 1))
    order = [0]
    current = 0
    while unvisited:
        nxt = min(unvisited, key=lambda j: dist[current][j])
        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    order.append(0)
    return order


def route_len(order, dist):
    return sum(dist[order[i]][order[i + 1]] for i in range(len(order) - 1))


def two_opt(order, dist):
    improved = True
    best = order[:]
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                new_order = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                if route_len(new_order, dist) < route_len(best, dist):
                    best = new_order
                    improved = True
    return best


def split_by_capacity_and_distance(order, demands, dist, capacity, max_route_km=150):
    """Splits the visiting order into multiple vehicle routes whenever EITHER
    the cumulative demand exceeds capacity OR the projected round-trip distance
    (current route so far + next leg + estimated return to depot) exceeds
    max_route_km. This prevents both overloaded vehicles and unrealistic
    country-spanning single routes when demand alone wouldn't force a split."""
    routes = []
    current = [0]
    load = 0
    current_km = 0.0
    prev = 0

    for idx in order[1:-1]:
        d = demands[idx]
        leg_km = dist[prev][idx] / 1000.0
        projected_km = current_km + leg_km + (dist[idx][0] / 1000.0)

        if load + d > capacity or projected_km > max_route_km:
            current.append(0)
            routes.append(current)
            current = [0, idx]
            load = d
            current_km = dist[0][idx] / 1000.0
        else:
            current.append(idx)
            load += d
            current_km += leg_km
        prev = idx

    current.append(0)
    routes.append(current)
    return routes


@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


@app.route("/api/customers")
def api_customers():
    return jsonify(CUSTOMERS)


@app.route("/api/plan_route", methods=["POST"])
def api_plan_route():
    body = request.get_json()
    customer_ids = body.get("customer_ids", [])
    capacity = int(body.get("capacity", DEFAULT_CAPACITY))
    max_route_km = int(body.get("max_route_km", DEFAULT_MAX_KM))

    if not customer_ids:
        return jsonify({"error": "No customers selected"}), 400

    selected = [CUSTOMERS_BY_ID[int(cid)] for cid in customer_ids if int(cid) in CUSTOMERS_BY_ID]
    if not selected:
        return jsonify({"error": "No valid customers found"}), 400

    coords = [(DEPOT_LAT, DEPOT_LON)] + [(c["lat"], c["lon"]) for c in selected]
    demands = [0] + [c["demand"] for c in selected]

    try:
        dist = osrm_table(coords)
    except Exception as e:
        return jsonify({"error": f"OSRM table failed: {e}"}), 500

    n = len(selected)
    order = nearest_neighbor_order(dist, n)
    order = two_opt(order, dist)
    sub_routes = split_by_capacity_and_distance(order, demands, dist, capacity, max_route_km)

    results = []
    for v_idx, route in enumerate(sub_routes):
        route_coords = [coords[i] for i in route]
        try:
            geometry, distance_km, duration_min = osrm_route(route_coords)
        except Exception as e:
            return jsonify({"error": f"OSRM route failed: {e}"}), 500

        stops = [selected[i - 1] for i in route[1:-1]]
        results.append({
            "vehicle": v_idx + 1,
            "stops": [
                {"id": int(s["id"]), "name": s["name"], "lat": s["lat"], "lon": s["lon"], "demand": int(s["demand"])}
                for s in stops
            ],
            "total_demand": int(sum(s["demand"] for s in stops)),
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 1),
            "geometry": geometry,
        })

    return jsonify({"routes": results, "depot": [DEPOT_LAT, DEPOT_LON]})


INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Ad-hoc Route Planner</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    background: #0f172a; color: #e2e8f0;
    display: flex; flex-direction: column;
  }
  h1 { font-size: 18px; margin: 14px 16px 4px; }
  .subtitle { color: #94a3b8; font-size: 12px; margin: 0 16px 12px; }
  .main { display: flex; flex: 1; min-height: 0; padding: 0 16px 16px; gap: 12px; }
  .left { flex: 0 0 340px; display: flex; flex-direction: column; min-height: 0; gap: 10px; }
  .right { flex: 1; min-height: 0; border-radius: 10px; overflow: hidden; border: 1px solid #334155; }
  #map { width: 100%; height: 100%; }

  .panel { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px; }
  input, select, button {
    background: #0f172a; border: 1px solid #334155; color: #e2e8f0;
    padding: 7px 9px; border-radius: 6px; font-size: 12px; width: 100%;
  }
  label { display: block; font-size: 11px; color: #94a3b8; margin-top: 6px; }
  button { cursor: pointer; font-weight: 600; margin-top: 8px; }
  button.primary { background: #2563eb; border-color: #2563eb; }
  button.primary:hover { background: #1d4ed8; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }

  .list-wrap { flex: 1; overflow: auto; background: #1e293b; border: 1px solid #334155; border-radius: 8px; }
  .cust-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid #263449; font-size: 12px; cursor: pointer; }
  .cust-row:hover { background: #263449; }
  .cust-row.selected { background: #1e3a5f; }
  .cust-row .name { flex: 1; }
  .cust-row .demand { color: #94a3b8; font-size: 11px; }

  .summary { font-size: 12px; color: #94a3b8; }
  .summary b { color: #e2e8f0; }

  .results { font-size: 12px; }
  .vehicle-card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
  .vehicle-card .title { font-weight: 600; margin-bottom: 4px; }
  .vehicle-card .stops { color: #94a3b8; font-size: 11px; }

  .error { color: #f87171; font-size: 12px; }
</style>
</head>
<body>

<h1>Ad-hoc Route Planner</h1>
<div class="subtitle">Select customers below or click their markers on the map, then plan a route.</div>

<div class="main">
  <div class="left">
    <div class="panel">
      <input type="text" id="search" placeholder="Search customer name/id...">
    </div>
    <div class="list-wrap" id="custList"></div>
    <div class="panel summary" id="selSummary">0 customers selected</div>
    <div class="panel">
      <label>Vehicle capacity</label>
      <input type="number" id="capacity" value="80">
      <label>Max distance per vehicle (km)</label>
      <input type="number" id="maxKm" value="150">
      <button class="primary" id="planBtn">Plan Route</button>
      <button id="clearBtn">Clear Selection</button>
    </div>
    <div class="list-wrap results" id="results" style="flex: 0 0 auto; max-height: 220px;"></div>
  </div>
  <div class="right"><div id="map"></div></div>
</div>

<script>
let customers = [];
let selected = new Set();
let markers = {};
let routeLayers = [];

const map = L.map('map').setView([44.2, 17.8], 8);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Esri'
}).addTo(map);

const DEPOT = [43.8563, 18.4131];
L.marker(DEPOT, {title: "Depot"}).addTo(map).bindPopup("Depot (Sarajevo)");

function markerStyle(isSelected) {
  return { radius: 5, color: isSelected ? "#facc15" : "#38bdf8", fillOpacity: 0.9, weight: isSelected ? 3 : 1 };
}

function toggleSelect(id) {
  if (selected.has(id)) selected.delete(id); else selected.add(id);
  markers[id].setStyle(markerStyle(selected.has(id)));
  renderList();
  updateSummary();
}

function renderList() {
  const q = document.getElementById("search").value.toLowerCase();
  const wrap = document.getElementById("custList");
  const list = customers.filter(c =>
    !q || c.name.toLowerCase().includes(q) || String(c.id).includes(q)
  );
  wrap.innerHTML = list.map(c => `
    <div class="cust-row ${selected.has(c.id) ? 'selected' : ''}" onclick="toggleSelect(${c.id})">
      <span class="name">${c.name} (#${c.id})</span>
      <span class="demand">demand ${c.demand}</span>
    </div>
  `).join("");
}

function updateSummary() {
  const totalDemand = customers.filter(c => selected.has(c.id)).reduce((s, c) => s + c.demand, 0);
  document.getElementById("selSummary").innerHTML =
    `<b>${selected.size}</b> customers selected - total demand <b>${totalDemand}</b>`;
}

fetch("/api/customers").then(r => r.json()).then(data => {
  customers = data;
  customers.forEach(c => {
    const m = L.circleMarker([c.lat, c.lon], markerStyle(false)).addTo(map);
    m.bindTooltip(`${c.name} (#${c.id})`);
    m.on('click', () => toggleSelect(c.id));
    markers[c.id] = m;
  });
  renderList();
});

document.getElementById("search").addEventListener("input", renderList);

document.getElementById("clearBtn").addEventListener("click", () => {
  selected.forEach(id => markers[id].setStyle(markerStyle(false)));
  selected.clear();
  renderList();
  updateSummary();
  routeLayers.forEach(l => map.removeLayer(l));
  routeLayers = [];
  document.getElementById("results").innerHTML = "";
});

const VEHICLE_COLORS = ["#ef4444","#22c55e","#a855f7","#f97316","#0891b2","#db2777"];

document.getElementById("planBtn").addEventListener("click", async () => {
  if (selected.size === 0) { alert("Select at least one customer."); return; }
  const btn = document.getElementById("planBtn");
  btn.disabled = true;
  btn.textContent = "Planning...";

  routeLayers.forEach(l => map.removeLayer(l));
  routeLayers = [];

  try {
    const resp = await fetch("/api/plan_route", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        customer_ids: Array.from(selected),
        capacity: parseInt(document.getElementById("capacity").value) || 80,
        max_route_km: parseInt(document.getElementById("maxKm").value) || 150
      })
    });
    const data = await resp.json();

    if (data.error) {
      document.getElementById("results").innerHTML = `<div class="error">${data.error}</div>`;
      return;
    }

    document.getElementById("results").innerHTML = data.routes.map((r, i) => `
      <div class="vehicle-card">
        <div class="title" style="color:${VEHICLE_COLORS[i % VEHICLE_COLORS.length]}">Vehicle ${r.vehicle}</div>
        <div class="stops">${r.stops.length} stops, demand ${r.total_demand} - ${r.distance_km} km, ${r.duration_min} min</div>
      </div>
    `).join("");

    data.routes.forEach((r, i) => {
      const layer = L.polyline(r.geometry, {
        color: VEHICLE_COLORS[i % VEHICLE_COLORS.length], weight: 4, opacity: 0.85
      }).addTo(map);
      routeLayers.push(layer);
    });

    if (routeLayers.length) {
      const group = L.featureGroup(routeLayers);
      map.fitBounds(group.getBounds(), {padding: [40, 40]});
    }
  } catch (e) {
    document.getElementById("results").innerHTML = `<div class="error">Request failed: ${e}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Plan Route";
  }
});
</script>

</body>
</html>
"""

if __name__ == "__main__":
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open("http://127.0.0.1:5050")

    app.run(debug=True, port=5050)