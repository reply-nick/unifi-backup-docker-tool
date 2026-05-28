#!/usr/bin/env python3
import logging
import sys
from pathlib import Path

from backup import download, cleanup as local_cleanup
from smb import upload, cleanup as samba_cleanup
from utils import rename_for_samba

LOG_FILE = "/var/log/unifi-backup.log"

FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


class DualHandler(logging.Handler):
    """Writes log records to both stdout and a log file."""

    def __init__(self, stream_handler, file_handler):
        super().__init__()
        self._stream = stream_handler
        self._file = file_handler

    def emit(self, record):
        self._stream.emit(record)
        self._file.emit(record)


_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter(FORMAT))

_file_handler = logging.FileHandler(LOG_FILE)
_file_handler.setFormatter(logging.Formatter(FORMAT))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(DualHandler(_stream_handler, _file_handler))

logger = logging.getLogger(__name__)


def main():
    try:
        backup_path = download()
    except Exception:
        logger.exception("download failed")
        return

    try:
        local_cleanup()
    except Exception:
        logger.exception("local cleanup failed")

    backup_path = Path(rename_for_samba(str(backup_path)))

    try:
        upload(backup_path)
    except Exception:
        logger.exception("samba upload failed")

    try:
        samba_cleanup()
    except Exception:
        logger.exception("samba cleanup failed")

    logger.info("finished")


if __name__ == "__main__":
    main()
