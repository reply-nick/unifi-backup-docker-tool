# unifi-backup-docker-tool

Dockerized UniFi OS backup service with an internal cron scheduler, local backup storage, and post-save Samba uploads — each with independent retention policies.

## Features

- Automated backup downloads from UniFi OS controllers
- Local backup storage with configurable age and count retention
- Samba (SMB) remote uploads using pure Python (`smbprotocol`) — no mounting required
- Independent retention policies for local and remote backups
- Cron-based scheduling with configurable intervals
- Environment-variable-driven configuration — no config files needed
- Graceful error handling — Samba failures don't block local backups and vice versa
- Automatic remote directory creation on first upload
- Resilient timestamp parsing (handles both `:` and `.` separators)
- Dual logging to both stdout and `/var/log/unifi-backup.log`

## Prerequisites

- Docker
- Docker Compose

## Setup

1. Clone this repository:

```bash
git clone <repo-url>
cd unifi-backup-docker-tool
```

2. Copy the example environment file and edit it with your credentials:

```bash
cp .env.example .env
```

3. Update `.env` with your UniFi controller credentials, Samba server details, and retention settings.

## Usage

Start the service:

```bash
docker compose up -d
```

View logs:

```bash
docker compose logs -f
```

Stop the service:

```bash
docker compose down
```

## Directory Structure

```
unifi-backup-docker-tool/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── entrypoint.sh
├── cron/
│   └── backup-cron
└── src/
    ├── backup.py      # UniFi backup download and local cleanup
    ├── main.py        # Orchestration entrypoint
    ├── smb.py         # Samba upload and remote cleanup
    └── utils.py       # Shared utilities (timestamp parsing, renaming)
```

## Environment Variables

### UniFi

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `UNIFI_SERVER_ADDRESS` | Yes | — | UniFi OS controller URL (e.g. `https://192.168.1.1:443`) |
| `UNIFI_USER` | Yes | — | Username for login |
| `UNIFI_PASSWORD` | Yes | — | Password for login |
| `UNIFI_VALIDATE_TLS` | No | `false` | Validate TLS certificate (`true`/`false`) |

### Local Storage

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKUP_FOLDER` | Yes | — | Local path for backup storage |
| `BACKUP_CONVERT_TIMESTAMP` | No | `true` | Convert Unix timestamps to ISO-8601 in filenames |
| `BACKUP_INCOMPETENT_FS` | No | `false` | Replace `:` with `.` in filenames for incompatible filesystems |
| `BACKUP_LOCAL_MIN_AGE_DAYS` | No | `7` | Minimum age before local backups are eligible for deletion |
| `BACKUP_LOCAL_MAX_COUNT` | No | `7` | Maximum number of local backups to keep |

### Samba

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SAMBA_HOST` | Yes | — | Samba server IP or hostname |
| `SAMBA_SHARE` | Yes | — | SMB share name |
| `SAMBA_USER` | Yes | — | Samba username |
| `SAMBA_PASSWORD` | Yes | — | Samba password |
| `SAMBA_DOMAIN` | No | `WORKGROUP` | Samba domain (leave empty for workgroup) |
| `SAMBA_REMOTE_PATH` | Yes | — | Remote directory on the share |
| `SAMBA_MIN_AGE_DAYS` | No | `30` | Minimum age before remote backups are eligible for deletion |
| `SAMBA_MAX_COUNT` | No | `30` | Maximum number of remote backups to keep |

### Cron

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BACKUP_CRON_SCHEDULE` | No | `0 3 * * *` | Cron schedule expression (default: daily at 3am) |

## How It Works

On each scheduled run, the tool executes the following steps:

1. **Download** — Authenticates to the UniFi controller and downloads the latest backup file
2. **Local cleanup** — Prunes local backups exceeding retention policy
3. **Rename** — Converts `:` to `.` in timestamps for Samba filename compatibility
4. **Samba upload** — Uploads the backup to the remote share (auto-creates directory if missing)
5. **Samba cleanup** — Prunes remote backups exceeding retention policy

Each step is error-isolated: a failure in one step does not prevent the others from completing.

## License

MIT
