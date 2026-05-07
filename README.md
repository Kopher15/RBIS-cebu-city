# RBIS — Roads & Bridges Inventory System

Public dashboard for the **City of Cebu Department of Engineering & Public Works (DEPW)**, tracking the condition, surface type, and estimated maintenance cost of every road segment in the city.

🌐 **Live dashboard:** [kopher15.github.io/RBIS-cebu-city](https://kopher15.github.io/RBIS-cebu-city/)

---

## What this is

RBIS replaces a fragile Google Sheets + manual API setup with a **single source of truth** workflow:

1. Field crews record road inspection data into the DEPW PostGIS database (`gis_db.road_inventory`)
2. A local Node script exports the inventory as `roads.geojson`
3. The dashboard, hosted on GitHub Pages, reads the static GeoJSON directly — no API server, no hosted database, zero infrastructure cost

The result: a fast, free, transparent public dashboard backed by the city's authoritative GIS database.

## Architecture

```
   ┌──────────────────┐         ┌─────────────────┐         ┌──────────────────┐
   │  PostGIS         │         │  GitHub repo    │         │  GitHub Pages    │
   │  (DEPW office)   │  push   │  RBIS-cebu-city │  serve  │  Public site     │
   │  road_inventory  │ ──────▶ │  data/*.geojson │ ──────▶ │  index.html      │
   │  7,995 segments  │         │  data/*.json    │         │  + Leaflet map   │
   └──────────────────┘         └─────────────────┘         └──────────────────┘
        ▲                                                           │
        │                                                           ▼
        └───────── npm run export (local script) ◀──────── Field crews & public
```

**Why static GeoJSON?**
- No server costs, no Render/Heroku to crash
- No API rate limits
- Browser caches aggressively → instant load on repeat visits
- The data is read-only by design; updates happen through the export workflow

## Repository structure

```
RBIS-cebu-city/
├── index.html              ← Single-file dashboard (HTML/CSS/JS, no build step)
├── data/
│   ├── roads.geojson       ← 7,995 road segments (regenerated from PostGIS)
│   └── cost-rates.json     ← DPWH unit cost schedule (manually edited)
├── scripts/
│   ├── export-roads.js     ← PostGIS → GeoJSON exporter
│   ├── package.json        ← Node deps (pg, dotenv)
│   ├── .env.example        ← DB connection template
│   └── PHASE_1_CHECKLIST.md
├── .gitignore
└── README.md
```

## Data refresh workflow

When field crews complete new inspections and the data is in PostGIS, push updates with:

```powershell
# 1. Re-export the GeoJSON from PostGIS
cd C:\RBIS-cebu-city\scripts
npm run export

# 2. Commit and push (back to repo root)
cd ..
git add data/roads.geojson
git commit -m "Refresh: <DATE> inspection update"
git push
```

GitHub Pages deploys the new data within ~60 seconds. Refresh the dashboard URL — new numbers appear.

**No build step. No deployment pipeline. No server restart.** The export script + git push *is* the deployment.

## Cost calculation rules

The "Estimated Cost" column applies the DPWH unit cost schedule (see [`data/cost-rates.json`](data/cost-rates.json)) to fully-inspected segments only.

A segment is **fully inspected** when all four fields are valid:
- `r_con` ∈ `{Bad, Poor, Fair, Good}` (no empty, no "For Evaluation", no "Unknown")
- `s_type` ∈ `{Asphalt, Concrete, Gravel, Earth, Mixed}` (no empty)
- `r_length` > 0
- `r_width` > 0

Formula: `cost = unit_rate × length(m) × width(m)`

**Roads with any missing field** display "—" in the cost column and are excluded from the total. The **inspection completeness bar** at the top of the dashboard shows what percentage of segments meet this bar — it's an honest measure of how much of the city has been formally surveyed vs. how much still needs ground truth.

### Cost rate table (PHP per cubic meter)

| Condition | Asphalt | Concrete | Gravel | Earth  | Mixed  |
|-----------|--------:|---------:|-------:|-------:|-------:|
| Bad       |   6,500 |    8,000 |  3,500 |  2,500 |  5,000 |
| Poor      |   1,800 |    2,200 |    900 |    700 |  1,200 |
| Fair      |     350 |      350 |    350 |    350 |    350 |
| Good      |     150 |      150 |    150 |    150 |    150 |

To adjust rates: edit `data/cost-rates.json` directly, commit, push. The dashboard reloads with new totals on refresh — no code change needed.

## Local development

The dashboard is a single static HTML file. Any HTTP server works:

```powershell
cd C:\RBIS-cebu-city
python -m http.server 8000
# open http://localhost:8000
```

> **Note:** Opening `index.html` directly via `file://` will fail. Browsers block `fetch()` for local files. Always serve over HTTP.

To regenerate the GeoJSON locally, you need:
- Node.js 18+
- Read access to the PostGIS database (`gis_db.road_inventory`)
- A `scripts/.env` file (copy from `.env.example` and fill in DB credentials)

Then:

```powershell
cd C:\RBIS-cebu-city\scripts
npm install
npm run export
```

## Inspection completeness — current status

The dashboard's persistent inspection bar reports the percentage of road segments that have been fully inspected. As of the most recent export, only a fraction of the city's roads have all four fields populated. This is normal and expected — it's a multi-year inspection effort.

**The bar is the planning tool**: when it goes green (≥75%), DEPW knows the city has been comprehensively surveyed.

## Data accuracy & known gaps

- 16 road segments in PostGIS have valid inspection data but no `r_name`. They appear on the map and contribute to the inspection completeness count, but are not grouped in the road table. DEPW field crews should triage these for naming.
- 1 row is soft-deleted (`is_deleted = true`) and excluded from all exports.

## Tech stack

- **Database:** PostgreSQL 15 + PostGIS 3
- **Export:** Node.js (`pg`, `dotenv`)
- **Frontend:** Single-file HTML, vanilla JS, [Leaflet](https://leafletjs.com/) for maps, [Chart.js](https://www.chartjs.org/) for charts
- **Hosting:** GitHub Pages (free static hosting)
- **Build step:** None

## License

The dashboard code is released under the [MIT License](LICENSE).

The road inventory data (`data/roads.geojson`) is public infrastructure data published by the City of Cebu DEPW.

## Contact

City of Cebu — Department of Engineering & Public Works
Cebu City, Philippines

---

*Bagong Pilipinas — Building transparent public infrastructure.*
