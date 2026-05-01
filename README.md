# OmniSync V1

A lightweight Python service for storing and syncing text key-value data across devices.

## Scope (Current)

- Single user
- Text key-value upsert and fetch
- Incremental pull for sync
- File sync (upload, download, metadata, hard delete)
- SQLite storage
- Bearer token authentication

Not included: realtime location upload, push notifications, multi-user auth.

## Quick Start

1. Install dependencies in the `bwg` conda env:

```powershell
& "C:\Users\yongjie\anaconda3\shell\condabin\conda-hook.ps1"; conda activate bwg; pip install -r requirements.txt
```

2. Configure environment variables:

```powershell
$env:APP_TOKEN="replace-with-strong-token"
$env:DB_PATH="./data/omnisync.db"
$env:FILE_STORAGE_PATH="./data/files"
$env:FILE_MAX_BYTES="52428800"
$env:HOST="127.0.0.1"
$env:PORT="8000"
```

3. Run service:

```powershell
& "C:\Users\yongjie\anaconda3\shell\condabin\conda-hook.ps1"; conda activate bwg; uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## API

- `GET /healthz`
- `POST /v1/items/{key}`
- `GET /v1/items/{key}`
- `GET /v1/text/{key}` (JSON, value only)
- `GET /v1/text/{key}.txt` (plain text)
- `GET /v1/items?since=<ISO8601>&limit=<1..500>`
- `PUT /v1/files/{key}` (multipart upload, optional `expected_version` query)
- `GET /v1/files/{key}` (download binary)
- `GET /v1/files/{key}/meta`
- `DELETE /v1/files/{key}` (hard delete, optional `expected_version` query)
- `GET /v1/files?since=<ISO8601>&limit=<1..500>`
- `POST /v1/files/gc?grace_seconds=<seconds>&limit=<n>`

`POST /v1/items/{key}` request:

```json
{
  "value": "text payload",
  "expected_version": 1
}
```

`DELETE /v1/files/{key}` response:

```json
{
  "key": "avatar",
  "hard_deleted": true
}
```

## Status Codes

- `200`: success
- `400`: bad input
- `401`: unauthorized
- `404`: item not found
- `409`: version conflict
- `500`: internal error

## File Sync Example

Upload:

```bash
curl -X PUT "http://127.0.0.1:8000/v1/files/avatar" \
  -H "Authorization: Bearer <token>" \
  -F "file=@./avatar.png"
```

Download:

```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8000/v1/files/avatar" \
  --output avatar.png
```

File meta:

```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8000/v1/files/avatar/meta"
```

Hard delete:

```bash
curl -X DELETE "http://127.0.0.1:8000/v1/files/avatar" \
  -H "Authorization: Bearer <token>"
```

Run garbage collection:

```bash
curl -X POST "http://127.0.0.1:8000/v1/files/gc?grace_seconds=0" \
  -H "Authorization: Bearer <token>"
```

## Debian 12 Deployment Guide

This section is the recommended production path for a low-spec Debian 12 VPS with Nginx.

### 1. Install system packages

  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip nginx sqlite3 curl

### 2. Create service user and project directory

  sudo useradd --system --create-home --shell /usr/sbin/nologin omnisync
  sudo mkdir -p /opt/omnisync
  sudo chown -R omnisync:omnisync /opt/omnisync

Upload your project files to /opt/omnisync.

### 3. Create virtual environment and install dependencies

  cd /opt/omnisync
  sudo -u omnisync python3 -m venv .venv
  sudo -u omnisync /opt/omnisync/.venv/bin/pip install -r requirements.txt

### 4. Configure environment variables

Create deployment env file:

  sudo cp /opt/omnisync/deploy/ENV.example /opt/omnisync/deploy/ENV

Generate token:

  openssl rand -hex 32

Edit /opt/omnisync/deploy/ENV and set at least:

  APP_TOKEN=<your_generated_token>
  DB_PATH=/opt/omnisync/data/omnisync.db
  FILE_STORAGE_PATH=/opt/omnisync/data/files
  FILE_MAX_BYTES=52428800
  HOST=127.0.0.1
  PORT=8000
  LOG_LEVEL=info

Prepare data directory:

  sudo mkdir -p /opt/omnisync/data
  sudo chown -R omnisync:omnisync /opt/omnisync/data

### 5. Run once for smoke test

  cd /opt/omnisync
  sudo -u omnisync APP_TOKEN=<your_generated_token> DB_PATH=/opt/omnisync/data/omnisync.db /opt/omnisync/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

Open a second terminal and verify:

  curl http://127.0.0.1:8000/healthz

Stop the foreground process after verification.

### 6. Enable systemd service

Copy service file:

  sudo cp /opt/omnisync/deploy/systemd/omnisync.service /etc/systemd/system/omnisync.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now omnisync

Check status and logs:

  sudo systemctl status omnisync
  sudo journalctl -u omnisync -f

### 7. Configure Nginx reverse proxy

Copy and enable site config:

  sudo cp /opt/omnisync/deploy/nginx/omnisync.conf /etc/nginx/sites-available/omnisync
  sudo ln -s /etc/nginx/sites-available/omnisync /etc/nginx/sites-enabled/omnisync
  sudo nginx -t
  sudo systemctl reload nginx

Edit server_name in the Nginx file before reload.

### 8. Optional: enable HTTPS

If your domain DNS already points to this VPS:

  sudo apt install -y certbot python3-certbot-nginx
  sudo certbot --nginx -d <your-domain>

### 9. API quick verify

Health:

  curl http://127.0.0.1/healthz

Upsert:

  curl -X POST "http://127.0.0.1/v1/items/clipboard" \
    -H "Authorization: Bearer <your_generated_token>" \
    -H "Content-Type: application/json" \
    -d '{"value":"hello from vps"}'

Get:

  curl -H "Authorization: Bearer <your_generated_token>" \
    "http://127.0.0.1/v1/items/clipboard"

### 10. Backup recommendation

At minimum, back up /opt/omnisync/data/omnisync.db daily.
Example cron entry:

  0 3 * * * cp /opt/omnisync/data/omnisync.db /opt/omnisync/data/backup-$(date +\%F).db
