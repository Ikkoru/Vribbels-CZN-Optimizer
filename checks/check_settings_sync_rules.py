"""Three settings rules that fail without a word.

`docs/settings_architecture.md` states each; nothing else exercises
them, and a regression in any one looks like a settings file that is
merely a little different from what the player expected:

1. **The tombstone gate.** A default the player deleted, which was in
   the defaults at the last sync and still is, is not put back. With no
   sidecar yet (an install from before tombstones), every current
   default counts as known, so a deletion made then sticks too. A
   default NEW since the last sync is added. Broken, a deleted Gear
   Score preset comes back at every launch.
2. **`SettingsManager.apply_layout` absorbs a legacy `config.json`**:
   its value for a key `settings.json` lacks is taken, and never one
   over a key `settings.json` has. Broken one way, a player upgrading
   from an old release loses their region and worker count; the other,
   a stale file overrides what they set since.
3. **Restore Defaults' per-entry buckets override the gate and leave
   the sidecar alone.** A tombstoned preset is offered under Restore
   Missing, restoring it puts it back, and the next launch keeps it.
   Combatant assignments compare `None` as no opinion: a shipped `None`
   offers nothing, a player's `None` against a shipped preset is
   Missing, two presets that differ are Changed.

Held on scratch folders; the live `Vribbels/settings/` is never touched.
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from ._harness import add_source_to_path

NAME = "settings sync's unguarded rules"

WEIGHTS_A = {"ATK%": 1.0, "CRate": 1.5}
WEIGHTS_B = {"DEF%": 1.0, "HP%": 0.5}
WEIGHTS_C = {"CDmg": 1.25}
SIDECAR = ".defaults_sync.json"


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _presets(user):
    return set(json.loads(
        (user / "presets.json").read_text(encoding="utf-8"))["presets"])


def _the_tombstone_gate():
    """Complaints about the tombstone gate, and the scratch folders it
    leaves for the Restore half."""
    import defaults_sync
    out = []
    root = Path(tempfile.mkdtemp(prefix="sync_rules_"))
    user, shipped = root / "settings", root / "default_settings"
    _write(shipped / "presets.json", {"presets": {"A": WEIGHTS_A,
                                                  "B": WEIGHTS_B}})
    # A player who deleted B before tombstones existed: no sidecar.
    _write(user / "presets.json", {"presets": {"A": WEIGHTS_A}})
    defaults_sync.sync_defaults(user, shipped)
    if "B" in _presets(user):
        out.append(
            "with no sidecar, a shipped preset the player had deleted was "
            "put back. Every current default has to count as known on a "
            "first sync, or a deletion made before tombstones existed "
            "comes back at the upgrade.")
    if not (user / SIDECAR).exists():
        return out + ["the first sync wrote no sidecar, so no later sync "
                      "can tell a deletion from a new default."], root
    defaults_sync.sync_defaults(user, shipped)
    if "B" in _presets(user):
        out.append(
            "a preset the player deleted, shipped at the last sync and "
            "still shipped, was put back. The tombstone gate is what "
            "respects a deletion; without it, it comes back every launch.")
    _write(shipped / "presets.json", {"presets": {
        "A": WEIGHTS_A, "B": WEIGHTS_B, "C": WEIGHTS_C}})
    defaults_sync.sync_defaults(user, shipped)
    got = _presets(user)
    if "C" not in got:
        out.append(
            "a preset new in the defaults since the last sync was not "
            "added. A release's new presets would reach nobody who has "
            "launched before.")
    if "B" in got:
        out.append(
            "a release adding another preset brought back the one the "
            "player deleted.")
    return out, root


def _legacy_config_is_absorbed():
    """Complaints about `apply_layout`'s legacy fold."""
    from settings_manager import SettingsManager
    out = []
    root = Path(tempfile.mkdtemp(prefix="layout_"))
    _write(root / "settings" / "settings.json", {"server_region": "asia"})
    legacy = root / "settings" / "config.json"
    _write(legacy, {"server_region": "global", "optimizer_workers": 3})
    mgr = SettingsManager(root)
    mgr.load()
    mgr.apply_layout((legacy, root / "config.json"))
    if mgr.get("optimizer_workers") != 3:
        out.append(
            f"a legacy config.json's optimizer_workers (3) was not taken "
            f"for a settings.json without the key (got "
            f"{mgr.get('optimizer_workers')!r}). A player upgrading from "
            f"before settings.json loses their worker count.")
    if mgr.get("server_region") != "asia":
        out.append(
            f"a legacy config.json's server_region overrode the one "
            f"settings.json holds (got {mgr.get('server_region')!r}, not "
            f"'asia'). The old file is left on disk, so every launch would "
            f"put the stale value back over what the player set since.")
    saved = json.loads((root / "settings" / "settings.json").read_text(
        encoding="utf-8"))
    if saved.get("optimizer_workers") != 3:
        out.append("the absorbed legacy value was not written to "
                   "settings.json, so it lives only until the next launch.")
    return out


def _restore_overrides_the_gate(root):
    """Complaints about Restore Defaults' buckets, on the folders the
    tombstone half left: B is tombstoned there."""
    from preset_manager import PresetManager
    from ui.tabs.setup_tab import SetupTab
    import defaults_sync
    out = []
    user, shipped = root / "settings", root / "default_settings"
    sidecar = (user / SIDECAR).read_bytes()
    mgr = PresetManager(root)
    mgr.load()
    tab = SimpleNamespace(_preset_weights_equal=SetupTab._preset_weights_equal)
    missing, _changed = SetupTab._diff_presets(tab, mgr,
                                              shipped / "presets.json")
    if ("B", "B") not in missing:
        return out + [
            f"Restore Defaults did not offer the tombstoned preset B under "
            f"Restore Missing (it offered {missing!r}). The dialog is the "
            f"one way to bring a deleted default back; it has to override "
            f"the gate."]
    ticked = SimpleNamespace(get=lambda: True)
    SetupTab._apply_presets(tab, mgr, json.loads(
        (shipped / "presets.json").read_text(encoding="utf-8")),
        {"B": {"restore": ticked}}, {})
    if "B" not in _presets(user):
        out.append("restoring B under Restore Missing did not write it to "
                   "presets.json.")
    if (user / SIDECAR).read_bytes() != sidecar:
        out.append(
            "Restore Defaults rewrote the sync sidecar. It mutates the "
            "player's file through the manager and nothing else; the "
            "sidecar records what was SHIPPED, which a restore does not "
            "change.")
    defaults_sync.sync_defaults(user, shipped)
    if "B" not in _presets(user):
        out.append("the launch after restoring B took it out again.")
    return out


def _assignment_buckets():
    """Complaints about the `None` rules in the combatant assignments'
    buckets."""
    from ui.tabs.setup_tab import SetupTab
    out = []
    root = Path(tempfile.mkdtemp(prefix="assign_"))
    shipped = root / "character_preset.json"
    _write(shipped, {"version": 2,
                     "assignments": {"1": None, "2": "P", "3": "P",
                                     "4": "P", "5": "P"},
                     "name_hints": {}})
    mgr = SimpleNamespace(
        assignments_by_id={"1": "Q", "2": None, "4": "Q", "5": "P"},
        name_hints={})
    missing, changed = SetupTab._diff_character_preset(None, mgr, shipped)
    missing = {rid for rid, _name in missing}
    changed = {rid for rid, _name in changed}
    if "1" in missing | changed:
        out.append(
            "a shipped assignment of None was offered. None is no opinion: "
            "every combatant the player set to a preset would show up.")
    if missing != {"2", "3"}:
        out.append(
            f"Restore Missing held {sorted(missing)}, not ['2', '3']: a "
            f"player's None, or no entry, against a shipped preset is "
            f"Missing.")
    if changed != {"4"}:
        out.append(
            f"Replace Changed held {sorted(changed)}, not ['4']: only two "
            f"presets that differ are Changed, and a player's None is not "
            f"one -- else every reset to Default Preset reads as noise.")
    return out


def run():
    add_source_to_path()
    failures, root = _the_tombstone_gate()
    failures.extend(_legacy_config_is_absorbed())
    failures.extend(_restore_overrides_the_gate(root))
    failures.extend(_assignment_buckets())
    return failures


FAULTS = [
    ("the tombstone gate dropped", "defaults_sync:_merge_presets",
     "if name not in known_set and name not in user_presets:",
     "if name not in user_presets:",
     "still shipped, was put back"),
    ("no grandfathering on a first sync", "defaults_sync:_merge_presets",
     "if not ctx.is_first_sync:", "if True:",
     "with no sidecar"),
    ("legacy config.json over settings.json",
     "settings_manager:SettingsManager.apply_layout",
     "            elif key in self.settings:\n"
     "                ordered[key] = self.settings[key]\n"
     "            elif key in legacy:\n"
     "                ordered[key] = legacy[key]\n",
     "            elif key in legacy:\n"
     "                ordered[key] = legacy[key]\n"
     "            elif key in self.settings:\n"
     "                ordered[key] = self.settings[key]\n",
     "overrode the one"),
    ("legacy config.json ignored",
     "settings_manager:SettingsManager.apply_layout",
     "            elif key in legacy:\n"
     "                ordered[key] = legacy[key]\n",
     "",
     "was not taken"),
    ("Restore Missing honouring the tombstone",
     "ui.tabs.setup_tab:SetupTab._diff_presets",
     "            if name not in user_presets:\n"
     "                missing.append((name, name))\n",
     "            if name not in user_presets:\n",
     "did not offer the tombstoned preset"),
    ("a shipped None offered",
     "ui.tabs.setup_tab:SetupTab._diff_character_preset",
     "            if default_preset is None:\n                continue\n",
     "",
     "a shipped assignment of None was offered"),
]
