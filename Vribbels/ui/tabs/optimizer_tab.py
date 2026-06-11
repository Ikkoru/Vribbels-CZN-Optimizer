"""
Optimization configuration and execution tab.

v1.1.0 overhaul: per-character persistent settings, simplified UI, set
combinations handled internally by the optimizer.

UI layout (top to bottom)
-------------------------
  Toolbar: [Combatant ▼] [Optimize for LVL ↕] [Start] [Stop] [help text]  [status]
  Body (fixed 3-column grid, non-draggable):
    Left:    Stats Comparison (Treeview; right-click -> stat contributions)
    Middle:  Configuration column, top to bottom:
                Element override (only shown for Unknown-attribute chars)
                Important Settings | Have at Least (side by side)
                Set Configuration (Flex Slots + set-effect % + buff
                  spinboxes + single sets checklist)
                Exclude Combatant's MFs (checklist + All/None buttons)
    Right:   Results (Treeview)
  Bottom:  Selected Build detail tree

Persistence
-----------
Every per-character widget is bound to OptimizerSettingsManager via either
trace_add (for IntVar/StringVar) or command= (for ttk.Scale moves). The
`_loading_settings` guard suppresses write-back during programmatic var
updates triggered by on_hero_select.

Calculation hookup
------------------
The Optimizer tab feeds per-character settings (Important Settings
sliders, Have at Least minimums, set-effect %, avg buff fields, level
stepper, element override) into `optimizer.optimize()` via the unified
settings dict built by `_build_optimizer_settings`. The optimizer
implements the v1.1.0 damage / shield-heal blended scoring from
docs/game_formulas.md §8 and applies the Have-at-least hard constraint
inline during its enumeration. This tab only handles UI / persistence /
result display; the actual math lives in optimizer.py.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
from typing import Optional

from ui.base_tab import BaseTab
from ui.context import AppContext
from game_data import (
    SETS, FOUR_PIECE_SETS, TWO_PIECE_SETS,
    SLOT_MAIN_STATS, RARITY_COLORS, ATTRIBUTE_COLORS,
    CHARACTERS, CHARACTERS_BY_NAME,
    get_character_by_name
)
# v1.1.0 Item 3: Display-name overrides for user-facing labels. Internal
# stat keys ("CRate", "CDmg", "Flat ATK", etc.) remain unchanged; this map
# is consulted whenever a stat name is shown to the user.
from game_data.constants import DISPLAY_NAMES
# Pure GS / Potential helpers — used by _populate_detail to compute the
# Selected Build tree's GS and Potential columns under the character's
# ASSIGNED scoring preset (which may differ from the globally-active
# preset on the fragments' cached .gear_score / .potential_low/high).
from models.memory_fragment import (
    compute_fragment_gs, compute_fragment_potential, bounds_for_fragment,
)


# Multi-line explanation shown below the toolbar where the Reset button
# used to live. Wraplength is set on the label widget so the text reflows
# when the user resizes the window.
OPTIMIZER_HELP_TEXT = (
    "The Optimizer looks through worthwhile Memory Fragments (MFs) to find the "
    "combination that leads to the most damage/healing/shielding.\n"
    "Select your preferred Sets, tweak Important Settings, exclude the "
    "equipped MFs of combatants that you do not want to strip, and press Start.\n"
    "Currently does not account for unleveled MFs' potential. "
    "Not reducing how many MFs are considered takes longer. "
    "Select Sets, reduce Flex Slots, exclude characters' MFs."
)


# Stat keys used by the "Have at least" panel. Ordered as displayed:
# column 1 = (ATK, DEF, HP, Ego), column 2 = (CRate, CDmg, Extra DMG%, DoT%).
HAL_COLUMN_1 = ["ATK", "DEF", "HP", "Ego"]
HAL_COLUMN_2 = ["CRate", "CDmg", "Extra DMG%", "DoT%"]
HAL_STATS_WITH_PCT = {"CRate", "CDmg", "Extra DMG%", "DoT%"}  # show "%" suffix
HAL_ALL_STATS = HAL_COLUMN_1 + HAL_COLUMN_2


# Element choices for the Unknown-character override dropdown.
ELEMENT_CHOICES = ["", "Passion", "Order", "Justice", "Void", "Instinct"]


# Force-main checkbox definitions. Each entry: (settings key, label, slot).
# Slot is needed when translating the checkbox state into the optimizer's
# legacy main_stat_<slot> filter list.
FORCE_MAIN_DEFS = [
    ("slot4_hp",  "IV: HP",   4, "HP%"),
    ("slot5_hp",  "V: HP",    5, "HP%"),
    ("slot6_hp",  "VI: HP",   6, "HP%"),
    ("slot6_ego", "VI: Ego",  6, "Ego"),
]


def _combobox_letter_jump(event, combobox):
    """Letter-key navigation on a readonly Combobox: pressing 'A' jumps to
    the next value starting with 'A' (case-insensitive), cycling at the end.
    Non-alphanumeric keys fall through (return None) so Tk's default arrow
    handling still works.

    Fires <<ComboboxSelected>> on a successful jump so the bound handler
    (on_hero_select) reacts as if the user picked the entry with the mouse.

    Binds to <KeyRelease> instead of <KeyPress>: readonly ttk.Combobox's
    internal handler can swallow KeyPress before our binding sees it on
    some platforms; KeyRelease fires after Tk's default processing.

    Kept deliberately in sync with the analogous helper in heroes_tab.py --
    edits to one should be mirrored in the other.
    """
    char = event.char
    if not char or not char.isalnum():
        return None
    char_lower = char.lower()

    values = list(combobox["values"])
    if not values:
        return "break"

    current = combobox.get()
    try:
        start = (values.index(current) + 1) % len(values)
    except ValueError:
        start = 0

    for offset in range(len(values)):
        idx = (start + offset) % len(values)
        if values[idx].lower().startswith(char_lower):
            combobox.set(values[idx])
            # Item 5 (round 5): readonly Combobox doesn't auto-select the
            # displayed text after a programmatic set(); force a full
            # selection so the whole name is highlighted, not just part.
            try:
                combobox.selection_clear()
                combobox.selection_range(0, "end")
            except tk.TclError:
                pass
            combobox.event_generate("<<ComboboxSelected>>")
            return "break"
    return "break"


def _combobox_arrow_nav(event, combobox, direction):
    """Up / Down arrow navigation on a readonly Combobox (Item 11).

    Tk's default behavior on a readonly ttk.Combobox: pressing Down OPENS
    the dropdown popup. Many users prefer the Windows-native pattern where
    Up / Down step through entries in place WITHOUT opening the popup.
    This handler implements that pattern:
      * `direction` is +1 for Down, -1 for Up.
      * Does NOT wrap at the ends (Item 5, round 5): at the first entry,
        Up does nothing; at the last entry, Down does nothing. Either way
        we return "break" so Tk's default open-popup binding is suppressed.
      * Forces a full text selection after moving (Item 5) so the whole
        name is highlighted rather than partially.
      * `<<ComboboxSelected>>` is fired so the bound on_hero_select runs
        as if the user had clicked the entry.
    """
    values = list(combobox["values"])
    if not values:
        return "break"
    current = combobox.get()
    try:
        idx = values.index(current)
    except ValueError:
        # No current selection yet -- land on the first or last entry.
        idx = -1 if direction > 0 else len(values)
    new_idx = idx + direction
    # Item 5: no wrap-around. Out of range -> stay put.
    if new_idx < 0 or new_idx >= len(values):
        return "break"
    combobox.set(values[new_idx])
    try:
        combobox.selection_clear()
        combobox.selection_range(0, "end")
    except tk.TclError:
        pass
    combobox.event_generate("<<ComboboxSelected>>")
    return "break"


def _popdown_listbox_seek(combobox, listbox_path, char):
    """Type-ahead seek inside an OPEN combobox dropdown list (Item 11).

    Moves the popdown listbox's highlight to the next entry starting with
    `char` (case-insensitive), cycling. Operates on the listbox via its Tcl
    path (it isn't a registered tkinter widget). Does NOT commit the value --
    that happens when the user presses Enter or clicks, same as native
    behavior; we only move the highlight.
    """
    if not char or not char.isalnum():
        return
    char_lower = char.lower()
    tkc = combobox.tk
    try:
        size = int(tkc.call(listbox_path, "size"))
    except tk.TclError:
        return
    if size == 0:
        return
    values = [str(tkc.call(listbox_path, "get", i)) for i in range(size)]
    try:
        cur = int(tkc.call(listbox_path, "index", "active"))
    except (tk.TclError, ValueError):
        cur = 0
    # Start one past the active entry so repeated presses cycle matches.
    for offset in range(1, size + 1):
        idx = (cur + offset) % size
        if values[idx].lower().startswith(char_lower):
            tkc.call(listbox_path, "selection", "clear", 0, "end")
            tkc.call(listbox_path, "selection", "set", idx)
            tkc.call(listbox_path, "activate", idx)
            tkc.call(listbox_path, "see", idx)
            return


def _bind_popdown_seek(combobox):
    """Enable type-ahead seek on a readonly Combobox's OPEN dropdown list
    (Item 11, round 7 -- "option 1" from the prior discussion).

    Tk's ttk combobox popdown doesn't implement letter-seek while open; its
    internal listbox lives at "<popdown>.f.l". We obtain the popdown via
    ttk::combobox::PopdownWindow (which creates it on demand, so this can run
    at setup time) and bind at the Tcl level -- the popdown listbox is not a
    registered tkinter widget, so a normal .bind() can't reach it.

    The whole thing is wrapped in try/except so that on any Tk build where
    the internal widget path differs, it silently no-ops: the open-list seek
    just won't work, while the closed-combo letter-jump (_combobox_letter_
    jump) and arrow-nav keep functioning. Kept in sync with heroes_tab.py.
    """
    try:
        popdown = combobox.tk.call("ttk::combobox::PopdownWindow", combobox)
    except tk.TclError:
        return
    listbox_path = f"{popdown}.f.l"

    def _on_key(char):
        # Only alnum keys trigger a seek; everything else (arrows, Enter,
        # Escape) returns "" so Tk's own listbox bindings keep working.
        if not char or not char.isalnum():
            return ""
        try:
            _popdown_listbox_seek(combobox, listbox_path, char)
        except tk.TclError:
            pass
        return "break"

    try:
        cmd = combobox.register(_on_key)
        # "+" appends to Tk's built-in listbox bindings rather than
        # replacing them; we run our command and issue a Tcl `break` only
        # when it returns "break" (i.e. a seek key was handled).
        script = f"+if {{[{cmd} %A] eq {{break}}}} {{ break }}"
        combobox.tk.call("bind", listbox_path, "<KeyPress>", script)
    except tk.TclError:
        pass


class OptimizerTab(BaseTab):
    """v1.1.0 Optimizer tab. See module docstring for layout overview."""

    # ------------------------------------------------------------ init / state

    def __init__(self, parent: tk.Widget, context: AppContext):
        super().__init__(parent, context)
        self._init_state()
        self.setup_ui()
        # Layout-settling guard (round 9 follow-up): when this tab is first
        # shown, Tk runs 2-3 layout passes in view of the user -- col 1's
        # natural width starts wider than its final settled value (likely a
        # ttk.Scale or Spinbox whose theme/font metrics resolve after the
        # first pass), so Important Settings / Set Configuration / Selected
        # Build visibly shrink and Exclude / Results visibly grow leftward
        # into the freed space. Binding update_idletasks() to <Map> drains
        # all pending geometry-idle events SYNCHRONOUSLY before Tk paints,
        # so the user only ever sees the settled state. _layout_settled
        # makes it one-shot -- subsequent tab switches (re-Map events) are
        # no-ops; update_idletasks is cheap when the queue is empty anyway,
        # but the flag keeps the intent explicit.
        self._layout_settled = False
        self.frame.bind("<Map>", self._settle_layout_once, add="+")
        # Task 3 (round 10 revisited, sub-problem B1): the Preset label
        # shown above Stats Comparison can go stale if the user reassigns
        # a character's preset from Heroes / Combatants while this tab
        # is inactive. Refresh on tab-switch via <<NotebookTabChanged>>;
        # the handler self-gates on "is this tab the active one?" so it's
        # a no-op when other tabs are selected.
        nb = self._find_notebook()
        if nb is not None:
            nb.bind("<<NotebookTabChanged>>",
                    self._on_notebook_tab_changed, add="+")
        self.root.after(100, self.check_queue)

    def _settle_layout_once(self, _event):
        """One-shot layout drain on the tab's first <Map>. See the comment
        in __init__ for the rationale."""
        if self._layout_settled:
            return
        self._layout_settled = True
        self.frame.update_idletasks()
        # Task 3 A1 (round 10 revisited): the preset_row in the toolbar has
        # pack_propagate(False) so it doesn't grow with its label content;
        # we explicitly size it to match the top_row's natural width so the
        # preset label clips at the right edge of the left toolbar cluster
        # (Combatant + Level + Start + Stop) instead of pushing help_label
        # right when the preset name is long. Done in the settle pass
        # rather than at creation because the top_row's reqwidth is only
        # reliable once Tk has computed the children's natural sizes.
        try:
            top_w = self._toolbar_top_row.winfo_reqwidth()
            if top_w > 1:
                self._toolbar_preset_row.configure(width=top_w)
        except (AttributeError, tk.TclError):
            pass

    def _find_notebook(self):
        """Walk up from this tab's frame until we find a ttk.Notebook
        ancestor. Returns None if not found -- shouldn't happen in normal
        use, but callers should handle None gracefully."""
        w = self.frame
        while w is not None:
            if isinstance(w, ttk.Notebook):
                return w
            try:
                w = w.master
            except AttributeError:
                return None
        return None

    def _on_notebook_tab_changed(self, _event):
        """Refresh per-tab state whenever the Notebook switches. Currently
        used to keep the Preset label in sync with CharacterPresetManager
        when the user reassigns from another tab. Self-gates on "is this
        tab now active?" so it's a no-op for other tabs."""
        nb = self._find_notebook()
        if nb is None:
            return
        try:
            current = nb.select()
        except tk.TclError:
            return
        if str(self.frame) == current:
            self._update_preset_label()

    def _init_state(self):
        # --- Selection state ---
        # selected_character is the visible string in the combobox (a hero
        # name, possibly suffixed with a res_id for unknown chars). The
        # res_id is the canonical key into OptimizerSettingsManager.
        self.selected_character = tk.StringVar()
        self._current_res_id: Optional[int] = None
        # Suppresses writeback to settings during programmatic var loads
        # in on_hero_select. Each trace callback checks this first.
        self._loading_settings = False

        # --- Per-character UI vars (Important Settings) ---
        self.extra_pct_var = tk.IntVar(value=0)
        self.dot_pct_var = tk.IntVar(value=0)
        self.atk_def_split_var = tk.IntVar(value=0)
        self.shielding_healing_weight_var = tk.IntVar(value=0)
        self.force_main_vars = {key: tk.BooleanVar(value=False)
                                 for key, _label, _slot, _stat in FORCE_MAIN_DEFS}
        self.element_override_var = tk.StringVar(value="")

        # --- Per-character UI vars (Have at Least) ---
        self.have_at_least_vars = {stat: tk.IntVar(value=0) for stat in HAL_ALL_STATS}

        # --- Per-character UI vars (Set Configuration) ---
        self.set_selected_vars: dict = {}  # set_id (int) -> BooleanVar
        self.max_flex_slots_var = tk.IntVar(value=6)
        self.set_effect_pct_var = tk.IntVar(value=0)
        self.avg_card_dmg_pct_var = tk.IntVar(value=100)
        self.avg_mult_buff_pct_var = tk.IntVar(value=0)
        self.avg_add_buff_pct_var = tk.IntVar(value=0)

        # --- Per-character UI vars (toolbar level stepper) ---
        self.optimize_for_level_var = tk.IntVar(value=62)

        # --- Global UI vars (Excluded gear) ---
        # Keyed by hero name (display string); the save callback converts
        # to res_ids at the boundary.
        self.exclude_hero_vars: dict = {}

        # --- Optimization runtime state ---
        self.optimization_results: list = []
        self.result_queue = queue.Queue()
        self.cancel_flag = [False]
        self.result_sort_col = "score"
        self.result_sort_reverse = False

        # --- Widget references (filled by setup_ui) ---
        self.hero_combo = None
        self.status_label = None
        self.stats_tree = None
        self.result_tree = None
        self.detail_tree = None
        self.progress_label = None
        self.exclude_heroes_frame = None
        self.element_override_frame = None
        self.set_grid_frame = None
        self.ad_readout_label = None
        self.sh_readout_label = None
        self.set_effect_readout_label = None
        self.preset_label = None

    # Convenience accessor -- avoids repeating self.context.optimizer_settings_manager
    @property
    def opt_settings(self):
        return self.context.optimizer_settings_manager

    # ----------------------------------------------------------- UI top-level

    def setup_ui(self):
        # ---- Toolbar ----
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill=tk.X, padx=5, pady=(1, 5))

        # Item 4: stack the Combatant label and dropdown vertically (a 2-row
        # sub-frame). The dropdown sits BELOW the "Combatant:" text instead
        # of beside it, freeing horizontal space for the other toolbar
        # controls and matching the new stacked status-label style on the
        # right (Item 3).
        # Task 3 A1 (round 10 revisited): the toolbar's left cluster
        # (Combatant + LVL + Start + Stop) is now wrapped in a vertical
        # left_cluster -> top_row container so that a preset_row can sit
        # below it, clipped to the top_row's width. Without this, long
        # preset names made combatant_frame grow and pushed every other
        # toolbar control right.
        left_cluster = ttk.Frame(toolbar)
        left_cluster.pack(side=tk.LEFT, anchor=tk.N)
        self._toolbar_top_row = ttk.Frame(left_cluster)
        self._toolbar_top_row.pack(side=tk.TOP, fill=tk.X, anchor=tk.W)
        combatant_frame = ttk.Frame(self._toolbar_top_row)
        combatant_frame.pack(side=tk.LEFT, padx=(0, 5), anchor=tk.N)
        ttk.Label(combatant_frame, text="Combatant:").pack(anchor=tk.W)
        # Item 1 (this round): width sized just for the longest character
        # name in CHARACTERS ("Heidemarie" = 10 chars) plus ~2 chars for the
        # scrollbar that appears inside the dropdown popup once it has more
        # entries than fit vertically. The default 18 was wider than
        # necessary -- this gives the toolbar more room for the help text
        # and status label.
        self.hero_combo = ttk.Combobox(
            combatant_frame, textvariable=self.selected_character,
            width=12, state="readonly",
        )
        self.hero_combo.pack(anchor=tk.W)
        # Task 3 (round 10 revisited): the Preset: label originally lived
        # here inside combatant_frame, then briefly above Stats Comparison
        # (A4) -- both pushed surrounding layout around. It's now below the
        # whole left toolbar cluster (top_row) inside a width-clipped
        # preset_row -- see the Stop button block.
        self.hero_combo.bind("<<ComboboxSelected>>", self.on_hero_select)
        # Letter-key navigation (v1.1.0): type a letter to jump to the next
        # matching combatant. KeyRelease + add="+" so readonly Combobox's
        # internal handler doesn't pre-empt us; some Tk versions don't fire
        # KeyPress to user bindings on readonly state.
        self.hero_combo.bind(
            "<KeyRelease>", lambda e: _combobox_letter_jump(e, self.hero_combo),
            add="+",
        )
        # Item 11: arrow keys step through the list in place instead of
        # opening the dropdown popup. Default Tk behavior on readonly
        # Combobox would open the popup on <Down>; we override that here.
        self.hero_combo.bind(
            "<Down>", lambda e: _combobox_arrow_nav(e, self.hero_combo, +1)
        )
        self.hero_combo.bind(
            "<Up>", lambda e: _combobox_arrow_nav(e, self.hero_combo, -1)
        )
        # Item 11 (round 7): type-ahead seek inside the OPEN dropdown list.
        _bind_popdown_seek(self.hero_combo)

        # Item 3: every subsequent toolbar widget uses anchor=tk.N so the
        # row is top-aligned (otherwise pack vertically centers the 1-line
        # widgets against the help label's 3 lines, leaving them floating
        # in the middle of the row).
        # Item 1 (this round): the LVL label + spinner are now stacked
        # vertically in their own sub-frame, mirroring the Combatant
        # label/dropdown stacking from a prior turn.
        level_frame = ttk.Frame(self._toolbar_top_row)
        level_frame.pack(side=tk.LEFT, padx=(15, 0), anchor=tk.N)
        ttk.Label(level_frame, text="Optimize for LVL:").pack(anchor=tk.W)
        level_spin = tk.Spinbox(
            level_frame, from_=60, to=62, increment=1, width=3,
            textvariable=self.optimize_for_level_var,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            buttonbackground=self.colors["bg_lighter"],
            insertbackground=self.colors["fg"],
        )
        level_spin.pack(anchor=tk.W)
        level_spin.bind("<MouseWheel>", lambda e: self._spinbox_wheel(e, level_spin))
        self.optimize_for_level_var.trace_add(
            "write", lambda *_: self._save_int_safe("optimize_for_level",
                                                       self.optimize_for_level_var))

        ttk.Button(self._toolbar_top_row, text="Start",
                   command=self.run_optimization).pack(
                       side=tk.LEFT, padx=(15, 2), pady=(3, 0), anchor=tk.N)
        ttk.Button(self._toolbar_top_row, text="Stop",
                   command=self.cancel_optimization).pack(
                       side=tk.LEFT, padx=2, pady=(3, 0), anchor=tk.N)

        # Task 3 A1 (round 10 revisited): preset row below the top row.
        # pack_propagate(False) so the row doesn't grow with its label;
        # width is synced to top_row's natural reqwidth in
        # _settle_layout_once so the label clips at the cluster's right
        # edge. Height is just enough for one Segoe UI 8pt line.
        self._toolbar_preset_row = ttk.Frame(left_cluster, height=17)
        self._toolbar_preset_row.pack_propagate(False)
        self._toolbar_preset_row.pack(side=tk.TOP, fill=tk.X, anchor=tk.W)
        self.preset_label = ttk.Label(
            self._toolbar_preset_row, text="Preset: (default)",
            foreground=self.colors["fg_dim"],
            font=("Segoe UI", 8),
        )
        self.preset_label.pack(side=tk.LEFT, anchor=tk.W)

        # ---- Help text (Item 5: moved from a separate row below the toolbar
        # to inline with the toolbar, packed between Stop and the status
        # label). fill=X + expand=True lets it absorb available horizontal
        # space; the Configure binding reflows wraplength on resize so the
        # text wraps neatly without pushing the status label off-screen.
        help_label = ttk.Label(
            toolbar, text=OPTIMIZER_HELP_TEXT,
            justify=tk.LEFT, foreground=self.colors["fg_dim"],
            wraplength=600,
        )
        help_label.pack(side=tk.LEFT, padx=(15, 0), fill=tk.X, expand=True, anchor=tk.N)
        help_label.bind(
            "<Configure>",
            lambda e, lbl=help_label: lbl.config(wraplength=max(200, e.width - 10)),
        )

        # Item 3: status text on two lines ("Loaded\nN fragments"), reduced
        # right padding so it sits close to the toolbar's right edge, and
        # top-aligned via anchor=tk.N to match the rest of the row.
        self.status_label = ttk.Label(
            toolbar, text="No data\nloaded",
            foreground=self.colors["fg_dim"],
            justify=tk.RIGHT,
        )
        self.status_label.pack(side=tk.RIGHT, padx=(10, 2), anchor=tk.N)

        # ---- Body grid (Item 8 restructure) ----
        # 3 columns: Stats Comp (fixed width), Config (weight=2),
        # Results / empty area (weight=2).
        # 2 rows: top row expands, bottom row natural height.
        # Layout (visual):
        #   Row 0: [Stats Comp] [Config         ] [EMPTY (above Results)]
        #   Row 1: [Selected Build (cols 0-1)  ] [Results (shorter)    ]
        # Selected Build spans cols 0-1 so its right edge aligns with the
        # Config column's right edge -- which is also the Exclude MFs
        # frame's right edge, per the user's spec.
        body = ttk.Frame(self.frame)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(0, weight=0)
        # Item 2 (round 6): col 2 (Results / Exclude) widened ~+100px via a
        # 2:3 weight split vs col 1. Item 2 (round 7): nudged another ~+40px
        # (100:171). Weights are proportional so the exact pixel delta drifts
        # with window width.
        body.grid_columnconfigure(1, weight=100)
        body.grid_columnconfigure(2, weight=171)
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)

        # --- Row 0 col 0: Stats Comparison (Item 3: sticky="new" so the
        # frame is only as tall as its content -- the empty space below it
        # stays empty instead of the frame stretching to fill row 0). ---
        left_frame = ttk.LabelFrame(body, text="Stats Comparison", padding=5)
        left_frame.grid(row=0, column=0, sticky="new", padx=(5, 4), pady=5)
        self._build_stats_tree(left_frame)

        # --- Row 0 col 1: Configuration (middle pane) ---
        self.middle_frame = ttk.Frame(body)
        self.middle_frame.grid(row=0, column=1, sticky="nsew", padx=4, pady=5)
        self._build_config(self.middle_frame)

        # --- Col 2 (rowspan 2): Exclude MFs (top) + Results (below). Item 4
        # moved the Exclude panel here from the bottom of the middle pane so
        # it sits directly above Results. Results expands to fill whatever
        # vertical space remains below Exclude. ---
        self._col2_container = ttk.Frame(body)
        self._col2_container.grid(row=0, column=2, rowspan=2, sticky="nsew",
                                  padx=(4, 5), pady=5)
        exclude_frame = ttk.LabelFrame(
            self._col2_container, text="Exclude Combatant's MFs", padding=5
        )
        exclude_frame.pack(fill=tk.X, pady=(0, 5))
        self._build_exclude_gear(exclude_frame)
        right_frame = ttk.LabelFrame(self._col2_container, text="Results", padding=5)
        right_frame.pack(fill=tk.BOTH, expand=True)
        self._build_results(right_frame)

        # --- Row 1 cols 0-1: Selected Build (Item 3 prev round: bottom-
        # aligned via sticky="sew"). ---
        detail_frame = ttk.LabelFrame(body, text="Selected Build", padding=5)
        detail_frame.grid(row=1, column=0, columnspan=2, sticky="sew",
                          padx=(5, 4), pady=(0, 5))
        self._build_detail_tree(detail_frame)

        # No data on startup -- disable interactive controls.
        self._update_enabled_state()

    # ---------------------------------------------------- UI: stats tree (left)

    def _build_stats_tree(self, parent):
        self.stats_tree = ttk.Treeview(
            parent, columns=("stat", "current", "new", "diff"),
            show="headings", height=14,
        )
        self.stats_tree.column("#0", width=0, stretch=False)
        self.stats_tree.heading("stat", text="Stat")
        # Item 3 (round 6): "Current" renamed to "Now".
        self.stats_tree.heading("current", text="Now")
        self.stats_tree.heading("new", text="New")
        self.stats_tree.heading("diff", text="+/-")
        # Item 3 (round 6): "stat" trimmed to just fit "Element%" (the widest
        # row label); the three value columns each fit ~5 chars. stretch=
        # False keeps the Treeview's natural width = the column-width sum, so
        # (with the parent grid column weight=0) the whole frame hugs it.
        # Tree height set to exactly the number of rows it now shows (Totals
        # header + 9 stats + blank + 3 Pot7 rows = 14) so the frame is only
        # as tall as its content.
        self.stats_tree.column("stat", width=62, stretch=False)
        self.stats_tree.column("current", width=44, anchor=tk.E, stretch=False)
        self.stats_tree.column("new", width=44, anchor=tk.E, stretch=False)
        self.stats_tree.column("diff", width=44, anchor=tk.E, stretch=False)
        self.stats_tree.pack(fill=tk.Y, expand=True)
        # Item 11: right-click opens the "Show all stat contributions" menu.
        self.stats_tree.bind("<Button-3>", self._show_stats_context_menu)

    # ------------------------------------------------- UI: middle pane builder

    def _build_config(self, parent):
        """Middle pane: element override, two-column settings, set config,
        exclude gear."""
        # Element override (conditional visibility -- toggled by
        # _update_element_override_visibility based on selected character).
        self.element_override_frame = ttk.LabelFrame(
            parent, text="Element override (Unknown character)", padding=4
        )
        ttk.Label(
            self.element_override_frame,
            text="Treat this character's damage as element:",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(0, 5))
        self.element_override_combo = ttk.Combobox(
            self.element_override_frame,
            textvariable=self.element_override_var,
            values=ELEMENT_CHOICES,
            state="readonly", width=12,
        )
        self.element_override_combo.pack(side=tk.LEFT)
        self.element_override_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self._save_str("element_override", self.element_override_var.get() or None),
        )
        # Don't pack the frame yet -- _update_element_override_visibility
        # adds/removes it based on the character's attribute.

        # Top row: Important Settings | Have at Least (side by side)
        top_row = ttk.Frame(parent)
        top_row.pack(fill=tk.X, pady=(0, 5))

        important_frame = ttk.LabelFrame(top_row, text="Important Settings", padding=5)
        important_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        self._build_important_settings(important_frame)

        have_frame = ttk.LabelFrame(
            top_row, text="Have at least this much of a stat", padding=5
        )
        # Item 4: HAL frame no longer expands -- it sizes to its natural
        # width so the panel hugs its (now narrower) spinboxes. important_
        # frame still has expand=True so it absorbs the freed horizontal
        # space. Task 3 (round 9): no right pad here, so the frame's right
        # edge aligns with the Set Configuration frame's right edge below.
        # Task 2 (round 9): ipadx=10 widens HAL by 20px (the +20 transfers
        # from Important Settings, since important_frame's expand=True
        # automatically gives up the space).
        have_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False,
                        padx=(3, 0), ipadx=10)
        self._build_have_at_least(have_frame)

        # Set Configuration
        set_frame = ttk.LabelFrame(parent, text="Set Configuration", padding=5)
        set_frame.pack(fill=tk.X, pady=(0, 5))
        self._set_frame_ref = set_frame
        self._build_set_config(set_frame)

        # Item 4 (round 6): the "Exclude Combatant's MFs" panel used to be
        # built here (bottom of the middle pane). It now lives in col 2
        # above the Results frame -- see setup_ui. _build_exclude_gear is
        # called from there instead.

    # ----------------------------------------------- UI: Important Settings

    def _build_important_settings(self, parent):
        # Block 1: Extra% + DoT% sliders
        ttk.Label(
            parent, text="What percent of damage is Extra DMG and DoT DMG?",
            font=("Segoe UI", 9), wraplength=350,
        ).pack(anchor=tk.W, pady=(2, 2))

        ed_row = ttk.Frame(parent)
        ed_row.pack(fill=tk.X, pady=(0, 6))
        self._labeled_slider(
            ed_row, "Extra", self.extra_pct_var,
            on_change=lambda v: self._save_int("extra_pct", v),
            label_width=5,  # Task 4 (round 10 revisited): exact text fit so
                            # Extra's slider-gap matches DoT's (the default
                            # +1 slack gives Extra ~7px slack and DoT ~3px
                            # because 1 "average char" is ~5px but actual
                            # text widths differ -- forcing label_width=5
                            # tightens Extra's slack to ~2px).
        )
        ttk.Label(ed_row, text="   ").pack(side=tk.LEFT)
        self._labeled_slider(
            ed_row, "DoT", self.dot_pct_var,
            on_change=lambda v: self._save_int("dot_pct", v),
        )

        # Block 2: ATK ↔ DEF slider
        ttk.Label(
            parent, text="What percent of damage scales off DEF?",
            font=("Segoe UI", 9), wraplength=350,
        ).pack(anchor=tk.W, pady=(2, 2))

        ad_row = ttk.Frame(parent)
        ad_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(ad_row, text="ATK", width=4).pack(side=tk.LEFT)
        ad_scale = ttk.Scale(
            ad_row, from_=0, to=100, variable=self.atk_def_split_var,
            orient=tk.HORIZONTAL,
            command=lambda v: self._save_int("atk_def_split", int(float(v))),
        )
        ad_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 3))
        # Task 7 (round 10): width 4 -> 3 was too aggressive ("DEF" got
        # clipped on the "F"); 4 with anchor=E keeps "DEF" intact while
        # shifting its empty slack from the right (between DEF and the
        # readout) to the left (between scale and DEF). Net effect:
        # DEF-text right edge now hugs the label's right edge, and the
        # gap from "DEF" to "100%" matches the other sliders'
        # scale-end-to-readout gap.
        ttk.Label(ad_row, text="DEF", width=4, anchor=tk.E).pack(side=tk.LEFT)
        # Task 2 (round 9): anchor=E so the readout's visible text hugs the
        # right edge (right padding now matches left). Task 1 (round 10
        # revisited): width 4 -> 5. ttk.Label's effective text area is
        # width-in-chars minus a couple px of theme-defined internal padding,
        # which left width=4 just shy of "100%"'s rendered width. anchor=E
        # keeps the visible glyphs glued to the right; the extra char of
        # slack lives invisibly on the left.
        self.ad_readout_label = ttk.Label(ad_row, text="0%", width=5, anchor=tk.E)
        self.ad_readout_label.pack(side=tk.LEFT, padx=(3, 0))
        self.atk_def_split_var.trace_add(
            "write",
            lambda *a: self.ad_readout_label.config(
                text=f"{self.atk_def_split_var.get()}%"
            ),
        )

        # Block 3: Shielding/Healing slider
        ttk.Label(
            parent, text="How much value should be given to Shielding & Healing?",
            font=("Segoe UI", 9), wraplength=350,
        ).pack(anchor=tk.W, pady=(2, 2))

        sh_row = ttk.Frame(parent)
        sh_row.pack(fill=tk.X, pady=(0, 6))
        sh_scale = ttk.Scale(
            sh_row, from_=0, to=100, variable=self.shielding_healing_weight_var,
            orient=tk.HORIZONTAL,
            command=lambda v: self._save_int("shielding_healing_weight", int(float(v))),
        )
        sh_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        # Task 2 (round 9): anchor=E for right-aligned text. Task 1 (round
        # 10 revisited): width 4 -> 5 to give "100%" room inside the label
        # itself -- the previous right-padx fix didn't help because the
        # clipping was internal to the label, not at the row's right edge.
        self.sh_readout_label = ttk.Label(sh_row, text="0%", width=5, anchor=tk.E)
        self.sh_readout_label.pack(side=tk.LEFT)
        self.shielding_healing_weight_var.trace_add(
            "write",
            lambda *a: self.sh_readout_label.config(
                text=f"{self.shielding_healing_weight_var.get()}%"
            ),
        )

        # Block 4: Force-main checkboxes (slot 4 HP, slot 5 HP, slot 6 HP, slot 6 Ego)
        # Item 12: label + checkboxes on the same line (previously the label
        # had its own row above the checkboxes).
        fm_row = ttk.Frame(parent)
        fm_row.pack(fill=tk.X, pady=(2, 2))
        ttk.Label(
            fm_row,
            text="Force HP/Ego on a Slot:",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(0, 5))
        for idx, (key, label, _slot, _stat) in enumerate(FORCE_MAIN_DEFS):
            # Task 2 (round 9): the last checkbox drops its 8px right pad so
            # the rightmost visible element sits flush with the frame's
            # right padding edge (matching the left edge of the leading
            # label).
            pad_right = 0 if idx == len(FORCE_MAIN_DEFS) - 1 else 8
            ttk.Checkbutton(
                fm_row, text=label,
                variable=self.force_main_vars[key],
                command=lambda k=key: self._save_force_main(k),
            ).pack(side=tk.LEFT, padx=(0, pad_right))

    def _labeled_slider(self, parent, label, var, on_change=None,
                        label_width=None):
        """Build a labeled slider + readout inside `parent`. Packs LEFT.

        on_change(int) is called whenever the slider moves to a new integer
        value. We pass int(float(v)) because ttk.Scale's command receives a
        string-formatted float (e.g. "23.0") even on an integer-bound Scale.

        Task 4 (round 10): `label_width` defaults to `len(label) + 1` -- 1
        char of slack, matching the ATK/DEF row below. Pass an explicit
        value to override (e.g. to enforce equal column widths across
        multiple sliders in the same row).
        """
        wrap = ttk.Frame(parent)
        wrap.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if label_width is None:
            label_width = len(label) + 1
        ttk.Label(wrap, text=label, width=label_width).pack(side=tk.LEFT)
        scale = ttk.Scale(
            wrap, from_=0, to=100, variable=var, orient=tk.HORIZONTAL,
            command=lambda v: on_change(int(float(v))) if on_change else None,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 3))
        # Task 2 (round 9): anchor=E for right-aligned text. Task 1 (round
        # 10 revisited): width 4 -> 5 to keep "100%" from clipping inside
        # the label (Tk's avg-char-width math underestimates the rendered
        # width of "100%" by 1-2 px on this theme).
        readout = ttk.Label(wrap, text="0%", width=5, anchor=tk.E)
        readout.pack(side=tk.LEFT)
        var.trace_add("write",
                      lambda *a, r=readout, v=var: r.config(text=f"{v.get()}%"))

    # -------------------------------------------------- UI: Have at Least

    def _build_have_at_least(self, parent):
        """Two columns of 4 spinboxes each. Col 1 = ATK/DEF/HP/Ego (raw
        integer), Col 2 = CRate/CDmg/Extra DMG%/DoT% (integer + "%").

        Item 4 (v1.1.0 polish round 3): the label-to-spinbox gap is now
        natural (label sized to fit its text) instead of a fixed width=10,
        and the spinboxes are width=4 (just enough for 4 digits). The two
        column frames don't expand horizontally either, so the surrounding
        LabelFrame sizes to its natural width.
        """
        cols = ttk.Frame(parent)
        # Task 3 (round 9, revised): no extra padding on either side -- col 1
        # text sits at the LabelFrame's own left padding edge (matching the
        # other config frames), and col 2's spinbox is right-aligned at the
        # LabelFrame's right padding edge (no whitespace hanging off the
        # right side). Task 2 (round 9): cols fills X (was fill=Y) so the
        # +20px HAL gained from Important Settings parks BETWEEN col 1
        # (LEFT) and col 2 (RIGHT) instead of pushing col 2 off its right
        # alignment.
        cols.pack(fill=tk.X, expand=False, padx=(0, 0))
        col1_frame = ttk.Frame(cols)
        col1_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 0))
        col2_frame = ttk.Frame(cols)
        # Task 2 (round 9): col 2 packed RIGHT (was LEFT) so it stays at
        # HAL's right padding edge after the frame widens.
        col2_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        # Item 2 (round 5): give every label in a column the same width
        # (the longest label's char count) so the spinboxes line up
        # vertically within each column. n2 (this round): colons removed,
        # so the width no longer counts a trailing ":".
        def _col_label_width(stats):
            return max(len(DISPLAY_NAMES.get(s, s)) for s in stats)
        col1_width = _col_label_width(HAL_COLUMN_1)
        col2_width = _col_label_width(HAL_COLUMN_2)

        for stat in HAL_COLUMN_1:
            # Task 3 (round 9): col 1 needed extra room between the stat
            # label and its spinbox -- "ATK" etc. were being crowded. Task 2
            # (round 9, follow-up, revised): instead of using padx between
            # the label and spinbox, the label's character allocation is
            # widened to col1_width + 1 with label_pad=0. Same visual
            # effect -- with anchor=W, the label widget now carries 1 char
            # of internal whitespace to the right of the text, the spinbox
            # sits flush against the label's right edge, and the +1 char
            # of width is reclaimed from the inter-column whitespace
            # (col 2 is RIGHT-anchored, so col 1 growing on its right eats
            # into the gap automatically).
            self._build_hal_row(col1_frame, stat, label_width=col1_width+1,
                                label_pad=0)
        for stat in HAL_COLUMN_2:
            # Task 2 (round 9, follow-up): col 2 spinbox narrowed to 3 chars
            # (CRate/CDmg/Extra/DoT are %-bounded -- 3 digits is enough).
            self._build_hal_row(col2_frame, stat, label_width=col2_width,
                                spin_width=3)

        # Task 2 (round 9, follow-up): note explaining HAL threshold
        # semantics, packed below the cols grid. wraplength is updated on
        # <Configure> so the text reflows whenever the HAL frame's width
        # changes (it does -- HAL trades width with Important Settings).
        hal_note = ttk.Label(
            parent,
            text=("Note: Input stats as you expect to see them in the "
            "in-game Combatants menu."),
            foreground=self.colors["fg_dim"],
            justify=tk.LEFT,
            wraplength=160,  # initial; will be replaced on first <Configure>
        )
        hal_note.pack(fill=tk.X, expand=False, pady=(4, 0))
        parent.bind(
            "<Configure>",
            lambda e, lbl=hal_note: lbl.config(wraplength=max(160, e.width - 29)),
            add="+",
        )

    def _build_hal_row(self, parent, stat, label_width=None, label_pad=2,
                       spin_width=4):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=1)
        # Item 3: translate the internal stat key to its user-facing label.
        # Item 2 (round 5): fixed per-column width so spinboxes align;
        # anchor=tk.W keeps the label text left-justified within that width.
        # n2 (this round): no trailing colon on the stat labels.
        # Task 3 (round 9): label_pad is the gap to the spinbox (col 1 = 9).
        label_text = DISPLAY_NAMES.get(stat, stat)
        ttk.Label(row, text=label_text, width=label_width,
                  anchor=tk.W).pack(side=tk.LEFT, padx=(0, label_pad))
        var = self.have_at_least_vars[stat]
        # Item 4: spinbox width default 4 (big enough for 4-digit ATK/HP
        # thresholds). Task 2 (round 9, follow-up): callers may override
        # via spin_width (col 2 uses 3 since its stats are %-bounded).
        spin = tk.Spinbox(
            row, from_=0, to=99999, increment=1, width=spin_width,
            textvariable=var,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            buttonbackground=self.colors["bg_lighter"],
            insertbackground=self.colors["fg"],
        )
        spin.pack(side=tk.LEFT)
        spin.bind("<MouseWheel>", lambda e, sp=spin: self._spinbox_wheel(e, sp))
        if stat in HAL_STATS_WITH_PCT:
            ttk.Label(row, text="%").pack(side=tk.LEFT, padx=(2, 0))
        # Save on any write -- Spinbox button clicks fire the var-trace.
        var.trace_add(
            "write",
            lambda *a, s=stat: self._save_have_at_least(s),
        )

    # --------------------------------------------------- UI: Set Configuration

    def _build_set_config(self, parent):
        # Row 1: Max Flex Slots stepper (left) + Set Effect group (right).
        # Item 10: the set-effect text + slider were originally a single
        # left-packed cluster on this row; they're now stacked vertically
        # in a right-aligned sub-frame so the long descriptive label can
        # wrap onto its own line without squishing the spinbox.
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=(0, 3))

        # Item 9: "Maximum Flex Slots" -> "Max Flex Slots".
        ttk.Label(row1, text="Max Flex Slots").pack(side=tk.LEFT, padx=(0, 4))
        flex_spin = tk.Spinbox(
            row1, from_=0, to=6, increment=1, width=3,
            textvariable=self.max_flex_slots_var,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            buttonbackground=self.colors["bg_lighter"],
            insertbackground=self.colors["fg"],
        )
        flex_spin.pack(side=tk.LEFT)
        flex_spin.bind("<MouseWheel>", lambda e, sp=flex_spin: self._spinbox_wheel(e, sp))
        self.max_flex_slots_var.trace_add(
            "write", lambda *a: self._save_int_safe("max_flex_slots",
                                                       self.max_flex_slots_var))

        # Item 10 / n5 (this round): set-effect group -- right-aligned
        # within row1, on the SAME line as Max Flex Slots. The descriptive
        # text is split across two lines (bracketed note on the 2nd line)
        # and sits to the LEFT of the slider (no longer stacked above it).
        se_frame = ttk.Frame(row1)
        se_frame.pack(side=tk.RIGHT)
        ttk.Label(
            se_frame,
            text="What percent of DMG has set effect\n"
                 "(only affects conditional sets)",
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, padx=(0, 5))
        se_scale = ttk.Scale(
            se_frame, from_=0, to=100, variable=self.set_effect_pct_var,
            orient=tk.HORIZONTAL, length=140,
            command=lambda v: self._save_int("set_effect_pct", int(float(v))),
        )
        se_scale.pack(side=tk.LEFT, padx=(0, 3))
        self.set_effect_readout_label = ttk.Label(se_frame, text="0%", width=5)
        self.set_effect_readout_label.pack(side=tk.LEFT)
        self.set_effect_pct_var.trace_add(
            "write",
            lambda *a: self.set_effect_readout_label.config(
                text=f"{self.set_effect_pct_var.get()}%"
            ),
        )

        # Row 2: Avg Card DMG / Mult Buff / Add Buff spinboxes
        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(0, 5))

        for label, var, field in [
            ("Avg Card DMG%", self.avg_card_dmg_pct_var, "avg_card_dmg_pct"),
            ("Avg Mult Buff%", self.avg_mult_buff_pct_var, "avg_mult_buff_pct"),
            ("Avg Add Buff%", self.avg_add_buff_pct_var, "avg_add_buff_pct"),
        ]:
            ttk.Label(row2, text=label).pack(side=tk.LEFT, padx=(0, 3))
            spin = tk.Spinbox(
                row2, from_=0, to=9999, increment=1, width=5,
                textvariable=var,
                bg=self.colors["bg_light"], fg=self.colors["fg"],
                buttonbackground=self.colors["bg_lighter"],
                insertbackground=self.colors["fg"],
            )
            spin.pack(side=tk.LEFT, padx=(0, 12))
            spin.bind("<MouseWheel>", lambda e, sp=spin: self._spinbox_wheel(e, sp))
            var.trace_add(
                "write", lambda *a, f=field, v=var: self._save_int_safe(f, v)
            )

        # Row 3+: Sets list (single grid; 4-piece sorted first, then 2-piece,
        # alphabetical within each).
        ttk.Label(
            parent,
            text="Selected Sets (the optimizer tries all "
                 "combinations of the selected sets and flex pieces):",
            font=("Segoe UI", 9), wraplength=600,
        ).pack(anchor=tk.W, pady=(2, 3))

        self.set_grid_frame = ttk.Frame(parent)
        self.set_grid_frame.pack(fill=tk.X)
        # Sort: 4-piece first (so heavyweight commitments are visible top),
        # then 2-piece, alphabetical within each.
        ncols = 3
        sorted_sets = sorted(
            SETS.items(),
            key=lambda kv: (-kv[1]["pieces"], kv[1]["name"].lower())
        )
        four = [(sid, si) for sid, si in sorted_sets if si["pieces"] == 4]
        two = [(sid, si) for sid, si in sorted_sets if si["pieces"] != 4]

        def _add_set_cb(sid, sinfo, row, col, top_pad):
            var = tk.BooleanVar(value=False)
            self.set_selected_vars[sid] = var
            # Item 9: "<pieces>pc: <name>" so the piece count leads.
            # Task 2 (round 10): split the visible text into two parts so
            # element-specific sets can be colored: "Xpc:" gets the first
            # element's color, "<name>" gets the second's. Single-element
            # sets use the same color for both; non-element sets use the
            # default foreground. ATTRIBUTE_COLORS is the same map the
            # exclude flow uses for combatant-name coloring, so the
            # palette matches across the tab. The checkbox itself is a
            # bare ttk.Checkbutton (no text) -- text-clicking is wired
            # back to it via <Button-1> bindings on the two labels.
            container = ttk.Frame(self.set_grid_frame)
            container.grid(row=row, column=col, sticky=tk.W,
                           padx=5, pady=(top_pad, 1))
            cb = ttk.Checkbutton(
                container, variable=var,
                command=self._save_sets_selected,
            )
            cb.pack(side=tk.LEFT)

            pieces_text = f"{sinfo['pieces']}pc:"
            name_text = " " + sinfo["name"]  # leading space separates from "pc:"
            elements = sinfo.get("elements", []) or []
            default_fg = self.colors["fg"]
            if len(elements) >= 2:
                pieces_color = ATTRIBUTE_COLORS.get(elements[0], default_fg)
                name_color = ATTRIBUTE_COLORS.get(elements[1], default_fg)
            elif len(elements) == 1:
                pieces_color = name_color = ATTRIBUTE_COLORS.get(
                    elements[0], default_fg
                )
            else:
                pieces_color = name_color = default_fg
            pieces_label = ttk.Label(
                container, text=pieces_text, foreground=pieces_color,
            )
            pieces_label.pack(side=tk.LEFT)
            name_label = ttk.Label(
                container, text=name_text, foreground=name_color,
            )
            name_label.pack(side=tk.LEFT)

            def _toggle(_event=None, v=var):
                v.set(not v.get())
                self._save_sets_selected()
            pieces_label.bind("<Button-1>", _toggle)
            name_label.bind("<Button-1>", _toggle)

        # Item 4 (round 7): 3 columns. n4 (this round): the 2-piece sets
        # always start on a fresh row below the 4-piece sets, with a small
        # vertical gap separating the two groups.
        for i, (sid, sinfo) in enumerate(four):
            _add_set_cb(sid, sinfo, i // ncols, i % ncols, 1)
        four_rows = (len(four) + ncols - 1) // ncols
        # a2 (this round): half the previous 10px gap between 4pc and 2pc.
        SET_GROUP_GAP = 5
        for j, (sid, sinfo) in enumerate(two):
            r = four_rows + j // ncols
            c = j % ncols
            top = SET_GROUP_GAP if j < ncols else 1
            _add_set_cb(sid, sinfo, r, c, top)

    # ------------------------------------------------ UI: Exclude Gear panel

    def _build_exclude_gear(self, parent):
        self.exclude_heroes_frame = ttk.Frame(parent)
        # Round 9 follow-up: lock the natural width to the eventual flow-
        # layout width (~694px for the current character roster at default
        # window sizes). The real exclude content is built post-Map (data
        # load -> refresh_exclude_heroes -> deferred 50ms after() callback
        # -> _reflow_exclude_heroes), and without this lock the LabelFrame's
        # reqwidth jumps from 1 -> 694 ~50ms after the tab paints, which
        # forces a visible grid re-balance: col 1 shrinks ~56px and col 2
        # grows the same. update_idletasks() can't catch this because the
        # deferral is timer-based, not idle-based. Locking the reqwidth
        # here keeps col 2's minimum stable from creation. If the roster
        # changes substantially, this value should be re-tuned to match.
        self.exclude_heroes_frame.configure(width=694)
        self.exclude_heroes_frame.pack(fill=tk.BOTH, expand=True)
        # Task 1 (round 9): the checklist used to use a fixed 8-column grid
        # with equal-weight columns -- every column scaled to the widest
        # name ("Heidemarie"), which left huge gaps after shorter names.
        # It's now a true flow layout: variable column widths sized to each
        # name and a variable column count per row based on container
        # width. The layout logic lives in refresh_exclude_heroes /
        # _reflow_exclude_heroes; this frame is left as a plain container.

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_row, text="All",
                   command=self._exclude_all_gear).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="None",
                   command=self._exclude_no_gear).pack(side=tk.LEFT)

    # ----------------------------------------------------------- UI: Results

    def _build_results(self, parent):
        self.progress_label = ttk.Label(
            parent, text="Ready to optimize", foreground=self.colors["fg_dim"]
        )
        self.progress_label.pack(anchor=tk.W)

        # Item 7: "rank" / # column removed -- row order in the tree is
        # already the implicit rank (top row = best build). Other columns'
        # widths trimmed by 5 px each; Sets still stretches to absorb the
        # remainder. Headings retain new-terminology display names per
        # Item 3 ("Crit%", "CDMG%", "Extra%").
        # Item 8: result_tree height reduced from 12 to 9 since the Results
        # frame now sits at the bottom-right beside Selected Build and
        # doesn't need the full vertical real estate it had as a top-row
        # pane.
        # Item 1 (round 7): added an "element" column before Extra% and an
        # "ego" column at the end. All numeric columns are right-aligned
        # (anchor=tk.E); only "sets" stays left-aligned and stretches.
        cols = ("score", "sets", "atk", "hp", "def",
                "crate", "cdmg", "element", "extra", "dot", "ego")
        self.result_tree = ttk.Treeview(
            parent, columns=cols, show="headings", height=9,
        )
        widths = {
            "score": 45, "sets": 120,
            "atk": 35, "hp": 35, "def": 35,
            "crate": 42, "cdmg": 44, "element": 46, "extra": 45,
            "dot": 42, "ego": 35,
        }
        headings = {
            "score": "Score", "sets": "Sets",
            "atk": "ATK", "hp": "HP", "def": "DEF",
            "crate": "Crit%", "cdmg": "CDMG%", "element": "Elem%",
            "extra": "Extra%", "dot": "DoT%", "ego": "Ego",
        }
        for c in cols:
            self.result_tree.heading(c, text=headings[c],
                                      command=lambda col=c: self.sort_results(col))
            self.result_tree.column(
                c, width=widths[c],
                anchor=tk.W if c == "sets" else tk.E,
                stretch=(c == "sets"),
            )

        result_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL,
                                       command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=result_scroll.set)
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_tree.bind("<<TreeviewSelect>>", self.on_result_select)

    # --------------------------------------------------- UI: detail tree

    def _build_detail_tree(self, parent):
        cols = ("slot", "set", "main", "sub1", "sub2", "sub3", "sub4",
                "gs", "owner")
        self.detail_tree = ttk.Treeview(
            parent, columns=cols, show="headings", height=6,
        )
        # n3 (this round): the separate "Potential" column was removed. The
        # "GS" column now shows the current GS when the MF is at max level,
        # or the Potential range (low-high) otherwise -- so it's widened to
        # fit a range like "60-100".
        col_defs = [
            ("slot",      "Slot",       94),  # Task 3 (round 9): 101 -> 94 to match dropped "+"
            ("set",       "Set",       110),
            ("main",      "Main",      90),
            ("sub1",      "Sub1",       90),
            ("sub2",      "Sub2",       90),
            ("sub3",      "Sub3",       90),
            ("sub4",      "Sub4",       90),
            ("gs",        "GS",         45),
            ("owner",     "Owner",      80),  # stretches
        ]
        for col, txt, w in col_defs:
            self.detail_tree.heading(col, text=txt)
            # Item 3 (round 7): substat cells (sub1-4) are now left-aligned
            # too, joining slot/set/main/owner. gs stays centered.
            anchor = (tk.W if col in ("slot", "set", "main",
                                      "sub1", "sub2", "sub3", "sub4", "owner")
                      else tk.CENTER)
            self.detail_tree.column(col, width=w, anchor=anchor,
                                     stretch=(col == "owner"))
        self.detail_tree.pack(fill=tk.X)

    # =================================================================
    # Public API used by main GUI
    # =================================================================

    def refresh_after_load(self):
        """Called by the main GUI after fresh data is loaded.

        Updates the status label, repopulates the hero combo with current
        character names, rebuilds the exclude-gear checklist, and ensures
        every captured character has an entry in OptimizerSettingsManager.
        Also re-selects whatever character is currently active (if any)
        so its settings get loaded into the UI vars.
        """
        fragment_count = len(self.optimizer.fragments)
        # Item 3: two-line status ("Loaded" on top, count on the bottom).
        self.status_label.config(
            text=f"Loaded\n{fragment_count} fragments",
            foreground=self.colors["green"],
        )
        self.refresh_hero_list()
        self.refresh_exclude_heroes()
        # Ensure each captured character has a settings entry. Bootstrap
        # at startup uses CHARACTERS; this adds any captured-but-unknown
        # res_ids that don't yet have an entry.
        self._ensure_captured_chars_have_settings()

        # Task 11 (round 10): previously this cleared optimization_results
        # outright on every reload -- a live equip event triggered the
        # same code path as a fresh capture, so the Results + Selected
        # Build panels would blank out every time the user moved an MF.
        # Now we try to re-map the cached results' MF references to the
        # newly-loaded fragments (matched by id), preserving the display.
        # Results whose MFs are no longer in the snapshot (e.g. deleted)
        # are dropped. Stats dicts get recomputed against the new MF
        # substats so upgrade events keep the display consistent (an
        # equip event leaves substats unchanged, so the recompute is a
        # no-op for that case). The cached SCORE is left alone -- it was
        # computed against the same substats and the scoring weights
        # haven't necessarily changed; re-running optimize is the
        # canonical way to get a fresh score.
        char = self.selected_character.get()
        prev_selection_idx = None
        if self.optimization_results and self.result_tree:
            try:
                sel = self.result_tree.selection()
                if sel:
                    prev_selection_idx = int(sel[0])
            except (ValueError, tk.TclError):
                prev_selection_idx = None

        if self.optimization_results:
            new_by_id = {
                getattr(f, "id", None): f for f in self.optimizer.fragments
            }
            new_by_id.pop(None, None)
            # Q9 (round 10): pre-compute settings + buff_baseline once so
            # the per-result score recompute below is cheap (settings dict
            # is non-trivial to build but constant across results).
            settings = self._build_optimizer_settings()
            base_mult = settings.get("avg_card_dmg_pct", 100) / 100.0
            mult_buff = settings.get("avg_mult_buff_pct", 0) / 100.0
            add_buff = settings.get("avg_add_buff_pct", 0) / 100.0
            buff_baseline = base_mult * (1.0 + mult_buff) + add_buff
            if buff_baseline <= 0:
                buff_baseline = 1.0
            updated = []
            for gear, score, stats in self.optimization_results:
                # Q8 (round 10): preserve results even when some MFs were
                # deleted -- keep the OLD ref so the row still renders
                # its remembered slot/set/substats, and the display layer
                # marks the Owner column as "(deleted)" for those entries
                # (see _populate_detail). This avoids the "selection drift"
                # problem the previous drop-on-missing approach had: index
                # 50 stays as the same logical build after a partial drop,
                # so the auto-restore at the bottom of this method lands
                # on the right row.
                new_gear = []
                for old_mf in gear:
                    new_mf = new_by_id.get(getattr(old_mf, "id", None))
                    if new_mf is None:
                        new_gear.append(old_mf)
                    else:
                        new_gear.append(new_mf)
                # Recompute stats against the new MF objects -- equip
                # events leave substats unchanged so this is a no-op, but
                # upgrade events change substats and we want the displayed
                # ATK/HP/DEF/CRate/etc. to reflect the post-upgrade values.
                # Q9 (round 10): recompute SCORE too -- upgrade events
                # change a fragment's contribution to the build, so the
                # cached score is stale. _compute_optimizer_score is pure
                # given (gear, stats, settings, char), so we just call it.
                try:
                    new_stats = self.optimizer.calculate_build_stats(
                        new_gear, char
                    )
                    new_score = self.optimizer._compute_optimizer_score(
                        new_gear, new_stats, settings, char
                    ) / buff_baseline
                except Exception:
                    new_stats = stats  # fallback to cached if anything goes wrong
                    new_score = score
                updated.append((new_gear, new_score, new_stats))
            self.optimization_results = updated

        # Refresh the trees from the (possibly re-mapped) results.
        if self.optimization_results:
            self.display_results(self.optimization_results)
        else:
            if self.result_tree:
                self.result_tree.delete(*self.result_tree.get_children())
            if self.detail_tree:
                self.detail_tree.delete(*self.detail_tree.get_children())
            if self.stats_tree:
                self.stats_tree.delete(*self.stats_tree.get_children())
            if self.progress_label:
                self.progress_label.config(text="Ready to optimize")

        # If the current selection still exists, reload its settings into
        # the UI. Otherwise clear selection.
        if self.selected_character.get() and self.selected_character.get() in self.hero_combo["values"]:
            self.on_hero_select()
        else:
            self.selected_character.set("")
            self._current_res_id = None

        # Restore the previously-selected build (if any) so Stats Comp +
        # Selected Build come back populated. on_hero_select above just
        # cleared Stats Comp to single-column (current-only); calling
        # on_result_select re-applies the comparison view and refreshes
        # the Selected Build owner column from the new MF refs.
        if (prev_selection_idx is not None
                and self.optimization_results
                and prev_selection_idx < len(self.optimization_results)
                and self.result_tree):
            try:
                self.result_tree.selection_set(str(prev_selection_idx))
                self.result_tree.see(str(prev_selection_idx))
                self.on_result_select(None)
            except tk.TclError:
                pass

        self._update_enabled_state()

    def refresh_hero_list(self):
        """Populate the combobox with currently-known characters.

        Display strings are formatted as just the character name; for
        captured-but-unknown characters (no entry in CHARACTERS) we
        append the res_id so the user can distinguish them.
        """
        all_heroes = set(self.optimizer.characters.keys()) | set(
            self.optimizer.character_info.keys()
        )
        # Build display map: name (or "name #res_id" for unknowns)
        display_strings = sorted(all_heroes)
        # The combo just shows raw names for now. res_id resolution happens
        # in _resolve_res_id when needed.
        self.hero_combo["values"] = display_strings

    def refresh_exclude_heroes(self):
        """Repopulate the exclude-gear checklist using a flow layout.

        Task 1 (round 9): each row is a sub-Frame packed top-down inside
        exclude_heroes_frame; checkbuttons within a row are packed LEFT
        with natural width and a small gap. A new row starts when the next
        checkbutton wouldn't fit in the remaining container width -- so
        column widths vary per name (no scaling to the widest) and the
        number of columns per row varies based on container width.
        Re-flows on <Configure> when the container resizes.

        Q7 #1 (round 10): skip the destructive rebuild when nothing
        visible has changed. Without this, every live-update reflow
        blinked the entire checklist; the blink was happening because
        Tk has to destroy + recreate ~30 checkbuttons even when their
        contents (hero list, excluded set, current character) are the
        same. We also key the cache by the currently-selected character
        so Q1's gray+strike treatment for the current char gets reapplied
        when the user picks a different combatant.
        """
        # Use the SAME source-of-truth as refresh_hero_list: union of
        # `characters` (which only has entries for characters with at least
        # one equipped MF) and `character_info` (which has every captured
        # character regardless of equipped gear). Without the union, any
        # character whose entire MF set is unequipped would silently
        # disappear from the exclude flow even though the rest of the UI
        # still shows them. Captured-but-unknown characters also live in
        # `character_info` (keyed by their res_id string), so they appear
        # too.
        new_heroes = sorted(
            set(self.optimizer.characters.keys())
            | set(self.optimizer.character_info.keys())
        )
        new_excluded = set(
            self.opt_settings.get_excluded_gear_chars()
            if self.opt_settings else []
        )
        new_current = self.selected_character.get()

        # Configure binding only needs to attach once.
        if not getattr(self, "_exclude_configure_bound", False):
            self.exclude_heroes_frame.bind(
                "<Configure>", self._on_exclude_configure
            )
            self._exclude_configure_bound = True

        # Q7 #1 skip-rebuild check: only rebuild when something visually
        # observable has changed.
        if (getattr(self, "_exclude_heroes", None) == new_heroes
                and getattr(self, "_exclude_excluded_set", None) == new_excluded
                and getattr(self, "_exclude_last_current", None) == new_current):
            return

        # Round 11 follow-up to Task 2: when ONLY the current-combatant
        # marker changed (heroes + excluded set are the same), avoid the
        # destroy + recreate cycle that causes a visible blink on every
        # combatant dropdown change. Instead just update the foreground
        # color and font of the previously-current + newly-current
        # checkbuttons in place. Falls back to a full rebuild when
        # widget refs are missing (e.g. first call before _reflow has
        # populated them).
        same_heroes = getattr(self, "_exclude_heroes", None) == new_heroes
        same_excluded = getattr(self, "_exclude_excluded_set", None) == new_excluded
        only_current_changed = (
            same_heroes
            and same_excluded
            and getattr(self, "_exclude_last_current", None) != new_current
        )
        old_current = getattr(self, "_exclude_last_current", None)
        self._exclude_heroes = new_heroes
        self._exclude_excluded_set = new_excluded
        self._exclude_last_current = new_current

        if only_current_changed and getattr(self, "_exclude_widgets", None):
            self._update_exclude_current_marker(old_current, new_current)
            return

        self._reflow_exclude_heroes()

    def _update_exclude_current_marker(self, old_current, new_current):
        """Cheap in-place update of the gray+strike treatment for one or
        two checkbuttons (the previously-selected combatant and the newly-
        selected one). No widget creation/destruction -- avoids the blink
        the full _reflow_exclude_heroes rebuild causes.

        Called from refresh_exclude_heroes when only the current combatant
        changed. If the strike font hasn't been built yet (first time the
        feature fires), this method creates it.
        """
        import tkinter.font as tkfont
        if not hasattr(self, "_exclude_strike_font"):
            self._exclude_strike_font = tkfont.Font(
                family="Segoe UI", size=9, overstrike=1
            )
        normal_font = ("Segoe UI", 9)

        # Restore the previous current-combatant's normal styling.
        if old_current and old_current in self._exclude_widgets:
            cb = self._exclude_widgets[old_current]
            char_data = get_character_by_name(old_current)
            normal_fg = ATTRIBUTE_COLORS.get(
                char_data.get("attribute", "Unknown"), self.colors["fg"]
            )
            try:
                cb.configure(
                    fg=normal_fg,
                    activeforeground=normal_fg,
                    font=normal_font,
                )
            except tk.TclError:
                pass  # widget was destroyed mid-update; full reflow will fix it

        # Apply gray+strike to the new current-combatant's checkbutton.
        if new_current and new_current in self._exclude_widgets:
            cb = self._exclude_widgets[new_current]
            try:
                cb.configure(
                    fg=self.colors["fg_dim"],
                    activeforeground=self.colors["fg_dim"],
                    font=self._exclude_strike_font,
                )
            except tk.TclError:
                pass

    def _on_exclude_configure(self, event):
        """Debounced re-flow trigger. Tk emits many Configure events during
        a resize drag; we only re-flow once after the storm settles.
        """
        if getattr(self, "_exclude_last_width", None) == event.width:
            return
        self._exclude_last_width = event.width
        if hasattr(self, "_exclude_reflow_after"):
            try:
                self.exclude_heroes_frame.after_cancel(self._exclude_reflow_after)
            except (tk.TclError, ValueError):
                pass
        self._exclude_reflow_after = self.exclude_heroes_frame.after(
            50, self._reflow_exclude_heroes
        )

    def _reflow_exclude_heroes(self):
        """Rebuild the per-row checkbutton frames at the current container
        width. Each name's width is estimated from font metrics so we don't
        need to realize each Checkbutton just to measure it.

        Stores a `_exclude_widgets` dict mapping hero name -> Checkbutton
        widget so `_update_exclude_current_marker` (round 11 Task 2) can
        do in-place font/fg updates on combatant change without a full
        rebuild.
        """
        import tkinter.font as tkfont

        # Tear down the old row frames + their checkbuttons.
        for widget in self.exclude_heroes_frame.winfo_children():
            widget.destroy()
        self.exclude_hero_vars.clear()
        self._exclude_widgets = {}

        container_w = self.exclude_heroes_frame.winfo_width()
        if container_w <= 1:
            # Container hasn't been realized yet (first call before geometry
            # settles); defer briefly and re-attempt.
            self.exclude_heroes_frame.after(50, self._reflow_exclude_heroes)
            return

        # Width estimation: text width via tkfont + a fixed overhead for the
        # checkbox indicator + a little internal padding. Tuned empirically
        # on a Windows theme; 27px lands without clipping.
        f = tkfont.Font(family="Segoe UI", size=9)
        checkbox_overhead = 27
        gap = 7        # px between checkbuttons in a row
        edge_pad = 0   # px on each side (kept symmetric per Task 1a)
        available_w = max(1, container_w - 2 * edge_pad)

        row_frame = None
        row_w = 0
        for hero in self._exclude_heroes:
            res_id = self._resolve_res_id(hero)
            initial = (str(res_id) in self._exclude_excluded_set
                       if res_id is not None else False)
            var = tk.BooleanVar(value=initial)
            self.exclude_hero_vars[hero] = var
            char_data = get_character_by_name(hero)
            fg_color = ATTRIBUTE_COLORS.get(
                char_data.get("attribute", "Unknown"), self.colors["fg"]
            )
            # Q1 (round 10): the currently-selected character's checkbutton
            # is grayed out + struck through so the user can see at a
            # glance that the optimizer ignores this row (their MFs are
            # always available -- see the filter in _build_optimizer_
            # settings). The check state itself is preserved so it returns
            # when the user picks a different combatant.
            is_current = (hero == self.selected_character.get())
            if is_current:
                fg_color = self.colors["fg_dim"]
                if not hasattr(self, "_exclude_strike_font"):
                    import tkinter.font as tkfont
                    self._exclude_strike_font = tkfont.Font(
                        family="Segoe UI", size=9, overstrike=1
                    )
                cb_font = self._exclude_strike_font
            else:
                cb_font = ("Segoe UI", 9)

            est_w = f.measure(hero) + checkbox_overhead

            if row_frame is None or row_w + est_w + gap > available_w:
                row_frame = ttk.Frame(self.exclude_heroes_frame)
                row_frame.pack(side=tk.TOP, anchor=tk.W, fill=tk.X,
                                padx=(edge_pad, edge_pad), pady=0)
                row_w = 0

            cb = tk.Checkbutton(
                row_frame, text=hero, variable=var,
                bg=self.colors["bg"], fg=fg_color,
                selectcolor=self.colors["bg_light"],
                activebackground=self.colors["bg"], activeforeground=fg_color,
                font=cb_font, anchor=tk.W,
                command=self._save_excluded_gear,
            )
            cb.pack(side=tk.LEFT, padx=(0, gap))
            self._exclude_widgets[hero] = cb  # round 11 Task 2: for in-place updates
            row_w += est_w + gap

    # =================================================================
    # res_id resolution + per-character settings load/save
    # =================================================================

    def _resolve_res_id(self, hero_name: str) -> Optional[int]:
        """Return the res_id for `hero_name`, or None if unknown.

        Resolution order:
          1. optimizer.character_info[name].res_id  -- live captured data
          2. CHARACTERS_BY_NAME[name]['res_id']     -- static known characters

        Returns None if neither knows the character.
        """
        if not hero_name:
            return None
        info = self.optimizer.character_info.get(hero_name)
        if info is not None and getattr(info, "res_id", None):
            try:
                return int(info.res_id)
            except (TypeError, ValueError):
                pass
        static = CHARACTERS_BY_NAME.get(hero_name)
        if static:
            rid = static.get("res_id")
            if rid:
                try:
                    return int(rid)
                except (TypeError, ValueError):
                    pass
        return None

    def _ensure_captured_chars_have_settings(self):
        """Make sure every captured character has a settings entry.

        Bootstrap-at-startup uses CHARACTERS (the static table). This
        method covers captured-but-unknown characters (res_id seen in
        snapshots but not yet in characters.py) so they too get persistent
        settings.

        Q6 (round 10): also bootstraps the "Exclude Combatant's MFs"
        checklist to default-checked-for-all. On first run (when the
        flag `excluded_default_initialized` is absent) we populate the
        excluded list with every known character's res_id. After that,
        any res_id encountered for the first time (no per-character
        entry yet) is auto-added to the excluded list -- so a newly
        released character defaults to excluded too. The user's manual
        unchecks are preserved across reloads because they're recorded
        in excluded_gear_chars (removal from the list), and we only
        ADD on first-seen.
        """
        if self.opt_settings is None:
            return

        # Q6 first-run bootstrap: populate excluded list with every
        # currently-known res_id. Includes both characters already in the
        # settings file (via bootstrap_known_characters at startup) and
        # any new captured res_ids we're about to ensure.
        #
        # Safety: only OVERWRITE the excluded list when it's empty. For
        # users upgrading from a previous version of the program who've
        # already configured their exclude list, the flag will be absent
        # but the list will be non-empty -- in that case we just set the
        # flag (so this check doesn't re-run on every launch) and leave
        # their state alone.
        if not self.opt_settings.data.get("excluded_default_initialized", False):
            current_excluded = list(self.opt_settings.get_excluded_gear_chars())
            if not current_excluded:
                all_rids = list(self.opt_settings.data.get("characters", {}).keys())
                for name in self.optimizer.character_info.keys():
                    rid = self._resolve_res_id(name)
                    if rid is not None:
                        rid_str = str(rid)
                        if rid_str not in all_rids:
                            all_rids.append(rid_str)
                self.opt_settings.set_excluded_gear_chars(all_rids)
            # Mark flag either way so subsequent launches don't re-check.
            self.opt_settings.data["excluded_default_initialized"] = True

        # Snapshot of which res_ids ALREADY have a per-character entry --
        # we use this BELOW the ensure_character loop to detect newly-
        # captured characters.
        existing_chars = set(self.opt_settings.data.get("characters", {}).keys())

        for name in self.optimizer.character_info.keys():
            rid = self._resolve_res_id(name)
            if rid is None:
                continue
            rid_str = str(rid)
            is_new = rid_str not in existing_chars
            self.opt_settings.ensure_character(rid, name=name)
            if is_new:
                # Q6: brand-new captured character -> default to excluded.
                excluded = list(self.opt_settings.get_excluded_gear_chars())
                if rid_str not in excluded:
                    excluded.append(rid_str)
                    self.opt_settings.set_excluded_gear_chars(excluded)

        # ensure_character doesn't auto-persist; nudge a write if any
        # new entries appeared. _write is safe to call repeatedly.
        if self.opt_settings.data["characters"]:
            self.opt_settings._write()

    def _load_settings_for(self, hero_name: str):
        """Populate every per-character UI var from this character's stored
        settings. Sets the `_loading_settings` guard so the trace callbacks
        don't write back to disk while we're populating.
        """
        if self.opt_settings is None:
            return
        res_id = self._resolve_res_id(hero_name)
        self._current_res_id = res_id

        if res_id is None:
            # Unknown res_id -- use defaults but don't persist (we'd be
            # creating an entry with no good key).
            s = self.opt_settings.get_character_data(0)  # returns defaults
        else:
            self.opt_settings.ensure_character(res_id, name=hero_name)
            s = self.opt_settings.get_character_data(res_id)

        self._loading_settings = True
        try:
            self.optimize_for_level_var.set(s.get("optimize_for_level", 62))
            self.extra_pct_var.set(s.get("extra_pct", 0))
            self.dot_pct_var.set(s.get("dot_pct", 0))
            self.atk_def_split_var.set(s.get("atk_def_split", 0))
            self.shielding_healing_weight_var.set(s.get("shielding_healing_weight", 0))

            fm = s.get("force_main", {})
            for key, _label, _slot, _stat in FORCE_MAIN_DEFS:
                self.force_main_vars[key].set(bool(fm.get(key, False)))

            hal = s.get("have_at_least", {})
            for stat in HAL_ALL_STATS:
                self.have_at_least_vars[stat].set(int(hal.get(stat, 0)))

            self.max_flex_slots_var.set(s.get("max_flex_slots", 6))
            self.set_effect_pct_var.set(s.get("set_effect_pct", 0))
            self.avg_card_dmg_pct_var.set(s.get("avg_card_dmg_pct", 100))
            self.avg_mult_buff_pct_var.set(s.get("avg_mult_buff_pct", 0))
            self.avg_add_buff_pct_var.set(s.get("avg_add_buff_pct", 0))

            selected_set_ids = set(s.get("sets_selected", []))
            for sid, var in self.set_selected_vars.items():
                var.set(sid in selected_set_ids)

            self.element_override_var.set(s.get("element_override") or "")
        finally:
            self._loading_settings = False

        self._update_element_override_visibility(hero_name)

    # ---- Save callbacks (per-control). Suppressed during loads. ----

    def _save_int(self, field: str, value: int):
        if self._loading_settings or self._current_res_id is None:
            return
        if self.opt_settings is None:
            return
        self.opt_settings.set(self._current_res_id, field, int(value))

    def _save_int_safe(self, field: str, var):
        """Trace-callback-safe wrapper around _save_int. Reads an IntVar
        and saves the result; no-ops if the var is in a transient empty
        state (Spinbox content erased mid-edit -- var.get() raises TclError
        until the user types a digit). The same pattern is used inline in
        _save_have_at_least; this helper lets the simple trace lambdas
        share it."""
        try:
            value = var.get()
        except tk.TclError:
            return
        self._save_int(field, value)

    def _save_str(self, field: str, value):
        if self._loading_settings or self._current_res_id is None:
            return
        if self.opt_settings is None:
            return
        self.opt_settings.set(self._current_res_id, field, value)

    def _save_force_main(self, key: str):
        if self._loading_settings or self._current_res_id is None:
            return
        if self.opt_settings is None:
            return
        self.opt_settings.set_force_main(
            self._current_res_id, key, self.force_main_vars[key].get()
        )

    def _save_have_at_least(self, stat: str):
        if self._loading_settings or self._current_res_id is None:
            return
        if self.opt_settings is None:
            return
        try:
            v = int(self.have_at_least_vars[stat].get())
        except (tk.TclError, ValueError):
            return  # spinbox in a half-typed state; ignore
        if v < 0:
            v = 0
        self.opt_settings.set_have_at_least(self._current_res_id, stat, v)

    def _save_sets_selected(self):
        if self._loading_settings or self._current_res_id is None:
            return
        if self.opt_settings is None:
            return
        ids = [sid for sid, var in self.set_selected_vars.items() if var.get()]
        self.opt_settings.set_sets_selected(self._current_res_id, ids)

    def _save_excluded_gear(self):
        """Translate the hero-name-keyed checkboxes back to a res_id list
        and persist. Skipped while no opt_settings is available."""
        if self.opt_settings is None:
            return
        excluded_ids = []
        for hero, var in self.exclude_hero_vars.items():
            if var.get():
                rid = self._resolve_res_id(hero)
                if rid is not None:
                    excluded_ids.append(str(rid))
        self.opt_settings.set_excluded_gear_chars(excluded_ids)

    def _exclude_all_gear(self):
        """Check every box in the exclude list."""
        for var in self.exclude_hero_vars.values():
            var.set(True)
        self._save_excluded_gear()

    def _exclude_no_gear(self):
        """Uncheck every box in the exclude list."""
        for var in self.exclude_hero_vars.values():
            var.set(False)
        self._save_excluded_gear()

    # =================================================================
    # Element override visibility
    # =================================================================

    def _update_element_override_visibility(self, hero_name: str):
        """Show the Element override dropdown only when the character's
        attribute is Unknown (i.e. they're not yet in CHARACTERS). For
        known characters, the override is hidden -- the optimizer uses
        their actual attribute.
        """
        char_data = get_character_by_name(hero_name)
        attribute = char_data.get("attribute", "Unknown")
        is_unknown = attribute == "Unknown"

        if is_unknown:
            # Pack at top of middle pane if not already visible
            if not self.element_override_frame.winfo_ismapped():
                self.element_override_frame.pack(
                    in_=self.element_override_frame.master,
                    fill=tk.X, pady=(0, 5), before=self._first_packed_child(
                        self.element_override_frame.master
                    ),
                )
        else:
            if self.element_override_frame.winfo_ismapped():
                self.element_override_frame.pack_forget()

    def _first_packed_child(self, parent):
        """Return the first packed child of `parent`, or None.

        Used as a `before=` reference so the element-override frame
        always sits at the top of the middle pane when shown.
        """
        for child in parent.winfo_children():
            if child is self.element_override_frame:
                continue
            return child
        return None

    # =================================================================
    # Enable/disable state
    # =================================================================

    def _update_enabled_state(self):
        """Disable interactive controls when no data is loaded."""
        has_data = len(self.optimizer.fragments) > 0
        state = "readonly" if has_data else "disabled"
        if self.hero_combo:
            self.hero_combo.config(state=state)
        # NB: we don't try to disable every individual widget; the combo
        # being disabled prevents character selection, which is enough
        # to keep the Start button from doing anything useful.

    # =================================================================
    # Optimization lifecycle
    # =================================================================

    def run_optimization(self):
        char_name = self.selected_character.get()
        if not char_name:
            messagebox.showwarning("Warning", "Please select a hero")
            return

        if self._current_res_id is None:
            # Allow optimization to proceed for unknown chars but skip
            # the persistence path. They'll use whatever the UI vars hold
            # at the moment.
            pass

        self.cancel_flag[0] = False

        # Item 5: if the chosen sets can't possibly lock enough slots to
        # leave a valid build under the current Maximum Flex Slots cap, bump
        # the cap up to the minimum that works (persisting it + reflecting
        # it in the UI). Returns the new value if a bump happened, else None.
        bumped_to = self._maybe_bump_flex_slots()

        settings = self._build_optimizer_settings()

        # Zero out the optimizer's legacy priority_score system so the
        # slot pre-filter sorts by gear_score (which uses the Scoring
        # tab's active preset). The actual build SCORING is the v1.1.0
        # damage/heal formula in optimizer._compute_optimizer_score --
        # the priority system below only affects which fragments are
        # KEPT per slot before enumeration starts.
        for name in self.optimizer.priorities:
            self.optimizer.priorities[name] = 0
        self.optimizer.recalculate_scores()

        self.progress_label.config(text="Starting...")
        self.result_tree.delete(*self.result_tree.get_children())

        def optimize_thread():
            def progress_cb(checked, total, found):
                self.result_queue.put(("progress", checked, total, found))
            results = self.optimizer.optimize(
                char_name, settings, progress_cb, self.cancel_flag
            )
            # The optimizer now applies the Have-at-least filter inline
            # during enumeration (faster + reports counters). Read its
            # last_optimize_stats to drive the "no builds matched" popup
            # message in check_queue.
            stats = getattr(self.optimizer, "last_optimize_stats", {}) or {}
            self.result_queue.put(("done", results, stats))

        threading.Thread(target=optimize_thread, daemon=True).start()

        # Item 5: surface the auto-bump AFTER kicking off the worker thread,
        # so the notice and the optimization run "in parallel" -- the modal
        # dialog blocks only the UI thread; the daemon worker keeps going.
        if bumped_to is not None:
            # Task 2 (round 9): pad the message out so the dialog is wide
            # enough for the title ("Not Enough Flex Slots") not to clip --
            # messagebox widths are driven by the message text, not the title.
            messagebox.showinfo(
                "Not Enough Flex Slots",
                f"Max Flex Slots was too low for the chosen sets — "
                f"increased it to {bumped_to}.",
            )

    def _max_lockable_slots(self, sets_selected: list) -> int:
        """Maximum number of slots that could be locked into satisfied
        chosen-set bonuses, given the user's selected sets.

        Considers the achievable combo shapes (mirrors optimizer
        _count_locked_slots' taxonomy):
          one 4pc + one 2pc        -> 6
          three 2pc                -> 6
          one 4pc alone            -> 4
          two 2pc                  -> 4
          one 2pc alone            -> 2
          nothing selected         -> 0
        Returns the best (largest) lockable count. `6 - this` is the
        minimum Maximum-Flex-Slots value that still admits a valid build.
        """
        num_4pc = sum(1 for sid in sets_selected
                      if SETS.get(sid, {}).get("pieces") == 4)
        num_2pc = sum(1 for sid in sets_selected
                      if SETS.get(sid, {}).get("pieces") == 2)
        best = 0
        if num_4pc >= 1 and num_2pc >= 1:
            best = max(best, 6)
        if num_2pc >= 3:
            best = max(best, 6)
        if num_4pc >= 1:
            best = max(best, 4)
        if num_2pc >= 2:
            best = max(best, 4)
        if num_2pc >= 1:
            best = max(best, 2)
        return best

    def _maybe_bump_flex_slots(self) -> Optional[int]:
        """If the current Maximum Flex Slots is too low for the chosen sets to
        leave any valid build, raise it to the minimum that works. Persists
        the new value to OptimizerSettingsManager and updates the UI spinbox.

        Returns the new flex value if a bump was performed, else None.

        Example: one 2-piece set chosen with Max Flex = 2 -> the set locks
        at most 2 slots, leaving 4 that must be flex -> bump to 4.
        """
        if self.opt_settings is None or self._current_res_id is None:
            return None
        s = self.opt_settings.get_character_data(self._current_res_id)
        sets_selected = list(s.get("sets_selected", []))
        cur_flex = int(s.get("max_flex_slots", 6))
        min_flex = 6 - self._max_lockable_slots(sets_selected)
        if cur_flex >= min_flex:
            return None
        # Persist + reflect in the UI var. Guard the trace so we don't write
        # twice (the var-trace would otherwise also fire _save_int).
        self.opt_settings.set(self._current_res_id, "max_flex_slots", min_flex)
        self._loading_settings = True
        try:
            self.max_flex_slots_var.set(min_flex)
        finally:
            self._loading_settings = False
        return min_flex

    def cancel_optimization(self):
        self.cancel_flag[0] = True
        self.progress_label.config(text="Cancelling...")

    def _build_optimizer_settings(self) -> dict:
        """Build the full optimizer settings dict from the current character's
        persisted state.

        Combines:
          * Legacy filter fields used by `get_gear_by_slot` (set requirements,
            main-stat filters per slot, top_percent, excluded_heroes).
          * v1.1.0 fields used by `calculate_build_stats` and
            `_compute_optimizer_score` (Extra%, DoT%, ATK/DEF split,
            shield/heal weight, set-effect %, avg buff fields, level
            stepper, element override, have-at-least minimums).

        See docs/game_formulas.md §8 for the formula consumers of each field.
        """
        # Defaults for the "no current character" case (shouldn't happen
        # in practice -- run_optimization gates on hero selection).
        if self.opt_settings is None or self._current_res_id is None:
            s = {
                "force_main": {k: False for k in ("slot4_hp", "slot5_hp", "slot6_hp", "slot6_ego")},
                "sets_selected": [],
                "max_flex_slots": 6,
                "have_at_least": {},
            }
        else:
            s = self.opt_settings.get_character_data(self._current_res_id)

        # Force-main flags -> per-slot main stat filter lists (None = "no filter").
        slot4_filter = ["HP%"] if s["force_main"].get("slot4_hp") else None
        slot5_filter = ["HP%"] if s["force_main"].get("slot5_hp") else None
        slot6_filter = []
        if s["force_main"].get("slot6_hp"):
            slot6_filter.append("HP%")
        if s["force_main"].get("slot6_ego"):
            slot6_filter.append("Ego")
        slot6_filter = slot6_filter if slot6_filter else None

        # Selected sets -> split into 4-piece and 2-piece lists for the
        # optimizer's legacy fields (kept for back-compat; the Phase 4
        # locked-count rule uses `sets_selected` directly).
        selected_4pc = []
        selected_2pc = []
        for sid in s.get("sets_selected", []):
            sinfo = SETS.get(sid)
            if sinfo is None:
                continue
            if sinfo.get("pieces") == 4:
                selected_4pc.append(sid)
            elif sinfo.get("pieces") == 2:
                selected_2pc.append(sid)

        # Excluded characters' gear: res_ids -> hero names
        excluded_heroes = []
        excluded_res_ids = set(self.opt_settings.get_excluded_gear_chars()
                                if self.opt_settings else [])
        # Don't exclude the current character's gear -- their pieces should
        # be available for re-equip.
        current_rid_str = str(self._current_res_id) if self._current_res_id else None
        for hero_name in self.optimizer.characters.keys():
            rid = self._resolve_res_id(hero_name)
            if rid is None:
                continue
            rid_str = str(rid)
            if rid_str == current_rid_str:
                continue
            if rid_str in excluded_res_ids:
                excluded_heroes.append(hero_name)

        return {
            # ----- Legacy filter fields (consumed by get_gear_by_slot + optimize) -----
            "four_piece_sets": selected_4pc,
            "two_piece_sets": selected_2pc,
            "main_stat_4": slot4_filter,
            "main_stat_5": slot5_filter,
            "main_stat_6": slot6_filter,
            "top_percent": 20,           # internal; not user-facing
            "include_equipped": True,    # always include; exclude list is the new gate
            "excluded_heroes": excluded_heroes,
            "max_results": 100,
            # ----- Phase 4 set-combo fields (consumed by optimize's locked-count rule) -----
            "sets_selected": list(s.get("sets_selected", [])),
            "max_flex_slots": int(s.get("max_flex_slots", 6)),
            # ----- Phase 5: weights for the slot pre-filter sort -----
            # The optimizer ranks fragments per slot by their score under
            # these weights before applying the Top filter. Resolved from
            # CharacterPresetManager (character's assignment) -> active
            # preset -> empty (all-1.0) per _get_weights_for_character.
            # When None or empty, the optimizer falls back to fragment.
            # gear_score (the cached value from the active preset).
            "slot_filter_weights": self._get_weights_for_character(
                self.selected_character.get()
            ) or None,
            # ----- v1.1.0 scoring fields (consumed by calculate_build_stats + _compute_optimizer_score) -----
            "optimize_for_level": s.get("optimize_for_level", 62),
            "extra_pct": s.get("extra_pct", 0),
            "dot_pct": s.get("dot_pct", 0),
            "atk_def_split": s.get("atk_def_split", 0),
            "shielding_healing_weight": s.get("shielding_healing_weight", 0),
            "set_effect_pct": s.get("set_effect_pct", 0),
            "avg_card_dmg_pct": s.get("avg_card_dmg_pct", 100),
            "avg_mult_buff_pct": s.get("avg_mult_buff_pct", 0),
            "avg_add_buff_pct": s.get("avg_add_buff_pct", 0),
            "element_override": s.get("element_override"),
            "have_at_least": s.get("have_at_least", {}),
        }

    # =================================================================
    # Queue + result display
    # =================================================================

    def check_queue(self):
        try:
            while True:
                msg = self.result_queue.get_nowait()
                if msg[0] == "progress":
                    _, checked, total, found = msg
                    pct = (checked / total * 100) if total > 0 else 0
                    # Item 6: the optimizer trims its in-flight results list
                    # periodically (keeping top max_results), so a live
                    # "Found N" count oscillates wildly between max_results and
                    # ~10x that. We deliberately DON'T surface the running
                    # count -- only progress through the search space. The
                    # final, accurate build count is shown in the "done"
                    # branch below.
                    self.progress_label.config(
                        text=f"Checked {checked:,} ({pct:.1f}%)"
                    )
                elif msg[0] == "done":
                    _, results, stats = msg
                    self.optimization_results = results
                    self.display_results(results)
                    passed_sets = stats.get("passed_set_reqs", 0)
                    passed_hal = stats.get("passed_have_at_least", 0)
                    if results:
                        self.progress_label.config(
                            text=f"Done! {len(results)} builds"
                        )
                    elif passed_sets > 0:
                        # Candidates passed the set requirements but ALL got
                        # filtered by Have-at-least. Show actionable hint.
                        self.progress_label.config(
                            text=f"Done! 0 builds (filtered from {passed_sets})"
                        )
                        messagebox.showinfo(
                            "No builds match",
                            "0 builds matched the 'Have at least' minimums. "
                            "Try lowering one or more thresholds in the right panel."
                        )
                    else:
                        # No candidate combinations even satisfied set requirements
                        # (e.g. no 4-piece set selected has 4 candidates in slot N,
                        # or all selected sets together can't fit in 6 slots).
                        self.progress_label.config(
                            text="Done! 0 builds (no candidates satisfied set requirements)"
                        )
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)

    def display_results(self, results: list):
        self.result_tree.delete(*self.result_tree.get_children())
        char = self.selected_character.get()
        # Q2 (round 10): resolve the user's selected sets for THIS character
        # once so _format_set_summary can tag accidental sets with "(F)".
        selected_set_ids = set()
        if self.opt_settings is not None and self._current_res_id is not None:
            try:
                s = self.opt_settings.get_character_data(self._current_res_id)
                selected_set_ids = set(s.get("sets_selected", []))
            except Exception:
                selected_set_ids = set()
        for i, (gear, score, stats) in enumerate(results[:100]):
            sets_str = self._format_set_summary(gear, selected_set_ids)
            # Item 1 (round 7): Element% isn't part of calculate_build_stats'
            # output, so augment to compute it for this build/character.
            # Ego is already in the stats dict. The value tuple order must
            # match the column order: ...cdmg, element, extra, dot, ego.
            stats = self._augment_stats(stats, gear, char)
            self.result_tree.insert("", tk.END, values=(
                f"{score:.0f}", sets_str,
                f"{stats.get('ATK', 0):.0f}",
                f"{stats.get('HP', 0):.0f}",
                f"{stats.get('DEF', 0):.0f}",
                f"{stats.get('CRate', 0):.1f}",
                f"{stats.get('CDmg', 0):.1f}",
                f"{stats.get('Element%', 0):.1f}",
                f"{stats.get('Extra DMG%', 0):.1f}",
                f"{stats.get('DoT%', 0):.1f}",
                f"{stats.get('Ego', 0):.0f}",
            ), iid=str(i))

    def _format_set_summary(self, gear, selected_set_ids=None) -> str:
        """Build the Results 'Sets' column string for one build (Item 9).

        Ordering: 4-piece active sets first, then 2-piece active sets, then
        a single "N Flex" token if any wildcard slots remain. Alphabetical
        (ascending) within each category.

        Only sets whose equipped count actually MEETS their piece
        requirement are named (an inactive 3-of-a-4pc set contributes its
        pieces to the flex count, not a name). Overflow pieces of an active
        set (e.g. a 6th piece of a 4-piece set) also count as flex.

        Name shortening: names <= 15 chars are kept as-is; longer names are
        collapsed to their first word.

        Q2 (round 10): `selected_set_ids` is the set of set IDs the user
        marked as desirable in the Optimizer tab's Set Configuration. When
        a build's gear contains an active set that ISN'T in this list
        (i.e. the optimizer's flex slots happened to roll a complete set),
        we tag the name with "(F)" so the user can tell the difference
        between an intentionally chosen set and an accidental one. The
        bonus is still active either way -- the tag is purely informational.
        Pass None / empty to skip the tagging (e.g. for legacy callers).
        """
        if selected_set_ids is None:
            selected_set_ids = set()
        else:
            selected_set_ids = set(selected_set_ids)

        set_counts: dict = {}
        for p in gear:
            set_counts[p.set_id] = set_counts.get(p.set_id, 0) + 1

        four_active = []
        two_active = []
        flex_count = 0
        for sid, count in set_counts.items():
            sinfo = SETS.get(sid)
            if sinfo is None:
                # Unknown set id -- treat every piece as a wildcard.
                flex_count += count
                continue
            pieces = sinfo.get("pieces", 2)
            if count >= pieces:
                name = sinfo["name"]
                short = name if len(name) <= 15 else name.split()[0]
                if sid not in selected_set_ids:
                    short = f"{short} (F)"
                if pieces == 4:
                    four_active.append(short)
                else:
                    two_active.append(short)
                # Pieces beyond the bonus threshold are wildcards.
                flex_count += (count - pieces)
            else:
                # Not enough pieces to trigger the bonus -- all wildcards.
                flex_count += count

        four_active.sort()
        two_active.sort()
        parts = four_active + two_active
        if flex_count > 0:
            parts.append(f"{flex_count} Flex")
        return " + ".join(parts)

    def sort_results(self, col: str):
        if not self.optimization_results:
            return
        if col == self.result_sort_col:
            self.result_sort_reverse = not self.result_sort_reverse
        else:
            self.result_sort_col = col
            self.result_sort_reverse = False

        # Sort the underlying list (re-indexed when redisplayed)
        char = self.selected_character.get()

        def _elem(e):
            # Item 1 (round 7): Element% isn't stored in e[2]; compute it
            # from the build's gear + the current character's attribute,
            # matching _augment_stats' logic.
            attribute = self._character_attribute(char)
            if not attribute:
                return 0.0
            target = f"{attribute} DMG%"
            return sum(p.main_stat.value for p in e[0]
                       if p.main_stat and p.main_stat.name == target)

        col_map = {
            "score": lambda e: e[1],
            "sets":  lambda e: "",
            "atk":   lambda e: e[2].get("ATK", 0),
            "hp":    lambda e: e[2].get("HP", 0),
            "def":   lambda e: e[2].get("DEF", 0),
            "crate": lambda e: e[2].get("CRate", 0),
            "cdmg":  lambda e: e[2].get("CDmg", 0),
            "element": _elem,
            "extra": lambda e: e[2].get("Extra DMG%", 0),
            "dot":   lambda e: e[2].get("DoT%", 0),
            "ego":   lambda e: e[2].get("Ego", 0),
        }
        key_func = col_map.get(col, col_map["score"])
        # Item 1 (round 5): secondary sort is always by score. Python's sort
        # is stable, so a two-pass approach (sort by score first, then by
        # the clicked column) leaves builds with equal primary values
        # ordered by score-descending. When the primary column IS score,
        # one pass suffices.
        if col == "score":
            sorted_entries = sorted(
                self.optimization_results,
                key=col_map["score"],
                reverse=not self.result_sort_reverse,
            )
        else:
            by_score = sorted(
                self.optimization_results,
                key=col_map["score"],
                reverse=True,  # secondary always score-descending
            )
            sorted_entries = sorted(
                by_score,
                key=key_func,
                reverse=not self.result_sort_reverse,
            )
        self.optimization_results = sorted_entries
        self.display_results(sorted_entries)

    def on_result_select(self, event):
        sel = self.result_tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        if idx >= len(self.optimization_results):
            return

        gear, score, new_stats = self.optimization_results[idx]
        char = self.selected_character.get()
        current_gear = self.optimizer.characters.get(char, [])
        current_stats = self.optimizer.calculate_build_stats(current_gear, char)

        # Item 8: inject Element% (not part of calculate_build_stats) so the
        # Stats Comparison tree can show it under Totals.
        current_stats = self._augment_stats(current_stats, current_gear, char)
        new_stats = self._augment_stats(new_stats, gear, char)

        self._populate_stats_compare(current_stats, new_stats)
        self._populate_detail(gear)

    def show_current_stats(self, char_name: str):
        gear = self.optimizer.characters.get(char_name, [])
        stats = self.optimizer.calculate_build_stats(gear, char_name)
        stats = self._augment_stats(stats, gear, char_name)
        self._populate_stats_compare(stats, None)

    def _character_attribute(self, char_name: str) -> str:
        """Resolve the character's Element attribute for Element% display.

        Known characters -> their CHARACTERS attribute. Unknown-attribute
        characters -> the user's element_override (the UI var holds the
        currently-selected character's saved override). Empty string means
        "no element" -> Element% shows 0.
        """
        char_data = get_character_by_name(char_name)
        attribute = char_data.get("attribute", "Unknown")
        if attribute == "Unknown":
            return self.element_override_var.get() or ""
        return attribute

    def _augment_stats(self, stats: dict, gear: list, char_name: str) -> dict:
        """Return a copy of `stats` with an 'Element%' key added.

        Element% = sum of slot-5 Element DMG% main stats whose element
        matches the character's attribute (e.g. 'Passion DMG%' for a Passion
        character). 0 when no matching main stat is equipped or the
        character has no resolvable element. Mirrors the optimizer's
        Element-DMG pickup in _compute_optimizer_score.
        """
        attribute = self._character_attribute(char_name)
        elem = 0.0
        if attribute:
            target = f"{attribute} DMG%"
            for p in gear:
                if p.main_stat and p.main_stat.name == target:
                    elem += p.main_stat.value
        out = dict(stats)
        out["Element%"] = elem
        return out

    # =================================================================
    # Item 11: "Show all stat contributions" right-click breakdown
    # =================================================================

    def _show_stats_context_menu(self, event):
        """Right-click on the Stats Comparison tree -> two options for the
        full per-source breakdown:
          (a) selected build       = the row currently picked in Results
          (b) currently equipped   = the character's actual in-game gear
        Item 6 split: a single menu item used to do (a) with fallback to (b);
        now the user picks which one explicitly.
        """
        if not self.selected_character.get():
            return
        menu = tk.Menu(self.stats_tree, tearoff=0)
        menu.add_command(
            label="Show all stat contributions (selected build)",
            command=lambda: self._show_breakdown_popup(use_selected=True),
        )
        menu.add_command(
            label="Show all stat contributions (currently equipped)",
            command=lambda: self._show_breakdown_popup(use_selected=False),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_breakdown_popup(self, use_selected: bool):
        """Resolve the gear to break down and open the popup.

        use_selected=True  -> the optimizer-proposed build from the
                              currently-selected Results row. If no row is
                              selected, ask the user to pick one (don't
                              silently fall back to currently-equipped;
                              Item 6 separates the two intents).
        use_selected=False -> the character's currently-equipped gear.
        """
        char = self.selected_character.get()
        if not char:
            return
        if use_selected:
            sel = self.result_tree.selection()
            if not sel:
                messagebox.showinfo(
                    "Stat Contributions (selected build)",
                    "No optimizer result is currently selected. Pick a row\n"
                    "from the Results list, or use the 'currently equipped'\n"
                    "option from the right-click menu.",
                )
                return
            try:
                idx = int(sel[0])
            except (ValueError, IndexError):
                return
            if idx < 0 or idx >= len(self.optimization_results):
                return
            gear = self.optimization_results[idx][0]
            is_proposed = True
            label = "selected build"
        else:
            gear = self.optimizer.characters.get(char, [])
            is_proposed = False
            label = "currently equipped"
            if not gear:
                messagebox.showinfo(
                    "Stat Contributions (currently equipped)",
                    f"{char} has no Memory Fragments equipped.",
                )
                return

        settings = self._build_optimizer_settings()
        try:
            bd = self.optimizer.compute_build_breakdown(gear, char, settings)
        except Exception as e:
            messagebox.showerror(
                "Stat Contributions",
                f"Could not compute the breakdown:\n\n{e}",
            )
            return
        text = self._format_breakdown_text(char, is_proposed, bd)
        self._show_text_popup(f"Stat Contributions ({label}) - {char}", text)

    @staticmethod
    def _format_breakdown_text(char: str, is_proposed: bool, bd: dict) -> str:
        """Render the breakdown dict into the fixed-width text block shown in
        the popup. Column widths per the v1.1.0 popup spec (items 8 + 9):

          ATK/DEF/HP:  Base 3, Partner 3, MF% 4, Pot 3, MF Flat 2,
                         Affection 2, Partner% 4, Set Effect Sum 4,
                         Equip (apx.) 2, Other = checkmark / cross (width 1)
          CRate/CDmg:  Base 5, MF Main 4, MF Sub Sum 4, Set Effect Sum 4,
                         Other 4 (or just the cross when zero)
          Element%, ExtrDMG%, Dot DMG%, Ego:
                       MF Main / MF Sub Sum 4 each, Set Effect Sum 4,
                         Other 4 (or just the cross when zero)
          xDMG% / +DMG%:  4 (set-effect contributions only; the user's
                         Avg Multi Buff% / Avg Add Buff% fields are
                         deliberately excluded per Item 7)

        The "0 if cross" rule for Other: when the value is zero, we render
        a bare cross mark (1 char) rather than a 4-wide padded zero, so the
        cross stands out vs. legitimate-but-small numeric contributions.
        """
        def _int(v, w):
            return f"{v:>{w}.0f}"

        def _dec(v, w):
            return f"{v:>{w}.1f}"

        def _other(v, w):
            # 4-wide decimal when non-zero; bare cross when zero (Item 8).
            return f"{v:>{w}.1f}" if abs(v) > 0.05 else "\u2717"

        def _flag(present):
            return "\u2713" if present else "\u2717"

        which = "optimizer-proposed" if is_proposed else "currently equipped"
        lines = [f"{char}  ({which} build)", ""]

        for stat in ("ATK", "DEF", "HP"):
            d = bd[stat]
            lines.append(
                f"{stat:<3}: {d['sum']:>4.0f} <= "
                f"Base {_int(d['base'], 3)}, "
                f"Partner {_int(d['partner_flat'], 3)}, "
                f"MF% {_dec(d['mf_pct'], 4)}, "
                f"Pot {_int(d['pot_pct'], 3)}, "
                f"MF Flat {_int(d['mf_flat'], 2)}, "
                f"Affection {_int(d['affection'], 2)}, "
                f"Partner% {_dec(d['partner_pct'], 4)}, "
                f"Set Effect Sum {_dec(d['set_effect'], 4)}, "
                f"Equip (apx.) {_int(d['equip_flat'], 2)}, "
                f"Other {_flag(d['other_present'])}"
            )
        lines.append("")

        # Item 1 (round 6): the stats below now lead with their total
        # followed by " <= " (matching the ATK/DEF/HP format). Totals are
        # padded to width 5. The total is the sum of the named components,
        # which reconciles with calculate_build_stats' value for that stat.
        cr = bd["CRate"]
        cr_total = cr["base"] + cr["mf_main"] + cr["mf_sub"] + cr["set_effect"] + cr["other"]
        lines.append(
            f"CritRate: {cr_total:>5.1f} <= Base {_dec(cr['base'], 5)}"
            f" + MF Main {_dec(cr['mf_main'], 4)}"
            f" + MF Sub Sum {_dec(cr['mf_sub'], 4)}"
            f" + Set Effect Sum {_dec(cr['set_effect'], 4)}"
            f" + Other {_other(cr['other'], 4)}"
        )
        cd = bd["CDmg"]
        cd_total = cd["base"] + cd["mf_main"] + cd["mf_sub"] + cd["set_effect"] + cd["other"]
        lines.append(
            f"CritDMG%: {cd_total:>5.1f} <= Base {_dec(cd['base'], 5)}"
            f" + MF Main {_dec(cd['mf_main'], 4)}"
            f" + MF Sub Sum {_dec(cd['mf_sub'], 4)}"
            f" + Set Effect Sum {_dec(cd['set_effect'], 4)}"
            f" + Other {_other(cd['other'], 4)}"
        )
        el = bd["Element%"]
        el_total = el["mf_main"] + el["set_effect"] + el["other"]
        lines.append(
            f"Element%: {el_total:>5.1f} <= MF Main {_dec(el['mf_main'], 4)}"
            f" + Set Effect Sum {_dec(el['set_effect'], 4)}"
            f" + Other {_other(el['other'], 4)}"
        )
        ex = bd["Extra DMG%"]
        ex_total = ex["mf_sub"] + ex["set_effect"] + ex["other"]
        lines.append(
            f"ExtrDMG%: {ex_total:>5.1f} <= MF Sub Sum {_dec(ex['mf_sub'], 4)}"
            f" + Set Effect Sum {_dec(ex['set_effect'], 4)}"
            f" + Other {_other(ex['other'], 4)}"
        )
        dt = bd["DoT%"]
        dt_total = dt["mf_sub"] + dt["set_effect"] + dt["other"]
        lines.append(
            f"DoT DMG%: {dt_total:>5.1f} <= MF Sub Sum {_dec(dt['mf_sub'], 4)}"
            f" + Set Effect Sum {_dec(dt['set_effect'], 4)}"
            f" + Other {_other(dt['other'], 4)}"
        )
        lines.append("")  # Item 6: blank line before Ego
        eg = bd["Ego"]
        eg_total = eg["mf_main"] + eg["mf_sub"] + eg["set_effect"] + eg["other"]
        lines.append(
            f"Ego: {eg_total:>4.1f} <= MF Main {_dec(eg['mf_main'], 4)}"
            f" + MF Sub Sum {_dec(eg['mf_sub'], 4)}"
            f" + Set Effect Sum {_dec(eg['set_effect'], 4)}"
            f" + Other {_other(eg['other'], 4)}"
        )
        lines.append("")
        lines.append(f"xDMG%: {_dec(bd['xDMG%'], 4)}")
        lines.append(f"+DMG%: {_dec(bd['+DMG%'], 4)}")
        # Item 8: "Potential 7" ATK/DEF/HP -- the inner stat values used by
        # the Have-at-least minimum check: calculated WITHOUT Partner% and
        # WITHOUT Equipment. Item 1 (round 6): no blank lines between the
        # three rows, and an explanatory note directly below. "HP " gets a
        # trailing space so its colon lines up with ATK:/DEF:.
        lines.append("")
        lines.append(f"Potential 7 ATK: {bd['ATK']['inner']:>4.0f}")
        lines.append(f"Potential 7 DEF: {bd['DEF']['inner']:>4.0f}")
        lines.append(f"Potential 7 HP : {bd['HP']['inner']:>4.0f}")
        lines.append(
            "Note: For Potential 7, ATK/DEF/HP are calculated without "
            "Partner% and Equipment."
        )
        return "\n".join(lines)

    def _show_text_popup(self, title: str, text: str):
        """Show `text` in a resizable Toplevel with a monospace Text widget,
        sized so each line fits without wrapping. v1.1.0 polish: cap raised
        from 120 to 200 chars so the wider ATK/DEF/HP lines (now including
        Set Effect Sum) display on one line."""
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=self.colors["bg"])
        top.transient(self.root)

        lines = text.split("\n")
        max_width = max((len(l) for l in lines), default=40)

        txt = tk.Text(
            top, wrap=tk.NONE, font=("Consolas", 10),
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            width=min(max_width + 2, 200),
            height=min(len(lines) + 1, 40),
            bd=0, padx=10, pady=10,
            insertbackground=self.colors["fg"],
        )
        txt.insert("1.0", text)
        txt.config(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        ttk.Button(top, text="Close", command=top.destroy).pack(pady=(0, 8))

    def _populate_stats_compare(self, current_stats: dict, new_stats: Optional[dict]):
        self.stats_tree.delete(*self.stats_tree.get_children())
        # Item 8: single "Totals" section. Element% added; Extra DMG%, DoT%,
        # and Ego moved up from the old "Substats" section.
        # Item 3 polish: each row tuple now carries (internal_key, decimals,
        # display_label). The internal_key is used for stats.get() lookup;
        # the display_label is what the user sees. None display_label means
        # "use internal_key as the label".
        # Item 10: rows are NO LONGER skipped when current==0 and new is
        # 0/None -- every configured stat is shown, even at zero.
        stat_order = [
            ("- Totals -", None, None),  # header
            ("ATK", 0, None),
            ("DEF", 0, None),
            ("HP", 0, None),
            ("CRate", 1, "Crit%"),
            ("CDmg", 1, "CDMG%"),
            ("Element%", 1, None),
            ("Extra DMG%", 1, "Extra%"),
            ("DoT%", 1, None),
            ("Ego", 0, None),
            # Item 3 (round 6): blank separator then the Potential-7 values
            # (inner ATK/DEF/HP -- without Partner% or Equipment, same as
            # the popup's "Potential 7" rows and the Have-at-least check).
            ("", None, None),  # blank separator row
            ("_inner_atk", 0, "Pot7 ATK"),
            ("_inner_def", 0, "Pot7 DEF"),
            ("_inner_hp",  0, "Pot7 HP"),
        ]
        for stat_key, decimals, display in stat_order:
            if decimals is None:
                # Header row
                self.stats_tree.insert("", tk.END,
                                        values=(stat_key, "", "", ""),
                                        tags=("header",))
                continue
            label = display if display is not None else stat_key
            curr = current_stats.get(stat_key, 0)
            new = new_stats.get(stat_key, 0) if new_stats is not None else None
            # Item 10: always show -- no zero-skip filter.

            curr_fmt = (f"{curr:.0f}" if decimals == 0 else f"{curr:.1f}")
            if new is None:
                self.stats_tree.insert("", tk.END,
                                        values=(label, curr_fmt, "-", "-"))
                continue
            diff = new - curr
            new_fmt = (f"{new:.0f}" if decimals == 0 else f"{new:.1f}")
            sign = "+" if diff > 0 else ""
            diff_fmt = f"{sign}{diff:.{decimals}f}"
            tag = "pos" if diff > 0.1 else "neg" if diff < -0.1 else ""
            self.stats_tree.insert("", tk.END,
                                    values=(label, curr_fmt, new_fmt, diff_fmt),
                                    tags=(tag,))

        self.stats_tree.tag_configure("pos", foreground=self.colors["green"])
        self.stats_tree.tag_configure("neg", foreground=self.colors["red"])
        self.stats_tree.tag_configure("header", foreground=self.colors["fg_dim"])

    def _populate_detail(self, gear):
        # Resolve the weights to use for this build's GS / Potential columns.
        # Per Task 5 of the v1.1.0 spec: the detail tree shows GS through the
        # lens of the CURRENT CHARACTER's assigned preset (Combatants tab
        # assignment), not the globally-active Scoring tab preset. So we
        # don't read fragment.gear_score / potential_low/high (those are
        # cached against the active preset) -- we recompute with the
        # character's weights and a per-fragment bounds cache.
        char_name = self.selected_character.get()
        weights = self._get_weights_for_character(char_name)

        # Per-main-stat bounds cache: there are at most ~16 distinct main
        # stat names across 6 fragments, so this caps at 6 entries in
        # practice. Skips the cubic-loop bounds work on duplicate mains.
        bounds_cache: dict = {}
        def _bounds(frag):
            key = frag.main_stat.name if frag.main_stat else None
            cached = bounds_cache.get(key)
            if cached is None:
                cached = bounds_for_fragment(frag, weights)
                bounds_cache[key] = cached
            return cached

        self.detail_tree.delete(*self.detail_tree.get_children())
        # Q8 (round 10): collect the current snapshot's MF ids so the Owner
        # column can show "(deleted)" for any cached gear ref that no longer
        # exists in optimizer.fragments. The kept (stale) MF still renders
        # its last-known slot/set/main/subs -- only the Owner column
        # changes -- so the user can still see WHAT used to be in that slot.
        current_ids = {getattr(f, "id", None) for f in self.optimizer.fragments}
        for p in sorted(gear, key=lambda x: x.slot_num):
            b = _bounds(p)
            gs = compute_fragment_gs(p, weights, bounds=b)
            pot_low, pot_high = compute_fragment_potential(p, weights, bounds=b)

            # Item 5: space between "<stat name>:" and the value.
            # Item 3: stat names translated through DISPLAY_NAMES so the
            # user-facing label uses the new terminology (e.g. "ATK Flat"
            # instead of "Flat ATK", "Crit%" instead of "CRate"). The
            # internal stat.name is unchanged -- this is purely a display
            # translation at the point of rendering.
            subs = []
            for s in p.substats[:4]:
                sub_label = DISPLAY_NAMES.get(s.name, s.name)
                subs.append(f"{sub_label}: {s.format_value()}")
            while len(subs) < 4:
                subs.append("-")
            if p.main_stat:
                main_label = DISPLAY_NAMES.get(p.main_stat.name, p.main_stat.name)
                main_str = f"{main_label}: {p.main_stat.format_value()}"
            else:
                main_str = "-"
            # n3 (this round): the GS column shows the current GS when the MF
            # is at max level (no upgrade headroom -> pot_low == pot_high),
            # or the Potential range (low-high) when it can still be leveled.
            if pot_low == pot_high:
                gs_cell = f"{gs:.0f}"
            else:
                gs_cell = f"{pot_low:.0f}-{pot_high:.0f}"
            # Q8 (round 10): mark MFs that no longer exist in the snapshot.
            if getattr(p, "id", None) not in current_ids:
                owner = "(deleted)"
            else:
                owner = p.equipped_to or ""
            self.detail_tree.insert("", tk.END, values=(
                f"{p.level} {p.slot_name}",
                p.set_name, main_str, *subs,
                gs_cell, owner,
            ), tags=(f"r{p.rarity_num}",))
        self.detail_tree.tag_configure("r4", foreground=RARITY_COLORS[4])
        self.detail_tree.tag_configure("r3", foreground=RARITY_COLORS[3])

    def _get_weights_for_character(self, char_name: str) -> dict:
        """Resolve the scoring weights for the current character's GS column.

        Resolution order (matches Heroes / Combatants tab):
          1. Character's assigned preset via CharacterPresetManager.get_preset_for.
             If the assigned preset name is missing or no longer exists in
             PresetManager, fall through (don't error).
          2. Currently-active preset (PresetManager.selected_preset).
          3. Empty dict — the GS helpers treat that as "all weights = 1.0".

        Returns:
            A dict[stat_name, weight] (padded by PresetManager.get_preset to
            cover SUPPORTED_STATS), OR an empty dict for the default-weights
            case. Callers pass straight into compute_fragment_gs /
            compute_fragment_potential.
        """
        cpm = self.context.character_preset_manager
        pm = self.context.preset_manager
        if pm is None:
            return {}

        # 1) Character's assignment
        if cpm is not None and char_name:
            assigned = cpm.get_preset_for(char_name)
            if assigned:
                weights = pm.get_preset(assigned)
                if weights is not None:
                    return weights

        # 2) Active preset
        active = pm.selected_preset
        if active:
            weights = pm.get_preset(active)
            if weights is not None:
                return weights

        # 3) Default
        return {}

    # =================================================================
    # Hero selection
    # =================================================================

    def on_hero_select(self, event=None):
        char = self.selected_character.get()
        if not char:
            return
        # Load persisted settings into the UI vars
        self._load_settings_for(char)
        # Item 3: always refresh the Stats Comparison tree on character
        # switch -- even when the character has no Memory Fragments
        # equipped. calculate_build_stats handles an empty gear list (returns
        # base + partner + affection + equipment stats); without this call,
        # the stats_tree retained the PREVIOUSLY-selected character's stats
        # when the new character had no gear.
        self.show_current_stats(char)
        # Task 3 (round 10): refresh the Preset label below the combobox.
        self._update_preset_label()
        # Q1 (round 10): refresh the exclude checklist so the previously-
        # selected character's gray+strike treatment is removed and the
        # newly-selected character's is applied. refresh_exclude_heroes
        # has a skip-if-unchanged guard, so calling it on every selection
        # is cheap when only the visual current-char marker changed.
        if self.exclude_heroes_frame is not None:
            self.refresh_exclude_heroes()

    def _update_preset_label(self):
        """Update the Preset label below the combobox to show the current
        character's assigned preset (via CharacterPresetManager). Shows
        "Preset: (default)" when no assignment exists -- mirrors the
        fallback in _get_weights_for_character. NB: if the user changes
        the assignment from a different tab, this label only refreshes
        the next time on_hero_select fires (i.e. when they re-pick a
        character here).
        """
        if self.preset_label is None:
            return
        char = self.selected_character.get()
        cpm = getattr(self.context, "character_preset_manager", None)
        assigned = None
        if cpm is not None and char:
            try:
                assigned = cpm.get_preset_for(char)
            except Exception:
                assigned = None
        text = f"Preset: {assigned}" if assigned else "Preset: (default)"
        self.preset_label.config(text=text)

    # =================================================================
    # Spinbox mousewheel helper
    # =================================================================

    def _spinbox_wheel(self, event, spinbox):
        """Increment/decrement a Spinbox on mouse wheel events.

        Tk's tk.Spinbox doesn't bind <MouseWheel> by default. event.delta
        is positive for wheel-up (increment) and negative for wheel-down
        (decrement) on Windows; macOS / Linux differ but the sign is
        consistent. We rely on Tk's invoke() which already handles the
        from_/to bounds.
        """
        if event.delta > 0:
            spinbox.invoke("buttonup")
        elif event.delta < 0:
            spinbox.invoke("buttondown")
        return "break"
