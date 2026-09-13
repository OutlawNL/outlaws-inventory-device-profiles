#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo ./update.sh"; exit 1; fi

APP_DIR="/opt/outlaws-inventory"
SERVICE="outlaws-inventory.service"
SERVICE_USER="outlaws-inventory"
PORT="8000"
BACKUP_ROOT="/var/backups/outlaws-inventory"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_VERSION="$(python3 - "$SOURCE_DIR/app/main.py" <<'PYVERSION'
import re, sys
text=open(sys.argv[1], encoding='utf-8').read()
m=re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', text, re.M)
if not m:
    raise SystemExit("Could not determine source APP_VERSION.")
print(m.group(1))
PYVERSION
)"
echo "Updating Outlaw's Inventory to v${SOURCE_VERSION}..."
PROGRESS_FILE="${OUTLAWS_UPDATE_RESULT:-}"
PROGRESS_VERSION="${OUTLAWS_UPDATE_VERSION:-}"
PROGRESS_JOB_ID="${OUTLAWS_UPDATE_JOB_ID:-}"
PROGRESS_STARTED_AT="${OUTLAWS_UPDATE_STARTED_AT:-$(date +%s)}"
INTERNAL_UPDATE="${OUTLAWS_INTERNAL_UPDATE:-0}"
ROLLBACK_ROOT="$BACKUP_ROOT/rollback"
ROLLBACK_HISTORY="$BACKUP_ROOT/rollback-history"
ROLLBACK_META="$ROLLBACK_ROOT/metadata.json"
ROLLBACK_STATE="$APP_DIR/data/update-staging/rollback.json"

report_progress() {
  local stage="$1" progress="$2" message="$3" state="${4:-installing}"
  [[ -n "$PROGRESS_FILE" ]] || return 0
  local temporary="${PROGRESS_FILE}.update.tmp.$$"
  runuser -u "$SERVICE_USER" -- python3 - "$temporary" "$state" "$stage" "$progress" "$message" "$PROGRESS_VERSION" "$PROGRESS_JOB_ID" "$PROGRESS_STARTED_AT" <<'PYPROGRESS'
import json, sys, time
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    'state':sys.argv[2], 'stage':sys.argv[3], 'progress':int(sys.argv[4]),
    'message':sys.argv[5], 'version':sys.argv[6], 'job_id':sys.argv[7],
    'started_at_epoch':int(sys.argv[8]), 'updated_at_epoch':int(time.time()),
    'heartbeat_at_epoch':int(time.time()),
}, indent=2), encoding='utf-8')
PYPROGRESS
  true
  runuser -u "$SERVICE_USER" -- chmod 600 "$temporary" 2>/dev/null || true
  runuser -u "$SERVICE_USER" -- mv -f "$temporary" "$PROGRESS_FILE"
}

mkdir -p "$BACKUP_DIR" "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"

current_installed_version() {
  python3 - "$APP_DIR/app/main.py" <<'PYVERSION'
import re, sys
text=open(sys.argv[1], encoding='utf-8').read()
m=re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', text, re.M)
print(m.group(1) if m else '')
PYVERSION
}

prune_update_backups() {
  python3 - "$BACKUP_ROOT" <<'PYPRUNE'
import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
pattern = re.compile(r"20\d{6}-\d{6}\Z")

try:
    candidates = sorted(
        (
            child for child in root.iterdir()
            if pattern.fullmatch(child.name)
            and child.is_dir()
            and not child.is_symlink()
        ),
        key=lambda child: child.name,
        reverse=True,
    )
except OSError as exc:
    print(f"Warning: could not inspect update backup retention: {exc}", file=sys.stderr)
    raise SystemExit(0)

for old_backup in candidates[2:]:
    try:
        shutil.rmtree(old_backup)
        print(f"Removed old update backup: {old_backup.name}")
    except OSError as exc:
        print(f"Warning: could not remove old update backup {old_backup}: {exc}", file=sys.stderr)
PYPRUNE
}

archive_existing_rollback() {
  [[ "$INTERNAL_UPDATE" == "1" ]] && return 0
  mkdir -p "$ROLLBACK_HISTORY"
  if [[ -d "$ROLLBACK_ROOT" && -f "$ROLLBACK_META" ]]; then
    local stamp version destination
    stamp="$(date +%Y%m%d-%H%M%S)"
    version="$(python3 - "$ROLLBACK_META" <<'PYROLLBACK'
import json,sys
try:
    print(json.load(open(sys.argv[1])).get('version','unknown'))
except Exception:
    print('unknown')
PYROLLBACK
)"
    destination="$ROLLBACK_HISTORY/${stamp}-v${version}"
    mv "$ROLLBACK_ROOT" "$destination"
  else
    rm -rf "$ROLLBACK_ROOT"
  fi
}

publish_manual_rollback() {
  local previous_version="$1"
  [[ "$INTERNAL_UPDATE" == "1" ]] && return 0
  [[ -n "$previous_version" ]] || return 0

  archive_existing_rollback
  mkdir -p "$ROLLBACK_ROOT/app"
  rsync -a --checksum --delete --exclude data --exclude venv --exclude '__pycache__' --exclude '.pytest_cache' "$BACKUP_DIR/app/" "$ROLLBACK_ROOT/app/"
  python3 - "$ROLLBACK_META" "$previous_version" <<'PYROLLBACK'
import json, sys
from datetime import datetime
from pathlib import Path
Path(sys.argv[1]).write_text(
    json.dumps({"version": sys.argv[2], "created_at": datetime.now().isoformat(timespec='seconds')}, indent=2),
    encoding='utf-8',
)
PYROLLBACK
  chmod 700 "$ROLLBACK_ROOT"
  runuser -u "$SERVICE_USER" -- python3 - "$ROLLBACK_STATE" "$previous_version" <<'PYROLLBACK'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(
    json.dumps({"state":"available","message":"Previous version available.","version":sys.argv[2]}, indent=2),
    encoding='utf-8',
)
PYROLLBACK
  true
  runuser -u "$SERVICE_USER" -- chmod 600 "$ROLLBACK_STATE" 2>/dev/null || true

  # Keep at most two older historical rollback snapshots in addition to the current one.
  mapfile -t rollback_history < <(find "$ROLLBACK_HISTORY" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk '{print $2}')
  local i
  for ((i=2; i<${#rollback_history[@]}; i++)); do rm -rf "${rollback_history[$i]}"; done
}

runtime_version_check() {
  local expected_version="$1"
  python3 - "$expected_version" <<PYHEALTH
import json, sys, time, urllib.request
expected = sys.argv[1]
last_error = "service did not respond"
for _ in range(40):
    try:
        request = urllib.request.Request(
            'http://127.0.0.1:$PORT/system/ready',
            headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode('utf-8'))
        running = str(payload.get('app_version') or '')
        if payload.get('ready') is True and running == expected:
            raise SystemExit(0)
        last_error = f"running APP_VERSION is {running or 'unknown'}; expected {expected}"
    except SystemExit:
        raise
    except Exception as exc:
        last_error = str(exc)
    time.sleep(1)
print(f"Runtime version verification failed: {last_error}", file=sys.stderr)
raise SystemExit(1)
PYHEALTH
}

SNAPSHOT_READY=0
LIVE_CHANGED=0
restore_existing() {
  echo "Update failed; restoring the previous installation…" >&2
  systemctl stop "$SERVICE" 2>/dev/null || true
  if [[ "$SNAPSHOT_READY" == 1 && "$LIVE_CHANGED" == 1 && -d "$BACKUP_DIR/app" ]]; then
    rm -rf "$APP_DIR"
    cp -a "$BACKUP_DIR/app" "$APP_DIR"
    python3 -m venv "$APP_DIR/venv"
    "$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null
  fi
  local restore_user="${PREVIOUS_SERVICE_USER:-$SERVICE_USER}"
  if id "$restore_user" >/dev/null 2>&1; then
    local restore_group
    restore_group="$(id -gn "$restore_user")"
    chown -R root:root "$APP_DIR"
    chown -R "$restore_user:$restore_group" "$APP_DIR/data" 2>/dev/null || true
  fi
  if [[ -f "$BACKUP_DIR/system-integration/service.unit" ]]; then
    cp -a "$BACKUP_DIR/system-integration/service.unit" "/etc/systemd/system/$SERVICE"
  fi
  if [[ -f "$BACKUP_DIR/system-integration/sudoers" ]]; then
    cp -a "$BACKUP_DIR/system-integration/sudoers" /etc/sudoers.d/outlaws-inventory-system-actions
    chmod 440 /etc/sudoers.d/outlaws-inventory-system-actions
  fi
  for helper in outlaws-inventory-self-update outlaws-inventory-self-rollback outlaws-inventory-self-update-launcher outlaws-inventory-self-rollback-launcher outlaws-inventory-verify-release; do
    [[ -f "$BACKUP_DIR/system-integration/$helper" ]] && cp -a "$BACKUP_DIR/system-integration/$helper" "/usr/local/sbin/$helper" || true
  done
  find "$APP_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$APP_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
  systemctl daemon-reload
  systemctl restart "$SERVICE" || true
}
finish_update() {
  local rc=$?
  trap - EXIT
  if (( rc != 0 )); then restore_existing || true; fi
  exit "$rc"
}
trap finish_update EXIT

if [[ ! -d "$APP_DIR" || ! -f "$APP_DIR/data/outlaws-inventory.db" ]]; then
  echo "No supported Outlaw's Inventory installation was found in $APP_DIR." >&2
  exit 1
fi
PREVIOUS_VERSION="$(current_installed_version)"
[[ -n "$PREVIOUS_VERSION" ]] || {
  echo "Could not determine the currently installed APP_VERSION." >&2
  exit 1
}
PREVIOUS_SERVICE_USER="$(systemctl show -p User --value "$SERVICE" 2>/dev/null || true)"
[[ -n "$PREVIOUS_SERVICE_USER" ]] || PREVIOUS_SERVICE_USER="$SERVICE_USER"

python3 - "$PREVIOUS_VERSION" <<'PYBASELINE'
import re, sys
def version(value):
    parts = [int(x) for x in re.findall(r"\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])
if version(sys.argv[1]) < version("0.15.0"):
    print("Unsupported upgrade source. Outlaw's Inventory v0.15.1 and later require v0.15.0 or newer.", file=sys.stderr)
    raise SystemExit(1)
PYBASELINE

report_progress "Checking system dependencies" 40 "Checking required system packages."
apt-get install -y python3 python3-venv python3-pip unzip rsync sudo ca-certificates iputils-ping libcap2-bin >/dev/null
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
mkdir -p "$BACKUP_DIR/system-integration"
[[ -f "/etc/systemd/system/$SERVICE" ]] && cp -a "/etc/systemd/system/$SERVICE" "$BACKUP_DIR/system-integration/service.unit" || true
[[ -f /etc/sudoers.d/outlaws-inventory-system-actions ]] && cp -a /etc/sudoers.d/outlaws-inventory-system-actions "$BACKUP_DIR/system-integration/sudoers" || true
for helper in outlaws-inventory-self-update outlaws-inventory-self-rollback outlaws-inventory-self-update-launcher outlaws-inventory-self-rollback-launcher outlaws-inventory-verify-release; do
  [[ -f "/usr/local/sbin/$helper" ]] && cp -a "/usr/local/sbin/$helper" "$BACKUP_DIR/system-integration/$helper" || true
done
systemctl stop "$SERVICE" 2>/dev/null || true
cp -a "$APP_DIR" "$BACKUP_DIR/app"
SNAPSHOT_READY=1
python3 - "$APP_DIR/data/outlaws-inventory.db" "$BACKUP_DIR/data-counts.json" <<'PYCOUNTS'
import json, sqlite3, sys
from pathlib import Path
source, target = Path(sys.argv[1]), Path(sys.argv[2])
tables = ("users", "devices", "categories", "attachments", "health_checks", "update_checks", "ssh_profiles")
con = sqlite3.connect(source)
counts = {}
for table in tables:
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    counts[table] = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if exists else 0
manifest = {"counts": counts}
target.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
PYCOUNTS

mkdir -p "$APP_DIR/data/uploads" "$APP_DIR/data/keys" "$APP_DIR/data/secrets" "$APP_DIR/data/update-staging"
report_progress "Installing application files" 52 "Copying the new application files."
LIVE_CHANGED=1
rsync -a --checksum --delete --exclude data --exclude venv --exclude '__pycache__' --exclude '.pytest_cache' "$SOURCE_DIR/" "$APP_DIR/"

INSTALLED_VERSION_AFTER_COPY="$(python3 - "$APP_DIR/app/main.py" <<'PYVERSION'
import re, sys
text=open(sys.argv[1], encoding='utf-8').read()
m=re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', text, re.M)
print(m.group(1) if m else '')
PYVERSION
)"
[[ "$INSTALLED_VERSION_AFTER_COPY" == "$SOURCE_VERSION" ]] || {
  echo "Version verification failed after copying files: expected $SOURCE_VERSION, found ${INSTALLED_VERSION_AFTER_COPY:-unknown}." >&2
  exit 1
}

report_progress "Clearing Python cache" 60 "Removing stale compiled Python bytecode."
find "$APP_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$APP_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

report_progress "Installing Python environment" 65 "Creating the Python environment and installing dependencies."
rm -rf "$APP_DIR/venv"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null

report_progress "Applying permissions" 78 "Applying application ownership and permissions."
chown -R root:root "$APP_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/data"
chmod 750 "$APP_DIR/data" "$APP_DIR/data/uploads" 2>/dev/null || true
chmod 700 "$APP_DIR/data/keys" "$APP_DIR/data/secrets" "$APP_DIR/data/update-staging" "$APP_DIR/data/backups" "$APP_DIR/data/setup-state" "$APP_DIR/data/avatars" 2>/dev/null || true
find "$APP_DIR/data/keys" -maxdepth 1 -type f ! -name '*.pub' -exec chmod 600 {} \;
find "$APP_DIR/data/keys" -maxdepth 1 -type f -name '*.pub' -exec chmod 644 {} \;
[[ -f "$APP_DIR/data/secrets/github-token" ]] && chmod 600 "$APP_DIR/data/secrets/github-token"

cat > "/etc/systemd/system/$SERVICE" <<EOF
[Unit]
Description=Outlaw's Inventory
After=network-online.target
Wants=network-online.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment=OUTLAWS_DATA_DIR=$APP_DIR/data
Environment=PYTHONDONTWRITEBYTECODE=1
UMask=0077
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

install -o root -g root -m 0755 "$SOURCE_DIR/scripts/outlaws-inventory-verify-release" /usr/local/sbin/outlaws-inventory-verify-release
install -m 0755 "$SOURCE_DIR/scripts/outlaws-inventory-self-update" /usr/local/sbin/outlaws-inventory-self-update
install -m 0755 "$SOURCE_DIR/scripts/outlaws-inventory-self-rollback" /usr/local/sbin/outlaws-inventory-self-rollback
install -m 0755 "$SOURCE_DIR/scripts/outlaws-inventory-self-update-launcher" /usr/local/sbin/outlaws-inventory-self-update-launcher
install -m 0755 "$SOURCE_DIR/scripts/outlaws-inventory-self-rollback-launcher" /usr/local/sbin/outlaws-inventory-self-rollback-launcher
cat > /etc/sudoers.d/outlaws-inventory-system-actions <<SUDOEOF
$SERVICE_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart outlaws-inventory.service, /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff, /usr/local/sbin/outlaws-inventory-self-update-launcher, /usr/local/sbin/outlaws-inventory-self-rollback-launcher
SUDOEOF
chmod 440 /etc/sudoers.d/outlaws-inventory-system-actions
visudo -cf /etc/sudoers.d/outlaws-inventory-system-actions >/dev/null

if ! runuser -u "$SERVICE_USER" -- /usr/bin/ping -c 1 -W 1 127.0.0.1 >/dev/null 2>&1; then
  setcap cap_net_raw+ep /usr/bin/ping 2>/dev/null || true
fi
if ! runuser -u "$SERVICE_USER" -- /usr/bin/ping -c 1 -W 1 127.0.0.1 >/dev/null 2>&1; then
  echo "Warning: the service account cannot use ICMP ping. Online Status checks may report a ping permission error." >&2
fi

report_progress "Restarting application" 88 "Restarting Outlaw's Inventory." "restarting"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"
report_progress "Validating updated service" 94 "Waiting for the updated service and verifying its running version." "validating"
runtime_version_check "$SOURCE_VERSION"
INSTALLED_VERSION_AFTER_RESTART="$(python3 - "$APP_DIR/app/main.py" <<'PYVERSION'
import re, sys
text=open(sys.argv[1], encoding='utf-8').read()
m=re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', text, re.M)
print(m.group(1) if m else '')
PYVERSION
)"
[[ "$INSTALLED_VERSION_AFTER_RESTART" == "$SOURCE_VERSION" ]] || {
  echo "Version verification failed after restart: expected $SOURCE_VERSION, found ${INSTALLED_VERSION_AFTER_RESTART:-unknown}." >&2
  exit 1
}
python3 - "$APP_DIR/data/outlaws-inventory.db" "$BACKUP_DIR/data-counts.json" <<'PYVERIFY'
import json, sqlite3, sys
from pathlib import Path
database, manifest = Path(sys.argv[1]), Path(sys.argv[2])
snapshot = json.loads(manifest.read_text(encoding="utf-8"))
before = snapshot.get("counts", snapshot)
con = sqlite3.connect(database)
for table, expected in before.items():
    current = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    if current < expected:
        raise SystemExit(f"Data validation failed for {table}: before={expected}, after={current}")
foreign_key_errors = con.execute("PRAGMA foreign_key_check").fetchall()
if foreign_key_errors:
    raise SystemExit(f"Data validation failed: foreign key violations detected: {foreign_key_errors[:5]}")
print("Persistent data validation passed.")
PYVERIFY
trap - EXIT
publish_manual_rollback "$PREVIOUS_VERSION"
prune_update_backups
report_progress "Update completed" 98 "The updated service is healthy; finalizing the update." "validating"
echo "Updated. Open: http://$(hostname -I | awk '{print $1}'):$PORT"
