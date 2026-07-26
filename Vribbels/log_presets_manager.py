"""
LogPresetsManager - per-combatant selection flags for the Capture tab's
"Log Presets" checklist.

The Capture tab's "[LIVE] Upgraded" log lines report a fragment's
Highest Potential under the presets currently assigned to combatants.
This manager remembers which combatants participate: a combatant whose
flag is False contributes its assigned preset neither to the checklist's
checked state nor to the potential computation.

Stored as JSON in `settings/log_presets.json` (pure user state, no
bundled default):

    {
        "version": 1,
        "selected": {
            "1017": true,     # res_id (string) -> include this
            "1055": false     #   combatant's assigned preset
        }
    }

Keyed by res_id (string) so preset renames and reassignments never lose
the user's choice. Combatants are added with selected=true the first
time the program sees them (captured) or knows them (present in
CHARACTERS). Absent ids read as selected (the default).
"""

import json
from pathlib import Path


LOG_PRESETS_VERSION = 1


class LogPresetsManager:
    """Loads and persists the per-combatant Log Presets selection flags."""

    def __init__(self, base_dir: Path):
        self.settings_dir = Path(base_dir) / "settings"
        self.file = self.settings_dir / "log_presets.json"
        self.selected: dict = {}   # res_id (str) -> bool

    def load(self):
        """Read flags from disk. An unreadable file behaves like a fresh
        one (everything selected) rather than blocking the tab."""
        self.selected = {}
        if not self.file.exists():
            return
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except Exception:
            return
        raw = data.get("selected", {}) if isinstance(data, dict) else {}
        if isinstance(raw, dict):
            self.selected = {str(k): bool(v) for k, v in raw.items()}

    def is_selected(self, res_id) -> bool:
        """Absent ids default to selected."""
        return self.selected.get(str(res_id), True)

    def set_selected(self, res_ids, value: bool):
        """Set the flag on several res_ids at once. Single write."""
        changed = False
        for rid in res_ids:
            rid = str(rid)
            if rid not in self.selected or self.selected[rid] != bool(value):
                self.selected[rid] = bool(value)
                changed = True
        if changed:
            self._write()

    def ensure_ids(self, res_ids) -> bool:
        """Add unseen res_ids with the default (selected). Single write.
        Returns True if anything was added."""
        added = False
        for rid in res_ids:
            rid = str(rid)
            if rid and rid != "0" and rid not in self.selected:
                self.selected[rid] = True
                added = True
        if added:
            self._write()
        return added

    def _write(self):
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        data = {"version": LOG_PRESETS_VERSION, "selected": self.selected}
        tmp = self.file.with_suffix(self.file.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.file)
