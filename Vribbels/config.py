"""
AppConfig: attribute-style access to the configuration values consumers
read via `context.config` (`server_region`, `optimizer_workers`).

The values live in settings/settings.json, owned by SettingsManager --
this module does no file I/O of its own. Reads return the store's
current value; attribute assignment persists immediately through
SettingsManager.set (atomic tmp-then-replace, unchanged-value writes
skipped). Legacy config.json files are absorbed into settings.json by
SettingsManager.apply_layout at startup and ignored afterwards.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from settings_manager import SettingsManager


class AppConfig:
    """Attribute-style view over SettingsManager for config values.

    Constructed once at startup (after SettingsManager has loaded and
    apply_layout has absorbed any legacy config.json) and shared with
    every tab through AppContext.config.
    """

    def __init__(self, settings_manager: "SettingsManager"):
        self._settings = settings_manager

    @property
    def server_region(self) -> str:
        value = self._settings.get("server_region", "global")
        return value if isinstance(value, str) and value else "global"

    @server_region.setter
    def server_region(self, value: str) -> None:
        self._settings.set("server_region", str(value))

    @property
    def optimizer_workers(self) -> int:
        # 0 = auto (cpu_count - 1, leaving a core for the UI / game
        # client), 1 = single-thread path, N = N capped to cpu_count --
        # resolution lives in optimizer/parallel.py. File-only (no UI
        # control): edit settings/settings.json while the program is
        # closed.
        try:
            return int(self._settings.get("optimizer_workers", 0))
        except (TypeError, ValueError):
            return 0

    @optimizer_workers.setter
    def optimizer_workers(self, value) -> None:
        self._settings.set("optimizer_workers", int(value))
