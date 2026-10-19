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

3.  Update merge with tombstone tracking: per-entity, adds default
    entries the user doesn't have. A sidecar `settings/.defaults_sync.json`
    records the keys present in defaults at the last sync; only keys NEW
    since then are candidates for adding. This is what makes user
    deletions stick -- without the tombstone, a deleted default would
    reappear every launch. Entries the user already has are NEVER
    overwritten, but for a preset they never edited, which takes a
    release's changed weights: the sidecar also records each shipped
    preset's weights, and `presets_history.json` every value one has
    shipped with, for a copy no sync recorded (`_merge_presets`).

    Per-file merge keys:
      - presets.json:            preset name
      - character_preset.json:   res_id (v2 schema; mixed-version files
                                 are normalized to v2 first and written
                                 back in v2 form)
      - optimizer_settings.json: res_id; chars added by the merge are
                                 also appended to excluded_gear_chars
                                 (new chars default to excluded)

    First-sync grandfathering: when the sidecar doesn't exist yet
    (upgrade from an older release), ALL current defaults are treated as
    already-known, protecting deletions made before tombstone tracking
    existed. Fresh installs are unaffected (Stage 2 copied everything,
    so there's nothing to add anyway).

Files with no bundled default (never touched here): settings.json,
config.json.

Known limitations (accepted trade-offs, do not "fix" without a design
discussion):
  - Renamed default entry: appears as a new key -> user gets both the
    old and new versions. Manual cleanup.
  - Changed default VALUES for a key the user has: not propagated (the
    user's version wins), but for an unedited preset. The Setup &
    Settings tab's Restore Defaults dialog is the intended way to pick
    these up. A preset edited back to a shipped value reads as unedited.

After the startup sync, once the game client's facts are laid over,
`presets_follow` re-works the shipped presets where the client's max
rolls moved them, and hands the result to every unedited copy.
  - A user file that does not read: its merge leaves it alone
    (`_user_json`). Startup mends or sets aside any that would not parse
    before this runs (`settings_repair`), so one still unreadable here
    is one that would not open.
"""

import json
import shutil
import sys
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
# The sidecar's record of each shipped preset's weights at the last
# sync, and of the weights the program re-worked a player's copy to
# (`presets_follow`): what tells an unedited copy from an edited one.
_PRESET_VALUES = "preset_values"
_PRESET_REWORKED = "preset_reworked"
# Every value each shipped preset has held, from the git history of
# `default_settings/presets.json`: for a copy no sync recorded a value
# for, which it then matches if it was never edited. Written by
# `default_settings/normalize/presets_history.py` before every build.
PRESETS_HISTORY_FILE = "presets_history.json"


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
        with them -- see `OptimizerGUI._report_sync_failures`.

        A failure here is not recoverable in place, but it MUST NOT be
        silent: stage 2 failing means a new user starts with no presets,
        no combatant assignments and no optimizer settings, in an app
        that otherwise looks perfectly healthy.
    """
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

    new_synced: dict = dict(synced)
    (new_synced["presets"], new_synced[_PRESET_VALUES],
     new_synced[_PRESET_REWORKED]) = _merge_presets(
        user_dir, defaults_dir, synced.get("presets", []), is_first_sync,
        _dict_of(synced.get(_PRESET_VALUES)),
        _dict_of(synced.get(_PRESET_REWORKED)),
    )
    new_synced["character_preset"] = _merge_character_preset(
        user_dir, defaults_dir, synced.get("character_preset", []), is_first_sync
    )
    new_synced["optimizer_settings"] = _merge_optimizer_settings(
        user_dir, defaults_dir, synced.get("optimizer_settings", []), is_first_sync
    )
    _save_sync_state(state_file, new_synced)

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


# -------------------- per-file merges --------------------
# Each returns the new tombstone list (the current defaults' key list)
# for the sidecar. On first sync they return the keys WITHOUT merging
# (grandfathering).

def _dict_of(value) -> dict:
    return value if isinstance(value, dict) else {}


def _preset_history(defaults_dir: Path) -> dict:
    """{preset name: [every value it has shipped with]}, {} where the
    history file is missing or does not read."""
    data = _safe_load_json(Path(defaults_dir) / PRESETS_HISTORY_FILE, {})
    return _dict_of(data.get("presets"))


def _unedited(name, mine, last_values, history) -> bool:
    """Whether a player's copy of preset `name` is one they never
    edited: the value the last sync shipped, or, where no sync recorded
    one, any value the preset has shipped with."""
    from preset_manager import weights_equal
    if name in last_values:
        return weights_equal(mine, last_values[name])
    return any(weights_equal(mine, past) for past in history.get(name, ()))


def _merge_presets(
    user_dir: Path,
    defaults_dir: Path,
    known_keys: list,
    is_first_sync: bool,
    last_values: dict,
    reworked: dict,
) -> tuple:
    """presets.json: add preset by NAME if new-in-defaults and absent
    from the user file, and bring a copy the player never edited to the
    shipped value where a release changed it.

    Returns (the defaults' preset names, their weights, the re-worked
    copies still standing) for the sidecar. A copy `presets_follow`
    re-worked counts as unedited too, and keeps its re-worked weights
    until a release changes the preset: then it takes the shipped one,
    and `presets_follow` re-works it again if it still needs it."""
    from preset_manager import weights_equal
    user_file = user_dir / "presets.json"
    default_file = defaults_dir / "presets.json"
    if not default_file.exists():
        return list(known_keys), last_values, reworked

    user_data = _user_json(user_file, {"presets": {}})
    if user_data is None:
        return list(known_keys), last_values, reworked
    default_data = _safe_load_json(default_file, {"presets": {}})

    user_presets = user_data.setdefault("presets", {})
    default_presets = default_data.get("presets", {})
    if not isinstance(user_presets, dict) or not isinstance(default_presets, dict):
        return list(known_keys), last_values, reworked

    changed = False
    history = _preset_history(defaults_dir)
    still_reworked = {}
    for name, weights in default_presets.items():
        mine = user_presets.get(name)
        if not isinstance(mine, dict) or not isinstance(weights, dict) \
                or weights_equal(mine, weights):
            continue
        if name in reworked and weights_equal(mine, reworked[name]):
            if name in last_values \
                    and weights_equal(weights, last_values[name]):
                still_reworked[name] = reworked[name]
                continue
        elif not _unedited(name, mine, last_values, history):
            continue
        user_presets[name] = dict(weights)
        changed = True

    # Grandfathering: with no sidecar, every current default counts as
    # known, so a deletion made before tombstones existed sticks.
    if not is_first_sync:
        known_set = set(known_keys)
        for name, weights in default_presets.items():
            if name not in known_set and name not in user_presets:
                user_presets[name] = weights
                changed = True

    if changed:
        _safe_write_json(user_file, user_data)
    values = {name: weights for name, weights in default_presets.items()
              if isinstance(weights, dict)}
    return list(default_presets.keys()), values, still_reworked


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
    bring every copy the player never edited to them; run once the
    client's facts are laid over (`game_client.use`).

    Where the rolls are those the presets were derived with, a copy
    re-worked at an earlier launch goes back to the shipped value. An
    edited copy is never touched: Restore Defaults offers it the
    re-worked value (`effective_presets`).

    `preset_manager`, where the presets are loaded, is updated and
    saves the file; else the file is written here. Returns the names of
    the presets it changed."""
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
        if not isinstance(mine, dict) or weights_equal(mine, target):
            continue
        if weights_equal(mine, shipped) or (
                name in reworked and weights_equal(mine, reworked[name])):
            mine_all[name] = {k: float(v) for k, v in target.items()}
            changed.append(name)
    new_reworked = {name: weights for name, weights in targets.items()
                    if weights_equal(mine_all.get(name), weights)}
    if changed:
        if preset_manager is not None:
            preset_manager._write()
        else:
            _safe_write_json(user_dir / "presets.json", data)
    if new_reworked != reworked:
        state[_PRESET_REWORKED] = new_reworked
        _save_sync_state(state_file, state)
    return changed


def _merge_character_preset(
    user_dir: Path,
    defaults_dir: Path,
    known_keys: list,
    is_first_sync: bool,
) -> list:
    """character_preset.json: add assignment by RES_ID if new-in-defaults
    and absent from the user file. Normalizes both sides to the v2
    schema first; v1 files on disk are rewritten as v2 (the defaults-side
    write silently fails in frozen builds, which is fine)."""
    user_file = user_dir / "character_preset.json"
    default_file = defaults_dir / "character_preset.json"
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

    if is_first_sync:
        if user_was_v1:
            _safe_write_json(user_file, user_data)
        if default_was_v1:
            _safe_write_json(default_file, default_data)
        return list(default_assignments.keys())

    known_set = set(known_keys)
    added = False
    for rid, preset in default_assignments.items():
        if rid in known_set:
            continue
        if rid not in user_assignments:
            user_assignments[rid] = preset
            user_name_hints[rid] = default_name_hints.get(rid, rid)
            added = True

    if added or user_was_v1:
        _safe_write_json(user_file, user_data)
    if default_was_v1:
        _safe_write_json(default_file, default_data)
    return list(default_assignments.keys())


def _merge_optimizer_settings(
    user_dir: Path,
    defaults_dir: Path,
    known_keys: list,
    is_first_sync: bool,
) -> list:
    """optimizer_settings.json: add char by RES_ID if new-in-defaults and
    absent from the user file. Newly-added chars are also appended to the
    user's excluded_gear_chars (new chars default to excluded). Top-level
    keys other than `characters` are never merged -- user values are
    authoritative."""
    user_file = user_dir / "optimizer_settings.json"
    default_file = defaults_dir / "optimizer_settings.json"
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

    if is_first_sync:
        return list(default_chars.keys())

    known_set = set(known_keys)
    added = False
    for rid, settings in default_chars.items():
        if rid in known_set:
            continue
        if rid not in user_chars:
            user_chars[rid] = settings
            if rid not in user_excluded:
                user_excluded.append(rid)
            added = True

    if added:
        _safe_write_json(user_file, user_data)
    return list(default_chars.keys())
