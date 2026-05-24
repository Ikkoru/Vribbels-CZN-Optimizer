"""
Heroes/Combatants display tab.

Provides sortable list of heroes with detailed gear display.


Where to look when you want to change X
=======================================

  Hero row list (left side):       refresh_heroes() -- rebuilds from
                                   self.optimizer.character_info, applies
                                   the configured sort, restores the
                                   previous selection from SettingsManager.
  Row click / keyboard nav:        _on_row_click, _on_row_right_click,
                                   _navigate_hero_list. The list is a
                                   canvas of frames (not a Treeview), so
                                   keyboard nav is hand-rolled and the
                                   canvas needs focus to receive Up/Down.
  Detail panel (right side):       show_hero_details() -- character frame,
                                   partner card, equipped MFs frame.
  Per-piece GS in detail panel:    uses compute_fragment_gs() with the
                                   per-character preset's weights, NOT
                                   the globally-Apply'd weights. The
                                   character-list GS column does the same;
                                   they must agree.
  Per-character preset assignment: _get_assigned_preset / _weights_for_preset
                                   / _refresh_preset_dropdown_values. The
                                   dropdown uses DEFAULT_PRESET_LABEL as
                                   a sentinel meaning "no assignment ->
                                   fall back to global weights" (which
                                   themselves come from scoring_tab's
                                   apply_active_weights -> preset_manager).
  Partner card (3 states):         show_hero_details's partner section.
                                   Known partner -> full card; partner_id
                                   with unknown res_id -> "Unknown partner
                                   (res_id X)"; no partner -> "None".
  Set name color:                  Combatants > Equipped MFs frame. Counts
                                   actual equipped pieces of the same set
                                   and compares to the set's pieces
                                   requirement -- white if complete, dim
                                   grey if partial.
  Right-click level checkpoint:    _on_row_right_click ->
                                   _prompt_level_checkpoint -> writes to
                                   LevelDataManager and refreshes.
  Selection memory:                refresh_heroes reads
                                   SettingsManager["last_selected_character"]
                                   to choose the initial select_hero_row
                                   target; select_hero_row writes it back
                                   on every successful selection.

Cross-file conventions
======================
- hero_data_list entries carry name + display fields + res_id + exp.
  res_id/exp come from CharacterInfo (the optimizer's per-hero data) and
  are needed by the right-click level-checkpoint flow.
- DEFAULT_PRESET_LABEL is a UI string only -- never persisted. The
  CharacterPresetManager stores None for "use default", and we translate
  to/from the label string at the dropdown boundary.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from typing import Optional

from ui.base_tab import BaseTab
from ui.context import AppContext
from game_data import (
    EQUIPMENT_SLOTS, SETS, STATS, RARITY_COLORS, RARITY_BG_COLORS,
    RARITY_STARTING_SUBSTATS, ATTRIBUTE_COLORS,
    get_character_by_name, get_partner, get_partner_stats,
    get_partner_passive_info, get_potential_stat_bonus
)
from models import Stat
from models.memory_fragment import compute_gs_bounds, normalize_gs


# UI label shown when a character has no preset assigned (default 1.0 weights).
DEFAULT_PRESET_LABEL = "Default Preset (all weights are 1.0)"


def compute_fragment_gs(
    fragment, weights: dict, bounds: Optional[tuple[float, float]] = None
) -> float:
    """Pure function: gear score for one fragment using the given stat
    weights, normalized to a 0-100 scale via the preset's theoretical bounds.

    Substats only -- main stats are intentionally excluded (matches the
    formulas in memory_fragment.py and scoring_tab.py). However, the
    fragment's main stat type DOES affect normalization: bounds passed in
    (or computed lazily here) exclude that stat from the substat pool, so
    100 is reachable for any fragment given perfect substats relative to
    its main-stat constraint (Philosophy B).

    Args:
        weights: stat_name -> weight (missing keys default to 1.0).
        bounds:  pre-computed (min_raw, max_raw) for these weights with the
                 fragment's main stat excluded. Pass it in when scoring
                 many fragments under the same preset -- cache by main_stat
                 name to share across fragments with the same main.
                 Computed lazily otherwise.
    """
    raw = 0.0
    for sub in fragment.substats:
        stat_info = STATS.get(
            sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1.0, 0.5)
        )
        max_roll = stat_info[3]
        if max_roll <= 0:
            continue
        normalized = sub.value / (max_roll * sub.roll_count)
        weight = weights.get(sub.name, 1.0)
        raw += normalized * sub.roll_count * weight
    raw *= 10

    if bounds is None:
        main_name = fragment.main_stat.name if fragment.main_stat else None
        bounds = compute_gs_bounds(weights, exclude_stat=main_name)
    return normalize_gs(raw, bounds)


class HeroesTab(BaseTab):
    """Heroes/Combatants list and detail display."""

    def __init__(self, parent: tk.Widget, context: AppContext):
        super().__init__(parent, context)
        self._init_state()
        self.setup_ui()
        self._maybe_warn_character_preset_corrupted()

    def _maybe_warn_character_preset_corrupted(self):
        """If character_preset.json was unreadable on load, tell the user once.
        Same flow as presets.json: defaults are applied, file is locked from
        writes until the user explicitly chooses to save (which quarantines)."""
        cpm = self.context.character_preset_manager
        if cpm is None or not cpm.is_corrupted():
            return
        messagebox.showwarning(
            "Character Preset File Corrupted",
            f"The per-character preset file appears to be invalid:\n\n"
            f"{cpm.corruption_error}\n\n"
            f"File: {cpm.assignments_file}\n\n"
            f"All characters have been reset to the default preset (all "
            f"weights 1.0). The file will not be edited unless you make a "
            f"new assignment from the dropdown (you'll be prompted to back "
            f"up the broken file first)."
        )

    def _init_state(self):
        """Initialize all state variables."""
        # Sorting state
        self.hero_sort_col = "name"
        self.hero_sort_reverse = False

        # Canvas/List widgets (set in setup_ui)
        self.hero_canvas = None
        self.hero_list_frame = None
        self.hero_canvas_window = None
        self.hero_row_widgets = []
        self.hero_data_list = []
        self.hero_col_char_widths = None
        self.selected_hero_index = -1
        self.hero_header_labels = []

        # Detail widgets (set in setup_ui)
        self.user_info_label = None
        self.hero_detail_name = None
        self.hero_char_info = None
        self.hero_partner_text = None
        self.hero_stats_label = None
        self.gear_frames = {}
        self.gear_labels = {}

    def setup_ui(self):
        """Setup the Heroes tab UI."""
        # User info frame at top
        user_frame = ttk.Frame(self.frame)
        user_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        self.user_info_label = tk.Label(
            user_frame,
            text="No data loaded",
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg=self.colors["fg"],
            anchor="w"
        )
        self.user_info_label.pack(side=tk.LEFT)

        # Main content: hero list on left, details on right
        content_pane = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        content_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Left: Hero list
        hero_list_container = ttk.Frame(content_pane)
        content_pane.add(hero_list_container, weight=1)

        # Hero list header - match original structure
        hero_header_frame = tk.Frame(hero_list_container, bg=self.colors["bg_lighter"])
        hero_header_frame.pack(fill=tk.X)

        # Use character widths for consistency between headers and data rows
        col_char_widths = [12, 6, 9, 10, 7, 5, 5, 14]  # +1 col for Preset
        col_names = ["Combatant", "Grade", "Attribute", "Class", "Level", "Ego", "GS", "Preset"]
        col_keys = ["name", "grade", "attribute", "class", "level", "ego", "gs", "preset"]

        self.hero_header_labels = []
        for i, (name, char_width) in enumerate(zip(col_names, col_char_widths)):
            # Left-align Combatant (index 0) and Preset (index 7) columns;
            # all other columns stay centered.
            anchor = tk.W if i in (0, 7) else tk.CENTER
            lbl = tk.Label(hero_header_frame, text=name, width=char_width,
                          bg=self.colors["bg_lighter"], fg=self.colors["fg"],
                          font=("Segoe UI", 9, "bold"),
                          anchor=anchor,
                          cursor="hand2")
            # Last column (Preset) absorbs any leftover row width — keeps its
            # 14-char minimum but stretches so long preset names aren't
            # truncated when there's space available.
            if i == 7:
                lbl.pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
            else:
                lbl.pack(side=tk.LEFT, padx=1)
            lbl.bind("<Button-1>", lambda e, k=col_keys[i]: self.sort_heroes(k))
            lbl.bind("<Enter>", lambda e, l=lbl: l.config(fg=self.colors["accent"]))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(fg=self.colors["fg"]))
            self.hero_header_labels.append(lbl)

        self.hero_col_char_widths = col_char_widths  # Store character widths for data rows

        # Scrollable hero list
        hero_canvas_frame = ttk.Frame(hero_list_container)
        hero_canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.hero_canvas = tk.Canvas(
            hero_canvas_frame,
            bg=self.colors["bg"],
            highlightthickness=0
        )
        hero_vsb = ttk.Scrollbar(hero_canvas_frame, orient=tk.VERTICAL, command=self.hero_canvas.yview)
        self.hero_canvas.configure(yscrollcommand=hero_vsb.set)

        self.hero_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hero_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.hero_list_frame = tk.Frame(self.hero_canvas, bg=self.colors["bg"])
        self.hero_canvas_window = self.hero_canvas.create_window(
            (0, 0),
            window=self.hero_list_frame,
            anchor="nw"
        )

        self.hero_canvas.bind("<Configure>", self._on_hero_canvas_configure)
        self.hero_list_frame.bind("<Configure>", lambda e: self._update_hero_scrollregion())

        # Up/Down navigate the character list when the canvas has focus.
        # Binding only fires when this widget is the focus, so the dropdown's
        # native arrow-key handling is unaffected when *it* has focus.
        self.hero_canvas.configure(takefocus=1)
        self.hero_canvas.bind("<Up>",   lambda e: self._navigate_hero_list(-1))
        self.hero_canvas.bind("<Down>", lambda e: self._navigate_hero_list(+1))
        # Windows-Explorer-style letter-jump: press a letter to select the
        # next hero whose name starts with that letter (case-insensitive,
        # cycling). Non-alphanumeric keys fall through so arrow keys above
        # still work. See _on_hero_canvas_key for details.
        self.hero_canvas.bind("<KeyPress>", self._on_hero_canvas_key)

        # Right: Hero details
        hero_detail_container = ttk.Frame(content_pane)
        content_pane.add(hero_detail_container, weight=2)
        self.hero_detail_container = hero_detail_container  # for width-clamp lookups

        # Title row: combatant name on left, "Assign preset" dropdown on right.
        title_row = ttk.Frame(hero_detail_container)
        title_row.pack(fill=tk.X, pady=(0, 5))

        self.hero_detail_name = ttk.Label(
            title_row, text="Select a combatant",
            font=("Segoe UI", 14, "bold")
        )
        self.hero_detail_name.pack(side=tk.LEFT, anchor=tk.W)

        # Right-aligned vertical group: label on top, combobox below.
        # `expand=True, fill=X` fills the leftover space between the name and
        # the partner-card right edge — the combobox then expands to that width
        # automatically, no manual width math required.
        preset_group = ttk.Frame(title_row)
        preset_group.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        self.preset_assign_label = ttk.Label(
            preset_group,
            text="Assign preset to (no selection) for custom Gear Score:"
        )
        self.preset_assign_label.pack(anchor=tk.W)

        self.preset_assign_combo = ttk.Combobox(
            preset_group, state="readonly", values=[DEFAULT_PRESET_LABEL]
        )
        self.preset_assign_combo.set(DEFAULT_PRESET_LABEL)
        self.preset_assign_combo.pack(anchor=tk.W, fill=tk.X)
        self.preset_assign_combo.bind(
            "<<ComboboxSelected>>", self._on_preset_combo_change
        )

        # Internal: name of the character whose row is currently selected
        # (used by the combobox change handler to know who to assign to).
        self._current_detail_hero = None

        # Debounce handle for resize-triggered combobox geometry recompute.
        self._combo_resize_after_id = None
        hero_detail_container.bind("<Configure>", self._on_detail_resize)

        # Info frame with Character and Partner Card
        # Character takes only needed space, Partner Card fills remaining with text wrapping
        info_frame = ttk.Frame(hero_detail_container)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        char_frame = ttk.LabelFrame(info_frame, text="Character", padding=5)
        char_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        self.hero_char_info = ttk.Label(char_frame, text="", justify=tk.LEFT)
        self.hero_char_info.pack(anchor=tk.W)

        partner_frame = ttk.LabelFrame(info_frame, text="Partner", padding=5)
        partner_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        # Right-click on the partner pane (the LabelFrame OR the Text widget
        # inside) opens the "Add confirmed level" dialog for the currently
        # equipped partner. Same flow as for characters; the partner res_id
        # and exp come from char_info.partner_res_id / char_info.partner_exp,
        # populated by the optimizer when the snapshot is parsed.
        partner_frame.bind("<Button-3>", self._on_partner_right_click)
        # Use a Text widget for the Partner pane (allows proper word-wrap of
        # the multi-line description). Wrap it in a sub-frame alongside a
        # vertical Scrollbar so long descriptions get an actual visible
        # scrollbar — the Text widget alone doesn't show one.
        partner_text_frame = ttk.Frame(partner_frame)
        partner_text_frame.pack(fill=tk.BOTH, expand=True)

        partner_scroll = ttk.Scrollbar(partner_text_frame, orient=tk.VERTICAL)
        self.hero_partner_text = tk.Text(
            partner_text_frame, wrap=tk.WORD, height=6,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            font=("Segoe UI", 9), bd=0, highlightthickness=0,
            padx=2, pady=2,
            yscrollcommand=partner_scroll.set,
        )
        partner_scroll.config(command=self.hero_partner_text.yview)
        partner_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.hero_partner_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.hero_partner_text.config(state=tk.DISABLED)
        # Right-click on the Text widget (where the partner description
        # actually renders) routes to the same handler as the parent frame.
        self.hero_partner_text.bind("<Button-3>", self._on_partner_right_click)

        stats_frame = ttk.LabelFrame(hero_detail_container, text="Build Stats", padding=5)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        self.hero_stats_label = ttk.Label(stats_frame, text="", justify=tk.LEFT)
        self.hero_stats_label.pack(anchor=tk.W)

        gear_outer_frame = ttk.LabelFrame(hero_detail_container, text="Equipped Memory Fragments", padding=5)
        gear_outer_frame.pack(fill=tk.BOTH, expand=True)

        self.gear_frames = {}
        self.gear_labels = {}

        gear_grid = ttk.Frame(gear_outer_frame)
        gear_grid.pack(fill=tk.BOTH, expand=True)

        # Slot positions matching original: (slot_num, row, col)
        slot_positions = [
            (3, 0, 0), (4, 0, 1),
            (2, 1, 0), (5, 1, 1),
            (1, 2, 0), (6, 2, 1),
        ]

        for slot_num, row, col in slot_positions:
            slot_name = EQUIPMENT_SLOTS.get(slot_num, f"Slot {slot_num}")

            frame = tk.Frame(gear_grid, bg=self.colors["bg_light"], relief=tk.RIDGE, bd=1)
            frame.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")

            header = tk.Label(frame, text=slot_name, font=("Segoe UI", 9, "bold"),
                            bg=self.colors["bg_light"], fg=self.colors["fg_dim"])
            header.pack(anchor=tk.W, padx=5, pady=(3, 0))

            main_stat = tk.Label(frame, text="", font=("Segoe UI", 9, "bold"),
                               bg=self.colors["bg_light"], fg=self.colors["orange"])
            main_stat.pack(anchor=tk.W, padx=5)

            sub_frames = []
            for i in range(4):
                sub_frame = tk.Frame(frame, bg=self.colors["bg_light"])
                sub_frame.pack(anchor=tk.W, padx=5, fill=tk.X)

                gs_contrib = tk.Label(sub_frame, text="", font=("Segoe UI", 7),
                                     bg=self.colors["bg_light"], fg=self.colors["accent"], width=3, anchor=tk.E)
                gs_contrib.pack(side=tk.LEFT)

                # Use Text widget for colored roll values
                sub_text = tk.Text(sub_frame, font=("Segoe UI", 8), height=1, width=40,
                                   bg=self.colors["bg_light"], fg=self.colors["fg"],
                                   bd=0, highlightthickness=0, padx=2, pady=0)
                sub_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
                # Configure tags for roll colors
                sub_text.tag_configure("max_roll", foreground=self.colors["green"])
                sub_text.tag_configure("min_roll", foreground=self.colors["red"])
                sub_text.tag_configure("normal", foreground=self.colors["yellow"])  # Mid-rolls in yellow
                sub_text.tag_configure("added", foreground=self.colors["fg"])  # Same as default
                sub_text.tag_configure("default", foreground=self.colors["fg"])
                sub_text.config(state=tk.DISABLED)

                sub_frames.append({"frame": sub_frame, "gs": gs_contrib, "text": sub_text})

            set_label = tk.Label(frame, text="", font=("Segoe UI", 8),
                               bg=self.colors["bg_light"], fg=self.colors["fg_dim"])
            set_label.pack(anchor=tk.W, padx=5, pady=(2, 0))

            # GS and Potential on same line
            gs_frame = tk.Frame(frame, bg=self.colors["bg_light"])
            gs_frame.pack(anchor=tk.W, padx=5, pady=(0, 3), fill=tk.X)

            gs_label = tk.Label(gs_frame, text="", font=("Segoe UI", 8, "bold"),
                               bg=self.colors["bg_light"], fg=self.colors["accent"])
            gs_label.pack(side=tk.LEFT)

            pot_label = tk.Label(gs_frame, text="", font=("Segoe UI", 8),
                                bg=self.colors["bg_light"], fg=self.colors["fg_dim"])
            pot_label.pack(side=tk.LEFT, padx=(10, 0))

            self.gear_frames[slot_num] = frame
            self.gear_labels[slot_num] = {
                "header": header,
                "main": main_stat,
                "subs": sub_frames,
                "set": set_label,
                "gs": gs_label,
                "potential": pot_label,
                "gs_frame": gs_frame
            }

        gear_grid.columnconfigure(0, weight=1)
        gear_grid.columnconfigure(1, weight=1)
        gear_grid.rowconfigure(0, weight=1)
        gear_grid.rowconfigure(1, weight=1)
        gear_grid.rowconfigure(2, weight=1)

    # Public API
    def refresh_heroes(self):
        """Refresh the heroes list."""
        # Clear existing rows
        for widget in self.hero_row_widgets:
            widget.destroy()
        self.hero_row_widgets.clear()
        self.hero_data_list.clear()
        self.selected_hero_index = -1

        # Update user info - match original format
        user = self.optimizer.user_info
        if user.nickname:
            user_text = (
                f"User: {user.nickname}  |  Level {user.level}  |  "
                f"Logins: {user.login_total}, Streak {user.login_continuous} (Best: {user.login_highest_continuous})"
            )
        else:
            user_text = "No user data available"
        self.user_info_label.config(text=user_text)

        # Get all heroes (from equipped gear or character info)
        all_heroes = set(self.optimizer.characters.keys()) | set(self.optimizer.character_info.keys())

        # Build hero data for sorting
        for hero in all_heroes:
            gear = self.optimizer.characters.get(hero, [])
            char_info = self.optimizer.character_info.get(hero)

            # Per-character GS: use this character's assigned preset weights.
            # Each fragment's bounds exclude its own main stat (Philosophy B),
            # so cache by main_stat across this character's pieces to avoid
            # recomputing bounds for the same (preset, main_stat) pair.
            preset_name = self._get_assigned_preset(hero)
            weights = self._weights_for_preset(preset_name)
            bounds_cache: dict = {}
            gs = 0.0
            for f in gear:
                main_name = f.main_stat.name if f.main_stat else None
                if main_name not in bounds_cache:
                    bounds_cache[main_name] = compute_gs_bounds(
                        weights, exclude_stat=main_name
                    )
                gs += compute_fragment_gs(f, weights, bounds_cache[main_name])
            preset_display = "-" if preset_name is None else preset_name

            hero_data = get_character_by_name(hero)
            grade = hero_data.get("grade", 0)
            attribute = hero_data.get("attribute", "Unknown")
            hero_class = hero_data.get("class", "Unknown")

            if char_info:
                level = char_info.level
                max_level = char_info.max_level
                ego = char_info.limit_break
                res_id = char_info.res_id
                exp = char_info.exp
            else:
                level = 0
                max_level = 0
                ego = 0
                res_id = 0
                exp = 0

            self.hero_data_list.append({
                "name": hero,
                "grade": grade,
                "attribute": attribute,
                "class": hero_class,
                "level": level,
                "max_level": max_level,
                "ego": ego,
                "gs": gs,
                "preset": preset_display,
                # res_id / exp drive the right-click "Add confirmed level"
                # checkpoint flow. They're 0 when char_info is missing (no
                # captured data for this hero) -- the right-click handler
                # treats 0 res_id as "can't record" and aborts cleanly.
                "res_id": res_id,
                "exp": exp,
            })

        # Sort heroes
        sort_key_map = {
            "name": lambda h: h["name"],
            "grade": lambda h: h["grade"],
            "attribute": lambda h: h["attribute"],
            "class": lambda h: h["class"],
            "level": lambda h: h["level"],
            "ego": lambda h: h["ego"],
            "gs": lambda h: h["gs"],
            "preset": lambda h: h["preset"],
        }

        key_func = sort_key_map.get(self.hero_sort_col, lambda h: h["name"])
        self.hero_data_list.sort(key=key_func, reverse=self.hero_sort_reverse)

        # Create rows with individually colored cells
        for i, h in enumerate(self.hero_data_list):
            level_str = f"{h['level']}/{h['max_level']}" if h['max_level'] > 0 else "-"
            ego_str = f"E{h['ego']}" if h['max_level'] > 0 else "-"
            gs_str = f"{h['gs']:.0f}" if h['gs'] > 0 else "-"

            row_frame = tk.Frame(self.hero_list_frame, bg=self.colors["bg"])
            row_frame.pack(fill=tk.X)

            # Store reference to row data
            row_frame.hero_index = i
            row_frame.hero_name = h["name"]

            # Column values
            values = [h["name"], f"{h['grade']}*", h["attribute"], h["class"],
                      level_str, ego_str, gs_str, h["preset"]]

            labels = []
            for j, (val, char_width) in enumerate(zip(values, self.hero_col_char_widths)):
                # Determine color - only attribute column (index 2) gets colored
                if j == 2:  # Attribute column
                    fg_color = ATTRIBUTE_COLORS.get(h["attribute"], self.colors["fg"])
                else:
                    fg_color = self.colors["fg"]

                # Left-align Combatant (j=0) and Preset (j=7); center the rest.
                row_anchor = tk.W if j in (0, 7) else tk.CENTER
                lbl = tk.Label(row_frame, text=val, width=char_width, anchor=row_anchor,
                              bg=self.colors["bg"], fg=fg_color, font=("Segoe UI", 9))
                # Mirror the header: Preset column stretches to fill leftover width.
                if j == 7:
                    lbl.pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
                else:
                    lbl.pack(side=tk.LEFT, padx=1)
                lbl.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx))
                lbl.bind("<Button-3>", lambda e, idx=i: self._on_row_right_click(e, idx))
                labels.append(lbl)

            row_frame.labels = labels
            row_frame.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx))
            row_frame.bind("<Button-3>", lambda e, idx=i: self._on_row_right_click(e, idx))
            self.hero_row_widgets.append(row_frame)

        # Restore the previously-selected character so refreshes (preset
        # apply, data reload) and program restarts don't snap selection
        # back to row 0. The persisted name comes from SettingsManager,
        # written every time select_hero_row succeeds. If the saved name
        # isn't in the rebuilt list (renamed, removed, not in this user's
        # captured data), fall back to row 0 -- same as the previous
        # always-row-0 behavior.
        if self.hero_row_widgets:
            target_idx = 0
            sm = getattr(self.context, "settings_manager", None)
            last_name = sm.get("last_selected_character") if sm else None
            if last_name:
                for i, h in enumerate(self.hero_data_list):
                    if h["name"] == last_name:
                        target_idx = i
                        break
            self.select_hero_row(target_idx)

        self._update_hero_scrollregion()

    # Sorting and display
    def sort_heroes(self, col: str):
        """Sort heroes list by column"""
        if col == self.hero_sort_col:
            self.hero_sort_reverse = not self.hero_sort_reverse
        else:
            self.hero_sort_col = col
            self.hero_sort_reverse = col in ["gs", "grade", "ego"]

        self.refresh_heroes()

    def _on_row_click(self, idx: int):
        """Click handler for hero rows. Selects the row AND moves keyboard
        focus to the hero canvas so subsequent Up/Down keys navigate the list
        (instead of being captured by whatever was focused before — typically
        the preset dropdown)."""
        try:
            self.hero_canvas.focus_set()
        except Exception:
            pass
        self.select_hero_row(idx)

    def _on_row_right_click(self, event, idx: int):
        """Right-click handler: shows a context menu with the option to
        record a confirmed in-game level for this character. Recorded
        checkpoints persist to presets/level_data.json and get applied to
        the active exp table at load time, so the next refresh / restart
        reflects them in the displayed level.

        The right-click also selects the row (so the user has visual
        feedback about which character the menu is acting on) before the
        menu pops up.
        """
        self._on_row_click(idx)
        if idx < 0 or idx >= len(self.hero_data_list):
            return
        hero = self.hero_data_list[idx]

        menu = tk.Menu(self.hero_canvas, tearoff=0)
        menu.add_command(
            label=f"Add confirmed level for {hero['name']}...",
            command=lambda h=hero: self._prompt_level_checkpoint(h),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            # tk_popup grabs the pointer; releasing the grab is good
            # practice and avoids subtle focus issues on some platforms.
            menu.grab_release()

    def _prompt_level_checkpoint(self, hero: dict):
        """Ask the user for the confirmed in-game level of `hero`, then
        record an (exp, level) checkpoint via LevelDataManager. On success,
        the augmented exp tables are reapplied immediately so the rest of
        the UI can refresh without a restart.

        Args:
            hero: a hero_data_list entry. Must include 'name', 'res_id',
                  and 'exp'. The current displayed level (if any) is used
                  as the dialog default to make typo recovery easier.
        """
        from tkinter import simpledialog, messagebox

        ldm = getattr(self.context, "level_data_manager", None)
        if ldm is None:
            messagebox.showerror(
                "Not Available",
                "Level data manager is not initialized."
            )
            return

        name = hero.get("name", "?")
        res_id = hero.get("res_id") or 0
        exp = hero.get("exp", 0)
        current_level = hero.get("level", 1)
        # res_id == 0 means we have no captured data for this hero (char_info
        # was missing during refresh_heroes), so we have no exp to anchor a
        # checkpoint on. Without exp, the data point is useless.
        if not res_id:
            messagebox.showerror(
                "Missing Data",
                f"Cannot record a checkpoint for {name}: no captured "
                f"data available for this character yet."
            )
            return

        # Bound at 1-62; the dialog will clamp invalid input on its own
        # but we also re-validate after to handle Cancel returning None.
        level = simpledialog.askinteger(
            "Confirm Level",
            f"What is {name}'s in-game level right now?\n\n"
            f"(Current snapshot exp: {exp})\n"
            f"Range: 1-62. Click Cancel to abort.",
            parent=self.hero_canvas,
            initialvalue=int(current_level) if current_level else 1,
            minvalue=1, maxvalue=62,
        )
        if level is None:
            return  # user cancelled

        try:
            ldm.add_checkpoint("characters", res_id=int(res_id),
                               name=name, exp=int(exp), level=int(level))
            ldm.apply_to_constants()
        except Exception as e:
            messagebox.showerror(
                "Save Failed",
                f"Could not save checkpoint: {e}"
            )
            return

        # Refresh so the new level threshold flows through to all displays.
        try:
            self.refresh_heroes()
        except Exception:
            pass

        messagebox.showinfo(
            "Checkpoint Saved",
            f"Recorded: {name} at exp={exp} is level {level}.\n\n"
            f"This data point now anchors the level lookup for all "
            f"characters; future calculations will use it."
        )

    def _on_partner_right_click(self, event):
        """Right-click handler for the Partner card. Pops the same context
        menu as the hero rows, but for the partner currently equipped on
        whichever character is displayed in the detail panel."""
        hero = self._current_detail_hero
        if not hero or hero not in self.optimizer.character_info:
            return
        char_info = self.optimizer.character_info[hero]
        partner_res_id = getattr(char_info, "partner_res_id", 0) or 0
        if not partner_res_id:
            return  # no partner equipped, nothing to confirm

        partner_name = getattr(char_info, "partner_name", "") or f"res_id {partner_res_id}"
        menu = tk.Menu(self.hero_partner_text, tearoff=0)
        menu.add_command(
            label=f"Add confirmed level for {partner_name}...",
            command=lambda: self._prompt_partner_level_checkpoint(char_info),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _prompt_partner_level_checkpoint(self, char_info):
        """Same flow as _prompt_level_checkpoint but routed to the
        'partners' category in LevelDataManager. Reads partner_res_id,
        partner_exp, partner_level, partner_name off the supplied
        CharacterInfo (populated by the optimizer at snapshot load)."""
        from tkinter import simpledialog, messagebox

        ldm = getattr(self.context, "level_data_manager", None)
        if ldm is None:
            messagebox.showerror("Not Available",
                                 "Level data manager is not initialized.")
            return

        partner_res_id = getattr(char_info, "partner_res_id", 0) or 0
        partner_exp = getattr(char_info, "partner_exp", 0) or 0
        partner_level = getattr(char_info, "partner_level", 1) or 1
        partner_name = getattr(char_info, "partner_name", "") or "?"
        if not partner_res_id:
            messagebox.showerror("Missing Data",
                                 "No partner equipped on this character.")
            return

        # Partners max at level 60 (not 62 like characters); enforce that
        # in the dialog so the user can't enter an impossible level.
        level = simpledialog.askinteger(
            "Confirm Partner Level",
            f"What is {partner_name}'s in-game level right now?\n\n"
            f"(Current snapshot exp: {partner_exp})\n"
            f"Range: 1-60. Click Cancel to abort.",
            parent=self.hero_partner_text,
            initialvalue=int(partner_level),
            minvalue=1, maxvalue=60,
        )
        if level is None:
            return

        try:
            ldm.add_checkpoint("partners", res_id=int(partner_res_id),
                               name=partner_name, exp=int(partner_exp),
                               level=int(level))
            ldm.apply_to_constants()
        except Exception as e:
            messagebox.showerror("Save Failed", f"Could not save checkpoint: {e}")
            return

        try:
            self.refresh_heroes()
        except Exception:
            pass

        messagebox.showinfo(
            "Checkpoint Saved",
            f"Recorded: {partner_name} at exp={partner_exp} is level {level}.\n\n"
            f"Future partner-level calculations will use this anchor."
        )

    def _navigate_hero_list(self, delta: int):
        """Move the hero-list selection by `delta` rows (e.g. -1 for Up, +1
        for Down) and scroll the new row into view. Returns "break" so the
        Canvas doesn't also scroll its content as a default reaction."""
        if not self.hero_row_widgets:
            return "break"
        cur = self.selected_hero_index if self.selected_hero_index >= 0 else 0
        new_idx = max(0, min(len(self.hero_row_widgets) - 1, cur + delta))
        if new_idx != self.selected_hero_index:
            self.select_hero_row(new_idx)
            self._scroll_row_into_view(new_idx)
        return "break"

    def _on_hero_canvas_key(self, event):
        """Letter-key navigation on the hero list: pressing 'A' jumps to the
        next hero whose name starts with 'A' (case-insensitive), cycling at
        the end. Mirror of the preset listbox handler in scoring_tab.

        Returns 'break' on a successful jump so the Canvas doesn't also
        scroll. Non-alphanumeric keys (arrows etc.) fall through to the
        canvas's other bindings.
        """
        char = event.char
        if not char or not char.isalnum():
            return None  # arrows/ctrl/etc. -- let other bindings run
        char_lower = char.lower()

        total = len(self.hero_data_list)
        if total == 0:
            return "break"

        # Start one past the current selection so repeated presses cycle
        # through all matches. Wrap to 0 at the end.
        cur = self.selected_hero_index if self.selected_hero_index >= 0 else -1
        start = (cur + 1) % total
        for offset in range(total):
            idx = (start + offset) % total
            name = self.hero_data_list[idx].get("name", "")
            if name.lower().startswith(char_lower):
                self.select_hero_row(idx)
                self._scroll_row_into_view(idx)
                return "break"
        return "break"  # no match -- still swallow so Tk doesn't do anything

    def _scroll_row_into_view(self, idx: int):
        """Ensure the row at `idx` is visible in the scrollable hero canvas.
        Scrolls minimally — only when the row is currently above or below the
        visible viewport."""
        if not (0 <= idx < len(self.hero_row_widgets)):
            return
        try:
            row = self.hero_row_widgets[idx]
            # Make sure geometry has been computed.
            self.hero_canvas.update_idletasks()
            row_y = row.winfo_y()
            row_h = row.winfo_height()
            canvas_h = self.hero_canvas.winfo_height()
            total_h = max(1, self.hero_list_frame.winfo_height())

            view_top = self.hero_canvas.canvasy(0)
            view_bottom = view_top + canvas_h

            if row_y < view_top:
                self.hero_canvas.yview_moveto(row_y / total_h)
            elif row_y + row_h > view_bottom:
                target = (row_y + row_h - canvas_h) / total_h
                self.hero_canvas.yview_moveto(max(0.0, target))
        except Exception:
            pass

    def select_hero_row(self, index: int):
        """Select a hero row and update display"""
        # Deselect previous - reset ALL labels to proper colors
        if 0 <= self.selected_hero_index < len(self.hero_row_widgets):
            old_row = self.hero_row_widgets[self.selected_hero_index]
            old_row.config(bg=self.colors["bg"])
            old_hero_data = self.hero_data_list[self.selected_hero_index]
            for j, lbl in enumerate(old_row.labels):
                lbl.config(bg=self.colors["bg"])
                # Restore attribute color for attribute column (index 2)
                if j == 2:
                    attr_color = ATTRIBUTE_COLORS.get(old_hero_data["attribute"], self.colors["fg"])
                    lbl.config(fg=attr_color)
                else:
                    lbl.config(fg=self.colors["fg"])

        # Select new
        self.selected_hero_index = index
        if 0 <= index < len(self.hero_row_widgets):
            new_row = self.hero_row_widgets[index]
            new_row.config(bg=self.colors["select"])
            new_hero_data = self.hero_data_list[index]
            for j, lbl in enumerate(new_row.labels):
                lbl.config(bg=self.colors["select"])
                # Keep attribute color for attribute column
                if j == 2:
                    attr_color = ATTRIBUTE_COLORS.get(new_hero_data["attribute"], self.colors["fg"])
                    lbl.config(fg=attr_color)
                else:
                    lbl.config(fg=self.colors["fg"])

            self.show_hero_details(new_hero_data["name"])

            # Persist so the selection survives preset apply, data reload,
            # and program restart. SettingsManager.set() is a no-op when
            # the value is unchanged, so this stays cheap even when
            # arrow-key navigation fires select_hero_row in rapid bursts.
            sm = getattr(self.context, "settings_manager", None)
            if sm is not None:
                sm.set("last_selected_character", new_hero_data["name"])

    def show_hero_details(self, hero_name: str):
        """Show detailed hero information including gear - matches original exactly"""
        self.hero_detail_name.config(text=hero_name)
        self._current_detail_hero = hero_name

        # Update the "Assign preset to X for custom Gear Score:" label and the
        # combobox state for this character.
        self.preset_assign_label.config(
            text=f"Assign preset to {hero_name} for custom Gear Score:"
        )
        self._refresh_preset_dropdown_values()
        assigned = self._get_assigned_preset(hero_name)
        if assigned is None:
            self.preset_assign_combo.set(DEFAULT_PRESET_LABEL)
        else:
            self.preset_assign_combo.set(assigned)

        char_info = self.optimizer.character_info.get(hero_name)
        if char_info:
            fb = char_info.friendship_bonus
            hero_data = get_character_by_name(hero_name)
            grade = hero_data.get("grade", "?")
            attribute = hero_data.get("attribute", "Unknown")
            hero_class = hero_data.get("class", "Unknown")

            # Build potential info string
            potential_lines = []
            if char_info.potential_50_level > 0 or char_info.potential_60_level > 0:
                if char_info.potential_50_level > 0:
                    stat_type_50, bonus_50 = get_potential_stat_bonus(
                        char_info.res_id, 50, char_info.potential_50_level
                    )
                    if stat_type_50:
                        potential_lines.append(f"  Node 5: Lv{char_info.potential_50_level} ({stat_type_50} +{bonus_50:.1f}%)")

                if char_info.potential_60_level > 0:
                    stat_type_60, bonus_60 = get_potential_stat_bonus(
                        char_info.res_id, 60, char_info.potential_60_level
                    )
                    if stat_type_60:
                        potential_lines.append(f"  Node 6: Lv{char_info.potential_60_level} ({stat_type_60} +{bonus_60:.1f}%)")

            potential_str = "\n".join(potential_lines) if potential_lines else "  None"

            char_text = (
                f"Grade: {grade}*  |  {attribute}  |  {hero_class}\n"
                f"Level: {char_info.level}/{char_info.max_level}\n"
                f"Ego Manifestation: E{char_info.limit_break}\n"
                f"Friendship Lv: {char_info.friendship_index}\n"
                f"  Bonus: ATK+{fb[0]}, DEF+{fb[1]}, HP+{fb[2]}\n"
                f"Potential:\n{potential_str}"
            )
            self.hero_char_info.config(text=char_text)

            if char_info.partner_name:
                # Get partner stats
                partner_stats = get_partner_stats(char_info.partner_res_id, char_info.partner_level)

                # Get partner metadata (grade and class)
                partner_data = get_partner(char_info.partner_res_id)
                partner_grade = partner_data.get("grade", 3)
                partner_class = partner_data.get("class", "Unknown")

                # Get partner passive and ego skill info
                passive_info = get_partner_passive_info(
                    char_info.partner_res_id, char_info.partner_limit_break
                )

                partner_text = (
                    f"{char_info.partner_name}  ({partner_grade}* {partner_class})\n"
                    f"Level: {char_info.partner_level}/{char_info.partner_max_level}  |  Ego: E{char_info.partner_limit_break}\n"
                    f"Stats: ATK+{partner_stats['atk']}, DEF+{partner_stats['def']}, HP+{partner_stats['hp']}\n"
                    f"\n{passive_info['passive_name']}\n"
                    f"{passive_info['passive_desc']}\n"
                    f"\n{passive_info['ego_name']} - {passive_info['ego_cost']} EP\n"
                    f"{passive_info['ego_desc']}"
                )
            elif char_info.partner_id:
                # A partner is equipped in-game but isn't in this build's
                # data (no entry in PARTNERS). optimizer.py recovers the
                # res_id from the raw inventory item even when the partner
                # is unknown, so we can show it here — that's the value the
                # user would add to partners.py.
                if char_info.partner_res_id:
                    partner_text = (
                        f"Unknown partner "
                        f"(res_id {char_info.partner_res_id}, "
                        f"instance {char_info.partner_id})"
                    )
                else:
                    # res_id couldn't be recovered (instance id not in raw
                    # char_items either — unusual). Show what we have.
                    partner_text = f"Unknown partner (instance {char_info.partner_id})"
            else:
                partner_text = "No partner equipped"
            # Update partner card Text widget
            self.hero_partner_text.config(state=tk.NORMAL)
            self.hero_partner_text.delete("1.0", tk.END)
            self.hero_partner_text.insert("1.0", partner_text)
            self.hero_partner_text.config(state=tk.DISABLED)
        else:
            self.hero_char_info.config(text="No character data available")
            # Update partner card Text widget
            self.hero_partner_text.config(state=tk.NORMAL)
            self.hero_partner_text.delete("1.0", tk.END)
            self.hero_partner_text.insert("1.0", "No partner data")
            self.hero_partner_text.config(state=tk.DISABLED)

        gear = self.optimizer.characters.get(hero_name, [])
        gear_by_slot = {p.slot_num: p for p in gear}
        total_gs = 0

        # Per-piece GS in this detail panel must match the per-character
        # GS shown in the character list (which uses the *assigned* preset),
        # not the globally-Apply'd weights. Bounds are per (preset, main
        # stat) under Philosophy B; cache across this character's pieces.
        detail_weights = self._weights_for_preset(self._get_assigned_preset(hero_name))
        detail_bounds_cache: dict = {}

        def _bounds_for(piece):
            main = piece.main_stat.name if piece.main_stat else None
            if main not in detail_bounds_cache:
                detail_bounds_cache[main] = compute_gs_bounds(
                    detail_weights, exclude_stat=main
                )
            return detail_bounds_cache[main]

        for slot_num in range(1, 7):
            labels = self.gear_labels.get(slot_num)
            if not labels:
                continue

            piece = gear_by_slot.get(slot_num)

            if piece:
                piece_gs = compute_fragment_gs(piece, detail_weights, _bounds_for(piece))
                total_gs += piece_gs
                rarity_color = RARITY_COLORS.get(piece.rarity_num, self.colors["fg"])
                bg_color = RARITY_BG_COLORS.get(piece.rarity_num, self.colors["bg_light"])

                # Update header to include gear level
                slot_name = EQUIPMENT_SLOTS.get(slot_num, f"Slot {slot_num}")
                labels["header"].config(text=f"{slot_name}  +{piece.level}", fg=rarity_color)

                if piece.main_stat:
                    main_text = f"{piece.main_stat.name}  +{piece.main_stat.format_value()}"
                    labels["main"].config(text=main_text, fg=rarity_color)
                else:
                    labels["main"].config(text="")

                num_starting = RARITY_STARTING_SUBSTATS.get(piece.rarity_num, 3)

                for i, sub_data in enumerate(labels["subs"]):
                    if i < len(piece.substats):
                        sub = piece.substats[i]

                        gs_contrib = sub.get_gs_contribution()
                        sub_data["gs"].config(text=f"{gs_contrib:.1f}")

                        # Get the Text widget
                        text_widget = sub_data["text"]

                        # Build stat name + total
                        stat_name = sub.name
                        total_val = sub.format_value()

                        # Get roll color info
                        roll_parts = self.format_roll_with_color(sub, sub_data["frame"], bg_color)

                        # Check if this is an added stat (type 2)
                        is_added = i >= num_starting

                        # Enable widget for editing
                        text_widget.config(state=tk.NORMAL)
                        text_widget.delete("1.0", tk.END)

                        # Determine base tag for stat name
                        base_tag = "added" if is_added else "default"

                        if sub.roll_count > 1:
                            # Format: "Stat +total (base | +upg1, +upg2)"
                            text_widget.insert(tk.END, f"{stat_name} +{total_val} (", base_tag)

                            base_shown = False
                            for idx, (roll_text, roll_color) in enumerate(roll_parts):
                                # Determine the tag based on color
                                if roll_color == self.colors["green"]:
                                    tag = "max_roll"
                                elif roll_color == self.colors["red"]:
                                    tag = "min_roll"
                                else:
                                    tag = "normal"

                                # First roll is base stat, rest are upgrades
                                if idx == 0:
                                    text_widget.insert(tk.END, roll_text, tag)
                                    base_shown = True
                                else:
                                    if idx == 1 and base_shown:
                                        text_widget.insert(tk.END, " | ", base_tag)
                                    elif idx > 1:
                                        text_widget.insert(tk.END, ", ", base_tag)
                                    text_widget.insert(tk.END, roll_text, tag)

                            text_widget.insert(tk.END, ")", base_tag)
                        else:
                            # Single roll - color the value if max/min
                            text_widget.insert(tk.END, f"{stat_name} +", base_tag)
                            if roll_parts and len(roll_parts) > 0:
                                roll_color = roll_parts[0][1]
                                if roll_color == self.colors["green"]:
                                    tag = "max_roll"
                                elif roll_color == self.colors["red"]:
                                    tag = "min_roll"
                                else:
                                    tag = base_tag
                                text_widget.insert(tk.END, total_val, tag)
                            else:
                                text_widget.insert(tk.END, total_val, base_tag)

                        # Disable widget and update background
                        text_widget.config(state=tk.DISABLED, bg=bg_color)

                        sub_data["frame"].config(bg=bg_color)
                        sub_data["gs"].config(bg=bg_color)
                    else:
                        text_widget = sub_data["text"]
                        text_widget.config(state=tk.NORMAL)
                        text_widget.delete("1.0", tk.END)
                        text_widget.config(state=tk.DISABLED, bg=bg_color)
                        sub_data["gs"].config(text="", bg=bg_color)
                        sub_data["frame"].config(bg=bg_color)

                set_pieces = piece.get_set_pieces()
                # Get bonus description from SETS
                set_info = SETS.get(piece.set_id)
                bonus_text = set_info.get("bonus", "") if set_info else ""
                # Count how many of THIS character's other equipped pieces
                # belong to the same set (piece.get_set_pieces() is the set's
                # REQUIRED count, not the equipped count -- it's a property of
                # the set definition, not the current loadout).
                equipped_in_set = sum(1 for p in gear if p.set_id == piece.set_id)
                required_pieces = set_info.get("pieces", 999) if set_info else 999
                set_complete = equipped_in_set >= required_pieces
                # Set name shows white (live) when the equipped count meets
                # the set's required-pieces threshold, dim grey otherwise --
                # gives an at-a-glance signal for which set bonuses are
                # actually active for this character.
                labels["set"].config(
                    text=f"{piece.set_name} ({set_pieces}) {bonus_text}",
                    fg=self.colors["fg"] if set_complete else self.colors["fg_dim"],
                )

                labels["gs"].config(text=f"GS: {piece_gs:.0f}")

                # Add potential display
                if piece.potential_low != piece.potential_high:
                    pot_text = f"Potential: {piece.potential_low:.0f}-{piece.potential_high:.0f}"
                else:
                    pot_text = ""
                labels["potential"].config(text=pot_text)

                self.gear_frames[slot_num].config(bg=bg_color)
                for widget in [labels["header"], labels["main"], labels["set"], labels["gs"], labels["potential"], labels["gs_frame"]]:
                    widget.config(bg=bg_color)
            else:
                bg_color = self.colors["bg_light"]
                # Reset header to just slot name
                slot_name = EQUIPMENT_SLOTS.get(slot_num, f"Slot {slot_num}")
                labels["header"].config(text=slot_name, fg=self.colors["fg_dim"])
                labels["main"].config(text="Empty", fg=self.colors["fg_dim"])
                for sub_data in labels["subs"]:
                    sub_data["gs"].config(text="", bg=bg_color)
                    # Clear Text widget properly
                    text_widget = sub_data["text"]
                    text_widget.config(state=tk.NORMAL)
                    text_widget.delete("1.0", tk.END)
                    text_widget.config(state=tk.DISABLED, bg=bg_color)
                    sub_data["frame"].config(bg=bg_color)
                labels["set"].config(text="")
                labels["gs"].config(text="")
                labels["potential"].config(text="")

                self.gear_frames[slot_num].config(bg=bg_color)
                for widget in [labels["header"], labels["main"], labels["set"], labels["gs"], labels["potential"], labels["gs_frame"]]:
                    widget.config(bg=bg_color)

        if gear:
            stats = self.optimizer.calculate_build_stats(gear, hero_name)
            set_counts = {}
            for f in gear:
                set_counts[f.set_name] = set_counts.get(f.set_name, 0) + 1
            sets_str = " + ".join(f"{c}x{n}" for n, c in set_counts.items() if c >= 2)

            stats_text = (
                f"Total GS: {total_gs:.0f}  |  Sets: {sets_str}\n"
                f"ATK: {stats.get('ATK', 0):.0f}  |  DEF: {stats.get('DEF', 0):.0f}  |  HP: {stats.get('HP', 0):.0f}\n"
                f"CRate: {stats.get('CRate', 0):.1f}%  |  CDmg: {stats.get('CDmg', 0):.1f}%"
            )
            self.hero_stats_label.config(text=stats_text)
        else:
            self.hero_stats_label.config(text="No gear equipped")

    # ----- Per-character preset helpers ----------------------------------

    def _get_assigned_preset(self, hero_name: str) -> Optional[str]:
        """Return the preset name currently assigned to a character.

        Returns None if:
          - no character preset manager is wired up,
          - the file is corrupted,
          - the character has no assignment (default),
          - or the assigned preset has since been deleted.
        """
        cpm = self.context.character_preset_manager
        if cpm is None or cpm.is_corrupted():
            return None
        name = cpm.get_preset_for(hero_name)
        if name is None:
            return None
        # Defensive: assignment to a now-deleted preset → treat as default.
        # (Normal flow has scoring_tab clear these on delete; this guards
        # against edge cases like external file edits.)
        pm = self.context.preset_manager
        if pm is not None and pm.has_preset(name):
            return name
        return None

    def _weights_for_preset(self, preset_name: Optional[str]) -> dict:
        """Resolve a preset name to its weights dict. None => default (1.0 all).

        Returning an empty dict is fine: compute_fragment_gs uses
        ``weights.get(stat, 1.0)`` so missing keys collapse to 1.0.
        """
        if preset_name is None or self.context.preset_manager is None:
            return {}
        weights = self.context.preset_manager.get_preset(preset_name)
        return weights if weights is not None else {}

    def _refresh_preset_dropdown_values(self):
        """Repopulate combobox values: 'Default Preset...' first, then sorted presets."""
        pm = self.context.preset_manager
        names = pm.get_preset_names() if pm is not None else []
        values = [DEFAULT_PRESET_LABEL] + names
        self.preset_assign_combo.configure(values=values)
        self._recompute_combo_geometry()

    def _on_preset_combo_change(self, event):
        """User chose an option in the dropdown. Save assignment, refresh UI."""
        if self._current_detail_hero is None:
            return
        cpm = self.context.character_preset_manager
        if cpm is None:
            return

        # Same flow as scoring_tab.py for presets.json corruption: confirm,
        # quarantine, then save fresh. If the user declines, revert the combo.
        if cpm.is_corrupted():
            confirm = messagebox.askyesno(
                "Corrupted Character Preset File",
                f"The character preset file is corrupted:\n\n"
                f"{cpm.corruption_error}\n\n"
                f"Saving will rename the broken file (adding '_corrupted' to "
                f"its filename) and create a fresh one with this assignment.\n\n"
                f"Continue?"
            )
            if not confirm:
                # Restore combo to whatever the manager would currently say
                # for this character (which is "Default" while corrupted).
                assigned = self._get_assigned_preset(self._current_detail_hero)
                self.preset_assign_combo.set(
                    DEFAULT_PRESET_LABEL if assigned is None else assigned
                )
                return
            try:
                cpm.quarantine()
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to back up the broken file: {e}"
                )
                return

        selected = self.preset_assign_combo.get()
        new_value = None if selected == DEFAULT_PRESET_LABEL else selected
        try:
            cpm.set_preset_for(self._current_detail_hero, new_value)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save preset assignment: {e}")
            return

        # Refresh hero list (so the GS column and Preset column update for the
        # affected character), then re-show the same character's details.
        target_name = self._current_detail_hero
        self.refresh_heroes()
        for i, h in enumerate(self.hero_data_list):
            if h["name"] == target_name:
                self.select_hero_row(i)
                break

        # Refresh the Scoring tab's preset listbox so the link-symbol
        # markers reflect the new assignment state. Cheap and idempotent;
        # no-op when scoring_tab isn't wired up (standalone tests).
        scoring_tab = getattr(self.context, "scoring_tab", None)
        if scoring_tab is not None:
            try:
                scoring_tab.refresh_preset_list()
            except Exception:
                pass

    def _on_detail_resize(self, event):
        """Container resized — debounce the combobox geometry recompute by 100ms."""
        if self._combo_resize_after_id is not None:
            try:
                self.context.root.after_cancel(self._combo_resize_after_id)
            except Exception:
                pass
        try:
            self._combo_resize_after_id = self.context.root.after(
                100, self._recompute_combo_geometry
            )
        except Exception:
            pass

    def _recompute_combo_geometry(self):
        """Set the dropdown popup height (in items).

        Width is handled by pack/fill — the combobox fills the leftover space
        in title_row automatically, so we don't touch it here.

        Height: enough to show every preset, capped at ~3/4 of the current
        window height + 8 extra items.
        """
        self._combo_resize_after_id = None
        if not hasattr(self, 'preset_assign_combo'):
            return
        try:
            values = list(self.preset_assign_combo.cget("values")) or [
                DEFAULT_PRESET_LABEL
            ]
            win_h = self.context.root.winfo_height()
            if win_h > 1:
                row_px = 20  # rough per-row pixel estimate
                max_items_by_height = max(3, (win_h * 3 // 4) // row_px) + 8
                chosen_items = min(len(values), max_items_by_height)
                self.preset_assign_combo.configure(height=chosen_items)
        except Exception:
            pass  # widget might not be fully realized yet

    # Helper methods
    def _update_hero_scrollregion(self):
        """Update scroll region and ensure content stays at top when it fits"""
        self.hero_canvas.configure(scrollregion=self.hero_canvas.bbox("all"))
        # If content fits in view, reset to top
        if self.hero_canvas.bbox("all"):
            content_height = self.hero_canvas.bbox("all")[3]
            visible_height = self.hero_canvas.winfo_height()
            if content_height <= visible_height:
                self.hero_canvas.yview_moveto(0)

    def _on_hero_canvas_configure(self, event):
        """Handle canvas resize - update width and check scrolling"""
        self.hero_canvas.itemconfig(self.hero_canvas_window, width=event.width)
        # Check if we need to reset scroll position
        if self.hero_canvas.bbox("all"):
            content_height = self.hero_canvas.bbox("all")[3]
            if content_height <= event.height:
                self.hero_canvas.yview_moveto(0)

    def format_roll_with_color(self, sub: Stat, parent_frame: tk.Frame, bg_color: str):
        """Format a substat roll string with individual roll coloring"""
        stat_info = STATS.get(sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1.0, 0.5))
        max_roll = stat_info[3]
        min_roll = stat_info[4]

        # Build the display text with color info
        parts = []

        if sub.roll_count > 1 and sub.rolls:
            # Has upgrades - format: "Stat +total (base,+upg1,+upg2)"
            for roll in sub.rolls:
                if roll.stat_type in [1, 2]:  # Base or added stat
                    val_str = f"{roll.value:.0f}" if not sub.is_percentage else f"{roll.value:.1f}"
                    if roll.is_max_roll:
                        parts.append((val_str, self.colors["green"]))
                    elif roll.is_min_roll:
                        parts.append((val_str, self.colors["red"]))
                    else:
                        parts.append((val_str, self.colors["fg_dim"]))
                else:  # Upgrade roll (type 3)
                    val_str = f"+{roll.value:.0f}" if not sub.is_percentage else f"+{roll.value:.1f}"
                    is_min = abs(roll.value - min_roll) < 0.01
                    is_max = abs(roll.value - max_roll) < 0.01
                    if is_max:
                        parts.append((val_str, self.colors["green"]))
                    elif is_min:
                        parts.append((val_str, self.colors["red"]))
                    else:
                        parts.append((val_str, self.colors["fg_dim"]))

            return parts
        else:
            # Single roll - just color the total
            val_str = sub.format_value()
            if sub.rolls and len(sub.rolls) > 0:
                if sub.rolls[0].is_max_roll:
                    return [(val_str, self.colors["green"])]
                elif sub.rolls[0].is_min_roll:
                    return [(val_str, self.colors["red"])]
            return [(val_str, self.colors["fg"])]
