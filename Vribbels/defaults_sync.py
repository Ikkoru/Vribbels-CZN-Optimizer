"""
defaults_sync - Reconciles bundled defaults (`default_settings/`, tracked
in git / bundled into the exe) with the user's state (`settings/`,
gitignored) on every startup, BEFORE any manager loads.

Three stages, in order:

1.  Maintainer bootstrap: `default_settings/` file missing but the
    user's `settings/` file exists -> copy settings -> defaults. Fires
    on a maintainer machine before `default_settings/` is committed;
    inert everywhere else. Skipped entirely in frozen builds (the
    defaults dir lives in read-only _MEIPASS).

2.  New-user bootstrap: user's `settings/` file missing but defaults
    exist -> copy defaults -> settings.

3.  Update merge, per entry:
    - **Adds** default entries the user doesn't have. The sidecar
      `settings/.defaults_sync.json` records the keys present in
      defaults at the last sync; only keys NEW since then are
      candidates for adding. This is what makes user deletions stick --
      without the tombstone, a deleted default would reappear every
      launch.
    - **Follows** a changed default where the user never changed the
      entry: the sidecar also records each default's value at the last
      sync, and an entry still holding it takes the new one. Where no
      sync recorded a value -- an install from before they were, or a
      deleted sidecar -- an entry matching ANY value the default has
      shipped with counts as unedited: `HISTORY_FILE`, written from git
      before every build. An entry the user changed is theirs and is
      never overwritten; it is reported as kept where its default moved.
      `settings.json` follows its code defaults (`SettingsManager.LAYOUT`)
      the same way, but for the keys that are the program's own state.
      Off where the user turned `FOLLOW_KEY` off: nothing follows or is
      reported, and the recorded values stand, so that turning it back
      on brings what is still unchanged to the defaults that moved.

    Per-file merge keys:
      - presets.json:            preset name, the whole preset
      - character_preset.json:   res_id (v2 schema; mixed-version files
                                 are normalized to v2 first and written
                                 back in v2 form). Never to a preset the
                                 user deleted
      - optimizer_settings.json: res_id, each FIELD on its own (but
                                 `name_hint`), so a user who changed one
                                 slider still gets the rest. Chars added
                                 by the merge are also appended to
                                 excluded_gear_chars (new chars default
                                 to excluded)
      - settings.json:           key

    An entry the program made itself for a combatant whose default no
    sync recorded -- the "Default Preset" assignment, a fresh Optimizer
    entry -- still as made, follows whole: a combatant the program met
    before a release shipped its default.

    First-sync grandfathering: when the sidecar doesn't exist yet
    (upgrade from an older release), ALL current defaults are treated as
    already-known, protecting deletions made before tombstone tracking
    existed. Fresh installs are unaffected (Stage 2 copied everything,
    so there's nothing to add anyway).

**Every file a launch changes is backed up first**, once a launch, into
`settings/backups/<when> <version>/`, the newest `BACKUPS_KEPT` kept;
`report` says what changed and where the backup is, for the notice the
program shows (`OptimizerGUI._report_defaults_updates`), and `undo` puts
the backup back and marks what it held as the user's own, so the next
launch does not update it again.

After the startup sync, once the game client's facts are laid over,
`presets_follow` re-works the shipped presets where the client's max
rolls moved them, and hands the result to every unedited copy, into the
same report and backup.

Files with no bundled default (never touched here): config.json.

Known limitations (accepted trade-offs, do not "fix" without a design
discussion):
  - Renamed default entry: appears as a new key -> user gets both the
    old and new versions. Manual cleanup.
  - An entry edited back to a value it once shipped with reads as
    unedited, and follows. The notice lists it, and Undo puts it back.
  - A user file that does not read: its merge leaves it alone
    (`_user_json`). Startup mends or sets aside any that would not parse
    before this runs (`settings_repair`), so one still unreadable here
    is one that would not open.
"""

import json
import re
import shutil
import sys
import time
from pathlib import Path

from json_file import write_json


_DEFAULTABLE_FILES = (
    "presets.json",
    "character_preset.json",
    "optimizer_settings.json",
)

# Tombstone sidecar, inside settings/. Read/write is best-effort;
# a failure degrades to "no tombstone this run" (a previously-deleted
# default may come back once, then be tombstoned on the next run).
_SYNC_STATE_FILENAME = ".defaults_sync.json"
# The sidecar's record of each default's value at the last sync, per
# file: what tells an entry the user never changed from one they did.
_VALUES = {"presets": "preset_values",
           "character_preset": "assignment_values",
           "optimizer_settings": "optimizer_values",
           "settings": "settings_values"}
# The weights `presets_follow` re-worked a copy to, and the values `undo`
# put back, per file: each counts as the user's own while it stands.
_PRESET_REWORKED = "preset_reworked"
_UNDONE = "undone"
# Every value each default has shipped with, from git history, per
# file: for an entry no sync recorded a value for, which it then matches
# if it was never changed. `optimizer_generic` is every fresh entry the
# program has made (`DEFAULT_CHARACTER_SETTINGS`), for an entry it made
# itself. Written by `default_settings/normalize/defaults_history.py`
# before every build.
HISTORY_FILE = "defaults_history.json"
# The settings.json switch that turns following off. Absent is on.
FOLLOW_KEY = "follow_defaults"
# Where a launch's backup goes, inside settings/, and how many are kept.
BACKUP_FOLDER = "backups"
BACKUPS_KEPT = 5
# A launch backup's name, as `_backup` makes it: the only folders pruned.
_BACKUP_NAME = re.compile(r"\d{4}-\d{2}-\d{2} \d{6} ")

_MISSING = object()


class Report:
    """What this launch did to the user's settings files.

    `updated` and `kept` hold one dict per entry: `kind` (the file:
    presets, character_preset, optimizer_settings, settings, or
    reworked for `presets_follow`'s), `key`, `fields` (an optimizer
    entry's, else None) and `label`, the entry's name to show. Kept is
    an entry the user changed whose default moved since the last sync.
    `backup` is the folder the changed files went to, None where nothing
    changed; `files` the names in it."""

    def __init__(self):
        self.updated = []
        self.kept = []
        self.backup = None
        self.files = []
        self.failed = []

    def __bool__(self):
        return bool(self.updated or self.kept)


# This launch's. Replaced at the start of each `sync_defaults`.
report = Report()


def resolve_defaults_dir(base_dir: Path) -> Path:
    """Directory holding the bundled defaults.

    Frozen build: inside `_MEIPASS` (read-only). Dev: `<base>/default_settings`.
    Shared by startup sync and the Setup & Settings tab's Restore Defaults dialog.
    """
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", base_dir))
        return bundle_root / "default_settings"
    return Path(base_dir) / "default_settings"


def sync_defaults(user_dir: Path, defaults_dir: Path) -> list:
    """Run the three-stage reconciliation. Call before managers load.

    Args:
        user_dir: the writable settings/ folder.
        defaults_dir: the bundled default_settings/ folder (may be
            read-only in frozen builds).

    Returns:
        A list of `(stage, filename, message)` for every copy that
        failed. Empty is the normal case. The caller decides what to do
        with them -- see `OptimizerGUI._report_sync_failures`. What the
        merge changed is `report`.

        A failure here is not recoverable in place, but it MUST NOT be
        silent: stage 2 failing means a new user starts with no presets,
        no combatant assignments and no optimizer settings, in an app
        that otherwise looks perfectly healthy.
    """
    global report
    report = Report()
    user_dir = Path(user_dir)
    defaults_dir = Path(defaults_dir)
    failures: list = []

    user_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1. The mkdir doubles as the frozen-build guard: _MEIPASS is
    # read-only, so a failure here means "no writable defaults dir" and
    # stages that write to it are skipped by returning early -- but the
    # merge (which only READS defaults) must still run, so only return
    # if the dir doesn't exist at all.
    try:
        defaults_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        if not defaults_dir.exists():
            failures.append(("locate defaults", defaults_dir.name, str(e)))
            return failures
    for fname in _DEFAULTABLE_FILES:
        d_path = defaults_dir / fname
        u_path = user_dir / fname
        if not d_path.exists() and u_path.exists():
            try:
                shutil.copy2(u_path, d_path)
            except Exception as e:
                failures.append(("maintainer bootstrap", fname, str(e)))

    # Stage 2.
    for fname in _DEFAULTABLE_FILES:
        u_path = user_dir / fname
        d_path = defaults_dir / fname
        if not u_path.exists() and d_path.exists():
            try:
                shutil.copy2(d_path, u_path)
            except Exception as e:
                failures.append(("new-user bootstrap", fname, str(e)))

    # Stage 3.
    state_file = user_dir / _SYNC_STATE_FILENAME
    is_first_sync = not state_file.exists()
    synced = _load_sync_state(state_file)
    ctx = _Context(user_dir, defaults_dir, synced, is_first_sync)

    new_synced: dict = dict(synced)
    new_synced["presets"] = _merge_presets(ctx, synced.get("presets", []))
    new_synced["character_preset"] = _merge_character_preset(
        ctx, synced.get("character_preset", []))
    new_synced["optimizer_settings"] = _merge_optimizer_settings(
        ctx, synced.get("optimizer_settings", []))
    _merge_settings(ctx)
    # With following off, the records stay as they were, so turning it
    # back on brings every entry still unchanged to the defaults that
    # moved meanwhile.
    if ctx.follow:
        new_synced.update(ctx.values)
    new_synced[_PRESET_REWORKED] = ctx.reworked
    new_synced[_UNDONE] = ctx.undone
    _save_sync_state(state_file, new_synced)
    failures.extend(report.failed)
    return failures


# -------------------- io helpers --------------------

def _safe_load_json(path: Path, fallback: dict) -> dict:
    """Read JSON dict from `path`; `fallback` on any failure."""
    try:
        if not path.exists():
            return fallback
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return fallback
        return data
    except Exception:
        return fallback


def _user_json(path: Path, fallback: dict):
    """The user's copy of a defaultable file: `fallback` where there is
    none, None where there is one that does not read as an object.

    None means the merge leaves the file alone. Merging into the
    fallback instead would save a file of the new defaults over
    everything it held -- and for character_preset.json at every launch,
    since a fallback with no `version` reads as the v1 schema, which is
    always written back.
    """
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _safe_write_json(path: Path, data: dict) -> bool:
    """`json_file.write_json`, creating the folder. True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, data, ensure_ascii=False)
        return True
    except Exception:
        return False


def _load_sync_state(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_sync_state(path: Path, data: dict) -> None:
    _safe_write_json(path, data)


def _dict_of(value) -> dict:
    return value if isinstance(value, dict) else {}


def _version() -> str:
    """This build's version, as a backup folder names it."""
    try:
        from version import __version__
        return str(__version__).split()[0]
    except Exception:
        return "unknown"


def _backup(user_dir: Path, fname: str) -> bool:
    """Copy `fname` from `user_dir` into this launch's backup folder,
    the first time this launch changes it. False where the copy failed:
    the caller then leaves the file alone rather than change it
    unsaved."""
    path = Path(user_dir) / fname
    if fname in report.files or not path.exists():
        return True
    try:
        if report.backup is None:
            root = Path(user_dir) / BACKUP_FOLDER
            stem = f"{time.strftime('%Y-%m-%d %H%M%S')} {_version()}"
            folder, n = root / stem, 1
            # Never into another launch's: it would lose what that one
            # kept.
            while folder.exists():
                n += 1
                folder = root / f"{stem} ({n})"
            folder.mkdir(parents=True)
            report.backup = folder
            _prune(root, folder)
        shutil.copy2(path, report.backup / fname)
    except Exception as e:
        report.failed.append(("backup", fname, str(e)))
        return False
    report.files.append(fname)
    return True


def _prune(root: Path, keep: Path) -> None:
    """Leave the newest `BACKUPS_KEPT` launch backups. Their names start
    with the time, so they sort oldest first; a folder named otherwise
    is the user's, and stays."""
    try:
        folders = sorted(p for p in root.iterdir()
                         if p.is_dir() and _BACKUP_NAME.match(p.name))
    except OSError:
        return
    for old in folders[:max(0, len(folders) - BACKUPS_KEPT)]:
        if old != keep:
            shutil.rmtree(old, ignore_errors=True)


def _write_user(user_dir: Path, fname: str, data: dict) -> bool:
    """Back the user's file up, then write `data` over it."""
    if not _backup(user_dir, fname):
        return False
    return _safe_write_json(Path(user_dir) / fname, data)


def follows(user_dir: Path) -> bool:
    """Whether the user lets unchanged settings follow new defaults
    (`FOLLOW_KEY` in settings.json, on where absent)."""
    data = _safe_load_json(Path(user_dir) / "settings.json", {})
    return data.get(FOLLOW_KEY, True) is not False


# -------------------- following --------------------

class _Context:
    """One sync's shared inputs: the sidecar's records, the history, and
    the records the merges build for the next sync."""

    def __init__(self, user_dir, defaults_dir, synced, is_first_sync):
        self.user_dir = Path(user_dir)
        self.defaults_dir = Path(defaults_dir)
        self.is_first_sync = is_first_sync
        self.follow = follows(user_dir)
        self.last = {kind: _dict_of(synced.get(name))
                     for kind, name in _VALUES.items()}
        self.history = _dict_of(_safe_load_json(
            self.defaults_dir / HISTORY_FILE, {}))
        self.reworked = _dict_of(synced.get(_PRESET_REWORKED))
        self.undone_before = _dict_of(synced.get(_UNDONE))
        self.undone = {}
        self.values = {}
        # The user's presets once theirs are merged; None where they
        # did not read.
        self.preset_names = None

    def past(self, kind):
        return _dict_of(self.history.get(kind))


def _decide(mine, shipped, last, past, undone, equal) -> str:
    """What to do with a user's value against its default's:

    - `same`: it is the default;
    - `update`: the user never changed it, and the default moved;
    - `kept`: the user changed it, and the default moved since the last
      sync, which the notice says;
    - `own`: the user changed it, and nothing new is on offer.

    `last` is the default's value at the last sync (`_MISSING` where none
    was recorded, and then any value in `past` counts as never changed);
    `undone` the value `undo` put back, which is the user's own."""
    if equal(mine, shipped):
        return "same"
    if undone is not _MISSING and equal(mine, undone):
        moved = last is not _MISSING and not equal(last, shipped)
        return "kept" if moved else "own"
    if last is not _MISSING:
        if equal(mine, last):
            return "update"
        return "own" if equal(last, shipped) else "kept"
    return "update" if any(equal(mine, p) for p in past) else "own"


def _same(a, b) -> bool:
    """Whether two settings values are the same, a list read as the set
    it is -- the Optimizer tab saves its selected sets in the order they
    were ticked, a default in the order it was written."""
    if isinstance(a, list) and isinstance(b, list):
        try:
            return sorted(a) == sorted(b)
        except TypeError:
            return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    return a == b


def _apply(ctx, decision, entry) -> bool:
    """Record `decision` for `entry` in the report; True where the value
    is to be updated. With following off, nothing is updated or
    reported."""
    if not ctx.follow:
        return False
    if decision == "update":
        report.updated.append(entry)
        return True
    if decision == "kept":
        report.kept.append(entry)
    return False


def _merge_presets(ctx, known_keys: list) -> list:
    """presets.json: add preset by NAME if new-in-defaults and absent
    from the user file, and bring a copy the user never changed to the
    shipped value where a release changed it.

    A copy `presets_follow` re-worked counts as unchanged too, and keeps
    its re-worked weights until a release changes the preset: then it
    takes the shipped one, and `presets_follow` re-works it again if it
    still needs it."""
    from preset_manager import weights_equal
    user_file = ctx.user_dir / "presets.json"
    default_file = ctx.defaults_dir / "presets.json"
    if not default_file.exists():
        return list(known_keys)

    user_data = _user_json(user_file, {"presets": {}})
    if user_data is None:
        return list(known_keys)
    default_data = _safe_load_json(default_file, {"presets": {}})

    user_presets = user_data.setdefault("presets", {})
    default_presets = default_data.get("presets", {})
    if not isinstance(user_presets, dict) or not isinstance(default_presets, dict):
        return list(known_keys)

    changed = False
    last = ctx.last["presets"]
    past = ctx.past("presets")
    undone = _dict_of(ctx.undone_before.get("presets"))
    still_reworked = {}
    for name, weights in default_presets.items():
        mine = user_presets.get(name)
        if not isinstance(mine, dict) or not isinstance(weights, dict):
            continue
        entry = {"kind": "presets", "key": name, "fields": None,
                 "label": name}
        held = undone.get(name, _MISSING)
        if held is not _MISSING and weights_equal(mine, held):
            ctx.undone.setdefault("presets", {})[name] = held
        elif name in ctx.reworked \
                and weights_equal(mine, ctx.reworked[name]) \
                and not weights_equal(mine, weights):
            if name in last and weights_equal(weights, last[name]):
                still_reworked[name] = ctx.reworked[name]
                continue
            if _apply(ctx, "update", entry):
                user_presets[name] = dict(weights)
                changed = True
            continue
        decision = _decide(mine, weights, last.get(name, _MISSING),
                           past.get(name, ()), held, weights_equal)
        if _apply(ctx, decision, entry):
            user_presets[name] = dict(weights)
            changed = True
    if ctx.follow:
        ctx.reworked = still_reworked

    # Grandfathering: with no sidecar, every current default counts as
    # known, so a deletion made before tombstones existed sticks.
    if not ctx.is_first_sync:
        known_set = set(known_keys)
        for name, weights in default_presets.items():
            if name not in known_set and name not in user_presets:
                user_presets[name] = weights
                changed = True

    if changed:
        _write_user(ctx.user_dir, "presets.json", user_data)
    ctx.preset_names = set(user_presets)
    ctx.values[_VALUES["presets"]] = {
        name: weights for name, weights in default_presets.items()
        if isinstance(weights, dict)}
    return list(default_presets.keys())


def _merge_character_preset(ctx, known_keys: list) -> list:
    """character_preset.json: add assignment by RES_ID if new-in-defaults
    and absent from the user file, and bring an assignment the user never
    changed to the shipped one where a release changed it. Normalizes
    both sides to the v2 schema first; v1 files on disk are rewritten as
    v2 (the defaults-side write silently fails in frozen builds, which
    is fine)."""
    user_file = ctx.user_dir / "character_preset.json"
    default_file = ctx.defaults_dir / "character_preset.json"
    if not default_file.exists():
        return list(known_keys)

    # Local import: character_preset_manager imports game_data, which is
    # heavier than anything this module otherwise needs.
    try:
        from character_preset_manager import normalize_to_v2
    except ImportError:
        return list(known_keys)

    user_raw = _user_json(user_file, {"assignments": {}})
    if user_raw is None:
        return list(known_keys)
    default_raw = _safe_load_json(default_file, {"assignments": {}})

    user_data = normalize_to_v2(user_raw)
    default_data = normalize_to_v2(default_raw)

    user_assignments = user_data.setdefault("assignments", {})
    user_name_hints = user_data.setdefault("name_hints", {})
    default_assignments = default_data.get("assignments", {})
    default_name_hints = default_data.get("name_hints", {})
    if not isinstance(user_assignments, dict) or not isinstance(default_assignments, dict):
        return list(known_keys)

    user_was_v1 = user_raw.get("version", 1) < 2
    default_was_v1 = default_raw.get("version", 1) < 2

    changed = False
    last = ctx.last["character_preset"]
    past = ctx.past("character_preset")
    undone = _dict_of(ctx.undone_before.get("character_preset"))
    for rid, preset in default_assignments.items():
        if rid not in user_assignments:
            continue
        mine = user_assignments[rid]
        if preset is not None and ctx.preset_names is not None \
                and preset not in ctx.preset_names:
            # A preset the user deleted is not on offer.
            continue
        entry = {"kind": "character_preset", "key": rid, "fields": None,
                 "label": user_name_hints.get(rid)
                 or default_name_hints.get(rid, rid)}
        if rid in undone and _same(mine, undone[rid]):
            ctx.undone.setdefault("character_preset", {})[rid] = mine
        if mine is None and preset is not None and rid not in last \
                and rid not in undone:
            # The "Default Preset" the program gives every combatant it
            # meets (`CharacterPresetManager.ensure_characters`), for one
            # whose default was not yet recorded: never chosen.
            decision = "update"
        else:
            decision = _decide(mine, preset, last.get(rid, _MISSING),
                               past.get(rid, ()), undone.get(rid, _MISSING),
                               _same)
        if _apply(ctx, decision, entry):
            user_assignments[rid] = preset
            changed = True

    if not ctx.is_first_sync:
        known_set = set(known_keys)
        for rid, preset in default_assignments.items():
            if rid in known_set:
                continue
            if rid not in user_assignments:
                user_assignments[rid] = preset
                user_name_hints[rid] = default_name_hints.get(rid, rid)
                changed = True

    if changed or user_was_v1:
        _write_user(ctx.user_dir, "character_preset.json", user_data)
    if default_was_v1:
        _safe_write_json(default_file, default_data)
    ctx.values[_VALUES["character_preset"]] = dict(default_assignments)
    return list(default_assignments.keys())


# An optimizer entry's fields that never follow: the combatant's name as
# the file last saw it, which the program refreshes itself.
_OPTIMIZER_OWN = frozenset({"name_hint"})


def _as_made(entry, generic) -> bool:
    """Whether every field of an optimizer entry holds what some fresh
    entry `generic` holds (`DEFAULT_CHARACTER_SETTINGS`, each version
    the program has had): one the program made and nobody changed. A
    retired `set_effect_pct` counts in the per-set form
    `OptimizerSettingsManager.load` migrates it to."""
    scalars = [g["set_effect_pct"] for g in generic if "set_effect_pct" in g]
    for field, value in entry.items():
        if field in _OPTIMIZER_OWN:
            continue
        if field == "set_effect_pcts" and isinstance(value, dict) and value:
            pcts = list(value.values())
            if all(p == pcts[0] for p in pcts) and pcts[0] in scalars:
                continue
        if not any(field in g and _same(value, g[field]) for g in generic):
            return False
    return True


def _merge_optimizer_settings(ctx, known_keys: list) -> list:
    """optimizer_settings.json: add char by RES_ID if new-in-defaults and
    absent from the user file, and bring each field of an entry the user
    never changed to the shipped value where a release changed it. An
    entry the program made itself (`OptimizerSettingsManager.
    bootstrap_known_characters`) for a combatant whose default no sync
    recorded follows WHOLE where it is still as made (`_as_made`): per
    field, its zeros would read as the user's. A field the entry lacks
    reads as a fresh entry's. Newly-added chars are also appended to the
    user's excluded_gear_chars (new chars default to excluded).
    Top-level keys other than `characters` are never merged -- user
    values are authoritative."""
    user_file = ctx.user_dir / "optimizer_settings.json"
    default_file = ctx.defaults_dir / "optimizer_settings.json"
    if not default_file.exists():
        return list(known_keys)

    user_data = _user_json(
        user_file,
        {"version": 1, "excluded_gear_chars": [], "characters": {}},
    )
    if user_data is None:
        return list(known_keys)
    default_data = _safe_load_json(
        default_file,
        {"version": 1, "excluded_gear_chars": [], "characters": {}},
    )

    user_chars = user_data.setdefault("characters", {})
    default_chars = default_data.get("characters", {})
    user_excluded = user_data.setdefault("excluded_gear_chars", [])
    if not isinstance(user_chars, dict) or not isinstance(default_chars, dict):
        return list(known_keys)
    if not isinstance(user_excluded, list):
        user_excluded = []
        user_data["excluded_gear_chars"] = user_excluded

    changed = False
    last = ctx.last["optimizer_settings"]
    past = ctx.past("optimizer_settings")
    generic = [g for g in ctx.history.get("optimizer_generic", [])
               if isinstance(g, dict)]
    fresh = {}
    try:
        from optimizer_settings_manager import DEFAULT_CHARACTER_SETTINGS
        fresh = dict(DEFAULT_CHARACTER_SETTINGS)
        generic.append(fresh)
    except Exception:
        pass
    undone = _dict_of(ctx.undone_before.get("optimizer_settings"))

    def own(entry):
        return {k: v for k, v in entry.items() if k not in _OPTIMIZER_OWN}

    for rid, shipped in default_chars.items():
        mine = user_chars.get(rid)
        if not isinstance(mine, dict) or not isinstance(shipped, dict):
            continue
        label = mine.get("name_hint") or shipped.get("name_hint") or rid
        last_entry = _dict_of(last.get(rid))
        past_entry = _dict_of(past.get(rid))
        undone_entry = _dict_of(undone.get(rid))
        if not last_entry and not undone_entry \
                and not _same(own(mine), own(shipped)) \
                and _as_made(mine, generic):
            # Made by the program (`bootstrap_known_characters`) before
            # this default was recorded, and still as made: it follows
            # whole. Field by field, its zeros would read as the user's.
            entry = {"kind": "optimizer_settings", "key": rid,
                     "fields": [f for f in own(shipped)
                                if not _same(mine.get(f, _MISSING),
                                             shipped[f])],
                     "label": label}
            if _apply(ctx, "update", entry):
                name = mine.get("name_hint")
                mine.clear()
                mine.update(shipped)
                if name:
                    mine["name_hint"] = name
                changed = True
            continue
        moved, stayed = [], []
        for field, value in shipped.items():
            if field in _OPTIMIZER_OWN:
                continue
            if field not in mine:
                # Never set, so it reads as a fresh entry's value: it
                # follows where that is not the default, unless the last
                # sync already offered this default.
                if not _same(value, fresh.get(field, _MISSING)) \
                        and not _same(last_entry.get(field, _MISSING),
                                      value):
                    moved.append(field)
                continue
            if field in undone_entry \
                    and _same(mine[field], undone_entry[field]):
                ctx.undone.setdefault("optimizer_settings", {}).setdefault(
                    rid, {})[field] = mine[field]
            decision = _decide(
                mine[field], value, last_entry.get(field, _MISSING),
                past_entry.get(field, ()),
                undone_entry.get(field, _MISSING), _same)
            if decision == "update":
                moved.append(field)
            elif decision == "kept":
                stayed.append(field)
        if not ctx.follow:
            continue
        if moved:
            report.updated.append({"kind": "optimizer_settings", "key": rid,
                                   "fields": moved, "label": label})
            for field in moved:
                mine[field] = shipped[field]
            changed = True
        if stayed:
            report.kept.append({"kind": "optimizer_settings", "key": rid,
                                "fields": stayed, "label": label})

    if not ctx.is_first_sync:
        known_set = set(known_keys)
        for rid, settings in default_chars.items():
            if rid in known_set:
                continue
            if rid not in user_chars:
                user_chars[rid] = settings
                if rid not in user_excluded:
                    user_excluded.append(rid)
                changed = True

    if changed:
        _write_user(ctx.user_dir, "optimizer_settings.json", user_data)
    ctx.values[_VALUES["optimizer_settings"]] = {
        rid: {k: v for k, v in s.items() if k not in _OPTIMIZER_OWN}
        for rid, s in default_chars.items() if isinstance(s, dict)}
    return list(default_chars.keys())


def _merge_settings(ctx) -> None:
    """settings.json: bring a key the user never changed to its code
    default (`SettingsManager.LAYOUT`) where a release changed it. Keys
    the user does not have yet are left to `SettingsManager.
    apply_layout`, which adds them; the program's own state
    (`SettingsManager.state_keys`) and `FOLLOW_KEY` never follow."""
    from settings_manager import SettingsManager
    user_file = ctx.user_dir / "settings.json"
    defaults = {key: value for key, value in SettingsManager.LAYOUT
                if not key.startswith("#")
                and key not in SettingsManager.state_keys()
                and key != FOLLOW_KEY}
    ctx.values[_VALUES["settings"]] = defaults
    if not user_file.exists():
        return
    data = _user_json(user_file, {})
    if data is None:
        return
    last = ctx.last["settings"]
    past = ctx.past("settings")
    undone = _dict_of(ctx.undone_before.get("settings"))
    changed = False
    for key, default in defaults.items():
        if key not in data:
            continue
        if key in undone and _same(data[key], undone[key]):
            ctx.undone.setdefault("settings", {})[key] = data[key]
        decision = _decide(data[key], default, last.get(key, _MISSING),
                           past.get(key, ()), undone.get(key, _MISSING),
                           _same)
        entry = {"kind": "settings", "key": key, "fields": None,
                 "label": key}
        if _apply(ctx, decision, entry):
            data[key] = default
            changed = True
    if changed:
        _write_user(ctx.user_dir, "settings.json", data)


# -------------------- undo --------------------

# The file each kind of entry lives in.
_FILES = {"presets": "presets.json", "reworked": "presets.json",
          "character_preset": "character_preset.json",
          "optimizer_settings": "optimizer_settings.json",
          "settings": "settings.json"}


def undo(user_dir: Path) -> list:
    """Put back the files this launch changed, from its backup, and mark
    every value it updated as the user's own, so the next launch does
    not update it again. Returns the names of the files put back; the
    caller reloads what holds them."""
    global report
    user_dir = Path(user_dir)
    if report.backup is None:
        return []
    restored = []
    for fname in report.files:
        try:
            shutil.copy2(report.backup / fname, user_dir / fname)
            restored.append(fname)
        except OSError as e:
            report.failed.append(("undo", fname, str(e)))
    state_file = user_dir / _SYNC_STATE_FILENAME
    state = _load_sync_state(state_file)
    undone = _dict_of(state.get(_UNDONE))
    for entry in report.updated:
        fname = _FILES.get(entry["kind"])
        if fname not in restored:
            continue
        data = _safe_load_json(user_dir / fname, {})
        kind = "presets" if entry["kind"] == "reworked" else entry["kind"]
        key = entry["key"]
        if kind == "presets":
            value = _dict_of(data.get("presets")).get(key)
        elif kind == "character_preset":
            value = _dict_of(data.get("assignments")).get(key, _MISSING)
        elif kind == "optimizer_settings":
            held = _dict_of(_dict_of(data.get("characters")).get(key))
            for field in entry["fields"] or ():
                if field in held:
                    undone.setdefault(kind, {}).setdefault(key, {})[field] = \
                        held[field]
            continue
        else:
            value = data.get(key, _MISSING)
        # None is an assignment's "Default Preset", a value like any
        # other; for a preset or a setting it is one the file lacks.
        if value is _MISSING or (value is None
                                 and kind != "character_preset"):
            continue
        undone.setdefault(kind, {})[key] = value
    state[_UNDONE] = undone
    _save_sync_state(state_file, state)
    done = Report()
    done.backup, done.files = report.backup, report.files
    report = done
    return restored


# -------------------- presets for the game client's rolls --------------------

# What `presets_follow` last worked out the shipped presets to be, where
# the game client's max rolls moved them: what Restore Defaults offers
# (`effective_presets`). None where they stand as shipped.
_effective = None


def effective_presets(default_presets: dict) -> dict:
    """The shipped presets as this launch has them: re-worked for the
    game client's max rolls where `presets_follow` found those moved."""
    out = dict(default_presets)
    out.update(_effective or {})
    return out


def presets_follow(user_dir: Path, defaults_dir: Path, preset_manager=None):
    """Re-work the shipped presets for the game client's max rolls, and
    bring every copy the user never changed to them; run once the
    client's facts are laid over (`game_client.use`).

    Where the rolls are those the presets were derived with, a copy
    re-worked at an earlier launch goes back to the shipped value. A
    changed copy is never touched: Restore Defaults offers it the
    re-worked value (`effective_presets`). Nothing is changed or
    reported where the user turned following off (`FOLLOW_KEY`).

    `preset_manager`, where the presets are loaded, is updated and
    saves the file; else the file is written here, after this launch's
    backup takes it. Returns the names of the presets it changed."""
    global _effective
    import preset_derivation
    from preset_manager import weights_equal
    user_dir, defaults_dir = Path(user_dir), Path(defaults_dir)
    defaults = _dict_of(_safe_load_json(defaults_dir / "presets.json",
                                        {}).get("presets"))
    targets = preset_derivation.rework(defaults_dir) or {}
    _effective = targets or None
    state_file = user_dir / _SYNC_STATE_FILENAME
    state = _load_sync_state(state_file)
    reworked = _dict_of(state.get(_PRESET_REWORKED))
    undone = _dict_of(_dict_of(state.get(_UNDONE)).get("presets"))
    follow = follows(user_dir)
    if preset_manager is not None:
        if preset_manager.is_corrupted():
            return []
        mine_all = preset_manager.presets
    else:
        data = _user_json(user_dir / "presets.json", {"presets": {}})
        if data is None:
            return []
        mine_all = data.setdefault("presets", {})
    changed = []
    for name, shipped in defaults.items():
        mine = mine_all.get(name)
        target = targets.get(name, shipped)
        if not isinstance(mine, dict) or weights_equal(mine, target) \
                or (name in undone and weights_equal(mine, undone[name])):
            continue
        if weights_equal(mine, shipped) or (
                name in reworked and weights_equal(mine, reworked[name])):
            if not follow:
                continue
            report.updated.append({"kind": "reworked", "key": name,
                                   "fields": None, "label": name})
            changed.append(name)
    if changed:
        if not _backup(user_dir, "presets.json"):
            del report.updated[len(report.updated) - len(changed):]
            return []
        for name in changed:
            mine_all[name] = {k: float(v)
                              for k, v in targets.get(name,
                                                      defaults[name]).items()}
        if preset_manager is not None:
            preset_manager._write()
        else:
            _safe_write_json(user_dir / "presets.json", data)
    new_reworked = {name: weights for name, weights in targets.items()
                    if weights_equal(mine_all.get(name), weights)}
    if follow and new_reworked != reworked:
        state[_PRESET_REWORKED] = new_reworked
        _save_sync_state(state_file, state)
    return changed
