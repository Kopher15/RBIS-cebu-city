import subprocess
import os
from lib.logger import get_logger

def load_gpkg_to_stage(cfg, conn_string=None):
    logger = get_logger(cfg["log_dir"], "gpkg_loader")
    
    # If no specific conn_string is passed, fall back to the first destination
    if conn_string is None:
        conn_string = cfg["destinations"][0]["conn_string"]

    gpkg_path = cfg["gpkg_path"]
    layer_name = cfg["layer_name"]
    stage_table = cfg["stage_table"]
    ogr2ogr = cfg["ogr2ogr_path"]

    # Build PG connection string for ogr2ogr (handles postgres:// or dbname= formats)
    # ogr2ogr uses "PG:connection_string"
    pg_dsn = f"PG:{conn_string}"

    logger.info(f"Loading {layer_name} from GPKG to {stage_table}...")

    cmd = [
        ogr2ogr,
        "-overwrite",
        "-f", "PostgreSQL",
        pg_dsn,
        gpkg_path,
        layer_name,
        "-nln", stage_table,
        "-t_srs", "EPSG:4326",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "OVERWRITE=YES"
    ]

    # Set environment variables for QGIS-bundled GDAL
    env = os.environ.copy()
    qgis_bin = os.path.dirname(ogr2ogr)
    qgis_share = os.path.join(os.path.dirname(qgis_bin), "share")
    env["PROJ_LIB"] = os.path.join(qgis_share, "proj")
    env["GDAL_DATA"] = os.path.join(qgis_share, "gdal")

    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        logger.info("Successfully loaded GPKG to staging table.")
    except subprocess.CalledProcessError as e:
        logger.error(f"ogr2ogr failed: {e.stderr}")
        raise Exception(f"Failed to load GPKG: {e.stderr}")
