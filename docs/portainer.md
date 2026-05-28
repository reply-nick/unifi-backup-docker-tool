# Portainer Deployment

Portainer stacks do not support the `build:` directive — images must be built
manually on the host first and then referenced by name in the stack config.

---

## 1. Build the Image

SSH into your host and run:

```bash
cd /path-to/unifi-backup-docker-tool
docker build -t unifi-backup-docker-tool:latest .
```

This builds the image locally and tags it as `unifi-backup-docker-tool:latest`.
No registry is required — Portainer will find it directly on the host.

---

## 2. Stack Configuration

In Portainer go to **Stacks → Add stack**, give it the name
`unifi-backup-docker-tool`, and paste the following into the web editor:

```yaml
services:
  unifi-backup-docker-tool:
    container_name: unifi-backup-docker-tool
    image: unifi-backup-docker-tool:latest
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

Click **Deploy the stack**. Portainer will start the container using the locally
built image. You can verify it is running under **Containers** and tail live logs
from the **Logs** tab.

---

## Rebuilding After Code Changes

Portainer cannot rebuild images automatically. After any change to the source
code or `Dockerfile`, rebuild the image manually on the host:

```bash
cd /path-to/unifi-backup-docker-tool
docker build -t unifi-backup-docker-tool:latest .
```

Then redeploy the stack in Portainer (**Stacks → unifi-backup-docker-tool →
Editor → Update the stack**). Portainer will recreate the container using the
newly built image.

---