from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from src.logging_utils import configure_weekly_logging


def test_configure_weekly_logging_creates_weekly_rotating_handler(tmp_path: Path) -> None:
    log_file = configure_weekly_logging(log_dir=tmp_path, level="INFO")

    assert log_file == tmp_path / "nas-rag-ingestion.log"

    root = logging.getLogger()
    rotating_handlers = [h for h in root.handlers if isinstance(h, TimedRotatingFileHandler)]
    assert rotating_handlers
    handler = rotating_handlers[0]
    assert handler.backupCount == 0
    assert handler.when == "W0"
    assert Path(handler.baseFilename) == log_file

