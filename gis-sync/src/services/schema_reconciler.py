from lib.db import get_db_connection
from lib.logger import get_logger

def reconcile(cfg, conn_string):
    logger = get_logger(cfg["log_dir"], "schema_reconciler")
    target_table = cfg["target_table"]
    stage_table = cfg["stage_table"]
    
    with get_db_connection(conn_string) as conn:
        with conn.cursor() as cur:
            # Get columns from both tables to compare
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{target_table.split('.')[-1]}'")
            target_cols = {row[0] for row in cur.fetchall()}
            
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{stage_table.split('.')[-1]}'")
            stage_cols = {row[0] for row in cur.fetchall()}
            
            added = stage_cols - target_cols
            for col in added:
                logger.info(f"New column detected in GPKG: {col}. Adding to production.")
                cur.execute(f'ALTER TABLE {target_table} ADD COLUMN "{col}" TEXT')
            
            return {"added": list(added), "mapped": list(stage_cols)}
