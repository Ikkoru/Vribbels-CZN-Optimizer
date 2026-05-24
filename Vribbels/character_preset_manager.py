"""
CharacterPresetManager - Per-character scoring preset assignments.

Persists which custom Gear Score preset each character uses for their personal
GS calculation. Stored as JSON in the same `presets/` folder as `presets.json`.

File format:
    {
        "assignments": {
            "Suzuna": "DPS Heavy",
            "Iroha":  null,        // null = default preset (all weights 1.0)
            "12345":  "Tank Build" // unknown character, keyed by ID-as-string
        }
    }
"""

import json
import shutil
from pathlib import Path
from typing import Optional


class CharacterPresetManager:
    """Loads, saves, and manages per-character preset assignments."""

    def __init__(self, base_dir: Path):
        """
        Args:
            base_dir: The program's base directory. Stored alongside presets.json.
        """
        self.presets_dir = Path(base_dir) / "presets"
        self.assignments_file = self.presets_dir / "character_preset.json"

        self.assignments: dict = {}     # character_name -> preset_name | None
        self.corrupted: bool = False
        self.corruption_error: Optional[str] = None

    # ----- loading -----

    def load(self):
        """Load assignments from disk. Sets corrupted=True on any structural problem."""
        self.assignments = {}
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

        for name, preset in data["assignments"].items():
            if not isinstance(name, str) or not name.strip():
                self._mark_corrupted("Character key must be a non-empty string.")
                return
            if preset is not None and not isinstance(preset, str):
                self._mark_corrupted(
                    f"Character '{name}': preset must be a string or null."
                )
                return

        self.assignments = dict(data["assignments"])

    def _mark_corrupted(self, reason: str):
        self.corrupted = True
        self.corruption_error = reason
        self.assignments = {}

    # ----- queries -----

    def is_corrupted(self) -> bool:
        return self.corrupted

    def get_preset_for(self, character_name: str) -> Optional[str]:
        """Return the assigned preset name, or None if default/unassigned."""
        return self.assignments.get(character_name)

    # ----- mutations (no-op while corrupted, except quarantine) -----

    def set_preset_for(self, character_name: str, preset_name: Optional[str]):
        """Assign a preset (or None for default) to a character and persist."""
        if self.corrupted:
            raise RuntimeError("Character preset file is corrupted; quarantine it first.")
        self.assignments[character_name] = preset_name
        self._write()

    def ensure_character(self, character_name: str) -> bool:
        """Add a new character with default (None) assignment if not yet seen.
        Returns True if a new entry was created."""
        if self.corrupted:
            return False
        if character_name in self.assignments:
            return False
        self.assignments[character_name] = None
        self._write()
        return True

    def ensure_characters(self, character_names) -> bool:
        """Bulk version of ensure_character. Single write. Returns True if any added."""
        if self.corrupted:
            return False
        added = False
        for name in character_names:
            if name not in self.assignments:
                self.assignments[name] = None
                added = True
        if added:
            self._write()
        return added

    def remove_assignments_to(self, preset_name: str) -> int:
        """Reset every character currently assigned to `preset_name` back to default.
        Returns the number of assignments cleared. Single write."""
        if self.corrupted:
            return 0
        cleared = 0
        for k, v in list(self.assignments.items()):
            if v == preset_name:
                self.assignments[k] = None
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
        self.assignments = {}

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
        """Persist current state. Creates the presets directory if needed."""
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        data = {"assignments": self.assignments}
        tmp_path = self.assignments_file.with_suffix(
            self.assignments_file.suffix + ".tmp"
        )
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        tmp_path.replace(self.assignments_file)
