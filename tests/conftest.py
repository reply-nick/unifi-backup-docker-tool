import os
import sys
import tempfile
from datetime import datetime

import pytest

# The source files use bare module imports (e.g. "from utils import ...").
# Add the src/ directory so those imports resolve.
_src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, _src_dir)

from src.reporter import BackupReport

# main.py creates a FileHandler at module level for /var/log/unifi-backup.log.
# Outside Docker we can't write there, so point it at a temp file.
_test_log = os.path.join(tempfile.gettempdir(), "unifi-backup-test.log")
os.environ["LOG_FILE"] = _test_log


SMTP_VARS = [
    "SMTP_ENABLED",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_TO",
    "SMTP_TLS",
]

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


@pytest.fixture
def isolated_env(monkeypatch):
    """Clear all SMTP env vars before each test and restore after."""
    for var in SMTP_VARS:
        monkeypatch.delenv(var, raising=False)
    yield
    # No restoration needed — monkeypatch handles cleanup


@pytest.fixture
def full_env(isolated_env):
    """Set all SMTP vars to valid values."""
    for key, value in VALID_ENV.items():
        os.environ[key] = value
    return VALID_ENV.copy()


@pytest.fixture
def mock_report():
    """Create a fully-populated successful BackupReport."""
    return BackupReport(
        success=True,
        started_at=datetime(2024, 11, 1, 3, 0, 1),
        finished_at=datetime(2024, 11, 1, 3, 0, 47),
        duration_seconds=46.0,
        filename="unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi",
        filesize_bytes=24300000,
        local_path="/backups/unifi_os_backup_2024-11-01T03:00:05_autobackup.unfi",
        local_cleanup_success=True,
        local_backups_remaining=7,
        local_cleanup_error=None,
        samba_upload_success=True,
        samba_upload_error=None,
        samba_cleanup_success=True,
        samba_backups_remaining=14,
        samba_cleanup_error=None,
        errors=[],
    )
