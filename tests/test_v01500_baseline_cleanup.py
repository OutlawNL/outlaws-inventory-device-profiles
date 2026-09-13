from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
UPDATE = (ROOT / "update.sh").read_text(encoding="utf-8")


def test_v01500_is_new_release_baseline():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN
    assert 'INSTALLER_VERSION = "0.18.8"' in MAIN
    assert 'version("0.15.0")' in UPDATE
    assert 'version_tuple(backup_version) < version_tuple("0.15.0")' in MAIN


def test_historical_schema_migrations_are_removed():
    init_db = MAIN[MAIN.index("def init_db() -> None:"):MAIN.index("def get_settings()", MAIN.index("def init_db() -> None:"))]
    assert "ALTER TABLE" not in init_db
    assert "PRAGMA table_info" not in init_db
    assert "health_migrations" not in init_db
    assert "device_migrations" not in init_db


def test_current_schema_is_canonical_for_new_installs():
    required_fragments = (
        "managed_ssh_profile_id INTEGER",
        "integration_details TEXT DEFAULT '{}'",
        "disk_warning_percent INTEGER",
        "disk_critical_percent INTEGER",
        "display_name TEXT DEFAULT ''",
        "must_change_password INTEGER NOT NULL DEFAULT 0",
        "show_system_checks INTEGER NOT NULL DEFAULT 0",
        "minecraft_jar_path TEXT DEFAULT 'server.jar'",
        "reboot_required INTEGER DEFAULT 0",
        "minecraft_jar_path TEXT DEFAULT ''",
    )
    for fragment in required_fragments:
        assert fragment in MAIN


def test_abandoned_runtime_compatibility_is_gone():
    forbidden = (
        "sa-outlaws-inventory",
        "System Checks (legacy ",
        "Backwards-compatible aliases",
        "automatic_update_schedule",
        "run_due_update_checks",
        "install_application_update_compatibility_route",
        "/settings/application-update/repository",
        "protected_ssh_profile_ids",
    )
    for value in forbidden:
        assert value not in MAIN
        assert value not in UPDATE


def test_updater_preserves_all_persistent_row_counts():
    assert 'manifest = {"counts": counts}' in UPDATE
    assert 'if current < expected:' in UPDATE
    assert 'if table == "ssh_profiles"' not in UPDATE
