from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "app" / "templates" / "dashboard.html").read_text(encoding="utf-8")
IDEAS = (ROOT / "docs" / "IDEAS.md").read_text(encoding="utf-8")


def test_release_version_is_v01631():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_dashboard_refreshes_silently_from_authoritative_page_render():
    assert "async function refreshDashboardOverview()" in DASHBOARD
    assert "fetch(`/?_live=${Date.now()}`" in DASHBOARD
    assert "window.setInterval(refreshDashboardOverview, 60000)" in DASHBOARD
    assert "window.addEventListener('pageshow'" in DASHBOARD
    assert "currentHero.className = freshHero.className" in DASHBOARD
    assert "currentKpis.innerHTML = freshKpis.innerHTML" in DASHBOARD
    assert "currentActions.innerHTML = freshActions.innerHTML" in DASHBOARD
    assert "window.location.reload" not in DASHBOARD


def test_dashboard_still_uses_shared_system_check_summary():
    assert "hcounts = health_summary()" in MAIN
    assert '"Return one effective status per host, identical to the System Checks page."' in MAIN


def test_software_checks_are_an_idea_with_clear_application_boundary():
    assert "## Software Checks / Software Version Tracking" in IDEAS
    assert "DJI Reframe" in IDEAS
    assert "VST/VST3" in IDEAS
    assert "Pi-hole and Minecraft remain **Application Checks**" in IDEAS
    assert "must not be duplicated under Software Checks" in IDEAS
