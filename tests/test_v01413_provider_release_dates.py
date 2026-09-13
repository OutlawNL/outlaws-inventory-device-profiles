import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _assignment(name):
    tree = ast.parse((ROOT / "app/main.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


def test_arturia_official_release_dates_are_preserved():
    catalog = _assignment("FIRMWARE_CATALOG")
    minifuse = next(item for item in catalog if item["vendor"] == "Arturia" and "MiniFuse 2" in item["models"])
    minilab = next(item for item in catalog if item["vendor"] == "Arturia" and "MiniLab MkII" in item["models"])
    assert minifuse["latest"] == "1.5.0.212"
    assert minifuse["release_date"] == "2024-10-08"
    assert minilab["latest"] == "1.1.2.1689"
    assert minilab["release_date"] == "2021-12-30"


def test_glinet_mt3000_official_release_date_is_preserved():
    catalog = _assignment("FIRMWARE_CATALOG")
    mt3000 = next(item for item in catalog if item["vendor"] == "GL.iNet" and "GL-MT3000" in item["models"])
    assert mt3000["latest"] == "4.8.1"
    assert mt3000["release_date"] == "2025-08-19"


def test_creality_ender_3_v3_ke_official_release_date_is_preserved():
    catalog = _assignment("CREALITY_STATIC_CATALOG")
    ender = next(item for item in catalog if "Ender-3 V3 KE" in item["models"])
    assert ender["latest"] == "1.1.0.17"
    assert ender["release_date"] == "2025-08-27"
