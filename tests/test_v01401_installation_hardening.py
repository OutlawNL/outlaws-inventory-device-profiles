import ast
import builtins
from pathlib import Path

def test_clean_start_no_orphaned_ssh_migration_variable():
    text = Path("app/main.py").read_text()
    assert "migrated_ssh_paths" not in text

def test_installer_refuses_existing_installation():
    text = Path("install.sh").read_text()
    assert 'An existing Outlaw\'s Inventory installation was detected' in text
    assert 'Use sudo ./update.sh for an existing installation' in text

def test_installer_requires_runtime_version_health_before_success():
    text = Path("install.sh").read_text()
    assert "/system/ready" in text
    assert "EXPECTED_VERSION" in text
    assert 'payload.get("ready") is True and running == expected' in text
    assert 'systemctl is-active "$SERVICE_NAME"' in text
    health = text.index('echo "Validating application startup..."')
    success = text.index('echo "Installation complete."')
    assert health < success

def test_installer_reports_diagnostics_and_stops_failed_restart_loop():
    text = Path("install.sh").read_text()
    assert 'Installation failed: Outlaw\'s Inventory did not become healthy.' in text
    assert 'systemctl status "$SERVICE_NAME" --no-pager -l' in text
    assert 'journalctl -u "$SERVICE_NAME" -n 50 --no-pager' in text
    assert 'systemctl stop "$SERVICE_NAME"' in text

def test_service_account_and_ping_are_validated():
    text = Path("install.sh").read_text()
    assert 'SERVICE_USER="outlaws-inventory"' in text
    assert 'useradd --system --gid "$SERVICE_USER"' in text
    assert '--shell /usr/sbin/nologin' in text
    assert 'runuser -u "$SERVICE_USER" -- /usr/bin/ping' in text

def test_bytecode_is_disabled_for_installed_and_updated_service():
    install = Path("install.sh").read_text()
    update = Path("update.sh").read_text()
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in install
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in update

def test_restore_normalizes_sensitive_runtime_permissions():
    text = Path("app/main.py").read_text()
    assert "def normalize_runtime_data_permissions()" in text
    restore = text[text.index("def restore_full_backup"):text.index("def prune_backups")]
    assert "normalize_runtime_data_permissions()" in restore
    assert "KEY_DIR: 0o700" in text
    assert "SECRETS_DIR: 0o700" in text
    assert "DB_PATH.chmod(0o600)" in text

def test_rollback_verifies_exact_running_target_version():
    text = Path("scripts/outlaws-inventory-self-rollback").read_text()
    assert "runtime_version_check()" in text
    assert "/system/ready" in text
    assert 'runtime_version_check "$TARGET_VERSION"' in text
    assert "__pycache__" in text
    assert "*.pyc" in text


def test_init_db_has_no_unresolved_name_loads():
    source = Path("app/main.py").read_text()
    tree = ast.parse(source)
    module_defs = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_defs.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module_defs.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                module_defs.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        module_defs.add(name.id)

    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "init_db")
    local_defs = {arg.arg for arg in func.args.args}
    for node in ast.walk(func):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.For):
            targets = [node.target]
        elif isinstance(node, ast.comprehension):
            targets = [node.target]
        elif isinstance(node, ast.With):
            targets = [item.optional_vars for item in node.items if item.optional_vars]
        elif isinstance(node, ast.ExceptHandler) and node.name:
            local_defs.add(node.name)
        for target in targets:
            for name in ast.walk(target):
                if isinstance(name, ast.Name):
                    local_defs.add(name.id)

    loads = {node.id for node in ast.walk(func) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    unresolved = loads - local_defs - module_defs - set(dir(builtins))
    assert not unresolved, f"init_db contains unresolved names: {sorted(unresolved)}"
