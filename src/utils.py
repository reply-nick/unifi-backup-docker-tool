import logging
import os
import random
import time
from datetime import datetime
from functools import wraps

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
            try:
                return datetime.fromisoformat(ts.replace(".", ":"))
            except ValueError:
                # Fallback: might be a Unix timestamp in milliseconds
                try:
                    return datetime.fromtimestamp(int(ts) / 1000)
                except (ValueError, OverflowError):
                    logger.error(f"Failed to parse timestamp from filename: {name}")
                    raise
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


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0, jitter: bool = True):
    """Retry a function on transient failure with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default 3).
        delay: Initial delay between retries in seconds (default 1.0).
        backoff: Multiplier applied to delay after each retry (default 2.0).
        jitter: Add random jitter to delay to avoid thundering herd (default True).
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exc = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        raise
                    logger.warning(
                        "%s attempt %d/%d failed: %s — retrying in %.1fs",
                        fn.__name__,
                        attempt,
                        max_attempts,
                        exc,
                        current_delay,
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
                    if jitter:
                        current_delay *= (0.5 + random.random())

        return wrapper

    return decorator
