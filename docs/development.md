# Development

## Prerequisites

- Python 3.9+
- Docker & Docker Compose
- `pytest` (for tests)

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install smbprotocol requests pytest
```

## Running Tests

```bash
pytest tests/ -v
```

Tests use `unittest.mock` for all external dependencies (SMTP, filesystem, network).
No real UniFi controller, Samba server, or SMTP server is needed.

## Running the App Locally

For debugging without Docker:

```bash
source .env
python -m src.main
```

Or with an explicit env file:

```bash
set -a && source .env && set +a && python -m src.main
```

Note: Local runs skip the cron scheduler and email report will not send unless
`SMTP_ENABLED=true` and all SMTP vars are set.

## Adding Tests

- Place tests in `tests/` alongside existing files.
- Use class-based test classes (e.g. `TestFeatureName`) for organization.
- Put shared fixtures in `tests/conftest.py`.
- Use `monkeypatch` from pytest to isolate environment variables.
- Mock all external I/O (SMTP, filesystem, network) — never hit real services.

## Docker Workflow

Build and run:

```bash
docker compose up --build -d
docker compose logs -f
```

Rebuild after code changes:

```bash
docker compose up --build -d
```

For a quick container shell:

```bash
docker compose exec unifi-backup-docker-tool bash
```

## Project Structure

```
src/
  main.py      # Orchestration entrypoint
  backup.py    # UniFi download + local cleanup
  smb.py       # Samba upload + remote cleanup
  reporter.py  # Email report generation and sending
  utils.py     # Shared utilities
tests/
  conftest.py       # Fixtures (mock_report, isolated_env, full_env)
  test_reporter.py  # Reporter unit tests
```
