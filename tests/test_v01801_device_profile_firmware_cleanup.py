from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORM = (ROOT / "app/templates/device_form.html").read_text(encoding="utf-8")
SETTINGS = (ROOT / "app/templates/settings.html").read_text(encoding="utf-8")
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_release_is_v01802():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_firmware_ui_exposes_only_url_and_filter_for_generic_configuration():
    assert "Firmware Filter / Keyword" in FORM
    assert 'id="generic-firmware-config"' in FORM
    assert "Firmware Provider<select" not in FORM
    assert "Firmware Source<select" not in FORM
    assert "Check Method<select" not in FORM
    assert "Confidence<select" not in FORM
    assert "Provider Identifier" not in FORM


def test_device_profile_notice_lives_in_firmware_configuration():
    firmware_pos = FORM.index('id="firmware"')
    profile_pos = FORM.index('id="device-profile-match"')
    assert profile_pos > firmware_pos
    assert "Firmware checking is managed automatically by this Device Profile." in FORM


def test_settings_lists_installed_profiles():
    assert 'class="installed-device-profiles"' in SETTINGS
    assert "profile.vendor" in SETTINGS
    assert "profile.model" in SETTINGS
    assert "profile.profile_version" in SETTINGS


def test_dji_download_discovery_handles_escaped_page_data_and_product_scoring():
    assert 'normalized = normalized.replace("\\\\/", "/")' in MAIN
    assert 're.sub(r"\\\\u002[fF]", "/", normalized)' in MAIN
    assert '"assistant" in low' in MAIN
    assert 'requested_tokens' in MAIN
    assert '20\\d{6}' in MAIN


def test_device_profile_check_records_automatic_method_and_official_confidence():
    assert 'check_method = "Device Profile"' in MAIN
    assert 'confidence = "Official"' in MAIN
    assert '"method": f"Device Profile · {profile_name}"' in MAIN
