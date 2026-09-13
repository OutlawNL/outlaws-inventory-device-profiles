from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_backup_inspection_cache_uses_physical_file_signature():
    text = (ROOT / "app/main.py").read_text()
    assert "BACKUP_INSPECTION_CACHE_FILE" in text
    assert "def _backup_cache_signature" in text
    assert '"size": int(stat.st_size)' in text
    assert '"mtime_ns": int(stat.st_mtime_ns)' in text
    assert '"ctime_ns": int(stat.st_ctime_ns)' in text

def test_list_backups_uses_cached_integrity_inspection():
    text = (ROOT / "app/main.py").read_text()
    assert "def _cached_backup_integrity" in text
    start = text.index("def inspect_full_backup")
    end = text.index("\ndef validate_full_backup", start)
    block = text[start:end]
    assert "_cached_backup_integrity(path) if use_cache" in block

def test_restore_always_forces_fresh_backup_validation():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("def validate_full_backup")
    end = text.index("\ndef list_backups", start)
    block = text[start:end]
    assert "inspect_full_backup(path, use_cache=False)" in block

def test_cache_is_not_part_of_backup_payload():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("BACKUP_COMPONENTS =")
    end = text.index("\ndef _backup_filename", start)
    block = text[start:end]
    assert "BACKUP_INSPECTION_CACHE_FILE" not in block

def test_cache_warms_in_background_on_startup():
    text = (ROOT / "app/main.py").read_text()
    assert "def _warm_backup_inspection_cache" in text
    assert 'threading.Thread(target=_warm_backup_inspection_cache, name="backup-inspection-cache", daemon=True).start()' in text

def test_dashboard_maintenance_card_is_blue():
    css = (ROOT / "app/static/app.css").read_text()
    assert ".dashboard-kpis .maintenance-card{border-color:rgba(79,127,184,.82);background:rgba(79,127,184,.055)}" in css
    assert ".pill.maintenance{background:#4f7fb8" in css
