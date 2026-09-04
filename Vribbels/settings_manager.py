"""
SettingsManager: persistent key-value store for user preferences.

Stores at <base_dir>/settings/settings.json as a flat JSON object. Used
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
            base_dir: project base dir. The 'settings' folder is used
                      (created on first save) for the settings.json file.
        """
        self.presets_dir = Path(base_dir) / "settings"
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

    # Canonical key order for settings.json, with "#N" section markers.
    # Applied on startup so the file reads as a documented settings sheet
    # rather than an arbitrary key dump, and so every key is visible to a
    # user editing it by hand instead of appearing only once first set.
    #
    # The order survives every later write: load() keeps the parsed dict
    # as-is, Python dicts preserve insertion order, and set() on an
    # existing key updates in place. Markers must have DISTINCT keys --
    # json.loads keeps only the last of any duplicate, so four literal
    # "#" keys would collapse into one on the first write.
    LAYOUT = (
        ("#1", "_Multi-core Settings_"),
        ("optimizer_workers", 0),
        ("#2", "_Debug Settings_"),
        ("debug_perf_log", False),
        ("#3", "_Settings with UI_"),
        ("server_region", "global"),
        ("optimizer_min_gear_level", 4),
        ("upgrade_log_ignore_atkdef_mismatch", True),
        ("upgrade_log_ignore_element_mismatch", True),
        ("upgrade_log_ignore_dps_hp", True),
        ("upgrade_log_ignore_dps_ego", True),
        ("optimizer_ignore_offelement", True),
        ("inventory_use_upgrade_log_filters", False),
        ("combatants_show_missing", False),
        ("materials_include_generic_combatant", False),
        ("materials_include_generic_partner", False),
        ("materials_include_generic_stones", False),
        ("#4", "_Memory_"),
        ("first_launch_done", False),
        ("update_last_checked", ""),
        ("update_latest_version", ""),
        ("selected_preset", ""),
    )

    def apply_layout(self, legacy_config_files=()) -> None:
        """Materialise the canonical key set in LAYOUT order, folding in
        any legacy config.json.

        Legacy config.json files hold `server_region` and
        `optimizer_workers`; their values are adopted for any key not
        already in settings.json (so nobody loses their region or
        worker count), but a value already in settings.json always
        wins. Once absorbed, config.json is ignored -- the file is left
        on disk.

        Keys not in LAYOUT are appended rather than dropped, so an
        unrecognised key (hand-added, or written by a newer version)
        survives. Writes only when something actually changed.
        """
        legacy: dict = {}
        for path in legacy_config_files:
            try:
                path = Path(path)
                if not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Earlier files in the list win; they're passed
                    # most-canonical-first.
                    for key, value in data.items():
                        legacy.setdefault(key, value)
            except Exception:
                continue

        before = list(self.settings.items())
        ordered: dict = {}
        for key, default in self.LAYOUT:
            if key.startswith("#"):
                ordered[key] = default
            elif key in self.settings:
                ordered[key] = self.settings[key]
            elif key in legacy:
                ordered[key] = legacy[key]
            else:
                ordered[key] = default
        for key, value in self.settings.items():
            if key not in ordered:
                ordered[key] = value

        if list(ordered.items()) != before:
            self.settings = ordered
            self._write()

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
