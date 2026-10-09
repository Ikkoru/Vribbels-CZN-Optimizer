"""
PresetManager - Persistent storage for user-defined gear scoring weight presets.

Presets are stored as JSON in the 'settings' folder alongside the program.

File format (current):
    {
        "presets": {
            "preset name": {"Flat ATK": 1.0, "ATK%": 1.5, ...},
            ...
        }
    }

The currently-selected preset name lives in settings.json, managed by
SettingsManager, NOT in this file. This split exists so the shipping
defaults bundle (presets.json) doesn't carry per-user state -- a bundled
file that included "selected_preset" would either (a) override a returning
user's choice every install or (b) need to be stripped before bundling.
Keeping the selection in settings.json sidesteps both.

Legacy format (pre-migration, still readable):
    {
        "selected_preset": "name or null",
        "presets": { ... }
    }

`load()` reads the legacy "selected_preset" key when present and copies
it into the SettingsManager (only if that doesn't already have a value);
subsequent `_write()` drops the key, so the file becomes the current
format on the next save.
"""

import json
from pathlib import Path
from typing import Any, Optional

from json_file import write_json


# Why a save is refused while the file is unread. A file that will not
# parse never gets this far -- `settings_repair` mends it or sets it
# aside at launch -- so this one would not open.
UNREAD = ("presets.json could not be read when the program started, so "
          "nothing is saved to it. Restart the program once it can be.")

# 11 stats currently supported in scoring (must match scoring_tab.py)
SUPPORTED_STATS = [
    "Flat ATK", "ATK%",
    "Flat DEF", "DEF%",
    "Flat HP", "HP%",
    "CRate", "CDmg",
    "Ego", "Extra DMG%",
    "DoT%",
]


def preset_problem(name, weights) -> Optional[str]:
    """Why presets.json could not hold this preset, or None."""
    if not isinstance(name, str) or not name.strip():
        return "Preset name must be a non-empty string."
    if not isinstance(weights, dict):
        return f"Preset '{name}' must be an object of stat weights."
    for stat, val in weights.items():
        if not isinstance(stat, str):
            return f"Preset '{name}' has non-string stat key."
        # Reject bools (which are isinstance int in Python)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return f"Preset '{name}', stat '{stat}': weight must be a number."
    return None


def structure_problem(data) -> Optional[str]:
    """Why `PresetManager.load` would refuse `data`, or None. What
    `settings_repair` holds a repaired file to as well."""
    if not isinstance(data, dict):
        return "Top-level JSON must be an object."
    if "presets" not in data:
        return "Missing 'presets' key."
    if not isinstance(data["presets"], dict):
        return "'presets' must be an object."
    for name, weights in data["presets"].items():
        problem = preset_problem(name, weights)
        if problem:
            return problem
    sel = data.get("selected_preset")
    if sel is not None and not isinstance(sel, str):
        return "'selected_preset' must be a string or null."
    return None


class PresetManager:
    """Loads, saves, and manages user-defined scoring weight presets."""

    def __init__(self, base_dir: Path, settings_manager: Optional[Any] = None):
        """
        Args:
            base_dir: The program's base directory. The 'presets' folder will
                      be created here if it doesn't exist.
            settings_manager: Optional SettingsManager instance that backs the
                      `selected_preset` field. When provided, the active
                      selection lives in settings.json (not presets.json).
                      Pass None for standalone use (e.g. tests / scripts) --
                      selection then lives in a local in-memory variable
                      and goes nowhere on disk.
        """
        self.presets_dir = Path(base_dir) / "settings"
        self.presets_file = self.presets_dir / "presets.json"

        self.settings_manager = settings_manager
        self.presets: dict = {}                 # name -> {stat: weight}
        # Fallback storage for selected_preset when no SettingsManager is
        # wired up. Only the property below reads it; production calls
        # always go through settings_manager. Set during load() either
        # from a legacy presets.json field or to None.
        self._legacy_selected: Optional[str] = None
        self.corrupted: bool = False
        self.corruption_error: Optional[str] = None

    # ----- selected_preset: backed by SettingsManager when available -----

    @property
    def selected_preset(self) -> Optional[str]:
        """Name of the currently-selected preset, or None.

        Reads from SettingsManager['selected_preset'] when wired up;
        otherwise from the in-memory fallback populated by load() from
        the legacy presets.json field.
        """
        if self.settings_manager is not None:
            val = self.settings_manager.get("selected_preset")
            return val if isinstance(val, str) else None
        return self._legacy_selected

    # ----- loading -----

    def load(self):
        """Load presets from disk. On any structural problem, sets corrupted=True.

        Migration: if the file is in the legacy format (has a top-level
        "selected_preset" key), copy that value into SettingsManager if
        the settings store doesn't already have one. The legacy key is
        then dropped from presets.json on the next `_write()`.
        """
        self.presets = {}
        self._legacy_selected = None
        self.corrupted = False
        self.corruption_error = None

        if not self.presets_file.exists():
            return  # No file yet — clean state.

        try:
            raw_text = self.presets_file.read_text(encoding="utf-8")
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

        problem = structure_problem(data)
        if problem:
            self._mark_corrupted(problem)
            return

        self.presets = {name: {k: float(v) for k, v in weights.items()}
                        for name, weights in data["presets"].items()}

        # selected_preset: present in the legacy format, absent in the
        # current one.
        sel = data.get("selected_preset")

        # Resolve the selection. Three cases:
        #   (a) SettingsManager already has a value: use that, ignore file.
        #   (b) SettingsManager wired but empty + file has a legacy value
        #       referencing an existing preset: migrate it. We also trigger
        #       a rewrite so the legacy key disappears from presets.json,
        #       leaving it in the current (settings-backed) format.
        #   (c) No SettingsManager: fall back to in-memory `_legacy_selected`.
        if self.settings_manager is not None:
            current = self.settings_manager.get("selected_preset")
            if not isinstance(current, str) or not current:
                if sel and sel in self.presets:
                    try:
                        self.settings_manager.set("selected_preset", sel)
                    except Exception:
                        pass
                    # Clean up the legacy field from presets.json so the
                    # file format matches the docstring going forward.
                    # Best-effort: if it fails, the field stays and the
                    # next save_preset/delete_presets will strip it.
                    try:
                        self._write()
                    except Exception:
                        pass
        else:
            if sel and sel in self.presets:
                self._legacy_selected = sel
            # else: name doesn't exist anymore; leave fallback as None.

    def _mark_corrupted(self, reason: str):
        self.corrupted = True
        self.corruption_error = reason
        self.presets = {}
        self._legacy_selected = None

    # ----- queries -----

    def is_corrupted(self) -> bool:
        return self.corrupted

    def has_preset(self, name: str) -> bool:
        return name in self.presets

    def get_preset(self, name: str) -> Optional[dict]:
        """
        Return weights for a preset, padded with 1.0 for any missing supported stat.
        Returns None if the preset doesn't exist.
        """
        if name not in self.presets:
            return None
        raw = self.presets[name]
        return {stat: raw.get(stat, 1.0) for stat in SUPPORTED_STATS}

    def get_preset_names(self) -> list:
        """Return preset names sorted alphabetically (case-insensitive)."""
        return sorted(self.presets.keys(), key=str.lower)

    # ----- mutations (all blocked while corrupted) -----

    def save_preset(self, name: str, weights: dict, set_selected: bool = True):
        """Save (or overwrite) a preset and persist. Raises if corrupted."""
        if self.corrupted:
            raise RuntimeError(UNREAD)
        clean = {stat: float(weights.get(stat, 1.0)) for stat in SUPPORTED_STATS}
        self.presets[name] = clean
        if set_selected:
            self._set_selected_internal(name)
        self._write()

    def delete_presets(self, names: list):
        """Delete one or more presets and persist. Raises if corrupted."""
        if self.corrupted:
            raise RuntimeError(UNREAD)
        for n in names:
            self.presets.pop(n, None)
        if self.selected_preset in names:
            self._set_selected_internal(None)
        self._write()

    def set_selected(self, name: Optional[str]):
        """Set the currently-active preset name and persist (no-op if corrupted).

        Persistence target is SettingsManager when wired up; otherwise the
        in-memory fallback gets updated and presets.json is rewritten.
        """
        if self.corrupted:
            return
        if name is not None and name not in self.presets:
            return
        self._set_selected_internal(name)
        # When the SettingsManager backs the field, no presets.json write
        # is needed -- the setting persisted itself. Only the standalone
        # path (no settings_manager) needs to write presets.json.
        if self.settings_manager is None:
            self._write()

    def _set_selected_internal(self, name: Optional[str]):
        """Route a new selection to the right backing store. Used by
        save_preset / delete_presets / set_selected to avoid duplicating
        the SettingsManager-vs-fallback decision."""
        if self.settings_manager is not None:
            try:
                self.settings_manager.set("selected_preset", name)
            except Exception:
                pass
        else:
            self._legacy_selected = name

    # ----- internals -----

    def _write(self):
        """Persist current state to disk. Creates the presets directory if needed.

        Writes only the presets dict -- selected_preset lives in settings.json
        when a SettingsManager is wired up, so it's intentionally absent here.
        """
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        data = {"presets": self.presets}
        write_json(self.presets_file, data, ensure_ascii=False)
