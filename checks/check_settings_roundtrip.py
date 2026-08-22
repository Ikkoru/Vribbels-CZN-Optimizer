"""Settings survive a save/load round-trip, on a COPY.

Three things are checked. First that every manager writes atomically --
temp file plus replace -- because a settings file half-written during a
crash is unrecoverable user state. Second that
`OptimizerSettingsManager.load()` preserves top-level keys it does not
know about: a load that re-reads only the keys it recognises silently
drops the exclude bootstrap's state and the level-seen map, and the
symptom appears runs later as combatants quietly un-excluding
themselves.

Third that every key in `DEFAULT_CHARACTER_SETTINGS` survives both
`_fresh_character_settings` and `get_character_data`. Those two spell
their keys out one per line rather than iterating the defaults, so a
per-character setting added to the defaults and missed in either one is
accepted, written, and then read back as its default forever -- a
slider that will not stay where it is put, with nothing logged.

Never touches `Vribbels/settings/`. Everything happens in a temp copy.
"""

import ast
import io
import json
import shutil
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, SOURCE_ROOT, Skip

NAME = "settings round-trip"

MANAGERS = [
    "settings_manager.py",
    "preset_manager.py",
    "optimizer_settings_manager.py",
    "character_preset_manager.py",
    "level_data_manager.py",
    "log_presets_manager.py",
]


def _writes_atomically(path: Path) -> bool:
    """True when the module's `_write` goes through a temp file."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_write":
            body = ast.dump(node)
            return "replace" in body and "tmp" in body.lower()
    return False


def run():
    failures = []
    add_source_to_path()

    for fname in MANAGERS:
        path = SOURCE_ROOT / fname
        if not path.exists():
            failures.append(f"{fname} is missing")
            continue
        if not _writes_atomically(path):
            failures.append(
                f"{fname}: _write does not look atomic (no temp file + "
                f"replace). A crash mid-write loses the user's state."
            )

    live = SOURCE_ROOT / "settings" / "optimizer_settings.json"
    if not live.exists():
        raise Skip("no settings/optimizer_settings.json to round-trip")

    tmp_root = Path(tempfile.mkdtemp())
    try:
        work = tmp_root / "settings"
        work.mkdir(parents=True)
        shutil.copy2(live, work / "optimizer_settings.json")

        import optimizer_settings_manager as osm
        before = json.loads(live.read_text(encoding="utf-8"))

        m = osm.OptimizerSettingsManager(tmp_root)
        m.load()
        m._write()
        after = json.loads((work / "optimizer_settings.json")
                           .read_text(encoding="utf-8"))

        for key in before:
            if key not in after:
                failures.append(
                    f"optimizer_settings.json: top-level key {key!r} was "
                    f"dropped by load() + _write(). User state is lost."
                )

        defaults = osm.DEFAULT_CHARACTER_SETTINGS
        fresh = osm._fresh_character_settings("probe")
        for key in defaults:
            if key not in fresh:
                failures.append(
                    f"_fresh_character_settings omits {key!r}. A new "
                    f"character's entry would never carry it."
                )

        # A round-trip through the store, so the reader is exercised on a
        # written entry rather than on the defaults dict.
        probe_id = 999999
        m.ensure_character(probe_id, name="probe")
        for key, value in defaults.items():
            if isinstance(value, int) and not isinstance(value, bool):
                m.set(probe_id, key, value + 1)
        m._write()

        reread = osm.OptimizerSettingsManager(tmp_root)
        reread.load()
        stored = reread.get_character_data(probe_id)
        for key, value in defaults.items():
            if key not in stored:
                failures.append(
                    f"get_character_data omits {key!r}. It is saved to "
                    f"disk and then read back as its default."
                )
            elif isinstance(value, int) and not isinstance(value, bool) \
                    and stored[key] != value + 1:
                failures.append(
                    f"{key!r} did not survive the round-trip: wrote "
                    f"{value + 1}, read back {stored[key]!r}."
                )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return failures
