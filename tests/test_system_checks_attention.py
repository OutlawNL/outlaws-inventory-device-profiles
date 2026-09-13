import ast
from pathlib import Path

def _status_function():
    source = Path("app/main.py").read_text()
    tree = ast.parse(source)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_system_check_status")
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, "app/main.py", "exec"), namespace)
    return namespace["_system_check_status"]

def _base():
    return {
        "health_checks": {},
        "ping_check": {"status": "online"},
        "disk_check": {"status": "online"},
        "http_check": None,
        "updates": {"package_count": 0, "status": "ok", "reboot_required": 0},
    }

def test_disk_warning_is_attention_even_without_updates():
    status = _status_function()
    item = _base()
    item["disk_check"] = {"status": "warning"}
    assert status(item) == "attention"

def test_updates_are_attention():
    status = _status_function()
    item = _base()
    item["updates"] = {"package_count": 3, "status": "available", "reboot_required": 0}
    assert status(item) == "attention"

def test_no_updates_and_healthy_disk_is_ok():
    status = _status_function()
    assert status(_base()) == "ok"

def test_ping_disabled_other_healthy_checks_are_ok():
    status = _status_function()
    item = _base()
    item["ping_check"] = None
    assert status(item) == "ok"


def test_no_active_checks_remains_unknown():
    status = _status_function()
    item = {
        "health_checks": {},
        "ping_check": None,
        "disk_check": None,
        "http_check": None,
        "updates": None,
        "applications": [],
    }
    assert status(item) == "unknown"
