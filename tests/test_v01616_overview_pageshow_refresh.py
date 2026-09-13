from pathlib import Path

TEMPLATE = Path("app/templates/system_checks.html").read_text()
MAIN = Path("app/main.py").read_text()


def test_release_version():
    assert 'APP_VERSION = "0.18.8"' in MAIN


def test_overview_refreshes_when_restored_or_shown():
    assert "window.addEventListener('pageshow'" in TEMPLATE
    assert 'refreshSystemChecksOverview();' in TEMPLATE
    assert 'window.setInterval(refreshSystemChecksOverview, 60000);' in TEMPLATE
    assert "cache: 'no-store'" in TEMPLATE
