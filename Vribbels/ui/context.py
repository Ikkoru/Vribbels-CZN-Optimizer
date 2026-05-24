"""
Application context for dependency injection across UI tabs.

Provides shared state and services to all tabs without tight coupling.
"""

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from optimizer import GearOptimizer
    from capture import CaptureManager
    from config import AppConfig
    from ui.tabs import InventoryTab, HeroesTab, ScoringTab
    from preset_manager import PresetManager
    from character_preset_manager import CharacterPresetManager
    from level_data_manager import LevelDataManager
    from settings_manager import SettingsManager


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
        load_file_callback: Callback to open file dialog and load data () -> None
        load_data_callback: Callback to load data file (filepath: str) -> None
        switch_tab_callback: Callback to switch to a tab (tab_frame: tk.Widget) -> None
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
    optimizer: 'GearOptimizer'
    capture_manager: 'CaptureManager'
    config: 'AppConfig'

    # Styling
    colors: dict
    style: ttk.Style

    # Callbacks
    load_file_callback: Callable[[], None]
    load_data_callback: Callable[[str], None]
    switch_tab_callback: Callable[[tk.Widget], None]
    refresh_callback: Optional[Callable[[], None]] = None
    inventory_tab: Optional['InventoryTab'] = None
    heroes_tab: Optional['HeroesTab'] = None
    scoring_tab: Optional['ScoringTab'] = None
    preset_manager: Optional['PresetManager'] = None
    character_preset_manager: Optional['CharacterPresetManager'] = None
    # User-confirmed (exp, level) checkpoints — augments the built-in
    # exp tables in constants.py via apply_to_constants(). Initialized at
    # program startup; the right-click "Add confirmed level" flow in the
    # Combatants tab writes through this manager.
    level_data_manager: Optional['LevelDataManager'] = None
    # General-purpose persistent key-value store for user preferences
    # that don't fit into the other managers' shapes. Currently holds
    # last_selected_character (Combatants tab row to restore on refresh
    # and program restart).
    settings_manager: Optional['SettingsManager'] = None
