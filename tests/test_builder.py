from pathlib import Path
import importlib.util
import shutil
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('catalog_builder',ROOT/'scripts/build_catalog.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

@pytest.fixture
def tree(tmp_path):
    shutil.copytree(ROOT/'schemas',tmp_path/'schemas')
    (tmp_path/'profiles').mkdir()
    shutil.copy2(next((ROOT/'profiles').rglob('*.yaml')),tmp_path/'profiles/one.yaml')
    builder.build(tmp_path,7)
    return tmp_path


def snapshot(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in (root/'catalog').rglob('*') if p.is_file()} | {'manifest.json':(root/'manifest.json').read_bytes()}


def test_invalid_profile_leaves_published_artifacts_unchanged(tree):
    before=snapshot(tree);(tree/'profiles/bad.yaml').write_text('id: incomplete\n')
    with pytest.raises(ValueError):builder.build(tree,8)
    assert snapshot(tree)==before


def test_duplicate_identity_leaves_published_artifacts_unchanged(tree):
    before=snapshot(tree);shutil.copy2(tree/'profiles/one.yaml',tree/'profiles/duplicate.yaml')
    with pytest.raises(ValueError,match='Duplicate'):builder.build(tree,8)
    assert snapshot(tree)==before


def test_failed_manifest_replace_restores_previous_catalog(tree,monkeypatch):
    before=snapshot(tree);replace=Path.replace
    def fail(path,target):
        if path.name=='manifest.json' and path.parent.name.startswith('.catalog-build-'):
            raise OSError('simulated failure')
        return replace(path,target)
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(OSError):builder.build(tree,8)
    assert snapshot(tree)==before


def test_successful_build_replaces_complete_catalog(tree):
    assert builder.build(tree,8)==(8,1)
    import json
    assert json.loads((tree/'catalog/index.json').read_text())['catalog_version']==8
    assert json.loads((tree/'manifest.json').read_text())['catalog_version']==8
