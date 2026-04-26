"""Logging utilities for CLI scripts in this repository."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def configure_weekly_logging(
    log_dir: str | Path = "/volume1/Temp/logs",
    log_file_name: str = "structured-nas-ingestions.log",
    level: str = "INFO",
) -> Path:
    """Configure root logging with weekly file rotation and console output.

    - Log file path defaults to `/volume1/Temp/logs/structured-nas-ingestions.log`
    - Weekly rollover happens every Monday at midnight UTC
    - `backupCount=0` keeps all historical log files
    """
    target_dir = Path(log_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = target_dir / log_file_name

    resolved_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = TimedRotatingFileHandler(
        filename=str(log_file_path),
        when="W0",
        interval=1,
        backupCount=0,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    # Reduce noisy third-party warnings while preserving parser warnings/errors.
    logging.getLogger("docling").setLevel(logging.WARNING)
    return log_file_path
