from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text()
CSS = (ROOT / "app/static/app.css").read_text()


def test_release_version():
    assert 'APP_VERSION = "0.18.8"' in MAIN


def test_http_check_never_falls_back_to_host():
    block = MAIN[MAIN.index("def run_health_check"):MAIN.index("def _health_last_checked")]
    assert 'target = check["url"] if check_type == "http" else check["host"]' in block
    assert 'if check_type == "http" else check["host"]) or check["host"]' not in block
    assert 'No HTTP(S) URL configured' in block


def test_http_url_subsection_matches_section_hierarchy():
    block = CSS[CSS.index("/* v0.16.13 System Check field hierarchy */"):]
    assert '.http-url-settings{' in block
    assert 'margin-top:14px;' in block
    assert 'padding-top:12px;' in block
    assert 'border-top:1px solid var(--line);' in block
