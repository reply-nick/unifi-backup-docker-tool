import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.smb import cleanup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockFileInfo:
    """Minimal mock of smbprotocol's file info object with get_value()."""

    def __init__(self, name_bytes: bytes):
        self._name_bytes = name_bytes

    def get_value(self) -> bytes:
        return self._name_bytes


def _make_mock_file(file_name: str, timestamp=None) -> dict:
    """Create a mock SMB file entry that mimics smbprotocol's response.

    The smbprotocol query_directory returns an iterable of dicts where
    ``dict["file_name"]`` is an object with ``.get_value()`` returning
    UTF-16-LE encoded bytes.  UTF-16-LE requires an even byte count,
    so we pad with two null bytes (null-terminated wide string).
    """
    if timestamp is None:
        timestamp = datetime.now() - timedelta(days=10)
    name_bytes = file_name.encode("utf-16-le") + b"\x00\x00"
    return {"file_name": _MockFileInfo(name_bytes)}


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

class TestSmbCleanup:
    def _setup_env(self, monkeypatch):
        monkeypatch.setenv("SAMBA_HOST", "192.168.1.100")
        monkeypatch.setenv("SAMBA_SHARE", "Backups")
        monkeypatch.setenv("SAMBA_USER", "sambauser")
        monkeypatch.setenv("SAMBA_PASSWORD", "sambapass")
        monkeypatch.setenv("SAMBA_REMOTE_PATH", "unifi")
        monkeypatch.setenv("SAMBA_MIN_AGE_DAYS", "7")
        monkeypatch.setenv("SAMBA_MAX_COUNT", "3")
        monkeypatch.setenv("BACKUP_CONVERT_TIMESTAMP", "true")

    def _make_mock_dir_open(self, files):
        """Create a mock dir_open that returns the given files on query_directory."""
        mock_dir_open = MagicMock()
        mock_dir_open.query_directory.side_effect = lambda *a, **kw: iter(files)
        mock_dir_open.create = MagicMock()
        mock_dir_open.close = MagicMock()
        return mock_dir_open

    def test_cleanup_removes_old_excess(self, monkeypatch):
        self._setup_env(monkeypatch)
        now = datetime.now()

        files = []
        for i in range(5):
            ts = now - timedelta(days=i + 10)
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
            files.append(_make_mock_file(name, ts))

        mock_dir_open = self._make_mock_dir_open(files)
        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect = MagicMock()
        mock_tree.__enter__ = MagicMock(return_value=mock_tree)
        mock_tree.__exit__ = MagicMock(return_value=False)

        mock_session = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
            patch("src.smb.Open", return_value=mock_dir_open),
        ):
            remaining = cleanup()

        assert remaining == 3

    def test_cleanup_skips_young_files(self, monkeypatch):
        self._setup_env(monkeypatch)
        now = datetime.now()

        files = []
        for i in range(5):
            ts = now - timedelta(days=i + 1)  # all within 7 days
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
            files.append(_make_mock_file(name, ts))

        mock_dir_open = self._make_mock_dir_open(files)
        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect = MagicMock()

        mock_session = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
            patch("src.smb.Open", return_value=mock_dir_open),
        ):
            remaining = cleanup()

        # All 5 remain — 3 newest kept by count, 2 oldest skipped by age
        assert remaining == 5

    def test_cleanup_returns_none_when_remote_path_missing(self, monkeypatch):
        self._setup_env(monkeypatch)

        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect = MagicMock()

        mock_session = MagicMock()
        mock_conn = MagicMock()

        # Open.create raises when the remote path doesn't exist
        mock_dir_open = MagicMock()
        mock_dir_open.create.side_effect = Exception("path not found")

        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
            patch("src.smb.Open", return_value=mock_dir_open),
        ):
            result = cleanup()

        assert result is None

    def test_cleanup_ignores_non_backup_files(self, monkeypatch):
        self._setup_env(monkeypatch)
        now = datetime.now()

        files = []
        # Add a non-backup file
        non_backup = _make_mock_file("some_other_file.txt")
        files.append(non_backup)

        # Add a backup file
        ts = now - timedelta(days=10)
        name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
        files.append(_make_mock_file(name, ts))

        mock_dir_open = self._make_mock_dir_open(files)
        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect = MagicMock()

        mock_session = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
            patch("src.smb.Open", return_value=mock_dir_open),
        ):
            remaining = cleanup()

        assert remaining == 1

    def test_cleanup_with_dot_timestamps(self, monkeypatch):
        self._setup_env(monkeypatch)
        now = datetime.now()

        files = []
        for i in range(4):
            ts = now - timedelta(days=i + 10)
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H.%M.%S')}_autobackup.unifi"
            files.append(_make_mock_file(name, ts))

        mock_dir_open = self._make_mock_dir_open(files)
        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect = MagicMock()

        mock_session = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
            patch("src.smb.Open", return_value=mock_dir_open),
        ):
            remaining = cleanup()

        assert remaining == 3

    def test_cleanup_respects_max_count_only(self, monkeypatch):
        monkeypatch.setenv("SAMBA_HOST", "192.168.1.100")
        monkeypatch.setenv("SAMBA_SHARE", "Backups")
        monkeypatch.setenv("SAMBA_USER", "sambauser")
        monkeypatch.setenv("SAMBA_PASSWORD", "sambapass")
        monkeypatch.setenv("SAMBA_REMOTE_PATH", "unifi")
        monkeypatch.setenv("SAMBA_MIN_AGE_DAYS", "0")
        monkeypatch.setenv("SAMBA_MAX_COUNT", "2")
        monkeypatch.setenv("BACKUP_CONVERT_TIMESTAMP", "true")

        now = datetime.now()
        files = []
        for i in range(5):
            ts = now - timedelta(days=i + 10)
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
            files.append(_make_mock_file(name, ts))

        mock_dir_open = self._make_mock_dir_open(files)
        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect = MagicMock()

        mock_session = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
            patch("src.smb.Open", return_value=mock_dir_open),
        ):
            remaining = cleanup()

        assert remaining == 2

    def test_cleanup_disconnected_on_exit(self, monkeypatch):
        self._setup_env(monkeypatch)

        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect = MagicMock()
        mock_tree.__enter__ = MagicMock(return_value=mock_tree)
        mock_tree.__exit__ = MagicMock(return_value=False)

        mock_session = MagicMock()
        mock_conn = MagicMock()

        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
        ):
            cleanup()

        mock_tree.disconnect.assert_called_once()

    def test_cleanup_handles_disconnect_failure(self, monkeypatch):
        self._setup_env(monkeypatch)

        mock_tree = MagicMock()
        mock_tree.connect = MagicMock()
        mock_tree.disconnect.side_effect = Exception("disconnect failed")

        mock_session = MagicMock()
        mock_conn = MagicMock()

        # Should not raise even if disconnect fails
        with (
            patch("src.smb._create_session", return_value=(mock_conn, mock_session)),
            patch("src.smb._connect_share", return_value=mock_tree),
        ):
            result = cleanup()
            # cleanup will fail when trying to Open the directory, but that
            # should be caught and return None
            assert result is None
