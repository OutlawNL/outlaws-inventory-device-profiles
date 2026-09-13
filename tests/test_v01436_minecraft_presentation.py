from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = (ROOT / "app/templates/system_checks.html").read_text()
DETAIL = (ROOT / "app/templates/system_check_detail.html").read_text()
CSS = (ROOT / "app/static/app.css").read_text()
MAIN = (ROOT / "app/main.py").read_text()


def test_empty_application_cells_are_visually_empty():
    assert 'if not server.http_check and not server.pihole and not server.minecraft' not in OVERVIEW


def test_minecraft_status_uses_three_column_rows_without_details_disclosure():
    assert 'class="minecraft-status-grid"' in DETAIL
    assert DETAIL.count('class="minecraft-status-row"') >= 3
    assert 'minecraft-extra-details' not in DETAIL
    assert '<summary>Details</summary>' not in DETAIL
    assert "server.minecraft.details.service_unit or 'Unknown'" in DETAIL
    assert "server.minecraft.details.current or 'Unknown'" in DETAIL
    assert "Update available: {{ server.minecraft.details.latest or 'Unknown' }}" in DETAIL
    assert "'Listening' if server.minecraft.details.port_listening else 'Not listening'" in DETAIL
    assert 'Server JAR</span>' not in DETAIL
    assert '.minecraft-status-row{display:grid;grid-template-columns:' in CSS


def test_minecraft_updater_keeps_exactly_one_previous_jar():
    start = MAIN.index("backup=jar+'.outlaws-previous'")
    block = MAIN[start:start + 4000]
    assert 'if os.path.exists(backup): os.unlink(backup)' in block
    assert 'os.replace(jar,backup); os.replace(tmp,jar)' in block
    assert '.outlaws-previous.' not in block
