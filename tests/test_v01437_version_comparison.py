import ast
from pathlib import Path

MAIN = Path('app/main.py').read_text(encoding='utf-8')
TREE = ast.parse(MAIN)


def _load_version_helpers():
    wanted = {'normalize_release_version', 'version_tuple'}
    nodes = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    ns = {'re': __import__('re')}
    exec(compile(module, '<version-helpers>', 'exec'), ns)
    return ns['version_tuple']


def test_release_version():
    assert 'APP_VERSION = "0.18.8"' in MAIN


def test_normal_semver_ordering_only():
    version = _load_version_helpers()
    assert version('0.14.22') < version('0.14.37')
    assert version('0.14.36') < version('0.14.37')
    assert version('0.14.37') == version('v0.14.37')
    assert version('0.15.0') > version('0.14.37')
    assert version('0.9.99') < version('0.14.37')


def test_legacy_compact_hotfix_rewrite_is_gone():
    assert 'compact hotfix' not in MAIN
    assert 'parts[2] // 10' not in MAIN
