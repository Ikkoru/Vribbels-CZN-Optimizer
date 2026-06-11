"""
LevelDataManager: stores user-confirmed (exp, level) checkpoints and
augments the built-in CHARACTER_EXP_TABLE / PARTNER_EXP_TABLE with them.

Background
==========
The exp tables in game_data/constants.py are partially documented from
snapshots and partially educated guesses with round-number values. The
only way to firm up the guesses is to anchor them: a user with a character
at known in-game level X reads off the snapshot exp value and confirms
"this character is at level X with Y exp" -- one new firm data point.

This module persists those confirmations to disk and feeds them back into
the constants module at startup so all level lookups reflect them.

Storage
=======
Path:  <base_dir>/presets/level_data.json
Shape: {
  "characters": [
    {"name": "Amir", "res_id": 1017, "exp": 320000, "level": 50,
     "confirmed_at": "2026-05-11"},
    ...
  ],
  "partners": [
    {"name": "Anteia", "res_id": 20008, "exp": 181000, "level": 50, ...},
    ...
  ]
}

Notes on conflict resolution
============================
When a user checkpoint disagrees with the built-in table at the same level,
the user data wins -- it's directly observed in-game. When two user
checkpoints disagree at the same level (e.g. you confirm two different
characters as level 50 with different exp values), the LATER entry wins.
This is a known limitation; in practice in-game thresholds are constant
across characters of the same kind (we've verified that for partners
across grades 4, 4.5, 5), so disagreements should be rare and usually
indicate a typo to be corrected by editing the JSON.
"""

import json
from datetime import date
from pathlib import Path
from typing import Optional


class LevelDataManager:
    """Loads, saves, and augments level checkpoint data."""

    def __init__(self, base_dir: Path):
        """
        Args:
            base_dir: project base dir. The 'settings' folder is used
                      (created on first save) for the level_data.json file.
        """
        self.presets_dir = Path(base_dir) / "settings"
        self.data_file = self.presets_dir / "level_data.json"

        # category -> list of checkpoint dicts
        self.checkpoints: dict = {"characters": [], "partners": []}
        self.corrupted = False
        self.corruption_error: Optional[str] = None

    # ----- loading / saving -----

    def load(self):
        """Load from disk. Clean state if the file doesn't exist yet."""
        self.checkpoints = {"characters": [], "partners": []}
        self.corrupted = False
        self.corruption_error = None

        if not self.data_file.exists():
            return

        try:
            raw = self.data_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            self.corrupted = True
            self.corruption_error = f"Cannot read level_data.json: {e}"
            return

        if not isinstance(data, dict):
            self.corrupted = True
            self.corruption_error = "level_data.json root must be an object"
            return

        for category in ("characters", "partners"):
            entries = data.get(category, [])
            if not isinstance(entries, list):
                continue  # tolerate partial / malformed sections
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                # Minimum fields: exp (int) and level (int). Others optional.
                if "exp" not in entry or "level" not in entry:
                    continue
                try:
                    entry["exp"] = int(entry["exp"])
                    entry["level"] = int(entry["level"])
                except (TypeError, ValueError):
                    continue
                self.checkpoints[category].append(entry)

    def _write(self):
        """Persist to disk via atomic temp-then-replace."""
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.data_file.with_suffix(self.data_file.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.checkpoints, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.data_file)

    # ----- adding checkpoints -----

    def add_checkpoint(self, category: str, *, res_id: int, name: str,
                       exp: int, level: int):
        """Record a confirmed (exp, level) data point and persist.

        Args:
            category: 'characters' or 'partners'.
            res_id:   the in-game resource id of the character/partner.
            name:     display name (for human readability in the JSON).
            exp:      snapshot exp value.
            level:    user-confirmed in-game level (1-62 for characters,
                      1-60 for partners; not validated here -- the dialog
                      layer is the right place to enforce bounds).
        """
        if category not in self.checkpoints:
            raise ValueError(f"unknown category: {category!r}")
        entry = {
            "name": name,
            "res_id": res_id,
            "exp": int(exp),
            "level": int(level),
            "confirmed_at": date.today().isoformat(),
        }
        self.checkpoints[category].append(entry)
        self._write()

    # ----- augmentation -----

    def augmented_table(self, base_table: list, category: str) -> list:
        """Merge user checkpoints into a base exp table.

        For each level appearing in either source, the user value wins if
        present; otherwise the base table's value is used. Returns a new
        list sorted by level (which equals sorted-by-exp for monotonic
        tables, but we sort by level explicitly to be robust to user data
        that might temporarily violate monotonicity during data entry).

        Args:
            base_table: list of (exp, level) tuples from constants.py.
            category:   'characters' or 'partners'.
        """
        by_level: dict[int, int] = {lvl: exp for exp, lvl in base_table}
        for entry in self.checkpoints.get(category, []):
            by_level[entry["level"]] = entry["exp"]

        merged = sorted(
            ((exp, lvl) for lvl, exp in by_level.items()),
            key=lambda t: t[1],
        )
        return merged

    def apply_to_constants(self):
        """Install augmented tables into game_data.constants so all level
        lookups (anywhere in the program) reflect user-confirmed data.

        The constants module exposes _active_character_exp_table and
        _active_partner_exp_table as module-level rebindable references;
        we rewrite those rather than mutating the base CHARACTER_EXP_TABLE
        / PARTNER_EXP_TABLE constants, so the originals stay pristine.
        """
        # Imported here, not at module top, to avoid a circular import:
        # constants is in game_data/ and prefers not to know about us.
        from game_data import constants

        constants._active_character_exp_table = self.augmented_table(
            constants.CHARACTER_EXP_TABLE, "characters"
        )
        constants._active_partner_exp_table = self.augmented_table(
            constants.PARTNER_EXP_TABLE, "partners"
        )
