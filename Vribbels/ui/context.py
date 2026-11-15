"""
Application context for dependency injection across UI tabs.

Provides shared state and services to all tabs without tight coupling.
"""

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    from optimizer import GearOptimizer
    from capture import CaptureManager
    from config import AppConfig
    from ui.tabs import InventoryTab, HeroesTab, ScoringTab, OptimizerTab
    from preset_manager import PresetManager
    from character_preset_manager import CharacterPresetManager
    from settings_manager import SettingsManager
    from optimizer_settings_manager import OptimizerSettingsManager
    from log_presets_manager import LogPresetsManager
    from checklist_manager import ChecklistManager


@dataclass
class AppContext:
    """
    Application context providing shared state and services to all tabs.

    This acts as a dependency injection container, allowing tabs to access
    shared resources without tight coupling to the main GUI class.

    Attributes:
        root: Main Tk window
        notebook: Main ttk.Notebook containing all tabs
        optimizer: GearOptimizer instance for data and optimization
        capture_manager: CaptureManager for capture operations
        config: AppConfig instance for user preferences
        colors: Color palette dictionary
        style: ttk.Style instance for theming

        # Callbacks for cross-tab communication
        load_data_callback: Callback to load data file (filepath: str) -> None
        refresh_callback: Optional callback to refresh displays after data load
        inventory_tab: Optional reference to InventoryTab for cross-tab refresh
        heroes_tab: Optional reference to HeroesTab for cross-tab refresh
        scoring_tab: Optional reference to ScoringTab; the heroes_tab uses
            this to refresh the preset listbox's assignment markers
            after a character preset is changed via the Combatants-tab
            combobox. Optional -- heroes_tab no-ops cleanly when None.
    """

    # Core widgets
    root: tk.Tk
    notebook: ttk.Notebook

    # Services
    optimizer: GearOptimizer
    capture_manager: CaptureManager
    config: AppConfig

    # Styling
    colors: dict
    style: ttk.Style

    # Callbacks
    load_data_callback: Callable[[str], None]
    refresh_callback: Callable[[], None] | None = None
    inventory_tab: InventoryTab | None = None
    heroes_tab: HeroesTab | None = None
    scoring_tab: ScoringTab | None = None
    # Used by the Setup & Settings tab's Restore Defaults flow to refresh the
    # Optimizer tab's displayed per-combatant settings after a restore.
    # Optional -- callers must check for None.
    optimizer_tab: OptimizerTab | None = None
    preset_manager: PresetManager | None = None
    character_preset_manager: CharacterPresetManager | None = None
    # General-purpose persistent key-value store for user preferences
    # that don't fit into the other managers' shapes.
    settings_manager: SettingsManager | None = None
    # Find and read the game client again once its folder is set: the
    # app's `reread_game_client`. None where nothing wired it (a check
    # building a tab alone).
    reread_game_client: Callable[[], None] | None = None
    # Per-character optimizer-tab settings (Important Settings, Have at
    # Least minimums, selected sets, etc). Indexed by res_id so character
    # renames don't lose data. See optimizer_settings_manager.py.
    optimizer_settings_manager: OptimizerSettingsManager | None = None
    # Per-combatant selection flags behind the Capture tab's Log Presets
    # checklist (which assigned presets participate in the "[LIVE]
    # Upgraded" Highest-Potential lines). See log_presets_manager.py.
    log_presets_manager: LogPresetsManager | None = None

    # Which Checklist shop products the user tracks. See
    # checklist_manager.py.
    checklist_manager: ChecklistManager | None = None
    # Where `stats_history.py` keeps what it read out of old debug
    # captures: the user's settings folder.
    stats_dir: Path | None = None
    # The game facts that ship with the program, read beside the
    # account's own -- see shared_facts.py. None reads as none shipped,
    # which is what a tab built without the app gets.
    shared_facts: dict | None = None
    # Where the account's own facts are read from for the Share Game
    # Data panel: the folder holding `settings/` and `snapshots/`.
    program_dir: Path | None = None
    # Re-renders the LAST "[LIVE] Upgraded" capture-log line against the
    # current Log Presets selection. Set by the main GUI; the Capture
    # tab calls it after a checklist toggle. Optional -- callers must
    # check for None.
    recompute_upgrade_line_callback: Callable[[], None] | None = None
