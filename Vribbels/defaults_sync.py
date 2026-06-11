"""
defaults_sync - One-shot reconciliation of bundled defaults vs the user's
settings on every startup.

Lives between the program-rename (`presets/` -> `settings/`) and the four
manager `load()` calls. Guarantees three things, in order:

1.  **Maintainer bootstrap** (one-time, only fires on the project
    maintainer's machine after the rename): if `default_settings/` is
    empty but `settings/` already has files, copy the three defaultable
    files settings/ -> default_settings/. This populates the shipped
    defaults from the maintainer's working state so they can review,
    edit, and commit `default_settings/`. After they commit the
    populated folder, this branch never fires again on their machine
    OR on any downstream user's machine.

2.  **New-user bootstrap**: if a defaultable file is missing from
    `settings/` (fresh install, no settings dir yet) and `default_settings/`
    has it, copy it over. The user starts with the same content the
    maintainer ships.

3.  **Update merge with tombstone tracking**: a sidecar file
    `settings/.defaults_sync.json` records the keys present in
    `default_settings/` the last time this function ran. On subsequent
    runs we compare that recorded state to the current defaults --
    entries in current-but-not-recorded are NEW and get added to the
    user (if the user doesn't have them already); entries in
    recorded-and-current are KNOWN, so the user's deletion (if they
    deleted one) sticks. Per-entity rules:
      - presets.json:         add preset by NAME if NEW and missing.
      - character_preset.json: add assignment for CHAR_NAME if NEW and missing.
      - optimizer_settings.json: add char by RES_ID if NEW and missing.
        New chars added this way also get auto-appended to
        excluded_gear_chars so the "new chars excluded by default" rule
        from Q6 holds for chars introduced via a release update.
    Existing user entries are NEVER overwritten. The user's manual
    tuning is always authoritative.

First-sync grandfathering
-------------------------
When `.defaults_sync.json` doesn't exist yet (e.g. user upgrades from a
pre-tombstone version), the merge treats ALL current defaults as
already-known. This protects pre-existing deletions: without this,
every previously-deleted default would silently come back on the first
post-upgrade launch. The shadow file is then written so subsequent runs
have proper tombstone tracking. For a fresh install (Stage 2 just
copied defaults wholesale), this is a no-op since user has every key
defaults has.

Files NOT touched by Stage 3:
  - `settings/settings.json` (pure user state -- no defaults file)
  - `settings/level_data.json` (pure user state -- no defaults file)

Edge cases
==========
- **Renamed default.** If `default_settings/` renames "Amir" -> "Amir
  (DPS)", the merge sees "Amir (DPS)" as a NEW key and adds it; the
  user's existing "Amir" entry stays. Result: user has both. Manual
  cleanup needed.
- **Removed default.** If a key disappears from defaults across
  versions, no action is taken on the user's side. Their copy (if any)
  stays put. The tombstone file is rewritten to reflect the new
  defaults' key set, so future runs treat that key as unknown again --
  benign because it's also not in defaults anymore.
- **Corrupted user file.** The merge skips it silently (the manager
  will quarantine on its own load() afterwards).
- **Same-name, different-weights preset.** No special handling -- the
  per-entity check is by name only. If the user has a "Amir" preset
  with their own weights and defaults ship a different "Amir", the
  user's wins. To pick up new default weights for an existing-named
  preset, the user would delete their version (which is then preserved
  as a tombstone -- so the next launch would re-add the new default).
  Actually, since the deletion is preserved, they'd need to delete AND
  manually edit `.defaults_sync.json` to remove the tombstone -- or
  delete the whole sidecar file (first-sync grandfathering then makes
  the next run a no-op for everything else, treating current defaults
  as authoritative).
"""

import json
import shutil
import sys
from pathlib import Path


# Files that have a corresponding default and need merge-on-update logic.
_DEFAULTABLE_FILES = (
    "presets.json",
    "character_preset.json",
    "optimizer_settings.json",
)


def resolve_defaults_dir(base_dir: Path) -> Path:
    """Return the directory where bundled defaults live.

    Frozen build (PyInstaller): inside `_MEIPASS` (read-only).
    Dev / source run: `<base_dir>/default_settings`.

    Matches the path-selection logic used by `OptimizerGUI.__init__`
    when calling `sync_defaults`. Exposed so other modules (e.g. the
    Setup tab's Restore Defaults dialog) can read the bundled defaults
    without re-implementing the frozen-vs-dev branch.
    """
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", base_dir))
        return bundle_root / "default_settings"
    return Path(base_dir) / "default_settings"


# Sidecar file recording which keys we've already seen in defaults.
# Lives inside settings/ next to the user's files. The leading dot is a
# tradition signaling "internal bookkeeping, leave alone"; on Windows
# it doesn't actually hide the file but the naming still communicates
# intent. Reading/writing this file is best-effort; failures degrade to
# "no tombstone tracking this run" which means previously-deleted
# defaults might come back once, then get tombstoned on the next run.
_SYNC_STATE_FILENAME = ".defaults_sync.json"


def sync_defaults(user_dir: Path, defaults_dir: Path) -> None:
    """Run the three-stage reconciliation before managers load.

    Args:
        user_dir: writable location for the user's settings/ folder.
            In a frozen build this is next to the .exe; in dev it's the
            source tree's Vribbels/.
        defaults_dir: location of the bundled `default_settings/` folder.
            In a frozen build this is inside PyInstaller's _MEIPASS
            (read-only); in dev it's a sibling of settings/.
    """
    user_dir = Path(user_dir)
    defaults_dir = Path(defaults_dir)

    user_dir.mkdir(parents=True, exist_ok=True)
    # NOTE: don't try to mkdir defaults_dir -- in frozen builds it's a
    # read-only path inside _MEIPASS. If it doesn't exist (e.g. dev with
    # nothing committed yet) Stage 1 below creates it; in frozen mode a
    # missing defaults_dir means there's nothing to merge and the function
    # silently no-ops, which is correct.

    # Stage 1: maintainer bootstrap (settings/ -> default_settings/).
    # Fires once per maintainer machine after the presets -> settings
    # rename. After they commit the populated default_settings/, this
    # branch is inert because the destination files exist. In a frozen
    # build, `defaults_dir` lives in read-only _MEIPASS; the try/except
    # below makes Stage 1 a silent no-op there.
    try:
        defaults_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return  # read-only fs -- skip both maintainer and merge stages
    for fname in _DEFAULTABLE_FILES:
        d_path = defaults_dir / fname
        u_path = user_dir / fname
        if not d_path.exists() and u_path.exists():
            try:
                shutil.copy2(u_path, d_path)
            except Exception:
                pass

    # Stage 2: new-user bootstrap (default_settings/ -> settings/).
    # Fires once per fresh install.
    for fname in _DEFAULTABLE_FILES:
        u_path = user_dir / fname
        d_path = defaults_dir / fname
        if not u_path.exists() and d_path.exists():
            try:
                shutil.copy2(d_path, u_path)
            except Exception:
                pass

    # Stage 3: tombstone-aware update merge.
    state_file = user_dir / _SYNC_STATE_FILENAME
    is_first_sync = not state_file.exists()
    synced = _load_sync_state(state_file)

    new_synced: dict = dict(synced)
    new_synced["presets"] = _merge_presets(
        user_dir, defaults_dir, synced.get("presets", []), is_first_sync
    )
    new_synced["character_preset"] = _merge_character_preset(
        user_dir, defaults_dir, synced.get("character_preset", []), is_first_sync
    )
    new_synced["optimizer_settings"] = _merge_optimizer_settings(
        user_dir, defaults_dir, synced.get("optimizer_settings", []), is_first_sync
    )
    _save_sync_state(state_file, new_synced)


# -------------------- helpers --------------------

def _safe_load_json(path: Path, fallback: dict) -> dict:
    """Read JSON from `path`. Return `fallback` on any failure."""
    try:
        if not path.exists():
            return fallback
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return fallback
        return data
    except Exception:
        return fallback


def _safe_write_json(path: Path, data: dict) -> bool:
    """Atomic write. Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)
        return True
    except Exception:
        return False


def _load_sync_state(path: Path) -> dict:
    """Read the tombstone sidecar. Returns empty dict if missing/corrupt."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_sync_state(path: Path, data: dict) -> None:
    """Write the tombstone sidecar. Best-effort."""
    _safe_write_json(path, data)


# -------------------- per-file tombstone-aware merges --------------------

def _merge_presets(
    user_dir: Path,
    defaults_dir: Path,
    known_keys: list,
    is_first_sync: bool,
) -> list:
    """presets.json: add preset BY NAME if NEW (not in last-seen defaults)
    and not already in the user file.

    Returns the new tombstone list (current defaults' keys) for the
    sidecar.
    """
    user_file = user_dir / "presets.json"
    default_file = defaults_dir / "presets.json"
    if not default_file.exists():
        return list(known_keys)

    user_data = _safe_load_json(user_file, {"presets": {}})
    default_data = _safe_load_json(default_file, {"presets": {}})

    user_presets = user_data.setdefault("presets", {})
    default_presets = default_data.get("presets", {})
    if not isinstance(user_presets, dict) or not isinstance(default_presets, dict):
        return list(known_keys)

    if is_first_sync:
        # Grandfather pre-tombstone deletions: treat all current defaults
        # as already known so nothing gets re-added on this first run.
        return list(default_presets.keys())

    known_set = set(known_keys)
    added = False
    for name, weights in default_presets.items():
        if name in known_set:
            continue  # tombstoned: known default, user may have deleted intentionally
        if name not in user_presets:
            user_presets[name] = weights
            added = True

    if added:
        _safe_write_json(user_file, user_data)
    return list(default_presets.keys())


def _merge_character_preset(
    user_dir: Path,
    defaults_dir: Path,
    known_keys: list,
    is_first_sync: bool,
) -> list:
    """character_preset.json: add assignment FOR RES_ID if NEW and missing.

    Round 11 schema bump (v2): both files use res_id (string) as the
    assignment key, with a parallel `name_hints` dict for display.
    Mixed-version inputs are normalized to v2 via
    `character_preset_manager.normalize_to_v2` before the per-key merge,
    and the file gets rewritten in v2 form so the version on disk
    catches up. Returns the new tombstone list (current defaults' res_id
    keys) for the sidecar.
    """
    user_file = user_dir / "character_preset.json"
    default_file = defaults_dir / "character_preset.json"
    if not default_file.exists():
        return list(known_keys)

    # Local import to avoid circulars at module-load time.
    try:
        from character_preset_manager import normalize_to_v2
    except ImportError:
        return list(known_keys)  # standalone use; bail.

    user_raw = _safe_load_json(user_file, {"assignments": {}})
    default_raw = _safe_load_json(default_file, {"assignments": {}})

    user_data = normalize_to_v2(user_raw)
    default_data = normalize_to_v2(default_raw)

    user_assignments = user_data.setdefault("assignments", {})
    user_name_hints = user_data.setdefault("name_hints", {})
    default_assignments = default_data.get("assignments", {})
    default_name_hints = default_data.get("name_hints", {})
    if not isinstance(user_assignments, dict) or not isinstance(default_assignments, dict):
        return list(known_keys)

    # If the on-disk user file wasn't v2 yet, write the normalized form
    # back so the manager doesn't have to re-migrate on its own load().
    user_was_v1 = user_raw.get("version", 1) < 2
    # Same for defaults -- in dev mode this also lets the maintainer's
    # next commit ship v2 defaults instead of a stale v1 file. In frozen
    # mode the write attempt silently fails (read-only _MEIPASS) which
    # is fine.
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
            # Carry the name_hint across too so the user's file gets a
            # readable hint for the new entry. Falls back to the rid
            # itself if defaults didn't ship a hint.
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
    """optimizer_settings.json: add char BY RES_ID if NEW and missing.

    Other top-level keys (excluded_gear_chars, version,
    excluded_default_initialized) stay user-authoritative.

    Q6 follow-up: chars added by this merge ALSO get appended to the
    user's `excluded_gear_chars` (if not already there), so the "new
    chars excluded by default" rule applies whether the new char arrived
    via a release-update merge OR via captured-but-unknown detection.
    """
    user_file = user_dir / "optimizer_settings.json"
    default_file = defaults_dir / "optimizer_settings.json"
    if not default_file.exists():
        return list(known_keys)

    user_data = _safe_load_json(
        user_file,
        {"version": 1, "excluded_gear_chars": [], "characters": {}},
    )
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
            # New char from a release update -> default to excluded.
            if rid not in user_excluded:
                user_excluded.append(rid)
            added = True

    if added:
        _safe_write_json(user_file, user_data)
    return list(default_chars.keys())
