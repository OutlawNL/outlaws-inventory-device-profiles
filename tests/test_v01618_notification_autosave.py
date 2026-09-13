from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
SETTINGS = (ROOT / "app" / "templates" / "settings.html").read_text(encoding="utf-8")


def test_v01618_version():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_notification_preferences_have_dedicated_autosave():
    names = (
        "notifications_enabled",
        "notification_health_enabled",
        "notification_firmware_enabled",
        "notification_updates_enabled",
        "notification_application_enabled",
    )
    assert '@app.post("/settings/notifications/autosave")' in MAIN
    for name in names:
        assert f'name="{name}" data-notification-autosave' in SETTINGS
        assert f'"{name}"' in MAIN
    assert "body:JSON.stringify({[el.name]:el.checked})" in SETTINGS
    assert "notificationAutosaveStatus.textContent = 'Saved'" in SETTINGS


def test_normal_smtp_save_does_not_rewrite_notification_preferences():
    route = MAIN.split('@app.post("/settings/notifications")', 1)[1].split('@app.post("/settings/notifications/autosave")', 1)[0]
    assert 'if return_to == "first-run":' in route
    assert 'values.update({"notifications_enabled"' in route
    # SMTP fields remain part of the explicit save operation.
    assert '"smtp_host":smtp_host.strip()' in route
    assert '"application_base_url":application_base_url.strip().rstrip("/")' in route


def test_notification_autosave_isolated_from_smtp_fields():
    route = MAIN.split('@app.post("/settings/notifications/autosave")', 1)[1].split('@app.post("/settings/notifications/test")', 1)[0]
    assert '"smtp_host"' not in route
    assert '"smtp_password"' not in route
    assert '"smtp_recipient_address"' not in route
