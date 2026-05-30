#!/bin/bash
set -e

LOG_FILE="/var/log/unifi-backup.log"

# Validate required environment variables
REQUIRED_VARS="UNIFI_SERVER_ADDRESS UNIFI_USER UNIFI_PASSWORD BACKUP_FOLDER SAMBA_HOST SAMBA_SHARE SAMBA_USER SAMBA_PASSWORD SAMBA_REMOTE_PATH"
for var in $REQUIRED_VARS; do
    if [ -z "${!var}" ]; then
        echo "$(date -u '+%Y-%m-%d %H:%M:%S') [ERROR] Required environment variable '$var' is not set" >&2
        exit 1
    fi
done

# Export env vars to /etc/environment so cron can access them
printenv > /etc/environment

# Write crontab with substituted BACKUP_CRON_SCHEDULE
CRON_SCHEDULE="${BACKUP_CRON_SCHEDULE:-0 3 * * *}"
sed "s|\$BACKUP_CRON_SCHEDULE|$CRON_SCHEDULE|g" /app/cron/backup-cron | crontab -

# Start cron in the background
cron

# Run an initial backup on startup if enabled
if [ "${BACKUP_ON_START:-true}" = "true" ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') [entrypoint] Running initial backup on startup"
    /usr/local/bin/python3 /app/src/main.py
fi

# Create log file and keep container alive
touch "$LOG_FILE"
echo "$(date -u '+%Y-%m-%d %H:%M:%S') [entrypoint] Starting unifi-backup-docker-tool, cron schedule: $CRON_SCHEDULE"
tail -f "$LOG_FILE"
