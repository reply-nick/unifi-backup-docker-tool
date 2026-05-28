#!/usr/bin/env python3
import logging
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from backup import download, cleanup as local_cleanup
from smb import upload, cleanup as samba_cleanup
from utils import rename_for_samba

LOG_FILE = "/var/log/unifi-backup.log"

FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"


class DualHandler(logging.Handler):
    """Writes log records to both stdout and a log file."""

    def __init__(self, stream_handler, file_handler):
        super().__init__()
        self._stream = stream_handler
        self._file = file_handler

    def emit(self, record):
        self._stream.emit(record)
        self._file.emit(record)


def _get_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name)
    if value is None:
        if default is not None:
            return default
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


@contextmanager
def timing(label: str):
    """Context manager that logs the duration of a block."""
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            logger.info("%s completed in %d:%02d:%02d", label, hours, minutes, seconds)
        elif minutes > 0:
            logger.info("%s completed in %d:%02d", label, minutes, seconds)
        else:
            logger.info("%s completed in %.1fs", label, seconds)


_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter(FORMAT))

_file_handler = logging.FileHandler(LOG_FILE)
_file_handler.setFormatter(logging.Formatter(FORMAT))

root_logger = logging.getLogger()
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
root_logger.setLevel(getattr(logging, log_level, logging.INFO))
root_logger.addHandler(DualHandler(_stream_handler, _file_handler))

logger = logging.getLogger(__name__)


def main():
    # Log startup context
    logger.info("=" * 60)
    logger.info("UniFi Backup Tool starting")
    logger.info("Log level: %s", log_level)
    logger.info("Server: %s", _get_env("UNIFI_SERVER_ADDRESS"))
    logger.info("Backup folder: %s", _get_env("BACKUP_FOLDER"))
    logger.info("Samba: %s@%s/share=%s/path=%s",
                _get_env("SAMBA_USER"), _get_env("SAMBA_HOST"),
                _get_env("SAMBA_SHARE"), _get_env("SAMBA_REMOTE_PATH", "unifi"))
    logger.info("Local retention: max=%s, min_age=%s days",
                _get_env("BACKUP_LOCAL_MAX_COUNT", "7"),
                _get_env("BACKUP_LOCAL_MIN_AGE_DAYS", "7"))
    logger.info("Samba retention: max=%s, min_age=%s days",
                _get_env("SAMBA_MAX_COUNT", "30"),
                _get_env("SAMBA_MIN_AGE_DAYS", "30"))
    logger.info("=" * 60)

    with timing("download"):
        try:
            backup_path = download()
        except Exception:
            logger.exception("download failed")
            return

    with timing("local cleanup"):
        try:
            local_cleanup()
        except Exception:
            logger.exception("local cleanup failed")

    backup_path = Path(rename_for_samba(str(backup_path)))

    with timing("samba upload"):
        try:
            upload(backup_path)
        except Exception:
            logger.exception("samba upload failed")

    with timing("samba cleanup"):
        try:
            samba_cleanup()
        except Exception:
            logger.exception("samba cleanup failed")

    logger.info("finished")


if __name__ == "__main__":
    main()
