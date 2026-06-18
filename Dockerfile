FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y cron && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /backups

WORKDIR /app

COPY src/ /app/src/
COPY cron/ /app/cron/
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

RUN pip install --no-cache-dir smbprotocol requests

CMD ["/entrypoint.sh"]
