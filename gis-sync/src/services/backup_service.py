from datetime import datetime
from lib.db import get_db_connection
from lib.logger import get_logger

def create_backup(cfg, conn_string):
    logger = get_logger(cfg["log_dir"], "backup_service")
    target = cfg["target_table"]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S").lower()
    bak_table = f"{target}_bak_{timestamp}"
    
    with get_db_connection(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE {bak_table} AS SELECT * FROM {target}")
            logger.info(f"Backup created: {bak_table}")
            return bak_table
