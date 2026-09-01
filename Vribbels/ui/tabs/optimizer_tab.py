"""
Optimization configuration and execution tab.

Per-character persistent settings, set combinations handled internally
by the optimizer.

UI layout (top to bottom)
-------------------------
  Toolbar: [Combatant ▼] [Optimize for LVL ↕] [Start] [Stop] [help text]  [status]
  Body (fixed 3-column grid, non-draggable):
    Left:    Stats Comparison (Treeview; right-click -> stat contributions)
    Middle:  Configuration column, top to bottom:
                Element override (only shown for Unknown-attribute chars)
                Important Settings | Have at Least (side by side)
                Set Configuration (Flex Slots + buff spinboxes + sets
                  checklist with per-conditional-set effect share
                  spinboxes)
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
sliders, Have at Least minimums, per-set effect shares, avg buff
fields, level stepper, element override) into `optimizer.optimize()` via the unified
settings dict built by `_build_optimizer_settings`. The optimizer
implements the damage / shield-heal blended scoring from
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
from ui.utils.all_none_row import make_all_none_row
from ui.utils.button_width import BUTTON_W_SMALL
from ui.utils.checkbox import make_checkbox
from ui.utils.label_width import LABEL_REQUEST_INSET
from ui.utils.tooltip import Tooltip
from ui.utils.combobox_nav import (
    combobox_letter_jump, combobox_arrow_nav, bind_popdown_seek,
)
from game_data import (
    SETS, FOUR_PIECE_SETS, TWO_PIECE_SETS,
    SLOT_MAIN_STATS, RARITY_COLORS, ATTRIBUTE_COLORS,
    CHARACTERS, CHARACTERS_BY_NAME,
    get_character_by_name
)
# Display-name overrides for user-facing labels. Internal stat keys
# ("CRate", "CDmg", "Flat ATK", etc.) remain unchanged; this map is
# consulted whenever a stat name is shown to the user.
from game_data.constants import DISPLAY_NAMES
# Pure GS / Potential helpers — used by _populate_detail to compute the
# Selected Build tree's GS and Potential columns under the character's
# ASSIGNED scoring preset (which may differ from the globally-active
# preset on the fragments' cached .gear_score / .potential_low/high).
from models.memory_fragment import (
    compute_fragment_gs, compute_fragment_potential, bounds_for_fragment,
)


# Multi-line explanation shown below the toolbar. The label's wraplength is
# re-set on <Configure> so the text reflows when the user resizes the
# window.
#
# OPTIMIZER_HELP_WRAPLENGTH is the width it settles at in the default
# window, and should be used as the label's INITIAL wraplength so the very
# first layout already matches the settled one. Getting that wrong is
# expensive: if the initial wrap is narrower, the text renders as 4 lines,
# the toolbar is taller, every panel below it is laid out too low, and the
# reveal settle loop needs extra full update() passes to correct it -- about
# 0.7s each, measured, on top of every launch.
OPTIMIZER_HELP_WRAPLENGTH = 930

OPTIMIZER_HELP_TEXT = (
    "The Optimizer finds the six Memory Fragments (MFs) that give the selected "
    "combatant the most damage, healing, and shielding.\nTell Important Settings "
    "how the combatant fights, pick Sets, exclude anyone you don't want stripped, "
    "then press Start. Click a result to see its pieces and stat changes.\nA wide "
    "search is slow: raise 'Ignore MFs below level', choose Sets, lower Max Flex "
    "Slots, exclude characters' MFs. Doesn't account for unleveled MFs' potential."
)


# Stat keys used by the "Have at least" panel. Ordered as displayed:
# column 1 = (ATK, DEF, HP, Ego), column 2 = (CRate, CDmg, Extra DMG%, DoT%).
HAL_COLUMN_1 = ["ATK", "DEF", "HP", "Ego"]
HAL_COLUMN_2 = ["CRate", "CDmg", "Extra DMG%", "DoT%"]
HAL_STATS_WITH_PCT = {"CRate", "CDmg", "Extra DMG%", "DoT%"}  # show "%" suffix

# Of those four, the only one a value above 100 is meaningless for.
# CDmg, Extra DMG% and DoT% all run well past it in game, so they keep
# the wide range the spinbox is built with.
HAL_STATS_CAPPED_AT_100 = {"CRate"}
HAL_ALL_STATS = HAL_COLUMN_1 + HAL_COLUMN_2


# Label column width shared by the Extra / Agony / Fracture sliders, in
# characters: the longest label plus a character of slack. Sizing all
# three alike is what leaves their tracks left-aligned.
# The three damage rows' names, and the widest value their readouts
# reach. Both columns are pinned to the MEASURED width of these, so the
# gaps either side of a slider are the rule's and nothing else.
DMG_TYPE_LABELS = ("Extra", "Agony", "Fracture")
DMG_READOUT_WIDEST = "100%"

# What the name column adds to the longest name's INK. A grid minsize is
# a FLOOR, not a width -- the column still grows to fit its widest cell,
# and a Label asks for its ink plus the style's own inset. Pinned to the
# ink alone, the longest name outgrew the floor and set its own column
# while the shorter rows kept the floor, so the sliders stopped lining
# up. This clears the widest REQUEST and leaves the rule's gap after it.
DMG_LABEL_COL_SLACK = 5

# The ATK/DEF row's own floor. Both are calibrated on screen rather than
# derived, because a string's rendered ink and what `font.measure`
# reports for it differ by about a pixel, and not by the same pixel for
# every string -- so the two rows do not necessarily agree.
AD_LABEL_COL_SLACK = 5

# A readout column pinned to the ink ALONE is outgrown the moment the
# value reaches its widest, and the column steals those pixels from the
# slider beside it: the sliders visibly shorten going from 99% to 100%.
# Clearing the REQUEST is what holds them still -- see label_width, and
# `_dmg_readout_col_px` below, which adds it.


def _name_col_px(names, slack=None):
    """Pixel width for a column holding any of `names`, measured.

    Called at build time rather than computed once at import: the font
    is not resolvable until a Tk root exists.
    """
    import tkinter.font as tkfont
    f = tkfont.nametofont("TkDefaultFont")
    return (max(f.measure(name) for name in names)
            + (DMG_LABEL_COL_SLACK if slack is None else slack))


def _dmg_label_col_px():
    """Pixel width of the damage rows' name column."""
    return _name_col_px(DMG_TYPE_LABELS)


def _dmg_readout_col_px():
    """Pixel width of a percent readout column.

    The widest value's ink PLUS what a Label asks for around it, so the
    column never has to grow when the value reaches 100% -- see
    LABEL_REQUEST_INSET.
    """
    import tkinter.font as tkfont
    return (tkfont.nametofont("TkDefaultFont").measure(DMG_READOUT_WIDEST)
            + LABEL_REQUEST_INSET)


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






class OptimizerTab(BaseTab):
    """Optimizer tab. See module docstring for layout overview."""

    # ------------------------------------------------------------ init / state

    def __init__(self, parent: tk.Widget, context: AppContext):
        super().__init__(parent, context)
        self._init_state()
        self.setup_ui()
        # Layout-settling guard: when this tab is first shown, Tk runs 2-3
        # layout passes in view of the user -- col 1's natural width starts
        # wider than its final settled value (a ttk.Scale / Spinbox whose
        # theme metrics resolve after the first pass), so panels visibly
        # shift. Binding update_idletasks() to <Map> drains all pending
        # geometry-idle events SYNCHRONOUSLY before Tk paints, so the user
        # only sees the settled state. _layout_settled makes it one-shot.
        self._layout_settled = False
        self.frame.bind("<Map>", self._settle_layout_once, add="+")
        # The Preset label above Stats Comparison can go stale if the user
        # reassigns a character's preset from the Combatants tab while this
        # tab is inactive. Refresh on tab-switch via <<NotebookTabChanged>>;
        # the handler self-gates on "is this tab the active one?".
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
        # The preset_row in the toolbar has pack_propagate(False) so it
        # doesn't grow with its label content; explicitly size it to the
        # top_row's natural width so the preset label clips at the right
        # edge of the left toolbar cluster instead of pushing help_label
        # right when the preset name is long. Done in the settle pass
        # because top_row's reqwidth is only reliable once Tk has computed
        # the children's natural sizes.
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
        # dot_pct_var drives the AGONY slider -- the setting key predates
        # the game naming its DoT types. See docs/game_formulas.md §3.4.
        self.dot_pct_var = tk.IntVar(value=0)
        self.fracture_pct_var = tk.IntVar(value=0)
        self.atk_def_split_var = tk.IntVar(value=0)
        self.shielding_healing_weight_var = tk.IntVar(value=0)
        self.force_main_vars = {key: tk.BooleanVar(value=False)
                                 for key, _label, _slot, _stat in FORCE_MAIN_DEFS}
        self.element_override_var = tk.StringVar(value="")

        # --- Per-character UI vars (Have at Least) ---
        # The %-bounded stats (col 2) accept one decimal place, so they
        # get DoubleVars; the raw-integer stats (col 1) stay IntVars.
        self.have_at_least_vars = {
            stat: (tk.DoubleVar(value=0.0) if stat in HAL_STATS_WITH_PCT
                   else tk.IntVar(value=0))
            for stat in HAL_ALL_STATS
        }

        # --- Per-character UI vars (Set Configuration) ---
        self.set_selected_vars: dict = {}  # set_id (int) -> BooleanVar
        # Per-CONDITIONAL-set effect share spinboxes (set_id -> IntVar
        # 0-100; unconditional sets get no spinbox -- their bonuses
        # always apply).
        self.set_effect_pct_vars: dict = {}
        self.max_flex_slots_var = tk.IntVar(value=6)
        self.avg_card_dmg_pct_var = tk.IntVar(value=100)
        self.avg_mult_buff_pct_var = tk.IntVar(value=0)
        self.avg_add_buff_pct_var = tk.IntVar(value=0)

        # --- Per-character UI vars (toolbar level stepper) ---
        self.optimize_for_level_var = tk.IntVar(value=62)

        # --- Global UI vars (Excluded gear) ---
        # Keyed by hero name (display string); the save callback converts
        # to res_ids at the boundary.
        self.exclude_hero_vars: dict = {}
        # hero name -> its Checkbutton. Created once per combatant and
        # repositioned on re-flow, never recreated -- see
        # _exclude_checkbutton / _reflow_exclude_heroes.
        self._exclude_widgets: dict = {}

        # --- Global UI vars (optimizer-wide) ---
        # Minimum MF level for optimizer candidacy: a single GLOBAL
        # setting (not per-character), persisted in settings.json via
        # SettingsManager. Defaults to 4: on a 607-fragment inventory that
        # cuts the search space ~10x (21.3s -> 2.4s measured) while keeping
        # every fragment close to finished. 0 disables the filter.
        self.min_gear_level_var = tk.IntVar(value=4)
        sm = getattr(self.context, "settings_manager", None)
        if sm is not None:
            try:
                self.min_gear_level_var.set(
                    int(sm.get("optimizer_min_gear_level", 4)))
            except (TypeError, ValueError):
                pass
        self.min_gear_level_var.trace_add(
            "write", lambda *_: self._save_min_gear_level())
        # Off-element Slot V candidacy filter: drop Slot V MFs whose
        # main stat is an element DMG% that doesn't match the selected
        # combatant's element. ATK%/HP% Slot V mains always pass;
        # unknown characters without an Element override are never
        # filtered. Also GLOBAL, persisted in settings.json. Default ON.
        self.ignore_offelement_var = tk.BooleanVar(value=True)
        if sm is not None:
            self.ignore_offelement_var.set(
                bool(sm.get("optimizer_ignore_offelement", True)))
        self.ignore_offelement_var.trace_add(
            "write", lambda *_: self._save_ignore_offelement())

        # --- Optimization runtime state ---
        self.optimization_results: list = []
        self.result_queue = queue.Queue()
        # cancel_flag is REPLACED with a fresh list on every Start (the
        # old one is set True first) -- see run_optimization for why a
        # single shared flag was racy. _run_id tags queue messages so
        # check_queue can drop stragglers from superseded runs.
        self.cancel_flag = [False]
        self._run_id = 0
        self._optimizing = False
        self.result_sort_col = "score"
        self.result_sort_reverse = False

        # --- Widget references (filled by setup_ui) ---
        self.hero_combo = None
        self.start_button = None
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
        self.preset_label = None
        # One hover-tooltip instance for the whole tab: only one tooltip
        # can be visible at a time, so a second instance would buy
        # nothing and could leave two on screen at once.
        self._tooltip = Tooltip(self.colors)

    # Convenience accessor -- avoids repeating self.context.optimizer_settings_manager
    @property
    def opt_settings(self):
        return self.context.optimizer_settings_manager

    # ----------------------------------------------------------- UI top-level

    def setup_ui(self):
        # Everything is built inside an UNMAPPED container that is packed as
        # the very last step. Tk maps and lays out widgets incrementally, and
        # anything already on screen repaints between those passes -- so
        # building straight into a mapped parent lets the user watch the tab
        # assemble itself: panels appear half-populated, then jump as later
        # widgets change the geometry. Children of an unmapped parent are
        # never drawn, so the whole construction cascade is invisible and the
        # tab appears once, already settled.
        content = ttk.Frame(self.frame)

        # ---- Toolbar ----
        toolbar = ttk.Frame(content)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, label ↕
        # pady top is 0, not matching the sides: content already
        # contributes its own, and this tab leads with a plain 9pt Label,
        # which renders its text a little in from its own top edge --
        # where a LabelFrame title (what the Memory Fragments tab leads
        # with) renders flush. Matching frame padding would put this tab's
        # text below every other's. See docs/ui_spacing.md "The rules".
        toolbar.pack(fill=tk.X, padx=2, pady=(0, 2))

        # Stack the Combatant label and dropdown vertically. The toolbar's
        # left cluster (Combatant + LVL + Start + Stop) is wrapped in a
        # vertical left_cluster -> top_row container so a preset_row can
        # sit below it, clipped to top_row's width. Without the clipping,
        # long preset names make combatant_frame grow and push every other
        # toolbar control right.
        left_cluster = ttk.Frame(toolbar)
        left_cluster.pack(side=tk.LEFT, anchor=tk.N)
        self._toolbar_top_row = ttk.Frame(left_cluster)
        self._toolbar_top_row.pack(side=tk.TOP, fill=tk.X, anchor=tk.W)
        combatant_frame = ttk.Frame(self._toolbar_top_row)
        # spacing: control group ↔ control group -- dropdown, label ↔
        combatant_frame.pack(side=tk.LEFT, padx=(0, 5), anchor=tk.N)
        # spacing: title above, element below -- label, dropdown ↕
        # The negative LEADING padding pulls the caption's glyphs left to
        # sit over the Combobox's text below it, which carries an inset of
        # its own that a Label does not. pack's padx can't go negative
        # ("must be positive screen distance"), so the correction has to
        # live on the widget. See docs/ui_spacing.md "The rules".
        ttk.Label(combatant_frame, text="Combatant:",
                  padding=(-2, 0, 0, 0)).pack(anchor=tk.W)
        # Width sized for the longest character name ("Heidemarie" = 10
        # chars) plus ~2 chars for the dropdown popup's scrollbar.
        self.hero_combo = ttk.Combobox(
            combatant_frame, textvariable=self.selected_character,
            width=12, state="readonly",
        )
        self.hero_combo.pack(anchor=tk.W)
        self.hero_combo.bind("<<ComboboxSelected>>", self.on_hero_select)
        # Letter-key navigation: type a letter to jump to the next matching
        # combatant. KeyRelease + add="+" so readonly Combobox's internal
        # handler doesn't pre-empt us; some Tk versions don't fire KeyPress
        # to user bindings on readonly state.
        self.hero_combo.bind(
            "<KeyRelease>", lambda e: combobox_letter_jump(e, self.hero_combo),
            add="+",
        )
        # Arrow keys step through the list in place instead of opening the
        # dropdown popup (Tk's default on readonly Combobox opens it).
        self.hero_combo.bind(
            "<Down>", lambda e: combobox_arrow_nav(e, self.hero_combo, +1)
        )
        self.hero_combo.bind(
            "<Up>", lambda e: combobox_arrow_nav(e, self.hero_combo, -1)
        )
        # Type-ahead seek inside the OPEN dropdown list.
        bind_popdown_seek(self.hero_combo)

        # Every subsequent toolbar widget uses anchor=tk.N so the row is
        # top-aligned (pack would otherwise vertically center the 1-line
        # widgets against the help label's 3 lines). LVL label + spinner
        # stack vertically, mirroring the Combatant stacking.
        level_frame = ttk.Frame(self._toolbar_top_row)
        # spacing: control group ↔ control group -- dropdown, label ↔
        level_frame.pack(side=tk.LEFT, padx=(11, 0), anchor=tk.N)
        # spacing: title above, element below -- label, spinbox ↕
        ttk.Label(level_frame, text="Optimize for LVL:",
                  padding=(-2, 0, 0, 0)).pack(anchor=tk.W)
        level_spin = tk.Spinbox(
            level_frame, from_=60, to=62, increment=1, width=3,
            textvariable=self.optimize_for_level_var,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            buttonbackground=self.colors["bg_lighter"],
            insertbackground=self.colors["fg"],
        )
        level_spin.pack(anchor=tk.W)
        self._clamp_on_commit(level_spin, self.optimize_for_level_var)
        level_spin.bind("<MouseWheel>", lambda e: self._spinbox_wheel(e, level_spin))
        self.optimize_for_level_var.trace_add(
            "write", lambda *_: self._save_int_safe("optimize_for_level",
                                                       self.optimize_for_level_var))

        self.start_button = ttk.Button(self._toolbar_top_row, text="Start",
                                       width=BUTTON_W_SMALL,
                                       command=self.run_optimization)
        # spacing: button -> button -- button, button ↔
        # spacing: control group ↔ control group -- spinbox, button ↔
        # spacing: tab list -> first element -- tab, button ↕
        # The pady is the correction that puts the buttons' painted top
        # edge level with the other elements in this row. A ttk.Button's
        # box edge IS its border, where a Label's box starts above its
        # glyphs, so equal pady would render them unequal.
        self.start_button.pack(side=tk.LEFT, padx=(13, 2), pady=(5, 0), anchor=tk.N)
        ttk.Button(self._toolbar_top_row, text="Stop",
                   width=BUTTON_W_SMALL,
                   command=self.cancel_optimization).pack(
                       side=tk.LEFT, padx=2, pady=(5, 0), anchor=tk.N)

        # Preset row below the top row. pack_propagate(False) so the row
        # doesn't grow with its label; width is synced to top_row's natural
        # reqwidth in _settle_layout_once so the label clips at the
        # cluster's right edge. Height fits one line of the body font.
        # 18, not 17: a Segoe UI 9 line box is 15px and the label's own
        # style inset takes the rest, so 17 clipped the descenders off
        # `Preset:` itself. The row is pinned rather than propagating,
        # so nothing else reports the clip.
        self._toolbar_preset_row = ttk.Frame(left_cluster, height=18)
        self._toolbar_preset_row.pack_propagate(False)
        self._toolbar_preset_row.pack(side=tk.TOP, fill=tk.X, anchor=tk.W)
        self.preset_label = ttk.Label(
            self._toolbar_preset_row, text="Preset: (default)",
            foreground=self.colors["fg_dim"],
            font=("Segoe UI", 9),
            # spacing: border edge -> first non-button element -- frame, label ↔
            # The negative LEADING padding trims the label's own internal
            # inset so its glyphs line up with the content's left edge.
            # pack's padx can't go negative, and taking one more would
            # clip the leading glyph.
            padding=(-2, 0, 0, 0),
        )
        self.preset_label.pack(side=tk.LEFT, anchor=tk.W)

        # ---- Help text, inline with the toolbar between Stop and the
        # status label. fill=X + expand=True lets it absorb available
        # horizontal space; the Configure binding reflows wraplength on
        # resize so the text wraps without pushing the status label
        # off-screen.
        help_label = ttk.Label(
            toolbar, text=OPTIMIZER_HELP_TEXT,
            justify=tk.LEFT, foreground=self.colors["fg_dim"],
            wraplength=OPTIMIZER_HELP_WRAPLENGTH,
        )
        # spacing: control group ↔ control group -- button, label ↔
        help_label.pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True, anchor=tk.N)

        def _rewrap(event, lbl=help_label):
            # Skip no-op reconfigures. Setting wraplength changes the label's
            # REQUESTED width, so a handler that writes unconditionally can
            # bounce the toolbar's layout for an extra pass or two -- and
            # every one of those passes is a full relayout of the tab.
            new = max(200, event.width - 10)
            try:
                if int(str(lbl.cget("wraplength"))) == new:
                    return
            except (ValueError, tk.TclError):
                pass
            lbl.config(wraplength=new)

        help_label.bind("<Configure>", _rewrap)

        # Status cluster at the toolbar's right edge: the "Loaded N
        # fragments" status on top, the two global filter rows directly
        # under it ("Ignore MFs below level" spinbox, "Ignore
        # off-Element MFs" checkbox).
        #
        # The cluster's height is CONSTRAINED, not free: the toolbar's
        # height is set by its tallest child -- the left cluster
        # (Combatant row + preset row) -- and three stacked rows on the
        # right have only a few pixels of headroom before they overtake
        # it, growing the toolbar and shifting every frame below it down.
        # So this font is a lever on the toolbar's height, not a
        # cosmetic choice; raising it needs the fit re-checked on screen.
        # It is the body size now, the same as TkDefaultFont, so the name
        # is historical -- there is no smaller font left in the app.
        small_font = ("Segoe UI", 9)
        status_cluster = ttk.Frame(toolbar)
        # spacing: control group ↔ control group -- label, label ↔
        # NOT TRACKED: packed RIGHT, so the distance to the help text on
        # its left is whatever the toolbar has spare -- 125px at the
        # window size it was read at. The rule's 16 is a minimum, and the
        # audit compares against a number. Its OTHER side is a real
        # distance and is tracked as `status cluster -> window edge`.
        status_cluster.pack(side=tk.RIGHT, padx=(10, 0), anchor=tk.N)
        # spacing: border edge -> first non-button element -- label, frame ↔
        # The negative TRAILING padding pulls the glyphs right, toward
        # the rule: a Label's box stops short of its own text where the
        # spinbox below it ends at its border. pack's padx cannot go
        # negative, so the correction lives on the widget. The target
        # moved to 5 after this was set, so the audit should now read it
        # a pixel wide.
        self.status_label = ttk.Label(
            status_cluster, text="No data loaded",
            foreground=self.colors["fg_dim"],
            justify=tk.RIGHT, font=small_font,
            padding=(0, 0, -2, 0),
        )
        self.status_label.pack(side=tk.TOP, anchor=tk.E)
        minlvl_row = ttk.Frame(status_cluster)
        # spacing: unique -- between mixed element rows (label -> spinbox) -- label, spinbox ↕
        # Target 5px, measured painted-edge to painted-edge. The rows are
        # different heights whatever this says -- a text row, a spinbox
        # row and a checkbox row seat their content at different insets --
        # so this pair and the pair below carry separate numbers.
        #
        # UNIQUE because the cluster has almost no vertical room, not
        # because no rule could describe it. Given the space this would
        # be 12 and governed by `config panel row ↕ row`, widened to
        # cover unrelated bordering rows. The constraint is what makes
        # it its own case.
        minlvl_row.pack(side=tk.TOP, anchor=tk.E, pady=(0, 0))
        # spacing: label ↔ its element -- label, spinbox ↔
        ttk.Label(minlvl_row, text="Ignore MFs below level:",
                  font=small_font).pack(side=tk.LEFT, padx=(0, 1))
        minlvl_spin = tk.Spinbox(
            minlvl_row, from_=0, to=5, increment=1, width=2,
            textvariable=self.min_gear_level_var, font=small_font,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            buttonbackground=self.colors["bg_lighter"],
            insertbackground=self.colors["fg"],
        )
        minlvl_spin.pack(side=tk.LEFT)
        self._clamp_on_commit(minlvl_spin, self.min_gear_level_var)
        minlvl_spin.bind("<MouseWheel>",
                         lambda e, sp=minlvl_spin: self._spinbox_wheel(e, sp))
        offelem_row = ttk.Frame(status_cluster)
        # spacing: unique -- between mixed element rows (spinbox -> checkbox) -- spinbox, checkbox ↕
        # Target 3px. Genuinely unique: there is not a second
        # spinbox-row-over-checkbox-row anywhere in the app. Were there,
        # the pair would want `spinbox row -> spinbox row` and
        # `checkbox/slider ↕ rows` united into one rule -- and the audit
        # taught to measure between the rows' LABELS rather than their
        # controls, which seat at different heights. The two rules being
        # separate today is what leaves this a one-off.
        # Shifted 2px left of the row above's right edge, so the two
        # rows START level. The checkbox already sits further from the
        # right edge than the rule asks; lining the row up is what that
        # buys, rather than a compromise between the two.
        offelem_row.pack(side=tk.TOP, anchor=tk.E, padx=(0, 2), pady=(0, 0))
        # spacing: label ↔ its element -- label, checkbox ↔
        offelem_label = ttk.Label(offelem_row, text="Ignore off-Element MFs",
                                  font=small_font)
        offelem_label.pack(side=tk.LEFT, padx=(0, 1))
        # spacing: exception -- border edge -> first non-button element -- checkbox, frame ↔
        # Sits 13px from the right edge where the rule asks for 5, and
        # where the status text above reads 8 and the spinbox 6. Keeping
        # it near-centred under the spinbox rather than flush right looks
        # and clicks better, and the click target is the reason it wins.
        offelem_cb = make_checkbox(
            offelem_row, self.colors, variable=self.ignore_offelement_var,
            font=small_font, compact=True,
        )
        offelem_cb.pack(side=tk.LEFT, padx=(0, 1))
        # What the filter does NOT touch is the part worth saying: the
        # name reads as though any off-Element stat is dropped. Bound to
        # both children rather than the row, the way the Set
        # Configuration rows are -- Tk fires Leave on a container as the
        # pointer crosses onto a child.
        for _w in (offelem_label, offelem_cb):
            self._tooltip.bind(
                _w,
                "Drops Slot V MFs whose Element is not the same as the "
                "character's. ATK% and HP% main stats always pass.\n"
                "No effect on a Combatant whose Element is unknown."
            )

        # ---- Body grid ----
        # 3 columns: Stats Comp, Config, Results / Exclude.
        # Columns 0 and 1 are weight=0, so each takes exactly its content's
        # requested width and never changes with the window. Column 2 is
        # the only weighted column, so ALL slack -- and every pixel gained
        # or lost on a resize -- goes to Exclude / Results. Sharing
        # proportional weights across all three instead couples them: every
        # column's width drifts with the window, and a width change in one
        # moves the other two.
        # 2 rows: top row expands, bottom row natural height.
        # Layout (visual):
        #   Row 0: [Stats Comp] [Config         ] [Exclude over Results]
        #   Row 1: [Selected Build (cols 0-1)  ] [Results (continued)  ]
        # Selected Build spans cols 0-1 so its right edge aligns with the
        # Config column's right edge.
        body = ttk.Frame(content)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(0, weight=0)
        # Selected Build spans columns 0-1, and Tk splits a spanning
        # widget's excess width EVENLY across the columns it covers unless
        # their weights say otherwise. At weight 0 the excess went to
        # column 0, widening Stats Comparison until its tree drifted past
        # the window edge; weight 1 sends all of it to column 1 instead.
        # Column 2's 1000 against column 1's 1 then keeps resize slack on
        # column 2 -- column 1's share rounds to zero even across a 400px
        # resize.
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=1000)
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)

        # --- Row 0 col 0: Stats Comparison. sticky="new" so the frame is
        # only as tall as its content. ---
        left_frame = ttk.LabelFrame(body, text="Stats Comparison", padding=0,
                                    style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        left_frame.grid(row=0, column=0, sticky="new", padx=2, pady=2)
        self._build_stats_tree(left_frame)

        # --- Row 0 col 1: Configuration (middle pane) ---
        self.middle_frame = ttk.Frame(body)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        self.middle_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self._build_config(self.middle_frame)

        # --- Col 2 (rowspan 2): Exclude MFs (top) + Results (below).
        # Results expands to fill whatever vertical space remains below
        # Exclude. ---
        self._col2_container = ttk.Frame(body)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        self._col2_container.grid(row=0, column=2, rowspan=2, sticky="nsew",
                                  padx=2, pady=2)
        # spacing: border edge -> first non-button element -- panel, checkbox ↔↕
        exclude_frame = ttk.LabelFrame(
            self._col2_container, text="Exclude Combatant's MFs", padding=(1, 3, 1, 3)
        )
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # The whole gap: the Results panel below packs with no pady of
        # its own, so this trailing component is the only lever on the
        # distance from this panel's border to the Results title.
        exclude_frame.pack(fill=tk.X, pady=(0, 5))
        self._build_exclude_gear(exclude_frame)
        # The Results panel's title is a labelwidget rather than plain
        # `text=` so the run status can sit beside it on the title line
        # instead of taking a row above the tree. A labelwidget bypasses
        # the Borderless.TLabelframe.Label style, so the accent colour is
        # applied here directly.
        results_header = ttk.Frame(self._col2_container)
        ttk.Label(results_header, text="Results",
                  foreground=self.colors["accent"]).pack(side=tk.LEFT)
        self.progress_label = ttk.Label(
            results_header, text="Ready to optimize",
            foreground=self.colors["fg_dim"]
        )
        # spacing: header subtext -- label, label ↔
        # The pad is the whole lever. Seating the status on the title's
        # line needs nothing, unlike every other site under this rule:
        # both are plain Labels in one font with no padding and the same
        # anchor, so they share a line box and align by construction.
        # Give either one a font or a padding of its own and that stops
        # being true.
        self.progress_label.pack(side=tk.LEFT, padx=(10, 0))
        # spacing: title above, element below -- title, tree ↕
        # padding is 0 all round: the tree inside sits flush with the
        # frame's bottom edge, matching Selected Build beside it. The
        # title -> tree gap lives on the tree's own pack pady, because
        # padding top on this style did not move it.
        right_frame = ttk.LabelFrame(self._col2_container, labelwidget=results_header,
                                     padding=(0, 0, 0, 0),
                                     style="Tight.Borderless.TLabelframe")
        right_frame.pack(fill=tk.BOTH, expand=True)
        self._build_results(right_frame)

        # --- Row 1 cols 0-1: Selected Build (bottom-aligned via
        # sticky="sew"). ---
        detail_frame = ttk.LabelFrame(body, text="Selected Build", padding=(0, 0, 0, 0),
                                      style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        detail_frame.grid(row=1, column=0, columnspan=2, sticky="sew",
                          padx=2, pady=2)
        self._build_detail_tree(detail_frame)

        # Map the finished tree in one go. Deliberately NO update_idletasks()
        # here: pumping Tk's idle queue during construction makes the root
        # window appear immediately, and startup then blocks for a second or
        # two in auto_load() -- reading the snapshot and refreshing every
        # other tab -- which would leave a half-drawn window on screen for
        # that whole time. Packing without pumping queues the layout instead,
        # so the first paint happens when mainloop starts, after the load.
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        content.pack(fill=tk.BOTH, expand=True, padx=2, pady=(1, 2))

        # No data on startup -- disable interactive controls.
        self._update_enabled_state()

    # ---------------------------------------------------- UI: stats tree (left)

    def _build_stats_tree(self, parent):
        self.stats_tree = ttk.Treeview(
            parent, columns=("stat", "current", "new", "diff"),
            show="headings", height=19,
        )
        self.stats_tree.column("#0", width=0, stretch=False)
        # Headings take their columns' anchors, set just below: `stat` is
        # left, the three number columns are right.
        self.stats_tree.heading("stat", text="Stat", anchor=tk.W)
        self.stats_tree.heading("current", text="Now", anchor=tk.E)
        self.stats_tree.heading("new", text="New", anchor=tk.E)
        self.stats_tree.heading("diff", text="+/-", anchor=tk.E)
        # Column widths are trimmed to the minimum that fits their content
        # ("Element%" is the widest row label; the three value columns fit
        # about five characters each). What that saves goes to the middle
        # config column, where the widest set name's spinbox would
        # otherwise clip. stretch=False keeps the Treeview's natural width
        # equal to the column-width sum, so -- with the parent grid
        # column's weight at 0 -- the whole frame hugs it and shrinks by
        # the same amount.
        #
        # Tree height = exactly the number of rows shown (Totals header +
        # 9 stats + blank + 8 Pot7 rows = 19) so the frame is only as tall
        # as its content; _populate_stats_compare re-syncs the height to
        # the live row count whenever the row set changes.
        self.stats_tree.column("stat", width=68, stretch=False)
        self.stats_tree.column("current", width=35, anchor=tk.E, stretch=False)
        self.stats_tree.column("new", width=35, anchor=tk.E, stretch=False)
        self.stats_tree.column("diff", width=35, anchor=tk.E, stretch=False)
        self.stats_tree.pack(fill=tk.Y, expand=True)
        # Right-click opens the "Show all stat contributions" menu.
        self.stats_tree.bind("<Button-3>", self._show_stats_context_menu)

    # ------------------------------------------------- UI: middle pane builder

    def _build_config(self, parent):
        """Middle pane: element override, two-column settings, set config,
        exclude gear."""
        # Element override (conditional visibility -- toggled by
        # _update_element_override_visibility based on selected character).
        # spacing: border edge -> first non-button element -- panel, label ↔↕
        self.element_override_frame = ttk.LabelFrame(
            parent, text="Element override (Unknown character)", padding=4
        )
        # spacing: label ↔ its element -- label, dropdown ↔
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
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # The whole gap: Set Configuration below leads with 0, so this
        # trailing component alone sets the distance from the Important
        # Settings / Have at Least borders to that panel's title.
        top_row.pack(fill=tk.X, pady=(0, 7))

        # spacing: border edge -> first non-button element -- panel, label ↔↕
        important_frame = ttk.LabelFrame(top_row, text="Important Settings",
                                         padding=(3, 0, 3, 2))
        # spacing: content frame -> content frame -- frame, frame ↔
        important_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2))
        self._build_important_settings(important_frame)

        # spacing: border edge -> first non-button element -- panel, label ↔↕
        have_frame = ttk.LabelFrame(
            top_row, text="Have at least this much of a stat", padding=(3, 4, 5, 5)
        )
        # HAL frame doesn't expand -- it sizes to its natural width so the
        # panel hugs its spinboxes; important_frame has expand=True so it
        # absorbs the freed horizontal space. No right pad, so the frame's
        # right edge aligns with Set Configuration's below.
        #
        # ipadx widens HAL on BOTH sides, and is what keeps its overall
        # footprint roughly steady as the col-2 spinboxes' character width
        # changes -- it is tuned against them, not set independently.
        # spacing: content frame -> content frame -- frame, frame ↔
        have_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False,
                        padx=(2, 0), ipadx=6)
        self._build_have_at_least(have_frame)

        # Set Configuration
        # spacing: border edge -> first non-button element -- panel, label ↔↕
        set_frame = ttk.LabelFrame(parent, text="Set Configuration", padding=(2, 5, 5, 5))
        # spacing: content frame -> content frame -- frame, frame ↕
        set_frame.pack(fill=tk.X, pady=(0, 5))
        self._set_frame_ref = set_frame
        self._build_set_config(set_frame)

        # The "Exclude Combatant's MFs" panel lives in col 2 above the
        # Results frame -- see setup_ui. _build_exclude_gear is called
        # from there, not here.

    # ----------------------------------------------- UI: Important Settings

    def _build_important_settings(self, parent):
        # Block 1: Extra% + DoT% sliders
        # spacing: border edge -> first non-button element -- panel, label ↔
        # spacing: explanation text -> the controls it explains -- label, slider ↕
        # No leading correction, unlike its siblings' absence of one: the
        # FRAME carries this panel's inset now, because an ordinary 9pt
        # Label is what most of the content is. This label used to hold a
        # -1 and the frame a pixel more, which put this one line on
        # target and left every other label a pixel out.
        ttk.Label(
            parent, text="What percent of damage is Extra, Agony, or Fracture/Scorched DMG?",
            font=("Segoe UI", 9), wraplength=376,
            padding=(0, 0, 0, 0),
        ).pack(anchor=tk.W, pady=(0, 1))

        # Each damage type gets a FULL row. Side by side, each slider's
        # rendered track fell below ~100px at common window widths (the
        # length=120 request only helps when pack can honor it), so
        # dragging skipped roughly every 8th integer. A full-width row
        # gives each track ample travel for every value. A shared
        # label column, pinned to the longest name's measured width,
        # keeps the tracks left-aligned with each other.
        ex_row = ttk.Frame(parent)
        # spacing: checkbox/slider ↕ checkbox/slider rows -- slider, slider ↕
        # Two slider rows with nothing between them are an ordinary
        # non-tall pair. The larger `config panel row ↕ row` distance
        # belongs to the gaps that cross a CAPTION, which is what ends
        # each block -- see frac_row below.
        ex_row.pack(fill=tk.X, pady=(0, 2))
        self._labeled_slider(
            ex_row, "Extra", self.extra_pct_var,
            on_change=lambda v: self._save_int("extra_pct", v),
            label_col_px=_dmg_label_col_px(),
        )
        dot_row = ttk.Frame(parent)
        # spacing: checkbox/slider ↕ checkbox/slider rows -- slider, slider ↕
        dot_row.pack(fill=tk.X, pady=(0, 2))
        self._labeled_slider(
            dot_row, "Agony", self.dot_pct_var,
            on_change=lambda v: self._save_int("dot_pct", v),
            label_col_px=_dmg_label_col_px(),
        )
        # One slider covers Fracture AND Scorched: the two are
        # mechanically identical, so a share each would score the same.
        # The caption above names both. See docs/game_formulas.md §3.4.
        frac_row = ttk.Frame(parent)
        # spacing: config panel row ↕ row -- slider, label ↕
        # (the larger trailing value ends the block, where the rows above
        # only separate rows of the same block)
        frac_row.pack(fill=tk.X, pady=(0, 4))
        self._labeled_slider(
            frac_row, "Fracture", self.fracture_pct_var,
            on_change=lambda v: self._save_int("fracture_pct", v),
            label_col_px=_dmg_label_col_px(),
        )

        # Block 2: ATK <-> DEF slider
        # spacing: explanation text -> the controls it explains -- label, slider ↕
        ttk.Label(
            parent, text="What percent of damage scales off DEF?",
            font=("Segoe UI", 9), wraplength=350,
        ).pack(anchor=tk.W, pady=(0, 1))

        ad_row = ttk.Frame(parent)
        # spacing: config panel row ↕ row -- slider, label ↕
        ad_row.pack(fill=tk.X, pady=(0, 4))
        # Four pinned columns, the same construction as the damage rows
        # above: every `width=` in CHARACTERS left slack that landed in
        # one rule-governed gap or the other depending on the anchor, and
        # no character count sits on the gap. See `_dmg_label_col_px`.
        ad_row.grid_columnconfigure(1, weight=1)
        ad_row.grid_columnconfigure(
            0, minsize=_name_col_px(("ATK", "DEF"), AD_LABEL_COL_SLACK))
        ad_row.grid_columnconfigure(3, minsize=_dmg_readout_col_px())
        ttk.Label(ad_row, text="ATK", anchor=tk.W).grid(
            row=0, column=0, sticky="w")
        ad_scale = ttk.Scale(
            ad_row, from_=0, to=100, variable=self.atk_def_split_var,
            orient=tk.HORIZONTAL, length=120,
            command=lambda v: self._save_int("atk_def_split", int(float(v))),
        )
        # spacing: label ↔ its element -- label, slider ↔
        # spacing: label ↔ its element -- slider, label ↔
        ad_scale.grid(row=0, column=1, sticky="ew", padx=(0, 0))
        ad_scale.bind(
            "<MouseWheel>",
            lambda e: self._scale_wheel(
                e, self.atk_def_split_var,
                lambda v: self._save_int("atk_def_split", v)),
        )
        # No `width=`: the column is pinned, so the label asks for its
        # own text and has no slack to put on either side of it.
        ttk.Label(ad_row, text="DEF", anchor=tk.W).grid(
            row=0, column=2, sticky="w")
        # anchor=E so the % stays put as digits are added; the column is
        # its widest value's measured width, so there is no slack left of
        # the glyphs for the gap to swallow.
        self.ad_readout_label = ttk.Label(ad_row, text="0%", anchor=tk.E)
        # spacing: label ↔ its element -- label, label ↔
        self.ad_readout_label.grid(row=0, column=3, sticky="e")
        self.atk_def_split_var.trace_add(
            "write",
            lambda *a: self.ad_readout_label.config(
                text=f"{self.atk_def_split_var.get()}%"
            ),
        )

        # Block 3: Shielding/Healing slider
        # spacing: explanation text -> the controls it explains -- label, slider ↕
        ttk.Label(
            parent, text="How much value should be given to Shielding & Healing?",
            font=("Segoe UI", 9), wraplength=350,
        ).pack(anchor=tk.W, pady=(0, 1))

        sh_row = ttk.Frame(parent)
        # spacing: config panel row ↕ row -- slider, checkbox ↕
        sh_row.pack(fill=tk.X, pady=(0, 6))
        sh_scale = ttk.Scale(
            sh_row, from_=0, to=100, variable=self.shielding_healing_weight_var,
            orient=tk.HORIZONTAL, length=120,
            command=lambda v: self._save_int("shielding_healing_weight", int(float(v))),
        )
        # spacing: border edge -> first non-button element -- panel, slider ↔
        # spacing: label ↔ its element -- slider, label ↔
        # The LEADING pad is this slider's own correction. It is the only
        # one in the panel that starts at the frame's edge -- the rest sit
        # after a row label -- and a Scale's trough begins at its box edge
        # where a Label's glyphs start inside theirs, so it needs a pixel
        # the labels do not.
        sh_row.grid_columnconfigure(0, weight=1)
        sh_row.grid_columnconfigure(1, minsize=_dmg_readout_col_px())
        sh_scale.grid(row=0, column=0, sticky="ew", padx=(1, 0))
        sh_scale.bind(
            "<MouseWheel>",
            lambda e: self._scale_wheel(
                e, self.shielding_healing_weight_var,
                lambda v: self._save_int("shielding_healing_weight", v)),
        )
        # anchor=E so the % stays put as digits are added; the column is
        # its widest value's measured width, so there is no slack left of
        # the glyphs for the gap to swallow.
        self.sh_readout_label = ttk.Label(sh_row, text="0%", anchor=tk.E)
        self.sh_readout_label.grid(row=0, column=1, sticky="e")
        self.shielding_healing_weight_var.trace_add(
            "write",
            lambda *a: self.sh_readout_label.config(
                text=f"{self.shielding_healing_weight_var.get()}%"
            ),
        )

        # Block 4: Force-main checkboxes (slot 4 HP, slot 5 HP, slot 6 HP, slot 6 Ego)
        # Label + checkboxes on the same line.
        fm_row = ttk.Frame(parent)
        # spacing: config panel row ↕ row -- slider, checkbox ↕
        fm_row.pack(fill=tk.X, pady=(1, 2))
        # spacing: label ↔ its element -- label, checkbox ↔
        ttk.Label(
            fm_row,
            text="Force HP/Ego on a Slot:",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(0, 0))
        for idx, (key, label, _slot, _stat) in enumerate(FORCE_MAIN_DEFS):
            # spacing: border edge -> first non-button element -- checkbox, panel ↔
            # spacing: element and its label ↔ element and its label -- checkbox, checkbox ↔
            # The last checkbox drops its right pad so the rightmost
            # visible element sits flush with the frame's right padding
            # edge, matching the left edge of the leading label.
            pad_right = 0 if idx == len(FORCE_MAIN_DEFS) - 1 else 4
            make_checkbox(
                fm_row, self.colors, text=label,
                variable=self.force_main_vars[key],
                command=lambda k=key: self._save_force_main(k),
            ).pack(side=tk.LEFT, padx=(0, pad_right))

    def _labeled_slider(self, parent, label, var, on_change=None,
                        label_col_px=None):
        """Build a labeled slider + readout inside `parent`. Packs LEFT.

        on_change(int) is called whenever the slider moves to a new integer
        value. We pass int(float(v)) because ttk.Scale's command receives a
        string-formatted float (e.g. "23.0") even on an integer-bound Scale.

        `label_col_px` is the pixel width of the name column, shared by
        every damage row so their sliders line up.
        """
        wrap = ttk.Frame(parent)
        wrap.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if label_col_px is None:
            label_col_px = _dmg_label_col_px()
        # A grid COLUMN at a measured pixel width, not a `width=` in
        # characters. Tk sizes a character width from the font's average,
        # 6px here, and "Fracture" is 43px of ink -- so seven characters
        # clip it by one and eight overshoot the rule by five. There is no
        # count that lands on the gap, and no padding anywhere to give the
        # missing pixel back. Same treatment as the Gear Score stat grid.
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, minsize=label_col_px)
        ttk.Label(wrap, text=label, anchor=tk.W).grid(
            row=0, column=0, sticky="w")
        # length=120 requests a track at least as long as the 0-100 value
        # range (ttk's default request is 100px, and after the thumb's
        # width the drag travel drops below 100px -- so dragging skips
        # integers). fill=X still lets it grow beyond the request.
        scale = ttk.Scale(
            wrap, from_=0, to=100, variable=var, orient=tk.HORIZONTAL,
            length=120,
            command=lambda v: on_change(int(float(v))) if on_change else None,
        )
        # spacing: label ↔ its element -- label, slider ↔
        # spacing: label ↔ its element -- slider, label ↔
        # Both sides are the rule: the name on the left and the percent
        # readout on the right. Each column is pinned to its own text's
        # width, so what is left here IS the gap.
        scale.grid(row=0, column=1, sticky="ew", padx=(0, 0))
        # Mouse wheel steps exactly +-1, so every integer is reachable
        # even at window sizes where the rendered track is short.
        scale.bind("<MouseWheel>",
                   lambda e, v=var, cb=on_change: self._scale_wheel(e, v, cb))
        # anchor=E so the % stays put as digits are added, and the column
        # pinned to "100%"'s MEASURED width so the box is exactly its
        # widest value -- a `width=` in characters left 2px of slack that
        # the gap to the slider could never spend. The readout's gap is
        # only a distance at 100%; the audit fills it to measure it.
        wrap.grid_columnconfigure(2, minsize=_dmg_readout_col_px())
        readout = ttk.Label(wrap, text="0%", anchor=tk.E)
        readout.grid(row=0, column=2, sticky="e")
        var.trace_add("write",
                      lambda *a, r=readout, v=var: r.config(text=f"{v.get()}%"))

    # -------------------------------------------------- UI: Have at Least

    def _build_have_at_least(self, parent):
        """Two columns of 4 spinboxes each. Col 1 = ATK/DEF/HP/Ego (raw
        integer), Col 2 = CRate/CDmg/Extra DMG%/DoT% (integer + "%").

        The label-to-spinbox gap is natural (label sized to fit its text)
        and the column frames don't expand horizontally, so the
        surrounding LabelFrame sizes to its natural width.
        """
        cols = ttk.Frame(parent)
        # No extra padding on either side -- col 1 text sits at the
        # LabelFrame's own left padding edge (matching the other config
        # frames), and col 2's spinbox is right-aligned at the LabelFrame's
        # right padding edge. cols fills X (not Y) so the extra width HAL
        # gains from Important Settings parks BETWEEN col 1 (LEFT) and
        # col 2 (RIGHT) instead of pushing col 2 off its right alignment.
        # spacing: border edge -> first non-button element -- panel, label ↔
        cols.pack(fill=tk.X, expand=False, padx=(0, 0))
        col1_frame = ttk.Frame(cols)
        col1_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 0))
        col2_frame = ttk.Frame(cols)
        # Col 2 packed RIGHT so it stays at HAL's right padding edge
        # regardless of frame width changes.
        col2_frame.pack(side=tk.RIGHT, fill=tk.Y, expand=False)

        # Give every label in a column the same width (the longest label's
        # char count) so the spinboxes line up vertically within each
        # column. No trailing colon on the stat labels.
        def _col_label_width(stats):
            return max(len(DISPLAY_NAMES.get(s, s)) for s in stats)
        col1_width = _col_label_width(HAL_COLUMN_1)
        col2_width = _col_label_width(HAL_COLUMN_2)

        for stat in HAL_COLUMN_1:
            # Col 1's label allocation is widened to col1_width + 1 with
            # label_pad=0 (instead of padx between label and spinbox):
            # with anchor=W the label carries 1 char of internal whitespace
            # to the right of the text, the spinbox sits flush against the
            # label's right edge, and the +1 char is reclaimed from the
            # inter-column whitespace (col 2 is RIGHT-anchored, so col 1
            # growing on its right eats into the gap automatically).
            self._build_hal_row(col1_frame, stat, label_width=col1_width+1,
                                label_pad=0)
        for stat in HAL_COLUMN_2:
            # Col 2 spinboxes are 4 chars wide and show one decimal place
            # (CRate/CDmg/Extra/DoT are %-valued; e.g. "60.5" fits).
            self._build_hal_row(col2_frame, stat, label_width=col2_width,
                                spin_width=4)

        # Note explaining HAL threshold semantics, packed below the cols
        # grid. wraplength is updated on <Configure> so the text reflows
        # whenever the HAL frame's width changes (it does -- HAL trades
        # width with Important Settings).
        hal_note = ttk.Label(
            parent,
            text=("Input stats as you expect them to be in the "
            "Combatants menu. Partner passive, Equipment, and "
            "conditional set effects are ignored (Partner flat "
            "stats still count)."),
            foreground=self.colors["fg_dim"],
            justify=tk.LEFT,
            wraplength=175,  # initial; will be replaced on first <Configure>
        )
        # spacing: explanation text -> the controls it explains -- spinbox, label ↕
        hal_note.pack(fill=tk.X, expand=False, pady=(2, 0))
        parent.bind(
            "<Configure>",
            lambda e, lbl=hal_note: lbl.config(wraplength=max(175, e.width - 19)),
            add="+",
        )

    def _build_hal_row(self, parent, stat, label_width=None, label_pad=2,
                       spin_width=4):
        row = ttk.Frame(parent)
        # spacing: spinbox row -> spinbox row -- spinbox, spinbox ↕
        row.pack(fill=tk.X, pady=1)
        # Internal stat key translated to its user-facing label; fixed
        # per-column width so spinboxes align; anchor=tk.W keeps the label
        # text left-justified within that width. No trailing colon.
        label_text = DISPLAY_NAMES.get(stat, stat)
        # spacing: label ↔ its element -- label, spinbox ↔
        # Col 1 passes label_pad=0 and buys the gap with an extra char of
        # label width instead -- see _build_have_at_least for why.
        ttk.Label(row, text=label_text, width=label_width,
                  anchor=tk.W).pack(side=tk.LEFT, padx=(0, label_pad))
        var = self.have_at_least_vars[stat]
        # %-valued stats (DoubleVar) display one decimal place and accept
        # decimal input; raw-integer stats keep the plain integer spinbox.
        # Spinbox width default 4 (enough for 4-digit ATK/HP thresholds);
        # callers may override via spin_width.
        if stat in HAL_STATS_WITH_PCT:
            spin = tk.Spinbox(
                row, from_=0,
                to=100 if stat in HAL_STATS_CAPPED_AT_100 else 999.9,
                increment=1, width=spin_width,
                format="%.1f",
                textvariable=var,
                bg=self.colors["bg_light"], fg=self.colors["fg"],
                buttonbackground=self.colors["bg_lighter"],
                insertbackground=self.colors["fg"],
            )
        else:
            spin = tk.Spinbox(
                row, from_=0, to=99999, increment=1, width=spin_width,
                textvariable=var,
                bg=self.colors["bg_light"], fg=self.colors["fg"],
                buttonbackground=self.colors["bg_lighter"],
                insertbackground=self.colors["fg"],
            )
        spin.pack(side=tk.LEFT)
        self._clamp_on_commit(spin, var)
        if stat in HAL_STATS_WITH_PCT:
            # Wheel steps the %-valued minimums by +-0.1 (the spinbox
            # BUTTONS keep stepping by 1 via increment=1).
            spin.bind("<MouseWheel>",
                      lambda e, v=var: self._hal_pct_wheel(e, v))
        else:
            spin.bind("<MouseWheel>", lambda e, sp=spin: self._spinbox_wheel(e, sp))
        # Save on any write -- Spinbox button clicks fire the var-trace.
        var.trace_add(
            "write",
            lambda *a, s=stat: self._save_have_at_least(s),
        )

    # --------------------------------------------------- UI: Set Configuration

    def _build_set_config(self, parent):
        # Row 1: Max Flex Slots stepper (left) + the three averages
        # spinboxes right-aligned on the same line. The averages live in
        # their own sub-frame packed RIGHT so the group hugs the frame's
        # right padding edge while its pairs keep left-to-right reading
        # order; Max Flex Slots stays at the left edge.
        row1 = ttk.Frame(parent)
        # spacing: config panel row ↕ row -- spinbox, spinbox ↕
        row1.pack(fill=tk.X, pady=(0, 5))

        # spacing: label ↔ its element -- label, spinbox ↔
        ttk.Label(row1, text="Max Flex Slots").pack(side=tk.LEFT, padx=(0, 2))
        flex_spin = tk.Spinbox(
            row1, from_=0, to=6, increment=1, width=3,
            textvariable=self.max_flex_slots_var,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            buttonbackground=self.colors["bg_lighter"],
            insertbackground=self.colors["fg"],
        )
        flex_spin.pack(side=tk.LEFT)
        self._clamp_on_commit(flex_spin, self.max_flex_slots_var)
        flex_spin.bind("<MouseWheel>", lambda e, sp=flex_spin: self._spinbox_wheel(e, sp))
        self.max_flex_slots_var.trace_add(
            "write", lambda *a: self._save_int_safe("max_flex_slots",
                                                       self.max_flex_slots_var))

        avg_frame = ttk.Frame(row1)
        avg_frame.pack(side=tk.RIGHT)
        avg_defs = [
            ("Avg Card DMG%", self.avg_card_dmg_pct_var, "avg_card_dmg_pct"),
            ("Avg Mult Buff%", self.avg_mult_buff_pct_var, "avg_mult_buff_pct"),
            ("Avg Add Buff%", self.avg_add_buff_pct_var, "avg_add_buff_pct"),
        ]
        for idx, (label, var, field) in enumerate(avg_defs):
            # spacing: label ↔ its element -- label, spinbox ↔
            ttk.Label(avg_frame, text=label).pack(side=tk.LEFT, padx=(0, 2))
            spin = tk.Spinbox(
                avg_frame, from_=-9999, to=9999, increment=1, width=5,
                textvariable=var,
                bg=self.colors["bg_light"], fg=self.colors["fg"],
                buttonbackground=self.colors["bg_lighter"],
                insertbackground=self.colors["fg"],
            )
            # spacing: border edge -> first non-button element -- spinbox, panel ↔
            # spacing: element and its label ↔ element and its label -- spinbox, label ↔
            # The last spinbox drops its trailing pad so the group sits
            # flush with the frame's right padding edge (same pattern as
            # the force-main checkbox row).
            pad_right = 0 if idx == len(avg_defs) - 1 else 6
            spin.pack(side=tk.LEFT, padx=(0, pad_right))
            self._clamp_on_commit(spin, var)
            spin.bind("<MouseWheel>", lambda e, sp=spin: self._spinbox_wheel(e, sp))
            var.trace_add(
                "write", lambda *a, f=field, v=var: self._save_int_safe(f, v)
            )

        # Row 3+: Sets list (single grid; 4-piece sorted first, then 2-piece,
        # alphabetical within each).
        # spacing: explanation text -> the controls it explains -- label, checkbox ↕
        ttk.Label(
            parent,
            text="All selected Set and Flex combinations are tried.\n"
            "Number = percent of combatant's damage the effect helps; "
            "0 = only the stats count:",
            font=("Segoe UI", 9), wraplength=580,
        ).pack(anchor=tk.W, pady=(2, 1))

        self.set_grid_frame = ttk.Frame(parent)
        # spacing: border edge -> first non-button element -- panel, checkbox ↔
        # The panel's own left padding is a pixel short for a checkbox.
        # It has to serve two kinds of first element: the text rows above,
        # whose glyphs carry an antialiased edge the audit no longer
        # counts, and these indicators, which are hard-edged and carry
        # none. Equal padding puts them a pixel apart to the eye, so the
        # grid buys the difference back here. Whole-frame rather than a
        # pad on grid column 0: the columns size to their widest set name
        # and the widest sits in the LAST one, where its spinbox clips
        # against the frame edge -- so every column has to move together.
        self.set_grid_frame.pack(fill=tk.X, padx=(1, 0))
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
            # "<pieces>pc <name>" so the piece count leads. The visible
            # text is split into two labels so element-specific sets can
            # be colored: "Xpc" gets the first element's color, "<name>"
            # gets the second's. Single-element sets use the same color
            # for both; non-element sets use the default foreground.
            # ATTRIBUTE_COLORS is the same map the exclude flow uses for
            # combatant-name coloring, so the palette matches across the
            # tab. The checkbox itself carries no text -- text-clicking
            # is wired back to it via <Button-1> bindings on the two
            # labels.
            container = ttk.Frame(self.set_grid_frame)
            # spacing: border edge -> first non-button element -- panel, checkbox ↔
            # spacing: element and its label ↔ element and its label -- spinbox, checkbox ↔
            # spacing: checkbox row -> checkbox row (small division) -- checkbox, checkbox ↕
            #
            # padx is asymmetric and tight on purpose. The grid's three
            # columns size to their widest set name, and the widest of all
            # ("Starlight and Dreams") sits in the last column, where any
            # overflow clips its spinbox against the frame edge. A
            # symmetric pad spends its margin on every column boundary
            # including the outer two; a leading-only gap spends it only
            # between columns and gives the rest back to the names.
            # Columns still read as separate because each one starts with
            # a checkbox indicator.
            #
            # Column 0 gets NO left pad: the value is a gap BETWEEN
            # columns, and applying it to the first column too pushes the
            # leading checkbox right of the explanatory text above and
            # makes that column wider than the rest.
            #
            # This container is a SHARED lever: its pady drives the
            # checkbox AND the conditional-set spinbox, which sit in it
            # together.
            container.grid(row=row, column=col, sticky=tk.W,
                           padx=(0 if col == 0 else 6, 0),
                           pady=(top_pad, 0))
            pieces_text = f"{sinfo['pieces']}pc"
            name_text = sinfo["name"]
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
            # The indicator takes the piece count's Element colour, so the
            # row reads as one coloured unit rather than a grey box beside
            # a coloured label.
            # spacing: border edge -> first non-button element -- panel, checkbox ↔
            # spacing: label ↔ its element -- checkbox, label ↔
            # The piece count is the CHECKBOX'S OWN TEXT, not a label
            # beside it. A text-less tk.Checkbutton asks for 23px around
            # a 16px indicator, so 7px of reserved space follows it that
            # no padding reaches -- where a checkbox carrying its own
            # text sits 5 from it. Splitting the two cost 2px and a
            # widget, and it bought nothing: the indicator already takes
            # the piece count's colour, so there was never a second
            # colour needing a second widget.
            cb = make_checkbox(
                container, self.colors, text=pieces_text, fg=pieces_color,
                variable=var, command=self._save_sets_selected,
            )
            cb.pack(side=tk.LEFT, padx=(0, 0))

            # spacing: label ↔ its element -- checkbox, label ↔
            # The set NAME does need its own widget: a two-Element set
            # colours the count and the name differently, and a
            # Checkbutton draws its text in one colour.
            name_label = ttk.Label(
                container, text=name_text, foreground=name_color,
            )
            # A pad, not the leading space the name used to carry: a
            # space is whatever the font makes it and cannot be tuned by
            # a pixel.
            name_label.pack(side=tk.LEFT, padx=(0, 0))

            # Conditional sets get an effect-share spinbox (0-100, % of
            # this combatant's damage the effect applies to; 0 = effect
            # ignored, set still usable for set-locking). Unconditional
            # set bonuses always apply -- no spinbox.
            if sinfo.get("type") == "conditional":
                pvar = tk.IntVar(value=0)
                self.set_effect_pct_vars[sid] = pvar
                pspin = tk.Spinbox(
                    container, from_=0, to=100, increment=1, width=3,
                    textvariable=pvar,
                    bg=self.colors["bg_light"], fg=self.colors["fg"],
                    buttonbackground=self.colors["bg_lighter"],
                    insertbackground=self.colors["fg"],
                )
                # spacing: label ↔ its element -- label, spinbox ↔
                pspin.pack(side=tk.LEFT, padx=(3, 0))
                pspin.bind(
                    "<MouseWheel>",
                    lambda e, sp=pspin: self._spinbox_wheel(e, sp))
                self._clamp_on_commit(pspin, pvar)
                pvar.trace_add(
                    "write", lambda *_a: self._save_set_effect_pcts())

            # Hover tooltip: the set's bonus description (the same text
            # the Combatants tab shows under an equipped piece). Bound to
            # the row's individual children (not the container) -- Tk
            # fires Leave on the container whenever the pointer crosses
            # onto a child.
            tip_text = sinfo.get("bonus", "")
            for w in (cb, name_label):
                self._tooltip.bind(w, tip_text)

            def _toggle(_event=None, v=var):
                v.set(not v.get())
                self._save_sets_selected()
            # Only the name needs wiring back: the count is inside the
            # checkbox now and toggles it natively.
            name_label.bind("<Button-1>", _toggle)

        # 3 columns; the 2-piece sets always start on a fresh row below
        # the 4-piece sets, with a small vertical gap separating the two
        # groups.
        for i, (sid, sinfo) in enumerate(four):
            # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
            # Leading only, so nothing is added above the first row
            # and the panel's top inset stays where it is.
            _add_set_cb(sid, sinfo, i // ncols, i % ncols,
                        0 if i < ncols else 4)
        four_rows = (len(four) + ncols - 1) // ncols
        # spacing: checkbox row -> checkbox row (small division) -- checkbox, checkbox ↕
        # What a row on the far side of the division adds ON TOP of the
        # ordinary pitch below it.
        SET_GROUP_GAP = 9
        for j, (sid, sinfo) in enumerate(two):
            r = four_rows + j // ncols
            c = j % ncols
            # The division above this group's FIRST row; every row
            # after it takes the ordinary pitch, not nothing. Leaving it
            # at 0 kept the whole second group 4px tighter than the
            # first, which the pitch reading hid by out-voting it.
            top = SET_GROUP_GAP if j < ncols else 4
            _add_set_cb(sid, sinfo, r, c, top)

    # ------------------------------------------------ UI: Exclude Gear panel

    def _build_exclude_gear(self, parent):
        self.exclude_heroes_frame = ttk.Frame(parent)
        # The checklist's content must NOT influence this frame's requested
        # size. The flow layout reads its available width FROM the frame, so
        # letting children propagate their size upward closes a feedback
        # loop: content sets the frame's width -> the body grid re-balances
        # its columns -> the width change fires <Configure> -> Configure
        # re-flows the content -> repeat. Closing that loop is what makes the
        # panel lay itself out once on first open instead of several times
        # over, and what stops the width needing re-tuning by hand.
        #
        # Both dimensions are set explicitly instead. The width below is a
        # LAYOUT PREFERENCE, not a measurement: it's how much of the body's
        # width column 2 asks for. It does NOT need re-tuning when the roster
        # grows -- a longer roster wraps into more rows at the same width.
        # The height is set by _reflow_exclude_heroes from the row count.
        # Neither dimension is derived from the children, so nothing feeds
        # back.
        self.exclude_heroes_frame.pack_propagate(False)
        self.exclude_heroes_frame.configure(width=694, height=1)
        self.exclude_heroes_frame.pack(fill=tk.BOTH, expand=True)
        # The checklist is a true flow layout: variable column widths sized
        # to each name, variable column count per row based on container
        # width (no scaling every column to the widest name). The layout
        # logic lives in refresh_exclude_heroes / _reflow_exclude_heroes;
        # this frame is left as a plain container.

        make_all_none_row(parent, self._exclude_all_gear,
                          self._exclude_no_gear)

    # ----------------------------------------------------------- UI: Results

    def _build_results(self, parent):
        # progress_label is NOT created here -- it lives in the frame's
        # labelwidget header, beside the "Results" title (see setup_ui).

        # No rank column -- row order in the tree is already the implicit
        # rank (top row = best build). "sets" is the only left-aligned,
        # stretching column; all numeric columns are right-aligned
        # (anchor=tk.E). Headings use the new-terminology display names
        # ("Crit%", "CDMG%", "Elem%", "Extra%").
        cols = ("score", "sets", "atk", "hp", "def",
                "crate", "cdmg", "element", "extra", "dot", "ego")
        self.result_tree = ttk.Treeview(
            parent, columns=cols, show="headings", height=9,
        )
        widths = {
            "score": 49, "sets": 350,
            "atk": 32, "hp": 34, "def": 34,
            "crate": 37, "cdmg": 51, "element": 42, "extra": 41,
            "dot": 38, "ego": 25,
        }
        headings = {
            "score": "Score", "sets": "Sets",
            "atk": "ATK", "hp": "HP", "def": "DEF",
            "crate": "Crit%", "cdmg": "CDMG%", "element": "Elem%",
            "extra": "Extra%", "dot": "DoT%", "ego": "Ego",
        }
        for c in cols:
            # The heading takes its column's anchor: a heading defaults to
            # centred whatever the cells below do, which leaves a
            # right-aligned number column with its title over the middle.
            anchor = tk.W if c == "sets" else tk.E
            self.result_tree.heading(c, text=headings[c], anchor=anchor,
                                      command=lambda col=c: self.sort_results(col))
            self.result_tree.column(
                c, width=widths[c], anchor=anchor, stretch=(c == "sets"),
            )

        result_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL,
                                       command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=result_scroll.set)
        # spacing: title above, element below -- title, tree ↕
        # The gap from the panel title to the tree lives HERE, not on the
        # LabelFrame's padding: the Tight.Borderless style's top padding
        # does not move it. See setup_ui, where the frame is built.
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                              pady=(1, 0))
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_tree.bind("<<TreeviewSelect>>", self.on_result_select)

    # --------------------------------------------------- UI: detail tree

    def _build_detail_tree(self, parent):
        cols = ("slot", "set", "main", "lvl", "sub1", "sub2", "sub3", "sub4",
                "gs", "owner")
        self.detail_tree = ttk.Treeview(
            parent, columns=cols, show="headings", height=6,
        )
        # LVL sits between Main and the substats, as it does on the Memory
        # Fragments tab: Main and the four Sub cells share the same
        # "Name: value" shape, so a break between them stops the eye
        # reading Main as a fifth substat.
        # The GS column shows the current GS when the MF is at max level,
        # or the Potential range (low-high) otherwise -- widened to fit a
        # range like "60-100".
        col_defs = [
            ("slot",      "Slot",       83),
            ("set",       "Set",       120),
            ("main",      "Main",      92),
            ("lvl",       "LVL",        24),
            ("sub1",      "Sub1",       87),
            ("sub2",      "Sub2",       87),
            ("sub3",      "Sub3",       87),
            ("sub4",      "Sub4",       87),
            ("gs",        "GS",         40),
            ("owner",     "Owner",      67),  # stretches
        ]
        for col, txt, w in col_defs:
            # Text-ish columns are left-aligned; the numeric lvl and gs
            # stay centered. The heading takes the same anchor as its
            # column, so a title never floats over a differently-aligned
            # cell below it.
            anchor = (tk.W if col in ("slot", "set", "main",
                                      "sub1", "sub2", "sub3", "sub4", "owner")
                      else tk.CENTER)
            self.detail_tree.heading(col, text=txt, anchor=anchor)
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
        self.status_label.config(
            text=f"Loaded {fragment_count} fragments",
            foreground=self.colors["green"],
        )
        self.refresh_hero_list()
        self.refresh_exclude_heroes()
        # Ensure each captured character has a settings entry. Bootstrap
        # at startup uses CHARACTERS; this adds any captured-but-unknown
        # res_ids that don't yet have an entry.
        self._ensure_captured_chars_have_settings()

        # Live equip events trigger this same code path as a fresh capture,
        # so clearing optimization_results outright here would blank the
        # Results + Selected Build panels every time the user moved an MF.
        # Instead we re-map the cached results' MF references to the newly-
        # loaded fragments (matched by id), preserving the display. Results
        # whose MFs are no longer in the snapshot (e.g. deleted) KEEP their
        # old refs; the display layer marks those Owner cells "(deleted)"
        # (see _populate_detail). Stats dicts get recomputed against the
        # new MF substats so upgrade events keep the display consistent
        # (an equip event leaves substats unchanged, so the recompute is
        # a no-op for that case).
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
            settings = self._build_optimizer_settings()
            # Re-map each result's MF refs onto the freshly-loaded
            # fragment objects (matched by id). Deleted MFs keep their
            # OLD ref so the row still renders its remembered
            # slot/set/substats; the display layer marks the Owner cell
            # "(deleted)" (see _populate_detail). Preserving index
            # identity matters: the auto-restore at the bottom of this
            # method re-selects by index.
            remapped = []
            for gear, score, stats in self.optimization_results:
                new_gear = [
                    new_by_id.get(getattr(old_mf, "id", None), old_mf)
                    for old_mf in gear
                ]
                remapped.append((new_gear, score, stats))
            # Recompute stats + the display score over the remapped
            # builds in one pass, re-blended against THIS list's max-D /
            # max-S and rescaled so the top row still reads 100. Equip
            # events leave substats (and thus D/S) unchanged so this is a
            # visual no-op; upgrade events change substats and the
            # column refreshes to match. Doing it here (not per-build
            # with the legacy scalar) keeps the Score column on the same
            # 0-100 scale optimize() produced.
            self.optimization_results = self.optimizer.reblend_results_for_display(
                remapped, char, settings
            )

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

        Display strings are the character names. Captured-but-unknown
        characters (no entry in CHARACTERS) are keyed by their res_id
        string in character_info, so that numeric string IS the name
        shown for them. res_id resolution happens in _resolve_res_id
        when needed.
        """
        all_heroes = set(self.optimizer.characters.keys()) | set(
            self.optimizer.character_info.keys()
        )
        display_strings = sorted(all_heroes)
        self.hero_combo["values"] = display_strings

    def refresh_exclude_heroes(self):
        """Repopulate the exclude-gear checklist using a flow layout.

        Each row is a sub-Frame packed top-down inside
        exclude_heroes_frame; checkbuttons within a row are packed LEFT
        with natural width and a small gap. A new row starts when the next
        checkbutton wouldn't fit in the remaining container width -- so
        column widths vary per name (no scaling to the widest) and the
        number of columns per row varies based on container width.
        Re-flows on <Configure> when the container resizes.

        Skips all work when nothing visible has changed, and updates in
        place rather than re-flowing whenever the roster itself is the same
        (only check states or the current-combatant marker differ). The
        cache is keyed by the currently-selected character so the
        current-char gray+strike treatment gets reapplied when the user
        picks a different combatant.
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

        # Skip-rebuild check: only rebuild when something visually
        # observable has changed.
        if (getattr(self, "_exclude_heroes", None) == new_heroes
                and getattr(self, "_exclude_excluded_set", None) == new_excluded
                and getattr(self, "_exclude_last_current", None) == new_current):
            return

        # While the roster is unchanged, nothing about the LAYOUT can have
        # changed -- only the check states and the current-combatant marker,
        # both of which are option updates on widgets that already exist.
        # Re-flowing here would rearrange identical rows for nothing.
        same_heroes = getattr(self, "_exclude_heroes", None) == new_heroes
        self._exclude_heroes = new_heroes
        self._exclude_excluded_set = new_excluded
        self._exclude_last_current = new_current

        if same_heroes and self._exclude_widgets:
            self._apply_exclude_states()
            return

        # Roster changed: force the re-flow past its partition guard, since
        # the same row shape may now hold different combatants.
        self._reflow_exclude_heroes(force=True)

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

    def _exclude_checkbutton(self, hero: str):
        """The Checkbutton for `hero`, created on first use and reused for
        the lifetime of the roster entry.

        Creating these per re-flow is what made the panel flash white: a
        freshly created batch of ~40 classic Tk widgets gets mapped and
        drawn before the layout that positions them is final, so the user
        sees a row of blank default-colored boxes. Widgets are therefore
        created once and only repositioned afterwards. `make_checkbox`
        now realizes each window at build time, which removes the erase
        the user saw -- but not the cost of destroying and rebuilding the
        set on every <Configure>, so the reuse stays.

        The check variable is created alongside and kept in
        exclude_hero_vars; _apply_exclude_states syncs its value from
        persisted state without disturbing the widget.
        """
        cb = self._exclude_widgets.get(hero)
        if cb is not None:
            return cb
        import tkinter.font as tkfont
        var = tk.BooleanVar(value=False)
        self.exclude_hero_vars[hero] = var
        char_data = get_character_by_name(hero)
        fg_color = ATTRIBUTE_COLORS.get(
            char_data.get("attribute", "Unknown"), self.colors["fg"]
        )
        if not hasattr(self, "_exclude_strike_font"):
            self._exclude_strike_font = tkfont.Font(
                family="Segoe UI", size=9, overstrike=1
            )
        cb = make_checkbox(
            self.exclude_heroes_frame, self.colors, text=hero, variable=var,
            fg=fg_color, command=self._save_excluded_gear,
        )
        self._exclude_widgets[hero] = cb
        return cb

    def _apply_exclude_states(self):
        """Sync every checkbutton's variable from the persisted excluded
        set, and apply the current-combatant gray+strike treatment. Pure
        option updates on existing widgets -- no creation, no re-layout.
        var.set() does not fire a Checkbutton's command, so this can't
        write back to settings.
        """
        current = self.selected_character.get()
        for hero, cb in self._exclude_widgets.items():
            res_id = self._resolve_res_id(hero)
            var = self.exclude_hero_vars.get(hero)
            if var is not None:
                var.set(str(res_id) in self._exclude_excluded_set
                        if res_id is not None else False)
            # The currently-selected combatant's row is grayed out and
            # struck through: the optimizer ignores it (their MFs are always
            # available -- see the filter in _build_optimizer_settings). The
            # check state is left alone so it returns when the user picks a
            # different combatant.
            if hero == current:
                fg_color = self.colors["fg_dim"]
                cb_font = self._exclude_strike_font
            else:
                char_data = get_character_by_name(hero)
                fg_color = ATTRIBUTE_COLORS.get(
                    char_data.get("attribute", "Unknown"), self.colors["fg"]
                )
                cb_font = ("Segoe UI", 9)
            try:
                cb.configure(fg=fg_color, activeforeground=fg_color,
                             font=cb_font)
            except tk.TclError:
                pass

    def _reflow_exclude_heroes(self, force: bool = False):
        """Position the exclude checklist's checkbuttons into rows that fit
        the current width.

        Widgets are created once (see _exclude_checkbutton) and placed by
        explicit coordinate here, so a re-flow moves widgets instead of
        destroying and recreating them -- no flashing, and no dependence on
        row sub-frames (a Tk widget can't change parent, so pooled row
        frames couldn't be reused across differing partitions).

        When the computed partition and width match what's already on
        screen this returns without touching a widget, so a burst of
        <Configure> events costs nothing. Pass force=True after the roster
        changes, where an identical partition may still need new widgets.
        """
        container_w = self.exclude_heroes_frame.winfo_width()
        if container_w <= 1:
            # Not realized yet -- this runs during startup, before mainloop.
            # Draining pending geometry yields the TRUE allocated width, so
            # the partition computed below is the final one and the
            # <Configure> that realization fires later hits the no-op guard
            # instead of re-flowing in view. This is only safe because the
            # main window is invisible for the whole of startup (see
            # OptimizerGUI._hide_until_ready): the drain paints, and painting
            # a half-built window is precisely what being hidden prevents.
            self.exclude_heroes_frame.update_idletasks()
            container_w = self.exclude_heroes_frame.winfo_width()
        if container_w <= 1:
            # Children never mapped (the withdraw() fallback path). Use the
            # frame's requested width -- the explicit layout preference set
            # in _build_exclude_gear.
            container_w = self.exclude_heroes_frame.winfo_reqwidth()
        if container_w <= 1:
            # Still unrealized (the tab has never been mapped). Realization
            # fires <Configure>, which brings us back here; retry once as a
            # fallback, but never chain retries.
            if not getattr(self, "_exclude_reflow_retried", False):
                self._exclude_reflow_retried = True
                self.exclude_heroes_frame.after(
                    50, self._reflow_exclude_heroes)
            return
        self._exclude_reflow_retried = False

        # spacing: element and its label ↔ element and its label -- checkbox, checkbox ↔
        # Between the checkbuttons' BOXES. A checkbutton's ink stops
        # short of its box on each side, so the rendered gap is wider
        # than this by a constant -- the rule's 8 is the rendered one.
        gap = 4        # minimum px between checkbuttons in a row
        edge_pad = 2   # px on each side (kept symmetric)
        available_w = max(1, container_w - 2 * edge_pad)

        # Drop widgets for combatants that left the roster, then make sure
        # every current one has a widget. Measurement uses each widget's
        # REAL requested width -- valid as soon as the widget exists -- so
        # there's no font-metric estimate to undershoot and no second
        # correction pass: a font-metric estimate runs a few px small per
        # name, which forces justification to re-measure and can still clip
        # the last name in a row.
        for gone in [h for h in self._exclude_widgets
                     if h not in self._exclude_heroes]:
            self._exclude_widgets.pop(gone).destroy()
            self.exclude_hero_vars.pop(gone, None)
        widths = {}
        for hero in self._exclude_heroes:
            widths[hero] = self._exclude_checkbutton(hero).winfo_reqwidth()
        # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
        # The row PITCH: rows are placed at y = row * row_h, so this
        # offset against the widget's own requested height is the
        # background left between them, one for one.
        #
        # **Keep it positive.** A negative offset makes the pitch shorter
        # than the widget, so consecutive rows OVERLAP and each one's
        # painted bottom is clipped by the row beneath it -- which also
        # makes the gap measure smaller than it is, so a reading taken
        # then understates the true value.
        #
        # A LEVER, not a rendered distance, and one that moves when the
        # WIDGET does: it sat at -2 while these carried Tk's default
        # border and focus ring, and routing them through `make_checkbox`
        # dropped 6px of requested height and took the gap with it.
        # Measured 5px at +2, and the relation is one for one, so +4 is
        # the rule's 7px. Re-measure after anything that changes the
        # checkbutton's height -- this rule is not in the audit yet, so
        # nothing else will notice.
        ROW_PITCH_OFFSET = 4
        row_h = max(
            (cb.winfo_reqheight() for cb in self._exclude_widgets.values()),
            default=22,
        ) + ROW_PITCH_OFFSET

        # Partition into rows: names keep their natural widths (no scaling
        # every column to the widest name) and the column count per row
        # follows from the available width.
        rows = []
        cur_row = []
        cur_w = 0
        for hero in self._exclude_heroes:
            w = widths[hero]
            if cur_row and cur_w + gap + w > available_w:
                rows.append(cur_row)
                cur_row = []
                cur_w = 0
            cur_w += w + (gap if cur_row else 0)
            cur_row.append(hero)
        if cur_row:
            rows.append(cur_row)

        # Nothing visible would change -> don't touch a single widget.
        if (not force
                and rows == getattr(self, "_exclude_partition", None)
                and container_w == getattr(self, "_exclude_packed_width", None)):
            return

        # Place every checkbutton by explicit coordinate. Rows other than
        # the last are justified: leftover width is spread into the
        # inter-name gaps so the row ends flush with the right edge. The last
        # row keeps the natural gap (justifying 2-3 names across the full
        # width looks broken). Because the widths are the widgets' real
        # requested widths, one pass lands flush -- no re-measure, and no
        # risk of clipping the last name in a row.
        for row_idx, row in enumerate(rows):
            n = len(row)
            content_w = sum(widths[h] for h in row)
            if n > 1 and row_idx < len(rows) - 1:
                extra, rem = divmod(max(0, available_w - content_w), n - 1)
            else:
                extra, rem = gap, 0
            x = edge_pad
            y = row_idx * row_h
            for i, hero in enumerate(row):
                self._exclude_widgets[hero].place(x=x, y=y)
                x += widths[hero] + extra + (1 if i < rem else 0)

        # The row count is the ONE thing the content drives (see
        # _build_exclude_gear): size the frame to exactly its rows.
        # One pitch short of `rows * row_h`: the pitch INCLUDES the gap
        # that follows a row, so reserving it for the last row too leaves
        # 4px of empty frame under the checklist -- which the All/None
        # row below then sits on top of its own pad, reading 7 where the
        # other three panels read 3.
        self.exclude_heroes_frame.configure(
            height=max(1, len(rows) * row_h - ROW_PITCH_OFFSET))
        self._exclude_partition = rows
        self._exclude_packed_width = container_w
        self._apply_exclude_states()

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

        Also bootstraps the "Exclude Combatant's MFs" checklist to
        default-checked-for-all. Every character the exclude system has
        seen before is tracked in the persisted `exclude_seen_rids`
        marker list; a res_id absent from that marker is "new to the
        exclude system" and gets auto-added to the excluded list (then
        recorded as seen). The user's manual unchecks are preserved
        across reloads: unchecking removes the res_id from
        excluded_gear_chars but leaves it in exclude_seen_rids, so it's
        never re-added.

        Tracking against exclude_seen_rids rather than "has a settings
        entry" is deliberate: bootstrap_known_characters creates a
        settings entry for every KNOWN character at startup, so a newly
        added known character would already have an entry by the time
        this runs and an entry-existence test would never see it as new.
        The seen-marker is independent of that.
        """
        if self.opt_settings is None:
            return

        # First-run bootstrap: populate the excluded list + the seen
        # marker with every currently-known res_id. Includes both
        # characters already in the settings file (via
        # bootstrap_known_characters at startup) and any new captured
        # res_ids we're about to ensure below.
        #
        # Safety: only OVERWRITE the excluded list when it's empty. For
        # users upgrading from a previous version of the program who've
        # already configured their exclude list, the flag will be absent
        # but the list will be non-empty -- in that case we just set the
        # flag (so this check doesn't re-run on every launch) and leave
        # their state alone.
        all_known_rids = list(self.opt_settings.data.get("characters", {}).keys())
        for name in self.optimizer.character_info.keys():
            rid = self._resolve_res_id(name)
            if rid is not None and str(rid) not in all_known_rids:
                all_known_rids.append(str(rid))

        if not self.opt_settings.data.get("excluded_default_initialized", False):
            current_excluded = list(self.opt_settings.get_excluded_gear_chars())
            if not current_excluded:
                self.opt_settings.set_excluded_gear_chars(all_known_rids)
            # Seed the seen marker with everything known at first run --
            # whether or not we overwrote the excluded list -- so the
            # per-character auto-exclude below only fires for res_ids that
            # appear AFTER this point (genuinely new characters).
            self._set_exclude_seen_rids(all_known_rids)
            # Mark flag either way so subsequent launches don't re-check.
            self.opt_settings.data["excluded_default_initialized"] = True
        elif "exclude_seen_rids" not in self.opt_settings.data:
            # Upgrade path: an existing user (flag already set) from before
            # the seen-marker existed. Grandfather every currently-known
            # res_id as "already seen" WITHOUT touching their exclude
            # state, so we don't wrongly re-exclude characters they'd
            # deliberately un-excluded. Genuinely new characters captured
            # after this point are absent from the marker and get the
            # default-excluded treatment below.
            self._set_exclude_seen_rids(all_known_rids)

        # Per-character pass: ensure a settings entry, and auto-exclude
        # any res_id the exclude system hasn't seen before (independent
        # of whether a settings entry already existed for it).
        seen_rids = set(self._get_exclude_seen_rids())
        newly_seen = []
        for name in self.optimizer.character_info.keys():
            rid = self._resolve_res_id(name)
            if rid is None:
                continue
            rid_str = str(rid)
            self.opt_settings.ensure_character(rid, name=name)
            self._sync_optimize_level(rid, name)
            if rid_str not in seen_rids:
                # New to the exclude system -> default to excluded.
                excluded = list(self.opt_settings.get_excluded_gear_chars())
                if rid_str not in excluded:
                    excluded.append(rid_str)
                    self.opt_settings.set_excluded_gear_chars(excluded)
                seen_rids.add(rid_str)
                newly_seen.append(rid_str)
        if newly_seen:
            self._set_exclude_seen_rids(sorted(seen_rids))

        # ensure_character doesn't auto-persist; nudge a write if any
        # new entries appeared. _write is safe to call repeatedly.
        if self.opt_settings.data["characters"]:
            self.opt_settings._write()

    def _sync_optimize_level(self, res_id, name: str) -> None:
        """Keep a combatant's "Optimize for LVL" in step with their real
        level, without overriding a deliberate choice.

        The setting defaults to 60 so the tab's numbers match the in-game
        stat sheet. When a combatant is levelled past the highest level the
        program has seen for them, the intent is almost always to optimize
        for the new level, so the setting follows -- ONCE. The highest
        observed level lives in the top-level `optimize_level_seen` map, and
        that's what makes it a one-time bump rather than a standing
        override: once recorded, a user who dials the level back down keeps
        it on every later load, because their actual level no longer exceeds
        what was already seen.

        On the FIRST sync for a combatant (nothing recorded yet) the setting
        is initialised from their actual level rather than left as-is, so
        entries still carrying the old default of 62 line up with the game
        as well.

        Clamped to 60..62, the band the stat tables cover -- a combatant
        below 60 is evaluated at 60 regardless (see
        GearOptimizer._resolve_effective_level).

        Mutates the settings entry in place; the caller's _write() persists
        it, so a first-run sync across the whole roster costs one write.
        """
        if self.opt_settings is None:
            return
        info = self.optimizer.character_info.get(name)
        actual = int(getattr(info, "level", 0) or 0) if info is not None else 0
        if actual <= 0:
            return
        rid_str = str(res_id)
        entry = self.opt_settings.data.get("characters", {}).get(rid_str)
        if not isinstance(entry, dict):
            return
        seen_map = self.opt_settings.data.setdefault("optimize_level_seen", {})
        prev_seen = seen_map.get(rid_str)
        if prev_seen is not None and actual <= int(prev_seen):
            return
        seen_map[rid_str] = actual
        try:
            current = int(entry.get("optimize_for_level", 60) or 60)
        except (TypeError, ValueError):
            current = 60
        target = max(60, min(62, actual))
        if prev_seen is None or target > current:
            entry["optimize_for_level"] = target

    def _get_exclude_seen_rids(self) -> list:
        """res_id strings the exclude system has already processed. Stored
        as a top-level key in optimizer_settings.json (preserved verbatim
        by the manager's load()). Absent -> empty list."""
        if self.opt_settings is None:
            return []
        val = self.opt_settings.data.get("exclude_seen_rids", [])
        return [str(x) for x in val] if isinstance(val, list) else []

    def _set_exclude_seen_rids(self, rids) -> None:
        """Persist the exclude-seen marker list. Written on the next
        manager _write (the caller triggers one)."""
        if self.opt_settings is None:
            return
        self.opt_settings.data["exclude_seen_rids"] = sorted({str(x) for x in rids})

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
            self.fracture_pct_var.set(s.get("fracture_pct", 0))
            self.atk_def_split_var.set(s.get("atk_def_split", 0))
            self.shielding_healing_weight_var.set(s.get("shielding_healing_weight", 0))

            fm = s.get("force_main", {})
            for key, _label, _slot, _stat in FORCE_MAIN_DEFS:
                self.force_main_vars[key].set(bool(fm.get(key, False)))

            hal = s.get("have_at_least", {})
            for stat in HAL_ALL_STATS:
                raw = hal.get(stat, 0)
                if stat in HAL_STATS_WITH_PCT:
                    self.have_at_least_vars[stat].set(round(float(raw), 1))
                else:
                    self.have_at_least_vars[stat].set(int(raw))

            self.max_flex_slots_var.set(s.get("max_flex_slots", 6))
            pcts = s.get("set_effect_pcts", {}) or {}
            for sid, pvar in self.set_effect_pct_vars.items():
                try:
                    pvar.set(int(pcts.get(str(sid), 0)))
                except (TypeError, ValueError):
                    pvar.set(0)
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
            if stat in HAL_STATS_WITH_PCT:
                # One decimal place for the %-valued stats.
                v = round(float(self.have_at_least_vars[stat].get()), 1)
            else:
                v = int(self.have_at_least_vars[stat].get())
        except (tk.TclError, ValueError):
            return  # spinbox in a half-typed state; ignore
        if v < 0:
            v = 0
        self.opt_settings.set_have_at_least(self._current_res_id, stat, v)

    def _save_set_effect_pcts(self):
        """Persist the per-conditional-set effect shares for the current
        character as the `set_effect_pcts` dict (zero entries dropped --
        absent id = 0)."""
        if self._loading_settings or self._current_res_id is None:
            return
        if self.opt_settings is None:
            return
        pcts = {}
        for sid, var in self.set_effect_pct_vars.items():
            try:
                v = int(var.get())
            except (tk.TclError, ValueError):
                return  # spinbox mid-edit; skip this save tick
            if v > 0:
                pcts[str(sid)] = min(100, v)
        self.opt_settings.set(self._current_res_id, "set_effect_pcts", pcts)

    def _save_min_gear_level(self):
        """Persist the GLOBAL minimum-MF-level filter to settings.json
        (SettingsManager). Not per-character, so no _loading_settings
        gating."""
        sm = getattr(self.context, "settings_manager", None)
        if sm is None:
            return
        try:
            v = int(self.min_gear_level_var.get())
        except (tk.TclError, ValueError):
            return
        sm.set("optimizer_min_gear_level", max(0, min(5, v)))

    def _current_min_gear_level(self) -> int:
        """The global minimum-MF-level filter's current value (0 = off),
        TclError-safe (spinbox mid-edit reads as 0... the last persisted
        value is what the run would use next launch anyway)."""
        try:
            return max(0, min(5, int(self.min_gear_level_var.get())))
        except (tk.TclError, ValueError):
            return 0

    def _save_ignore_offelement(self):
        """Persist the GLOBAL off-element Slot V filter toggle to
        settings.json (SettingsManager). Not per-character, so no
        _loading_settings gating."""
        sm = getattr(self.context, "settings_manager", None)
        if sm is None:
            return
        try:
            v = bool(self.ignore_offelement_var.get())
        except tk.TclError:
            return
        sm.set("optimizer_ignore_offelement", v)

    def _current_ignore_offelement(self) -> bool:
        """The global off-element Slot V filter's current state."""
        try:
            return bool(self.ignore_offelement_var.get())
        except tk.TclError:
            return True

    def _save_sets_selected(self):
        if self._loading_settings or self._current_res_id is None:
            return
        if self.opt_settings is None:
            return
        ids = [sid for sid, var in self.set_selected_vars.items() if var.get()]
        self.opt_settings.set_sets_selected(self._current_res_id, ids)

    def _save_excluded_gear(self):
        """Translate the hero-name-keyed checkboxes back to a res_id list
        and persist. Skipped while no opt_settings is available.

        Preserves persisted res_ids that aren't currently DISPLAYED in the
        checklist: only captured characters get a checkbox, but the
        excluded list is bootstrapped with EVERY known character's res_id.
        Rebuilding the list from the checkboxes alone would silently drop
        the not-yet-captured entries on any toggle -- and they'd never be
        re-added (the auto-exclude in _ensure_captured_chars_have_settings
        only fires for res_ids the exclude system hasn't seen before, and
        bootstrap already marked these as seen), so those characters would
        arrive UN-excluded when first captured.
        """
        if self.opt_settings is None:
            return
        displayed_ids = set()
        checked_ids = []
        for hero, var in self.exclude_hero_vars.items():
            rid = self._resolve_res_id(hero)
            if rid is None:
                continue
            rid_str = str(rid)
            displayed_ids.add(rid_str)
            if var.get():
                checked_ids.append(rid_str)
        # Keep every persisted exclusion we don't show a checkbox for.
        kept = [rid for rid in self.opt_settings.get_excluded_gear_chars()
                if rid not in displayed_ids]
        self.opt_settings.set_excluded_gear_chars(kept + checked_ids)

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
                # spacing: content frame -> content frame -- frame, frame ↕
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
        # The combo is disabled when nothing is loaded, but
        # selected_character can retain a stale name (e.g. data reloaded
        # empty) -- don't start a pointless run over zero fragments.
        if not self.optimizer.fragments:
            messagebox.showwarning("Warning", "No data loaded")
            return
        # Start is disabled while a run is live; guard anyway in case the
        # command fires through another path (e.g. keyboard invoke).
        if self._optimizing:
            return

        if self._current_res_id is None:
            # Allow optimization to proceed for unknown chars but skip
            # the persistence path. They'll use whatever the UI vars hold
            # at the moment.
            pass

        # Signal any straggler worker to stop, then hand the NEW run its
        # OWN flag object. Re-using one shared list was racy: resetting
        # cancel_flag[0] = False could revive a just-cancelled worker
        # that hadn't polled the flag yet, leaving two threads mutating
        # shared optimizer state.
        self.cancel_flag[0] = True
        self.cancel_flag = [False]
        run_flag = self.cancel_flag
        self._run_id += 1
        run_id = self._run_id

        # If the chosen sets can't possibly lock enough slots to leave a
        # valid build under the current Maximum Flex Slots cap, bump the
        # cap up to the minimum that works (persisting it + reflecting
        # it in the UI). Returns the new value if a bump happened, else None.
        bumped_to = self._maybe_bump_flex_slots()

        settings = self._build_optimizer_settings()

        # Zero out the optimizer's legacy priority_score system so the
        # slot pre-filter sorts by gear_score (which uses the Scoring
        # tab's active preset). The actual build SCORING is the
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
                self.result_queue.put(("progress", run_id, checked, total, found))
            try:
                results = self.optimizer.optimize(
                    char_name, settings, progress_cb, run_flag
                )
                # The optimizer applies the Have-at-least filter inline
                # during enumeration (faster + reports counters). Read its
                # last_optimize_stats to drive the "no builds matched" popup
                # message in check_queue.
                stats = getattr(self.optimizer, "last_optimize_stats", {}) or {}
            except Exception:
                # A crashed worker must STILL post "done" -- check_queue's
                # done handler is the only thing that re-enables Start.
                results, stats = [], {}
            self.result_queue.put(("done", run_id, results, stats))

        self._optimizing = True
        if self.start_button is not None:
            self.start_button.config(state=tk.DISABLED)
        threading.Thread(target=optimize_thread, daemon=True).start()

        # Surface the auto-bump AFTER kicking off the worker thread, so
        # the notice and the optimization run "in parallel" -- the modal
        # dialog blocks only the UI thread; the daemon worker keeps going.
        if bumped_to is not None:
            # Pad the message out so the dialog is wide enough for the
            # title ("Not Enough Flex Slots") not to clip -- messagebox
            # widths are driven by the message text, not the title.
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
          * Scoring fields used by `calculate_build_stats` and
            `_compute_optimizer_score` (Extra%, DoT%, ATK/DEF split,
            shield/heal weight, per-set effect shares, avg buff fields,
            level stepper, element override, have-at-least minimums).

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
        # optimizer's legacy fields (kept for back-compat; the
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
            # GLOBAL minimum-MF-level candidacy filter (settings.json,
            # not per-character). 0 = off.
            "min_gear_level": self._current_min_gear_level(),
            # GLOBAL off-element Slot V candidacy filter (settings.json,
            # not per-character). Drops Slot V candidates whose main
            # stat is an element DMG% not matching the combatant's
            # element; ATK%/HP% mains always pass.
            "ignore_offelement_slot5": self._current_ignore_offelement(),
            # ----- Set-combo fields (consumed by optimize's locked-count rule) -----
            "sets_selected": list(s.get("sets_selected", [])),
            "max_flex_slots": int(s.get("max_flex_slots", 6)),
            # ----- Weights for the slot pre-filter sort -----
            # The optimizer ranks fragments per slot by their score under
            # these weights before applying the Top filter. Resolved from
            # CharacterPresetManager (character's assignment) -> active
            # preset -> empty (all-1.0) per _get_weights_for_character.
            # When None or empty, the optimizer falls back to fragment.
            # gear_score (the cached value from the active preset).
            "slot_filter_weights": self._get_weights_for_character(
                self.selected_character.get()
            ) or None,
            # ----- Scoring fields (consumed by calculate_build_stats + _compute_optimizer_score) -----
            "optimize_for_level": s.get("optimize_for_level", 62),
            "extra_pct": s.get("extra_pct", 0),
            "dot_pct": s.get("dot_pct", 0),
            "fracture_pct": s.get("fracture_pct", 0),
            "atk_def_split": s.get("atk_def_split", 0),
            "shielding_healing_weight": s.get("shielding_healing_weight", 0),
            "set_effect_pcts": dict(s.get("set_effect_pcts", {}) or {}),
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
                # Every message is tagged with the run-id it came from;
                # drop stragglers from superseded runs so a cancelled
                # worker's late "done" can't overwrite the current run's
                # progress or results.
                if msg[1] != self._run_id:
                    continue
                if msg[0] == "progress":
                    _, _rid, checked, total, found = msg
                    pct = (checked / total * 100) if total > 0 else 0
                    # The optimizer trims its in-flight results list
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
                    _, _rid, results, stats = msg
                    self._optimizing = False
                    if self.start_button is not None:
                        self.start_button.config(state=tk.NORMAL)
                    self.optimization_results = results
                    self.display_results(results)
                    passed_sets = stats.get("passed_set_reqs", 0)
                    # Show the run's wall time next to the build count.
                    duration = stats.get("duration_seconds", 0.0)
                    # Record the whole run to settings/perf_log.txt. The
                    # counters dict is splatted wholesale rather than picked
                    # over, so every counter optimize() records lands in the
                    # log without this call needing to know their names.
                    import perf_log
                    perf_log.log(
                        "optimize",
                        char=self.selected_character.get(),
                        fragments=len(self.optimizer.fragments),
                        min_gear_level=self._current_min_gear_level(),
                        ignore_offelement=self._current_ignore_offelement(),
                        **{k: v for k, v in stats.items()},
                    )
                    if duration >= 60:
                        time_note = f" in {int(duration // 60)}m {duration % 60:.0f}s"
                    elif duration > 0:
                        time_note = f" in {duration:.1f}s"
                    else:
                        time_note = ""
                    # Per-slot candidate counts: the compared total is
                    # their PRODUCT, which the Top filter's 10-fragment
                    # floor and 20% cut often make very round (six
                    # floored slots = exactly 1,000,000) and insensitive
                    # to filter changes. The breakdown is what actually
                    # moves when a filter starts biting a slot.
                    slot_counts = stats.get("slot_candidates") or {}
                    slots_note = ""
                    if slot_counts:
                        slots_note = " (slots " + "×".join(
                            str(slot_counts[s]) for s in sorted(slot_counts)
                        ) + ")"
                    if results:
                        self.progress_label.config(
                            text=f"Done{time_note}! "
                                 f"{stats.get('total_combinations', 0):,} "
                                 f"builds compared{slots_note}"
                        )
                    elif passed_sets > 0:
                        # Candidates passed the set requirements but ALL got
                        # filtered by Have-at-least. Show actionable hint.
                        self.progress_label.config(
                            text=f"Done{time_note}! 0 builds "
                                 f"(filtered from {passed_sets})"
                        )
                        messagebox.showinfo(
                            "No builds match",
                            "0 builds matched the 'Have at least' minimums. "
                            "Try lowering one or more thresholds in the right panel."
                        )
                    else:
                        # No candidate combinations even satisfied set
                        # requirements (e.g. no 4-piece set selected has 4
                        # candidates in slot N, or all selected sets
                        # together can't fit in 6 slots).
                        #
                        # The label stays as short as the branch above it:
                        # the reasons run long enough to clip it, and a
                        # zero-build run needs the same announcement
                        # whichever way it got there.
                        self.progress_label.config(
                            text=f"Done{time_note}! 0 builds (no candidates)"
                        )
                        active = []
                        if self._current_min_gear_level() > 0:
                            active.append("'Ignore MFs below level'")
                        if self._current_ignore_offelement():
                            active.append("'Ignore off-Element MFs'")
                        reasons = [
                            "No combination of your Memory Fragments "
                            "satisfied the Set Configuration.",
                            "",
                            "Either a set you picked has too few fragments "
                            "in one slot, or the sets together need more "
                            "than 6 slots. Raising Maximum Flex Slots, or "
                            "picking fewer sets, is usually the fix.",
                        ]
                        if active:
                            reasons += [
                                "",
                                "Also active: " + " and ".join(active) + ".",
                            ]
                        if slot_counts:
                            reasons += [
                                "",
                                "Candidates per slot: " + ", ".join(
                                    f"{s}: {slot_counts[s]}"
                                    for s in sorted(slot_counts)
                                ),
                            ]
                        messagebox.showinfo(
                            "No builds match", "\n".join(reasons)
                        )
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)

    def display_results(self, results: list):
        self.result_tree.delete(*self.result_tree.get_children())
        char = self.selected_character.get()
        # Resolve the user's selected sets for THIS character once so
        # _format_set_summary can tag accidental sets with "(F)".
        selected_set_ids = set()
        if self.opt_settings is not None and self._current_res_id is not None:
            try:
                s = self.opt_settings.get_character_data(self._current_res_id)
                selected_set_ids = set(s.get("sets_selected", []))
            except Exception:
                selected_set_ids = set()
        # Fragment-id set of the character's currently-equipped build, so
        # the row that exactly matches it can be tagged "(E)". Empty when
        # the character has fewer than a full build equipped.
        equipped_ids = frozenset(
            getattr(p, "id", None)
            for p in self.optimizer.characters.get(char, [])
        )
        for i, (gear, score, stats) in enumerate(results[:100]):
            sets_str = self._format_set_summary(gear, selected_set_ids)
            # Tag the already-equipped build with "(E)" so the user can
            # see at a glance that one option is what they already have.
            score_str = f"{score:.1f}"
            if equipped_ids and frozenset(
                getattr(p, "id", None) for p in gear
            ) == equipped_ids:
                score_str = f"{score_str} (E)"
            # Element% isn't part of calculate_build_stats' output, so
            # augment to compute it for this build/character. Ego is
            # already in the stats dict. The value tuple order must
            # match the column order: ...cdmg, element, extra, dot, ego.
            stats = self._augment_stats(stats, gear, char)
            self.result_tree.insert("", tk.END, values=(
                score_str, sets_str,
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
        """Build the Results 'Sets' column string for one build.

        Ordering: 4-piece active sets first, then 2-piece active sets, then
        a single "N Flex" token if any wildcard slots remain. Alphabetical
        (ascending) within each category.

        Only sets whose equipped count actually MEETS their piece
        requirement are named (an inactive 3-of-a-4pc set contributes its
        pieces to the flex count, not a name). Overflow pieces of an active
        set (e.g. a 6th piece of a 4-piece set) also count as flex.

        Name shortening: names <= 15 chars are kept as-is; longer names are
        collapsed to their first word.

        `selected_set_ids` is the set of set IDs the user
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
            # Element% isn't stored in e[2]; compute it
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
        # Secondary sort is always by score. Python's sort
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
        # Compute the current build at the SAME effective level the
        # optimizer and the breakdown popup use (the "Optimize for LVL"
        # stepper), so the Stats Comparison "Now" column and the popup's
        # "currently equipped" numbers agree. Without this the current
        # build would be read at the character's actual level and the
        # level-dependent stats (ATK/DEF/HP and their Pot7 rows) would
        # disagree whenever the stepper differs from the actual level.
        eff_level = self._effective_optimize_level(char)
        current_stats = self.optimizer.calculate_build_stats(
            current_gear, char, effective_level=eff_level
        )

        # Inject Element% (not part of calculate_build_stats) so the
        # Stats Comparison tree can show it under Totals.
        current_stats = self._augment_stats(current_stats, current_gear, char)
        new_stats = self._augment_stats(new_stats, gear, char)

        self._populate_stats_compare(current_stats, new_stats)
        self._populate_detail(gear)

    def show_current_stats(self, char_name: str):
        gear = self.optimizer.characters.get(char_name, [])
        # Match the optimizer / breakdown effective level so this view
        # agrees with the Results "New" column and the contributions
        # popup (see on_result_select).
        eff_level = self._effective_optimize_level(char_name)
        stats = self.optimizer.calculate_build_stats(
            gear, char_name, effective_level=eff_level
        )
        stats = self._augment_stats(stats, gear, char_name)
        self._populate_stats_compare(stats, None)

    def _effective_optimize_level(self, char_name: str):
        """The level the Optimizer tab evaluates a build at: the current
        character's "Optimize for LVL" stepper value. Falls back to the
        UI var, then None (which lets calculate_build_stats resolve its
        own default). Kept in one place so every Stats Comparison /
        breakdown consumer reads the same level."""
        if self.opt_settings is not None and self._current_res_id is not None:
            try:
                s = self.opt_settings.get_character_data(self._current_res_id)
                return s.get("optimize_for_level")
            except Exception:
                pass
        try:
            return self.optimize_for_level_var.get()
        except tk.TclError:
            return None

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
    # "Show all stat contributions" right-click breakdown
    # =================================================================

    def _show_stats_context_menu(self, event):
        """Right-click on the Stats Comparison tree -> two options for the
        full per-source breakdown:
          (a) selected build       = the row currently picked in Results
          (b) currently equipped   = the character's actual in-game gear
        The user picks which one explicitly -- no silent fallback from
        (a) to (b).
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
                              the two intents are separate menu entries).
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
            bd = self.optimizer.compute_build_breakdown(
                gear, char, settings=settings)
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
        the popup. Column widths:

          ATK/DEF/HP:  Base 3, Partner 3, MF% 4, Pot 3, MF Flat 2,
                         Affinity 2, Partner% 4, Set Effect Sum 4,
                         Equip (apx.) 2, Other = checkmark / cross (width 1)
          CRate/CDmg:  Base 5, MF Main 4, MF Sub Sum 4, Set Effect Sum 4,
                         Other 4 (or just the cross when zero)
          Element%, ExtrDMG%, Dot DMG%, Ego:
                       MF Main / MF Sub Sum 4 each, Set Effect Sum 4,
                         Other 4 (or just the cross when zero)
          xDMG% / +DMG%:  4 (set-effect contributions only; the user's
                         Avg Multi Buff% / Avg Add Buff% fields are
                         deliberately excluded)

        The "0 if cross" rule for Other: when the value is zero, we render
        a bare cross mark (1 char) rather than a 4-wide padded zero, so the
        cross stands out vs. legitimate-but-small numeric contributions.
        """
        def _int(v, w):
            return f"{v:>{w}.0f}"

        def _dec(v, w):
            return f"{v:>{w}.1f}"

        def _other(v, w):
            # 4-wide decimal when non-zero; bare cross when zero.
            return f"{v:>{w}.1f}" if abs(v) > 0.05 else "\u2717"

        def _other_int(v, w):
            # Integer variant of _other (Ego is integer-valued in game
            # data, so its rows render without decimal points).
            return f"{v:>{w}.0f}" if abs(v) > 0.05 else "\u2717"

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
                f"Affinity {_int(d['affection'], 2)}, "
                f"Partner% {_dec(d['partner_pct'], 4)}, "
                f"Set Effect Sum {_dec(d['set_effect'], 4)}, "
                f"Equip (apx.) {_int(d['equip_flat'], 2)}, "
                f"Other {_flag(d['other_present'])}"
            )
        lines.append("")

        # The stats below lead with their total followed by " <= "
        # (matching the ATK/DEF/HP format). Totals are padded to width 5.
        # The total is the sum of the named components, which reconciles
        # with calculate_build_stats' value for that stat.
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
        lines.append("")  # blank line before Ego
        eg = bd["Ego"]
        eg_total = eg["mf_main"] + eg["mf_sub"] + eg["set_effect"] + eg["other"]
        lines.append(
            f"Ego: {eg_total:>4.0f} <= MF Main {_int(eg['mf_main'], 3)}"
            f" + MF Sub Sum {_int(eg['mf_sub'], 3)}"
            f" + Set Effect Sum {_int(eg['set_effect'], 3)}"
            f" + Other {_other_int(eg['other'], 3)}"
        )
        lines.append("")
        lines.append(f"xDMG%: {_dec(bd['xDMG%'], 4)}")
        lines.append(f"+DMG%: {_dec(bd['+DMG%'], 4)}")
        # "Potential 7" ATK/DEF/HP -- the inner values used by the
        # Have-at-least minimum check: Partner flat class stats count,
        # Partner passives and Equipment don't. No blank lines between
        # the three rows, and an
        # explanatory note directly below. "HP " gets a trailing space so
        # its colon lines up with ATK:/DEF:.
        lines.append("")
        lines.append("")
        lines.append(
            "Note: For Potential 7, stats are calculated without "
            "Partner passives, Equipment, and Conditional Sets "
            "(Partner flat stats still count)."
        )
        lines.append("")
        lines.append(f"Pot7 ATK: {bd['ATK']['inner']:>4.0f}")
        lines.append(f"Pot7 DEF: {bd['DEF']['inner']:>4.0f}")
        lines.append(f"Pot7 HP : {bd['HP']['inner']:>4.0f}")
        lines.append("")
        # Potential 7 CRate/CDMG: the final value minus everything the
        # in-game Potential 7 checks can't see -- conditional set
        # contributions and ALL partner contributions (unconditional
        # set bonuses stay in). Mirrors the Have-at-least gate's
        # _hal_crate/_hal_cdmg. "CDMG " gets a trailing space so its
        # colon lines up with CRate's.
        lines.append(
            f"Pot7 CritRate: {cr_total - cr.get('pot7_excluded', 0.0):>5.1f}"
        )
        lines.append(
            f"Pot7 CritDMG%: {cd_total - cd.get('pot7_excluded', 0.0):>5.1f}"
        )
        # Potential 7 Extra DMG% / DoT% / Ego: the final value minus
        # partner passive contributions (no conditional-set path feeds
        # these stats). Same Totals ordering and label style as the
        # rows above; labels padded so the colons align within the trio.
        ex_p7 = ex_total - ex.get("pot7_excluded", 0.0)
        dt_p7 = dt_total - dt.get("pot7_excluded", 0.0)
        eg_p7 = eg_total - eg.get("pot7_excluded", 0.0)
        lines.append(f"Pot7 ExtrDMG%: {ex_p7:>5.1f}")
        lines.append(f"Pot7 DoT DMG%: {dt_p7:>5.1f}")
        lines.append("")
        lines.append(f"Pot7 Ego: {eg_p7:>4.0f}")
        return "\n".join(lines)

    def _show_text_popup(self, title: str, text: str):
        """Show `text` in a resizable Toplevel with a monospace Text widget,
        sized so each line fits without wrapping. The 200-char width cap
        keeps the wider ATK/DEF/HP lines (including Set Effect Sum) on one
        line."""
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=self.colors["bg"])
        top.transient(self.root)

        lines = text.split("\n")
        max_width = max((len(l) for l in lines), default=40)

        # spacing: out of scope -- a popup window, deferred like the modal
        # dialogs and the Materials and About tabs.
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

        ttk.Button(top, text="Close", width=BUTTON_W_SMALL,
                   command=top.destroy).pack(pady=(0, 8))

    def _populate_stats_compare(self, current_stats: dict, new_stats: Optional[dict]):
        self.stats_tree.delete(*self.stats_tree.get_children())
        # Single "Totals" section covering base stats, Crit, Element%,
        # Extra%, DoT%, and Ego. Each row tuple carries (internal_key,
        # decimals, display_label): internal_key is used for stats.get()
        # lookup, display_label is what the user sees (None means "use
        # internal_key as the label"). Rows are never skipped at zero --
        # every configured stat is shown.
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
            # Blank separator then the Potential-7 values: inner
            # ATK/DEF/HP (Partner flat counts; Partner passives and
            # Equipment don't), the crit values without conditional
            # sets or partner passive contributions, and Extra%/DoT%/Ego
            # without partner passive contributions -- same as the
            # popup's "Potential 7" rows and the Have-at-least check.
            ("", None, None),  # blank separator row
            ("_inner_atk", 0, "Pot7 ATK"),
            ("_inner_def", 0, "Pot7 DEF"),
            ("_inner_hp",  0, "Pot7 HP"),
            ("_hal_crate", 1, "Pot7 Crit%"),
            ("_hal_cdmg",  1, "Pot7 CDMG"),
            ("_hal_extra", 1, "Pot7 Extra%"),
            ("_hal_dot",   1, "Pot7 DoT%"),
            ("_hal_ego",   0, "Pot7 Ego"),
        ]
        # Size the visible height to the actual row count -- the tree's
        # build-time height predates the Pot7 crit rows, which otherwise
        # sit hidden behind a scroll. Doing it here keeps the height
        # self-maintaining if rows are added or removed later.
        self.stats_tree.configure(height=len(stat_order))
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
        # The detail tree shows GS through the lens of the CURRENT
        # CHARACTER's assigned preset (Combatants tab assignment), not the
        # globally-active Scoring tab preset. So we don't read
        # fragment.gear_score / potential_low/high (those are cached
        # against the active preset) -- we recompute with the character's
        # weights and a per-fragment bounds cache.
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
        # Collect the current snapshot's MF ids so the Owner column can
        # show "(deleted)" for any cached gear ref that no longer exists
        # in optimizer.fragments. The kept (stale) MF still renders its
        # last-known slot/set/main/subs -- only the Owner column changes --
        # so the user can still see WHAT used to be in that slot.
        current_ids = {getattr(f, "id", None) for f in self.optimizer.fragments}
        for p in sorted(gear, key=lambda x: x.slot_num):
            b = _bounds(p)
            gs = compute_fragment_gs(p, weights, bounds=b)
            pot_low, pot_high = compute_fragment_potential(p, weights, bounds=b)

            # Stat names are translated through DISPLAY_NAMES so the
            # user-facing label uses the new terminology (e.g. "ATK Flat"
            # instead of "Flat ATK", "Crit%" instead of "CRate"). The
            # internal stat.name is unchanged -- this is purely a display
            # translation at the point of rendering.
            subs = []
            for s in p.substats[:4]:
                sub_label = DISPLAY_NAMES.get(s.name, s.name)
                subs.append(f"{sub_label} {s.format_value()}")
            while len(subs) < 4:
                subs.append("-")
            if p.main_stat:
                main_label = DISPLAY_NAMES.get(p.main_stat.name, p.main_stat.name)
                main_str = f"{main_label} {p.main_stat.format_value()}"
            else:
                main_str = "-"
            # The GS column shows the current GS when the MF is at max
            # level (no upgrade headroom -> pot_low == pot_high), or the
            # Potential range (low-high) when it can still be leveled.
            if pot_low == pot_high:
                gs_cell = f"{gs:.0f}"
            else:
                gs_cell = f"{pot_low:.0f}-{pot_high:.0f}"
            # Mark MFs that no longer exist in the snapshot.
            if getattr(p, "id", None) not in current_ids:
                owner = "(deleted)"
            else:
                owner = p.equipped_to or ""
            self.detail_tree.insert("", tk.END, values=(
                p.slot_name,
                p.set_name, main_str, f"{p.level}", *subs,
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
        # Always refresh the Stats Comparison tree on character
        # switch -- even when the character has no Memory Fragments
        # equipped. calculate_build_stats handles an empty gear list (returns
        # base + partner + affection + equipment stats); without this call,
        # the stats_tree retained the PREVIOUSLY-selected character's stats
        # when the new character had no gear.
        self.show_current_stats(char)
        # Refresh the Preset label below the combobox.
        self._update_preset_label()
        # Refresh the exclude checklist so the previously-selected
        # character's gray+strike treatment is removed and the newly-
        # selected character's is applied. refresh_exclude_heroes has a
        # skip-if-unchanged guard, so calling it on every selection is
        # cheap when only the visual current-char marker changed.
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

    def _clamp_on_commit(self, spin, var):
        """Hold `var` inside the spinbox's own range once typing stops.

        **A `tk.Spinbox`'s `from_`/`to` bound its BUTTONS and its wheel,
        not its text.** Typed input reaches the variable unchecked in
        both directions -- 500 and -7 both arrive intact through a
        `from_=0, to=100` spinbox -- so the floor needs this as much as
        the ceiling does.

        The bounds are READ OFF THE WIDGET rather than passed in, so
        each spinbox declares its own range once and this enforces what
        it declared. A field that should accept negatives says so with
        its `from_`.

        On commit rather than per keystroke: mid-edit the field passes
        through states that are not numbers at all -- empty after a
        select-all, a lone minus sign -- and a per-stroke clamp would
        spend most of its life fighting them.

        The variable is what gets held, not the saved value. Clamping
        only on the way out would leave the field reading 500 while the
        optimizer used 100.
        """
        state = {}
        try:
            state["good"] = var.get()
        except tk.TclError:
            state["good"] = spin.cget("from")

        def commit(_event=None):
            self._commit_clamp(spin, var, state)
        spin.bind("<FocusOut>", commit, add="+")
        spin.bind("<Return>", commit, add="+")

    def _commit_clamp(self, spin, var, state=None):
        """Hold `var` inside `spin`'s range, blinking it if it moved.

        A method rather than the closure above so it can be CALLED. Tk
        will not deliver a key event to an unmapped widget, so nothing
        headless can press Return into a spinbox -- which would leave the
        whole clamp untestable without the maintainer at the keyboard.
        `checks/check_tabs_build.py` calls this instead.

        `state` carries the last value that WAS a number. Text that is
        not one cannot be clamped toward anything, so the field goes
        back to what it last held rather than to a bound -- which for a
        field the user has not otherwise touched is the saved value.

        Returns whether it changed anything.
        """
        lo, hi = float(spin.cget("from")), float(spin.cget("to"))
        try:
            value = var.get()
        except tk.TclError:
            if state is None:
                return False
            var.set(state["good"])
            self._blink(spin)
            return True
        held = type(value)(min(max(value, lo), hi))
        if state is not None:
            state["good"] = held
        if held == value:
            return False
        var.set(held)
        self._blink(spin)
        return True

    # A clamp that snapped silently would read as the number being
    # accepted. Three quick flashes behind the value say it moved.
    #
    # Its own red, not the palette's: `red` is a foreground, chosen to
    # read as text against the dark background, and a field filled with
    # it puts the value it is about invisibly on top. This one is dark
    # enough to keep the digits legible while it flashes.
    CLAMP_ALERT = "#9b0f1b"
    CLAMP_BLINK_MS = 110
    CLAMP_BLINKS = 3

    def _blink(self, widget):
        """Flash a widget's background between the alert colour and its
        own, ending on its own."""
        normal = self.colors["bg_light"]
        alert = self.CLAMP_ALERT
        last = self.CLAMP_BLINKS * 2 - 1

        def step(n):
            try:
                widget.config(bg=alert if n % 2 == 0 else normal)
            except tk.TclError:
                return                   # the tab went away mid-blink
            if n < last:
                self.root.after(self.CLAMP_BLINK_MS, step, n + 1)

        step(0)

    def _scale_wheel(self, event, var, on_change=None, lo=0, hi=100):
        """Step a ttk.Scale's IntVar by exactly +-1 on mouse wheel.

        Guarantees every integer 0-100 is reachable regardless of the
        rendered track length (dragging can't land on all values when
        the track's pixel travel is shorter than the value range).
        on_change(int) is invoked on an actual change so persistence
        fires -- setting the var directly does NOT trigger the Scale's
        command= callback.
        """
        step = 1 if event.delta > 0 else -1
        try:
            cur = int(var.get())
        except tk.TclError:
            return "break"
        new = max(lo, min(hi, cur + step))
        if new != cur:
            var.set(new)
            if on_change:
                on_change(new)
        return "break"

    def _hal_pct_wheel(self, event, var):
        """+-0.1 mouse-wheel steps for the %-valued "Have at least"
        spinboxes (the spinbox buttons keep stepping by 1). Rounded to
        one decimal and floored at 0; persistence fires via the var's
        write-trace."""
        step = 0.1 if event.delta > 0 else -0.1
        try:
            cur = float(var.get())
        except tk.TclError:
            return "break"
        var.set(round(max(0.0, cur + step), 1))
        return "break"
