from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
OVERVIEW = (ROOT / "app/templates/system_checks.html").read_text()


def test_release_version_is_0165():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN
    assert 'INSTALLER_VERSION = "0.18.8"' in MAIN


def test_health_autosave_preserves_existing_results_and_checks_only_new_type():
    assert 'previously_enabled_health_types' in MAIN
    assert 'newly_enabled_health_types = requested_health_types - previously_enabled_health_types' in MAIN
    assert 'next_status = previous_status' in MAIN
    assert 'check_type in newly_enabled_health_types' in MAIN


def test_apt_is_checked_immediately_when_reenabled():
    assert 'apt_was_enabled = bool(existing_update and existing_update["enabled"])' in MAIN
    assert 'if update_check and update_check["enabled"] and (not autosave or not apt_was_enabled):' in MAIN


def test_application_checks_still_check_immediately_when_reenabled():
    assert 'if pihole_check and (not autosave or not pihole_was_enabled):' in MAIN
    assert 'if minecraft_check and (not autosave or not minecraft_was_enabled):' in MAIN


def test_system_checks_overview_refreshes_silently_every_minute():
    assert 'window.setInterval(refreshSystemChecksOverview, 60000);' in OVERVIEW
    assert "fetch(`/system-checks?_live=${Date.now()}`" in OVERVIEW
    assert "cache: 'no-store'" in OVERVIEW
    assert "window.location.reload()" not in OVERVIEW
    assert "currentCard.innerHTML = freshCard.innerHTML" in OVERVIEW


def test_live_refresh_uses_delegated_handlers_for_replaced_rows():
    assert "document.addEventListener('click'" in OVERVIEW
    assert "document.addEventListener('submit'" in OVERVIEW
    assert "event.target.closest('.classic-name-update-toggle')" in OVERVIEW
