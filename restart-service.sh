#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="omni-sync"
PROJECT_DIR="/home/yongjie/OmniSync"
SERVICE_SRC="$PROJECT_DIR/deploy/systemd/omnisync.service"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}.service"

echo "==> Copy service file"
sudo cp "$SERVICE_SRC" "$SERVICE_DST"

echo "==> Reload systemd"
sudo systemctl daemon-reload

echo "==> Restart service"
sudo systemctl restart "$SERVICE_NAME"

echo "==> Service status"
sudo systemctl status "$SERVICE_NAME" --no-pager -l

echo
echo "==> Recent logs"
sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager