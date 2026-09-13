from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_general_notification_dashboard_link_uses_root():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'target_url = base if base else ""' in main
    assert 'target_url = f"{base}/dashboard"' not in main


def test_ssh_profiles_have_clear_add_and_configured_sections():
    template = (ROOT / "app/templates/settings.html").read_text(encoding="utf-8")
    assert ">Add SSH Profile<" in template
    assert ">Configured Profiles<" in template


def test_obsolete_product_rename_conversion_is_gone():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8").lower()
    assert "old_install_prefix" not in main
    assert "outlaw's inventory" in main


def test_backup_baseline_is_current_supported_line():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'version_tuple(backup_version) < version_tuple("0.15.0")' in main
