import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.main import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_main_env(monkeypatch):
    """Set all required environment variables for main.py."""
    monkeypatch.setenv("UNIFI_SERVER_ADDRESS", "https://192.168.1.1:443")
    monkeypatch.setenv("UNIFI_USER", "admin")
    monkeypatch.setenv("UNIFI_PASSWORD", "secret")
    monkeypatch.setenv("UNIFI_VALIDATE_TLS", "false")
    monkeypatch.setenv("BACKUP_FOLDER", "/tmp/test_backups")
    monkeypatch.setenv("BACKUP_CONVERT_TIMESTAMP", "true")
    monkeypatch.setenv("BACKUP_INCOMPETENT_FS", "false")
    monkeypatch.setenv("BACKUP_LOCAL_MIN_AGE_DAYS", "7")
    monkeypatch.setenv("BACKUP_LOCAL_MAX_COUNT", "7")
    monkeypatch.setenv("SAMBA_HOST", "192.168.1.100")
    monkeypatch.setenv("SAMBA_SHARE", "Backups")
    monkeypatch.setenv("SAMBA_USER", "sambauser")
    monkeypatch.setenv("SAMBA_PASSWORD", "sambapass")
    monkeypatch.setenv("SAMBA_REMOTE_PATH", "unifi")
    monkeypatch.setenv("SAMBA_MIN_AGE_DAYS", "30")
    monkeypatch.setenv("SAMBA_MAX_COUNT", "30")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    # Disable email reporting
    monkeypatch.setenv("SMTP_ENABLED", "false")


# ---------------------------------------------------------------------------
# Successful run
# ---------------------------------------------------------------------------

class TestMainSuccessfulRun:
    def _make_mock_backup_path(self, tmp_path):
        backup_path = tmp_path / "unifi_os_backup_2024-11-01T03:00:05_autobackup.unifi"
        backup_path.write_bytes(b"backup data")
        return backup_path

    def test_full_success_sets_report_success(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        backup_path = self._make_mock_backup_path(tmp_path)

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", return_value=5),
            patch("src.main.upload"),
            patch("src.main.samba_cleanup", return_value=10),
            patch("src.main.rename_for_samba", side_effect=lambda p: p),
            patch("src.main.send_report") as mock_send,
        ):
            main()

        report = mock_send.call_args[0][0]
        assert report.success is True
        assert report.filename == backup_path.name

    def test_download_path_passed_to_upload(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        backup_path = self._make_mock_backup_path(tmp_path)

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", return_value=5),
            patch("src.main.upload") as mock_upload,
            patch("src.main.samba_cleanup", return_value=10),
            patch("src.main.rename_for_samba", side_effect=lambda p: p),
            patch("src.main.send_report"),
        ):
            main()

        # upload should be called with the backup path (after rename_for_samba)
        mock_upload.assert_called_once()
        called_path = mock_upload.call_args[0][0]
        assert isinstance(called_path, Path)

    def test_report_contains_download_info(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        backup_path = self._make_mock_backup_path(tmp_path)

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", return_value=5),
            patch("src.main.upload"),
            patch("src.main.samba_cleanup", return_value=10),
            patch("src.main.rename_for_samba", side_effect=lambda p: p),
            patch("src.main.send_report") as mock_send,
        ):
            main()

        report = mock_send.call_args[0][0]
        assert report.filename == backup_path.name
        assert report.filesize_bytes == len(backup_path.read_bytes())
        assert report.local_path == str(backup_path)
        assert report.local_cleanup_success is True
        assert report.local_backups_remaining == 5
        assert report.samba_upload_success is True
        assert report.samba_cleanup_success is True
        assert report.samba_backups_remaining == 10

    def test_incompetent_fs_skips_rename(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))
        monkeypatch.setenv("BACKUP_INCOMPETENT_FS", "true")

        # File with colons in the name (not yet renamed)
        backup_path = tmp_path / "unifi_os_backup_2024-11-01T03:00:05_autobackup.unifi"
        backup_path.write_bytes(b"backup data")

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", return_value=5),
            patch("src.main.upload") as mock_upload,
            patch("src.main.samba_cleanup", return_value=10),
            patch("src.main.send_report"),
        ):
            main()

        # upload should be called with the original path (colons preserved)
        called_path = mock_upload.call_args[0][0]
        assert ":" in str(called_path)


# ---------------------------------------------------------------------------
# Download failure
# ---------------------------------------------------------------------------

class TestMainDownloadFailure:
    def test_download_failure_sets_failed_status(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        with (
            patch("src.main.download", side_effect=ConnectionError("network error")),
            patch("src.main.local_cleanup", return_value=0),
            patch("src.main.samba_cleanup", return_value=0),
            patch("src.main.send_report") as mock_send,
        ):
            main()

        report = mock_send.call_args[0][0]
        assert report.success is False
        assert "Download failed" in report.errors
        assert report.filename is None

    def test_download_failure_skips_samba_upload(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        with (
            patch("src.main.download", side_effect=ConnectionError("network error")),
            patch("src.main.local_cleanup", return_value=0),
            patch("src.main.samba_cleanup", return_value=0),
            patch("src.main.send_report") as mock_send,
        ):
            main()

        report = mock_send.call_args[0][0]
        assert "Samba upload skipped — no backup available" in report.errors


# ---------------------------------------------------------------------------
# Partial failure
# ---------------------------------------------------------------------------

class TestMainPartialFailure:
    def test_local_cleanup_failure(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        backup_path = tmp_path / "unifi_os_backup_2024-11-01T03:00:05_autobackup.unifi"
        backup_path.write_bytes(b"backup data")

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", side_effect=OSError("disk full")),
            patch("src.main.upload"),
            patch("src.main.samba_cleanup", return_value=10),
            patch("src.main.rename_for_samba", side_effect=lambda p: p),
            patch("src.main.send_report") as mock_send,
        ):
            main()

        report = mock_send.call_args[0][0]
        assert report.success is False
        assert "Local cleanup failed" in report.errors

    def test_samba_upload_failure(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        backup_path = tmp_path / "unifi_os_backup_2024-11-01T03:00:05_autobackup.unifi"
        backup_path.write_bytes(b"backup data")

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", return_value=5),
            patch("src.main.upload", side_effect=ConnectionError("smb timeout")),
            patch("src.main.samba_cleanup", return_value=10),
            patch("src.main.rename_for_samba", side_effect=lambda p: p),
            patch("src.main.send_report") as mock_send,
        ):
            main()

        report = mock_send.call_args[0][0]
        assert report.success is False
        assert "Samba upload failed" in report.errors

    def test_samba_cleanup_failure(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        backup_path = tmp_path / "unifi_os_backup_2024-11-01T03:00:05_autobackup.unifi"
        backup_path.write_bytes(b"backup data")

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", return_value=5),
            patch("src.main.upload"),
            patch("src.main.samba_cleanup", side_effect=ConnectionError("smb error")),
            patch("src.main.rename_for_samba", side_effect=lambda p: p),
            patch("src.main.send_report") as mock_send,
        ):
            main()

        report = mock_send.call_args[0][0]
        assert report.success is False
        assert "Samba cleanup failed" in report.errors


# ---------------------------------------------------------------------------
# Report sending failure
# ---------------------------------------------------------------------------

class TestMainReportFailure:
    def test_report_failure_does_not_crash(self, monkeypatch, tmp_path):
        _setup_main_env(monkeypatch)
        monkeypatch.setenv("BACKUP_FOLDER", str(tmp_path))

        backup_path = tmp_path / "unifi_os_backup_2024-11-01T03:00:05_autobackup.unifi"
        backup_path.write_bytes(b"backup data")

        with (
            patch("src.main.download", return_value=backup_path),
            patch("src.main.local_cleanup", return_value=5),
            patch("src.main.upload"),
            patch("src.main.samba_cleanup", return_value=10),
            patch("src.main.rename_for_samba", side_effect=lambda p: p),
            patch("src.main.send_report", side_effect=ConnectionError("smtp down")),
        ):
            # Should not raise — report failure is caught
            main()
