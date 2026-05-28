#!/bin/bash
set -e

LOG_FILE="/var/log/unifi-backup.log"

# Validate required environment variables
REQUIRED_VARS="UNIFI_SERVER_ADDRESS UNIFI_USER UNIFI_PASSWORD BACKUP_FOLDER SAMBA_HOST SAMBA_SHARE SAMBA_USER SAMBA_PASSWORD SAMBA_REMOTE_PATH"
for var in $REQUIRED_VARS; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required environment variable '$var' is not set" >&2
        exit 1
    fi
done

# Export env vars to /etc/environment so cron can access them
printenv > /etc/environment

# Write crontab with substituted BACKUP_CRON_SCHEDULE
CRON_SCHEDULE="${BACKUP_CRON_SCHEDULE:-0 3 * * *}"
sed "s|\$BACKUP_CRON_SCHEDULE|$CRON_SCHEDULE|g" /app/cron/backup-cron > /etc/cron.d/unifi-backup-cron
chmod 0644 /etc/cron.d/unifi-backup-cron

# Install the crontab
crontab /etc/cron.d/unifi-backup-cron

# Start cron in the background
cron

# Create log file and keep container alive
touch "$LOG_FILE"
tail -f "$LOG_FILE"
