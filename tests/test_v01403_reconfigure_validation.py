from pathlib import Path

def test_reconfigure_always_uses_dedicated_system_checks_profile():
    text = Path("app/main.py").read_text()
    page = text[text.index("def host_integration_page"):text.index("@app.post(\"/devices/{device_id}/host-integration\")")]
    assert "dedicated_profile = ensure_system_check_profile()" in page
    assert 'selected_id = int(dedicated_profile["id"])' in page
    assert "profile = dedicated_profile" in page

    post = text[text.index("def configure_host_integration"):text.index("@app.post(\"/devices/{device_id}/host-integration/validate\")")]
    assert "profile = ensure_system_check_profile()" in post
    assert 'ssh_profile_id = int(profile["id"])' in post
    assert "fetch_ssh_profile(ssh_profile_id) if ssh_profile_id" not in post

def test_configure_remote_host_requires_all_live_managed_permissions():
    text = Path("app/main.py").read_text()
    start = text.index("def configure_remote_host")
    end = text.find("\ndef ", start + 10)
    block = text[start:end if end != -1 else len(text)]
    for label in (
        "SSH key login",
        "APT available",
        "APT update permission",
        "APT upgrade permission",
        "Kernel upgrade permission",
        "Reboot permission",
    ):
        assert label in block
    assert "validation_steps" in block
    assert "Configuration was written, but validation failed:" in block

def test_managed_validation_does_not_fail_only_because_of_stale_update_status():
    text = Path("app/main.py").read_text()
    block = text[text.index("def managed_host_validation"):text.index("SYSTEM_CHECK_ACCOUNT")]
    assert '"update_status":' in block
    assert "update_working" not in block
    assert "if critical_ok and configuration_ok:" in block

def test_failed_reconfigure_ui_separates_title_and_message():
    template = Path("app/templates/host_integration.html").read_text()
    css = Path("app/static/app.css").read_text()
    assert 'class="notice error host-setup-result"' in template
    assert "host-validation-steps" in template
    assert ".host-setup-result" in css
    assert "gap:6px!important" in css

def test_reconfigure_wording_persists_after_failed_post():
    template = Path("app/templates/host_integration.html").read_text()
    form = Path("app/templates/host_integration_form.html").read_text()
    assert "return_to in ['device','system-checks']" in template
    assert "return_to in ['device','system-checks']" in form
    assert "Reconfigure System Checks" in form
