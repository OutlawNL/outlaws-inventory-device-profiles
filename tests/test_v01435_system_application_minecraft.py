from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_system_checks_have_separate_system_and_application_columns():
    html=(ROOT/'app/templates/system_checks.html').read_text()
    assert '<th>Name</th><th>System</th><th>Application</th><th>Last Checked</th><th>Status</th><th>Action</th>' in html
    assert 'data-label="System"' in html
    assert 'data-label="Application"' in html

def test_minecraft_detail_is_compact():
    html=(ROOT/'app/templates/system_check_detail.html').read_text()
    assert '<span>Version</span>' in html
    assert 'minecraft-status-grid' in html

def test_desktop_check_items_stay_on_one_line():
    css=(ROOT/'app/static/app.css').read_text()
    assert '.system-checks-classic-table .health-check-list{flex-wrap:nowrap}' in css

def test_minecraft_runtime_refresh_is_part_of_health_cycle_without_latest_lookup():
    main=(ROOT/'app/main.py').read_text()
    assert 'def execute_minecraft_runtime_check' in main
    scheduler=main[main.index('def run_due_health_checks'):main.index('def _record_scheduler_start')]
    assert 'execute_minecraft_runtime_check(minecraft_check)' in scheduler
    runtime=main[main.index('def execute_minecraft_runtime_check'):main.index('def execute_application_check')]
    assert '_latest_minecraft_release()' not in runtime
