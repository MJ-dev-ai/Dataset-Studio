from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import LOGGER_NAME, LOG_BACKUP_COUNT, LOG_FILE_MAX_BYTES

_LOG_DIRECTORY: Path | None = None


class DurableRotatingFileHandler(RotatingFileHandler):
    """Flush every record and force error records to durable storage."""

    def emit(self, record):
        super().emit(record)
        self.flush()
        if record.levelno >= logging.ERROR and self.stream is not None:
            os.fsync(self.stream.fileno())


def configure_logging(log_dir: str | os.PathLike) -> logging.Logger:
    """Configure the application logger once and return it."""
    global _LOG_DIRECTORY
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if any(isinstance(handler, DurableRotatingFileHandler) for handler in logger.handlers):
        return logger

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    _LOG_DIRECTORY = directory
    handler = DurableRotatingFileHandler(
        directory / "dataset_editor.log",
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def flush_logs(durable: bool = False):
    """Flush every application handler, optionally forcing file buffers to disk."""
    for handler in get_logger().handlers:
        handler.flush()
        stream = getattr(handler, "stream", None)
        if durable and stream is not None and hasattr(stream, "fileno"):
            try:
                os.fsync(stream.fileno())
            except (OSError, ValueError):
                pass


def append_pending_crash(traceback_text: str) -> Path:
    """Durably append an unhandled exception for recovery on the next launch."""
    directory = _LOG_DIRECTORY or Path.cwd() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "pending_crash.log"
    timestamp = datetime.now(timezone.utc).isoformat()
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(f"\n[{timestamp}] Unhandled exception\n{traceback_text.rstrip()}\n")
        stream.flush()
        os.fsync(stream.fileno())
    return destination


def append_crash_report(title: str, traceback_text: str) -> Path:
    """Durably append a recoverable or fatal crash report."""
    directory = _LOG_DIRECTORY or Path.cwd() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "crash.log"
    timestamp = datetime.now(timezone.utc).isoformat()
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(f"\n[{timestamp}] {title}\n{traceback_text.rstrip()}\n")
        stream.flush()
        os.fsync(stream.fileno())
    return destination
