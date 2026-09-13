from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_application_version_opens_only_when_explicitly_requested():
    template = (ROOT / "app/templates/settings.html").read_text()
    assert "{% if update_open == '1' %}open{% endif %}" in template
    assert "update_open == '1' or application_update.update_available" not in template
    assert "update_open == '1' or application_update.newer_than_release" not in template

def test_update_available_still_marks_application_version_visually():
    template = (ROOT / "app/templates/settings.html").read_text()
    assert "application_update.update_available %} update-available" in template
    assert "Application Version{% if application_update.update_available %} · Update Available{% endif %}" in template
