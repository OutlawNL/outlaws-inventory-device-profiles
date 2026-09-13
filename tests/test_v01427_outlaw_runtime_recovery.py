from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
FORM = (ROOT / "app/templates/host_integration_form.html").read_text(encoding="utf-8")


def test_release_version():
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "0.18.8"' in MAIN


def test_runtime_identity_is_outlaw_not_sa_account():
    assert 'SYSTEM_CHECK_ACCOUNT = "outlaw"' in MAIN
    assert "sa-outlaws-inventory" not in MAIN
    assert "Service Account: outlaw" in FORM


def test_configure_can_create_missing_outlaw_and_installs_key():
    assert "/usr/sbin/useradd --create-home --shell /bin/bash" in MAIN
    assert "authorized_keys" in MAIN
    assert "outlaws-key-only" in MAIN


def test_pihole_permissions_follow_runtime_identity():
    assert 'f"{managed_user} ALL=(root) NOPASSWD: /usr/local/bin/pihole -up --check-only"' in MAIN
    assert 'f"{managed_user} ALL=(root) NOPASSWD: /usr/local/bin/pihole -up"' in MAIN
    assert 'sudo -n /usr/local/bin/pihole -up --check-only </dev/null' in MAIN
    assert 'client.exec_command("sudo -n /usr/local/bin/pihole -up"' in MAIN


def test_failed_reconfigure_preserves_existing_runtime_profile():
    marker = "A failed reconfigure must never replace a previously working runtime profile."
    assert marker in MAIN
    block = MAIN[MAIN.index(marker)-300:MAIN.index(marker)+500]
    assert "managed_ssh_profile_id" not in block[block.index(marker):]


def test_sa_account_is_only_historical_documentation():
    active_files = [ROOT / "app", ROOT / "docs", ROOT / "README.md"]
    hits = []
    for item in active_files:
        paths = item.rglob("*") if item.is_dir() else [item]
        for path in paths:
            if path.is_file() and path.suffix in {".py", ".html", ".md"}:
                if "sa-outlaws-inventory" in path.read_text(encoding="utf-8"):
                    hits.append(str(path.relative_to(ROOT)))
    assert hits == []
