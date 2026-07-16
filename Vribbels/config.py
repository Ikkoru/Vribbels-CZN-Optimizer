"""
Application configuration and user preferences management.

Stored at `<base>/settings/config.json`. A legacy copy at
`<base>/config.json` is moved into settings/ on first load.

Path resolution: in a frozen build (PyInstaller) the writable base is
`sys.executable.parent`; in dev it's the directory containing this
module. Do NOT use `__file__` directly for the frozen case -- it
resolves into PyInstaller's read-only `_MEIPASS` temp dir and every
save is silently lost when the program exits.
"""

import json
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, asdict, fields


@dataclass
class AppConfig:
    """Application configuration and user preferences."""
    server_region: str = "global"
    # Optimizer worker processes (plan.md Phase C). 0 = auto
    # (cpu_count - 1, leaving a core for the UI / game client), 1 =
    # single-thread legacy path, N = N capped to cpu_count. File-only
    # for now (no UI control); read fresh at every Start, so editing
    # settings/config.json applies without restarting. Parallelism only
    # kicks in on runs large enough to amortize worker startup -- see
    # PARALLEL_MIN_COMBOS in optimizer/parallel.py.
    optimizer_workers: int = 0


def _writable_base_dir() -> Path:
    """Frozen build: next to the .exe. Dev: directory containing this
    file. Duplicates `_user_data_dir()` in czn_optimizer_gui.py because
    config.py is imported too early for that import to be safe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


_BASE_DIR = _writable_base_dir()
CONFIG_FILE = _BASE_DIR / "settings" / "config.json"
_LEGACY_CONFIG_FILE = _BASE_DIR / "config.json"


def _migrate_legacy_config_if_needed() -> None:
    """Move `<base>/config.json` -> `<base>/settings/config.json` once.

    Idempotent; if the new file exists the legacy one is ignored.
    Best-effort: I/O failures are swallowed and load falls back to
    defaults.
    """
    try:
        if CONFIG_FILE.exists():
            return
        if not _LEGACY_CONFIG_FILE.exists():
            return
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_LEGACY_CONFIG_FILE), str(CONFIG_FILE))
    except Exception:
        pass


def load_config() -> AppConfig:
    """Load configuration, or return defaults if missing/corrupt.

    Also materializes missing fields INTO the file: a config.json
    written before a field existed (or no config.json at all) gets the
    new field written back with its default, so users can discover and
    edit settings like `optimizer_workers` without consulting docs.
    Unknown keys already in the file (e.g. from a newer version) are
    preserved by the write-back.
    """
    _migrate_legacy_config_if_needed()
    if not CONFIG_FILE.exists():
        cfg = AppConfig()
        save_config(cfg)
        return cfg

    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
        # Ignore unknown keys instead of letting AppConfig(**data) raise
        # TypeError -- a config written by a newer version (or a stray
        # key) would otherwise trip the blanket except below and silently
        # reset EVERY setting to defaults, discarding valid fields like
        # server_region.
        known = {f.name for f in fields(AppConfig)}
        cfg = AppConfig(**{k: v for k, v in data.items() if k in known})
        if any(name not in data for name in known):
            # File predates one or more fields -- write the merged view
            # back so the new defaults become visible/editable. Unknown
            # keys from `data` are kept (a newer version's file survives
            # a downgrade); known keys are refreshed from the dataclass.
            try:
                merged = {**data, **asdict(cfg)}
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(merged, f, indent=2)
            except Exception:
                pass
        return cfg
    except Exception:
        return AppConfig()


def save_config(config: AppConfig):
    """Save configuration. Creates settings/ if needed. Silent on failure."""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(asdict(config), f, indent=2)
    except Exception:
        pass
