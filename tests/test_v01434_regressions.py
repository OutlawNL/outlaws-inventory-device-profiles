from pathlib import Path

MAIN = Path('app/main.py').read_text()
HOST = Path('app/templates/host_integration_form.html').read_text()
INSTALL = Path('install.sh').read_text()
UPDATE = Path('update.sh').read_text()

def test_version_tuple_uses_current_semver_rules():
    assert 're.fullmatch' in MAIN
    assert 'parts[0] == 0 and parts[1] == 8' not in MAIN

def test_minecraft_permission_is_actually_probed():
    assert "printf '__MINECRAFTUPDATE__" in MAIN
    assert 'sudo -n -l /usr/local/sbin/outlaws-minecraft-update /tmp/outlaws-validation.jar' in MAIN

def test_reconfigure_groups_host_and_application_checks():
    assert 'System Checks' in HOST
    assert 'Application Checks' in HOST

def test_existing_outlaw_profile_can_be_normalized():
    assert "UPDATE ssh_profiles SET name='System Checks'" in MAIN

def test_installer_updater_show_version_and_avoid_unconditional_usermod():
    assert "Installing Outlaw's Inventory v${EXPECTED_VERSION}" in INSTALL
    assert "Updating Outlaw's Inventory to v${SOURCE_VERSION}" in UPDATE
    assert 'current_home="$(getent passwd "$SERVICE_USER"' in INSTALL
    assert 'current_home="$(getent passwd "$SERVICE_USER"' in UPDATE
