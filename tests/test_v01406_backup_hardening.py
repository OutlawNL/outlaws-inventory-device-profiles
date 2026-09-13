from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_new_backup_filename_contains_application_version():
    text = (ROOT / "app/main.py").read_text()
    assert 'outlaws-inventory-{kind}-backup-v{APP_VERSION}-{stamp}.oi-backup' in text

def test_backup_listing_separates_integrity_from_restore_support():
    text = (ROOT / "app/main.py").read_text()
    assert "def inspect_full_backup" in text
    assert '"status": "Invalid"' in text
    assert 'status="Unsupported"' in text
    assert 'status="Restorable"' in text
    assert '"restorable": bool(inspection["restorable"])' in text

def test_download_is_not_conditioned_on_restore_support():
    template = (ROOT / "app/templates/settings.html").read_text()
    row = template[template.index('{% for b in backups %}'):template.index('{% endfor %}', template.index('{% for b in backups %}'))]
    assert '<a class="button secondary" href="/settings/backups/{{ b.name|urlencode }}/download">Download</a>' in row
    assert '{% if b.restorable %}' in row
    assert row.index('>Download</a>') < row.index('{% if b.restorable %}')

def test_backup_status_labels_are_restorable_unsupported_invalid():
    template = (ROOT / "app/templates/settings.html").read_text()
    css = (ROOT / "app/static/app.css").read_text()
    assert "{{ b.status }}" in template
    assert ".backup-status-restorable" in css
    assert ".backup-status-unsupported" in css
    assert ".backup-status-invalid" in css

def test_retention_prunes_only_verified_automatic_backups():
    text = (ROOT / "app/main.py").read_text()
    start = text.index("def prune_backups")
    end = text.index("\ndef _validated_clock_time", start)
    block = text[start:end]
    assert 'manifest.get("kind") == "automatic"' in block
    assert "automatic.append(path)" in block
    assert "for path in automatic[max(1, retention):]" in block

def test_retention_label_explicitly_says_automatic():
    template = (ROOT / "app/templates/settings.html").read_text()
    assert "Keep Automatic Backups" in template
    assert ">Keep latest<" not in template

def test_newer_backup_is_not_restorable_by_older_application():
    text = (ROOT / "app/main.py").read_text()
    assert 'version_tuple(backup_version) > version_tuple(APP_VERSION)' in text
    assert "Update this installation before restoring it." in text

def test_update_preparation_removes_stale_result_file_before_recreating_it():
    text = (ROOT / "app/main.py").read_text()
    assert 'for stale_name in ("pending.json", "result.json", "SHA256SUMS"):' in text
