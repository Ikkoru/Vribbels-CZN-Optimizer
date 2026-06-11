"""
ScoringTab - Gear scoring configuration interface.

This tab provides controls for configuring how Memory Fragments are scored:
- Custom stat priority weights (0-5 spinboxes for each stat)
- Save / load / delete user-defined preset configurations
- Real-time score recalculation and inventory refresh

The scoring system affects:
- Gear score calculation for each Memory Fragment
- Filtering during optimization (top X% selection)
- Inventory display rankings
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path

from ..base_tab import BaseTab
from ..context import AppContext
from game_data import STATS
# a7 (this round): user-facing stat-name overrides (e.g. "Flat ATK" ->
# "ATK Flat", "CRate" -> "Crit%", "CDmg" -> "CDMG%"). Applied to the
# Stat Weight Configuration labels so they match the rest of the app.
from game_data.constants import DISPLAY_NAMES
from preset_manager import PresetManager, SUPPORTED_STATS
from models.memory_fragment import compute_gs_bounds


# Display order: (stat_key used internally, label shown to the user)
STAT_DISPLAY_NAMES = [
    ("Flat ATK", "Flat ATK"), ("ATK%", "ATK%"),
    ("Flat DEF", "Flat DEF"), ("DEF%", "DEF%"),
    ("Flat HP",  "Flat HP"),  ("HP%",  "HP%"),
    ("CRate",    "Crit Rate"),("CDmg", "Crit Damage"),
    ("Ego",      "Ego"),      ("Extra DMG%", "Extra DMG%"),
    ("DoT%",     "DoT%"),
]

# Width (in chars) used for buttons and the preset-name entry.
# Sized to fit the longest button label: "Delete Selected Presets" (23 chars).
BTN_WIDTH = 23

# Glyph shown in the icon column for presets currently assigned to >=1
# character (via CharacterPresetManager). A dedicated Treeview column
# holds this so it always renders in a fixed-width gutter on the left,
# keeping the preset names themselves vertically aligned regardless of
# which rows are linked. Unlinked rows get an empty string in the same
# column. If the link emoji doesn't render on a particular system (rare
# on Windows 10+, but possible elsewhere), swap this constant for a
# plain ASCII marker like "*" -- everything else flows from here.
ASSIGNED_ICON = "\U0001F517"   # link symbol (U+1F517)


class ScoringTab(BaseTab):
    """Tab for configuring gear scoring weights and managing presets."""

    def __init__(self, parent: tk.Widget, context: AppContext):
        super().__init__(parent, context)
        self._init_state()

        # Use the PresetManager and CharacterPresetManager from AppContext.
        # czn_optimizer_gui.py creates and loads them before constructing tabs,
        # so they're already populated. Falling back to a fresh one keeps the
        # tab usable in standalone tests where context is bare.
        if context.preset_manager is not None:
            self.preset_manager = context.preset_manager
        else:
            program_dir = Path(__file__).resolve().parent.parent.parent
            self.preset_manager = PresetManager(program_dir)
            self.preset_manager.load()

        self.character_preset_manager = context.character_preset_manager  # may be None

        self.setup_ui()
        self._initialize_from_loaded_presets()

    # ============================================================
    # Initialization
    # ============================================================

    def _init_state(self):
        """Initialize state variables."""
        self.stat_weight_vars = {}        # dict[str, tk.DoubleVar]
        self.preset_name_var = None       # tk.StringVar (set in setup_ui)
        self.weight_status = None         # ttk.Label
        self.preset_tree = None           # ttk.Treeview

        # Currently-applied preset name, or None if "default" / "custom".
        self.active_preset_name = None

    def _initialize_from_loaded_presets(self):
        """After UI is built, apply whichever preset (or default) is active."""
        # If the file was corrupt, tell the user once.
        if self.preset_manager.is_corrupted():
            messagebox.showwarning(
                "Presets File Corrupted",
                f"The presets file appears to be invalid:\n\n"
                f"{self.preset_manager.corruption_error}\n\n"
                f"File: {self.preset_manager.presets_file}\n\n"
                f"Default weights have been applied. The file will not be edited "
                f"unless you save a new preset (you'll be prompted to back up "
                f"the broken file first)."
            )
            self._reset_sliders_to_default()
            self.active_preset_name = None
            self.weight_status.config(text="Applied default weights (all 1.0)")
            self.refresh_preset_list()
            return

        self.refresh_preset_list()

        sel = self.preset_manager.selected_preset
        if sel and self.preset_manager.has_preset(sel):
            weights = self.preset_manager.get_preset(sel)
            self._set_sliders(weights)
            self.active_preset_name = sel
            self.weight_status.config(text=f"Applied {sel}")
        else:
            self._reset_sliders_to_default()
            self.active_preset_name = None
            self.weight_status.config(text="Applied default weights (all 1.0)")

    # ============================================================
    # UI construction
    # ============================================================

    def setup_ui(self):
        main_frame = ttk.Frame(self.frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(
            main_frame, text="Gear Score Calculation",
            font=("Segoe UI", 14, "bold")
        ).pack(anchor=tk.W)
        ttk.Label(
            main_frame, text="Configure how gear scores are calculated",
            foreground=self.colors["fg_dim"]
        ).pack(anchor=tk.W, pady=(0, 10))

        content = ttk.Frame(main_frame)
        content.pack(fill=tk.BOTH, expand=True)
        # Fixed 50/50 split (v1.1.0): replaces the previous ttk.PanedWindow
        # so the sash isn't draggable. uniform= ties the two columns to the
        # same width-share group so they stay equal as the window resizes.
        content.grid_columnconfigure(0, weight=1, uniform="halves")
        content.grid_columnconfigure(1, weight=1, uniform="halves")
        content.grid_rowconfigure(0, weight=1)

        # --- Left side: explanation ----------------------------------
        explain_frame = ttk.LabelFrame(content, text="How Gear Score Works", padding=10)
        explain_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        explanation = """GEAR SCORE (GS) EXPLANATION

The Gear Score measures how well a Memory Fragment (MF) rolled.
0 is the worst possible outcome. 100 is the best.
These measurements are calculated based on the weights to the right →.
Change the values based on how important each stat is to your build, then press "Apply Current Weights".
This program comes with presets for each character, but you may also create and save your own.

These weights affect the Memory Fragments and Combatants tabs. The Optimizer tab is not affected (almost).

WEIGHTS:
Configure custom weights to emphasize stats you care about.
For example, if a stat is set at 1.0, setting another stat at 2.0 means you value it twice as much.
The resulting Gear Score is normalized between 0 and 100. Negative weights are allowed (mark a stat as harmful) — normalization clamps to 0 if scores go below the theoretical floor.

PRESETS:
Save weight configurations as presets and switch between them with double-click, or by pressing the "Apply Selected Preset" button.
In the Combatants tab, set a default preset for each character. This only affects the Combatants tab, the "Highest GS/Potential: Assigned Presets Only" option, and which MFs are considered by the Optimizer.
Creating presets for each character is useful for finding and dismantling MFs that no character wants.
Use the "Highest GS" and "Highest Pot." columns in the Memory Fragments tab for this. These columns use all the presets, so an MF with a low "Highest Pot." would be mediocre for all currently existing characters.

POTENTIAL:
The possible Gear Score that an MF can get after being fully upgraded.
 - Low:  every remaining upgrade rolls minimum on the worst-weighted stat
 - High: every remaining upgrade rolls maximum on the best-weighted stat
  
Notes:
 - The Optimizer does not consider bad MFs (to speed up calculations). It uses assigned Presets to know which MFs are bad.
 - In the Combatants tab, total character GS is the sum of equipped MF scores — the max is 600.
 - GS is calculated from substats only — the main stat itself doesn't add to the score. An MF not being able to have a substat that is the same as the main stat is accounted for by the normalization system.
 - 3★ Rare MFs cap below 100 (fewer upgrade rolls than the 4★ ceiling).

STAT MIN - MAX ROLLS:
 - Flat ATK: 5 - 8
 - Flat DEF: 3 - 5
 - Flat HP: 10 - 12
 - ATK%/DEF%/HP%: 0.8 - 1.3%
 - CRate: 1.2 - 2.0%
 - CDmg: 2.4 - 4.0%
 - Extra DMG%/DoT%: 2.7 - 3.4%
 - Ego: 2 - 5"""

        explain_text = scrolledtext.ScrolledText(
            explain_frame, height=20, wrap=tk.WORD,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            font=("Consolas", 9)
        )
        # Round 11 follow-up to Task 3: scrolledtext.ScrolledText wraps
        # its Text widget in an internal tk.Frame whose bg defaults to
        # the system white. On first show the wrapping frame paints
        # briefly before the inner Text widget paints over it, producing
        # a visible white flash. Force the wrapping frame (and the
        # associated scrollbar) to the dark bg so the flash is gone.
        try:
            explain_text.frame.configure(bg=self.colors["bg_light"])
        except (AttributeError, tk.TclError):
            pass
        try:
            explain_text.vbar.configure(
                bg=self.colors["bg_light"],
                troughcolor=self.colors["bg"],
                activebackground=self.colors["bg_lighter"],
            )
        except (AttributeError, tk.TclError):
            pass
        explain_text.insert("1.0", explanation)
        explain_text.config(state=tk.DISABLED)
        explain_text.pack(fill=tk.BOTH, expand=True)

        # --- Right side: configuration -------------------------------
        config_frame = ttk.LabelFrame(content, text="Stat Weight Configuration", padding=10)
        config_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        ttk.Label(
            config_frame,
            text="Adjust weights for custom scoring (1.0 = normal)",
            foreground=self.colors["fg_dim"]
        ).pack(anchor=tk.W, pady=(0, 10))

        # Top region: stats on the left, button column on the right.
        # Two separate frames so stat rows keep their natural compact spacing
        # without being pushed apart by taller button rows.
        top = ttk.Frame(config_frame)
        top.pack(fill=tk.X, anchor=tk.W)

        stats_frame = ttk.Frame(top)
        stats_frame.pack(side=tk.LEFT, anchor=tk.N)

        # Spacer between stats and buttons.
        ttk.Frame(top, width=20).pack(side=tk.LEFT)

        # The button frame fills its parent vertically so weighted empty rows
        # inside it can push the lower buttons down to align with DoT%.
        btn_frame = ttk.Frame(top)
        btn_frame.pack(side=tk.LEFT, fill=tk.Y)

        self._build_stats_grid(stats_frame)
        self._build_button_column(btn_frame)

        # Status label, anchored to the left so it sits right below DoT%.
        self.weight_status = ttk.Label(
            config_frame, text="Applied default weights (all 1.0)",
            foreground=self.colors["fg_dim"]
        )
        self.weight_status.pack(anchor=tk.W, padx=5, pady=(15, 5))

        # Preset list, fills remaining space and resizes with the window.
        # ttk.Treeview with two data-only columns: a narrow marker gutter on
        # the left and the preset name on the right. We use show="" (not
        # show="tree") so the special #0 tree column is suppressed entirely
        # -- otherwise it reserves a few pixels of leading indent + disclosure
        # indicator space that has no use in a flat list. Data columns still
        # render even when neither "tree" nor "headings" is in show.
        list_frame = ttk.Frame(config_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.preset_tree = ttk.Treeview(
            list_frame,
            columns=("marker", "name"),
            show="",            # no #0 tree column, no headers -- data cells only
            selectmode="extended",
            yscrollcommand=scrollbar.set,
        )
        # "marker" is the icon gutter on the left -- narrow, fixed width.
        # "name" takes the rest of the available width.
        self.preset_tree.column("marker", width=24, minwidth=24, stretch=False, anchor="center")
        self.preset_tree.column("name", width=200, stretch=True, anchor="w")
        scrollbar.config(command=self.preset_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.preset_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.preset_tree.bind("<Double-Button-1>", self.on_preset_double_click)
        # Windows-Explorer-style typing-ahead: press a letter to jump to the
        # next preset whose name starts with that letter. Cycles when reaching
        # the end. Non-alphanumeric keys (arrows, etc.) fall through to Tk's
        # built-in handling.
        self.preset_tree.bind("<KeyPress>", self._on_preset_key)

    def _build_stats_grid(self, parent: ttk.Frame):
        """11 stat label+spinbox pairs in a 2-column grid (DoT% alone in row 5).

        Lives in its own frame so spacing isn't perturbed by the (taller)
        button column to the right.
        """
        for i, (stat_key, display_name) in enumerate(STAT_DISPLAY_NAMES):
            row, col = i // 2, i % 2
            cell = ttk.Frame(parent)
            # Task 5 (round 9): +5px between the two weight columns (col 1
            # gets 5px extra left padding -> 15px inter-column gap vs 10).
            cell.grid(row=row, column=col, sticky=tk.W,
                      padx=(10 if col == 1 else 5, 5), pady=2)

            # a7 (round 8): label uses the canonical DISPLAY_NAMES override
            # (falling back to display_name); trailing colon dropped.
            # Task 5 (round 9): width 12 -> 9 (longest label is 8 chars) so
            # the spinbox sits closer to its text.
            label = DISPLAY_NAMES.get(stat_key, display_name)
            ttk.Label(cell, text=label, width=9).pack(side=tk.LEFT)
            var = tk.DoubleVar(value=1.0)
            self.stat_weight_vars[stat_key] = var

            spin = tk.Spinbox(
                cell, from_=0.0, to=5.0, increment=0.1, width=5,
                textvariable=var, format="%.1f",
                bg=self.colors["bg_light"], fg=self.colors["fg"],
                buttonbackground=self.colors["bg_lighter"],
                insertbackground=self.colors["fg"],
                selectbackground=self.colors["select"],
                selectforeground=self.colors["fg"],
                relief=tk.FLAT, bd=1
            )
            spin.pack(side=tk.LEFT, padx=(0, 2))
            # Mouse-wheel adjustment (v1.1.0): same handler as Optimizer tab.
            # tk.Spinbox doesn't bind <MouseWheel> by default; without this
            # the user has to click the up/down buttons to change values.
            spin.bind(
                "<MouseWheel>",
                lambda e, sp=spin: self._spinbox_wheel(e, sp),
            )

    def _build_button_column(self, parent: ttk.Frame):
        """Five buttons + label + entry in a 2-column grid that fills its parent.

        Top buttons sit at row 0 (so they line up with the top of ATK% in the
        adjacent stats frame). Rows 1 and 2 are weighted empty space, pushing
        the lower group (label, save+entry, apply/delete) down so the bottom
        buttons line up with the bottom of DoT%.
        """
        # Row 0: Apply Current Weights | Reset Current Weights
        ttk.Button(
            parent, text="Apply Current Weights",
            command=self.on_apply_current_weights, width=BTN_WIDTH
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        ttk.Button(
            parent, text="Reset Current Weights",
            command=self.on_reset_current_weights, width=BTN_WIDTH
        ).grid(row=0, column=1, sticky="ew", padx=2, pady=2)

        # Rows 1, 2: weighted empty space — absorbs vertical slack so rows
        # 3-5 are pinned to the bottom of the frame.
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        # Row 3, col 1: "Preset Name:" label sits just above the entry.
        ttk.Label(parent, text="Preset Name:").grid(
            row=3, column=1, sticky="sw", padx=2
        )

        # Row 4: Save Weights Preset As | preset name entry
        ttk.Button(
            parent, text="Save Weights Preset As",
            command=self.on_save_preset, width=BTN_WIDTH
        ).grid(row=4, column=0, sticky="ew", padx=2, pady=2)

        self.preset_name_var = tk.StringVar()
        tk.Entry(
            parent, textvariable=self.preset_name_var, width=BTN_WIDTH,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            insertbackground=self.colors["fg"],
            selectbackground=self.colors["select"],
            selectforeground=self.colors["fg"],
            relief=tk.FLAT, bd=1, highlightthickness=0
        ).grid(row=4, column=1, sticky="ew", padx=2, pady=2)

        # Row 5: Apply Selected Preset | Delete Selected Presets
        ttk.Button(
            parent, text="Apply Selected Preset",
            command=self.on_apply_selected_preset, width=BTN_WIDTH
        ).grid(row=5, column=0, sticky="ew", padx=2, pady=2)

        ttk.Button(
            parent, text="Delete Selected Presets",
            command=self.on_delete_selected_presets, width=BTN_WIDTH
        ).grid(row=5, column=1, sticky="ew", padx=2, pady=2)

        # Force button columns to share width.
        parent.grid_columnconfigure(0, uniform="btn_col")
        parent.grid_columnconfigure(1, uniform="btn_col")

    # ============================================================
    # Public API used from outside the tab
    # ============================================================

    def apply_active_weights(self):
        """
        Recalculate gear scores for all current fragments using whatever
        weights are currently in the spinboxes, then refresh dependent tabs.
        Does NOT change the status label — used after live updates / data loads
        so the displayed "Applied X" text stays consistent.

        Both the base GS and the potential range are normalized to a 0-100
        scale per the active weights' theoretical bounds, with each
        fragment's main stat EXCLUDED from its bounds calculation (so 100
        is reachable regardless of which main stat the fragment has).
        Bounds are cached by main_stat name across the fragment loop --
        there are only ~16 distinct main stats max, so this is far cheaper
        than recomputing per fragment.
        """
        weights = {stat: var.get() for stat, var in self.stat_weight_vars.items()}
        bounds_cache: dict = {}  # main_stat name -> (min_raw, max_raw)
        for fragment in self.optimizer.fragments:
            main_name = fragment.main_stat.name if fragment.main_stat else None
            if main_name not in bounds_cache:
                bounds_cache[main_name] = compute_gs_bounds(
                    weights, exclude_stat=main_name
                )
            bounds = bounds_cache[main_name]
            fragment.calculate_base_score(weights=weights, bounds=bounds)
            fragment.calculate_potential(weights=weights, bounds=bounds)

        self.context.inventory_tab.refresh_inventory()
        self.context.heroes_tab.refresh_heroes()

    # ============================================================
    # Button handlers
    # ============================================================

    def on_apply_current_weights(self):
        """Apply whatever the spinboxes currently say. Marks as 'custom weights'."""
        self.apply_active_weights()
        self.active_preset_name = None
        self.preset_manager.set_selected(None)
        self.weight_status.config(text="Applied custom weights")

    def on_reset_current_weights(self):
        """Set every spinbox to 1.0, apply, mark as default."""
        self._reset_sliders_to_default()
        self.apply_active_weights()
        self.active_preset_name = None
        self.preset_manager.set_selected(None)
        self.weight_status.config(text="Applied default weights (all 1.0)")

    def on_apply_selected_preset(self):
        """Apply a preset selected in the listbox (must be exactly one)."""
        sel = self.preset_tree.selection()
        if len(sel) > 1:
            messagebox.showerror(
                "Multiple Presets Selected",
                f"Please select only one preset to apply.\n\n"
                f"You currently have {len(sel)} presets selected."
            )
            return
        if not sel:
            messagebox.showwarning(
                "No Preset Selected",
                "Please select a preset from the list to apply."
            )
            return

        # Treeview iids ARE the preset names (we set them so on insert),
        # so the lookup is direct.
        name = sel[0]
        weights = self.preset_manager.get_preset(name)
        if weights is None:
            messagebox.showerror("Error", f"Preset '{name}' was not found.")
            self.refresh_preset_list()
            return

        self._set_sliders(weights)
        self.apply_active_weights()
        self.active_preset_name = name
        self.preset_manager.set_selected(name)
        self.weight_status.config(text=f"Applied {name}")

    def on_preset_double_click(self, event):
        """Apply the preset under the double-clicked row, regardless of selection."""
        # identify_row returns the iid of the row at the event y, or "" if
        # the click was below the last row.
        iid = self.preset_tree.identify_row(event.y)
        if not iid:
            return
        # iid is the preset name (set explicitly on insert).
        name = iid
        weights = self.preset_manager.get_preset(name)
        if weights is None:
            messagebox.showerror("Error", f"Preset '{name}' was not found.")
            self.refresh_preset_list()
            return

        self._set_sliders(weights)
        self.apply_active_weights()
        self.active_preset_name = name
        self.preset_manager.set_selected(name)
        self.weight_status.config(text=f"Applied {name}")

    def on_save_preset(self):
        """Save the current spinbox values as a new preset and apply it."""
        name = self.preset_name_var.get().strip()
        if not name:
            messagebox.showerror(
                "Invalid Preset Name",
                "Please enter a name for the preset in the Preset Name field."
            )
            return

        # If the file is corrupted, get explicit consent before overwriting.
        if self.preset_manager.is_corrupted():
            confirm_msg = (
                f"The presets file is corrupted:\n\n"
                f"{self.preset_manager.corruption_error}\n\n"
                f"Saving will rename the broken file (adding '_corrupted' to its "
                f"filename) and create a fresh one with this preset.\n\n"
                f"Continue?"
            )
            if not messagebox.askyesno("Corrupted Presets File", confirm_msg):
                return
            try:
                self.preset_manager.quarantine()
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to back up the corrupted file: {e}"
                )
                return

        # Confirm overwrite if the name already exists.
        if self.preset_manager.has_preset(name):
            if not messagebox.askyesno(
                "Overwrite Preset",
                f"A preset named '{name}' already exists.\n\n"
                f"Overwrite it with the current weights?"
            ):
                return

        weights = {stat: var.get() for stat, var in self.stat_weight_vars.items()}
        try:
            self.preset_manager.save_preset(name, weights, set_selected=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save preset: {e}")
            return

        self.refresh_preset_list()
        self.apply_active_weights()
        self.active_preset_name = name
        self.weight_status.config(text=f"Applied {name}")
        self.preset_name_var.set("")
        # Refresh Combatants in case this overwrites a preset already assigned
        # to one or more characters (their GS should reflect the new weights).
        if self.context.heroes_tab is not None:
            try:
                self.context.heroes_tab.refresh_heroes()
            except Exception:
                pass

    def on_delete_selected_presets(self):
        """Delete one or more selected presets, with confirmation."""
        sel = self.preset_tree.selection()
        if not sel:
            messagebox.showwarning(
                "No Preset Selected",
                "Please select one or more presets to delete."
            )
            return

        if self.preset_manager.is_corrupted():
            messagebox.showwarning(
                "Presets File Corrupted",
                "The presets file is corrupted and cannot be edited until "
                "you save a new preset (which will back up the broken file)."
            )
            return

        # Treeview iids are the preset names (set on insert), so the
        # selection tuple IS the list of names to delete.
        names = list(sel)
        listing = "\n".join(f"  • {n}" for n in names)
        confirm_msg = (
            f"Are you sure you want to delete the following preset"
            f"{'s' if len(names) > 1 else ''}?\n\n{listing}\n\nThis cannot be undone."
        )
        if not messagebox.askyesno("Confirm Delete", confirm_msg):
            return

        try:
            self.preset_manager.delete_presets(names)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete preset(s): {e}")
            return

        # Reset every character that pointed at any deleted preset back to default.
        if self.character_preset_manager is not None:
            for n in names:
                try:
                    self.character_preset_manager.remove_assignments_to(n)
                except Exception:
                    pass

        # If the currently-applied preset was deleted, downgrade status to
        # "Applied custom weights" but keep the spinbox values as-is.
        if self.active_preset_name in names:
            self.active_preset_name = None
            self.weight_status.config(text="Applied custom weights")

        self.refresh_preset_list()
        # Refresh Combatants tab so its Preset column and per-character GS update.
        if self.context.heroes_tab is not None:
            try:
                self.context.heroes_tab.refresh_heroes()
            except Exception:
                pass

    # ============================================================
    # Helpers
    # ============================================================

    def refresh_preset_list(self):
        """Repopulate the Treeview from PresetManager (alphabetical) and
        highlight the currently-applied preset, if any.

        Each row carries the ASSIGNED_ICON in its left gutter column (#0)
        when at least one character in CharacterPresetManager points at
        the preset -- a visual cue that deleting or editing that preset
        will affect Combatants-tab GS for those characters. Unlinked rows
        get an empty string in the gutter so the name column starts at
        the same x-coordinate for every row.

        Iid scheme: each row's iid IS the preset name. This makes lookup
        from selection() trivial (no separate index->name mapping) and
        is safe because PresetManager guarantees unique preset names.

        The highlight matters most on program start: without it, the
        Treeview loads with no row selected, so the user has no visual
        indication of which preset's weights are currently in effect.
        On Apply / Save / Delete the preset_manager's selected_preset is
        updated, so subsequent refreshes reflect the right row.
        """
        # Clear all existing rows.
        for iid in self.preset_tree.get_children():
            self.preset_tree.delete(iid)

        names = list(self.preset_manager.get_preset_names())

        # Which preset names are currently assigned to >=1 character?
        assigned_names = set()
        if self.character_preset_manager is not None:
            for preset_name in self.character_preset_manager.assignments.values():
                if preset_name:
                    assigned_names.add(preset_name)

        for name in names:
            icon = ASSIGNED_ICON if name in assigned_names else ""
            # iid=name makes the selection->name lookup direct (see
            # on_apply_selected_preset / on_delete_selected_presets).
            # values=(icon, name) puts the marker in the "marker" data
            # column and the preset name in the "name" data column.
            self.preset_tree.insert(
                "", tk.END, iid=name, values=(icon, name)
            )

        selected = self.preset_manager.selected_preset
        if selected and selected in names:
            self.preset_tree.selection_set(selected)
            self.preset_tree.focus(selected)
            self.preset_tree.see(selected)

    def _on_preset_key(self, event):
        """Letter-key navigation: pressing 'A' jumps to the next preset
        starting with 'A' (case-insensitive), cycling at the end of the
        list. Matches against the preset name (which is also the row's
        iid), so the marker glyph in the gutter doesn't affect matching.

        Returns 'break' on a successful jump to prevent Tk's default
        Treeview behavior from also reacting. Falls through (returns None)
        for non-alphanumeric keys so arrow keys etc. still work.
        """
        char = event.char
        if not char or not char.isalnum():
            return None  # arrows, ctrl, etc. -- let Tk handle them
        char_lower = char.lower()

        items = self.preset_tree.get_children()  # tuple of iids (=names)
        total = len(items)
        if total == 0:
            return "break"

        # Start one past the current selection so repeated presses cycle
        # through all matches. Wrap to 0 at the end.
        sel = self.preset_tree.selection()
        if sel:
            try:
                start = (items.index(sel[0]) + 1) % total
            except ValueError:
                start = 0
        else:
            start = 0

        for offset in range(total):
            idx = (start + offset) % total
            iid = items[idx]
            # iid is the preset name.
            if iid.lower().startswith(char_lower):
                self.preset_tree.selection_set(iid)
                self.preset_tree.focus(iid)
                self.preset_tree.see(iid)
                return "break"
        return "break"  # no match -- still swallow so Tk doesn't try anything

    def _set_sliders(self, weights: dict):
        """Push a weights dict into the spinbox vars (missing stats default to 1.0)."""
        for stat, var in self.stat_weight_vars.items():
            var.set(float(weights.get(stat, 1.0)))

    def _reset_sliders_to_default(self):
        for var in self.stat_weight_vars.values():
            var.set(1.0)

    def _spinbox_wheel(self, event, spinbox):
        """Increment/decrement a Spinbox on mouse-wheel events.

        tk.Spinbox doesn't bind <MouseWheel> by default. event.delta is
        positive for wheel-up (increment) and negative for wheel-down on
        Windows; macOS / Linux differ in magnitude but the sign is
        consistent. invoke() handles from_/to bounds for us, so we don't
        have to clamp the value here.
        """
        if event.delta > 0:
            spinbox.invoke("buttonup")
        elif event.delta < 0:
            spinbox.invoke("buttondown")
        return "break"
