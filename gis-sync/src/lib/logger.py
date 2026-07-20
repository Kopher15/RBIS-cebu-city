"""Centralized logger. One file per day in log_dir, plus console output.

API:
    get_logger(log_dir, name="gpkg_sync") -> logging.Logger

The first positional arg is ALWAYS log_dir to match the established
caller convention `get_logger(cfg["log_dir"])`. The `name` arg is
optional and lets services/scripts identify themselves in log lines
without affecting where logs are written.

All loggers share the same file handler (one file per day) but each
has its own name for filtering. Console output goes to stdout at INFO.
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

_DEFAULT_NAME = "gpkg_sync"
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Track which (name, log_dir) pairs we have already configured so repeat
# calls do not stack handlers.
_configured: set[tuple[str, str]] = set()


def get_logger(log_dir: str, name: str = _DEFAULT_NAME) -> logging.Logger:
    """Return a configured logger that writes to log_dir/sync_<date>.log
    and stdout.

    Args:
        log_dir: Directory for the daily rotating log file. Created if missing.
        name:    Logger name (appears in log lines). Defaults to gpkg_sync.
                 Pass __name__ from a module to tag its messages, e.g.
                 get_logger(cfg["log_dir"], __name__).

    Returns:
        logging.Logger configured at INFO level with file + console handlers.
    """
    logger = logging.getLogger(name)
    key = (name, os.path.abspath(log_dir))
    if key in _configured:
        return logger

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(
        log_dir, f"sync_{datetime.now().strftime('%Y-%m-%d')}.log"
    )

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    # File handler: rotating, shared across all loggers writing to this dir.
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # Console handler: stdout, INFO level. Fixes the silent-script trap
    # where logger.info() produced no terminal output.
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    _configured.add(key)
    return logger
