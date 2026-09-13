from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_uses_dedicated_noninteractive_service_account():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'SERVICE_USER="outlaws-inventory"' in text
    assert 'groupadd --system "$SERVICE_USER"' in text
    assert 'useradd --system --gid "$SERVICE_USER"' in text
    assert '--shell /usr/sbin/nologin' in text
    assert 'User=$SERVICE_USER' in text
    assert 'Group=$SERVICE_USER' in text
    assert 'outlaw ALL=(root)' not in text


def test_update_migrates_to_service_account_without_deleting_human_outlaw():
    text = (ROOT / "update.sh").read_text(encoding="utf-8")
    assert 'SERVICE_USER="outlaws-inventory"' in text
    assert 'PREVIOUS_SERVICE_USER=' in text
    assert 'useradd --system --gid "$SERVICE_USER"' in text
    assert 'userdel outlaw' not in text
    assert 'deluser outlaw' not in text
    assert 'outlaw ALL=(root)' not in text


def test_failed_service_account_migration_restores_system_integration():
    text = (ROOT / "update.sh").read_text(encoding="utf-8")
    assert 'system-integration/service.unit' in text
    assert 'system-integration/sudoers' in text
    assert 'outlaws-inventory-self-update-launcher' in text
    assert 'restore_user="${PREVIOUS_SERVICE_USER:-$SERVICE_USER}"' in text


def test_self_update_and_rollback_helpers_use_dedicated_service_account():
    for name in ("outlaws-inventory-self-update", "outlaws-inventory-self-rollback"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert 'SERVICE_USER="outlaws-inventory"' in text
        assert 'chown outlaw:outlaw' not in text


def test_installer_verifies_service_account_ping_capability():
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    update = (ROOT / "update.sh").read_text(encoding="utf-8")
    for text in (install, update):
        assert "iputils-ping" in text
        assert "libcap2-bin" in text
        assert 'runuser -u "$SERVICE_USER" -- /usr/bin/ping' in text
        assert 'setcap cap_net_raw+ep /usr/bin/ping' in text


def test_health_notification_hides_internal_ping_diagnostics():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    health = main[main.index('if cfg["health_enabled"]'):main.index('if cfg["firmware_enabled"]')]
    assert 'text=f\'{r["name"]}: {r["status"]}\'' in health
    assert 'r["last_error"]' not in health
    assert '"/system-checks"' in health


def test_notification_singular_plural_grammar():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'verb = "require" if event_count != 1 else "requires"' in main
    assert 'f"{event_count} item{plural} {verb} attention"' in main
    assert 'detected an item that needs review.' in main


def test_notification_routes_are_current():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    start = main.index("def collect_notification_events")
    end = main.index("def dispatch_notifications", start)
    block = main[start:end]
    assert '"/health"' not in block
    assert '"/updates"' not in block
    assert '"/system-checks"' in block
    assert '"/settings?update_open=1#application-version"' in block
