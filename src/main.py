#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from backup import download, cleanup as local_cleanup
from reporter import BackupReport, send_report
from smb import upload, cleanup as samba_cleanup
from utils import rename_for_samba

LOG_FILE = os.environ.get("LOG_FILE", "/var/log/unifi-backup.log")

FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"


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


_file_handler = logging.FileHandler(LOG_FILE)
_file_handler.setFormatter(logging.Formatter(FORMAT))

root_logger = logging.getLogger()
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
root_logger.setLevel(getattr(logging, log_level, logging.INFO))
root_logger.addHandler(_file_handler)

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

    report = BackupReport(success=False, started_at=datetime.now())

    backup_path: Path | None = None

    with timing("download"):
        try:
            backup_path = download()
            report.filename = backup_path.name
            report.filesize_bytes = backup_path.stat().st_size
            report.local_path = str(backup_path)
        except Exception:
            logger.exception("download failed")
            report.errors.append("Download failed")

    with timing("local cleanup"):
        try:
            remaining = local_cleanup()
            report.local_cleanup_success = True
            report.local_backups_remaining = remaining
        except Exception:
            logger.exception("local cleanup failed")
            report.local_cleanup_error = str(sys.exc_info()[1])
            report.errors.append("Local cleanup failed")

    if backup_path is not None:
        incompetent_fs = _get_env("BACKUP_INCOMPETENT_FS", "false").lower() == "true"
        if not incompetent_fs:
            backup_path = Path(rename_for_samba(str(backup_path)))
        with timing("samba upload"):
            try:
                upload(backup_path)
                report.samba_upload_success = True
            except Exception:
                logger.exception("samba upload failed")
                report.samba_upload_error = str(sys.exc_info()[1])
                report.errors.append("Samba upload failed")
    else:
        logger.warning("skipping samba upload — no backup available")
        report.errors.append("Samba upload skipped — no backup available")

    with timing("samba cleanup"):
        try:
            remaining = samba_cleanup()
            report.samba_cleanup_success = True
            report.samba_backups_remaining = remaining
        except Exception:
            logger.exception("samba cleanup failed")
            report.samba_cleanup_error = str(sys.exc_info()[1])
            report.errors.append("Samba cleanup failed")

    report.finished_at = datetime.now()

    if report.success is False:
        report.success = (
            report.filename is not None
            and report.local_cleanup_success
            and report.samba_upload_success
            and report.samba_cleanup_success
        )

    try:
        send_report(report)
    except Exception:
        logger.exception("report sending failed")

    logger.info("finished")


if __name__ == "__main__":
    main()
