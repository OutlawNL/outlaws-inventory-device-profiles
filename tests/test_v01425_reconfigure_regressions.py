from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _main():
    return (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_release_version_01425():
    main = _main()
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in main


def test_ssh_directory_install_uses_separate_owner_and_group_arguments():
    block = _main()[_main().index("def configure_remote_host"):_main().index("def ensure_managed_host_checks")]
    line = next(line for line in block.splitlines() if "install -d -m 700" in line)
    assert " -o " in line
    assert " -g " in line
    assert ':\\"$managed_group\\"' not in line


def test_reconfigure_form_reflects_pihole_and_existing_check_state():
    form = (ROOT / "app/templates/host_integration_form.html").read_text(encoding="utf-8")
    main = _main()
    assert 'name="create_pihole"' in form
    assert 'setup_checks.pihole' in form
    assert 'setup_checks.health' in form
    assert 'setup_checks.updates' in form
    assert '"pihole": bool(pihole and pihole["enabled"])' in main


def test_reconfigure_pihole_permission_matches_selected_check():
    main = _main()
    block = main[main.index("def configure_remote_host"):main.index("def ensure_managed_host_checks")]
    assert "enable_pihole: bool = False" in block
    assert "if enable_pihole:" in block
    assert 'NOPASSWD: /usr/local/bin/pihole -up --check-only' in block
    assert 'NOPASSWD: /usr/local/bin/pihole -up' in block


def test_existing_managed_checks_are_not_reset_on_reconfigure():
    main = _main()
    block = main[main.index("def ensure_managed_host_checks"):main.index('@app.get("/devices/{device_id}/host-integration"')]
    assert "current != desired" in block
    assert "status='unknown'" not in block.split("def ensure_managed_pihole_check", 1)[0]
    assert "UPDATE update_checks SET ssh_profile_id=?, host=?, system_type=?, enabled=1, updated_at=?" in block


def test_successful_reconfigure_rechecks_enabled_pihole():
    main = _main()
    route = main[main.index('@app.post("/devices/{device_id}/host-integration")'):main.index('@app.post("/devices/{device_id}/host-integration/validate")')]
    assert "ensure_managed_pihole_check(device, ssh_profile_id, bool(create_pihole))" in route
    assert 'if pihole and pihole["enabled"]:' in route
    assert "execute_application_check(pihole)" in route
