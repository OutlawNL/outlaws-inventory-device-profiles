from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'app/main.py').read_text()
DETAIL = (ROOT / 'app/templates/system_check_detail.html').read_text()
HOST = (ROOT / 'app/templates/host_integration_form.html').read_text()


def test_minecraft_port_health_is_checked():
    assert 'def _minecraft_port_status' in MAIN
    assert "'server_port': int(port_status.get('port') or 0)" in MAIN
    assert 'is running but {detail} is not listening' in MAIN
    assert 'Port</span>' in DETAIL
    assert 'Listening' in DETAIL and 'Not listening' in DETAIL


def test_minecraft_safe_upgrade_action_exists():
    assert 'def run_remote_minecraft_update' in MAIN
    assert '/usr/local/sbin/outlaws-minecraft-update' in MAIN
    assert 'version_manifest_v2.json' in MAIN
    assert 'Downloaded server.jar failed Mojang SHA-1 verification.' in MAIN
    assert 'Update failed; previous server.jar restored.' in MAIN
    assert '/applications/minecraft/update' in MAIN
    assert 'Upgrade Minecraft' in DETAIL


def test_reconfigure_can_provision_minecraft_update_permission():
    assert 'enable_minecraft: bool = False' in MAIN
    assert 'Minecraft update permission' in MAIN
    assert 'create_minecraft' in HOST
