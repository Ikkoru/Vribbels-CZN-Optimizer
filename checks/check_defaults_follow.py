"""Settings the player never changed follow a release's new defaults; ones
they changed never do, and the program says which is which.

Three moments move a player's settings, and each must tell an unchanged
entry from a changed one with nothing but the files to go on:

1. **A release changes a default** (`defaults_sync.sync_defaults`), in
   any of four files: a Gear Score preset, a combatant's preset, a
   combatant's Optimizer settings field by field, a settings.json key.
   The sidecar records each default's value at the last sync; an entry
   still holding it takes the new one. With no value recorded -- an
   install from before they were -- an entry matching ANY value the
   default has shipped with (`defaults_history.json`) counts as
   unchanged, and so does one the program made itself and nobody
   changed. Wrong one way, a player's tuning is overwritten at an update;
   wrong the other, every unchanged setting keeps an old release's values
   for good.
2. **The game client's max rolls move** (`defaults_sync.presets_follow`
   over `preset_derivation.rework`). Every unedited preset takes the
   re-worked weights, and keeps them across a sync until a release
   changes the preset or the rolls go back -- not flipping back to the
   shipped value at each launch. Restore Defaults offers the re-worked
   ones (`effective_presets`).
3. **Undo** puts back the files a launch changed, from the backup it made
   of them first, and what it put back stays the player's at the next
   launch.

Held on scratch copies of the bundled defaults and a made-up player's
settings, with the defaults, the code defaults and the max rolls moved by
hand. Also holds the history file to the defaults it ships beside: one
that lags reads the release's own values as edits.
"""

import copy
import json
import shutil
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path, note

NAME = "settings the player never changed follow new defaults"

FILES = ("presets.json", "character_preset.json", "optimizer_settings.json",
         "settings.json")


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _scratch_defaults(scratch, shipped_dir):
    defaults = scratch / "defaults"
    shutil.copytree(shipped_dir, defaults,
                    ignore=shutil.ignore_patterns("normalize"))
    return defaults


def _keys(entries):
    """{(kind, key): fields} of a report's list."""
    return {(e["kind"], e["key"]): e["fields"] for e in entries}


def _bytes(user):
    return {name: (user / name).read_bytes() for name in FILES
            if (user / name).exists()}


def _moved_rolls(STATS):
    """STATS with the max Crit Rate roll moved, and what to put back."""
    info = STATS["S_CRI_INC_ADD"]
    STATS["S_CRI_INC_ADD"] = info[:3] + (info[3] + 0.4, info[4])
    return info


def run():
    add_source_to_path()
    import defaults_sync
    from game_data import STATS
    from settings_manager import SettingsManager
    out = []
    shipped_dir = SOURCE_ROOT / "default_settings"
    held_stats = {stat: STATS[stat] for stat in STATS}
    layout = SettingsManager.LAYOUT
    out.extend(_history_is_current(shipped_dir))
    try:
        with tempfile.TemporaryDirectory(prefix="defaults_follow_") as scratch:
            scratch = Path(scratch)
            out.extend(_presets(scratch / "presets", shipped_dir, STATS))
            out.extend(_other_files(scratch / "others", shipped_dir))
            out.extend(_switch_backup_undo(scratch / "undo", shipped_dir,
                                           STATS))
        out.extend(_launch_hook(STATS, shipped_dir))
        out.extend(_notice_says())
        out.extend(_notice_builds())
    finally:
        SettingsManager.LAYOUT = layout
        STATS.update(held_stats)
        # What the scenarios left in the module, so a later check sees
        # a launch's state rather than this one's.
        defaults_sync.report = defaults_sync.Report()
        defaults_sync._effective = None
    if any(STATS[stat] != held for stat, held in held_stats.items()):
        out.append("the check left STATS changed.")
    return out


def _history_is_current(shipped_dir):
    """The history holds every default as it ships: one that lags reads
    the release's own values as edits, and every unchanged copy as the
    player's own."""
    import defaults_sync
    from character_preset_manager import normalize_to_v2
    from optimizer_settings_manager import DEFAULT_CHARACTER_SETTINGS
    from preset_manager import weights_equal
    from settings_manager import SettingsManager
    same = defaults_sync._same
    history = _read(shipped_dir / defaults_sync.HISTORY_FILE)

    def holds(values, value, equal=same):
        return any(equal(value, past) for past in values or ())

    lacking = []
    for name, weights in _read(shipped_dir / "presets.json")[
            "presets"].items():
        if not holds(history.get("presets", {}).get(name), weights,
                     weights_equal):
            lacking.append(f"preset {name}")
    assignments = normalize_to_v2(
        _read(shipped_dir / "character_preset.json"))["assignments"]
    for rid, preset in assignments.items():
        if not holds(history.get("character_preset", {}).get(rid), preset):
            lacking.append(f"combatant {rid}'s preset")
    for rid, entry in _read(shipped_dir / "optimizer_settings.json")[
            "characters"].items():
        fields = history.get("optimizer_settings", {}).get(rid, {})
        for field, value in entry.items():
            if field not in defaults_sync._OPTIMIZER_OWN \
                    and not holds(fields.get(field), value):
                lacking.append(f"combatant {rid}'s {field}")
    if not holds(history.get("optimizer_generic"),
                 DEFAULT_CHARACTER_SETTINGS):
        lacking.append("a fresh Optimizer entry")
    for key, value in SettingsManager.LAYOUT:
        if not key.startswith("#") \
                and not holds(history.get("settings", {}).get(key), value):
            lacking.append(f"settings.json's {key}")
    if not lacking:
        return []
    more = f" and {len(lacking) - 3} more" if len(lacking) > 3 else ""
    return [f"{defaults_sync.HISTORY_FILE} lacks what ships for "
            f"{', '.join(lacking[:3])}{more}: run default_settings/normalize/"
            f"defaults_history.py (zCreate exe.bat does), or a player's "
            f"unchanged settings read as changed."]


def _presets(scratch, shipped_dir, STATS):
    """A Gear Score preset through a launch with no sidecar, a release,
    and the client's max rolls moving and going back."""
    import defaults_sync
    import preset_derivation
    from preset_manager import PresetManager, weights_equal
    out = []
    scratch.mkdir()
    shipped = _read(shipped_dir / "presets.json")["presets"]
    # Three presets the derivation covers: their combatant ships
    # Optimizer settings.
    ref, _stored = preset_derivation.shipped_reference(shipped_dir)
    old, edited, follows = sorted(
        n for n in shipped
        if preset_derivation.combatant_of(n) in ref.settings)[:3]
    defaults = _scratch_defaults(scratch, shipped_dir)
    user = scratch / "settings"
    user.mkdir()
    # The player: `old` still at a value it once shipped with, `edited`
    # tuned, `follows` as shipped. No sidecar yet.
    past = copy.deepcopy(shipped[old])
    past["ATK%"] = round(float(past.get("ATK%", 1.0)) + 0.37, 3)
    history = _read(defaults / defaults_sync.HISTORY_FILE)
    history["presets"].setdefault(old, []).append(past)
    _write(defaults / defaults_sync.HISTORY_FILE, history)
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
                   f"recorded, kept it after an update: an unedited preset "
                   f"keeps last release's weights for good "
                   f"(`_merge_presets`, defaults_history.json).")
    if not weights_equal(got[edited], mine[edited]):
        out.append(f"{edited}, which the player tuned, was overwritten by "
                   f"the sync.")

    # A release changes `follows` and `edited`.
    released = copy.deepcopy(shipped)
    released[follows] = dict(shipped[follows], CRate=7.77)
    released[edited] = dict(shipped[edited], CRate=6.66)
    _write(defaults / "presets.json", {"presets": released})
    defaults_sync.sync_defaults(user, defaults)
    got = _read(user / "presets.json")["presets"]
    if not weights_equal(got[follows], released[follows]):
        out.append(f"{follows}, never edited, kept the old weights after a "
                   f"release changed it: the sidecar's recorded value should "
                   f"mark it unedited.")
    if not weights_equal(got[edited], mine[edited]):
        out.append(f"{edited}, which the player tuned, took a release's "
                   f"weights.")
    if ("presets", edited) not in _keys(defaults_sync.report.kept):
        out.append(f"{edited}, tuned, whose default a release moved, is not "
                   f"in the notice's kept list.")

    # The client's max rolls move.
    _write(defaults / "presets.json", {"presets": shipped})
    defaults_sync.sync_defaults(user, defaults)
    manager = PresetManager(scratch)
    manager.presets_dir = user
    manager.presets_file = user / "presets.json"
    manager.load()
    info = _moved_rolls(STATS)
    try:
        target = preset_derivation.rework(defaults)
        changed = defaults_sync.presets_follow(user, defaults, manager)
        got = _read(user / "presets.json")["presets"]
        if not target or not any(
                not weights_equal(target[n], shipped[n]) for n in target):
            out.append("a moved max Crit Rate roll re-worked no preset "
                       "(`preset_derivation.rework`).")
        elif not weights_equal(got[follows], target[follows]) \
                or follows not in changed:
            out.append(f"with the max rolls moved, {follows}, never edited, "
                       f"did not take the re-worked weights.")
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
                       f"shipped weights while the rolls still moved it: it "
                       f"flips at every launch.")
        # Following off while a release moves the preset and the rolls
        # go back: the copy stays, and so does the record of its re-work.
        _write(user / "settings.json", {defaults_sync.FOLLOW_KEY: False})
        released = dict(shipped,
                        **{follows: dict(shipped[follows], CRate=5.55)})
        _write(defaults / "presets.json", {"presets": released})
        defaults_sync.sync_defaults(user, defaults)
    finally:
        STATS["S_CRI_INC_ADD"] = info
    manager.load()
    defaults_sync.presets_follow(user, defaults, manager)
    got = _read(user / "presets.json")["presets"]
    if target and not weights_equal(got[follows], target[follows]):
        out.append(f"with following off, a release or the rolls going back "
                   f"moved {follows}, a re-worked preset.")
    # Back on: the copy, still as re-worked, takes the release's.
    _write(user / "settings.json", {defaults_sync.FOLLOW_KEY: True})
    defaults_sync.sync_defaults(user, defaults)
    manager.load()
    defaults_sync.presets_follow(user, defaults, manager)
    got = _read(user / "presets.json")["presets"]
    if not weights_equal(got[follows], released[follows]):
        out.append(f"turned back on, following left {follows} on the weights "
                   f"re-worked before it was off, though a release moved it "
                   f"meanwhile: the record of the re-work did not survive.")
    # The release goes back too: the copy returns to the shipped.
    _write(defaults / "presets.json", {"presets": shipped})
    defaults_sync.sync_defaults(user, defaults)
    manager.load()
    defaults_sync.presets_follow(user, defaults, manager)
    got = _read(user / "presets.json")["presets"]
    if not weights_equal(got[follows], shipped[follows]):
        out.append(f"with the max rolls back as shipped, {follows} kept its "
                   f"re-worked weights.")
    if defaults_sync.effective_presets(shipped) != shipped:
        out.append("with the max rolls back as shipped, Restore Defaults "
                   "still offers re-worked weights.")
    return out


def _other_files(scratch, shipped_dir):
    """The other three files through a launch with no sidecar, then a
    release that moves their defaults, then the launch after."""
    import defaults_sync
    from character_preset_manager import normalize_to_v2
    from optimizer_settings_manager import DEFAULT_CHARACTER_SETTINGS
    from settings_manager import SettingsManager
    same = defaults_sync._same
    out = []
    scratch.mkdir()
    defaults = _scratch_defaults(scratch, shipped_dir)
    user = scratch / "settings"
    user.mkdir()
    history = _read(defaults / defaults_sync.HISTORY_FILE)
    presets = _read(defaults / "presets.json")["presets"]
    shipped_cp = normalize_to_v2(_read(defaults / "character_preset.json"))
    assigned = shipped_cp["assignments"]
    shipped_opt = _read(defaults / "optimizer_settings.json")
    chars = shipped_opt["characters"]
    fresh = copy.deepcopy(DEFAULT_CHARACTER_SETTINGS)
    own = defaults_sync._OPTIMIZER_OWN

    # Combatant presets: one at a value it once shipped with, one the
    # player chose, one on the program's own "Default Preset", one whose
    # preset the player deleted.
    named = sorted(rid for rid, p in assigned.items() if p in presets)
    cp_old, cp_chosen, cp_made, cp_deleted = named[:4]
    gone = assigned[cp_deleted]
    spare = [p for p in sorted(presets)
             if p not in (assigned[cp_old], assigned[cp_chosen], gone)]
    other, chosen = spare[:2]
    history["character_preset"].setdefault(cp_old, []).append(other)
    history["character_preset"][cp_made] = [
        p for p in history["character_preset"].get(cp_made, [])
        if p is not None]
    mine_cp = copy.deepcopy(shipped_cp)
    mine_cp["assignments"].update({cp_old: other, cp_chosen: chosen,
                                   cp_made: None, cp_deleted: None})

    # Optimizer settings: a field at a value it once shipped with, a
    # field the player tuned, an entry the program made, sets in another
    # order under another name, and a field the entry lacks.
    pool = sorted(r for r, e in chars.items()
                  if r.isdigit() and isinstance(e, dict)
                  and not defaults_sync._as_made(e, [fresh]))

    def take(test=lambda r: True):
        rid = next(r for r in pool if test(r))
        pool.remove(rid)
        return rid

    def number(rid, field):
        return isinstance(chars[rid].get(field), (int, float)) \
            and not isinstance(chars[rid].get(field), bool)

    op_order = take(lambda r: len(chars[r].get("sets_selected") or ()) >= 2)
    op_missing = take(lambda r: any(
        f not in own and not same(v, fresh.get(f))
        for f, v in chars[r].items()))
    missing = next(f for f, v in chars[op_missing].items()
                   if f not in own and not same(v, fresh.get(f)))
    op_old = take(lambda r: number(r, "extra_pct"))
    op_tuned = take(lambda r: number(r, "extra_pct")
                    and number(r, "dot_pct"))
    op_made = take()
    past_extra = chars[op_old]["extra_pct"] + 11
    history["optimizer_settings"][op_old].setdefault(
        "extra_pct", []).append(past_extra)
    tuned_past = history["optimizer_settings"][op_tuned].get("dot_pct", [])
    tuned = next(v for v in range(37, 1000)
                 if v not in tuned_past and v != chars[op_tuned]["dot_pct"])
    mine_opt = copy.deepcopy(shipped_opt)
    mc = mine_opt["characters"]
    mc[op_old]["extra_pct"] = past_extra
    mc[op_tuned]["dot_pct"] = tuned
    mc[op_made] = dict(copy.deepcopy(fresh), name_hint="Made by the program")
    mc[op_order]["sets_selected"] = list(
        reversed(chars[op_order]["sets_selected"]))
    mc[op_order]["name_hint"] = "Renamed by the game"
    del mc[op_missing][missing]

    # settings.json: one key as it shipped, one the player tuned, one of
    # the program's own state, and the switch.
    layout = SettingsManager.LAYOUT
    code = dict(layout)
    as_shipped, tuned_key = ("optimizer_min_gear_level",
                             "upgrade_log_slot6_atk_heal_above")
    state_key = "update_last_checked"
    for key in (as_shipped, tuned_key, state_key, defaults_sync.FOLLOW_KEY):
        if key not in code:
            return [f"settings.json has no {key} to move: the check wants "
                    f"another key of its kind."]
    if state_key not in SettingsManager.state_keys():
        return [f"{state_key} is no longer the program's own state: the "
                f"check wants another key of that section."]
    mine_settings = {k: v for k, v in layout}
    mine_settings[tuned_key] = code[tuned_key] + 9

    _write(user / "presets.json",
           {"presets": {n: w for n, w in presets.items() if n != gone}})
    _write(user / "character_preset.json", mine_cp)
    _write(user / "optimizer_settings.json", mine_opt)
    _write(user / "settings.json", mine_settings)
    _write(defaults / defaults_sync.HISTORY_FILE, history)

    defaults_sync.sync_defaults(user, defaults)
    updated = _keys(defaults_sync.report.updated)
    got_cp = _read(user / "character_preset.json")["assignments"]
    got = _read(user / "optimizer_settings.json")["characters"]
    if got_cp[cp_old] != assigned[cp_old]:
        out.append(f"combatant {cp_old}'s preset, at a value it once shipped "
                   f"with and no sync recorded, kept it after an update "
                   f"(`_merge_character_preset`).")
    if got_cp[cp_chosen] != chosen:
        out.append(f"combatant {cp_chosen}'s preset, which the player chose, "
                   f"was overwritten by the sync.")
    if got_cp[cp_made] != assigned[cp_made]:
        out.append(f"combatant {cp_made}'s \"Default Preset\", the program's "
                   f"own from before its default shipped, did not take the "
                   f"shipped preset: a combatant the program met first never "
                   f"gets one.")
    if got_cp[cp_deleted] is not None:
        out.append(f"combatant {cp_deleted}'s preset followed to {gone!r}, "
                   f"a preset the player deleted.")
    if not same(got[op_old]["extra_pct"], chars[op_old]["extra_pct"]) \
            or updated.get(("optimizer_settings", op_old)) != ["extra_pct"]:
        out.append(f"combatant {op_old}'s Extra share, at a value it once "
                   f"shipped with and no sync recorded, did not follow alone "
                   f"(`_merge_optimizer_settings`).")
    if not same(got[op_tuned]["dot_pct"], tuned):
        out.append(f"combatant {op_tuned}'s Agony share, which the player "
                   f"tuned, was overwritten by the sync.")
    made = dict(chars[op_made], name_hint="Made by the program")
    if not same(got[op_made], made):
        out.append(f"combatant {op_made}'s Optimizer settings, made by the "
                   f"program before its default shipped and never changed, "
                   f"did not take the shipped ones whole, keeping the name "
                   f"(`_as_made`).")
    if got[op_order]["sets_selected"] != mc[op_order]["sets_selected"] \
            or got[op_order]["name_hint"] != "Renamed by the game" \
            or ("optimizer_settings", op_order) in updated:
        out.append(f"combatant {op_order}'s sets in another order, or its "
                   f"name, read as a change to follow.")
    if not same(got[op_missing].get(missing, fresh), chars[op_missing][missing]) \
            or updated.get(("optimizer_settings", op_missing)) != [missing]:
        out.append(f"combatant {op_missing}'s {missing}, which its entry "
                   f"lacked, did not take the shipped value as an update.")
    if _read(user / "settings.json")[tuned_key] != mine_settings[tuned_key]:
        out.append(f"settings.json's {tuned_key}, which the player changed, "
                   f"was overwritten by the sync.")

    # A release moves them.
    released_cp = copy.deepcopy(shipped_cp)
    moved_to = next(p for p in spare[2:] if p != other)
    released_cp["assignments"][cp_old] = moved_to
    released_cp["assignments"][cp_chosen] = moved_to
    _write(defaults / "character_preset.json", released_cp)
    released_opt = copy.deepcopy(shipped_opt)
    released_opt["characters"][op_tuned]["extra_pct"] += 3
    released_opt["characters"][op_tuned]["dot_pct"] = tuned + 5
    # The player's sets, the shipped ones in another order, are still
    # the default: they follow when it moves.
    from game_data import SETS
    sets = released_opt["characters"][op_order]["sets_selected"]
    sets.append(next(s for s in sorted(SETS) if s not in sets))
    _write(defaults / "optimizer_settings.json", released_opt)
    moved = dict(code)
    moved[as_shipped] = code[as_shipped] + 3
    moved[tuned_key] = code[tuned_key] + 4
    moved[state_key] = "moved by a release"
    moved[defaults_sync.FOLLOW_KEY] = False
    try:
        SettingsManager.LAYOUT = tuple(
            (k, moved.get(k, v)) for k, v in layout)
        defaults_sync.sync_defaults(user, defaults)
        updated = _keys(defaults_sync.report.updated)
        kept = _keys(defaults_sync.report.kept)
        got_cp = _read(user / "character_preset.json")["assignments"]
        got = _read(user / "optimizer_settings.json")["characters"]
        got_settings = _read(user / "settings.json")
        if got_cp[cp_old] != moved_to:
            out.append(f"combatant {cp_old}'s preset, never chosen, kept the "
                       f"old one after a release moved it.")
        if got_cp[cp_chosen] != chosen \
                or ("character_preset", cp_chosen) not in kept:
            out.append(f"combatant {cp_chosen}'s preset, which the player "
                       f"chose, took a release's, or the notice does not "
                       f"list it as kept.")
        if not same(got[op_tuned]["extra_pct"],
                    released_opt["characters"][op_tuned]["extra_pct"]) \
                or not same(got[op_tuned]["dot_pct"], tuned) \
                or updated.get(("optimizer_settings", op_tuned)) \
                != ["extra_pct"] \
                or kept.get(("optimizer_settings", op_tuned)) != ["dot_pct"]:
            out.append(f"combatant {op_tuned}, with its Agony share tuned and "
                       f"a release moving that and its Extra share, did not "
                       f"take the Extra share alone and list the Agony "
                       f"share as kept.")
        if not same(got[op_order]["sets_selected"], sets) \
                or updated.get(("optimizer_settings", op_order)) \
                != ["sets_selected"] \
                or got[op_order]["name_hint"] != "Renamed by the game":
            out.append(f"combatant {op_order}'s sets, the shipped ones in "
                       f"another order, did not follow a release that moved "
                       f"them, keeping its name: an order read as a choice "
                       f"(`_same`).")
        if got_settings[as_shipped] != moved[as_shipped]:
            out.append(f"settings.json's {as_shipped}, never changed, kept "
                       f"the old default after a release moved it "
                       f"(`_merge_settings`).")
        if got_settings[tuned_key] != mine_settings[tuned_key] \
                or ("settings", tuned_key) not in kept:
            out.append(f"settings.json's {tuned_key}, which the player "
                       f"changed, took a release's default, or the notice "
                       f"does not list it as kept.")
        if got_settings[state_key] != mine_settings[state_key]:
            out.append(f"settings.json's {state_key}, the program's own "
                       f"memory, took a release's default.")
        if got_settings[defaults_sync.FOLLOW_KEY] is not True:
            out.append("the switch that turns following off followed a "
                       "release's default itself.")
        # The launch after: nothing new to say.
        defaults_sync.sync_defaults(user, defaults)
        if defaults_sync.report:
            out.append(f"the launch after a release reported again: "
                       f"{_keys(defaults_sync.report.updated)} updated, "
                       f"{_keys(defaults_sync.report.kept)} kept.")
    finally:
        SettingsManager.LAYOUT = layout
    return out


def _switch_backup_undo(scratch, shipped_dir, STATS):
    """With following off, a launch changes and reports nothing; turned
    back on, it brings what is still unchanged to the defaults that moved
    meanwhile, backing each file up once before changing it and keeping
    the newest few backups, and Undo puts the files back for good."""
    import defaults_sync
    import preset_derivation
    from character_preset_manager import normalize_to_v2
    from preset_manager import PresetManager, weights_equal
    from settings_manager import SettingsManager
    out = []
    scratch.mkdir()
    defaults = _scratch_defaults(scratch, shipped_dir)
    user = scratch / "settings"
    user.mkdir()
    layout = SettingsManager.LAYOUT
    code = dict(layout)
    _write(user / "settings.json", code)
    # A fresh install: stage 2 copies the rest, and records the values.
    defaults_sync.sync_defaults(user, defaults)

    shipped = _read(defaults / "presets.json")["presets"]
    ref, _stored = preset_derivation.shipped_reference(defaults)
    first, second = sorted(
        n for n in shipped
        if preset_derivation.combatant_of(n) in ref.settings)[:2]
    shipped_cp = normalize_to_v2(_read(defaults / "character_preset.json"))
    rid = sorted(r for r, p in shipped_cp["assignments"].items()
                 if p in shipped)[0]
    elsewhere = next(p for p in sorted(shipped)
                     if p != shipped_cp["assignments"][rid])
    key = "optimizer_min_gear_level"

    def release(crates, level):
        _write(defaults / "presets.json", {"presets": dict(shipped, **{
            name: dict(shipped[name], CRate=crate)
            for name, crate in crates.items()})})
        SettingsManager.LAYOUT = tuple(
            (k, level if k == key else v) for k, v in layout)

    # Following off: a release, and the max rolls moving, change and
    # report nothing.
    settings = _read(user / "settings.json")
    settings[defaults_sync.FOLLOW_KEY] = False
    _write(user / "settings.json", settings)
    cp = copy.deepcopy(shipped_cp)
    cp["assignments"][rid] = elsewhere
    _write(defaults / "character_preset.json", cp)
    before = _bytes(user)
    try:
        release({first: 7.77}, code[key] + 2)
        defaults_sync.sync_defaults(user, defaults)
        report = defaults_sync.report
        if _bytes(user) != before:
            out.append("with following off, a release changed the player's "
                       "files.")
        if report or report.backup is not None:
            out.append("with following off, a launch reported what moved or "
                       "made a backup.")
        info = _moved_rolls(STATS)
        try:
            defaults_sync.presets_follow(user, defaults)
        finally:
            STATS["S_CRI_INC_ADD"] = info
        if _bytes(user) != before or defaults_sync.report:
            out.append("with following off, moved max rolls re-worked the "
                       "player's presets, or said so.")
    finally:
        SettingsManager.LAYOUT = layout

    # Following back on, a further release, and the rolls moved. Older
    # backups than a launch keeps, and a folder of the player's own.
    settings[defaults_sync.FOLLOW_KEY] = True
    _write(user / "settings.json", settings)
    backups = user / defaults_sync.BACKUP_FOLDER
    for day in range(1, defaults_sync.BACKUPS_KEPT + 2):
        (backups / f"2000-01-{day:02} 000000 v0").mkdir(parents=True)
    (backups / "0 mine").mkdir()
    before = _bytes(user)
    info = _moved_rolls(STATS)
    try:
        release({first: 7.77, second: 6.66}, code[key] + 3)
        defaults_sync.sync_defaults(user, defaults)
        updated = _keys(defaults_sync.report.updated)
        if not {("presets", first), ("character_preset", rid),
                ("settings", key)} <= set(updated):
            out.append("turned back on, following left defaults that moved "
                       "while it was off on the old values: the records "
                       "moved on without it.")
        report = defaults_sync.report
        folder = report.backup
        manager = PresetManager(scratch)
        manager.presets_dir = user
        manager.presets_file = user / "presets.json"
        manager.load()
        reworked = defaults_sync.presets_follow(user, defaults, manager)
        after = _bytes(user)
        if folder is None or not folder.is_dir():
            out.append("a launch that changed the player's files made no "
                       "backup of them.")
            return out
        if report.backup != folder:
            out.append("the presets' re-work for the moved rolls made a "
                       "second backup in the same launch.")
        if set(report.files) != {"presets.json", "character_preset.json",
                                 "settings.json"}:
            out.append(f"the launch's backup holds {sorted(report.files)}, "
                       f"not the three files it changed.")
        for name in report.files:
            if not (folder / name).is_file() \
                    or (folder / name).read_bytes() != before[name]:
                out.append(f"the backup's {name} is not the file as it was "
                           f"before the launch changed it.")
        if not reworked:
            out.append("with the rolls moved, the launch re-worked no preset, "
                       "so Undo of a re-work went untested.")
        kept = sorted(p.name for p in backups.iterdir()
                      if defaults_sync._BACKUP_NAME.match(p.name))
        if len(kept) != defaults_sync.BACKUPS_KEPT or folder.name not in kept:
            out.append(f"after a launch, {len(kept)} backups stand, not the "
                       f"newest {defaults_sync.BACKUPS_KEPT}.")
        if not (backups / "0 mine").is_dir():
            out.append("pruning the backups took a folder of the player's "
                       "own.")

        # Undo, then the next launch: the files stay as they were.
        restored = defaults_sync.undo(user)
        if set(restored) != set(report.files) or _bytes(user) != before:
            out.append("Undo did not put back every file the launch "
                       "changed, as it was.")
        if defaults_sync.report.updated:
            out.append("after Undo, the report still lists updates for the "
                       "notice.")
        try:
            SettingsManager.LAYOUT = tuple(
                (k, code[key] + 3 if k == key else v) for k, v in layout)
            defaults_sync.sync_defaults(user, defaults)
            manager.load()
            defaults_sync.presets_follow(user, defaults, manager)
        finally:
            SettingsManager.LAYOUT = layout
        if _bytes(user) != before:
            moved = [n for n in before if _bytes(user).get(n) != before[n]]
            out.append(f"the launch after Undo changed {moved} again: what "
                       f"Undo put back is the player's.")
        if defaults_sync.report.updated:
            out.append("the launch after Undo reported updates.")
        if after == before:
            out.append("the launch changed nothing, so Undo went untested.")
        # A release moving an undone preset again: left, and said so.
        try:
            release({first: 7.77, second: 5.55}, code[key] + 3)
            defaults_sync.sync_defaults(user, defaults)
        finally:
            SettingsManager.LAYOUT = layout
        if _bytes(user).get("presets.json") != before["presets.json"] \
                or ("presets", second) not in _keys(defaults_sync.report.kept):
            out.append(f"a release moving {second} again after Undo put it "
                       f"back changed it, or the notice does not list it as "
                       f"left as it is.")
    finally:
        STATS["S_CRI_INC_ADD"] = info
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
        info = _moved_rolls(STATS)
        try:
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


def _sample_report(backup=True):
    import defaults_sync
    report = defaults_sync.Report()
    report.updated = [
        {"kind": "presets", "key": "A", "fields": None, "label": "Alpha"},
        {"kind": "optimizer_settings", "key": "1",
         "fields": ["dot_pct", "extra_pct"], "label": "Beta"},
    ]
    report.kept = [{"kind": "character_preset", "key": "2", "fields": None,
                    "label": "Gamma"}]
    if backup:
        report.backup = Path("settings") / "backups" / "2026-01-01 000000 v9"
        report.files = ["presets.json"]
    return report


def _notice_says():
    """The notice names each entry under its group, an Optimizer entry's
    fields in the tab's words, the backup, and the switch."""
    import defaults_sync
    from ui import defaults_notice
    from ui.tabs import setup_tab
    out = []
    if defaults_notice.notice_text(defaults_sync.Report()) != "":
        out.append("a launch that changed nothing would show a notice.")
    text = defaults_notice.notice_text(_sample_report())
    words = defaults_notice.GROUP_WORDS
    for wanted in (f"{words['presets']}: Alpha",
                   f"{words['optimizer_settings']}: Beta (Agony share, "
                   f"Extra share)",
                   f"{words['character_preset']}: Gamma",
                   "2026-01-01 000000 v9",
                   defaults_notice.SWITCH_WORDS):
        if wanted not in text:
            out.append(f"the notice lacks {wanted!r}.")
    if text.find("Gamma") < text.find("Beta"):
        out.append("the notice lists what it kept before what it updated.")
    if defaults_notice.SWITCH_WORDS != " ".join(setup_tab.FOLLOW_TEXT.split()):
        out.append("the notice names the Setup & Settings switch otherwise "
                   "than its label reads (`setup_tab.FOLLOW_TEXT`).")
    if "backups" in defaults_notice.notice_text(_sample_report(backup=False)):
        out.append("a launch with no backup would name one.")
    return out


def _notice_builds():
    """The notice's dialog builds, Undo is there where a backup is, and
    Undo closes it and undoes. Built at alpha 0 under a withdrawn root,
    so nothing shows."""
    import tkinter as tk
    from tkinter import ttk
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        note(f"Tk will not start here ({exc}): the notice's dialog was not "
             f"built.")
        return []
    import czn_optimizer_gui as gui
    from ui import defaults_notice
    from ui import spacing_audit as sa
    out = []
    build = tk.Toplevel.__init__
    try:
        root.withdraw()
        root.attributes("-alpha", 0.0)
        sa.hide_new_windows()
        undone, opened = [], []
        for backup in (True, False):
            dlg = defaults_notice.show(
                root, dict(gui.COLORS), _sample_report(backup),
                on_undo=lambda: undone.append(1),
                on_open=lambda: opened.append(1))
            buttons = {}

            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, (ttk.Button, tk.Button)):
                        buttons[child.cget("text")] = child
                    walk(child)
            walk(dlg)
            wanted = {"OK", "Open Backup Folder", "Undo"} if backup \
                else {"OK"}
            if set(buttons) != wanted:
                out.append(f"the notice {'with' if backup else 'without'} a "
                           f"backup has the buttons {sorted(buttons)}, not "
                           f"{sorted(wanted)}.")
            if backup and "Undo" in buttons:
                buttons["Undo"].invoke()
                if not undone or dlg.winfo_exists():
                    out.append("the notice's Undo did not undo and close it.")
            elif dlg.winfo_exists():
                dlg.destroy()
    finally:
        tk.Toplevel.__init__ = build
        root.destroy()
    return out


def _history_lags(section):
    """Point the check at a copy of the shipped defaults whose history
    lacks one value that ships, in `section`."""
    global SOURCE_ROOT
    import defaults_sync
    root = Path(tempfile.mkdtemp(prefix="lagging_"))
    shutil.copytree(SOURCE_ROOT / "default_settings",
                    root / "default_settings",
                    ignore=shutil.ignore_patterns("normalize"))
    path = root / "default_settings" / defaults_sync.HISTORY_FILE
    history = _read(path)
    if section == "presets":
        shipped = _read(root / "default_settings" / "presets.json")
        history["presets"][sorted(shipped["presets"])[-1]] = []
    else:
        history["settings"]["optimizer_workers"] = [12345]
    _write(path, history)
    SOURCE_ROOT = root


def _history_lags_presets():
    _history_lags("presets")


def _history_lags_settings():
    _history_lags("settings")


# What this check must catch, for `checks/faults.py`.
SYNC, NOTICE = "defaults_sync", "ui.defaults_notice"
FAULTS = [
    ("the history ignored", f"{SYNC}:_decide",
     'return "update" if any(equal(mine, p) for p in past) else "own"',
     'return "own"', "at a value it once shipped with"),
    ("a changed entry overwritten", f"{SYNC}:_decide",
     'return "own" if equal(last, shipped) else "kept"', 'return "update"',
     "which the player tuned"),
    ("a changed entry never reported", f"{SYNC}:_decide",
     'return "own" if equal(last, shipped) else "kept"', 'return "own"',
     "is not in the notice's kept list"),
    ("an undone entry's moved default unreported", f"{SYNC}:_decide",
     'return "kept" if moved else "own"', 'return "own"',
     "again after Undo put it back"),
    ("a program-made entry needs no history",
     f"{SYNC}:_merge_optimizer_settings",
     "if not last_entry and not undone_entry",
     "if not last_entry and not past_entry and not undone_entry",
     "did not take the shipped ones whole"),
    ("a program-made entry never as made", f"{SYNC}:_as_made",
     'scalars = [g["set_effect_pct"] for g in generic',
     "return False\n    scalars = [g for g in generic",
     "did not take the shipped ones whole"),
    ("the program's Default Preset kept", f"{SYNC}:_merge_character_preset",
     "if mine is None and preset is not None and rid not in last",
     "if False and mine is None and rid not in last",
     "the program's own from before its default shipped"),
    ("a deleted preset assigned", f"{SYNC}:_merge_character_preset",
     "if preset is not None and ctx.preset_names is not None",
     "if False and ctx.preset_names is not None",
     "a preset the player deleted"),
    ("a missing field never filled", f"{SYNC}:_merge_optimizer_settings",
     "value):\n                    moved.append(field)",
     "value):\n                    pass",
     "which its entry lacked"),
    ("a list's order read as a choice", f"{SYNC}:_same",
     "return sorted(a) == sorted(b)", "return a == b",
     "an order read as a choice"),
    ("the combatant's name followed", f"{SYNC}:_OPTIMIZER_OWN",
     'frozenset({"name_hint"})', "frozenset()", "keeping the name"),
    ("the program's own state followed", f"{SYNC}:_merge_settings",
     "and key not in SettingsManager.state_keys()", "",
     "the program's own memory"),
    ("the switch followed", f"{SYNC}:_merge_settings",
     "and key != FOLLOW_KEY}", "}", "followed a release's default itself"),
    ("the switch ignored", f"{SYNC}:follows",
     "return data.get(FOLLOW_KEY, True) is not False", "return True",
     "with following off, a release changed the player's files"),
    ("the records move on while off", f"{SYNC}:sync_defaults",
     "if ctx.follow:\n        new_synced.update(ctx.values)",
     "if True:\n        new_synced.update(ctx.values)",
     "the records moved on without it"),
    ("reported while off", f"{SYNC}:_apply",
     "if not ctx.follow:\n        return False",
     "if not ctx.follow:\n        report.kept.append(entry)\n"
     "        return False",
     "with following off, a launch reported"),
    ("the sync drops a re-work while off", f"{SYNC}:_merge_presets",
     "if ctx.follow:\n        ctx.reworked = still_reworked",
     "if True:\n        ctx.reworked = still_reworked",
     "the record of the re-work did not survive"),
    ("the re-work drops its record while off", f"{SYNC}:presets_follow",
     "if follow and new_reworked != reworked:",
     "if new_reworked != reworked:",
     "the record of the re-work did not survive"),
    ("no backup", f"{SYNC}:_write_user",
     "if not _backup(user_dir, fname):", "if False:",
     "made no backup"),
    ("the backup made after the write", f"{SYNC}:_write_user",
     "if not _backup(user_dir, fname):\n        return False\n"
     "    return _safe_write_json(Path(user_dir) / fname, data)",
     "ok = _safe_write_json(Path(user_dir) / fname, data)\n"
     "    _backup(user_dir, fname)\n    return ok",
     "is not the file as it was before the launch changed it"),
    ("a backup per file", f"{SYNC}:_backup",
     "if report.backup is None:", "if True:",
     "is not the file as it was before the launch changed it"),
    ("old backups kept", f"{SYNC}:_prune", "if old != keep:", "if False:",
     "backups stand, not the newest"),
    ("the player's folders pruned", f"{SYNC}:_BACKUP_NAME",
     r're.compile(r"\d{4}-\d{2}-\d{2} \d{6} ")', 're.compile("")',
     "took a folder of the player's own"),
    ("Undo forgets what it put back", f"{SYNC}:undo",
     ["state[_UNDONE] = undone", "undone = _dict_of(state.get(_UNDONE))"],
     ["pass", "undone = {}"],
     "what Undo put back is the player's"),
    ("Undo puts nothing back", f"{SYNC}:undo",
     "shutil.copy2(report.backup / fname, user_dir / fname)", "pass",
     "Undo did not put back every file"),
    ("Undo leaves the report", f"{SYNC}:undo", "report = done", "pass",
     "after Undo, the report still lists updates"),
    ("the re-work ignores Undo", f"{SYNC}:presets_follow",
     "or (name in undone and weights_equal(mine, undone[name]))", "or False",
     "what Undo put back is the player's"),
    ("no Undo in the notice", f"{NOTICE}:show", "if report.updated:",
     "if False:", "has the buttons"),
    ("the notice misnames the switch", f"{NOTICE}:SWITCH_WORDS",
     '"Update unchanged settings to new defaults automatically"',
     '"Follow new defaults"', "otherwise than its label reads"),
    ("the notice names fields raw", f"{NOTICE}:FIELD_WORDS",
     '"dot_pct": "Agony share",', '"dot_pct": "dot_pct",',
     "Beta (Agony share, Extra share)"),
    ("the history lags a preset", _history_lags_presets, None, None,
     "lacks what ships for preset"),
    ("the history lags a setting", _history_lags_settings, None, None,
     "lacks what ships for settings.json's"),
]
