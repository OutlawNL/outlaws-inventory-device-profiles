from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/templates/system_check_detail.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()

def test_history_is_compact_neutral():
    assert 'class="card history-card"' in TEMPLATE
    assert 'activity-history-chevron' in TEMPLATE
    assert 'class="pill ' not in TEMPLATE[TEMPLATE.index('id="history"'):TEMPLATE.index('{% if server.minecraft %}', TEMPLATE.index('id="history"'))]
    assert '.activity-history-main strong{font-size:14px' in CSS

def test_history_details_contain_result_summary_and_output():
    block = TEMPLATE[TEMPLATE.index('id="history"'):TEMPLATE.index('{% if server.minecraft %}', TEMPLATE.index('id="history"'))]
    assert '<span>Result</span>' in block
    assert '<span>Details</span>' in block
    assert '<pre class="command-output">{{ event.details }}</pre>' in block
    assert '{{ event.created_at }}{% if event.summary %}' not in block

def test_failure_notices_reference_history():
    assert 'Open the History entry for details.' in TEMPLATE
    assert 'Open Upgrade Output below' not in TEMPLATE
    assert 'Open Reboot Output below' not in TEMPLATE
