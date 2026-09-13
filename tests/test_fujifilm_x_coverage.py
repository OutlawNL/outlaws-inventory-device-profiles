from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FUJIFILM = ROOT / "profiles" / "fujifilm"


def profiles():
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in FUJIFILM.glob("*.yaml")]


def test_fujifilm_x_catalog_scope_is_complete_and_device_specific():
    entries = profiles()
    assert len(entries) == 78
    assert Counter(entry["device"]["category"] for entry in entries) == {
        "Camera": 51,
        "Lens": 27,
    }
    assert all(entry["device"]["vendor"] == "Fujifilm" for entry in entries)
    assert all(entry["firmware"]["strategy"] == "html_release" for entry in entries)
    assert all("/firmware/cameras/" in entry["firmware"]["source"]["url"]
               or "/firmware/lenses/" in entry["firmware"]["source"]["url"]
               for entry in entries)


def test_fujifilm_device_names_and_aliases_do_not_collide():
    def normalized(value):
        return "".join(character for character in value.lower() if character.isalnum())

    names = {}
    for entry in profiles():
        device = entry["device"]
        for name in [device["model"], *device.get("aliases", [])]:
            key = normalized(name)
            assert key not in names or names[key] == entry["id"], (name, names[key], entry["id"])
            names[key] = entry["id"]
