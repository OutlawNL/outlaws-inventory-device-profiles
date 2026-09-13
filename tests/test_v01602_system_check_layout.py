from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()
DEVICE = (ROOT / "app/templates/device_form.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()

def test_system_check_columns_stack_independently():
    left = DETAIL[DETAIL.index('system-detail-column-left'):DETAIL.index('system-detail-column-right')]
    right = DETAIL[DETAIL.index('system-detail-column-right'):DETAIL.index('</form>', DETAIL.index('system-detail-column-right'))]
    assert left.index('id="checks"') < left.index('id="history"')
    assert 'id="updates"' not in left
    assert right.index('id="updates"') < right.index('{% if server.minecraft %}')
    assert 'id="minecraft-updates"' in right
    assert 'id="pihole-updates"' in right
    assert '.system-detail-column{display:flex;flex-direction:column;gap:16px' in CSS

def test_device_history_is_neutral_and_keeps_count_badge():
    block = DEVICE[DEVICE.index('class="card full device-history"'):DEVICE.index('<div class="card full device-attachments-card">', DEVICE.index('class="card full device-history"'))]
    assert 'history-count' in block
    assert "event.result=='success' %}ok" not in block
    assert '>Success<' not in block
    assert '>Failed<' not in block
    assert '<span>Result</span>' in block
    assert 'history-chevron' in block
