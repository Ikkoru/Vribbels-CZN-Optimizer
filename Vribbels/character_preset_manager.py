"""
CharacterPresetManager - Per-character scoring preset assignments.

Persists which custom Gear Score preset each character uses for their personal
GS calculation. Stored as JSON in `settings/character_preset.json`.

Schema version 2 (ID-keyed)
===========================
    {
        "version": 2,
        "assignments": {
            "1017":  "Amir",         # res_id (string) -> preset name
            "1055":  null,           # null = default preset (all weights 1.0)
            "20034": "Tank Build"    # captured-but-unknown id, no CHARACTERS entry yet
        },
        "name_hints": {
            "1017":  "Amir",         # cosmetic; the manager uses this for the
            "1055":  "Adelheid",     #   .assignments name-keyed view and the
            "20034": "20034"         #   API's name <-> id translation only.
        }
    }

Keying by res_id (not character name) solves the captured-but-unknown ->
known-by-name migration problem: if you assigned a preset to a character
captured as "1055" before they were added to CHARACTERS as "Adelheid",
the assignment stays put under key "1055". When CHARACTERS is updated,
only the cosmetic `name_hint` field shifts; the user's choice survives.

Schema version 1 (legacy, name-keyed)
=====================================
    {"assignments": {"Amir": "Amir", "1055": null, ...}}

V1 files are migrated to V2 on load() via `migrate_v1_to_v2`. After
migration, the manager writes back in V2 form so the migration runs at
most once per file. The migration:
  - Numeric keys (digit-only strings)  -> kept as the res_id key.
  - Name keys resolvable via CHARACTERS -> rewritten to that res_id key.
  - Other name keys (unknown names)    -> kept as the key (fallback).
  - Conflicts: prefer the non-null assignment if one of them is null.

API
===
The public methods (`get_preset_for(name)`, `set_preset_for(name, preset)`,
`ensure_character(name)`, etc.) still accept character DISPLAY NAMES for
backward compatibility. Internally they translate name -> res_id via
CHARACTERS lookup. Captured-but-unknown chars (numeric-string display
names) resolve to themselves.

For callers that already have a res_id at hand, parallel methods exposing
res_id directly are provided (`*_by_id` variants).

The legacy `.assignments` attribute is preserved as a NAME-keyed view of
the data (for code that reads but doesn't mutate it). Writes through that
dict do NOT persist -- use the API methods.
"""

import json
import shutil
from pathlib import Path
from typing import Optional


CHARACTER_PRESET_SCHEMA_VERSION = 2


# ----- module-level helpers (also imported by defaults_sync) ---------

def _build_character_name_maps() -> tuple:
    """Build {name: res_id_str} and {res_id_str: name} from CHARACTERS.

    Returns (name_to_id, id_to_name). On import failure (standalone use
    without game_data), returns ({}, {}).
    """
    try:
        from game_data.characters import CHARACTERS
    except ImportError:
        return {}, {}

    name_to_id: dict = {}
    id_to_name: dict = {}
    for rid, char_data in CHARACTERS.items():
        if not isinstance(char_data, dict):
            continue
        cname = char_data.get("name", "")
        if cname and cname != "Unknown":
            name_to_id[cname] = str(rid)
            id_to_name[str(rid)] = cname
    return name_to_id, id_to_name


def migrate_v1_to_v2(name_keyed_assignments: dict) -> tuple:
    """Convert a v1 name-keyed assignments dict to v2 (id-keyed) form.

    Args:
        name_keyed_assignments: {char_name | numeric_str: preset_name | None}

    Returns:
        (assignments_by_id, name_hints) -- both dicts keyed by res_id-as-string.

    Pure function. Used by CharacterPresetManager.load() AND by
    defaults_sync._merge_character_preset (so the merge can normalize
    mismatched-version files before comparing keys).
    """
    name_to_id, id_to_name = _build_character_name_maps()

    assignments_by_id: dict = {}
    name_hints: dict = {}
    for key, value in name_keyed_assignments.items():
        if not isinstance(key, str):
            continue  # malformed entry, skip

        if key.isdigit():
            # Numeric key -- already a res_id. Look up display name if known.
            rid_str = key
            hint = id_to_name.get(rid_str, key)
        else:
            # Name key. Try CHARACTERS lookup.
            resolved = name_to_id.get(key)
            if resolved is not None:
                rid_str = resolved
                hint = key
            else:
                # Unknown name not in CHARACTERS -- keep the name as the key.
                # Manual cleanup may be needed if it's a typo, but losing
                # the entry silently would be worse.
                rid_str = key
                hint = key

        existing = assignments_by_id.get(rid_str)
        if rid_str in assignments_by_id:
            # Collision: numeric key + name key for the same character.
            # Prefer the non-null assignment.
            if existing is None and value is not None:
                assignments_by_id[rid_str] = value
            # Update name_hint to the proper-name form if we have one.
            if not name_hints.get(rid_str, "").isdigit() and hint.isdigit():
                pass  # existing hint is the proper name; keep it
            else:
                name_hints[rid_str] = hint
        else:
            assignments_by_id[rid_str] = value
            name_hints[rid_str] = hint

    return assignments_by_id, name_hints


def normalize_to_v2(data: dict) -> dict:
    """Return `data` in v2 form. If already v2, returns unchanged. If v1
    (or missing version), runs `migrate_v1_to_v2` and returns the v2
    structure.

    Pure function. Used by both the manager and defaults_sync.
    """
    if not isinstance(data, dict):
        return {"version": CHARACTER_PRESET_SCHEMA_VERSION,
                "assignments": {}, "name_hints": {}}
    version = data.get("version", 1)
    if version >= 2:
        # Already v2 -- ensure required keys exist.
        out = {
            "version": CHARACTER_PRESET_SCHEMA_VERSION,
            "assignments": dict(data.get("assignments", {})),
            "name_hints": dict(data.get("name_hints", {})),
        }
        return out
    # v1 migration
    name_keyed = data.get("assignments", {})
    if not isinstance(name_keyed, dict):
        name_keyed = {}
    assignments_by_id, name_hints = migrate_v1_to_v2(name_keyed)
    return {
        "version": CHARACTER_PRESET_SCHEMA_VERSION,
        "assignments": assignments_by_id,
        "name_hints": name_hints,
    }


# ----- the manager --------------------------------------------------

class CharacterPresetManager:
    """Loads, saves, and manages per-character preset assignments."""

    def __init__(self, base_dir: Path):
        """
        Args:
            base_dir: The program's base directory. Stored alongside the
                      other manager files in `settings/`.
        """
        self.presets_dir = Path(base_dir) / "settings"
        self.assignments_file = self.presets_dir / "character_preset.json"

        # Authoritative storage: res_id (str) -> preset_name | None.
        self.assignments_by_id: dict = {}
        # Cosmetic mirror: res_id (str) -> display name.
        self.name_hints: dict = {}

        # Round 11 Task 4: cache the CHARACTERS lookup tables built by
        # `_build_character_name_maps`. Without this, every
        # `_resolve_name_to_id` call rebuilt them from scratch -- which
        # added up to N rebuilds per HeroesTab.refresh_heroes (one per
        # combatant), each iterating all ~40 CHARACTERS entries. Lazy
        # init + invalidate via `invalidate_name_cache()` if game data
        # ever changes mid-run (it doesn't today, but the hook is there).
        self._name_to_id_cache = None
        self._id_to_name_cache = None

        self.corrupted: bool = False
        self.corruption_error: Optional[str] = None

    def invalidate_name_cache(self):
        """Drop the cached CHARACTERS lookup tables. Call this if game
        data is reloaded at runtime so future name<->id translations
        pick up the new mappings."""
        self._name_to_id_cache = None
        self._id_to_name_cache = None

    def _get_character_name_maps(self) -> tuple:
        """Lazy-init + cache for (name_to_id, id_to_name)."""
        if self._name_to_id_cache is None:
            n2i, i2n = _build_character_name_maps()
            self._name_to_id_cache = n2i
            self._id_to_name_cache = i2n
        return self._name_to_id_cache, self._id_to_name_cache

    # ----- name <-> id resolution -----

    def _resolve_name_to_id(self, character_name: str) -> Optional[str]:
        """Translate a character display name to its res_id-as-string.

        Resolution order:
          1. CHARACTERS by name (proper-name -> res_id).
          2. If the name itself is a digit-only string, treat it as a
             captured-but-unknown res_id and return as-is.
          3. If the name is already a key in our store (e.g. an unknown
             non-numeric name that survived migration), return it.
          4. Otherwise None.

        Round 11 Task 4: CHARACTERS lookup uses the cached map instead
        of rebuilding it on every call. ~Nx speedup in refresh_heroes,
        where N is the number of combatants.
        """
        if not isinstance(character_name, str) or not character_name:
            return None
        name_to_id, _ = self._get_character_name_maps()
        if character_name in name_to_id:
            return name_to_id[character_name]
        if character_name.isdigit():
            return character_name
        if character_name in self.assignments_by_id:
            return character_name
        return None

    # ----- loading -----

    def load(self):
        """Load assignments from disk. Sets corrupted=True on any structural problem."""
        self.assignments_by_id = {}
        self.name_hints = {}
        self.corrupted = False
        self.corruption_error = None

        if not self.assignments_file.exists():
            return

        try:
            raw_text = self.assignments_file.read_text(encoding="utf-8")
        except Exception as e:
            self._mark_corrupted(f"Cannot read file: {e}")
            return

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            self._mark_corrupted(
                f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"
            )
            return

        if not isinstance(data, dict):
            self._mark_corrupted("Top-level JSON must be an object.")
            return

        if "assignments" not in data:
            self._mark_corrupted("Missing 'assignments' key.")
            return

        if not isinstance(data["assignments"], dict):
            self._mark_corrupted("'assignments' must be an object.")
            return

        # Structural validation -- before migration so we catch malformed
        # entries either way.
        for name, preset in data["assignments"].items():
            if not isinstance(name, str) or not name.strip():
                self._mark_corrupted("Character key must be a non-empty string.")
                return
            if preset is not None and not isinstance(preset, str):
                self._mark_corrupted(
                    f"Character '{name}': preset must be a string or null."
                )
                return

        # Normalize to v2 schema. Idempotent for already-v2 data.
        v2 = normalize_to_v2(data)
        self.assignments_by_id = v2["assignments"]
        self.name_hints = v2["name_hints"]

        # Persist the migrated form so future loads skip the migration step.
        if data.get("version", 1) < CHARACTER_PRESET_SCHEMA_VERSION:
            self._write()

    def _mark_corrupted(self, reason: str):
        self.corrupted = True
        self.corruption_error = reason
        self.assignments_by_id = {}
        self.name_hints = {}

    # ----- legacy name-keyed view (read-only) -----

    @property
    def assignments(self) -> dict:
        """Backward-compat view: {display_name: preset | None}.

        Built fresh on every access. Mutating this dict does NOT propagate
        back to the manager -- use `set_preset_for` / `ensure_character`.
        Provided so older code that iterates `manager.assignments` keeps
        working through the v2 schema cutover.
        """
        view: dict = {}
        for rid, preset in self.assignments_by_id.items():
            display = self.name_hints.get(rid, rid)
            view[display] = preset
        return view

    # ----- queries -----

    def is_corrupted(self) -> bool:
        return self.corrupted

    def get_preset_for(self, character_name: str) -> Optional[str]:
        """Return the assigned preset name, or None if default/unassigned."""
        rid = self._resolve_name_to_id(character_name)
        if rid is None:
            return None
        return self.assignments_by_id.get(rid)

    def get_preset_by_id(self, res_id) -> Optional[str]:
        """Return the assigned preset for a res_id (int or str)."""
        return self.assignments_by_id.get(str(res_id))

    def get_name_hint(self, res_id) -> Optional[str]:
        """Return the stored display-name hint for a res_id, if any."""
        return self.name_hints.get(str(res_id))

    # ----- mutations (no-op while corrupted, except quarantine) -----

    def set_preset_for(self, character_name: str, preset_name: Optional[str]):
        """Assign a preset (or None for default) to a character and persist.

        Translates the name to a res_id internally and writes through to
        `assignments_by_id`. For unknown characters whose name doesn't
        resolve to a CHARACTERS entry, the name itself is used as the key.
        """
        if self.corrupted:
            raise RuntimeError("Character preset file is corrupted; quarantine it first.")
        rid = self._resolve_name_to_id(character_name)
        if rid is None:
            # Truly unknown -- use the name as the key. Future migrations
            # will fix it if CHARACTERS catches up.
            rid = character_name
        self.assignments_by_id[rid] = preset_name
        self.name_hints[rid] = character_name
        self._write()

    def set_preset_by_id(self, res_id, preset_name: Optional[str],
                         name_hint: str = ""):
        """ID-first variant of set_preset_for. `name_hint` updates the
        display-name hint (cosmetic). Empty hint leaves the existing one
        alone."""
        if self.corrupted:
            raise RuntimeError("Character preset file is corrupted; quarantine it first.")
        rid = str(res_id)
        self.assignments_by_id[rid] = preset_name
        if name_hint:
            self.name_hints[rid] = name_hint
        elif rid not in self.name_hints:
            self.name_hints[rid] = rid
        self._write()

    def ensure_character(self, character_name: str) -> bool:
        """Add a new character with default (None) assignment if not yet seen.
        Returns True if a new entry was created. Refreshes the name_hint
        if the entry exists and the stored hint is stale (e.g.
        captured-but-unknown becoming known)."""
        if self.corrupted:
            return False
        rid = self._resolve_name_to_id(character_name)
        if rid is None:
            rid = character_name
        if rid in self.assignments_by_id:
            # Existing entry -- refresh name_hint if the new name is better.
            current_hint = self.name_hints.get(rid, "")
            if character_name and current_hint != character_name:
                self.name_hints[rid] = character_name
                self._write()
            return False
        self.assignments_by_id[rid] = None
        self.name_hints[rid] = character_name
        self._write()
        return True

    def ensure_characters(self, character_names) -> bool:
        """Bulk version of ensure_character. Single write. Returns True if any added."""
        if self.corrupted:
            return False
        added = False
        for name in character_names:
            rid = self._resolve_name_to_id(name)
            if rid is None:
                rid = name
            if rid not in self.assignments_by_id:
                self.assignments_by_id[rid] = None
                self.name_hints[rid] = name
                added = True
            else:
                # Refresh stale hint
                current_hint = self.name_hints.get(rid, "")
                if name and current_hint != name:
                    self.name_hints[rid] = name
                    added = True  # write so the refresh persists
        if added:
            self._write()
        return added

    def remove_assignments_to(self, preset_name: str) -> int:
        """Reset every character currently assigned to `preset_name` back to default.
        Returns the number of assignments cleared. Single write."""
        if self.corrupted:
            return 0
        cleared = 0
        for rid, current in list(self.assignments_by_id.items()):
            if current == preset_name:
                self.assignments_by_id[rid] = None
                cleared += 1
        if cleared:
            self._write()
        return cleared

    def quarantine(self):
        """Move the corrupted file aside (presets_corrupted.json, _corrupted2, ...)
        and reset to a clean state so subsequent writes can proceed."""
        if not self.corrupted:
            return
        if self.assignments_file.exists():
            target = self._unique_quarantine_path()
            shutil.move(str(self.assignments_file), str(target))
        self.corrupted = False
        self.corruption_error = None
        self.assignments_by_id = {}
        self.name_hints = {}

    # ----- internals -----

    def _unique_quarantine_path(self) -> Path:
        stem = self.assignments_file.stem
        suffix = self.assignments_file.suffix
        candidate = self.assignments_file.with_name(f"{stem}_corrupted{suffix}")
        if not candidate.exists():
            return candidate
        i = 2
        while True:
            candidate = self.assignments_file.with_name(
                f"{stem}_corrupted{i}{suffix}"
            )
            if not candidate.exists():
                return candidate
            i += 1

    def _write(self):
        """Persist current state in v2 format. Creates the settings dir if needed."""
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": CHARACTER_PRESET_SCHEMA_VERSION,
            "assignments": self.assignments_by_id,
            "name_hints": self.name_hints,
        }
        tmp_path = self.assignments_file.with_suffix(
            self.assignments_file.suffix + ".tmp"
        )
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        tmp_path.replace(self.assignments_file)
