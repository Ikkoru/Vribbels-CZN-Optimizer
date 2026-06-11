"""
OptimizerSettingsManager - Per-character optimizer settings persistence.

The Optimizer tab needs to remember each character's individual configuration
between launches (Important Settings sliders, Have at Least minimums, selected
sets, set-effect %, Average Buff fields, etc). This manager owns that state.

Design choices
==============
- **File**: settings/optimizer_settings.json, alongside the other manager files.
- **Key by res_id, not name.** Character names can change in the game data, so
  we key per-character entries by `str(res_id)`. A `name_hint` field is stored
  alongside each entry purely for human readability when inspecting the file;
  the manager doesn't trust or use it for lookups.
- **Bootstrap on every load.** `bootstrap_known_characters()` walks
  `CHARACTERS` (the game's master table from characters.py) and adds an entry
  for every res_id that's not already present, using DEFAULT_CHARACTER_SETTINGS.
  This means new characters added to the game (or to characters.py) get their
  optimizer settings auto-initialized the next time the program starts.
- **Stale entries kept.** When a res_id disappears from CHARACTERS (rare:
  game removes a character, or characters.py is edited downward) we DON'T
  prune the corresponding entry. Cheap defensive choice -- if it comes back
  later, the user keeps their settings.
- **Global vs per-character.** The "excluded gear chars" list is global (one
  list of characters whose currently-equipped gear should be skipped when
  the optimizer searches for candidate fragments, regardless of who you're
  currently optimizing for). Everything else is per-character.

File format (version 1)
=======================
    {
        "version": 1,
        "excluded_gear_chars": ["1004", "1009"],      # list of res_id strings
        "characters": {
            "1017": {                                   # res_id (string key)
                "name_hint": "Amir",                    # cosmetic; not used for lookup
                "optimize_for_level": 62,               # 60 / 61 / 62
                "extra_pct": 0,                         # 0-100, % of damage that's Extra DMG
                "dot_pct": 0,                           # 0-100, % of damage that's DoT
                "atk_def_split": 0,                     # 0-100, % of damage scaling off DEF (0 = full ATK)
                "shielding_healing_weight": 0,          # 0-100, blend toward shield/heal score
                "force_main": {
                    "slot4_hp": false,
                    "slot5_hp": false,
                    "slot6_hp": false,
                    "slot6_ego": false
                },
                "have_at_least": {                      # hard constraints on FINAL stats
                    "ATK": 0,    "DEF": 0,    "HP": 0,    "Ego": 0,
                    "CRate": 0,  "CDmg": 0,
                    "Extra DMG%": 0,    "DoT%": 0
                },
                "sets_selected": [9, 11, 18],           # set IDs eligible for this character
                "max_flex_slots": 6,                    # 0-6, max non-set pieces in a build
                "set_effect_pct": 0,                    # 0-100, weight of conditional-set effects
                "avg_card_dmg_pct": 100,                # Base Multiplier approximation
                "avg_mult_buff_pct": 0,                 # extra multiplicative buffs
                "avg_add_buff_pct": 0,                  # extra additive buffs
                "element_override": null                # used only when character.attribute == "Unknown"
            }
        }
    }

The "Have at Least" thresholds are compared against FINAL stat values --
the same numbers the Combatants tab displays. Builds that fail any of them
are excluded from optimizer results.
"""

import json
from pathlib import Path
from typing import Any, Optional


OPTIMIZER_SETTINGS_VERSION = 1


# Single source of truth for what a fresh character entry looks like.
# When `ensure_character` adds a new entry, it copies this dict, deep-copying
# the nested dicts/lists so each character has its own mutable state.
DEFAULT_CHARACTER_SETTINGS: dict = {
    "name_hint": "",
    "optimize_for_level": 62,
    "extra_pct": 0,
    "dot_pct": 0,
    "atk_def_split": 0,
    "shielding_healing_weight": 0,
    "force_main": {
        "slot4_hp": False,
        "slot5_hp": False,
        "slot6_hp": False,
        "slot6_ego": False,
    },
    "have_at_least": {
        "ATK": 0, "DEF": 0, "HP": 0, "Ego": 0,
        "CRate": 0, "CDmg": 0,
        "Extra DMG%": 0, "DoT%": 0,
    },
    "sets_selected": [],
    "max_flex_slots": 6,
    "set_effect_pct": 100,
    "avg_card_dmg_pct": 100,
    "avg_mult_buff_pct": 0,
    "avg_add_buff_pct": 0,
    "element_override": None,
}


def _fresh_character_settings(name_hint: str = "") -> dict:
    """Return a deep copy of DEFAULT_CHARACTER_SETTINGS suitable as a new entry.

    Each nested dict / list is copied independently so different characters
    don't share mutable state.
    """
    return {
        "name_hint": name_hint,
        "optimize_for_level": DEFAULT_CHARACTER_SETTINGS["optimize_for_level"],
        "extra_pct": DEFAULT_CHARACTER_SETTINGS["extra_pct"],
        "dot_pct": DEFAULT_CHARACTER_SETTINGS["dot_pct"],
        "atk_def_split": DEFAULT_CHARACTER_SETTINGS["atk_def_split"],
        "shielding_healing_weight": DEFAULT_CHARACTER_SETTINGS["shielding_healing_weight"],
        "force_main": dict(DEFAULT_CHARACTER_SETTINGS["force_main"]),
        "have_at_least": dict(DEFAULT_CHARACTER_SETTINGS["have_at_least"]),
        "sets_selected": list(DEFAULT_CHARACTER_SETTINGS["sets_selected"]),
        "max_flex_slots": DEFAULT_CHARACTER_SETTINGS["max_flex_slots"],
        "set_effect_pct": DEFAULT_CHARACTER_SETTINGS["set_effect_pct"],
        "avg_card_dmg_pct": DEFAULT_CHARACTER_SETTINGS["avg_card_dmg_pct"],
        "avg_mult_buff_pct": DEFAULT_CHARACTER_SETTINGS["avg_mult_buff_pct"],
        "avg_add_buff_pct": DEFAULT_CHARACTER_SETTINGS["avg_add_buff_pct"],
        "element_override": DEFAULT_CHARACTER_SETTINGS["element_override"],
    }


class OptimizerSettingsManager:
    """Per-character + global optimizer settings, persisted to disk."""

    def __init__(self, base_dir: Path):
        self.path = Path(base_dir) / "settings" / "optimizer_settings.json"
        self.data: dict = {
            "version": OPTIMIZER_SETTINGS_VERSION,
            "excluded_gear_chars": [],
            "characters": {},
        }
        self.corrupted: bool = False
        self.corruption_error: Optional[str] = None

    # ------------------------------------------------------------------ load

    def load(self):
        """Read optimizer_settings.json if it exists.

        Missing file is fine (fresh install) -- we start with the default
        shape and the bootstrap call will populate `characters` from
        CHARACTERS. JSON parse errors flag the file as corrupted; the
        manager then behaves like an empty store but does NOT write
        back over the broken file. Operator can fix or delete it.
        """
        self.corrupted = False
        self.corruption_error = None
        if not self.path.exists():
            return

        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            self._mark_corrupted(f"Failed to read: {exc}")
            return

        if not isinstance(data, dict):
            self._mark_corrupted("Root is not a JSON object")
            return

        # Future migrations: switch on `version`. v1 is the current schema.
        # We don't error on unknown versions -- we just keep going with
        # whatever fields we recognize.
        excluded = data.get("excluded_gear_chars", [])
        if not isinstance(excluded, list):
            excluded = []
        self.data["excluded_gear_chars"] = [str(x) for x in excluded]

        characters = data.get("characters", {})
        if not isinstance(characters, dict):
            characters = {}
        # Coerce keys to strings (JSON loads them as strings already, but be defensive)
        clean_chars: dict = {}
        for key, value in characters.items():
            if not isinstance(value, dict):
                continue
            clean_chars[str(key)] = value
        self.data["characters"] = clean_chars

        # Round 10: preserve any unknown top-level keys verbatim so newer
        # features (e.g. the `excluded_default_initialized` flag added
        # by the Optimizer tab's first-run-bootstrap path) don't get
        # silently dropped on load -> next write cycle. Anything we
        # don't explicitly recognize is carried forward as-is.
        for key, value in data.items():
            if key in ("version", "excluded_gear_chars", "characters"):
                continue
            self.data[key] = value

    def _mark_corrupted(self, reason: str):
        self.corrupted = True
        self.corruption_error = reason
        # Keep `self.data` at its empty default so callers don't get None.

    # ----------------------------------------------------------------- write

    def _write(self):
        """Persist current state. No-op if corrupted (don't overwrite broken file).

        Atomic write: stage to a `.tmp` sibling then rename. On filesystems
        where rename is atomic across the same directory (NTFS / ext4 / APFS
        all qualify), an interrupted write leaves either the old file intact
        or the new one in place -- never a half-written file.
        """
        if self.corrupted:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Always write the current schema version, even if we loaded an
        # older one (post-migration this is what we want; v1 is current).
        self.data["version"] = OPTIMIZER_SETTINGS_VERSION
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        tmp_path.replace(self.path)

    # -------------------------------------------------------- character ops

    def ensure_character(self, res_id, name: str = "") -> bool:
        """Make sure an entry exists for `res_id`. Returns True if newly added.

        `res_id` is accepted as int OR str -- normalized to str for the
        dict key. If the entry already exists and the name_hint differs
        from `name`, the name_hint is refreshed (cheap cosmetic update).
        Callers should only pass `name` when they actually know it.

        Does NOT persist on its own -- callers either batch via
        `bootstrap_known_characters()` (which writes once at the end) or
        rely on the set/setter calls below that auto-write.
        """
        key = str(res_id)
        if key in self.data["characters"]:
            entry = self.data["characters"][key]
            if name and entry.get("name_hint") != name:
                entry["name_hint"] = name
            return False
        self.data["characters"][key] = _fresh_character_settings(name_hint=name)
        return True

    def bootstrap_known_characters(self, characters_dict: dict) -> bool:
        """Walk the master CHARACTERS dict; ensure an entry per known res_id.

        Called at startup (after `load()`) and after any data reload that
        might surface a new character. Persists once at the end if anything
        changed. Returns True if the file was written.
        """
        changed = False
        for res_id, char_data in characters_dict.items():
            if char_data is None:
                continue  # res_id 0 is a "no character" sentinel in some tables
            name = char_data.get("name", "") if isinstance(char_data, dict) else ""
            if not name or name == "Unknown":
                # Skip placeholder entries -- they'll get a proper name later
                # and bootstrap will re-run then.
                continue
            if self.ensure_character(res_id, name):
                changed = True
        if changed:
            self._write()
        return changed

    # ------------------------------------------------ per-character getters

    def get_character_data(self, res_id) -> dict:
        """Return the full settings dict for a character.

        If `res_id` is not in the store, returns a fresh defaults dict
        (NOT linked to the store -- callers can mutate freely without
        affecting future lookups). This lets the UI render sensibly when
        a character is selected before being bootstrapped.
        """
        key = str(res_id)
        entry = self.data["characters"].get(key)
        if entry is None:
            return _fresh_character_settings()
        # Return a shallow copy of nested dicts/lists so callers can't
        # corrupt the stored state by mutating the return value.
        return {
            "name_hint": entry.get("name_hint", ""),
            "optimize_for_level": entry.get("optimize_for_level",
                DEFAULT_CHARACTER_SETTINGS["optimize_for_level"]),
            "extra_pct": entry.get("extra_pct", 0),
            "dot_pct": entry.get("dot_pct", 0),
            "atk_def_split": entry.get("atk_def_split", 0),
            "shielding_healing_weight": entry.get("shielding_healing_weight", 0),
            "force_main": dict(entry.get("force_main", DEFAULT_CHARACTER_SETTINGS["force_main"])),
            "have_at_least": dict(entry.get("have_at_least", DEFAULT_CHARACTER_SETTINGS["have_at_least"])),
            "sets_selected": list(entry.get("sets_selected", [])),
            "max_flex_slots": entry.get("max_flex_slots", 6),
            "set_effect_pct": entry.get("set_effect_pct",
                DEFAULT_CHARACTER_SETTINGS["set_effect_pct"]),
            "avg_card_dmg_pct": entry.get("avg_card_dmg_pct", 100),
            "avg_mult_buff_pct": entry.get("avg_mult_buff_pct", 0),
            "avg_add_buff_pct": entry.get("avg_add_buff_pct", 0),
            "element_override": entry.get("element_override", None),
        }

    def get(self, res_id, field: str, default=None):
        """Get a single field for a character. Auto-creates the entry if absent."""
        key = str(res_id)
        entry = self.data["characters"].get(key)
        if entry is None:
            return default if default is not None else DEFAULT_CHARACTER_SETTINGS.get(field)
        return entry.get(field, default if default is not None else DEFAULT_CHARACTER_SETTINGS.get(field))

    # ------------------------------------------------ per-character setters

    def set(self, res_id, field: str, value) -> bool:
        """Set a single field for a character. Persists immediately if changed.

        Returns True if the file was written, False if the call was a no-op
        (value unchanged or store is corrupted).
        """
        if self.corrupted:
            return False
        key = str(res_id)
        if key not in self.data["characters"]:
            self.data["characters"][key] = _fresh_character_settings()
        entry = self.data["characters"][key]
        if entry.get(field) == value:
            return False  # no-op; avoid noisy disk writes on idempotent UI ticks
        entry[field] = value
        self._write()
        return True

    def set_force_main(self, res_id, slot_key: str, checked: bool) -> bool:
        """Toggle one of the force-main checkbox flags."""
        if self.corrupted:
            return False
        key = str(res_id)
        if key not in self.data["characters"]:
            self.data["characters"][key] = _fresh_character_settings()
        fm = self.data["characters"][key].setdefault(
            "force_main", dict(DEFAULT_CHARACTER_SETTINGS["force_main"])
        )
        if fm.get(slot_key) == checked:
            return False
        fm[slot_key] = checked
        self._write()
        return True

    def set_have_at_least(self, res_id, stat: str, value: int) -> bool:
        """Update a single 'Have at least' threshold."""
        if self.corrupted:
            return False
        key = str(res_id)
        if key not in self.data["characters"]:
            self.data["characters"][key] = _fresh_character_settings()
        hal = self.data["characters"][key].setdefault(
            "have_at_least", dict(DEFAULT_CHARACTER_SETTINGS["have_at_least"])
        )
        if hal.get(stat) == value:
            return False
        hal[stat] = value
        self._write()
        return True

    def set_sets_selected(self, res_id, set_ids: list) -> bool:
        """Replace the entire 'selected sets' list for a character."""
        if self.corrupted:
            return False
        key = str(res_id)
        if key not in self.data["characters"]:
            self.data["characters"][key] = _fresh_character_settings()
        # Normalize: integers, sorted, deduplicated
        normalized = sorted({int(x) for x in set_ids})
        if self.data["characters"][key].get("sets_selected") == normalized:
            return False
        self.data["characters"][key]["sets_selected"] = normalized
        self._write()
        return True

    # ----------------------------------------------------------- global ops

    def get_excluded_gear_chars(self) -> list:
        """Return the list of res_id strings whose equipped gear should be skipped."""
        return list(self.data.get("excluded_gear_chars", []))

    def set_excluded_gear_chars(self, res_ids: list) -> bool:
        """Replace the entire excluded-gear list. Persists immediately."""
        if self.corrupted:
            return False
        normalized = sorted({str(x) for x in res_ids})
        if self.data.get("excluded_gear_chars") == normalized:
            return False
        self.data["excluded_gear_chars"] = normalized
        self._write()
        return True
