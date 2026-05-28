#!/usr/bin/env python3
"""Email reporting for UniFi backup runs using smtplib."""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class BackupReport:
    """Carries all report data through the backup run."""
    success: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None

    # Download
    filename: str | None = None
    filesize_bytes: int | None = None
    local_path: str | None = None

    # Local cleanup
    local_cleanup_success: bool = False
    local_backups_remaining: int | None = None
    local_cleanup_error: str | None = None

    # Samba upload
    samba_upload_success: bool = False
    samba_upload_error: str | None = None

    # Samba cleanup
    samba_cleanup_success: bool = False
    samba_backups_remaining: int | None = None
    samba_cleanup_error: str | None = None

    # General errors
    errors: list[str] = field(default_factory=list)


def _human_readable_size(size_bytes: int | None) -> str:
    """Format a byte count as KB, MB, or GB."""
    if size_bytes is None:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _format_duration(seconds: float | None) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds is None:
        return "N/A"
    minutes, secs = divmod(int(seconds), 60)
    hours, mins = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {mins}m {secs}s"
    elif minutes > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def _build_body(report: BackupReport) -> str:
    """Build a plain-text email body from a BackupReport."""
    status = "SUCCESS" if report.success else "FAILED"

    started = report.started_at.strftime("%Y-%m-%d %H:%M:%S") if report.started_at else "N/A"

    if report.finished_at:
        finished = report.finished_at.strftime("%Y-%m-%d %H:%M:%S")
        report.duration_seconds = (report.finished_at - report.started_at).total_seconds()
    else:
        finished = "N/A"

    lines = [
        "UniFi Backup Report",
        "===================",
        f"Status   : {status}",
        f"Started  : {started}",
        f"Finished : {finished}",
        f"Duration : {_format_duration(report.duration_seconds)}",
        "",
        "Download",
        "--------",
        f"File     : {report.filename or 'N/A'}",
        f"Size     : {_human_readable_size(report.filesize_bytes)}",
        f"Saved to : {report.local_path or 'N/A'}",
        "",
        "Local Storage",
        "-------------",
        f"Cleanup  : {'OK' if report.local_cleanup_success else 'FAILED'}",
        f"Remaining: {report.local_backups_remaining if report.local_backups_remaining is not None else 'N/A'} backups",
        "",
        "Samba Upload",
        "------------",
        f"Upload   : {'OK' if report.samba_upload_success else 'FAILED'}"
        + (f" — {report.samba_upload_error}" if report.samba_upload_error else ""),
        "",
        "Samba Storage",
        "-------------",
        f"Cleanup  : {'OK' if report.samba_cleanup_success else 'FAILED'}",
        f"Remaining: {report.samba_backups_remaining if report.samba_backups_remaining is not None else 'N/A'} backups",
        "",
        "Errors / Warnings",
        "-----------------",
        "\n".join(report.errors) if report.errors else "None",
    ]
    return "\n".join(lines) + "\n"


def send_report(report: BackupReport) -> None:
    """Send a backup report email via SMTP.

    If email reporting is disabled or configuration is incomplete,
    logs a message and returns without raising.
    """
    if os.environ.get("SMTP_ENABLED", "false").lower() != "true":
        logger.info("email reporting disabled (SMTP_ENABLED is not true)")
        return

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port_str = os.environ.get("SMTP_PORT", "587")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM")
    smtp_to = os.environ.get("SMTP_TO")
    smtp_tls = os.environ.get("SMTP_TLS", "true").lower() != "false"

    missing = [name for name, value in (
        ("SMTP_HOST", smtp_host),
        ("SMTP_PORT", smtp_port_str),
        ("SMTP_USER", smtp_user),
        ("SMTP_PASSWORD", smtp_password),
        ("SMTP_FROM", smtp_from),
        ("SMTP_TO", smtp_to),
    ) if not value]

    if missing:
        logger.warning("email reporting skipped — missing configuration: %s", ", ".join(missing))
        return

    port = int(smtp_port_str)

    body = _build_body(report)

    success_emoji = "\u2705"
    fail_emoji = "\u274c"
    if report.filename:
        label = "Success" if report.success else "Failed"
        subject = f"[UniFi Backup] {success_emoji if report.success else fail_emoji} {label} — {report.filename}"
    else:
        started_date = report.started_at.strftime("%Y-%m-%d") if report.started_at else "unknown"
        label = "Success" if report.success else "Failed"
        subject = f"[UniFi Backup] {success_emoji if report.success else fail_emoji} {label} — {started_date}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = smtp_to
    msg.set_content(body)

    try:
        if port == 465 or not smtp_tls:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(smtp_host, port, context=context, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, port, timeout=30)
            server.starttls(context=ssl.create_default_context())

        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        logger.info("backup report email sent to %s", smtp_to)
    except Exception:
        logger.exception("failed to send backup report email")
