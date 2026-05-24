"""
SettingsManager: persistent key-value store for user preferences.

Stores at <base_dir>/presets/settings.json as a flat JSON object. Used
for state that doesn't fit into the per-preset / per-character /
per-checkpoint stores: e.g., "which character was selected last", which
might later expand to window geometry, last open tab, etc.

Reads are in-memory; writes go through an atomic tmp-then-rename to disk
so the file is always either the old version or the new version, never
a half-written intermediate.
"""

import json
from pathlib import Path
from typing import Any, Optional


class SettingsManager:
    """Tiny persisted key-value store. One JSON object on disk."""

    def __init__(self, base_dir: Path):
        """
        Args:
            base_dir: project base dir. The 'presets' folder is reused
                      (created on first save) for the settings.json file.
        """
        self.presets_dir = Path(base_dir) / "presets"
        self.settings_file = self.presets_dir / "settings.json"
        self.settings: dict = {}
        self.corrupted = False
        self.corruption_error: Optional[str] = None

    def load(self):
        """Load from disk. Clean state if the file doesn't exist yet.
        On any structural problem, sets corrupted=True and leaves the
        in-memory dict empty (so callers see "no saved settings" rather
        than partial / wrong data)."""
        self.settings = {}
        self.corrupted = False
        self.corruption_error = None

        if not self.settings_file.exists():
            return

        try:
            raw = self.settings_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            self.corrupted = True
            self.corruption_error = f"Cannot read settings.json: {e}"
            return

        if not isinstance(data, dict):
            self.corrupted = True
            self.corruption_error = "settings.json root must be a JSON object"
            return

        self.settings = data

    def _write(self):
        """Persist to disk via atomic tmp-then-replace."""
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_file.with_suffix(self.settings_file.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.settings_file)

    def get(self, key: str, default: Any = None) -> Any:
        """Look up a key; return default if absent."""
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a key and persist to disk.

        No-op (no disk write) when the value is unchanged -- callers can
        hammer this on rapid-fire events like keyboard navigation through
        a list without worrying about disk thrashing. Disk write failures
        are swallowed so a single bad save can't break the running app;
        the in-memory state still reflects the change for the current
        session.
        """
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        try:
            self._write()
        except Exception:
            pass
