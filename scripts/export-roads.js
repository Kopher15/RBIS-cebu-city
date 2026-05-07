'use strict';

/**
 * RBIS Cebu City — PostGIS to GeoJSON Export
 *
 * Reads public.road_inventory from local PostGIS and writes a static
 * GeoJSON file consumed by the GitHub Pages dashboard.
 *
 * Usage:
 *   1. cp .env.example .env  (fill in DB_PASSWORD)
 *   2. npm install
 *   3. npm run export
 *
 * Output: ../data/roads.geojson
 */

const fs = require('fs');
const path = require('path');
const { Client } = require('pg');
require('dotenv').config();

// ─── Configuration ──────────────────────────────────────────────────────────

const REQUIRED_ENV = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD'];
const OUTPUT_PATH = path.resolve(__dirname, '..', 'data', 'roads.geojson');

// Locked data contract: 30 fields, all lowercase, no spaces.
// Excluded by design: length (m), est. cost, date updated, photo 1,
//                     is_deleted, deleted_at
const FIELD_LIST = [
  'id', 'fid', 'r_id', 'r_name', 'r_con', 'r_class', 'r_importan',
  'r_length', 'r_width', 's_type', 'district', 'brgy_name',
  'l_asphalt', 'l_concrete', 'l_earth', 'l_gravel',
  'l_good', 'l_fair', 'l_poor', 'l_bad', 'l_mixed', 'l_new',
  'd_flow', 'terrain', 'n_lanes',
  'asphalt_cost', 'concreting_cost', 'earthworks_cost',
  'remarks', 'inspector'
];

// ─── Helpers ────────────────────────────────────────────────────────────────

function logStep(msg) {
  console.log(`\n→ ${msg}`);
}

function logSuccess(msg) {
  console.log(`  ✓ ${msg}`);
}

function logError(msg) {
  console.error(`  ✗ ${msg}`);
}

function validateEnvironment() {
  const missing = REQUIRED_ENV.filter(key => !process.env[key]);
  if (missing.length > 0) {
    logError(`Missing required environment variables: ${missing.join(', ')}`);
    logError(`Did you copy .env.example to .env and fill in values?`);
    process.exit(1);
  }
}

// ─── SQL ────────────────────────────────────────────────────────────────────

// Build the json_build_object property list dynamically from FIELD_LIST.
// Every column name in FIELD_LIST is a safe lowercase identifier — no spaces,
// no special characters — so no quoted identifiers are needed here.
const propertyPairs = FIELD_LIST
  .map(field => `'${field}', "${field}"`)
  .join(',\n        ');

const ROADS_GEOJSON_SQL = `
  SELECT json_build_object(
    'type', 'FeatureCollection',
    'features', COALESCE(json_agg(feature), '[]'::json)
  ) AS geojson
  FROM (
    SELECT json_build_object(
      'type', 'Feature',
      'id', "id",
      'geometry', ST_AsGeoJSON(ST_Transform(geom, 4326))::json,
      'properties', json_build_object(
        ${propertyPairs}
      )
    ) AS feature
    FROM public.road_inventory
    WHERE geom IS NOT NULL
      AND (is_deleted IS NOT TRUE OR is_deleted IS NULL)
  ) AS features_subquery;
`;

const COUNT_SQL = `
  SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE geom IS NOT NULL) AS rows_with_geom,
    COUNT(*) FILTER (WHERE is_deleted IS NOT TRUE OR is_deleted IS NULL) AS active_rows,
    COUNT(*) FILTER (
      WHERE geom IS NOT NULL
        AND (is_deleted IS NOT TRUE OR is_deleted IS NULL)
    ) AS exportable_rows
  FROM public.road_inventory;
`;

const SRID_SQL = `
  SELECT DISTINCT ST_SRID(geom) AS srid
  FROM public.road_inventory
  WHERE geom IS NOT NULL
  LIMIT 5;
`;

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log(' RBIS Cebu City — PostGIS to GeoJSON Export');
  console.log('═══════════════════════════════════════════════════════════');

  validateEnvironment();

  const client = new Client({
    host: process.env.DB_HOST,
    port: parseInt(process.env.DB_PORT, 10),
    database: process.env.DB_NAME,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD
  });

  logStep(`Connecting to PostgreSQL at ${process.env.DB_HOST}:${process.env.DB_PORT}/${process.env.DB_NAME}`);

  try {
    await client.connect();
    logSuccess('Connected');
  } catch (err) {
    logError(`Connection failed: ${err.message}`);
    logError('Common causes: wrong password, wrong port, postgres not running');
    process.exit(1);
  }

  try {
    // ─── Pre-flight: row count diagnostics ────────────────────────────────
    logStep('Running pre-flight checks');
    const counts = await client.query(COUNT_SQL);
    const c = counts.rows[0];
    logSuccess(`Total rows in road_inventory: ${c.total_rows}`);
    logSuccess(`Rows with geometry:           ${c.rows_with_geom}`);
    logSuccess(`Rows not soft-deleted:        ${c.active_rows}`);
    logSuccess(`Rows that will be exported:   ${c.exportable_rows}`);

    if (parseInt(c.exportable_rows, 10) === 0) {
      logError('No exportable rows found. Aborting.');
      process.exit(1);
    }

    // ─── Pre-flight: SRID check ───────────────────────────────────────────
    logStep('Checking geometry SRIDs');
    const srids = await client.query(SRID_SQL);
    const sridList = srids.rows.map(r => r.srid).join(', ');
    logSuccess(`Detected SRIDs in geom column: ${sridList}`);
    if (srids.rows.length > 1) {
      logError('Warning: multiple SRIDs found. ST_Transform will normalize all to 4326.');
    }

    // ─── Main export ──────────────────────────────────────────────────────
    logStep('Building GeoJSON FeatureCollection');
    const result = await client.query(ROADS_GEOJSON_SQL);
    const geojson = result.rows[0].geojson;
    const featureCount = geojson.features.length;
    logSuccess(`Built FeatureCollection with ${featureCount} features`);

    if (featureCount !== parseInt(c.exportable_rows, 10)) {
      logError(`Mismatch: expected ${c.exportable_rows} features, got ${featureCount}`);
    }

    // ─── Write file ───────────────────────────────────────────────────────
    logStep(`Writing to ${OUTPUT_PATH}`);
    const json = JSON.stringify(geojson);
    fs.writeFileSync(OUTPUT_PATH, json, 'utf8');
    const sizeKB = (Buffer.byteLength(json, 'utf8') / 1024).toFixed(1);
    logSuccess(`File written (${sizeKB} KB)`);

    // ─── Sanity check: dump first feature for human verification ──────────
    logStep('First feature sample (for verification)');
    if (geojson.features[0]) {
      const sample = geojson.features[0];
      console.log(JSON.stringify({
        type: sample.type,
        id: sample.id,
        geometry: {
          type: sample.geometry?.type,
          coordinates_summary: sample.geometry?.coordinates
            ? `${sample.geometry.coordinates.length} line(s)`
            : 'NULL'
        },
        properties: sample.properties
      }, null, 2));
    }

    console.log('\n═══════════════════════════════════════════════════════════');
    console.log(' Export complete.');
    console.log('═══════════════════════════════════════════════════════════');
  } catch (err) {
    logError(`Export failed: ${err.message}`);
    if (err.position) {
      logError(`SQL error position: ${err.position}`);
    }
    process.exit(1);
  } finally {
    await client.end();
  }
}

main().catch(err => {
  console.error('Unexpected error:', err);
  process.exit(1);
});
