import ast
from pathlib import Path

def _catalog():
    tree = ast.parse(Path("app/main.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CREALITY_STATIC_CATALOG":
                    return ast.literal_eval(node.value)
    raise AssertionError("CREALITY_STATIC_CATALOG not found")

def test_k1_max_monochrome_s11_fallback():
    catalog = _catalog()
    item = next(x for x in catalog if x.get("variant") == "Monochrome" and x.get("mainboard") == "CR4CU220812S11")
    assert item["latest"] == "1.3.5.22"
    assert item["release_date"] == "2026-07-10"
