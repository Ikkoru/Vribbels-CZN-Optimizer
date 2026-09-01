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

Fourth that every key the app reads or writes appears in
`SettingsManager.LAYOUT`. A key missing from it still works: it is
created on first write and appended after everything else. What it
loses is the file -- it is absent until something sets it, and then
lands past the `#N` section markers rather than under the one it
belongs to, so a user reading `settings.json` to find a switch does not
see it.

Never touches `Vribbels/settings/`. Everything happens in a temp copy.
"""

import ast
import io
import json
import re
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
    "log_presets_manager.py",
]

# The two ways a settings key is spelled in this source: a literal
# handed to the manager, and a module constant holding one. The
# receiver names are listed rather than matching any `.get(` -- a dict
# lookup is spelled the same way, and `flags.get("attribute")` is not a
# settings key.
KEY_CALL = re.compile(
    r"\b(?:sm|settings_manager|_settings)\s*\.\s*(?:get|set)"
    r"\(\s*['\"]([a-z_][a-z0-9_]*)['\"]")
KEY_CONST = re.compile(
    r"^[A-Z][A-Z0-9_]*_KEY\s*=\s*['\"]([a-z_][a-z0-9_]*)['\"]", re.M)


def _layout_covers_every_key():
    """Complaints for settings keys the app uses and LAYOUT omits.

    The four Upgrade Log filters are added from their own tuple: they
    are read by iterating it, so no source line spells one.
    """
    import settings_manager
    from upgrade_log_filters import UPGRADE_LOG_FILTERS

    used = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in (KEY_CALL, KEY_CONST):
            for found in pattern.finditer(text):
                used.setdefault(found.group(1), path.name)
    for key in UPGRADE_LOG_FILTERS:
        used.setdefault(key, "upgrade_log_filters.py")

    listed = {key for key, _default in settings_manager.SettingsManager.LAYOUT}
    return [
        f"settings key {key!r} ({where}) is not in "
        f"SettingsManager.LAYOUT. settings.json will not carry it until "
        f"something writes it, and it then lands past the last section "
        f"marker instead of under the section it belongs to."
        for key, where in sorted(used.items()) if key not in listed
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

    failures.extend(_layout_covers_every_key())

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
