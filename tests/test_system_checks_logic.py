import ast
from pathlib import Path


def _load_disk_status_function():
    source = Path('app/main.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_disk_status_from_percent')
    module = ast.Module(body=[fn], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(module), 'app/main.py', 'exec'), namespace)
    return namespace['_disk_status_from_percent']


def test_disk_threshold_boundaries():
    check = _load_disk_status_function()
    assert check(84, 85, 95) == 'online'
    assert check(85, 85, 95) == 'warning'
    assert check(94, 85, 95) == 'warning'
    assert check(95, 85, 95) == 'critical'
    assert check(100, 85, 95) == 'critical'
