#!/usr/bin/env python3
"""
Vribbels - CZN Memory Fragment Tool
A Fribbels-inspired gear management and optimization tool for Chaos Zero Nightmare.
Includes integrated data capture and setup functionality.


Project orientation (for future maintainers / future Claude)
=============================================================

Top-level layout
----------------
  czn_optimizer_gui.py      Tk root + tab orchestration + single-instance
                            lock. Main entry point. Owns the AppContext
                            and instantiates the managers (preset,
                            character_preset, optimizer_settings,
                            level_data, settings).
  config.py                 AppConfig -- attribute-style view over
                            SettingsManager for server_region and
                            optimizer_workers (context.config).
  preset_manager.py         User scoring presets (named weight sets).
  character_preset_manager  Per-character preset assignments. v2 schema
                            keyed by res_id with parallel name_hints.
  optimizer_settings_manager Per-character Optimizer-tab config plus the
                            global excluded_gear_chars list.
  level_data_manager.py     User-confirmed (exp, level) checkpoints
                            that augment the exp tables at startup.
  settings_manager.py       Generic persistent key-value store
                            (settings.json): server_region,
                            optimizer_workers, last selected
                            character/preset, debug flags.
  log_presets_manager.py    Per-combatant flags behind the Capture tab's
                            Log Presets checklist (which assigned presets
                            the "[LIVE] Upgraded" Highest-Potential lines
                            compare).
  defaults_sync.py          Three-stage reconciler that runs in
                            OptimizerGUI.__init__ BEFORE any manager
                            loads: maintainer bootstrap, new-user
                            bootstrap, tombstone-aware update merge.
                            See settings/.defaults_sync.json for the
                            tombstone sidecar.
  version.py                Version string.

Subpackages
-----------
  capture/      Data-capture machinery (mitmproxy add-on + hosts edits +
                temp-cert mgmt). manager.py contains the addon template
                that handles live piece create / equip / unequip / swap /
                upgrade / delete events.
  game_data/    Static game-rule data:
                  constants.py   experience tables, stats, rarities, slots,
                                 affection bonuses, growth stones
                  characters.py  per-character base stats, attributes,
                                 classes, potential-tree assignments
                  partners.py    per-partner data + class-based base stats
  models/       In-memory dataclasses (MemoryFragment + the math helpers
                that compute GS and Potential).
  optimizer/    optimizer.py -- the snapshot-to-CharacterInfo pipeline
                and the layered Final ATK/DEF/HP damage formula.
  ui/           context.py (AppContext shared between tabs) + tabs/
                (one file per visible tab in the application).

Where to look when changing X
-----------------------------
  GS / Potential formula             models/memory_fragment.py
  Damage / Final stats formula       optimizer/optimizer.py
  Adding a new preset stat           preset_manager.py + scoring_tab
  Character data (stats, potential)  game_data/characters.py
  Partner data                       game_data/partners.py
  EXP -> level conversion            game_data/constants.py
  Live inventory updates             capture/manager.py (addon template)
  Inventory display / filtering      ui/tabs/inventory_tab.py
  Per-character preset assignment    ui/tabs/heroes_tab.py
  Right-click level checkpoint flow  heroes_tab._prompt_level_checkpoint
                                     + level_data_manager.py

Data flow (one user action -> displayed result)
-----------------------------------------------
  in-game action (e.g. equip a Fragment)
    -> mitmproxy intercepts the WebSocket message
    -> capture/manager.py addon parses + updates piece_items
    -> _save_data() writes memory_fragments_*.json
    -> user clicks Refresh in the app (or it auto-detects)
    -> optimizer reads the JSON, builds character_info
    -> tabs read character_info via AppContext
    -> render

Conventions
-----------
  - Stat names use the display strings ("Flat ATK", "ATK%", "CRate", ...)
    everywhere user-facing. Raw enum keys ("S_ATK_INC_ADD_OUT") appear
    only at the data-parsing boundary in models/.
  - Anything in /settings/*.json is user-modifiable and reread on
    startup; bundled defaults live in /default_settings/ (tracked) and
    are merged into /settings/ by defaults_sync. Any file outside those
    two trees is hardcoded data.
  - capture/manager.py is the ONLY file with strict ASCII requirements
    (Windows cp932 codec can't write Unicode). All other source files
    use Python's default UTF-8 encoding and can contain anything.

Single-instance lock
--------------------
main() binds a localhost socket on port 53117 (IANA dynamic range) as
the cheapest cross-platform single-instance check. Hold the returned
socket in a module-level reference; releasing it frees the lock.
"""

import json
import os
import sys
import itertools
import socket
import subprocess
import shutil
import ctypes
import re
import threading
import webbrowser
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont

# === GAME DATA CHECKS ===
# MUST come before the game_data import below and before any project
# import that reaches it: a syntax error in a data file is raised while
# that module is being imported, so this is the only point at which it
# can still be reported as a message box rather than a traceback. Keep
# this above the imports if they are ever reordered.
from game_data_validator import check_data_files
if not check_data_files():
    sys.exit(1)

# === GAME DATA IMPORTS ===
from game_data import *
from models import *
from capture import *
from optimizer import GearOptimizer
from config import AppConfig
from ui import AppContext, MaterialsTab, SetupTab, CaptureTab, InventoryTab, OptimizerTab, HeroesTab, ScoringTab, AboutTab
# Used to augment "[LIVE] Upgraded" log lines with the post-upgrade
# Highest Pot. range across all currently-defined presets (see
# _drain_pending_upgrade_lines below).
from models.memory_fragment import compute_gs_bounds, compute_fragment_potential
# Reconciles bundled defaults in `default_settings/` with the user's
# `settings/` folder. Must run BEFORE any manager loads.
from defaults_sync import sync_defaults


def _user_data_dir() -> Path:
    """Return the directory that holds user-modifiable state
    (settings/, snapshots/, etc.).

    Frozen build (PyInstaller):
        Next to the .exe (sys.executable.parent). Files written here
        persist across runs.

    Dev / source run:
        The directory containing this file -- i.e. Vribbels/.

    Why this matters: in a frozen build, `__file__` resolves to a path
    inside PyInstaller's `_MEIPASS` temp dir, which is wiped on exit.
    Using `__file__`-based paths for user data in a frozen build would
    silently lose every save the moment the program closes. Capture's
    BASE_DIR already handles this for snapshots/; this helper extends
    the same treatment to settings/, etc.

    Bundled read-only defaults (`default_settings/`) resolve differently:
    see defaults_sync.resolve_defaults_dir.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


class MultiSelectListbox(tk.Frame):
    """A frame containing a listbox with multi-select capability"""
    def __init__(self, parent, items, height=4, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.listbox = tk.Listbox(self, selectmode=tk.MULTIPLE, height=height,
                                  exportselection=False, bg="#363650", fg="#cdd6f4",
                                  selectbackground="#3b6ea5", selectforeground="#cdd6f4",
                                  highlightthickness=0)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        
        for item in items:
            self.listbox.insert(tk.END, item)
    
    def get_selected(self) -> list[str]:
        indices = self.listbox.curselection()
        return [self.listbox.get(i) for i in indices]
    
    def select_items(self, items: list[str]):
        self.listbox.selection_clear(0, tk.END)
        for i in range(self.listbox.size()):
            if self.listbox.get(i) in items:
                self.listbox.selection_set(i)


class OptimizerGUI:
    def __init__(self):
        # AppConfig is created in setup_ui, after SettingsManager loads
        # and absorbs any legacy config.json (apply_layout). Nothing
        # reads context.config before the tabs are built.
        self.config = None

        self.root = tk.Tk()
        # Hide the window before anything else touches it. tk.Tk() maps the
        # window immediately, so without this the user watches an empty
        # white frame for as long as construction + auto_load take, and
        # then watches the UI draw itself widget by widget as Tk works
        # through its map queue -- including panels whose geometry settles
        # late and visibly jump into place. Everything is built off-screen
        # and _reveal_window() (end of __init__) shows it once, complete.
        self._hide_until_ready()
        self.root.title("Vribbels CZN Optimizer (Ikkoru)")
        self.root.geometry("1550x1000")
        self.root.minsize(1300, 800)

        self.colors = {
            "bg": "#1e1e2e", "bg_light": "#2a2a3e", "bg_lighter": "#363650",
            "fg": "#cdd6f4", "fg_dim": "#6c7086", "accent": "#89b4fa",
            "green": "#a6e3a1", "red": "#f38ba8", "yellow": "#f9e2af", "purple": "#cba6f7",
            "orange": "#FF8C00", "select": "#3b6ea5",
        }

        self.root.configure(bg=self.colors["bg"])
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()

        self.optimizer = GearOptimizer()

        # Initialize capture manager
        self.capture_manager = CaptureManager(
            output_folder=OUTPUT_DIR,
            log_callback=lambda msg, tag=None: self.capture_tab_instance.capture_log_msg(msg, tag) if hasattr(self, 'capture_tab_instance') else None,
            status_callback=lambda status: self.capture_tab_instance.capture_status_label.config(text=status) if hasattr(self, 'capture_tab_instance') else None,
            live_update_callback=lambda: self.root.after(0, self._handle_live_update)
        )

        # Create AppContext for UI tabs
        self.app_context = AppContext(
            root=self.root,
            notebook=None,  # Set after notebook created in setup_ui
            optimizer=self.optimizer,
            capture_manager=self.capture_manager,
            colors=self.colors,
            style=self.style,
            load_file_callback=self.load_file,
            load_data_callback=self.load_data,
            switch_tab_callback=self._switch_to_tab,
            config=self.config
        )

        import perf_log
        import time as _time

        _t = _time.perf_counter()
        self.setup_ui()
        perf_log.log("startup:build_tabs", secs=_time.perf_counter() - _t)

        _t = _time.perf_counter()
        self.auto_load()
        perf_log.log("startup:auto_load", secs=_time.perf_counter() - _t)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        _t = _time.perf_counter()
        self._reveal_window()
        perf_log.log("startup:reveal", secs=_time.perf_counter() - _t)
        # Only now that the window is up and mapped can a modal dialog
        # be shown safely, so the game-data report waits until here.
        self._report_data_problems()
        _t0 = getattr(self, "_startup_t0", None)
        if _t0 is not None:
            perf_log.log("startup:TOTAL", secs=_time.perf_counter() - _t0)

    def _hide_until_ready(self):
        """Make the window invisible for the duration of startup.

        Prefers full transparency to withdraw(): a transparent window is
        still MAPPED, so its children realize their true sizes and any
        startup code that measures winfo_width() -- the Optimizer tab's
        exclude checklist flow layout does -- gets real numbers rather
        than falling back to requested ones and re-flowing later, in
        view. Falls back to withdraw() wherever per-window alpha isn't
        supported.
        """
        self._hidden_via = "withdraw"
        try:
            self.root.attributes("-alpha", 0.0)
            self._hidden_via = "alpha"
        except tk.TclError:
            self.root.withdraw()

    def _reveal_window(self):
        """Show the finished window, once.

        Runs full update() passes -- not just update_idletasks() -- while
        the window is still invisible. The difference is the whole fix:
        geometry runs in idle handlers, but the <Configure> events that
        geometry generates, and the redraws that follow them, are ordinary
        events. Draining only idle work therefore leaves the layout one
        pass short and parts of the window never painted, so the window
        appears mid-settle and finishes assembling in view.

        Concretely, the toolbar's help text re-wraps on <Configure>; that
        changes the toolbar's height, which shifts everything in the body
        below it. Until that event is processed, the body is laid out for
        a taller toolbar.

        Repeats until the root and notebook stop changing requested size,
        with a floor of three passes (the first pass triggers the re-wrap,
        the second re-lays out, the third repaints) and a ceiling so a
        layout that oscillates can't hang startup.
        """
        # Give the OPTIMIZER tab one mapped layout pass while still
        # invisible, if it isn't already the tab about to be shown. A tab
        # that has never been displayed has never had its <Configure>
        # handlers run, so it settles -- visibly -- the first time the user
        # opens it: the Optimizer tab's help text re-wraps, which changes the
        # toolbar height and shifts every panel below it.
        #
        # ONLY that one tab. Cycling all eight cost 2.6-3.8s of startup
        # (measured) -- more than every other phase combined -- because each
        # select() + update() forces a full layout and draw of a tab the user
        # may never open. The Optimizer tab is the only one with a known
        # Configure-driven layout dependency; if another turns out to shift,
        # add it here by name rather than going back to cycling everything.
        import time as _time
        import perf_log
        _t = _time.perf_counter()
        try:
            originally_selected = self.notebook.select()
            optimizer_tab_id = str(self.optimizer_tab_instance.frame)
            if optimizer_tab_id != originally_selected:
                self.notebook.select(optimizer_tab_id)
                self.root.update()
                self.notebook.select(originally_selected)
        except (tk.TclError, AttributeError):
            pass
        perf_log.log("startup:reveal.pre_settle_tabs",
                     secs=_time.perf_counter() - _t)

        _t = _time.perf_counter()
        last = None
        passes = 0
        pass_secs = []
        for i in range(10):
            _p = _time.perf_counter()
            self.root.update()
            pass_secs.append(round(_time.perf_counter() - _p, 3))
            passes = i + 1
            size = (
                self.root.winfo_reqwidth(), self.root.winfo_reqheight(),
                self.notebook.winfo_reqwidth(), self.notebook.winfo_reqheight(),
            )
            if i >= 2 and size == last:
                break
            last = size
        perf_log.log("startup:reveal.settle_loop",
                     secs=_time.perf_counter() - _t, passes=passes,
                     per_pass=pass_secs)
        if self._hidden_via == "alpha":
            self.root.attributes("-alpha", 1.0)
        else:
            self.root.deiconify()
        self._take_foreground()

    def _take_foreground(self):
        """Bring the window to the front on first show.

        Windows refuses to let a process raise a window when the foreground
        lock belongs to someone else. Launching from an Explorer window and
        declining the UAC prompt leaves that lock with Explorer, so the
        window maps BEHIND the folder it was started from -- and clicking any
        other window before declining releases the lock, which is exactly why
        that works around it. Briefly flagging the window topmost is the
        standard way to bypass the restriction without actually staying
        always-on-top; the flag is cleared on the next idle pass.
        """
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after_idle(
                lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except tk.TclError:
            pass

    def configure_styles(self):
        self.style.configure(".", background=self.colors["bg"], foreground=self.colors["fg"])
        self.style.configure("TFrame", background=self.colors["bg"])
        self.style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["fg"])
        self.style.configure("TButton", background=self.colors["bg_light"], foreground=self.colors["fg"], padding=5)
        self.style.map("TButton", background=[("active", self.colors["bg_lighter"])])
        self.style.configure("TCombobox", fieldbackground=self.colors["bg_lighter"], background=self.colors["bg_lighter"],
                             foreground=self.colors["fg"], selectbackground=self.colors["select"],
                             selectforeground=self.colors["fg"])
        self.style.map("TCombobox", fieldbackground=[("readonly", self.colors["bg_lighter"])], 
                       foreground=[("readonly", self.colors["fg"])])
        self.style.configure("TCheckbutton", background=self.colors["bg"], foreground=self.colors["fg"])
        self.style.map("TCheckbutton", background=[("active", self.colors["bg_lighter"])],
                       foreground=[("active", self.colors["fg"])])
        # Compact checkbutton for the Optimizer tab's toolbar status
        # cluster: zero padding keeps that row short enough for the
        # cluster to fit inside the toolbar's existing height (see the
        # cluster's comment in optimizer_tab.setup_ui). Colors etc.
        # fall back to the TCheckbutton settings above.
        self.style.configure("Compact.TCheckbutton", padding=0)
        self.style.configure("TLabelframe", background=self.colors["bg"])
        self.style.configure("TLabelframe.Label", background=self.colors["bg"], foreground=self.colors["accent"])
        self.style.configure("TScale", background=self.colors["bg"], troughcolor=self.colors["bg_light"])
        self.style.configure("TNotebook", background=self.colors["bg"])
        self.style.configure("TNotebook.Tab", background=self.colors["bg_light"], foreground=self.colors["fg"], padding=[10, 5])
        self.style.map("TNotebook.Tab", background=[("selected", self.colors["bg_lighter"])])
        self.style.configure("Treeview", background=self.colors["bg_light"], foreground=self.colors["fg"],
                             fieldbackground=self.colors["bg_light"], rowheight=24)
        self.style.configure("Treeview.Heading", background=self.colors["bg_lighter"], foreground=self.colors["fg"])
        self.style.map("Treeview.Heading", background=[("active", self.colors["select"])],
                       foreground=[("active", self.colors["fg"])])
        self.style.map("Treeview", background=[("selected", self.colors["select"])],
                       foreground=[("selected", self.colors["fg"])])

    def setup_ui(self):
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        # Original behavior: opened ko-fi.com in the browser. Replaced with the
        # same messagebox used by the About tab's Support Development button.
        # kofi_btn = tk.Button(top_bar, text="Support on Ko-Fi",
        #                     command=lambda: webbrowser.open("https://ko-fi.com/H2H21PHYKW"),
        #                     bg="#72a4f2", fg="white", font=("Segoe UI", 9, "bold"),
        #                     relief=tk.FLAT, padx=10, pady=3, cursor="hand2")
        # kofi_btn.pack(side=tk.RIGHT, padx=5)

        def _show_donation_message():
            messagebox.showinfo(
                "Support Development",
                "Currently not accepting donations.\n\n"
                "If you wish to instead donate to the original creator of this project, "
                "feel free to do so at:\nhttps://ko-fi.com/H2H21PHYKW"
            )

        kofi_btn = tk.Button(top_bar, text="Support on Ko-Fi",
                            command=_show_donation_message,
                            bg="#72a4f2", fg="white", font=("Segoe UI", 9, "bold"),
                            relief=tk.FLAT, padx=10, pady=3, cursor="hand2")
        kofi_btn.pack(side=tk.RIGHT, padx=5)
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Update AppContext with notebook reference
        self.app_context.notebook = self.notebook

        # Instantiate the managers BEFORE creating any tab so each tab can
        # access them via self.context. All four share the `settings/` folder
        # under the user data dir (see _user_data_dir at module scope -- it
        # redirects writes to a persistent location in frozen builds instead
        # of PyInstaller's read-only _MEIPASS).
        from preset_manager import PresetManager
        from character_preset_manager import CharacterPresetManager
        from level_data_manager import LevelDataManager
        from settings_manager import SettingsManager
        from optimizer_settings_manager import OptimizerSettingsManager
        from log_presets_manager import LogPresetsManager
        import perf_log
        import time as _time

        # Startup phase timers. Only ~0.19s of a ~2.5s launch was accounted
        # for by the tab refreshes, so these split the rest into the four
        # places it can actually be: manager loading, tab construction, the
        # snapshot load, and the reveal settle. Module import time is NOT
        # covered here -- use `python -X importtime` for that.
        _t_start = _time.perf_counter()
        # Shared with __init__, which times the later phases and the total.
        self._startup_t0 = _t_start

        program_dir = _user_data_dir()
        # Reconcile bundled defaults vs the user's settings/ BEFORE any
        # manager loads (see defaults_sync.py). Failure is non-fatal;
        # managers would just see empty files and behave like a fresh
        # install. Frozen builds read defaults from _MEIPASS; the user's
        # writable state lives next to the exe.
        user_settings_dir = program_dir / "settings"
        if getattr(sys, "frozen", False):
            bundle_root = Path(getattr(sys, "_MEIPASS", program_dir))
            defaults_dir = bundle_root / "default_settings"
        else:
            defaults_dir = program_dir / "default_settings"
        try:
            sync_defaults(user_settings_dir, defaults_dir)
        except Exception:
            pass

        # SettingsManager FIRST so it can be passed to PresetManager.
        # PresetManager uses it as the canonical store for `selected_preset`
        # (was previously inside presets.json, which made it impossible to
        # ship as a bundled default without polluting user state).
        self.settings_manager = SettingsManager(program_dir)
        self.settings_manager.load()

        self.preset_manager = PresetManager(
            program_dir, settings_manager=self.settings_manager
        )
        self.preset_manager.load()
        self.character_preset_manager = CharacterPresetManager(program_dir)
        self.character_preset_manager.load()
        # Level data manager: stores user-confirmed (exp, level) checkpoints
        # and rewrites constants._active_*_exp_table so all level lookups
        # see the augmented values. Must be applied BEFORE the optimizer
        # builds character info (which calls get_level_from_exp).
        self.level_data_manager = LevelDataManager(program_dir)
        self.level_data_manager.load()
        self.level_data_manager.apply_to_constants()
        # Optimizer settings manager: per-character optimizer-tab state
        # (Important Settings sliders, Have at Least minimums, selected
        # sets, set-effect %, Average Buff fields, etc). Keyed by res_id
        # so character renames don't lose data. Bootstrapping walks
        # CHARACTERS and adds a default entry for every known character
        # that doesn't have one yet -- so new characters added to
        # characters.py automatically get optimizer settings on the next
        # program start.
        self.optimizer_settings_manager = OptimizerSettingsManager(program_dir)
        self.optimizer_settings_manager.load()
        self.optimizer_settings_manager.bootstrap_known_characters(CHARACTERS)
        # Log Presets flags: per-combatant participation in the Capture
        # tab's Upgraded-line Highest-Potential comparison. Every known
        # character is ensured at startup (captured-but-unknown ids get
        # ensured at each data load); new ids default to selected.
        self.log_presets_manager = LogPresetsManager(program_dir)
        self.log_presets_manager.load()
        self.log_presets_manager.ensure_ids(str(rid) for rid in CHARACTERS.keys())
        # Fold any legacy config.json into settings.json and materialise
        # the canonical key order (SettingsManager.LAYOUT). Both historical
        # locations are offered, settings/ first since that's the one
        # config.json was migrated to previously.
        try:
            from pathlib import Path as _Path
            _base = _Path(program_dir)
            self.settings_manager.apply_layout((
                _base / "settings" / "config.json",
                _base / "config.json",
            ))
        except Exception:
            pass

        # Attribute-style config view over settings.json (server_region,
        # optimizer_workers). Created after apply_layout so legacy
        # config.json values are already absorbed; shared with every tab
        # via context.config.
        self.config = AppConfig(self.settings_manager)
        self.app_context.config = self.config

        # Diagnostics logging is opt-in and off by default: set
        # "debug_perf_log": true in settings/settings.json to record startup
        # phases, optimize runs and refresh timings to settings/perf_log.txt.
        # Disabled, no file is created and the timing wrappers cost nothing.
        perf_log.configure(
            program_dir,
            enabled=bool(
                getattr(self, "settings_manager", None)
                and self.settings_manager.get("debug_perf_log", False)
            ),
        )
        self._start_hang_watchdog(program_dir)
        self._start_data_validation()
        perf_log.log("startup:managers", secs=_time.perf_counter() - _t_start)
        self.app_context.preset_manager = self.preset_manager
        self.app_context.character_preset_manager = self.character_preset_manager
        self.app_context.level_data_manager = self.level_data_manager
        self.app_context.settings_manager = self.settings_manager
        self.app_context.optimizer_settings_manager = self.optimizer_settings_manager
        self.app_context.log_presets_manager = self.log_presets_manager
        self.app_context.recompute_upgrade_line_callback = (
            self.recompute_last_upgrade_line
        )
        # Give the optimizer a reference to settings_manager so its
        # calculate_build_stats can look up the per-character "Optimize
        # at" level override. Optional dependency -- the optimizer falls
        # back to level-60-baseline behavior when this is None.
        self.optimizer.settings_manager = self.settings_manager

        # ---- Create tab instances (order is unrelated to display order) ----
        self.optimizer_tab_instance = OptimizerTab(self.notebook, self.app_context)
        self.optimizer_tab = self.optimizer_tab_instance.get_frame()

        self.inventory_tab_instance = InventoryTab(self.notebook, self.app_context)
        self.inventory_tab = self.inventory_tab_instance.get_frame()

        self.materials_tab_instance = MaterialsTab(self.notebook, self.app_context)
        self.materials_tab = self.materials_tab_instance.get_frame()

        self.heroes_tab_instance = HeroesTab(self.notebook, self.app_context)
        self.heroes_tab = self.heroes_tab_instance.get_frame()

        self.capture_tab_instance = CaptureTab(self.notebook, self.app_context)
        self.capture_tab = self.capture_tab_instance.get_frame()

        self.setup_tab_instance = SetupTab(self.notebook, self.app_context)
        self.setup_tab = self.setup_tab_instance.get_frame()

        # Set cross-tab refs BEFORE ScoringTab is created — it uses both at init.
        self.app_context.inventory_tab = self.inventory_tab_instance
        self.app_context.heroes_tab = self.heroes_tab_instance
        # Setup tab's Restore Defaults flow refreshes the Optimizer tab
        # through this ref after restoring per-combatant settings.
        self.app_context.optimizer_tab = self.optimizer_tab_instance

        self.scoring_tab_instance = ScoringTab(self.notebook, self.app_context)
        self.scoring_tab = self.scoring_tab_instance.get_frame()
        # Heroes tab uses this to refresh the preset listbox's assignment
        # markers after a Combatants-tab preset change. Set after creation;
        # the heroes_tab queries via the context and no-ops if None.
        self.app_context.scoring_tab = self.scoring_tab_instance
        # The Memory Fragments tab names the active scoring weights, which
        # only the Scoring tab knows -- and it didn't exist when that label
        # was built. Set it now, so it reads correctly even on a launch
        # with no snapshot to load.
        self.inventory_tab_instance.refresh_active_preset_label()

        self.about_tab_instance = AboutTab(self.notebook, self.app_context)
        self.about_tab = self.about_tab_instance.get_frame()

        # ---- Add tabs to notebook in display order ----
        # Optimizer | Memory Fragments | Gear Score | Combatants | Materials |
        #   Capture | Setup | About
        self.notebook.add(self.optimizer_tab, text="Optimizer")
        self.notebook.add(self.inventory_tab, text="Memory Fragments")
        self.notebook.add(self.scoring_tab, text="Gear Score")
        self.notebook.add(self.heroes_tab, text="Combatants")
        self.notebook.add(self.materials_tab, text="Materials")
        self.notebook.add(self.capture_tab, text="Capture")
        self.notebook.add(self.setup_tab, text="Setup")
        self.notebook.add(self.about_tab, text="About")

        # First-launch default: switch to the Setup tab so the user lands
        # on the proxy/cert installation flow before trying to use the
        # rest of the app (which is useless without captured data). The
        # "first_launch_done" flag in settings.json is set after this
        # fires once, so subsequent launches keep the notebook's default
        # tab (Optimizer, leftmost). Clearing settings.json -- e.g. as a
        # "reset to factory state" -- correctly re-triggers this.
        if not self.settings_manager.get("first_launch_done"):
            self.notebook.select(self.setup_tab)
            self.settings_manager.set("first_launch_done", True)

    def _start_hang_watchdog(self, program_dir):
        """With `debug_perf_log` on, dump every thread's stack to
        settings/hang_traceback.txt every 30 seconds.

        For diagnosing an unresponsive window: whatever call is blocking
        the main thread appears at the bottom of the main thread's stack,
        which beats inferring it from symptoms. Repeats, so a healthy run
        just produces a series of dumps parked in mainloop -- that itself
        is the "startup finished, we're idle and fine" reading.

        The file handle is kept on the instance because faulthandler
        writes to it from a watchdog thread; letting it be collected
        would close it mid-dump.
        """
        try:
            import perf_log
            if not perf_log.is_enabled():
                return
            import faulthandler
            path = Path(program_dir) / "settings" / "hang_traceback.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            self._hang_dump_file = open(path, "w", encoding="utf-8")
            faulthandler.dump_traceback_later(
                30, repeat=True, file=self._hang_dump_file, exit=False
            )
        except Exception:
            pass

    def _start_data_validation(self):
        """Kick off the game-data value checks on a worker thread.

        Runs alongside the rest of startup rather than in it: the checks
        walk every character, partner and set, and nothing about them
        needs to finish before the window appears. `_report_data_problems`
        (called after the reveal) shows the result.
        """
        self._data_problems = None

        def work():
            try:
                from game_data_validator import find_data_problems
                problems = find_data_problems()
            except Exception as exc:                     # noqa: BLE001
                problems = [f"the data check itself failed: "
                            f"{type(exc).__name__}: {exc}"]
            self._data_problems = problems

        threading.Thread(target=work, daemon=True).start()

    def _report_data_problems(self, attempts: int = 0):
        """Show the game-data check's findings, once the worker has them.

        Polls rather than being pushed from the worker so the dialog is
        guaranteed to appear on the UI thread, after the window is up --
        a modal dialog raised during startup would sit behind a
        transparent window with nothing to parent it to. Gives up quietly
        after ~10s; a check that slow is not worth a dialog.
        """
        problems = getattr(self, "_data_problems", None)
        if problems is None:
            if attempts < 100:
                self.root.after(
                    100, lambda: self._report_data_problems(attempts + 1))
            return
        if not problems:
            return
        try:
            from game_data_validator import format_problem_report
            messagebox.showwarning("Game data problems",
                                   format_problem_report(problems))
        except Exception:
            pass

    def _switch_to_tab(self, tab_frame: tk.Widget):
        """Switch notebook to the specified tab frame."""
        self.notebook.select(tab_frame)

    def on_close(self):
        """Handle window close event."""
        if self.capture_manager.is_capturing():
            if messagebox.askyesno("Confirm Exit", "Capture is still running. Stop and exit?"):
                self.capture_tab_instance.stop_capture()
            else:
                return
        self.root.destroy()

    def auto_load(self):
        latest = self.capture_manager.get_latest_capture()
        if latest:
            self.load_data(str(latest))

    def load_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Memory Fragment Snapshot",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir="snapshots"
        )
        if filepath:
            self.load_data(filepath)

    def load_data(self, filepath: str):
        try:
            self.optimizer.load_data(filepath)

            # Ensure every character we just loaded has a row in
            # character_preset.json (default = no preset). New IDs only.
            self._ensure_characters_in_preset_file()

            # Update optimizer tab UI
            self.optimizer_tab_instance.refresh_after_load()

            # Update other tabs. Memory Fragments and Combatants are
            # deliberately NOT refreshed here: apply_active_weights() below
            # refreshes both itself, so doing it here too rebuilt each of
            # them twice per load -- and the first pass rendered with the
            # previous scores anyway, since the re-score happens inside
            # apply_active_weights. (The live-update path has always relied
            # on apply_active_weights alone for the same reason.)
            self.inventory_tab_instance.populate_set_filters()
            self.materials_tab_instance.refresh_materials()

            # Re-score fragments using the currently-active scoring weights
            # (preset or custom), so loading fresh data doesn't wipe them out.
            # This also refreshes the Memory Fragments and Combatants tabs.
            import time as _time
            import perf_log as _perf
            _t = _time.perf_counter()
            self.scoring_tab_instance.apply_active_weights()
            _perf.log("rescore+refresh_tabs",
                      secs=_time.perf_counter() - _t,
                      fragments=len(self.optimizer.fragments))

            # The Log Presets checklist derives from preset assignments,
            # which ensure-new-characters above may have extended.
            if hasattr(self, "capture_tab_instance"):
                self.capture_tab_instance.refresh_log_presets()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")
            import traceback
            traceback.print_exc()

    def _handle_live_update(self):
        """Handle live update from capture — reload latest snapshot and refresh UI.

        Re-entrancy guard: a burst of WebSocket messages (e.g. equip +
        unequip from one in-game action) can fire this callback while a
        previous invocation is still mid-refresh; the nested call would
        walk half-mutated optimizer state and trigger cascading layout
        passes. Nested calls are dropped — the outer call reads the
        latest snapshot off disk, so anything written in between is
        picked up by that read.
        """
        if getattr(self, "_in_live_update", False):
            return
        self._in_live_update = True
        try:
            latest = self.capture_manager.get_latest_capture()
            if latest:
                # Summary of what the Combatants tab shows, taken BEFORE
                # the reload. Compared against the same summary afterwards
                # so a rebuild of that tab -- the most expensive refresh in
                # this path -- is skipped for events that don't touch it,
                # e.g. upgrading or forging a fragment nobody has equipped.
                before = self._combatants_signature()
                try:
                    self.optimizer.load_data(str(latest))
                    self._ensure_characters_in_preset_file()
                    # Optimizer tab needs its hero combo + exclude-heroes list
                    # repopulated so newly-captured characters appear there too
                    # (the manual load_data path also calls this; the live path
                    # used to skip it, which was the reason the Optimizer tab
                    # appeared stale after capture).
                    self.optimizer_tab_instance.refresh_after_load()
                    self.inventory_tab_instance.populate_set_filters()
                    self.materials_tab_instance.refresh_materials()
                    # apply_active_weights re-scores and refreshes the
                    # Memory Fragments tab, and the Combatants tab unless
                    # told the latter has nothing new to show. An
                    # unavailable signature counts as changed.
                    after = self._combatants_signature()
                    self.scoring_tab_instance.apply_active_weights(
                        refresh_heroes=(before is None or after is None
                                        or before != after)
                    )
                    self.capture_tab_instance.refresh_log_presets()
                except Exception:
                    pass  # Silently ignore reload errors during live monitoring

            # Drain any deferred upgrade log lines that arrived while the
            # addon's stdout was being read. Must happen AFTER the reload so
            # the upgraded fragment is in optimizer.fragments with its new
            # level/upgrades when we look it up.
            self._drain_pending_upgrade_lines()
        finally:
            self._in_live_update = False

    def _combatants_signature(self):
        """HeroesTab.display_signature(), or None if it can't be taken.
        None means "assume it changed" -- a stale Combatants tab is worse
        than a redundant refresh."""
        try:
            return self.heroes_tab_instance.display_signature()
        except Exception:
            return None

    def _drain_pending_upgrade_lines(self):
        """Pull queued "[LIVE] Upgraded ... [pid=N]" lines off the capture
        manager's queue, look each fragment up in optimizer.fragments to
        compute its post-upgrade Highest Pot. range, and emit the augmented
        log line to the Capture tab.

        Highest Pot. semantics here match the Memory Fragments tab's
        column: the min low / max high across every preset currently in
        PresetManager. If no presets exist (only the implicit default),
        a single (low, high) is computed against the default weights.
        """
        if not hasattr(self.capture_manager, "pending_upgrade_lines"):
            return
        import queue
        while True:
            try:
                line = self.capture_manager.pending_upgrade_lines.get_nowait()
            except queue.Empty:
                break
            augmented = self._augment_upgrade_log(line)
            if hasattr(self, "capture_tab_instance"):
                # log_upgrade_msg (not capture_log_msg): records the line's
                # extent so Log Presets toggles can rewrite it in place.
                self.capture_tab_instance.log_upgrade_msg(
                    f"[proxy] {augmented}", "info"
                )

    def _selected_log_preset_names(self) -> list:
        """Distinct preset names assigned to at least one combatant whose
        Log Presets flag is selected (the Capture tab checklist). Sorted.
        Assignments to since-deleted presets are skipped. Combatants
        absent from log_presets.json count as selected (the default)."""
        cpm = self.character_preset_manager
        pm = self.preset_manager
        lpm = getattr(self, "log_presets_manager", None)
        if cpm is None or pm is None or cpm.is_corrupted():
            return []
        names = set()
        for rid, preset in cpm.assignments_by_id.items():
            if not preset or not pm.has_preset(preset):
                continue
            if lpm is None or lpm.is_selected(rid):
                names.add(preset)
        return sorted(names)

    def _upgrade_potentials_suffix(self, fragment) -> str:
        """The ". Highest Potential: ..." suffix for an Upgraded log line:
        top 5 presets by max high across the SELECTED assigned presets
        (see _selected_log_preset_names), each with ITS OWN (low, high)
        pair -- never a synthetic min/max combined across presets, whose
        ends could come from different presets and mislead. Philosophy B:
        the fragment's main stat is excluded from each preset's bounds
        (mirrors the Memory Fragments tab).

        Returns "" when presets exist but none is selected. When NO user
        presets exist at all, falls back to the default-weight range so
        there's still something useful to display."""
        pm = self.preset_manager
        main_name = fragment.main_stat.name if fragment.main_stat else None
        all_names = list(pm.get_preset_names()) if pm is not None else []
        if not all_names:
            weights = {}
            bounds = compute_gs_bounds(weights, exclude_stat=main_name)
            low, high = compute_fragment_potential(fragment, weights, bounds)
            return f". Highest Potential: {low:.0f}-{high:.0f}"

        selected = self._selected_log_preset_names()
        if not selected:
            return ""

        scored = []
        for name in selected:
            weights = pm.get_preset(name) or {}
            bounds = compute_gs_bounds(weights, exclude_stat=main_name)
            low, high = compute_fragment_potential(fragment, weights, bounds)
            scored.append((low, high, name))
        # Sort by high desc -- ties broken by low desc (a tighter high-end
        # with a higher floor is preferable when ceilings tie). Top 5.
        scored.sort(key=lambda t: (-t[1], -t[0]))
        parts = [f"{low:.0f}-{high:.0f} [{name}]"
                 for (low, high, name) in scored[:5]]
        return ". Highest Potential: " + ", ".join(parts)

    def recompute_last_upgrade_line(self):
        """Re-render the LAST "[LIVE] Upgraded" capture-log line against
        the current Log Presets selection. The fragment OBJECT was
        retained at augment time, so its stats reflect the state as of
        that upgrade even after later reloads rebuilt optimizer.fragments.
        No-op before the first upgrade of the session."""
        fragment = getattr(self, "_last_upgrade_fragment", None)
        base = getattr(self, "_last_upgrade_base", None)
        if fragment is None or base is None:
            return
        if not hasattr(self, "capture_tab_instance"):
            return
        text = f"[proxy] {base}{self._upgrade_potentials_suffix(fragment)}"
        self.capture_tab_instance.rewrite_last_upgrade_line(text, "info")

    def _augment_upgrade_log(self, line: str) -> str:
        """Strip the internal [pid=N] marker from `line`, find the upgraded
        fragment, and append its Highest Potential under the selected
        assigned presets (see _upgrade_potentials_suffix for the exact
        semantics and ordering).

        Also RETAINS the fragment object + the marker-stripped base line so
        a later Log Presets toggle can re-render this line in place
        (recompute_last_upgrade_line) with the stats as of this upgrade.

        Returns the augmented line. On any failure (marker missing,
        fragment not found) returns the marker-stripped line WITHOUT
        appending Highest Potential -- never leaks the [pid=N] token to
        the user.
        """
        # Pull the marker; if absent, just show the line unchanged.
        m = re.search(r"\s*\[pid=(\d+)\]\s*$", line)
        if not m:
            return line
        base = line[: m.start()].rstrip()
        try:
            pid = int(m.group(1))
        except ValueError:
            return base

        # Find the upgraded fragment.
        fragment = next(
            (f for f in self.optimizer.fragments if getattr(f, "id", None) == pid),
            None,
        )
        if fragment is None:
            return base

        # Retain for in-place re-render on Log Presets toggles.
        self._last_upgrade_fragment = fragment
        self._last_upgrade_base = base

        return f"{base}{self._upgrade_potentials_suffix(fragment)}"

    def _ensure_characters_in_preset_file(self):
        """Make sure every character currently in optimizer data has an entry
        in character_preset.json (defaulting to no preset) and in
        log_presets.json (defaulting to selected). No-op for already known
        characters; only newly-seen ones trigger a write."""
        try:
            names = (
                set(self.optimizer.characters.keys())
                | set(self.optimizer.character_info.keys())
            )
            self.character_preset_manager.ensure_characters(names)
        except Exception:
            pass
        try:
            ids = [str(ci.res_id)
                   for ci in self.optimizer.character_info.values()
                   if getattr(ci, "res_id", 0)]
            self.log_presets_manager.ensure_ids(ids)
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


# --- Native Windows dialogs for the pre-startup prompts ------------------
#
# These run BEFORE OptimizerGUI creates the application's Tk root, and
# they must NOT create one of their own. A Tk root that is created and
# destroyed before the real one leaves the process unable to pump events
# for the root that follows: the main window paints (the reveal's
# update() passes draw it) and then never responds to anything again.
# tkinter's messagebox is a wrapper around this same native dialog on
# Windows, so nothing changes visually.
MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONQUESTION = 0x00000020
MB_ICONWARNING = 0x00000030
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000
IDYES = 6

# ShellExecuteW's result when the user dismissed the UAC prompt
# (SE_ERR_ACCESSDENIED), as opposed to elevation failing for a reason
# worth reporting.
SE_ERR_ACCESSDENIED = 5


def _win_message(title: str, text: str, flags: int) -> int:
    """Show an owner-less native Windows message box and return its ID*
    result (0 if the call itself fails). Always foreground + topmost:
    these prompts appear before the app has a window of its own, and
    launching from an Explorer window otherwise leaves them behind it.
    """
    try:
        return ctypes.windll.user32.MessageBoxW(
            None, text, title, flags | MB_SETFOREGROUND | MB_TOPMOST
        )
    except Exception:
        return 0


def run_as_admin() -> int:
    """Relaunch this program elevated.

    Returns the raw ShellExecuteW result: > 32 means the elevated copy
    started and this process should exit; SE_ERR_ACCESSDENIED means the
    user dismissed the UAC prompt; any other small value is a real
    failure. 0 if the call raised or the platform isn't Windows.
    """
    if sys.platform != "win32":
        return 0

    try:
        if getattr(sys, 'frozen', False):
            script = sys.executable
            params = " ".join(sys.argv[1:])
        else:
            script = sys.executable
            params = f'"{sys.argv[0]}"'
            if len(sys.argv) > 1:
                params += " " + " ".join(sys.argv[1:])

        return ctypes.windll.shell32.ShellExecuteW(
            None, "runas", script, params, None, 1
        )
    except Exception as e:
        print(f"Failed to elevate: {e}")
        return 0


# Loopback port used as a process-wide single-instance lock. Picked from
# the IANA dynamic/private range (49152-65535) at a value with no known
# common-software collisions. The port is only bound for the lifetime of
# the process; the OS frees it on exit (clean or crash), so we don't need
# stale-lockfile cleanup the way a file-based scheme would.
_SINGLE_INSTANCE_PORT = 53117


def _acquire_single_instance_lock():
    """Try to bind a localhost socket as a single-instance lock.

    Returns the bound socket (which the caller must keep alive for the
    lifetime of the program -- letting it go out of scope releases the
    lock) on success, or None if another instance is already running.

    A note on cross-platform behavior: SO_REUSEADDR is intentionally NOT
    set, because we WANT the bind to fail when another instance holds
    the port. On Linux/macOS that's the default; on Windows it's also the
    default unless SO_REUSEADDR is explicitly set, so this works on all
    three.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _SINGLE_INSTANCE_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main():
    # Single-instance check must happen BEFORE any Tk root is created --
    # creating a Tk root before deciding to exit causes an empty flicker
    # window. We hold the returned socket as a module-level reference so
    # garbage collection can't release the lock mid-run.
    global _instance_lock
    _instance_lock = _acquire_single_instance_lock()
    if _instance_lock is None:
        # A Tk root is fine here ONLY because the process exits straight
        # afterwards -- no second root ever follows it. See the comment
        # above _win_message before reusing this pattern anywhere that
        # keeps running.
        warn_root = tk.Tk()
        warn_root.withdraw()
        messagebox.showwarning(
            "Already Running",
            "Another instance of Vribbels CZN Optimizer (Ikkoru) is already running.\n\n"
            "Only one instance can run at a time."
        )
        warn_root.destroy()
        sys.exit(0)

    if sys.platform == "win32" and not is_admin():
        # Native dialogs, not tkinter's: creating a Tk root here and
        # destroying it leaves the real window frozen (see _win_message).
        response = _win_message(
            "Administrator Required",
            "This application needs Administrator privileges for the capture feature.\n\n"
            "Do you want to restart with elevated permissions?\n\n"
            "(Click 'No' to continue without capture functionality)",
            MB_YESNO | MB_ICONQUESTION,
        )

        if response == IDYES:
            ret = run_as_admin()
            if ret > 32:
                sys.exit(0)
            if ret != SE_ERR_ACCESSDENIED:
                # Dismissing the UAC prompt is a decision, not a failure;
                # only report elevation that actually went wrong.
                _win_message(
                    "Elevation Failed",
                    "Could not get administrator privileges.",
                    MB_OK | MB_ICONWARNING,
                )

    app = OptimizerGUI()
    app.run()


if __name__ == "__main__":
    # Required for the parallel optimizer in frozen (PyInstaller) builds:
    # Windows spawn re-launches this executable for every worker process,
    # and freeze_support() detects those worker launches and runs the
    # multiprocessing bootstrap INSTEAD of the GUI (no-op when not frozen
    # and no-op for a normal user launch). Must be the first statement in
    # this guard. All other side effects (single-instance lock, admin
    # prompt, Tk roots) stay inside main(), so a spawned worker importing
    # this module never triggers them -- and never trips the
    # single-instance lock.
    import multiprocessing
    multiprocessing.freeze_support()
    main()