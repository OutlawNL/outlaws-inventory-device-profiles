from pathlib import Path
import re

def test_backup_inspection_cache_file_is_defined_before_use():
    source = (Path(__file__).parents[1] / "app" / "main.py").read_text()
    assignment = re.search(
        r'^BACKUP_INSPECTION_CACHE_FILE\s*=\s*DATA_DIR\s*/\s*"backup-inspection-cache\.json"\s*$',
        source,
        re.MULTILINE,
    )
    assert assignment is not None
    first_use = source.find("BACKUP_INSPECTION_CACHE_FILE")
    assert first_use == assignment.start()
