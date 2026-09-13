from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'app/main.py').read_text()
DETAIL=(ROOT/'app/templates/system_check_detail.html').read_text()
OVERVIEW=(ROOT/'app/templates/system_checks.html').read_text()

def test_release_version():
    assert 'APP_VERSION = "0.18.8"' in MAIN
    assert 'DATABASE_SCHEMA_VERSION = "0.18.8"' in MAIN

def test_minecraft_is_application_check_with_auto_detection():
    assert "application_type not in ('pihole', 'minecraft')" in MAIN
    assert '_minecraft_version_from_jar' in MAIN
    assert "version.json" in MAIN
    assert "piston-meta.mojang.com/mc/game/version_manifest_v2.json" in MAIN
    assert 'name="check_minecraft"' in DETAIL
    assert 'automatic detection' in DETAIL
    assert '</b>Minecraft' in OVERVIEW

def test_legacy_profile_cleanup_is_removed_from_runtime():
    assert "sa-outlaws-inventory" not in MAIN
    assert "System Checks (legacy " not in MAIN
