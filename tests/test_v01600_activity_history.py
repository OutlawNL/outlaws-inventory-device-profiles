from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()
DEVICE = (ROOT / "app/templates/device_form.html").read_text()


def test_release_version_and_history_schema():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'CREATE TABLE IF NOT EXISTS activity_history' in MAIN
    assert 'idx_activity_history_device' in MAIN
    assert 'def add_activity_event(' in MAIN
    assert 'def fetch_activity_history(' in MAIN


def test_meaningful_actions_are_recorded():
    for event in ('system_upgrade', 'reboot', 'pihole_update', 'minecraft_update', 'firmware_update'):
        assert f'"{event}"' in MAIN
    assert '"Maintenance Mode Enabled"' in MAIN
    assert '"Maintenance Mode Disabled"' in MAIN
    assert 'previous_maintenance != requested_maintenance' in MAIN


def test_firmware_history_only_follows_mark_updated_action():
    mark = MAIN[MAIN.index('def mark_firmware_updated'):MAIN.index('def defer_firmware_update')]
    assert 'add_activity_event' in mark
    check = MAIN[MAIN.index('def check_one'):MAIN.index('def mark_firmware_updated')]
    assert 'add_activity_event' not in check


def test_system_detail_moves_action_output_to_history():
    assert '<h3>History</h3>' in DETAIL
    assert '{{ event.details }}' in DETAIL
    assert '<summary>Upgrade Output</summary>' not in DETAIL
    assert '<summary>Reboot Output</summary>' not in DETAIL
    assert '<summary>Update Output</summary>' not in DETAIL


def test_device_detail_uses_generic_history():
    assert '<strong>History</strong>' in DEVICE
    assert '{{ event.title }}' in DEVICE
    assert 'Recent activity' not in DEVICE
