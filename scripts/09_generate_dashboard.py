import json
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FLEET_JSON = PROJECT_ROOT / "cache" / "fleet_dashboard_data.json"
ROUTES_JSON = PROJECT_ROOT / "cache" / "route_coords.json"
CUSTOMERS_PATH = PROJECT_ROOT / "cache" / "customers_clustered_final1.csv"
OUT_HTML = PROJECT_ROOT / "apps" / "fleet_map_dashboard.html"

DEPOT_LAT = 43.8563
DEPOT_LON = 18.4131

with open(FLEET_JSON) as f:
    fleet_data = json.load(f)
vehicles = fleet_data["vehicles"]
assumptions = fleet_data["generated_assumptions"]

with open(ROUTES_JSON) as f:
    route_coords = json.load(f)

df = pd.read_csv(CUSTOMERS_PATH)
df = df[df["id"] != 0]
customers = df[["id", "name", "lat", "lon", "cluster", "demand"]].to_dict("records")

# attach a route_key to each vehicle so JS can look up its coords directly
for v in vehicles:
    v["route_key"] = f"{v['cluster']}_{v['vehicle_number_in_cluster']}"

total_fuel = sum(v["fuel_liters"] for v in vehicles)
total_cost = sum(v["total_cost_bam"] for v in vehicles)
total_co2 = sum(v["co2_kg"] for v in vehicles)
total_km = sum(v["route_distance_km"] for v in vehicles)
overnight_count = sum(1 for v in vehicles if v["needs_overnight"])

vehicles_json = json.dumps(vehicles)
routes_json = json.dumps(route_coords)
customers_json = json.dumps(customers)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Fleet Map Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; margin: 0; }}
  body {{
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    display: flex;
    flex-direction: column;
  }}
  h1 {{ font-size: 18px; margin: 14px 16px 4px; }}
  .subtitle {{ color: #94a3b8; font-size: 12px; margin: 0 16px 12px; }}

  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    margin: 0 16px 12px;
  }}
  .card {{
    background: #1e293b;
    border-radius: 8px;
    padding: 10px 12px;
    border: 1px solid #334155;
  }}
  .card .label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; }}
  .card .value {{ font-size: 18px; font-weight: 600; margin-top: 2px; }}
  .card.warn .value {{ color: #f59e0b; }}

  .main {{
    display: flex;
    flex: 1;
    min-height: 0;
    padding: 0 16px 16px;
    gap: 12px;
  }}
  .left {{
    flex: 0 0 46%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }}
  .right {{
    flex: 1;
    min-height: 0;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #334155;
  }}
  #map {{ width: 100%; height: 100%; }}

  .controls {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }}
  input, select {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    padding: 7px 9px;
    border-radius: 6px;
    font-size: 12px;
  }}
  input[type="text"] {{ min-width: 160px; flex: 1; }}

  .table-wrap {{
    flex: 1;
    overflow: auto;
    border-radius: 10px;
    border: 1px solid #334155;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; background: #1e293b; }}
  th, td {{ padding: 7px 8px; text-align: left; border-bottom: 1px solid #334155; white-space: nowrap; }}
  th {{ background: #0f172a; color: #94a3b8; font-weight: 600; position: sticky; top: 0; cursor: pointer; }}
  tr {{ cursor: pointer; }}
  tr:hover td {{ background: #263449; }}
  tr.selected td {{ background: #1e3a5f; }}
  .plate {{ font-family: monospace; font-weight: 600; }}
  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 10px; font-weight: 600; }}
  .badge.overnight {{ background: #7c2d12; color: #fdba74; }}
  .badge.ok {{ background: #14532d; color: #86efac; }}

  .footnote {{ color: #64748b; font-size: 10px; margin: 10px 16px 0; line-height: 1.5; }}
</style>
</head>
<body>

<h1>Fleet Map Dashboard</h1>
<div class="subtitle">Click a vehicle to highlight its route on the map. {len(vehicles)} vehicles, {len(customers)} customers, {total_km:,.0f} km total.</div>

<div class="cards">
  <div class="card"><div class="label">Vehicles</div><div class="value">{len(vehicles)}</div></div>
  <div class="card"><div class="label">Distance</div><div class="value">{total_km:,.0f} km</div></div>
  <div class="card"><div class="label">Fuel</div><div class="value">{total_fuel:,.0f} L</div></div>
  <div class="card"><div class="label">Cost</div><div class="value">{total_cost:,.0f} BAM</div></div>
  <div class="card"><div class="label">CO&#8322;</div><div class="value">{total_co2:,.0f} kg</div></div>
  <div class="card warn"><div class="label">Overnight</div><div class="value">{overnight_count}</div></div>
</div>

<div class="main">
  <div class="left">
    <div class="controls">
      <input type="text" id="search" placeholder="Search plate, mark, cluster...">
      <select id="filterOvernight">
        <option value="">All vehicles</option>
        <option value="yes">Overnight only</option>
        <option value="no">Same-day only</option>
      </select>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Plate</th><th>Mark</th><th>Cluster</th><th>Veh#</th>
            <th>Custs</th><th>Dist</th><th>Fuel</th><th>Cost</th><th>Status</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>
  <div class="right"><div id="map"></div></div>
</div>

<div class="footnote">
  Estimates only: average speed {assumptions['average_speed_kmh']} km/h,
  {assumptions['service_time_per_stop_min']} min/stop, fuel {assumptions['fuel_price_per_liter_bam']} BAM/L,
  wage {assumptions['driver_wage_per_hour_bam']} BAM/h. Plates/marks are illustrative, not real fleet data.
</div>

<script>
const vehicles = {vehicles_json};
const routeCoords = {routes_json};
const customers = {customers_json};
const DEPOT = [{DEPOT_LAT}, {DEPOT_LON}];

const CLUSTER_COLORS = ["#ef4444","#3b82f6","#22c55e","#a855f7","#f97316","#b91c1c",
  "#0891b2","#15803d","#1d4ed8","#db2777","#dc2626","#4f46e5","#c2410c"];

function colorForCluster(cid) {{
  const clusters = [...new Set(vehicles.map(v => v.cluster))].sort((a,b)=>a-b);
  const idx = clusters.indexOf(cid);
  return CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
}}

const map = L.map('map', {{ zoomControl: true }}).setView([44.2, 17.8], 8);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  attribution: 'Esri'
}}).addTo(map);

L.marker(DEPOT, {{title: "Depot"}}).addTo(map).bindPopup("Depot (Sarajevo)");

// customer markers, colored by cluster
customers.forEach(c => {{
  L.circleMarker([c.lat, c.lon], {{
    radius: 3, color: colorForCluster(c.cluster), fillOpacity: 0.8, weight: 1
  }}).addTo(map).bindPopup(`${{c.name}} (id ${{c.id}}) - cluster ${{c.cluster}} - demand ${{c.demand}}`);
}});

// draw all routes at low opacity, keep references so we can highlight one later
const routeLayers = {{}};
vehicles.forEach(v => {{
  const coords = routeCoords[v.route_key];
  if (!coords || coords.length === 0) return;
  const layer = L.polyline(coords, {{
    color: colorForCluster(v.cluster), weight: 2, opacity: 0.35
  }}).addTo(map);
  layer.on('click', () => selectVehicle(v.route_key));
  routeLayers[v.route_key] = layer;
}});

let selectedKey = null;

function selectVehicle(key) {{
  if (selectedKey && routeLayers[selectedKey]) {{
    const prev = vehicles.find(v => v.route_key === selectedKey);
    routeLayers[selectedKey].setStyle({{ weight: 2, opacity: 0.35, color: colorForCluster(prev.cluster) }});
  }}
  selectedKey = key;
  const layer = routeLayers[key];
  if (layer) {{
    layer.setStyle({{ weight: 5, opacity: 1, color: "#facc15" }});
    layer.bringToFront();
    map.fitBounds(layer.getBounds(), {{ padding: [40, 40] }});
  }}
  document.querySelectorAll("#tbody tr").forEach(tr => {{
    tr.classList.toggle("selected", tr.dataset.key === key);
  }});
}}

function render(list) {{
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = list.map(v => `
    <tr data-key="${{v.route_key}}" onclick="selectVehicle('${{v.route_key}}')" class="${{v.route_key === selectedKey ? 'selected' : ''}}">
      <td class="plate">${{v.plate}}</td>
      <td>${{v.mark}}</td>
      <td>${{v.cluster}}</td>
      <td>${{v.vehicle_number_in_cluster}}</td>
      <td>${{v.n_customers}}</td>
      <td>${{v.route_distance_km.toFixed(1)}} km</td>
      <td>${{v.fuel_liters.toFixed(1)}} L</td>
      <td>${{v.total_cost_bam.toFixed(0)}} BAM</td>
      <td>${{v.needs_overnight
            ? '<span class="badge overnight">Overnight</span>'
            : '<span class="badge ok">Same-day</span>'}}</td>
    </tr>
  `).join("");
}}

function applyFilters() {{
  const q = document.getElementById("search").value.toLowerCase();
  const overnightFilter = document.getElementById("filterOvernight").value;
  let list = vehicles.filter(v => {{
    const matchesSearch = !q ||
      v.plate.toLowerCase().includes(q) ||
      v.mark.toLowerCase().includes(q) ||
      String(v.cluster).includes(q);
    const matchesOvernight =
      overnightFilter === "" ||
      (overnightFilter === "yes" && v.needs_overnight) ||
      (overnightFilter === "no" && !v.needs_overnight);
    return matchesSearch && matchesOvernight;
  }});
  render(list);
}}

document.getElementById("search").addEventListener("input", applyFilters);
document.getElementById("filterOvernight").addEventListener("change", applyFilters);

applyFilters();
</script>

</body>
</html>
"""

OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
OUT_HTML.write_text(html, encoding="utf-8")
print(f"Saved combined dashboard: {OUT_HTML}")