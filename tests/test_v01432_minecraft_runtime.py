from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text()
OVERVIEW = (ROOT / "app" / "templates" / "system_checks.html").read_text()
DETAIL = (ROOT / "app" / "templates" / "system_check_detail.html").read_text()

def test_minecraft_runtime_is_checked_separately_from_jar_version():
    assert "def _minecraft_runtime_status" in MAIN
    assert "ActiveState,SubState,NRestarts,MainPID,Result" in MAIN
    assert "runtime_state in ('failed','stopped')" in MAIN
    assert "runtime_state != 'running'" in MAIN

def test_minecraft_crash_loop_is_not_treated_as_running():
    assert "restarts>=3 and age is not None and age<60" in MAIN
    assert "crash loop" in MAIN

def test_minecraft_overview_is_compact_and_details_show_runtime():
    assert "</b>Minecraft{% if server.minecraft.status=='available' %}<small>update</small>{% endif %}" not in OVERVIEW
    assert "</b>Minecraft" in OVERVIEW
    assert "<span>Service</span>" in DETAIL
    assert "runtime_status" in DETAIL
