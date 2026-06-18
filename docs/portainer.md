# Portainer Deployment

The published image is available at
`ghcr.io/reply-nick/unifi-backup-docker-tool:latest` — no build step is needed.

---

## 1. Create the Environment File

On the Portainer host, create a `stack.env` file with your credentials.
Use the template below as a starting point:

```env
# UniFi
UNIFI_SERVER_ADDRESS=https://192.168.1.1:443
UNIFI_USER=admin
UNIFI_PASSWORD=secret
UNIFI_VALIDATE_TLS=false

# Local storage
BACKUP_FOLDER=/backups
BACKUP_CONVERT_TIMESTAMP=true
BACKUP_INCOMPETENT_FS=false
BACKUP_LOCAL_MIN_AGE_DAYS=7
BACKUP_LOCAL_MAX_COUNT=7

# Samba
SAMBA_HOST=192.168.1.100
SAMBA_SHARE=Backups
SAMBA_USER=sambauser
SAMBA_PASSWORD=sambapass
SAMBA_DOMAIN=WORKGROUP
SAMBA_REMOTE_PATH=unifi
SAMBA_MIN_AGE_DAYS=30
SAMBA_MAX_COUNT=30

# Cron schedule (default: 3am daily)
BACKUP_CRON_SCHEDULE=0 3 * * *

# Run backup on container startup (default: true)
BACKUP_ON_START=true

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
LOG_LEVEL=INFO

# Email reporting (optional)
SMTP_ENABLED=false
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=you@gmail.com
SMTP_TO=you@gmail.com
SMTP_TLS=true
```

Edit each value to match your environment.

---

## 2. Stack Configuration

In Portainer go to **Stacks → Add stack**, give it the name
`unifi-backup-docker-tool`, and paste the following into the web editor:

```yaml
services:
  unifi-backup-docker-tool:
    container_name: unifi-backup-docker-tool
    image: ghcr.io/reply-nick/unifi-backup-docker-tool:latest
    env_file: stack.env
    environment:
      - TZ=America/Chicago
    volumes:
      - /path-to/backups:/backups
    restart: unless-stopped
```

> **Note:** Replace `TZ=America/Chicago` with your local timezone if different.
> A full list of valid timezone strings can be found at
> https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

---

## 3. Deploy

Click **Deploy the stack**. Portainer will pull the image from the GitHub
Container Registry and start the container. You can verify it is running under
**Containers** and tail live logs from the **Logs** tab.

---

## Updating

To update to the latest version, go to your stack in Portainer
(**Stacks → unifi-backup-docker-tool → Editor → Update the stack**). Portainer
will pull the newest image and recreate the container.
