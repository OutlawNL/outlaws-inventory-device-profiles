#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/opt/outlaws-inventory"
SERVICE_NAME="outlaws-inventory.service"
SERVICE_USER="outlaws-inventory"
PORT="8000"
DATA_DIR="$APP_DIR/data"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPECTED_VERSION="$(sed -nE 's/^APP_VERSION[[:space:]]*=[[:space:]]*["'\'']([^"'\'']+)["'\''].*/\1/p' "$SOURCE_DIR/app/main.py" | head -n1)"
[[ -n "$EXPECTED_VERSION" ]] || { echo "Could not determine source APP_VERSION." >&2; exit 1; }

if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo ./install.sh"; exit 1; fi
if [[ ! -r /etc/os-release ]]; then echo "Unable to identify the operating system." >&2; exit 1; fi
. /etc/os-release
if [[ "${ID:-}" != "debian" && "${ID_LIKE:-}" != *debian* ]]; then echo "This installer supports Debian-compatible systems." >&2; exit 1; fi
if [[ -f "$APP_DIR/app/main.py" || -f "$DATA_DIR/outlaws-inventory.db" ]]; then
  echo "An existing Outlaw's Inventory installation was detected in $APP_DIR." >&2
  echo "Use sudo ./update.sh for an existing installation, or remove the old installation only when intentionally rebuilding this host." >&2
  exit 1
fi

echo "Installing Outlaw's Inventory v${EXPECTED_VERSION}..."
apt-get update
apt-get install -y python3 python3-venv python3-pip unzip rsync sudo ca-certificates curl iputils-ping libcap2-bin

if ! getent group "$SERVICE_USER" >/dev/null 2>&1; then
  groupadd --system "$SERVICE_USER"
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_USER" --create-home --home-dir /var/lib/outlaws-inventory --shell /usr/sbin/nologin "$SERVICE_USER"
else
  current_group="$(id -gn "$SERVICE_USER")"
  current_home="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
  current_shell="$(getent passwd "$SERVICE_USER" | cut -d: -f7)"
  if [[ "$current_group" != "$SERVICE_USER" || "$current_home" != "/var/lib/outlaws-inventory" || "$current_shell" != "/usr/sbin/nologin" ]]; then
    usermod --gid "$SERVICE_USER" --home /var/lib/outlaws-inventory --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
fi

mkdir -p "$APP_DIR" "$DATA_DIR/uploads" "$DATA_DIR/keys" "$DATA_DIR/secrets" "$DATA_DIR/update-staging" "$DATA_DIR/backups"
rsync -a --delete --exclude data --exclude venv --exclude '__pycache__' "$SOURCE_DIR/" "$APP_DIR/"
chown -R root:root "$APP_DIR"
chmod 700 "$DATA_DIR/keys" "$DATA_DIR/secrets" "$DATA_DIR/update-staging"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR" "$DATA_DIR/uploads"
chmod 700 "$DATA_DIR/keys" "$DATA_DIR/secrets" "$DATA_DIR/update-staging" "$DATA_DIR/backups"
find "$DATA_DIR/keys" -maxdepth 1 -type f ! -name '*.pub' -exec chmod 600 {} \; 2>/dev/null || true
find "$DATA_DIR/keys" -maxdepth 1 -type f -name '*.pub' -exec chmod 644 {} \; 2>/dev/null || true

cat > /etc/systemd/system/$SERVICE_NAME <<EOF
[Unit]
Description=Outlaw's Inventory
After=network-online.target
Wants=network-online.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment=OUTLAWS_DATA_DIR=$DATA_DIR
Environment=PYTHONDONTWRITEBYTECODE=1
UMask=0077
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

install -o root -g root -m 0755 "$SOURCE_DIR/scripts/outlaws-inventory-verify-release" /usr/local/sbin/outlaws-inventory-verify-release
install -m 0755 "$SOURCE_DIR"/scripts/outlaws-inventory-self-update /usr/local/sbin/outlaws-inventory-self-update
install -m 0755 "$SOURCE_DIR"/scripts/outlaws-inventory-self-rollback /usr/local/sbin/outlaws-inventory-self-rollback
install -m 0755 "$SOURCE_DIR"/scripts/outlaws-inventory-self-update-launcher /usr/local/sbin/outlaws-inventory-self-update-launcher
install -m 0755 "$SOURCE_DIR"/scripts/outlaws-inventory-self-rollback-launcher /usr/local/sbin/outlaws-inventory-self-rollback-launcher
cat > /etc/sudoers.d/outlaws-inventory-system-actions <<EOF
$SERVICE_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart outlaws-inventory.service, /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff, /usr/local/sbin/outlaws-inventory-self-update-launcher, /usr/local/sbin/outlaws-inventory-self-rollback-launcher
EOF
chmod 440 /etc/sudoers.d/outlaws-inventory-system-actions
visudo -cf /etc/sudoers.d/outlaws-inventory-system-actions >/dev/null

# System Checks uses ICMP ping. Debian normally grants ping the required file
# capability; verify it for the dedicated service account and repair it when needed.
if ! runuser -u "$SERVICE_USER" -- /usr/bin/ping -c 1 -W 1 127.0.0.1 >/dev/null 2>&1; then
  setcap cap_net_raw+ep /usr/bin/ping 2>/dev/null || true
fi
if ! runuser -u "$SERVICE_USER" -- /usr/bin/ping -c 1 -W 1 127.0.0.1 >/dev/null 2>&1; then
  echo "Warning: the service account cannot use ICMP ping. Online Status checks may report a ping permission error." >&2
fi

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "Validating application startup..."
if ! python3 - "$EXPECTED_VERSION" "$PORT" <<'PYHEALTH'
import json, sys, time, urllib.request
expected, port = sys.argv[1], sys.argv[2]
last_error = "service did not respond"
for _ in range(45):
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/system/ready",
            headers={"Cache-Control":"no-cache","Pragma":"no-cache"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload=json.loads(response.read().decode("utf-8"))
        running=str(payload.get("app_version") or "")
        if payload.get("ready") is True and running == expected:
            raise SystemExit(0)
        last_error=f"running APP_VERSION is {running or 'unknown'}; expected {expected}"
    except SystemExit:
        raise
    except Exception as exc:
        last_error=str(exc)
    time.sleep(1)
print(f"Application startup verification failed: {last_error}", file=sys.stderr)
raise SystemExit(1)
PYHEALTH
then
  echo >&2
  echo "Installation failed: Outlaw's Inventory did not become healthy." >&2
  systemctl status "$SERVICE_NAME" --no-pager -l >&2 || true
  echo >&2
  journalctl -u "$SERVICE_NAME" -n 50 --no-pager >&2 || true
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  exit 1
fi

if [[ "$(systemctl is-active "$SERVICE_NAME")" != "active" ]]; then
  echo "Installation failed: $SERVICE_NAME is not active after startup validation." >&2
  systemctl status "$SERVICE_NAME" --no-pager -l >&2 || true
  exit 1
fi

IP_ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -n "$IP_ADDRESS" ]] || IP_ADDRESS="localhost"
echo
echo "Installation complete."
echo "Open: http://$IP_ADDRESS:$PORT/setup"
