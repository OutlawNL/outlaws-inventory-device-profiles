from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()


def test_release_is_v01609_and_css_payload_is_real_css():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert "\\n\\n/* v0.16.8" not in CSS
    assert ".system-checks-classic-table .system-checks-host-row > td" in CSS
    assert ".classic-system-detail-form #updates" in CSS
    assert "max-width:100%!important" in CSS


def test_disabled_health_checks_are_not_rendered_in_overview_model():
    start = MAIN.index("def _system_check_rows")
    end = MAIN.index("\ndef _first_run_counts", start)
    block = MAIN[start:end]
    assert 'if not row["enabled"]:' in block
    assert "continue" in block


def test_final_health_check_can_be_disabled_and_scheduler_respects_enabled():
    start = MAIN.index("def _save_health_group")
    end = MAIN.index("\ndef _run_saved_health_group", start)
    block = MAIN[start:end]
    assert 'if not checks:' in block
    assert 'SET enabled=0' in block
    assert 'if not checks: checks=["ping"]' not in block
    sched_start = MAIN.index("def run_due_health_checks")
    sched_end = MAIN.index("\ndef _record_scheduler_start", sched_start)
    scheduler = MAIN[sched_start:sched_end]
    assert 'if check["enabled"] and not check["maintenance"]' in scheduler


def test_system_upgrade_success_uses_standard_green_notice():
    assert '<div class="notice success">System upgrade completed successfully.' in DETAIL
