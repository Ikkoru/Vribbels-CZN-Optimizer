"""Inventory tab for viewing and filtering Memory Fragments.


Where to look when you want to change X
=======================================

  Filter checkboxes:     populate_main_stat_filters, populate_set_filters,
                         rarity / equipped / slot filter logic.
                         FILTER_SLOT_MAIN_STATS (below) drives the
                         per-slot main-stat checkboxes -- it's a local
                         dict separate from constants.SLOT_MAIN_STATS
                         because the UI needs a deterministic display
                         ORDER (the grid layout assumes specific row/col
                         positions for elemental DMG% etc.) that the
                         logical SLOT_MAIN_STATS doesn't constrain.
  ROW_TOP_PAD:           manual pixel spacing between checkbox-grid rows
                         to keep groups visually separated. Tied to the
                         FILTER_SLOT_MAIN_STATS row layout; if you reorder
                         that, revisit these too.
  Highest GS column:     refresh_inventory iterates each preset once per
                         fragment to compute the max GS. Bounds are
                         precomputed per preset (via
                         _presets_for_highest_gs) and reused across all
                         fragments to keep the per-cell cost low.
  Highest Pot. column:   same pattern, plus tracks the matching (low,
                         high) pair so display can show a range. The
                         pair comes from the SAME preset that produced
                         the max high (not a synthetic mix).
  Header tooltips:       _setup_header_tooltips -- custom Toplevel popups
                         with a 400ms delay; the standard Treeview doesn't
                         offer header tooltips so we hand-roll them.
  Sort direction:        first click on a column defaults to descending
                         except for the "Highest" columns which default
                         to ascending (the use case is finding bad MFs,
                         not best).
"""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from game_data import EQUIPMENT_SLOTS, RARITY_COLORS, SETS
# Item 5 (round 6): user-facing stat-name overrides (e.g. "Flat ATK" ->
# "ATK Flat", "CDmg" -> "CDMG%"). Applied when rendering the tree's Main /
# Sub columns so the Memory Fragments tab matches the Optimizer tab.
from game_data.constants import DISPLAY_NAMES
from models.memory_fragment import compute_gs_bounds, compute_fragment_potential
from ..base_tab import BaseTab
from .heroes_tab import compute_fragment_gs


# Display label -> canonical stat name (as stored in main_stat.name).
# The canonical names match the first element of STATS tuples and the values
# in FILTER_SLOT_MAIN_STATS, so slot-driven filter logic can use them directly.
MAIN_STAT_DISPLAY = [
    ("ATK%",      "ATK%"),
    ("DEF%",      "DEF%"),
    ("HP%",       "HP%"),
    ("Crit%",     "CRate"),
    ("CritDMG%",  "CDmg"),
    ("Passion%",  "Passion DMG%"),
    ("Justice%",  "Justice DMG%"),
    ("Order%",    "Order DMG%"),
    ("Void%",     "Void DMG%"),
    ("Instinct%", "Instinct DMG%"),
    ("Ego",       "Ego"),
]

# Per-slot list of valid main stats — authoritative for the filter UI.
# Source: user-provided gameplay spec (NOT game_data.SLOT_MAIN_STATS, which
# may include theoretically-possible-but-actually-impossible combinations
# like DEF% on slot IV/V).
# Slots 1/2/3 are intentionally absent: their mains (Flat ATK/DEF/HP) are
# always-pass, never shown in the UI.
FILTER_SLOT_MAIN_STATS = {
    4: ["ATK%", "HP%", "CRate", "CDmg"],
    5: ["ATK%", "HP%", "Passion DMG%", "Justice DMG%", "Order DMG%",
        "Void DMG%", "Instinct DMG%"],
    6: ["ATK%", "DEF%", "HP%", "Ego"],
}

# Layout grid for the Main Stats filter — fixed positions so checkboxes never
# jump around when slot selections change. Format: list of rows, each row is
# a list of display labels.
# Item 9 (round 7): "Ego" moved onto the first row, to the right of HP%
# (was on its own trailing row).
MAIN_STAT_LAYOUT = [
    ["ATK%", "DEF%", "HP%", "Ego"],
    ["Crit%", "CritDMG%"],
    ["Passion%", "Justice%", "Order%"],
    ["Void%", "Instinct%"],
]


class InventoryTab(BaseTab):
    """
    Inventory tab displays all Memory Fragments with filtering options.

    Provides filters by slot, set, main stat, rarity, and equipped status.
    Updates automatically when data is loaded via populate_set_filters().
    """

    def __init__(self, parent, context):
        super().__init__(parent, context)

        # Filter state
        self.inv_slot_vars = {}
        self.inv_set_vars = {}
        # Main stats: keyed by display label (e.g. "Crit%"), value is BooleanVar.
        # Always-on by default, switched off only by None button or slot toggle.
        self.inv_main_stat_vars = {}
        # Mirror the checkbox widgets so we can disable/enable them dynamically.
        self.inv_main_stat_checks = {}
        # Display label -> canonical name (filled at startup).
        self.inv_main_stat_canonical = {label: name for label, name in MAIN_STAT_DISPLAY}

        # Unknown main stats discovered in the loaded data (canonical name == raw).
        # Keyed by canonical name, displayed in their own row at the bottom.
        self.inv_unknown_main_stat_vars = {}
        self.inv_unknown_main_stat_checks = {}

        self.inv_unequipped_var = None
        self.inv_include_uncommon_var = None
        self.inv_only_assigned_presets_var = None

        # Inventory display state
        self.inv_tree = None
        # Default sort: potential descending. Lets the user immediately see
        # the highest-ceiling fragments without clicking a column.
        self.inv_sort_col = "potential"
        self.inv_sort_reverse = True
        self.inv_filtered_data = []

        # Tooltip state for column headers (see _setup_header_tooltips)
        self._tooltip_window = None
        self._tooltip_after_id = None
        self._last_tooltip_col = None

        # Frame for set checkboxes (populated dynamically)
        self.inv_set_frame_inner = None

        # Frames for the Main Stats filter (populated in setup_ui).
        self.inv_main_stat_frame_inner = None
        self.inv_main_unknown_frame = None  # row container for unknowns; hidden if empty.

        self.setup_ui()

    def setup_ui(self):
        """Setup the Inventory tab UI."""
        # Build two fonts for the Main Stats filter checkboxes:
        #   - normal: a copy of TkDefaultFont so it matches surrounding widgets
        #   - strike: the same font with overstrike enabled
        # We use tk.Checkbutton (not ttk) for those rows specifically because
        # ttk styles' font configuration is unreliable across themes — vista
        # and others ignore overstrike. tk.Checkbutton honors `font` directly.
        try:
            default = tkfont.nametofont("TkDefaultFont")
            self._mainstat_font = tkfont.Font(font=default)
            self._mainstat_strike_font = tkfont.Font(font=default)
            self._mainstat_strike_font.configure(overstrike=1)
        except Exception:
            # Last-resort fallback — explicit family/size shouldn't be needed,
            # but if the named-font lookup fails, plain tuples still work.
            self._mainstat_font = ("TkDefaultFont", 9)
            self._mainstat_strike_font = ("TkDefaultFont", 9, "overstrike")

        filter_frame = ttk.Frame(self.frame)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)

        # ----- Slots filter -----------------------------------------------
        slot_frame = ttk.LabelFrame(filter_frame, text="Slots", padding=3)
        slot_frame.pack(side=tk.LEFT, padx=(0, 10), anchor=tk.N)

        slot_inner = ttk.Frame(slot_frame)
        slot_inner.pack()

        # Left col: 3,2,1 (top->bottom). Right col: 4,5,6 (top->bottom).
        left_slots = [3, 2, 1]
        right_slots = [4, 5, 6]
        for row, (left_slot, right_slot) in enumerate(zip(left_slots, right_slots)):
            for col, slot_num in [(0, left_slot), (1, right_slot)]:
                slot_name = EQUIPMENT_SLOTS[slot_num]
                var = tk.BooleanVar(value=True)
                self.inv_slot_vars[slot_num] = var
                ttk.Checkbutton(
                    slot_inner, text=slot_name, variable=var,
                    command=lambda n=slot_num: self._on_slot_toggle(n)
                ).grid(row=row, column=col, sticky=tk.W, padx=2)

        slot_btn_frame = ttk.Frame(slot_frame)
        slot_btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(slot_btn_frame, text="All", width=5,
                   command=self.select_all_slots).pack(side=tk.LEFT, padx=1)
        ttk.Button(slot_btn_frame, text="None", width=5,
                   command=self.select_no_slots).pack(side=tk.LEFT, padx=1)

        # ----- Sets filter -----------------------------------------------
        set_frame = ttk.LabelFrame(filter_frame, text="Sets", padding=3)
        set_frame.pack(side=tk.LEFT, padx=(0, 10), anchor=tk.N)

        self.inv_set_frame_inner = ttk.Frame(set_frame)
        self.inv_set_frame_inner.pack()

        set_btn_frame = ttk.Frame(set_frame)
        set_btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(set_btn_frame, text="All", width=5,
                   command=self.select_all_sets).pack(side=tk.LEFT, padx=1)
        ttk.Button(set_btn_frame, text="None", width=5,
                   command=self.select_no_sets).pack(side=tk.LEFT, padx=1)

        # ----- Main Stats filter -----------------------------------------
        main_frame = ttk.LabelFrame(filter_frame, text="Main Stats", padding=3)
        main_frame.pack(side=tk.LEFT, padx=(0, 10), anchor=tk.N)

        self.inv_main_stat_frame_inner = ttk.Frame(main_frame)
        self.inv_main_stat_frame_inner.pack(anchor=tk.W)

        # Build the fixed layout. Every checkbox starts checked & enabled --
        # availability is then refined by _refresh_main_stat_availability().
        # 3px extra top padding before rows that begin a new "stat family":
        #   row 1 (Crit%/CritDMG%), row 2 (Passion%/Justice%/Order%).
        # Item 9 (round 7): Ego now lives on row 0 (right of HP%), so the
        # old row-4 padding entry is gone. Task 4 (round 9): bumped 2 -> 3
        # (+1px between ATK%/Crit% rows and between Crit%/Passion% rows).
        ROW_TOP_PAD = {1: 3, 2: 3}
        for row_idx, row_labels in enumerate(MAIN_STAT_LAYOUT):
            extra_top = ROW_TOP_PAD.get(row_idx, 0)
            for col_idx, label in enumerate(row_labels):
                var = tk.BooleanVar(value=True)
                self.inv_main_stat_vars[label] = var
                cb = self._make_mainstat_checkbutton(
                    self.inv_main_stat_frame_inner, label, var
                )
                cb.grid(row=row_idx, column=col_idx, sticky=tk.W,
                        padx=2, pady=(extra_top, 0))
                self.inv_main_stat_checks[label] = cb

        # Reserve a row below the layout for unknown main stats. Hidden until
        # populated; populate_set_filters() repopulates this every load.
        unknown_row = len(MAIN_STAT_LAYOUT)
        self.inv_main_unknown_frame = ttk.Frame(self.inv_main_stat_frame_inner)
        self.inv_main_unknown_frame.grid(
            row=unknown_row, column=0, columnspan=10, sticky=tk.W
        )
        # Empty by default; widgets get added dynamically.

        main_btn_frame = ttk.Frame(main_frame)
        main_btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(main_btn_frame, text="All", width=5,
                   command=self.select_all_main_stats).pack(side=tk.LEFT, padx=1)
        ttk.Button(main_btn_frame, text="None", width=5,
                   command=self.select_no_main_stats).pack(side=tk.LEFT, padx=1)

        # Initial availability sync (all slots checked at startup → everything on).
        self._refresh_main_stat_availability()

        # ----- Options ---------------------------------------------------
        opt_frame = ttk.Frame(filter_frame)
        opt_frame.pack(side=tk.LEFT, padx=(0, 10))

        self.inv_unequipped_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="Unequipped Only", variable=self.inv_unequipped_var,
                        command=self.refresh_inventory).pack(anchor=tk.W)

        # Item 10 (round 7): "Include Uncommon" now defaults to OFF, so the
        # list shows only Rare+ fragments unless the user opts in.
        self.inv_include_uncommon_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="Include Uncommon", variable=self.inv_include_uncommon_var,
                        command=self.refresh_inventory).pack(anchor=tk.W)

        # Restricts the new "Highest GS" column to only consider presets that
        # are currently assigned to characters in the Combatants tab. Useful
        # when many presets exist but only a few are actually in use.
        self.inv_only_assigned_presets_var = tk.BooleanVar(value=False)
        # a4 (this round): two-line label -- text after the colon drops to
        # the second line; "Pot." spelled out as "Potential".
        ttk.Checkbutton(opt_frame, text="Highest GS/Potential:\nAssigned Presets Only",
                        variable=self.inv_only_assigned_presets_var,
                        command=self.refresh_inventory).pack(anchor=tk.W)

        # ----- Treeview ---------------------------------------------------
        tree_frame = ttk.Frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        inv_cols = ("slot", "set", "lvl", "main", "sub1", "sub2", "sub3", "sub4",
                    "gs", "potential", "equipped", "highest_gs", "highest_potential")
        self.inv_tree = ttk.Treeview(tree_frame, columns=inv_cols, show="headings", height=25)

        for col, txt, w in [("slot", "Slot", 80), ("set", "Set", 140), ("lvl", "Level", 35),
                            ("main", "Main", 90), ("sub1", "Sub1", 90), ("sub2", "Sub2", 90),
                            ("sub3", "Sub3", 90), ("sub4", "Sub4", 90), ("gs", "GS", 35),
                            ("potential", "Potential", 50), ("equipped", "Equipped", 65),
                            ("highest_gs", "Highest GS", 65),
                            ("highest_potential", "Highest Potential", 312)]:
            self.inv_tree.heading(col, text=txt, command=lambda c=col.lower(): self.sort_inventory(c))
            # Item 7 (round 7): substat cells (sub1-4) are now left-aligned
            # too, joining slot/set/main/equipped. The numeric/short columns
            # (lvl, gs, potential, highest_gs) stay centered. Q4 (round 10):
            # highest_potential moved to the left-aligned group because its
            # "60-100 [preset]" format reads more naturally flush-left than
            # centered.
            self.inv_tree.column(col, width=w, anchor=tk.W if col in ["slot", "set", "main", "sub1", "sub2", "sub3", "sub4", "equipped", "highest_potential"] else tk.CENTER)

        inv_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=inv_scroll.set)
        self.inv_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inv_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Hook up the column-header tooltip system (only Highest GS has a
        # tooltip currently; others can be added by extending _column_tooltip_text).
        self._inv_cols = inv_cols
        self.inv_tree.bind("<Motion>", self._on_tree_motion)
        self.inv_tree.bind("<Leave>", lambda e: self._hide_tooltip())

    # ----- Slot filter ---------------------------------------------------

    def _on_slot_toggle(self, slot_num):
        """When a slot toggles, sync the Main Stats filter availability and refresh."""
        self._refresh_main_stat_availability()
        self.refresh_inventory()

    def select_all_slots(self):
        for var in self.inv_slot_vars.values():
            var.set(True)
        self._refresh_main_stat_availability()
        self.refresh_inventory()

    def select_no_slots(self):
        for var in self.inv_slot_vars.values():
            var.set(False)
        self._refresh_main_stat_availability()
        self.refresh_inventory()

    # ----- Set filter ----------------------------------------------------

    def select_all_sets(self):
        for var in self.inv_set_vars.values():
            var.set(True)
        self.refresh_inventory()

    def select_no_sets(self):
        for var in self.inv_set_vars.values():
            var.set(False)
        self.refresh_inventory()

    def populate_set_filters(self):
        """Populate set filter checkboxes.

        Item 6 (round 6): show ALL game sets (even those the current snapshot
        owns none of), ordered like the Optimizer tab -- 4-piece sets first,
        then 2-piece, alphabetical within each. Each label shows the number
        of that set currently owned in brackets, e.g. "Storm Caller (3)".
        Unknown numeric set IDs present in the data but absent from SETS are
        appended after the known sets so they remain filterable. Laid out in
        5 columns (was 4).

        Preserves selection state across reloads -- if a set was unchecked
        before a live update, it stays unchecked. New sets default to checked.
        """
        # Snapshot current selection state before tearing down widgets.
        previous = {name: var.get() for name, var in self.inv_set_vars.items()}

        for widget in self.inv_set_frame_inner.winfo_children():
            widget.destroy()
        self.inv_set_vars.clear()

        # Count how many of each set the current snapshot owns (by set_name).
        owned_counts: dict = {}
        for f in self.optimizer.fragments:
            owned_counts[f.set_name] = owned_counts.get(f.set_name, 0) + 1

        # Known sets from game data, ordered 4pc-first then 2pc, alpha within.
        ordered = sorted(
            SETS.values(),
            key=lambda s: (-s["pieces"], s["name"].lower()),
        )
        set_names = [s["name"] for s in ordered]

        # Append unknown numeric set IDs seen in the data but not in SETS.
        known_names = {s["name"] for s in SETS.values()}
        unknown_numeric = sorted(
            (n for n in owned_counts if n not in known_names and n.isdigit()),
            key=int,
        )
        set_names.extend(unknown_numeric)

        # Task 8 (round 8): proportional-font Checkbutton (set name) + a
        # separate count Label, gridded into TWO grid columns per logical
        # column: column 2c holds the name, column 2c+1 holds the "(N)".
        # a3 (this round): because grid sizes column 2c to its OWN widest
        # name, the count sits just past the longest name IN THAT COLUMN
        # (not a global max) -- so the gap is variable per set and no column
        # has its counts stranded far from short names. The count Label is
        # width=count_w + anchor=E so the brackets stay right-aligned within
        # the count column. Clicking the count toggles the box too.
        # n4 (round 8): the 2-piece (and unknown) sets start on a fresh row
        # below the 4-piece sets. a2 (this round): the separating gap is
        # halved (8 -> 4).
        ncols = 5
        name_pieces = {s["name"]: s["pieces"] for s in SETS.values()}
        # set_names is already ordered 4pc -> 2pc -> unknown, so a stable
        # split preserves the alphabetical ordering within each group.
        four_names = [n for n in set_names if name_pieces.get(n) == 4]
        rest_names = [n for n in set_names if name_pieces.get(n) != 4]
        # Task 4 follow-up (round 9): the count cell width is computed PER
        # LOGICAL COLUMN, not as a global maximum. Columns whose counts are
        # all short (e.g. single-digit "(N)") no longer get padded out to the
        # widest count's char width -- their bracketed numbers sit tight
        # against each column's longest name. The four_names / rest_names
        # slices match the row-major fill order used below (i % ncols).
        def _col_count_w(c):
            col_sets = four_names[c::ncols] + rest_names[c::ncols]
            if not col_sets:
                return 3
            return max(len(f"({owned_counts.get(n, 0)})") for n in col_sets)
        col_count_widths = [_col_count_w(c) for c in range(ncols)]

        def _add_set_cell(set_name, row, logical_col, top_pad):
            count = owned_counts.get(set_name, 0)
            var = tk.BooleanVar(value=previous.get(set_name, True))
            self.inv_set_vars[set_name] = var
            base_col = logical_col * 2
            ttk.Checkbutton(
                self.inv_set_frame_inner, text=set_name, variable=var,
                command=self.refresh_inventory,
            ).grid(row=row, column=base_col, sticky=tk.W,
                   padx=(2, 0), pady=(top_pad, 0))
            # Task 4 (round 9, revised): the count label gets a fixed width
            # (per-column max, see col_count_widths) with anchor=E so the
            # closing brackets line up right-aligned within the count
            # column. Task 4 follow-up (round 9): tried -1 left pad but Tk
            # rejects negative pad values ("bad pad value"), so 0 is the
            # actual minimum -- the per-column count_w is what reduced the
            # visible distance for short-count columns.
            cnt = ttk.Label(self.inv_set_frame_inner, text=f"({count})",
                            width=col_count_widths[logical_col], anchor=tk.E)
            cnt.grid(row=row, column=base_col + 1, sticky=tk.W,
                     padx=(0, 8), pady=(top_pad, 0))
            # Clicking the count toggles the checkbox too (the count label
            # isn't part of the Checkbutton's own hit area).
            cnt.bind(
                "<Button-1>",
                lambda _e, v=var: (v.set(not v.get()), self.refresh_inventory()),
            )

        SET_GROUP_GAP = 4
        for i, set_name in enumerate(four_names):
            _add_set_cell(set_name, i // ncols, i % ncols, 0)
        four_rows = (len(four_names) + ncols - 1) // ncols
        for j, set_name in enumerate(rest_names):
            r = four_rows + j // ncols
            top = SET_GROUP_GAP if j < ncols else 0
            _add_set_cell(set_name, r, j % ncols, top)

        # Also rebuild unknown main-stat checkboxes for the data we just loaded.
        self.populate_unknown_main_stats()

    # ----- Main Stats filter ---------------------------------------------

    def select_all_main_stats(self):
        for label, var in self.inv_main_stat_vars.items():
            # Only check if currently enabled (greyed-out ones stay unchecked).
            if str(self.inv_main_stat_checks[label].cget("state")) != "disabled":
                var.set(True)
        for canonical, var in self.inv_unknown_main_stat_vars.items():
            var.set(True)
        self.refresh_inventory()

    def select_no_main_stats(self):
        for var in self.inv_main_stat_vars.values():
            var.set(False)
        for var in self.inv_unknown_main_stat_vars.values():
            var.set(False)
        self.refresh_inventory()

    def populate_unknown_main_stats(self):
        """Rebuild the unknown-main-stats row from currently loaded fragments.

        An unknown main is one whose canonical name isn't in either:
          - MAIN_STAT_DISPLAY (the 11 stats shown in the filter), nor
          - the always-pass list ("Flat ATK", "Flat DEF", "Flat HP" — slot
            1/2/3 mains, which are excluded from the filter UI by design and
            always pass through).

        Surviving unknowns are listed by their raw stat string. Selection
        state is preserved across reloads.
        """
        for widget in self.inv_main_unknown_frame.winfo_children():
            widget.destroy()

        # Stats that should NEVER appear in the filter, even when present in
        # the data: the 11 displayed mains (always shown) and the three flat
        # slot 1/2/3 mains (always pass through, never shown).
        known = set(c for _, c in MAIN_STAT_DISPLAY)
        known.update({"Flat ATK", "Flat DEF", "Flat HP"})

        seen_unknown = set()
        for f in self.optimizer.fragments:
            if f.main_stat and f.main_stat.name not in known:
                seen_unknown.add(f.main_stat.name)

        # Drop vars for unknowns that no longer appear in the data.
        for stale in [k for k in self.inv_unknown_main_stat_vars if k not in seen_unknown]:
            del self.inv_unknown_main_stat_vars[stale]
            self.inv_unknown_main_stat_checks.pop(stale, None)

        # Add (or re-add) widgets for each currently-seen unknown.
        for col_idx, canonical in enumerate(sorted(seen_unknown)):
            if canonical not in self.inv_unknown_main_stat_vars:
                # New unknown: default to checked.
                self.inv_unknown_main_stat_vars[canonical] = tk.BooleanVar(value=True)
            var = self.inv_unknown_main_stat_vars[canonical]
            cb = self._make_mainstat_checkbutton(
                self.inv_main_unknown_frame, canonical, var
            )
            cb.grid(row=0, column=col_idx, sticky=tk.W, padx=2)
            self.inv_unknown_main_stat_checks[canonical] = cb

    def _make_mainstat_checkbutton(self, parent, label: str, var: tk.BooleanVar):
        """Build a tk.Checkbutton styled to blend with the surrounding ttk
        widgets in the dark theme. Used by both the fixed-position grid and
        the unknowns row so they look identical."""
        return tk.Checkbutton(
            parent, text=label, variable=var,
            command=self.refresh_inventory,
            bg=self.colors["bg"], fg=self.colors["fg"],
            activebackground=self.colors["bg"],
            activeforeground=self.colors["fg"],
            disabledforeground=self.colors["fg_dim"],
            selectcolor=self.colors["bg_light"],
            font=self._mainstat_font,
            anchor=tk.W, bd=0, highlightthickness=0,
        )

    def _refresh_main_stat_availability(self):
        """Enable/grey-out main stat checkboxes based on which slots are checked.

        Logic:
          - "Effective slots" = currently-checked slots in {4,5,6}, OR all of
            {4,5,6} if no slots are checked at all (parity with the
            "all-or-none = no filter" semantics used everywhere else).
          - A main stat is available iff at least one effective slot lists it
            in FILTER_SLOT_MAIN_STATS.
          - Newly-available stats auto-check; newly-unavailable ones uncheck
            and disable.
          - Slots 1/2/3 are not part of this filter UI — their mains always
            pass through refresh_inventory regardless.
        """
        any_slot_checked = any(v.get() for v in self.inv_slot_vars.values())
        if any_slot_checked:
            effective_slots = {
                s for s, v in self.inv_slot_vars.items() if v.get()
            } & {4, 5, 6}
        else:
            # Zero slots checked -> treat as all slots checked.
            effective_slots = {4, 5, 6}

        available_canonical = set()
        for slot_num in effective_slots:
            available_canonical.update(FILTER_SLOT_MAIN_STATS.get(slot_num, []))

        for label, canonical in MAIN_STAT_DISPLAY:
            var = self.inv_main_stat_vars[label]
            cb = self.inv_main_stat_checks[label]
            currently_disabled = str(cb.cget("state")) == "disabled"
            should_be_enabled = canonical in available_canonical

            if should_be_enabled:
                # Just became available: auto-check.
                if currently_disabled:
                    var.set(True)
                cb.configure(state="normal", font=self._mainstat_font)
            else:
                # Just became unavailable: uncheck, disable, strike-through.
                var.set(False)
                cb.configure(state="disabled", font=self._mainstat_strike_font)

    # ----- Refresh / display ---------------------------------------------

    def refresh_inventory(self):
        """Refresh inventory display based on current filter settings."""
        self.inv_tree.delete(*self.inv_tree.get_children())

        uneq_only = self.inv_unequipped_var.get()
        include_uncommon = self.inv_include_uncommon_var.get()
        min_rarity = 2 if include_uncommon else 3

        # Selected slots — zero checked is treated the same as all checked
        # (= no filter), matching the all-or-none convention used by every
        # other filter on this tab.
        slot_nums = {s for s, v in self.inv_slot_vars.items() if v.get()}
        if not slot_nums:
            slot_nums = set(range(1, 7))

        # Selected sets — all-checked or all-unchecked behaves like "no filter".
        set_names = set()
        all_sets_selected = True
        for set_name, var in self.inv_set_vars.items():
            if var.get():
                set_names.add(set_name)
            else:
                all_sets_selected = False
        if all_sets_selected or not set_names:
            set_names = None  # don't filter by set

        # Selected main stats — same semantics: all-or-none = "no filter".
        # Only enabled checkboxes (slot-relevant ones) participate in "all".
        enabled_labels = [
            lbl for lbl in self.inv_main_stat_vars
            if str(self.inv_main_stat_checks[lbl].cget("state")) != "disabled"
        ]
        checked_canonical = set()
        all_mains_checked = True
        for label in enabled_labels:
            if self.inv_main_stat_vars[label].get():
                checked_canonical.add(self.inv_main_stat_canonical[label])
            else:
                all_mains_checked = False
        # Unknowns are always enabled — include them in the all/none accounting.
        for canonical, var in self.inv_unknown_main_stat_vars.items():
            if var.get():
                checked_canonical.add(canonical)
            else:
                all_mains_checked = False
        any_main_checked = bool(checked_canonical)
        # Filter by main stat ONLY when the selection is partial.
        # (all checked -> show everything; nothing checked -> show everything)
        filter_by_main = not all_mains_checked and any_main_checked

        # ---- apply filters ----
        filtered = [f for f in self.optimizer.fragments if f.rarity_num >= min_rarity]
        filtered = [f for f in filtered if f.slot_num in slot_nums]
        if set_names:
            filtered = [f for f in filtered if f.set_name in set_names]
        if uneq_only:
            filtered = [f for f in filtered if not f.equipped_to]

        if filter_by_main:
            # Slots 1/2/3 always pass (their mains aren't represented in the filter).
            # Slots 4/5/6 must have a main stat whose canonical name is checked.
            new_filtered = []
            for f in filtered:
                if f.slot_num in (1, 2, 3):
                    new_filtered.append(f)
                else:
                    main_name = f.main_stat.name if f.main_stat else None
                    if main_name in checked_canonical:
                        new_filtered.append(f)
            filtered = new_filtered

        self.inv_filtered_data = filtered
        self._display_inventory_sorted()

    def _display_inventory_sorted(self):
        """Display filtered inventory with current sort settings."""
        self.inv_tree.delete(*self.inv_tree.get_children())

        if not hasattr(self, 'inv_filtered_data'):
            return

        filtered = self.inv_filtered_data

        # Compute Highest GS and Highest Potential GS across custom presets
        # (or just assigned ones, if the corresponding checkbox is on).
        # Annotate each fragment with both results so the sort keys can read
        # them without recomputing.
        #
        # Bounds are per (preset, fragment's main stat) under Philosophy B,
        # so we can't pre-compute one bounds per preset. Instead we cache
        # lazily as we encounter each (preset, main_stat) combination --
        # at most P x 16 entries for P presets and 16 possible main stats.
        preset_data = self._presets_for_highest_gs()  # list[(name, weights)]
        no_presets = not preset_data
        bounds_cache: dict = {}  # (preset_idx, main_stat_name) -> bounds

        for f in filtered:
            if no_presets:
                f.highest_preset_gs = 0.0
                f.highest_preset_potential_low = 0.0
                f.highest_preset_potential_high = 0.0
                f.highest_preset_potential_name = None
                continue

            main_name = f.main_stat.name if f.main_stat else None
            best_gs = float("-inf")
            # Highest Potential GS: find the preset giving the highest
            # ceiling (potential_high), and store BOTH that ceiling AND
            # the corresponding floor (potential_low) under that same
            # preset. Mirrors the regular Potential column's "low-high"
            # display under the active preset, but generalized across
            # presets -- the displayed range is always one preset's
            # actual range, not a synthetic mix.
            best_high = float("-inf")
            best_low = 0.0
            # Round 10 task 9: track the winning preset's NAME too so the
            # display can append it in brackets. For fully-leveled MFs the
            # high collapses to the current GS, so "preset with max high"
            # is the same as "preset with max GS" -- one annotation works
            # for both cases.
            best_high_preset = None
            for pi, (pname, weights) in enumerate(preset_data):
                key = (pi, main_name)
                if key not in bounds_cache:
                    bounds_cache[key] = compute_gs_bounds(
                        weights, exclude_stat=main_name
                    )
                bounds = bounds_cache[key]
                gs = compute_fragment_gs(f, weights, bounds)
                if gs > best_gs:
                    best_gs = gs
                low, high = compute_fragment_potential(f, weights, bounds)
                if high > best_high:
                    best_high = high
                    best_low = low
                    best_high_preset = pname
            f.highest_preset_gs = best_gs
            f.highest_preset_potential_low = best_low
            f.highest_preset_potential_high = best_high
            f.highest_preset_potential_name = best_high_preset

        sort_key_map = {
            "slot": lambda f: f.slot_num,
            "set": lambda f: f.set_name,
            "lvl": lambda f: f.level,
            "main": lambda f: f.main_stat.name if f.main_stat else "",
            "gs": lambda f: f.gear_score,
            "potential": lambda f: f.potential_high,
            "equipped": lambda f: f.equipped_to or "",
            "highest_gs": lambda f: f.highest_preset_gs,
            # Sort by ceiling (mirrors the regular Potential column). At max
            # level, ceiling == base GS under the same preset, so sorting by
            # this naturally falls back to Highest GS — same self-collapsing
            # behavior the regular Potential column has at max level.
            "highest_potential": lambda f: f.highest_preset_potential_high,
        }

        key_func = sort_key_map.get(self.inv_sort_col, lambda f: f.gear_score)
        filtered_sorted = sorted(filtered, key=key_func, reverse=self.inv_sort_reverse)

        for f in filtered_sorted[:500]:
            # Item 5 (round 6): translate stat names through DISPLAY_NAMES and
            # add a space after the colon (matches the Optimizer tab).
            subs = []
            for s in f.substats[:4]:
                sub_label = DISPLAY_NAMES.get(s.name, s.name)
                subs.append(f"{sub_label}: {s.format_value()}")
            while len(subs) < 4:
                subs.append("-")

            if f.main_stat:
                main_label = DISPLAY_NAMES.get(f.main_stat.name, f.main_stat.name)
                main_str = f"{main_label}: {f.main_stat.format_value()}"
            else:
                main_str = "-"
            pot = f"{f.potential_low:.0f}-{f.potential_high:.0f}" if f.potential_low != f.potential_high else "-"

            set_pieces = f.get_set_pieces()
            set_display = f"{f.set_name} ({set_pieces})"

            # Highest GS / Highest Potential GS: show "—" when no presets are
            # eligible (no custom presets at all, or none assigned with the
            # checkbox on). Both columns share the same eligibility.
            hgs_str = "—" if no_presets else f"{f.highest_preset_gs:.0f}"
            # Highest Potential display rules (round 10):
            #   no presets eligible       -> "—"
            #   range (unleveled)         -> "60-100 [preset]"
            #   single (fully leveled)    -> "-"  (NO preset name -- the
            #                                     Highest GS column already
            #                                     shows the value for max-
            #                                     level MFs, so repeating
            #                                     value+preset here would be
            #                                     redundant. q3 follow-up.)
            if no_presets:
                hpot_str = "—"
            elif f.highest_preset_potential_low != f.highest_preset_potential_high:
                pname = getattr(f, "highest_preset_potential_name", None)
                preset_suffix = f" [{pname}]" if pname else ""
                hpot_str = (f"{f.highest_preset_potential_low:.0f}-"
                            f"{f.highest_preset_potential_high:.0f}"
                            f"{preset_suffix}")
            else:
                hpot_str = "-"

            self.inv_tree.insert("", tk.END, values=(
                f.slot_name, set_display, f"{f.level}",
                main_str, *subs, f"{f.gear_score:.0f}", pot, f.equipped_to or "",
                hgs_str, hpot_str,
            ), tags=(f"r{f.rarity_num}",))

        self.inv_tree.tag_configure("r4", foreground=RARITY_COLORS[4])
        self.inv_tree.tag_configure("r3", foreground=RARITY_COLORS[3])
        self.inv_tree.tag_configure("r2", foreground=RARITY_COLORS[2])

    def sort_inventory(self, col: str):
        """Sort inventory by specified column."""
        if col == self.inv_sort_col:
            self.inv_sort_reverse = not self.inv_sort_reverse
        else:
            self.inv_sort_col = col
            # First click on Highest GS sorts ascending (low scores at the
            # top) so bad fragments surface immediately — matches the column's
            # "find bad MFs" purpose. The other numeric columns still default
            # to descending on first click.
            self.inv_sort_reverse = col in ["gs", "lvl", "potential"]

        self._display_inventory_sorted()

    # =========================================================================
    # Highest GS — best score across custom (named) presets
    # =========================================================================

    def _presets_for_highest_gs(self):
        """Resolve the list of presets to consider for the Highest GS column.

        - All custom presets from the preset_manager (the virtual default
          weights aren't a stored preset, so they're excluded automatically).
        - If "Assigned Presets Only" is checked, narrow to just the presets
          referenced by an assignment in the character_preset_manager.

        Returns a list of (name, weights) tuples. Bounds are NOT pre-computed
        -- under Philosophy B they depend on each fragment's main stat, so
        callers compute them lazily inside the per-fragment loop (cached
        by (preset_idx, main_stat) to avoid recomputation across fragments
        sharing the same main stat).

        Returns an empty list when there's nothing to compare against.

        Round 10 task 9: previously returned just the weights dicts; now
        returns (name, weights) so the Highest Potential column can show
        which preset won in brackets after the range.
        """
        pm = getattr(self.context, "preset_manager", None)
        if pm is None:
            return []

        names = list(pm.get_preset_names())
        if not names:
            return []

        if self.inv_only_assigned_presets_var and self.inv_only_assigned_presets_var.get():
            cpm = getattr(self.context, "character_preset_manager", None)
            if cpm is None:
                return []
            assigned = {p for p in cpm.assignments.values() if p}
            names = [n for n in names if n in assigned]
            if not names:
                return []

        return [(name, pm.get_preset(name) or {}) for name in names]

    # =========================================================================
    # Column-header tooltips
    # =========================================================================
    #
    # Tk's Treeview has no native tooltip support on column headers, so we
    # roll our own: track which column the mouse is over, schedule a delayed
    # popup, hide it on column-change / leave / motion-out-of-heading.

    # Delay before the tooltip appears, in ms. Long enough that just passing
    # over a header doesn't trigger it, short enough that an intentional
    # hover feels responsive.
    _TOOLTIP_DELAY_MS = 400

    def _column_tooltip_text(self, col_id: str):
        """Return tooltip text for the column under the mouse, or None.

        col_id is Tk's "#N" column identifier (1-based). We map it back to
        our internal column name and return the tooltip if any.
        """
        try:
            col_idx = int(col_id.lstrip("#")) - 1
        except (ValueError, AttributeError):
            return None
        if col_idx < 0 or col_idx >= len(self._inv_cols):
            return None
        col_name = self._inv_cols[col_idx]

        if col_name == "highest_gs":
            scope = (
                "assigned Custom Presets"
                if (self.inv_only_assigned_presets_var
                    and self.inv_only_assigned_presets_var.get())
                else "all Custom Presets"
            )
            return (f"Shows the highest Gear Score out of {scope}.\n"
                    "Useful for finding bad MFs.")
        if col_name == "highest_potential":
            scope = (
                "assigned Custom Presets"
                if (self.inv_only_assigned_presets_var
                    and self.inv_only_assigned_presets_var.get())
                else "all Custom Presets"
            )
            return (f"Shows the highest Potential Gear Score out of {scope}.\n"
                    "Useful for finding bad MFs.")
        return None

    def _on_tree_motion(self, event):
        """Track which header the mouse is over; show/hide tooltip accordingly."""
        region = self.inv_tree.identify_region(event.x, event.y)
        if region != "heading":
            if self._last_tooltip_col is not None:
                self._hide_tooltip()
                self._last_tooltip_col = None
            return

        col_id = self.inv_tree.identify_column(event.x)
        if col_id == self._last_tooltip_col:
            return  # still on the same column; nothing to do

        # Column changed — drop any existing tooltip and schedule the new one.
        self._last_tooltip_col = col_id
        self._hide_tooltip()
        text = self._column_tooltip_text(col_id)
        if text is None:
            return

        x_root = event.x_root
        y_root = event.y_root
        self._tooltip_after_id = self.frame.after(
            self._TOOLTIP_DELAY_MS,
            lambda: self._show_tooltip(x_root, y_root, text),
        )

    def _show_tooltip(self, x_root: int, y_root: int, text: str):
        """Pop a small borderless Toplevel near the mouse position."""
        self._tooltip_after_id = None
        if self._tooltip_window is not None:
            return  # already shown (defensive — shouldn't happen)
        try:
            tw = tk.Toplevel(self.frame)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x_root + 12}+{y_root + 18}")
            tk.Label(
                tw, text=text, justify=tk.LEFT,
                background="#ffffe0", foreground="#000000",
                relief=tk.SOLID, borderwidth=1, padx=6, pady=4,
                font=("Segoe UI", 9),
            ).pack()
            self._tooltip_window = tw
        except Exception:
            self._tooltip_window = None

    def _hide_tooltip(self):
        """Cancel pending tooltip and destroy the current one if any."""
        if self._tooltip_after_id is not None:
            try:
                self.frame.after_cancel(self._tooltip_after_id)
            except Exception:
                pass
            self._tooltip_after_id = None
        if self._tooltip_window is not None:
            try:
                self._tooltip_window.destroy()
            except Exception:
                pass
            self._tooltip_window = None
