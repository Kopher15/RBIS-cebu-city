# Phase 1 Verification Checklist

Follow these steps in order. Stop and report at the first step that fails.

## Step 1: File placement

Place the four delivered files into your project folder:

```
RBIS-cebu-city/
├── .gitignore                  ← root gitignore
└── scripts/
    ├── package.json
    ├── .env.example
    ├── .gitignore
    └── export-roads.js
```

Also create an empty `data/` folder at the root level. The script will write into it.

## Step 2: Install Node.js dependencies

```bash
cd RBIS-cebu-city/scripts
npm install
```

**Expected:** `node_modules/` folder appears, no errors. Two packages installed: `pg` and `dotenv` (plus their dependencies).

**If it fails:** confirm Node.js is installed (`node --version` should print v16 or higher).

## Step 3: Set up your local environment file

```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in your real values:

```
DB_HOST=localhost
DB_PORT=5433
DB_NAME=gis_db
DB_USER=postgres
DB_PASSWORD=<your actual postgres password>
```

**Critical:** `.env` is gitignored. It will never reach GitHub. Verify by running `git status` later — `.env` should not appear.

## Step 4: Run the export

```bash
npm run export
```

## Step 5: Expected output

The script prints a banner, runs pre-flight checks, then writes the file. A successful run looks like this:

```
═══════════════════════════════════════════════════════════
 RBIS Cebu City — PostGIS to GeoJSON Export
═══════════════════════════════════════════════════════════

→ Connecting to PostgreSQL at localhost:5433/gis_db
  ✓ Connected

→ Running pre-flight checks
  ✓ Total rows in road_inventory: <some number>
  ✓ Rows with geometry:           <some number>
  ✓ Rows not soft-deleted:        <some number>
  ✓ Rows that will be exported:   <some number>

→ Checking geometry SRIDs
  ✓ Detected SRIDs in geom column: 4326

→ Building GeoJSON FeatureCollection
  ✓ Built FeatureCollection with <N> features

→ Writing to /path/to/RBIS-cebu-city/data/roads.geojson
  ✓ File written (<size> KB)

→ First feature sample (for verification)
{
  "type": "Feature",
  "id": 1,
  "geometry": {
    "type": "MultiLineString",
    "coordinates_summary": "1 line(s)"
  },
  "properties": {
    "id": 1,
    "fid": ...,
    "r_id": ...,
    "r_name": "...",
    ... (30 fields total)
  }
}

═══════════════════════════════════════════════════════════
 Export complete.
═══════════════════════════════════════════════════════════
```

## Step 6: What to send back

Paste the entire console output (from the banner to "Export complete") into the chat. I will verify:

- Connection succeeded
- Row counts make sense (no zeros where you don't expect them)
- SRID is 4326 (or document if it's something else)
- All 30 properties are present in the first feature sample
- The MultiLineString geometry is intact

## What NOT to do yet

- Do NOT touch `index.html` — that is Phase 2.
- Do NOT push anything to GitHub yet — that is Phase 3.
- Do NOT commit `.env` (the gitignore prevents this, but be aware).

## If something fails

Common failures and what they mean:

| Error message | Cause |
|---|---|
| `Missing required environment variables` | You skipped Step 3 or `.env` is in the wrong folder |
| `Connection failed: password authentication failed` | Wrong password in `.env` |
| `Connection failed: ECONNREFUSED` | Postgres isn't running, or wrong port |
| `relation "public.road_inventory" does not exist` | Wrong database name, or you're connected to the wrong server |
| `No exportable rows found` | All rows have `is_deleted = true` or `geom IS NULL` |
| `column "X" does not exist` | A column from the locked contract isn't in your table after all |

Whatever the error, paste the full output. I'll diagnose from there.
