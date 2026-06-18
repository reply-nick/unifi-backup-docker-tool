import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.backup import cleanup, download


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

class TestDownload:
    def _setup_env(self, monkeypatch):
        monkeypatch.setenv("UNIFI_SERVER_ADDRESS", "https://192.168.1.1:443")
        monkeypatch.setenv("UNIFI_USER", "admin")
        monkeypatch.setenv("UNIFI_PASSWORD", "secret")
        monkeypatch.setenv("UNIFI_VALIDATE_TLS", "false")
        monkeypatch.setenv("BACKUP_FOLDER", "/tmp/test_backups")
        monkeypatch.setenv("BACKUP_CONVERT_TIMESTAMP", "true")
        monkeypatch.setenv("BACKUP_INCOMPETENT_FS", "false")

    def _make_response(self, filename="unifi_os_backup_1748395312000_autobackup"):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {
            "Content-Type": "application/octet-stream",
            "filename": filename,
        }
        resp.content = b"backup content here"
        resp.raise_for_status = MagicMock()
        return resp

    def test_download_success(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        mock_resp = self._make_response()
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session.get.return_value = mock_resp

        with patch("src.backup.requests.Session", return_value=mock_session):
            result = download()

        assert result.name == "unifi_os_backup_2025-05-27T20:21:52_autobackup"
        assert result.exists()

    def test_download_with_incompetent_fs(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))
        monkeypatch.setenv("BACKUP_INCOMPETENT_FS", "true")

        mock_resp = self._make_response()
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session.get.return_value = mock_resp

        with patch("src.backup.requests.Session", return_value=mock_session):
            result = download()

        assert ":" not in result.name
        assert result.name == "unifi_os_backup_2025-05-27T20.21.52_autobackup"

    def test_download_trailing_slash_stripped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("UNIFI_SERVER_ADDRESS", "https://192.168.1.1:443/")
        monkeypatch.setenv("UNIFI_USER", "admin")
        monkeypatch.setenv("UNIFI_PASSWORD", "secret")
        monkeypatch.setenv("UNIFI_VALIDATE_TLS", "false")
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))
        monkeypatch.setenv("BACKUP_CONVERT_TIMESTAMP", "true")
        monkeypatch.setenv("BACKUP_INCOMPETENT_FS", "false")

        mock_resp = self._make_response()
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session.get.return_value = mock_resp

        with patch("src.backup.requests.Session", return_value=mock_session):
            download()

        mock_session.post.assert_called_once()
        call_url = mock_session.post.call_args[0][0]
        assert call_url == "https://192.168.1.1:443/api/auth/login"


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def _setup_env(self, monkeypatch):
        monkeypatch.setenv("BACKUP_FOLDER", "/tmp/test_backups")
        monkeypatch.setenv("BACKUP_CONVERT_TIMESTAMP", "true")
        monkeypatch.setenv("BACKUP_LOCAL_MIN_AGE_DAYS", "7")
        monkeypatch.setenv("BACKUP_LOCAL_MAX_COUNT", "3")

    def test_cleanup_removes_old_excess(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        now = datetime.now()
        # Create 5 backups — 3 newest should be kept, 2 oldest deleted
        for i in range(5):
            ts = now - timedelta(days=i + 10)  # all older than 7 days
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
            (tmp_path / name).touch()

        remaining = cleanup()
        assert remaining == 3

        remaining_files = [f for f in tmp_path.iterdir() if f.name.startswith("unifi_os_backup_")]
        assert len(remaining_files) == 3

    def test_cleanup_skips_young_files(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        now = datetime.now()
        # Create 5 backups — 2 are old, 3 are recent (within 7 days)
        for i in range(5):
            days_ago = i + 1
            ts = now - timedelta(days=days_ago)
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
            (tmp_path / name).touch()

        remaining = cleanup()
        # All 5 should remain — 3 newest kept by count, 2 oldest skipped by age
        assert remaining == 5
        assert len([f for f in tmp_path.iterdir() if f.name.startswith("unifi_os_backup_")]) == 5

    def test_cleanup_respects_max_count(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))
        monkeypatch.setenv("BACKUP_CONVERT_TIMESTAMP", "true")
        monkeypatch.setenv("BACKUP_LOCAL_MIN_AGE_DAYS", "0")
        monkeypatch.setenv("BACKUP_LOCAL_MAX_COUNT", "2")

        now = datetime.now()
        for i in range(4):
            ts = now - timedelta(days=i + 10)
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
            (tmp_path / name).touch()

        remaining = cleanup()
        assert remaining == 2

    def test_cleanup_ignores_non_backup_files(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        now = datetime.now()
        # Create a backup and a non-backup file
        ts = now - timedelta(days=10)
        name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
        (tmp_path / name).touch()
        (tmp_path / "some_other_file.txt").touch()

        remaining = cleanup()
        assert remaining == 1

    def test_cleanup_ignores_directories(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        now = datetime.now()
        ts = now - timedelta(days=10)
        name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
        (tmp_path / name).touch()
        (tmp_path / "subdir").mkdir()

        remaining = cleanup()
        assert remaining == 1

    def test_cleanup_empty_folder(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        remaining = cleanup()
        assert remaining == 0

    def test_cleanup_with_dot_timestamps(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        now = datetime.now()
        for i in range(4):
            ts = now - timedelta(days=i + 10)
            # Dot-separated timestamps (from incompetent FS or rename_for_samba)
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H.%M.%S')}_autobackup.unifi"
            (tmp_path / name).touch()

        remaining = cleanup()
        assert remaining == 3

    def test_cleanup_no_deletion_under_max_count(self, monkeypatch, tmp_path):
        self._setup_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        now = datetime.now()
        for i in range(2):
            ts = now - timedelta(days=i + 10)
            name = f"unifi_os_backup_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_autobackup.unifi"
            (tmp_path / name).touch()

        remaining = cleanup()
        assert remaining == 2
