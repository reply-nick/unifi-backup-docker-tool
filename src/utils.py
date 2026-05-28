import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

BACKUP_FILE_NAME_PREFIX = "unifi_os_backup_"


def parse_backup_timestamp(name: str, convert_ts: bool = True) -> datetime:
    """Extract and parse a datetime from a backup filename.

    Handles both ISO-8601 with colons (e.g. ``2026-05-28T03:01:52``) and
    dot-separated variants (e.g. ``2026-05-28T03.01.52``) that arise when
    ``BACKUP_INCOMPETENT_FS`` is enabled or when files were previously
    renamed by ``rename_for_samba``.
    """
    ts = name.removeprefix(BACKUP_FILE_NAME_PREFIX).split("_", 1)[0]

    if convert_ts:
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return datetime.fromisoformat(ts.replace(".", ":"))
    else:
        return datetime.fromtimestamp(int(ts) / 1000)


def rename_for_samba(local_file_path: str) -> str:
    """Rename a local backup file so colons are replaced with dots.

    Returns the (possibly new) path as a string.
    """
    renamed = local_file_path.replace(":", ".")
    if renamed != local_file_path:
        os.rename(local_file_path, renamed)
        logger.info("renamed %s -> %s", local_file_path, renamed)
    return renamed
