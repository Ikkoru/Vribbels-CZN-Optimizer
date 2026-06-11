"""
Application configuration and user preferences management.

Round 11 follow-up: the config file moved from `<base>/config.json` into
the user-state folder `<base>/settings/config.json` so all writable user
data lives together. On the first run after the move, `load_config()`
migrates an existing legacy `config.json` into the new location and
removes the original.

Path resolution mirrors the `_user_data_dir()` helper in
czn_optimizer_gui.py: in a frozen build (PyInstaller) the writable base
is `sys.executable.parent`; in dev it's the directory containing this
module. Using `__file__` directly would have aimed at PyInstaller's
read-only _MEIPASS in frozen builds, silently dropping every save.
"""

import json
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class AppConfig:
    """Application configuration and user preferences."""
    server_region: str = "global"  # Default to global server


def _writable_base_dir() -> Path:
    """Return the writable base directory.

    Frozen build: next to the .exe. Dev: directory containing this file.
    Matches `_user_data_dir()` in czn_optimizer_gui.py -- kept inline here
    to avoid a circular import (config.py is imported VERY early).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


_BASE_DIR = _writable_base_dir()
CONFIG_FILE = _BASE_DIR / "settings" / "config.json"
_LEGACY_CONFIG_FILE = _BASE_DIR / "config.json"


def _migrate_legacy_config_if_needed() -> None:
    """Move `<base>/config.json` -> `<base>/settings/config.json` once.

    Idempotent: if the new file already exists, leaves the legacy file
    alone (treat the new file as authoritative). If only the legacy file
    exists, moves it into settings/ and creates settings/ if needed. If
    neither exists, this is a no-op.

    Best-effort: any I/O failure is swallowed so the caller still gets a
    usable AppConfig (it'll fall back to defaults on load).
    """
    try:
        if CONFIG_FILE.exists():
            # New location wins. If the legacy file is still around for
            # some reason, leave it -- the user can delete manually.
            return
        if not _LEGACY_CONFIG_FILE.exists():
            return
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_LEGACY_CONFIG_FILE), str(CONFIG_FILE))
    except Exception:
        pass


def load_config() -> AppConfig:
    """Load configuration from file, or return defaults if not found.

    Triggers a one-time migration from the legacy `<base>/config.json`
    location into `<base>/settings/config.json` before reading.
    """
    _migrate_legacy_config_if_needed()
    if not CONFIG_FILE.exists():
        return AppConfig()

    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
        return AppConfig(**data)
    except Exception:
        # If config is corrupted, return defaults
        return AppConfig()


def save_config(config: AppConfig):
    """Save configuration to file. Creates settings/ if needed."""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(asdict(config), f, indent=2)
    except Exception:
        pass  # Silently fail if can't save
