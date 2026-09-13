from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()
OVERVIEW = (ROOT / "app/templates/system_checks.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()


def test_release_version_and_ping_can_be_fully_disabled():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'requested_health_types = set(checks)' in MAIN
    assert 'set(checks or ["ping"])' not in MAIN
    assert '<strong>Ping</strong><small>Checks basic network reachability using ICMP</small>' in DETAIL
    assert '{% if server.ping_check %}<span class="health-check-item">' in OVERVIEW
    assert '</b>Ping</span>{% endif %}' in OVERVIEW


def test_history_is_grouped_and_raw_output_is_secondary():
    assert 'def group_activity_history(events)' in MAIN
    for title in ('System Upgrades', 'Reboots', 'Minecraft', 'Pi-hole', 'Maintenance'):
        assert title in MAIN
    assert 'activity_history_groups=group_activity_history' in MAIN
    assert 'class="activity-history-group"' in DETAIL
    assert 'class="history-command-output"' in DETAIL
    assert '<summary>Command Output</summary>' in DETAIL


def test_success_notice_is_transient_and_mobile_order_is_semantic():
    assert "['upgrade','reboot','minecraft_update','pihole_update']" in DETAIL
    assert 'window.history.replaceState' in DETAIL
    assert '#checks{order:1} #updates{order:2} #minecraft-updates,#pihole-updates{order:3} #history{order:4}' in CSS
