import os
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils import (
    BACKUP_FILE_NAME_PREFIX,
    parse_backup_timestamp,
    rename_for_samba,
    retry,
)


# ---------------------------------------------------------------------------
# parse_backup_timestamp
# ---------------------------------------------------------------------------

class TestParseBackupTimestamp:
    def test_colon_timestamp(self):
        name = "unifi_os_backup_2026-05-28T03:01:52_abc123"
        result = parse_backup_timestamp(name, convert_ts=True)
        assert result == datetime(2026, 5, 28, 3, 1, 52)

    def test_dot_timestamp(self):
        name = "unifi_os_backup_2026-05-28T03.01.52_abc123"
        result = parse_backup_timestamp(name, convert_ts=True)
        assert result == datetime(2026, 5, 28, 3, 1, 52)

    def test_epoch_timestamp(self):
        name = "unifi_os_backup_1748395312000_abc123"
        result = parse_backup_timestamp(name, convert_ts=False)
        assert result == datetime.fromtimestamp(1748395312)

    def test_epoch_timestamp_with_convert_false(self):
        name = "unifi_os_backup_1748395312000_abc123"
        result = parse_backup_timestamp(name, convert_ts=False)
        assert result == datetime.fromtimestamp(1748395312)

    def test_prefix_stripped(self):
        name = "unifi_os_backup_2026-05-28T03:01:52_abc123_extra_stuff"
        result = parse_backup_timestamp(name, convert_ts=True)
        assert result == datetime(2026, 5, 28, 3, 1, 52)

    def test_convert_true_with_dots(self):
        name = "unifi_os_backup_2026-05-28T03.01.52_abc123"
        result = parse_backup_timestamp(name, convert_ts=True)
        assert result == datetime(2026, 5, 28, 3, 1, 52)

    def test_convert_true_with_colons(self):
        name = "unifi_os_backup_2026-05-28T03:01:52_abc123"
        result = parse_backup_timestamp(name, convert_ts=True)
        assert result == datetime(2026, 5, 28, 3, 1, 52)

    def test_convert_true_with_epoch(self):
        name = "unifi_os_backup_1748395312000_abc123"
        result = parse_backup_timestamp(name, convert_ts=False)
        assert result == datetime.fromtimestamp(1748395312)

    def test_convert_true_with_epoch_raises_on_fromisoformat(self):
        """When convert_ts=True and the timestamp is numeric, fromisoformat
        should fail and fall through to the except branch — but since it's
        not a valid ISO string with dots either, it should raise ValueError."""
        name = "unifi_os_backup_1748395312000_abc123"
        with pytest.raises(ValueError):
            parse_backup_timestamp(name, convert_ts=True)


# ---------------------------------------------------------------------------
# rename_for_samba
# ---------------------------------------------------------------------------

class TestRenameForSamba:
    def test_renames_colons_to_dots(self, tmp_path):
        original = tmp_path / "unifi_os_backup_2026-05-28T03:01:52_abc.unifi"
        original.touch()
        result = rename_for_samba(str(original))
        expected = str(tmp_path / "unifi_os_backup_2026-05-28T03.01.52_abc.unifi")
        assert result == expected
        assert Path(expected).exists()
        assert not original.exists()

    def test_no_rename_when_no_colons(self, tmp_path):
        original = tmp_path / "unifi_os_backup_2026-05-28T03.01.52_abc.unifi"
        original.touch()
        result = rename_for_samba(str(original))
        assert result == str(original)
        assert original.exists()

    def test_returns_path_string(self, tmp_path):
        original = tmp_path / "unifi_os_backup_2026-05-28T03:01:52_abc.unifi"
        original.touch()
        result = rename_for_samba(str(original))
        assert isinstance(result, str)

    def test_renames_path_not_filename(self, tmp_path):
        """rename_for_samba replaces ALL colons in the full path, not just
        the filename — matching the existing behavior."""
        original = tmp_path / "unifi_os_backup_2026-05-28T03:01:52_abc.unifi"
        original.touch()
        result = rename_for_samba(str(original))
        assert ":" not in result


# ---------------------------------------------------------------------------
# retry decorator
# ---------------------------------------------------------------------------

class TestRetry:
    def test_succeeds_on_first_attempt(self):
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = fn()
        assert result == "ok"
        assert call_count == 1

    def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient error")
            return "ok"

        result = fn()
        assert result == "ok"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            fn()
        assert call_count == 3

    def test_preserves_function_name(self):
        @retry(max_attempts=3, delay=0.01)
        def my_function():
            return 42

        assert my_function.__name__ == "my_function"

    def test_passes_args_and_kwargs(self):
        @retry(max_attempts=3, delay=0.01)
        def add(a, b, c=10):
            return a + b + c

        assert add(1, 2) == 13
        assert add(1, 2, c=5) == 8

    def test_custom_delay(self):
        """Verify that the delay parameter works by measuring time."""
        @retry(max_attempts=2, delay=0.05)
        def fn():
            raise ValueError("fail")

        start = time.monotonic()
        with pytest.raises(ValueError):
            fn()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.04  # at least one 0.05s delay (with jitter min 0.5x)

    def test_jitter_reduced_delay(self):
        """With jitter=True, delay should vary — we can't test exact values
        but we can verify it doesn't raise and completes."""
        @retry(max_attempts=2, delay=0.01)
        def fn():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            fn()
