"""`zCreate exe.bat`'s reminder names exactly the default files a copy
from `settings/` would change.

`default_settings/normalize/compare_defaults.py` decides whether the
maintainer is told to delete files and relaunch, or to delete nothing.
Wrong one way, a real change to the defaults never ships and nothing
says so; wrong the other, the reminder is orange at every build over
state the build strips anyway, and stops being read.

Held on scratch copies of the shipped files, changed one way at a time.
"""

import json
import shutil
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path

NAME = "the build's reminder names the defaults that differ"

DEFAULTS = SOURCE_ROOT / "default_settings"


def _case(compare, change):
    """What `differing` says after `change(settings_dir, defaults_dir)`
    on fresh copies of the shipped files."""
    root = Path(tempfile.mkdtemp(prefix="cmp_defaults_"))
    try:
        mine, shipped = root / "settings", root / "defaults"
        for folder in (mine, shipped):
            folder.mkdir()
            for name in compare.FILES:
                shutil.copy(DEFAULTS / name, folder / name)
        change(mine, shipped)
        found = compare.differing(mine, shipped)
        return None if found is None else [name for name, _ in found]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _edit(name, edit):
    def change(mine, _shipped):
        path = mine / name
        data = json.loads(path.read_text(encoding="utf-8"))
        edit(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    return change


def _first(mapping):
    return next(iter(mapping))


def run():
    add_source_to_path()
    from default_settings.normalize import compare_defaults as compare

    out = []

    def expect(what, change, wanted):
        got = _case(compare, change)
        if got != wanted:
            out.append(f"{what}: the reminder names {got}, not {wanted}. "
                       f"`compare_defaults.differing` decides which "
                       f"default files the build tells you to delete.")

    def preset_weight(data):
        weights = data["presets"][_first(data["presets"])]
        key = _first(weights)
        weights[key] = (weights[key] or 0) + 1

    def assignment(data):
        data["assignments"]["SomeoneNew"] = "x"

    def optimizer_value(data):
        chars = data["characters"]
        chars[_first(chars)]["extra_pct"] = 37

    def user_state(data):
        data["excluded_gear_chars"] = ["1001"]
        data["optimize_level_seen"] = {"1001": 60}
        chars = data["characters"]
        chars[_first(chars)]["optimize_for_level"] = 60

    def labels(data):
        data.setdefault("name_hints", {})["99999"] = "Someone"

    expect("identical copies", lambda m, s: None, [])
    expect("a Gear Score weight changed",
           _edit("presets.json", preset_weight), ["presets.json"])
    expect("an assignment added",
           _edit("character_preset.json", assignment),
           ["character_preset.json"])
    expect("an Optimizer setting changed",
           _edit("optimizer_settings.json", optimizer_value),
           ["optimizer_settings.json"])
    expect("only per-user state the build strips",
           _edit("optimizer_settings.json", user_state), [])
    expect("only name labels",
           _edit("character_preset.json", labels), [])
    expect("a shipped file already deleted",
           lambda m, s: (s / "presets.json").unlink(), ["presets.json"])

    green, lines = compare.steps([])
    if green != compare.GREEN or lines != ["1. Delete nothing",
                                           "2. Take a deep breath"]:
        out.append(f"with nothing to delete the reminder reads {lines}, "
                   f"not green `Delete nothing` / `Take a deep breath`.")
    orange, lines = compare.steps([("presets.json", None)])
    if orange != compare.ORANGE or lines != [
            "1. Delete default json files: presets.json",
            "2. zRUN Vribbels"]:
        out.append(f"with presets.json to delete the reminder reads "
                   f"{lines}, not orange `Delete default json files: "
                   f"presets.json` / `zRUN Vribbels`.")
    return out


CMP = "default_settings.normalize.compare_defaults"

FAULTS = [
    ("the per-user state compared",
     f"{CMP}:comparable",
     "        normalize_defaults.normalize(data)\n",
     "        pass\n",
     "only per-user state the build strips"),
    ("the labels compared",
     f"{CMP}:_without_labels",
     "if k not in LABELS}",
     "if True}",
     "only name labels"),
    ("a deleted file passed over",
     f"{CMP}:differing",
     'out.append((name, "already deleted"))',
     "pass",
     "a shipped file already deleted"),
    ("every file reported",
     f"{CMP}:differing",
     "if comparable(name, a) != comparable(name, b):",
     "if True:",
     "identical copies"),
    ("the green lines lost",
     f"{CMP}:steps",
     'return GREEN, ["1. Delete nothing", "2. Take a deep breath"]',
     'return ORANGE, ["1. Delete nothing", "2. Take a deep breath"]',
     "not green"),
]
