"""A preset the player never edited follows the shipped one; an edited
one never does.

Two moments move a player's presets, and both must tell an unedited
copy from an edited one with nothing but the copy itself to go on:

1. **A release changes a shipped preset** (`defaults_sync._merge_presets`).
   The sidecar records each preset's value at the last sync; a copy
   still holding it takes the new one. With no value recorded -- an
   install from before they were -- a copy matching ANY value the
   preset has shipped with (`presets_history.json`) counts as
   unedited. Wrong one way, a player's tuning is overwritten at an
   update with nothing said; wrong the other, every unedited preset
   keeps last release's weights for good.
2. **The game client's max rolls move** (`defaults_sync.presets_follow`
   over `preset_derivation.rework`). Every unedited copy takes the
   re-worked weights, and keeps them across a sync until a release
   changes the preset or the rolls go back -- not flipping back to the
   shipped value at each launch. Restore Defaults offers the re-worked
   ones (`effective_presets`).

Held on scratch copies of the bundled defaults and a made-up player's
settings, with the max rolls moved by hand. Also holds the history file
to the presets it ships beside: one that lags reads the release's own
values as edits.
"""

import copy
import json
import shutil
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path

NAME = "a preset the player never edited follows the shipped one"


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run():
    add_source_to_path()
    import defaults_sync
    import preset_derivation
    from game_data import STATS
    from preset_manager import PresetManager, weights_equal
    out = []
    shipped_dir = SOURCE_ROOT / "default_settings"
    shipped = _read(shipped_dir / "presets.json")["presets"]
    history = defaults_sync._preset_history(shipped_dir)
    for name, weights in shipped.items():
        if not any(weights_equal(weights, past)
                   for past in history.get(name, ())):
            out.append(f"presets_history.json lacks {name}'s shipped "
                       f"weights: run default_settings/normalize/"
                       f"presets_history.py (zCreate exe.bat does), or a "
                       f"player's unedited copy reads as edited.")
            break

    # Three presets the derivation covers: their combatant ships
    # Optimizer settings.
    ref, _stored = preset_derivation.shipped_reference(shipped_dir)
    old, edited, follows = sorted(
        n for n in shipped
        if preset_derivation.combatant_of(n) in ref.settings)[:3]
    held_stats = {stat: STATS[stat] for stat in STATS}
    with tempfile.TemporaryDirectory(prefix="presets_follow_") as scratch:
        scratch = Path(scratch)
        defaults, user = scratch / "defaults", scratch / "settings"
        shutil.copytree(shipped_dir, defaults,
                        ignore=shutil.ignore_patterns("normalize"))
        user.mkdir()
        # The player: `old` still at a value it once shipped with,
        # `edited` tuned, `follows` as shipped. No sidecar yet.
        past = copy.deepcopy(shipped[old])
        past["ATK%"] = round(float(past.get("ATK%", 1.0)) + 0.37, 3)
        hist = defaults_sync._preset_history(defaults)
        hist.setdefault(old, []).append(past)
        _write(defaults / defaults_sync.PRESETS_HISTORY_FILE,
               {"presets": hist})
        mine = copy.deepcopy(shipped)
        mine[old] = past
        mine[edited] = dict(shipped[edited], CDmg=9.99)
        _write(user / "presets.json", {"presets": mine})
        for name in ("character_preset.json", "optimizer_settings.json"):
            shutil.copy2(defaults / name, user / name)

        defaults_sync.sync_defaults(user, defaults)
        got = _read(user / "presets.json")["presets"]
        if not weights_equal(got[old], shipped[old]):
            out.append(f"{old}, at a value it once shipped with and no sync "
                       f"recorded, kept it after an update: an unedited "
                       f"preset keeps last release's weights for good "
                       f"(`_merge_presets`, presets_history.json).")
        if not weights_equal(got[edited], mine[edited]):
            out.append(f"{edited}, which the player tuned, was overwritten "
                       f"by the sync.")

        # A release changes `follows` and `edited`.
        released = copy.deepcopy(shipped)
        released[follows] = dict(shipped[follows], CRate=7.77)
        released[edited] = dict(shipped[edited], CRate=6.66)
        _write(defaults / "presets.json", {"presets": released})
        defaults_sync.sync_defaults(user, defaults)
        got = _read(user / "presets.json")["presets"]
        if not weights_equal(got[follows], released[follows]):
            out.append(f"{follows}, never edited, kept the old weights after "
                       f"a release changed it: the sidecar's recorded value "
                       f"should mark it unedited.")
        if not weights_equal(got[edited], mine[edited]):
            out.append(f"{edited}, which the player tuned, took a release's "
                       f"weights.")

        # The client's max rolls move.
        _write(defaults / "presets.json", {"presets": shipped})
        defaults_sync.sync_defaults(user, defaults)
        manager = PresetManager(scratch)
        manager.presets_dir = user
        manager.presets_file = user / "presets.json"
        manager.load()
        info = STATS["S_CRI_INC_ADD"]
        try:
            STATS["S_CRI_INC_ADD"] = info[:3] + (info[3] + 0.4, info[4])
            target = preset_derivation.rework(defaults)
            changed = defaults_sync.presets_follow(user, defaults, manager)
            got = _read(user / "presets.json")["presets"]
            if not target or not any(
                    not weights_equal(target[n], shipped[n]) for n in target):
                out.append("a moved max Crit Rate roll re-worked no preset "
                           "(`preset_derivation.rework`).")
            elif not weights_equal(got[follows], target[follows]) \
                    or follows not in changed:
                out.append(f"with the max rolls moved, {follows}, never "
                           f"edited, did not take the re-worked weights.")
            if not weights_equal(got[edited], mine[edited]):
                out.append(f"with the max rolls moved, {edited}, which the "
                           f"player tuned, was re-worked.")
            offered = defaults_sync.effective_presets(shipped)
            if target and not weights_equal(offered[edited], target[edited]):
                out.append("Restore Defaults would not offer the re-worked "
                           "weights to a tuned preset (`effective_presets`).")
            # A launch: the sync first, which must leave a re-worked copy.
            defaults_sync.sync_defaults(user, defaults)
            got = _read(user / "presets.json")["presets"]
            if target and not weights_equal(got[follows], target[follows]):
                out.append(f"the next launch's sync put {follows} back to the "
                           f"shipped weights while the rolls still moved it: "
                           f"it flips at every launch.")
        finally:
            STATS["S_CRI_INC_ADD"] = info
        # The rolls go back: the re-worked copy returns to the shipped.
        manager.load()
        defaults_sync.presets_follow(user, defaults, manager)
        got = _read(user / "presets.json")["presets"]
        if not weights_equal(got[follows], shipped[follows]):
            out.append(f"with the max rolls back as shipped, {follows} kept "
                       f"its re-worked weights.")
        if defaults_sync.effective_presets(shipped) != shipped:
            out.append("with the max rolls back as shipped, Restore Defaults "
                       "still offers re-worked weights.")
    out.extend(_launch_hook(STATS, shipped_dir))
    if any(STATS[stat] != held for stat, held in held_stats.items()):
        out.append("the check left STATS changed.")
    return out


def _launch_hook(STATS, shipped_dir):
    """`OptimizerGUI._presets_follow_client`, which every client read
    ends in: with the rolls moved, it hands the re-worked presets on,
    re-scores what shows, and -- from source -- tells the maintainer,
    once."""
    from types import SimpleNamespace
    from czn_optimizer_gui import OptimizerGUI
    from preset_manager import PresetManager
    out = []
    with tempfile.TemporaryDirectory(prefix="presets_hook_") as scratch:
        scratch = Path(scratch)
        user = scratch / "settings"
        user.mkdir()
        shutil.copy2(shipped_dir / "presets.json", user / "presets.json")
        manager = PresetManager(scratch)
        manager.load()
        told, scored = [], []
        app = SimpleNamespace(
            _client_settings_dir=user, preset_manager=manager,
            scoring_tab_instance=SimpleNamespace(
                apply_active_weights=lambda: scored.append(1)),
            _warn=lambda title, text: told.append(title))
        info = STATS["S_CRI_INC_ADD"]
        try:
            STATS["S_CRI_INC_ADD"] = info[:3] + (info[3] + 0.4, info[4])
            OptimizerGUI._presets_follow_client(app)
            OptimizerGUI._presets_follow_client(app)
        finally:
            STATS["S_CRI_INC_ADD"] = info
            app._rolls_moved_told = True
            OptimizerGUI._presets_follow_client(app)
        if not scored:
            out.append("a client read that re-worked the presets left the "
                       "Gear Scores on the old weights: nothing re-scored "
                       "(`_presets_follow_client`).")
        if len(told) != 1:
            out.append(f"a source run with moved rolls told the maintainer "
                       f"{len(told)} times, not once.")
    return out
