"""Settings survive a save/load round-trip, on a COPY.

Two things are checked. First that every manager writes atomically --
temp file plus replace -- because a settings file half-written during a
crash is unrecoverable user state. Second that
`OptimizerSettingsManager.load()` preserves top-level keys it does not
know about: a load that re-reads only the keys it recognises silently
drops the exclude bootstrap's state and the level-seen map, and the
symptom appears runs later as combatants quietly un-excluding
themselves.

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
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return failures
