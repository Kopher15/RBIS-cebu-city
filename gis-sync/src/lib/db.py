import psycopg
from contextlib import contextmanager

@contextmanager
def get_db_connection(conn_string):
    """
    Creates a context-managed connection to a PostgreSQL database
    using the provided connection string.
    """
    conn = psycopg.connect(conn_string)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
