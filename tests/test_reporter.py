import os
import smtplib
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.reporter import (
    BackupReport,
    _build_body,
    _format_duration,
    _human_readable_size,
    send_report,
)

VALID_ENV = {
    "SMTP_ENABLED": "true",
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "test@gmail.com",
    "SMTP_PASSWORD": "secret",
    "SMTP_FROM": "test@gmail.com",
    "SMTP_TO": "recipient@gmail.com",
    "SMTP_TLS": "true",
}


# ---------------------------------------------------------------------------
# _human_readable_size
# ---------------------------------------------------------------------------

class TestHumanReadableSize:
    def test_none_returns_na(self):
        assert _human_readable_size(None) == "N/A"

    def test_zero_bytes(self):
        assert _human_readable_size(0) == "0 B"

    def test_small_bytes(self):
        assert _human_readable_size(500) == "500 B"

    def test_almost_one_kb(self):
        assert _human_readable_size(1023) == "1023 B"

    def test_one_kb(self):
        assert _human_readable_size(1024) == "1.0 KB"

    def test_one_point_five_kb(self):
        assert _human_readable_size(1536) == "1.5 KB"

    def test_one_mb(self):
        assert _human_readable_size(1048576) == "1.0 MB"

    def test_23_mb(self):
        assert _human_readable_size(24300000) == "23.2 MB"

    def test_one_gb(self):
        assert _human_readable_size(1073741824) == "1.0 GB"

    def test_two_gb(self):
        assert _human_readable_size(2147483648) == "2.0 GB"

    def test_one_tb(self):
        assert _human_readable_size(1099511627776) == "1.0 TB"


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_none_returns_na(self):
        assert _format_duration(None) == "N/A"

    def test_zero_seconds(self):
        assert _format_duration(0) == "0s"

    def test_thirty_seconds(self):
        assert _format_duration(30) == "30s"

    def test_fifty_nine_seconds(self):
        assert _format_duration(59) == "59s"

    def test_one_minute(self):
        assert _format_duration(60) == "1m 0s"

    def test_one_minute_thirty_seconds(self):
        assert _format_duration(90) == "1m 30s"

    def test_two_minutes_five_seconds(self):
        assert _format_duration(125) == "2m 5s"

    def test_one_hour(self):
        assert _format_duration(3600) == "1h 0m 0s"

    def test_one_hour_two_minutes_five_seconds(self):
        assert _format_duration(3725) == "1h 2m 5s"


# ---------------------------------------------------------------------------
# _build_body
# ---------------------------------------------------------------------------

class TestBuildBody:
    def test_body_success_full(self, mock_report):
        body = _build_body(mock_report)
        assert "Status   : SUCCESS" in body
        assert "unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi" in body
        assert "23.2 MB" in body
        assert "/backups/unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi" in body
        assert "Cleanup  : OK" in body
        assert "Remaining: 7 backups" in body
        assert "Upload   : OK" in body
        assert "Remaining: 14 backups" in body
        assert "None" in body

    def test_body_failed_download(self):
        report = BackupReport(
            success=False,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            finished_at=datetime(2024, 11, 1, 3, 0, 47),
            errors=["Download failed"],
        )
        body = _build_body(report)
        assert "Status   : FAILED" in body
        assert "File     : N/A" in body
        assert "Size     : N/A" in body
        assert "Saved to : N/A" in body

    def test_body_with_errors(self):
        report = BackupReport(
            success=False,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            errors=["Download failed", "Samba upload skipped"],
        )
        body = _build_body(report)
        assert "Download failed" in body
        assert "Samba upload skipped" in body

    def test_body_with_upload_error(self):
        report = BackupReport(
            success=False,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            samba_upload_success=False,
            samba_upload_error="Connection timeout",
        )
        body = _build_body(report)
        assert "Upload   : FAILED — Connection timeout" in body

    def test_body_na_remaining(self):
        report = BackupReport(
            success=False,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            local_backups_remaining=None,
            samba_backups_remaining=None,
        )
        body = _build_body(report)
        assert "Remaining: N/A backups" in body

    def test_body_contains_all_sections(self, mock_report):
        body = _build_body(mock_report)
        for section in [
            "UniFi Backup Report",
            "Download",
            "Local Storage",
            "Samba Upload",
            "Samba Storage",
            "Errors / Warnings",
        ]:
            assert section in body

    def test_body_trailing_newline(self, mock_report):
        body = _build_body(mock_report)
        assert body.endswith("\n")

    def test_body_sets_duration_on_report(self, mock_report):
        mock_report.duration_seconds = None
        _build_body(mock_report)
        assert mock_report.duration_seconds == 46.0

    def test_body_finished_not_set(self):
        report = BackupReport(
            success=False,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            finished_at=None,
        )
        body = _build_body(report)
        assert "Finished : N/A" in body


# ---------------------------------------------------------------------------
# send_report — disabled
# ---------------------------------------------------------------------------

class TestSendReportDisabled:
    def test_disabled_skips(self, isolated_env):
        os.environ["SMTP_ENABLED"] = "false"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.logger") as mock_logger:
            send_report(report)

        mock_logger.info.assert_called_with(
            "email reporting disabled (SMTP_ENABLED is not true)"
        )


# ---------------------------------------------------------------------------
# send_report — missing config
# ---------------------------------------------------------------------------

class TestSendReportMissingConfig:
    def test_missing_host_skips(self, isolated_env, full_env):
        del os.environ["SMTP_HOST"]
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.logger") as mock_logger:
            send_report(report)

        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args[0][1]
        assert "SMTP_HOST" in call_args

    def test_missing_multiple_vars(self, isolated_env, full_env):
        del os.environ["SMTP_USER"]
        del os.environ["SMTP_PASSWORD"]
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.logger") as mock_logger:
            send_report(report)

        call_args = mock_logger.warning.call_args[0][1]
        assert "SMTP_USER" in call_args
        assert "SMTP_PASSWORD" in call_args

    def test_all_missing_vars_logged(self, isolated_env):
        os.environ["SMTP_ENABLED"] = "true"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.logger") as mock_logger:
            send_report(report)

        call_args = mock_logger.warning.call_args[0][1]
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO"]:
            assert var in call_args
        # SMTP_PORT has a default of "587" so it is not missing


# ---------------------------------------------------------------------------
# send_report — case insensitive
# ---------------------------------------------------------------------------

class TestSendReportCaseInsensitive:
    def test_enabled_true_uppercase(self, isolated_env):
        os.environ["SMTP_ENABLED"] = "TRUE"
        for k, v in VALID_ENV.items():
            if k != "SMTP_ENABLED":
                os.environ[k] = v
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP") as mock_smtp:
            send_report(report)
            mock_smtp.assert_called_once()

    def test_enabled_true_mixed_case(self, isolated_env):
        os.environ["SMTP_ENABLED"] = "True"
        for k, v in VALID_ENV.items():
            if k != "SMTP_ENABLED":
                os.environ[k] = v
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP") as mock_smtp:
            send_report(report)
            mock_smtp.assert_called_once()

    def test_tls_true_uppercase(self, isolated_env, full_env):
        os.environ["SMTP_TLS"] = "TRUE"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP") as mock_smtp:
            send_report(report)
            mock_smtp.assert_called_once()
            instance = mock_smtp.return_value
            instance.starttls.assert_called_once()

    def test_tls_false_uppercase(self, isolated_env, full_env):
        os.environ["SMTP_TLS"] = "FALSE"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP_SSL") as mock_ssl:
            send_report(report)
            mock_ssl.assert_called_once()


# ---------------------------------------------------------------------------
# send_report — port and TLS
# ---------------------------------------------------------------------------

class TestSendReportPortAndTls:
    def test_default_port_is_587(self, isolated_env, full_env):
        del os.environ["SMTP_PORT"]
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP") as mock_smtp:
            send_report(report)
            mock_smtp.assert_called_once()
            args = mock_smtp.call_args
            assert args[0][1] == 587

    def test_port_465_forces_ssl(self, isolated_env, full_env):
        os.environ["SMTP_PORT"] = "465"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP_SSL") as mock_ssl:
            send_report(report)
            mock_ssl.assert_called_once()

    def test_port_465_overrides_tls(self, isolated_env):
        os.environ["SMTP_ENABLED"] = "true"
        os.environ["SMTP_HOST"] = "smtp.gmail.com"
        os.environ["SMTP_PORT"] = "465"
        os.environ["SMTP_USER"] = "test@gmail.com"
        os.environ["SMTP_PASSWORD"] = "secret"
        os.environ["SMTP_FROM"] = "test@gmail.com"
        os.environ["SMTP_TO"] = "recipient@gmail.com"
        os.environ["SMTP_TLS"] = "true"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP_SSL") as mock_ssl:
            send_report(report)
            mock_ssl.assert_called_once()

    def test_tls_false_forces_ssl(self, isolated_env, full_env):
        os.environ["SMTP_TLS"] = "false"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP_SSL") as mock_ssl:
            send_report(report)
            mock_ssl.assert_called_once()

    def test_tls_false_with_port_465(self, isolated_env):
        os.environ["SMTP_ENABLED"] = "true"
        os.environ["SMTP_HOST"] = "smtp.gmail.com"
        os.environ["SMTP_PORT"] = "465"
        os.environ["SMTP_USER"] = "test@gmail.com"
        os.environ["SMTP_PASSWORD"] = "secret"
        os.environ["SMTP_FROM"] = "test@gmail.com"
        os.environ["SMTP_TO"] = "recipient@gmail.com"
        os.environ["SMTP_TLS"] = "false"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP_SSL") as mock_ssl:
            send_report(report)
            mock_ssl.assert_called_once()

    def test_starttls_default(self, isolated_env, full_env):
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP") as mock_smtp:
            send_report(report)
            mock_smtp.assert_called_once()
            instance = mock_smtp.return_value
            instance.starttls.assert_called_once()


# ---------------------------------------------------------------------------
# send_report — sends email
# ---------------------------------------------------------------------------

class TestSendReportSendsEmail:
    def test_sends_email_success(self, isolated_env, full_env):
        report = BackupReport(success=True, started_at=datetime.now())

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server) as mock_smtp:
            send_report(report)

        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()

    def test_subject_contains_filename(self, isolated_env, full_env):
        report = BackupReport(
            success=True,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            filename="unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi",
        )

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server) as mock_smtp:
            send_report(report)

        sent_msg = mock_server.send_message.call_args[0][0]
        assert "unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi" in sent_msg["Subject"]


# ---------------------------------------------------------------------------
# send_report — smtp failure
# ---------------------------------------------------------------------------

class TestSendReportSmtpFailure:
    def test_connection_refused_does_not_raise(self, isolated_env, full_env):
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ConnectionRefusedError("Connection refused")
            send_report(report)  # Should not raise

    def test_auth_error_does_not_raise(self, isolated_env, full_env):
        report = BackupReport(success=True, started_at=datetime.now())

        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(403, "Auth failed")
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)  # Should not raise


# ---------------------------------------------------------------------------
# send_report — subject
# ---------------------------------------------------------------------------

class TestSendReportSubject:
    def test_subject_with_filename(self, isolated_env, full_env):
        report = BackupReport(
            success=True,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            filename="unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi",
        )

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)

        sent_msg = mock_server.send_message.call_args[0][0]
        assert "[UniFi Backup]" in sent_msg["Subject"]
        assert "unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi" in sent_msg["Subject"]

    def test_subject_without_filename(self, isolated_env, full_env):
        report = BackupReport(
            success=True,
            started_at=datetime(2024, 11, 1, 3, 0, 1),
            filename=None,
        )

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)

        sent_msg = mock_server.send_message.call_args[0][0]
        assert "2024-11-01" in sent_msg["Subject"]

    def test_subject_success_emoji(self, isolated_env, full_env):
        report = BackupReport(success=True, started_at=datetime.now())

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)

        sent_msg = mock_server.send_message.call_args[0][0]
        assert "\u2705" in sent_msg["Subject"]

    def test_subject_failure_emoji(self, isolated_env, full_env):
        report = BackupReport(success=False, started_at=datetime.now())

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)

        sent_msg = mock_server.send_message.call_args[0][0]
        assert "\u274c" in sent_msg["Subject"]


# ---------------------------------------------------------------------------
# send_report — email headers
# ---------------------------------------------------------------------------

class TestSendReportEmailHeaders:
    def test_email_headers_set_correctly(self, isolated_env, full_env):
        report = BackupReport(success=True, started_at=datetime.now())

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)

        sent_msg = mock_server.send_message.call_args[0][0]
        assert sent_msg["From"] == "test@gmail.com"
        assert sent_msg["To"] == "recipient@gmail.com"


# ---------------------------------------------------------------------------
# send_report — edge cases
# ---------------------------------------------------------------------------

class TestSendReportEdgeCases:
    def test_empty_string_env_var_treated_as_missing(self, isolated_env):
        os.environ["SMTP_ENABLED"] = "true"
        os.environ["SMTP_HOST"] = "smtp.gmail.com"
        os.environ["SMTP_PORT"] = "587"
        os.environ["SMTP_USER"] = ""
        os.environ["SMTP_PASSWORD"] = "secret"
        os.environ["SMTP_FROM"] = "test@gmail.com"
        os.environ["SMTP_TO"] = "recipient@gmail.com"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.logger") as mock_logger:
            send_report(report)

        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args[0][1]
        assert "SMTP_USER" in call_args

    def test_port_as_string_converted(self, isolated_env, full_env):
        os.environ["SMTP_PORT"] = "587"
        report = BackupReport(success=True, started_at=datetime.now())

        with patch("src.reporter.smtplib.SMTP") as mock_smtp:
            send_report(report)
            mock_smtp.assert_called_once()

    def test_all_required_present_sends(self, isolated_env, full_env):
        report = BackupReport(success=True, started_at=datetime.now())

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)

        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()

    def test_env_vars_not_modified_after_send(self, isolated_env, full_env):
        original = full_env.copy()
        report = BackupReport(success=True, started_at=datetime.now())

        mock_server = MagicMock()
        with patch("src.reporter.smtplib.SMTP", return_value=mock_server):
            send_report(report)

        for key, value in original.items():
            assert os.environ.get(key) == value
