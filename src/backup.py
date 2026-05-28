#!/usr/bin/env python3
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

from utils import BACKUP_FILE_NAME_PREFIX, parse_backup_timestamp

logger = logging.getLogger(__name__)

LOGIN_URL = "/api/auth/login"
BACKUP_URL = "/api/backup/download"


def _get_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name)
    if value is None:
        if default is not None:
            return default
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


def download() -> Path:
    server_address = _get_env("UNIFI_SERVER_ADDRESS").removesuffix("/")
    user_name = _get_env("UNIFI_USER")
    password = _get_env("UNIFI_PASSWORD")
    validate_tls = _get_env("UNIFI_VALIDATE_TLS", "false").lower() == "true"
    backup_folder = _get_env("BACKUP_FOLDER")
    convert_ts = _get_env("BACKUP_CONVERT_TIMESTAMP", "true").lower() == "true"
    incompetent_fs = _get_env("BACKUP_INCOMPETENT_FS", "false").lower() == "true"

    sess = requests.Session()
    logger.info("logging in")
    resp = sess.post(
        f"{server_address}{LOGIN_URL}",
        json={"username": user_name, "password": password},
        verify=validate_tls,
    )
    resp.raise_for_status()
    logger.info("logged in")
    resp = sess.get(f"{server_address}{BACKUP_URL}", verify=validate_tls)
    resp.raise_for_status()
    assert resp.headers["Content-Type"] == "application/octet-stream"
    filename = resp.headers["filename"]
    assert filename.startswith(BACKUP_FILE_NAME_PREFIX)

    if convert_ts:
        file_ts, filename_end = filename.removeprefix(BACKUP_FILE_NAME_PREFIX).split("_", 1)
        file_ts = datetime.fromtimestamp(int(file_ts) / 1000)
        filename = f"{BACKUP_FILE_NAME_PREFIX}{file_ts.isoformat(timespec='seconds')}_{filename_end}"
        if incompetent_fs:
            filename = filename.replace(":", ".")

    logger.info('downloaded "%s"', filename)
    download_path = Path(backup_folder) / filename
    Path(backup_folder).mkdir(parents=True, exist_ok=True)
    with Path(download_path).open("wb") as f:
        f.write(resp.content)
    logger.info('saved "%s" at "%s"', filename, backup_folder)
    return download_path


def cleanup():
    backup_folder = _get_env("BACKUP_FOLDER")
    convert_ts = _get_env("BACKUP_CONVERT_TIMESTAMP", "true").lower() == "true"
    min_age_days = int(_get_env("BACKUP_LOCAL_MIN_AGE_DAYS", "7"))
    max_count = int(_get_env("BACKUP_LOCAL_MAX_COUNT", "7"))

    backups = []
    logger.info("starting clean up")
    for b in Path(backup_folder).iterdir():
        if not b.is_file():
            continue
        if not b.name.startswith(BACKUP_FILE_NAME_PREFIX):
            continue
        file_ts = parse_backup_timestamp(b.name, convert_ts)
        backups.append((file_ts, b))

    backups.sort(key=lambda x: x[0], reverse=True)
    now = datetime.now()

    for b in backups[max_count:]:
        backup_path = b[1]
        if now - b[0] < timedelta(days=min_age_days):
            logger.info('skipping cleanup of backup "%s" because it has not reached minimum age', backup_path)
            continue
        logger.info('deleting backup "%s"', backup_path)
        backup_path.unlink()
