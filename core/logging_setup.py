import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

_MANAGED_HANDLER_ATTR = "_maybeai_managed"


def resolve_log_path(log_file: Optional[Path | str] = None) -> Path:
    """Resolves the rotating log file path under MAYBEAI_DATA_DIR or ./data."""
    if log_file is not None:
        return Path(log_file)
    data_dir = os.getenv("MAYBEAI_DATA_DIR", "").strip() or "data"
    return Path(data_dir) / "logs" / "maybeai.log"


def _stdout_logging_enabled() -> bool:
    raw = os.getenv("MAYBEAI_LOG_STDOUT", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[Path | str] = None,
) -> logging.Logger:
    """Configures rotating file logging and optional stdout stream logging."""
    log_path = resolve_log_path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level_name = (level or os.getenv("MAYBEAI_LOG_LEVEL", "INFO")).strip().upper()
    log_level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        if getattr(existing, _MANAGED_HANDLER_ATTR, False):
            root_logger.removeHandler(existing)
            try:
                existing.close()
            except Exception:
                pass

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    setattr(file_handler, _MANAGED_HANDLER_ATTR, True)
    root_logger.addHandler(file_handler)

    if _stdout_logging_enabled():
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(log_level)
        setattr(stream_handler, _MANAGED_HANDLER_ATTR, True)
        root_logger.addHandler(stream_handler)

    root_logger.setLevel(log_level)
    return logging.getLogger("maybeai")
