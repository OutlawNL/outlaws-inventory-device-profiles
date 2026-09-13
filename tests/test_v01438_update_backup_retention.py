import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE = (ROOT / "update.sh").read_text(encoding="utf-8")


def _extract_prune_function() -> str:
    match = re.search(
        r"prune_update_backups\(\) \{\n(?P<body>.*?)\n\}\n\narchive_existing_rollback\(\)",
        UPDATE,
        re.S,
    )
    assert match, "prune_update_backups function not found"
    return "prune_update_backups() {\n" + match.group("body") + "\n}\n"


def _run_prune(tmp_path: Path, names: list[str]) -> set[str]:
    backup_root = tmp_path / "outlaws-inventory"
    backup_root.mkdir()
    for name in names:
        (backup_root / name).mkdir()
        (backup_root / name / "marker").write_text(name, encoding="utf-8")

    script = _extract_prune_function() + '\nBACKUP_ROOT="$1"\nprune_update_backups\n'
    subprocess.run(["bash", "-c", script, "bash", str(backup_root)], check=True)
    return {path.name for path in backup_root.iterdir()}


def test_release_version_is_01438():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "0.18.8"' in main


def test_cleanup_runs_only_after_success_validation_and_rollback_publish():
    assert UPDATE.index('trap - EXIT') < UPDATE.index('publish_manual_rollback "$PREVIOUS_VERSION"')
    assert UPDATE.index('publish_manual_rollback "$PREVIOUS_VERSION"') < UPDATE.index('prune_update_backups', UPDATE.index('publish_manual_rollback "$PREVIOUS_VERSION"'))


def test_retention_keeps_zero_one_or_two_timestamp_backups(tmp_path):
    for index, names in enumerate([
        [],
        ["20260830-210000"],
        ["20260830-210000", "20260830-220000"],
    ]):
        case = tmp_path / str(index)
        case.mkdir()
        assert _run_prune(case, names) == set(names)


def test_retention_keeps_only_two_newest_timestamp_backups(tmp_path):
    remaining = _run_prune(tmp_path, [
        "20260829-163423",
        "20260830-202948",
        "20260830-212510",
        "20260830-213739",
    ])
    assert remaining == {"20260830-212510", "20260830-213739"}


def test_retention_never_touches_non_timestamp_directories(tmp_path):
    remaining = _run_prune(tmp_path, [
        "rollback",
        "rollback-history",
        "20260830-213739",
        "20260830-212510",
        "20260830-210549",
        "20260830-210549-extra",
        "not-a-backup",
    ])
    assert remaining == {
        "rollback",
        "rollback-history",
        "20260830-213739",
        "20260830-212510",
        "20260830-210549-extra",
        "not-a-backup",
    }


def test_retention_does_not_follow_timestamp_named_symlink(tmp_path):
    backup_root = tmp_path / "outlaws-inventory"
    backup_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("safe", encoding="utf-8")
    (backup_root / "20260830-213739").mkdir()
    (backup_root / "20260830-212510").mkdir()
    (backup_root / "20260830-210549").symlink_to(outside, target_is_directory=True)

    script = _extract_prune_function() + '\nBACKUP_ROOT="$1"\nprune_update_backups\n'
    subprocess.run(["bash", "-c", script, "bash", str(backup_root)], check=True)

    assert (backup_root / "20260830-210549").is_symlink()
    assert (outside / "keep").read_text(encoding="utf-8") == "safe"
