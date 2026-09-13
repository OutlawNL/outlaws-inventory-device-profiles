from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.18.8"


def test_version_constants_match_release():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    for constant in ("APP_VERSION", "DATABASE_SCHEMA_VERSION", "INSTALLER_VERSION"):
        assert f'{constant} = "{VERSION}"' in main


def test_release_tree_contains_no_runtime_data_or_cache():
    assert not (ROOT / "data").exists()
    assert not [p for p in ROOT.rglob("*.pyc") if "__pycache__" not in p.parts]
    assert not [p for p in ROOT.rglob("__pycache__") if p.parent.name not in {"tests", "app", "providers"}]
    assert not [p for p in ROOT.rglob(".pytest_cache") if p.parent != ROOT]


def test_no_historical_loose_release_notes():
    assert not list(ROOT.glob("Release-Notes-v*.md"))


def test_supported_product_name_only():
    forbidden = "homelab" + "-dashboard"
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".sh", ".md", ".html", ".css", ".txt"}:
            assert forbidden not in path.read_text(encoding="utf-8", errors="ignore").lower(), path


def test_update_preserves_data_directory():
    update = (ROOT / "update.sh").read_text(encoding="utf-8")
    assert "--exclude data" in update
    assert 'APP_DIR="/opt/outlaws-inventory"' in update
