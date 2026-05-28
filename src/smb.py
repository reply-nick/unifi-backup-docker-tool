from datetime import datetime, timedelta
from pathlib import Path

from smbprotocol.connection import Connection
from smbprotocol.open import (
    Open,
    FilePipePrinterAccessMask,
    CreateOptions,
    FileAttributes,
    ShareAccess,
    CreateDisposition,
    ImpersonationLevel,
    FileInformationClass,
    DirectoryAccessMask,
)
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect

import logging
import os
import uuid

from utils import BACKUP_FILE_NAME_PREFIX, parse_backup_timestamp

logger = logging.getLogger(__name__)


def _get_samba_config():
    host = os.environ.get("SAMBA_HOST")
    share = os.environ.get("SAMBA_SHARE")
    user = os.environ.get("SAMBA_USER")
    password = os.environ.get("SAMBA_PASSWORD")
    domain = os.environ.get("SAMBA_DOMAIN", "")
    remote_path = os.environ.get("SAMBA_REMOTE_PATH", "unifi")
    if not all([host, share, user, password, remote_path]):
        raise EnvironmentError("Missing required Samba environment variables")
    remote_path = remote_path.strip("/")
    return host, share, user, password, domain, remote_path


def _create_session(host, user, password):
    guid = uuid.uuid4()
    conn = Connection(guid, host)
    conn.connect()
    session = Session(conn, username=user, password=password)
    session.connect()
    return conn, session


def _connect_share(session, share):
    tree = TreeConnect(session, share)
    tree.connect()
    return tree


def _ensure_dir_exists(tree, path):
    parts = [p for p in path.split("/") if p]
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        try:
            dir_open = Open(tree, current)
            dir_open.create(
                impersonation_level=ImpersonationLevel.Impersonation,
                desired_access=DirectoryAccessMask.FILE_ADD_FILE | DirectoryAccessMask.FILE_ADD_SUBDIRECTORY,
                file_attributes=FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
                share_access=ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE | ShareAccess.FILE_SHARE_DELETE,
                create_disposition=CreateDisposition.FILE_OPEN_IF,
                create_options=CreateOptions.FILE_DIRECTORY_FILE,
            )
            dir_open.close()
        except Exception:
            pass


def upload(local_file_path: Path) -> None:
    logger.info("uploading %s", local_file_path)
    host, share, user, password, domain, remote_path = _get_samba_config()

    conn, session = _create_session(host, user, password)
    try:
        tree = _connect_share(session, share)

        _ensure_dir_exists(tree, remote_path)
        remote_full_path = f"{remote_path}/{local_file_path.name}"

        with open(str(local_file_path), "rb") as f:
            data = f.read()

        file_open = Open(tree, remote_full_path)
        file_open.create(
            impersonation_level=ImpersonationLevel.Impersonation,
            desired_access=FilePipePrinterAccessMask.GENERIC_ALL,
            file_attributes=FileAttributes.FILE_ATTRIBUTE_NORMAL,
            share_access=ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE | ShareAccess.FILE_SHARE_DELETE,
            create_disposition=CreateDisposition.FILE_OPEN_IF,
            create_options=0,
        )
        chunk_size = 4 * 1024 * 1024
        for i in range(0, len(data), chunk_size):
            chunk = data[i : i + chunk_size]
            file_open.write(chunk)
        file_open.close()

        logger.info("uploaded %s to %s/", local_file_path.name, remote_path)
    finally:
        try:
            tree.disconnect()
        except Exception:
            pass


def cleanup() -> None:
    logger.info("starting samba cleanup")
    host, share, user, password, domain, remote_path = _get_samba_config()
    min_age_days = int(os.environ.get("SAMBA_MIN_AGE_DAYS", "30"))
    max_count = int(os.environ.get("SAMBA_MAX_COUNT", "30"))
    convert_ts = os.environ.get("BACKUP_CONVERT_TIMESTAMP", "true").lower() == "true"

    conn, session = _create_session(host, user, password)

    try:
        tree = _connect_share(session, share)

        try:
            dir_open = Open(tree, remote_path)
            dir_open.create(
                impersonation_level=ImpersonationLevel.Impersonation,
                desired_access=DirectoryAccessMask.FILE_LIST_DIRECTORY,
                file_attributes=FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
                share_access=ShareAccess.FILE_SHARE_READ,
                create_disposition=CreateDisposition.FILE_OPEN,
                create_options=CreateOptions.FILE_DIRECTORY_FILE,
            )
        except Exception:
            logger.info("remote path %s does not exist, skipping cleanup", remote_path)
            return

        files = dir_open.query_directory(
            pattern=f"{BACKUP_FILE_NAME_PREFIX}*",
            file_information_class=FileInformationClass.FILE_NAMES_INFORMATION,
        )
        dir_open.close()

        backups = []
        for f in files:
            name = f["file_name"].get_value().decode("utf-16-le").rstrip("\x00")
            if not name.startswith(BACKUP_FILE_NAME_PREFIX):
                continue
            file_ts = parse_backup_timestamp(name, convert_ts)
            backups.append((file_ts, name))

        backups.sort(key=lambda x: x[0], reverse=True)
        now = datetime.now()

        for b in backups[max_count:]:
            file_ts, name = b
            if now - file_ts < timedelta(days=min_age_days):
                logger.info("skipping cleanup of %s because it has not reached minimum age", name)
                continue
            remote_full_path = os.path.join(remote_path, name)
            try:
                file_open = Open(tree, remote_full_path)
                file_open.create(
                    impersonation_level=ImpersonationLevel.Impersonation,
                    desired_access=FilePipePrinterAccessMask.DELETE,
                    file_attributes=FileAttributes.FILE_ATTRIBUTE_NORMAL,
                    share_access=ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
                    create_disposition=CreateDisposition.FILE_OPEN,
                    create_options=CreateOptions.FILE_NON_DIRECTORY_FILE | CreateOptions.FILE_DELETE_ON_CLOSE,
                )
                file_open.close()
                logger.info("deleted %s from samba share", name)
            except Exception as e:
                logger.error("failed to delete %s: %s", name, e)
    finally:
        try:
            tree.disconnect()
        except Exception:
            pass
