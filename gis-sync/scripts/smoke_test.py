import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lib.db import load_config, connect
from lib.logger import get_logger

cfg = load_config(os.path.join("config", "sync.config.json"))
log = get_logger(cfg["log_dir"])
log.info("Smoke test starting")

with connect(cfg) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.road_inventory;")
        n = cur.fetchone()[0]
        log.info(f"road_inventory rows: {n}")
        cur.execute("SELECT COUNT(*) FROM public.sync_log;")
        log.info(f"sync_log rows: {cur.fetchone()[0]}")

log.info("Smoke test OK")
print("OK")
