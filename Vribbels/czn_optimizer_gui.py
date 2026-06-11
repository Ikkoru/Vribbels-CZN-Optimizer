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
  config.py                 AppConfig (server_region) -- now stored at
                            settings/config.json (was at base_dir before
                            round 11; load_config migrates on first hit).
  preset_manager.py         User scoring presets (named weight sets).
  character_preset_manager  Per-character preset assignments. v2 schema
                            keyed by res_id with parallel name_hints.
  optimizer_settings_manager Per-character Optimizer-tab config plus the
                            global excluded_gear_chars list.
  level_data_manager.py     User-confirmed (exp, level) checkpoints
                            that augment the exp tables at startup.
  settings_manager.py       Generic persistent key-value store. Holds
                            last_selected_character + selected_preset.
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
import webbrowser
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont

# === GAME DATA IMPORTS ===
from game_data import *
from models import *
from capture import *
from optimizer import GearOptimizer
from config import load_config, save_config, AppConfig
from ui import AppContext, MaterialsTab, SetupTab, CaptureTab, InventoryTab, OptimizerTab, HeroesTab, ScoringTab, AboutTab
# Used to augment "[LIVE] Upgraded" log lines with the post-upgrade
# Highest Pot. range across all currently-defined presets (see
# _drain_pending_upgrade_lines below).
from models.memory_fragment import compute_gs_bounds, compute_fragment_potential
# Round 10: reconciles bundled defaults in `default_settings/` with the
# user's `settings/` folder. Must run BEFORE any manager loads so the
# first-run / new-user / update-merge cases all see consistent state.
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

    Round 10 note: bundled defaults under `default_settings/` need to
    resolve to the bundle root (which in frozen builds is _MEIPASS for
    read-only data), not the user data dir. defaults_sync handles that
    distinction internally by checking both locations.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# Round 10: `_bootstrap_user_data` was removed. Its job (one-time copy of
# bundled defaults from _MEIPASS/presets/ to the user's presets/) is now
# handled by `defaults_sync.sync_defaults()`, which also covers the
# per-entity update-merge case (new characters added in a program
# update flow into the user's settings without overwriting their
# customizations).


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
        # Load configuration
        self.config = load_config()

        self.root = tk.Tk()
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

        self.setup_ui()

        self.auto_load()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

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

        program_dir = _user_data_dir()
        # Round 10: reconcile bundled defaults vs the user's settings/
        # BEFORE any manager loads. Handles three cases (maintainer
        # bootstrap, new-user bootstrap, update-merge) -- see
        # defaults_sync.py for the full breakdown. Failure here is
        # non-fatal; managers below would just see empty files and
        # behave as if it's a fresh install.
        #
        # In a frozen build the bundled defaults live in _MEIPASS (the
        # PyInstaller extract dir) and the user's writable state lives
        # next to the exe. In dev they're both siblings in the source
        # tree.
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
        self.app_context.preset_manager = self.preset_manager
        self.app_context.character_preset_manager = self.character_preset_manager
        self.app_context.level_data_manager = self.level_data_manager
        self.app_context.settings_manager = self.settings_manager
        self.app_context.optimizer_settings_manager = self.optimizer_settings_manager
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
        # Round 11 follow-up: optimizer_tab ref for the Setup tab's
        # Restore Defaults > Combatant Settings flow (refreshes the
        # selected combatant's settings after a restore).
        self.app_context.optimizer_tab = self.optimizer_tab_instance

        self.scoring_tab_instance = ScoringTab(self.notebook, self.app_context)
        self.scoring_tab = self.scoring_tab_instance.get_frame()
        # Heroes tab uses this to refresh the preset listbox's assignment
        # markers after a Combatants-tab preset change. Set after creation;
        # the heroes_tab queries via the context and no-ops if None.
        self.app_context.scoring_tab = self.scoring_tab_instance

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

            # Update other tabs
            self.inventory_tab_instance.populate_set_filters()
            self.inventory_tab_instance.refresh_inventory()
            self.heroes_tab_instance.refresh_heroes()
            self.materials_tab_instance.refresh_materials()

            # Re-score fragments using the currently-active scoring weights
            # (preset or custom), so loading fresh data doesn't wipe them out.
            self.scoring_tab_instance.apply_active_weights()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")
            import traceback
            traceback.print_exc()

    def _handle_live_update(self):
        """Handle live update from capture — reload latest snapshot and refresh UI.

        Round 10 Q7: re-entrancy guard. A burst of WebSocket messages (e.g.
        equip + unequip from one in-game action) can fire this callback
        repeatedly while a previous invocation is still mid-refresh. Without
        the guard, the second call walks half-mutated optimizer state and
        triggers cascading layout passes which the user saw as the col 2
        "jumping left-right without end" symptom. We just drop nested calls
        — the outer call already pulls the latest snapshot off disk, so
        anything written between the two calls gets picked up by that read.
        """
        if getattr(self, "_in_live_update", False):
            return
        self._in_live_update = True
        try:
            latest = self.capture_manager.get_latest_capture()
            if latest:
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
                    # apply_active_weights also refreshes inventory + heroes tabs
                    self.scoring_tab_instance.apply_active_weights()
                except Exception:
                    pass  # Silently ignore reload errors during live monitoring

            # Drain any deferred upgrade log lines that arrived while the
            # addon's stdout was being read. Must happen AFTER the reload so
            # the upgraded fragment is in optimizer.fragments with its new
            # level/upgrades when we look it up.
            self._drain_pending_upgrade_lines()
        finally:
            self._in_live_update = False

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
                self.capture_tab_instance.capture_log_msg(
                    f"[proxy] {augmented}", "info"
                )

    def _augment_upgrade_log(self, line: str) -> str:
        """Strip the internal [pid=N] marker from `line`, find the upgraded
        fragment, compute Highest Potential under each preset, and append the
        best-preset (low, high) pair plus that preset's name in brackets.

        Returns the augmented line. On any failure (marker missing,
        fragment not found, no presets defined) returns the marker-stripped
        line WITHOUT appending Highest Potential -- never leaks the [pid=N]
        token to the user.

        Round 10 task 6: the previous version reported min(low) across
        all presets together with max(high) -- a synthetic range whose two
        ends didn't necessarily come from the same preset. Now matches the
        Memory Fragments tab's column logic: pick the preset with the
        max high, use ITS (low, high) pair. Also appends the winning
        preset's name and renamed "Highest Pot." -> "Highest Potential".
        For fully-leveled MFs (low == high under every preset), the
        preset with max high is also the preset with max GS, so the
        same one-pass loop handles both cases.
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

        # Walk every preset, score each one, then sort by high desc and
        # take the top 3 to display. Philosophy B: exclude this fragment's
        # main stat when computing preset bounds (mirrors the MF tab).
        pm = self.preset_manager
        preset_names = list(pm.get_preset_names()) if pm is not None else []
        main_name = fragment.main_stat.name if fragment.main_stat else None
        if not preset_names:
            # No user presets defined -- compute against default weights so
            # there's still something useful to display.
            weights = {}
            bounds = compute_gs_bounds(weights, exclude_stat=main_name)
            low, high = compute_fragment_potential(
                fragment, weights, bounds
            )
            return f"{base}. Highest Potential: {low:.0f}-{high:.0f}"

        # Compute (low, high, name) per preset.
        scored = []
        for name in preset_names:
            weights = pm.get_preset(name) or {}
            bounds = compute_gs_bounds(weights, exclude_stat=main_name)
            low, high = compute_fragment_potential(fragment, weights, bounds)
            scored.append((low, high, name))
        # Sort by high desc -- ties broken by low desc (a tighter high-end
        # with a higher floor is preferable when ceilings tie). Take top 4.
        scored.sort(key=lambda t: (-t[1], -t[0]))
        top = scored[:4]
        parts = [f"{low:.0f}-{high:.0f} [{name}]" for (low, high, name) in top]
        return f"{base}. Highest Potential: " + ", ".join(parts)

    def _ensure_characters_in_preset_file(self):
        """Make sure every character currently in optimizer data has an entry
        in character_preset.json (defaulting to no preset). No-op for already
        known characters; only newly-seen ones trigger a write."""
        try:
            names = (
                set(self.optimizer.characters.keys())
                | set(self.optimizer.character_info.keys())
            )
            self.character_preset_manager.ensure_characters(names)
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    if sys.platform != "win32":
        return False
    
    try:
        if getattr(sys, 'frozen', False):
            script = sys.executable
            params = " ".join(sys.argv[1:])
        else:
            script = sys.executable
            params = f'"{sys.argv[0]}"'
            if len(sys.argv) > 1:
                params += " " + " ".join(sys.argv[1:])
        
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
        return ret > 32
    except Exception as e:
        print(f"Failed to elevate: {e}")
        return False


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
        temp_root = tk.Tk()
        temp_root.withdraw()
        
        response = messagebox.askyesno(
            "Administrator Required",
            "This application needs Administrator privileges for the capture feature.\n\n"
            "Do you want to restart with elevated permissions?\n\n"
            "(Click 'No' to continue without capture functionality)"
        )
        
        temp_root.destroy()
        
        if response:
            if run_as_admin():
                sys.exit(0)
            else:
                temp_root2 = tk.Tk()
                temp_root2.withdraw()
                messagebox.showwarning("Elevation Failed", "Could not get administrator privileges.")
                temp_root2.destroy()
    
    app = OptimizerGUI()
    app.run()


if __name__ == "__main__":
    main()