"""Behavioral regression tests for the v0.18.8 audit repairs.

Imports the real application; all data is temporary and all remote I/O is mocked.
No startup hooks, background jobs, host commands or production data are used.
"""
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
_runtime = tempfile.TemporaryDirectory(prefix="oi-audit-import-")
os.environ["OUTLAWS_DATA_DIR"] = _runtime.name
sys.path.insert(0, str(ROOT))
from app import main as m


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Unexpected external I/O")
    monkeypatch.setattr(m.requests.sessions.Session, "request", denied)
    monkeypatch.setattr(m.subprocess, "run", denied)
    monkeypatch.setattr(m.subprocess, "Popen", denied)
    monkeypatch.setattr(m.paramiko.SSHClient, "connect", denied)


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "live.sqlite3"
    monkeypatch.setattr(m, "DB_PATH", path)
    def connect():
        con = sqlite3.connect(path, timeout=0.05)
        con.row_factory = sqlite3.Row
        return con
    monkeypatch.setattr(m, "db", connect)
    return connect


def test_recovery_login_consumes_own_code_once(database):
    with database() as con:
        con.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,
          mfa_enabled INTEGER,totp_secret TEXT,recovery_codes_hash TEXT,is_active INTEGER,updated_at TEXT);
        CREATE TABLE mfa_login_challenges(id INTEGER PRIMARY KEY,user_id INTEGER,
          token_hash TEXT,expires_at TEXT);
        """)
        for uid, codes in [(1, ["ALPHA", "BETA"]), (2, ["OTHER"])]:
            con.execute("INSERT INTO users VALUES (?,?,?,1,'',?,1,'')",
                        (uid, str(uid), str(uid), m._recovery_hashes(codes)))
        con.execute("INSERT INTO mfa_login_challenges VALUES (2,1,?,'2099-01-01')",
                    (m._hash_session_token("challenge"),))
    request = SimpleNamespace(cookies={m.MFA_CHALLENGE_COOKIE: "challenge"})
    assert m._verify_totp_or_recovery(m._get_mfa_challenge(request), "ALPHA")
    with database() as con:
        rows = con.execute("SELECT recovery_codes_hash FROM users ORDER BY id").fetchall()
    assert json.loads(rows[0][0]) == json.loads(m._recovery_hashes(["BETA"]))
    assert json.loads(rows[1][0]) == json.loads(m._recovery_hashes(["OTHER"]))
    assert not m._verify_totp_or_recovery(m._get_mfa_challenge(request), "ALPHA")


def test_profile_version_format_mismatch_is_unknown_not_update(monkeypatch):
    firmware = {"version_comparison": {"current_version_pattern": r"^[0-9]+\.[0-9]+\.[0-9]{4}$"}}
    assert m._profile_versions_are_comparable("01.00.0400", "01.00.0500", firmware)
    assert not m._profile_versions_are_comparable("01.00.06.00", "01.00.0400", firmware)
    monkeypatch.setattr(m, "_check_device_provider", lambda device: {
        "status": "unknown", "latest": "01.00.0400", "_comparison_safe": False,
    })
    result = m.check_device({"current_firmware": "01.00.06.00", "latest_firmware_override": ""})
    assert result["latest"] == "01.00.0400"
    assert result["status"] == "unknown"
    assert "_comparison_safe" not in result


def test_failed_safety_copy_preserves_original_component_files(database, tmp_path, monkeypatch):
    with database() as con:
        con.execute("CREATE TABLE original(value TEXT)")
    components = tuple((name, tmp_path / name) for name in ("uploads", "keys", "secrets", "avatars"))
    for _, directory in components:
        directory.mkdir()
        (directory / "original.txt").write_text("must survive")
    monkeypatch.setattr(m, "BACKUP_COMPONENTS", components)
    monkeypatch.setattr(m, "validate_full_backup", lambda p: {})
    monkeypatch.setattr(m, "normalize_runtime_data_permissions", lambda: None)
    def fail_copy(*args, **kwargs):
        raise OSError("simulated disk full while capturing safety copy")
    monkeypatch.setattr(m.shutil, "copytree", fail_copy)
    with pytest.raises(OSError, match="simulated disk full"):
        m.restore_full_backup(tmp_path / "not-opened.zip")
    assert all((directory / "original.txt").exists() for _, directory in components)


def test_unhashed_extra_backup_file_is_rejected(tmp_path):
    data = b"database bytes for checksum-layer test"
    manifest = {"format": m.BACKUP_FORMAT, "schema_version": m.BACKUP_SCHEMA,
                "application_version": m.APP_VERSION,
                "files": [{"path": "database.sqlite3", "size": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()}]}
    path = tmp_path / "extra.oi-backup"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("database.sqlite3", data)
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("secrets/unlisted.txt", b"not covered by manifest")
    assert m._inspect_full_backup_integrity(path)["valid"] is False


def test_check_all_releases_write_lock_before_next_network_check(database, monkeypatch):
    with database() as con:
        con.execute("CREATE TABLE devices(id INTEGER,status TEXT,latest_firmware TEXT,release_date TEXT,release_summary TEXT,release_notes_url TEXT,confidence TEXT,firmware_source TEXT,check_method TEXT,last_checked TEXT,updated_at TEXT)")
        con.execute("INSERT INTO devices(id) VALUES (1)")
        con.execute("INSERT INTO devices(id) VALUES (2)")
    devices = [dict(id=i, category="Camera", auto_check=1, lifecycle="Supported",
                    firmware_source="", check_method="") for i in (1, 2)]
    monkeypatch.setattr(m, "fetch_devices", lambda: devices)
    monkeypatch.setattr(m, "category_config", lambda _: {"show_firmware": True})
    monkeypatch.setattr(m, "_firmware_monitoring_supported", lambda _: True)
    blocked = []
    def check(device):
        if device["id"] == 2:
            with database() as con:
                con.execute("UPDATE devices SET status='concurrent' WHERE id=2")
                blocked.append(True)
        return dict(status="ok", latest="1.0", release_date="", summary="", notes_url="", confidence="Official")
    monkeypatch.setattr(m, "check_device", check)
    assert m.execute_all_firmware_checks() == 2
    assert blocked == [True]


def test_new_device_check_keeps_async_event_loop_responsive(monkeypatch):
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): return SimpleNamespace(lastrowid=1)
    monkeypatch.setattr(m, "db", Connection)
    monkeypatch.setattr(m, "_available_device_profile", lambda *a, **k: None)
    monkeypatch.setattr(m, "_initial_device_firmware_check", lambda _: time.sleep(0.2) or "")
    kwargs = {name: param.default.default for name, param in inspect.signature(m.create_device).parameters.items()
              if hasattr(param.default, "default")}
    kwargs.update(request=SimpleNamespace(state=SimpleNamespace(user={"id": 1})), display_name="Audit device")
    async def exercise():
        ticks = []
        async def heartbeat():
            await asyncio.sleep(0.02)
            ticks.append(time.monotonic())
        start = time.monotonic()
        pulse = asyncio.create_task(heartbeat())
        await asyncio.sleep(0)
        await m.create_device(**kwargs)
        await pulse
        return ticks[0] - start
    assert asyncio.run(exercise()) < 0.15


def test_catalog_match_download_failure_does_not_fall_back_to_legacy(monkeypatch):
    monkeypatch.setattr(m, "device_profiles_catalog", lambda: {"profiles": [{"id": "matched"}]})
    monkeypatch.setattr(m, "match_device_profile", lambda *args: {"id": "matched"})
    def unavailable(*args, **kwargs): raise OSError("profile download unavailable, no cache")
    monkeypatch.setattr(m, "ensure_device_profile", unavailable)
    monkeypatch.setattr(m, "_firmware_monitoring_supported", lambda _: True)
    marker = {"status": "ok", "latest": "legacy-version"}
    monkeypatch.setattr(m, "_onkyo_result", lambda _: marker)
    assert m._check_device_provider({"vendor": "Example", "model": "Camera", "lifecycle": "Supported", "firmware_url": ""})["status"] == "unknown"


def test_end_of_support_without_verified_latest_stays_unknown():
    device = dict(vendor="Example", model="Camera", firmware_provider="Auto", firmware_url="",
                  lifecycle="End of Support", latest_firmware="", current_firmware="1.0",
                  release_date="", release_summary="", release_notes_url="", confidence="Unknown",
                  firmware_source="Unknown", check_method="Not configured")
    result = m._check_device_provider(device)
    assert result["status"] == "unknown"
    assert result["latest"] == ""
    assert result["confidence"] == "Unknown"


def test_daily_backup_catches_up(database, monkeypatch):
    class Clock:
        @staticmethod
        def now(): return m.datetime_original(2026, 9, 12, 2, 1)
    monkeypatch.setattr(m, "datetime_original", m.datetime, raising=False)
    monkeypatch.setattr(m, "datetime", Clock)
    monkeypatch.setattr(m, "backup_settings", lambda: dict(schedule="daily", time="02:00", last_run="", retention=10))
    with database() as con: con.execute("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)")
    calls = []
    monkeypatch.setattr(m, "create_full_backup", lambda kind: calls.append(kind))
    monkeypatch.setattr(m, "prune_backups", lambda _: None)
    assert m.run_due_automatic_backup() == "backup completed"
    assert calls == ["automatic"]


def test_delete_other_users_device_preserves_attachments(database, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(m, "require_current_user_id", lambda: 1)
    attachment = tmp_path / "other-users-attachment.txt"
    attachment.write_text("belongs to user 2")
    with database() as con:
        con.executescript("CREATE TABLE devices(id INTEGER, owner_user_id INTEGER); CREATE TABLE attachments(device_id INTEGER,stored_name TEXT);")
        con.execute("INSERT INTO devices VALUES (42,2)")
        con.execute("INSERT INTO attachments VALUES (42,?)", (attachment.name,))
    m.delete_device(42)
    with database() as con:
        assert con.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 1
    assert attachment.exists()


class FakeSSH:
    def __init__(self, output, error=""):
        self.output, self.error, self.commands = output, error, []
        self.policy = None
    def load_system_host_keys(self): pass
    def set_missing_host_key_policy(self, policy): self.policy = policy
    def connect(self, **kwargs): pass
    def close(self): pass
    def exec_command(self, command, **kwargs):
        self.commands.append(command)
        channel = SimpleNamespace(recv_exit_status=lambda: 0)
        return None, SimpleNamespace(read=lambda: self.output.encode(), channel=channel), SimpleNamespace(read=lambda: self.error.encode())


def test_ssh_pin_verifies_before_authentication(monkeypatch):
    from app.ssh_transport import ssh_client, PinnedHostKeyPolicy
    import base64
    key = m.paramiko.RSAKey.generate(1024)
    pin = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
    client = ssh_client({"known_host_fingerprint": pin})
    assert isinstance(client._policy, PinnedHostKeyPolicy)
    client._policy.missing_host_key(client, "example", key)
    with pytest.raises(m.paramiko.SSHException, match="mismatch"):
        client._policy.missing_host_key(client, "example", m.paramiko.RSAKey.generate(1024))


def test_apt_failure_stops_before_successful_reboot_probe(monkeypatch):
    import subprocess
    client = FakeSSH("", "sudo: a password is required")
    original = client.exec_command
    def command(cmd, **kwargs):
        assert cmd.startswith("sudo -n /usr/bin/apt-get update || exit $?;")
        stdin, stdout, stderr = original(cmd, **kwargs)
        stdout.channel.recv_exit_status = lambda: 1
        return stdin, stdout, stderr
    client.exec_command = command
    monkeypatch.setattr(m, "_ssh_client", lambda _: client)
    monkeypatch.setattr(m, "_load_private_key", lambda _: None)
    monkeypatch.setattr(m, "_profile_for_update_check", lambda _: dict(private_key_path="fake", port=22, username="outlaw"))
    result = m.run_remote_update_check(dict(host="192.0.2.1", system_type="debian"))
    assert result["status"] == "failed"
    assert result["error"]


def test_ssh_profile_form_saves_and_updates_per_owner(database, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "KEY_DIR", tmp_path)
    (tmp_path / "fake-key").write_text("not a real key")
    with database() as con:
        con.execute("CREATE TABLE ssh_profiles(owner_user_id INTEGER,name TEXT,username TEXT,port INTEGER,private_key_path TEXT,known_host_fingerprint TEXT,created_at TEXT,updated_at TEXT,UNIQUE(owner_user_id,name))")
    for owner, port in [(1,22),(2,23),(1,24)]:
        monkeypatch.setattr(m, "require_current_user_id", lambda: owner)
        assert m.add_ssh_profile("Audit", "outlaw", port, "fake-key", "").status_code == 303
    with database() as con:
        assert [tuple(r) for r in con.execute("SELECT owner_user_id,port FROM ssh_profiles ORDER BY owner_user_id")] == [(1,24),(2,23)]


def test_disabling_all_health_checks_preserves_empty_selection(monkeypatch):
    monkeypatch.setattr(m, "fetch_device", lambda _: {"display_name": "Audit", "name": "Audit"})
    monkeypatch.setattr(m, "fetch_device_health_check", lambda _: None)
    monkeypatch.setattr(m, "resolved_target", lambda *a: "192.0.2.1")
    monkeypatch.setattr(m, "get_settings", lambda: {})
    seen = []
    class StopAfterCapture(Exception): pass
    def capture(*args):
        seen.extend(args[7])
        raise StopAfterCapture()
    monkeypatch.setattr(m, "_save_health_group", capture)
    kwargs = {name: param.default.default for name, param in inspect.signature(m.save_system_check_detail).parameters.items()
              if hasattr(param.default, "default")}
    kwargs.update(device_id=1, request=None)
    with pytest.raises(StopAfterCapture): m.save_system_check_detail(**kwargs)
    assert seen == []


def test_health_90_minute_interval_does_not_run_after_60_minutes():
    check = dict(enabled=1, maintenance=0, interval_minutes=90, last_checked="2026-09-12 12:00")
    assert m.health_check_is_due(check, m.datetime(2026, 9, 12, 13, 0)) is False
