"""Combatants tab: sortable combatant list plus a gear detail pane.

Where to look when changing X
=============================

- **The row list** — `refresh_heroes()` rebuilds from
  `optimizer.character_info`, applies the sort and restores the
  selection.
- **Whether a live update rebuilds this tab** — `display_signature()`,
  taken either side of a snapshot reload and compared. **Extend it
  whenever a new field reaches the rows or the detail pane**, or that
  field goes stale in silence.
- **Selection and keyboard** — the list is a `ttk.Treeview`, so
  selection, Up/Down and scrolling are its own. `_on_tree_select` drives
  the detail pane; `_on_hero_list_key` adds letter-jump. A row's iid is
  its index into `hero_data_list`.
- **Row colour** — one TAG per Element, set on the row. A Treeview
  colours a ROW, never a cell, so the Element colour runs the full
  width.
- **The detail pane** — `show_hero_details()`: character card (ONE Text
  widget holding details, the Sets line and the build-stat block),
  partner card, equipped MFs frame.
- **Equipped MF cells** — one Text widget each, drawn by
  `_render_gear_cell`. Columns are the `toprow` / `subrow` tags' tab
  stops (`GEAR_TAB_*`); colours are tags. Every widget in the pane
  repaints on every selection, so one widget per cell rather than eleven
  is what keeps moving through the list smooth.
- **Build stats** — `HERO_STAT_ROWS` / `HERO_STAT_DISPLAY` set the two
  columns, laid out on the Text widget's tab stops.
  `_format_stats_text` builds the block, `_format_sets_text` the Sets
  line. Both the display and `_compute_and_apply_fixed_sizes` read them,
  so a new row is picked up by the sizing pass automatically.
- **Per-piece GS** — `compute_fragment_gs()` with the PER-CHARACTER
  preset's weights, not the globally applied ones. The list's GS column
  does the same; **the two must agree.**
- **Preset assignment** — `_get_assigned_preset` /
  `_weights_for_preset` / `_refresh_preset_dropdown_values`.
- **Set name colour** — counts equipped pieces of the same set against
  the set's requirement: white if complete, dim grey if partial.

Partner card has three states: known partner → full card; unknown res_id
→ full card named "Unknown (res_id X)"; `partner_id` with no name →
"Unknown partner (res_id X)" line; none → "None".

Conventions
===========

- `hero_data_list` entries carry name, display fields, `res_id` and
  `exp`. The last two come from `CharacterInfo` and drive the
  right-click level-checkpoint flow.
- **`DEFAULT_PRESET_LABEL` is a UI string only, never persisted.**
  `CharacterPresetManager` stores `None` for "use default"; the
  translation happens at the dropdown boundary.
"""

import time
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from typing import Optional

import perf_log

from ui.base_tab import BaseTab
from ui.context import AppContext
from ui.utils.tooltip import Tooltip
from ui.utils.combobox_nav import (
    combobox_letter_jump, combobox_arrow_nav, bind_popdown_seek,
)
from game_data import (
    EQUIPMENT_SLOTS, SETS, STATS, RARITY_COLORS, RARITY_BG_COLORS,
    RARITY_STARTING_SUBSTATS, ATTRIBUTE_COLORS,
    get_character_by_name, get_partner, get_partner_stats,
    get_partner_passive_info
)
from models import Stat
from models.memory_fragment import compute_gs_bounds, normalize_gs


# UI label shown when a character has no preset assigned (default 1.0 weights).
DEFAULT_PRESET_LABEL = "Default Preset (all weights are 1.0)"



# Build-stat rows under the Character card: (left column key, right
# column key). None leaves that half of the row empty -- Element has no
# left-hand partner. Laid out on the Text widget's tab stops rather than
# by padding the text, so the two value columns align in a proportional
# font.
HERO_STAT_ROWS = [
    ("ATK", "CRate"),
    ("DEF", "CDmg"),
    ("HP", "Extra DMG%"),
    ("Ego", "DoT%"),
    (None, "Element"),
]

# Stat key -> the label shown for it. "Element" isn't a calculate_build_stats
# key; it's the summed matching-element DMG% mains, computed in
# show_hero_details.
HERO_STAT_DISPLAY = {
    "ATK": "ATK", "DEF": "DEF", "HP": "HP", "Ego": "Ego",
    "CRate": "Crit%", "CDmg": "CDMG", "Extra DMG%": "Extra%",
    "DoT%": "DoT%", "Element": "Element",
}

# The widest value each STAT will ever hold, as the string itself.
#
# Per stat, not per column, because the column's edge is placed at
# `max(label + 4 + value)` taken row by row -- so a row pairing a wide
# label with a narrow value costs nothing. `Element` is the widest label
# in the block and would drag the whole column right if the two were
# maxed separately.
#
# Strings rather than character counts: Segoe UI's digits are tabular, so
# a count is exact for digits alone, but `.` and `%` are not digit-width
# and the right column carries both.
#
# Stated rather than measured from the loaded data, so the columns do not
# jitter between combatants. A value that outgrows its entry clips rather
# than pushing the column, so widen it here if one ever does.
HERO_STAT_VALUE_MAXIMA = {
    "ATK": "9999", "DEF": "9999", "HP": "9999", "Ego": "999",
    "CRate": "99.9%", "CDmg": "999.9%", "Extra DMG%": "99.9%",
    "DoT%": "99.9%", "Element": "99.9%",
}

# Fixed size of one Equipped Memory Fragments cell. Stated rather than
# derived: deriving it meant estimating the LabelFrame overhead, the wrap
# width and the line count separately, and the three estimates disagreed.
# Calibrated against the longest set description currently in the game --
# a longer one clips rather than growing the cell.
GEAR_CELL_W = 401
GEAR_CELL_H = 163

# How far the set-description text wraps short of the cell's own width.
# Raise it to pull the wrap in, lower it to let the text run wider. The
# cell is a fixed size, so this is the only thing that moves the wrap.
GEAR_SET_WRAP_INSET = 6

# Tab stops inside a gear cell, in pixels from the text's left edge. The
# cell is one Text widget, so its columns are tab stops rather than
# packed frames, and these are the only levers on them.
# spacing: TBD -- gear cell column
GEAR_TAB_GS = 196        # centre stop: GS and Potential, between the ends
GEAR_TAB_SLOT = 385      # right stop: the slot name and its level
GEAR_TAB_QUALITY = 20    # right stop: a substat's roll-quality percent
GEAR_TAB_SUB = 26        # left stop: where the substat text starts

# What separates GS from Potential on a cell's top row. A Text has no
# letter-spacing, so the only lever inside a line is the space glyph --
# 3px of advance each in Segoe UI 9, which is why this is a string and
# not a pixel count.
# spacing: element and its label ↔ element and its label
GEAR_GS_POT_GAP = "  "

# Width the Character panel gives up to the Partner panel beside it.
# They share a row, so what one does not take, the other gets.
CHAR_WIDTH_CEDED = 19

# Lines the Character panel always reserves under each heading, filled
# with blanks when there is less to say, so its height is the same for
# every combatant.
#
# Six slots hold at most three 2-piece sets, or two sets plus a Flex
# token -- three lines either way.
CHAR_SETS_LINES = 3
# One per potential node the program tracks. Nodes 5 and 6 are the two
# carrying stats; the rest are parsed and dropped (see
# docs/game_formulas.md "The potential tree"), so listing them here waits
# on them being stored.
CHAR_POTENTIAL_LINES = 2
# Shared by the set names and the potential nodes, so the two blocks read
# as the same kind of list.
CHAR_SUBLIST_INDENT = "  "

# The widest line the details block renders: the Affinity BONUS line,
# `  Bonus: ATK+39, DEF+12, HP+36`, at 175px. The combatant's NAME is not
# in this panel at all -- it is the heading above -- so nothing here
# scales with it.
#
# Two traps, both of which have caught a reader already. The widest by
# CHARACTER COUNT and the widest in PIXELS are different strings, and the
# pixel one is what matters. And the obvious candidate is not the widest:
# the Grade / element / class line tops out at 156px, well short of the
# bonus figures, which grow with Affinity level.
#
# Re-measure rather than reason: format every combatant's card and take
# max(measure(line)).
CHAR_CONTENT_PX = 180
# Details block + "Sets:" + its lines + "Stats:" + one per stat row.
CHAR_TOTAL_LINES = 8 + 1 + CHAR_SETS_LINES + 1 + 5

# Character-list column widths, in PIXELS. A tk.Label's `width` counts
# CHARACTERS, which is only a width in a monospaced font -- these are
# applied as the Treeview's column widths.
#
# **Every number here is a FLOOR, not a width.** A grid column ends up at
#
#     max(this number, the bold header's width, the widest cell's width)
#
# so LOWERING one below its content changes nothing on screen -- the
# label still asks for room for its text and the column still grants it.
# Raising one always works. To go narrower than the content, the content
# has to be truncated; nothing here will do it.
#
# Each is currently the wider of its bold header and its widest real
# value, plus a little room -- measured, not guessed.
#
# Preset is last and stretches, so its number is a minimum in the other
# sense as well: it also takes the leftover width.
HERO_COL_PX = [65, 35, 54, 54, 30, 23, 42, 24, 64, 30, 180]

# Treeview column ids, and the heading each shows. The id IS the sort
# key, so a heading click needs no lookup table.
HERO_COL_IDS = ("name", "grade", "attribute", "class", "level",
                "ego", "affinity", "gs", "partner", "partner_level",
                "preset")
HERO_COL_TITLES = ("Combatant", "Grade", "Attribute", "Class", "Level",
                   "Ego", "Affinity", "GS", "Partner", "Level", "Preset")

# Tag for a row whose Element the program does not know, so it still gets
# an explicit foreground rather than inheriting the theme's.
HERO_TAG_UNKNOWN = "_unknown_element"


def _padded_sublist(tokens):
    """Indented lines, one per token, padded to CHAR_SETS_LINES.

    Every path through the Sets block comes here, the empty one included
    -- an early `return "None"` skipped both the indent and the padding,
    so an ungeared combatant's panel was a different shape from everyone
    else's.
    """
    lines = [CHAR_SUBLIST_INDENT + t for t in tokens[:CHAR_SETS_LINES]]
    lines += [""] * (CHAR_SETS_LINES - len(lines))
    return "\n".join(lines)


def _default_font():
    """TkDefaultFont, or an explicit equivalent when it isn't registered.

    The Character card's Text widget and the fixed-size computation must
    use the SAME font: the computation derives the card's width and its
    tab stops from font metrics, and a mismatch would put the columns
    somewhere other than where they were measured.
    """
    try:
        return tkfont.nametofont("TkDefaultFont")
    except Exception:
        return tkfont.Font(family="Segoe UI", size=9)




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
        # Time every refresh_heroes call into settings/perf_log.txt. Wrapping
        # the bound method here rather than editing the method body keeps the
        # measurement in one place and catches every caller (data load,
        # live capture update, preset change, Restore Defaults).
        import perf_log
        self.refresh_heroes = perf_log.timed("refresh_heroes",
                                             self.refresh_heroes)

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
        self.hero_tree = None
        self.hero_data_list = []
        self.hero_col_char_widths = None
        self.selected_hero_index = -1

        # Detail widgets (set in setup_ui)
        self.user_info_label = None
        self.hero_detail_name = None
        self.hero_char_text = None
        self.hero_partner_text = None
        # slot number -> the one Text widget that draws that cell
        self.gear_cells = {}

    def setup_ui(self):
        """Setup the Heroes tab UI."""
        # Shared by every substat roll-quality figure in the gear cells.
        self._gear_tooltip = Tooltip(self.colors)
        # Two independent vertical stacks, one per column, rather than a
        # full-width header above a full-width content pane. A shared
        # header row would hold the character list down to the TALLER of
        # the two headers -- the right column's name + preset dropdown --
        # even though the left one is a single line. Stacking per column
        # lets the list rise under the user info label on its own.
        columns = ttk.Frame(self.frame)
        # spacing: content frame -> content frame
        # spacing: tab list -> first element
        columns.pack(fill=tk.BOTH, expand=True, padx=2, pady=(1, 2))
        # The 6:8 weight split gives the left character-list column ~43%
        # of the content width (widened to fit the Partner column). Tk grid
        # weights are proportional, so the exact pixel split tracks the
        # window size.
        columns.grid_columnconfigure(0, weight=6)
        columns.grid_columnconfigure(1, weight=8)
        columns.grid_rowconfigure(0, weight=1)

        left_column = ttk.Frame(columns)
        left_column.grid(row=0, column=0, sticky="nsew")
        right_column = ttk.Frame(columns)
        right_column.grid(row=0, column=1, sticky="nsew")

        # Col 0 header: user info label
        user_info_subframe = ttk.Frame(left_column)
        user_info_subframe.pack(fill=tk.X)
        # spacing: tab list -> first element
        # ttk.Label, not tk.Label: this needs negative padding to cancel
        # the font's internal offset (see docs/ui_spacing.md
        # "The rules"), and tk.Label's pady clamps at 0 so it can barely
        # give anything back. The ttk default background already matches
        # colors["bg"], so the appearance is unchanged.
        self.user_info_label = ttk.Label(
            user_info_subframe,
            text="No data loaded",
            font=("Segoe UI", 9),
            foreground=self.colors["fg"],
            padding=(0, 0, 0, 0),
            anchor="w"
        )
        # anchor=NW pins it to the top-left of the subframe so it stays
        # aligned with the title group on the right (which is taller --
        # 2 lines for the preset label + combo).
        self.user_info_label.pack(side=tk.LEFT, anchor=tk.NW)

        # Col 1 header: Combatant name + preset dropdown.
        title_row = ttk.Frame(right_column)
        # spacing: content frame -> content frame
        title_row.pack(fill=tk.X, padx=(4, 0))

        # spacing: header subtext
        # padding cancels the 14pt font's internal leading -- same
        # correction as the other tabs' headings.
        self.hero_detail_name = ttk.Label(
            title_row, text="Select a combatant", padding=(0, -3, 0, -2),
            font=("Segoe UI", 14, "bold")
        )
        self.hero_detail_name.pack(side=tk.LEFT, anchor=tk.NW)

        # Right-aligned vertical group: label on top, combobox below.
        # `expand=True, fill=X` fills the leftover space between the name
        # and title_row's right edge.
        preset_group = ttk.Frame(title_row)
        # spacing: TBD -- heading -> the control group beside it
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
        # Letter-key navigation on the preset assignment dropdown.
        # KeyRelease + add="+" so readonly Combobox's internal handler
        # doesn't pre-empt the user binding (some Tk versions don't fire
        # KeyPress to user bindings on readonly state).
        self.preset_assign_combo.bind(
            "<KeyRelease>",
            lambda e: combobox_letter_jump(e, self.preset_assign_combo),
            add="+",
        )
        # Arrow keys step through presets in place instead of opening the
        # dropdown popup (matches the Combatant dropdown in the Optimizer
        # tab).
        self.preset_assign_combo.bind(
            "<Down>",
            lambda e: combobox_arrow_nav(e, self.preset_assign_combo, +1),
        )
        self.preset_assign_combo.bind(
            "<Up>",
            lambda e: combobox_arrow_nav(e, self.preset_assign_combo, -1),
        )
        # Type-ahead seek inside the OPEN dropdown list.
        bind_popdown_seek(self.preset_assign_combo)

        # Fix the dropdown width to match the label above it, sized for
        # the longest expected combatant name ("Heidemarie"). Uses
        # TkDefaultFont metrics -> char count; the pack fill is dropped so the
        # explicit width sticks (the height popup logic in
        # _recompute_combo_geometry only touches `height`, never `width`).
        try:
            _f = tkfont.nametofont("TkDefaultFont")
            _sample = "Assign preset to Heidemarie for custom Gear Score:"
            _char_px = max(1, _f.measure("0"))
            _chars = max(10, round(_f.measure(_sample) / _char_px) - 1)
            self.preset_assign_combo.configure(width=_chars)
            self.preset_assign_combo.pack_configure(fill=tk.NONE)
        except Exception:
            pass

        # Internal: name of the character whose row is currently selected
        # (used by the combobox change handler to know who to assign to).
        self._current_detail_hero = None

        # Left: Hero list.
        hero_list_container = ttk.Frame(left_column)
        # spacing: content frame -> content frame
        # The top pad is larger than the sides because it stands in for
        # what three nesting levels contribute on the other columns; this
        # one has fewer levels above it. The bottom pad is the tab's own
        # bottom margin, shared with the container below.
        hero_list_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=(6, 2))

        # The character list is a Treeview: ONE widget that draws its own
        # rows, where the hand-rolled version was a label per cell -- 374
        # widgets that Tk re-laid-out on every window resize, which is what
        # made this tab drag. Pixel columns, sorting, selection, scrolling
        # and keyboard navigation all come with it.
        #
        # The cost is that a Treeview colours a ROW, never a single cell:
        # a tag's foreground covers the whole row, so the Element colour
        # runs the full width rather than sitting on the Attribute cell.
        hero_tree_frame = ttk.Frame(hero_list_container)
        hero_tree_frame.pack(fill=tk.BOTH, expand=True)

        self.hero_tree = ttk.Treeview(
            hero_tree_frame, columns=HERO_COL_IDS, show="headings",
            selectmode="browse",
        )
        hero_vsb = ttk.Scrollbar(hero_tree_frame, orient=tk.VERTICAL,
                                 command=self.hero_tree.yview)
        self.hero_tree.configure(yscrollcommand=hero_vsb.set)
        self.hero_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hero_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        for col_id, title, width_px in zip(
                HERO_COL_IDS, HERO_COL_TITLES, HERO_COL_PX):
            # Left-align Combatant, Partner and Preset; centre the rest.
            # The second "Level" is the PARTNER's -- it follows the Partner
            # column, which is what disambiguates it.
            anchor = (tk.W if col_id in ("name", "partner", "preset")
                      else tk.CENTER)
            self.hero_tree.heading(
                col_id, text=title, anchor=anchor,
                command=lambda k=col_id: self.sort_heroes(k))
            # Preset takes the leftover width; every other column is fixed.
            self.hero_tree.column(
                col_id, width=width_px, minwidth=width_px, anchor=anchor,
                stretch=(col_id == "preset"))

        # One tag per Element, plus a fallback. Rows carry the tag for
        # their own Element, which is what colours them.
        for element, colour in ATTRIBUTE_COLORS.items():
            self.hero_tree.tag_configure(element, foreground=colour)
        self.hero_tree.tag_configure(
            HERO_TAG_UNKNOWN, foreground=self.colors["fg"])

        self.hero_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        # Windows-Explorer-style letter-jump: press a letter to select the
        # next combatant whose name starts with it. Up/Down come free with
        # the Treeview.
        self.hero_tree.bind("<KeyPress>", self._on_hero_list_key)

        # Right: Hero details
        hero_detail_container = ttk.Frame(right_column)
        # spacing: content frame -> content frame
        hero_detail_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=(6, 2))
        self.hero_detail_container = hero_detail_container  # for width-clamp lookups

        # Debounce handle for resize-triggered combobox geometry recompute.
        # The combobox itself lives in the right column's title_row, but the
        # <Configure> binding stays on hero_detail_container because that's
        # the panel whose width drives the combobox's target geometry (they
        # share content_pane's weight=8 column).
        self._combo_resize_after_id = None
        hero_detail_container.bind("<Configure>", self._on_detail_resize)

        # Info frame with Character and Partner Card
        # Character takes only needed space, Partner Card fills remaining with text wrapping
        info_frame = ttk.Frame(hero_detail_container)
        # info_frame absorbs the vertical excess space in the detail panel
        # (fill=BOTH, expand=True), so the Equipped MF frame below it sits
        # at the BOTTOM of the cavity instead of floating mid-panel with
        # empty space below. The Character / Partner frames inside
        # info_frame get pack_configure'd to fill=Y / fill=BOTH down in
        # _compute_and_apply_fixed_sizes so they grow with it.
        # spacing: content frame -> content frame
        info_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        # No frame padding: the text inset lives on the Text's own
        # padx/pady, so its lighter background reaches the frame border --
        # the same construction as the Partner frame below.
        char_frame = ttk.LabelFrame(info_frame, text="Character", padding=0)
        # spacing: content frame -> content frame
        # Leading 0, not 2: this panel's left edge already carries
        # hero_detail_container's 2 plus the LabelFrame's own border, which
        # together overshot the rule. The trailing half is untouched, so
        # the gap to the Partner panel beside it is unchanged.
        char_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 2))
        self._char_frame = char_frame  # fixed-size target

        # ONE Text widget holds the whole card: the character details, the
        # Sets line, and the two-column build-stat block. The stat columns
        # line up on tab stops rather than in a grid -- the stops are set
        # from font metrics in _compute_and_apply_fixed_sizes, because a
        # Text widget has no columns of its own to align to.
        #
        # No scrollbar, unlike Partner: this card's content is a fixed
        # number of lines and the frame is sized to hold them, where
        # Partner's passive/ego prose has no bound. The widget packs
        # straight into the LabelFrame for the same reason -- there is
        # nothing to sit beside it.
        # spacing: frame edge -> first non-button element
        # The panel's inset sits here rather than on the LabelFrame,
        # inside the text widget's own lighter background. The pady has
        # the line box's leading above the first glyph netted out of it,
        # which is why it differs between text panels in different fonts.
        # wrap=NONE: every line here is sized to fit -- the stat block is
        # tab-stopped to measured columns and the Sets line is wrapped by
        # the width computation -- so a wrap would only ever fire on
        # something that had already gone wrong, and hide it.
        self.hero_char_text = tk.Text(
            char_frame, wrap=tk.NONE, height=6,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            font=_default_font(), bd=0, highlightthickness=0,
            padx=6, pady=3,
        )
        self.hero_char_text.pack(fill=tk.BOTH, expand=True)
        self.hero_char_text.config(state=tk.DISABLED)

        # No frame padding: the text inset lives on the Text's own
        # padx/pady, so its lighter background reaches the frame border.
        partner_frame = ttk.LabelFrame(info_frame, text="Partner", padding=0)
        # spacing: content frame -> content frame
        partner_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self._partner_frame = partner_frame  # fixed-size target
        # Right-click on the partner pane (the LabelFrame OR the Text widget
        # inside) opens the "Add confirmed level" dialog for the currently
        # equipped partner. Same flow as for characters; the partner res_id
        # and exp come from char_info.partner_res_id / char_info.partner_exp,
        # populated by the optimizer when the snapshot is parsed.
        # Use a Text widget for the Partner pane (allows proper word-wrap of
        # the multi-line description). Wrap it in a sub-frame alongside a
        # vertical Scrollbar so long descriptions get an actual visible
        # scrollbar — the Text widget alone doesn't show one.
        partner_text_frame = ttk.Frame(partner_frame)
        partner_text_frame.pack(fill=tk.BOTH, expand=True)

        partner_scroll = ttk.Scrollbar(partner_text_frame, orient=tk.VERTICAL)
        # spacing: frame edge -> first non-button element
        # The panel's inset sits here rather than on the LabelFrame,
        # inside the text widget's own lighter background. The pady has
        # the line box's leading above the first glyph netted out of it,
        # which is why it differs between text panels in different fonts.
        self.hero_partner_text = tk.Text(
            partner_text_frame, wrap=tk.WORD, height=6,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            font=("Segoe UI", 9), bd=0, highlightthickness=0,
            padx=6, pady=3,
            yscrollcommand=partner_scroll.set,
        )
        partner_scroll.config(command=self.hero_partner_text.yview)
        partner_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.hero_partner_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.hero_partner_text.config(state=tk.DISABLED)
        # Right-click on the Text widget (where the partner description
        # actually renders) routes to the same handler as the parent frame.

        gear_outer_frame = ttk.LabelFrame(
            hero_detail_container, text="Equipped Memory Fragments", padding=0,
            style="Gear.Borderless.TLabelframe")
        # spacing: content frame -> content frame
        # The bottom pad is 0: this frame is the last thing in the detail
        # column, so anything here would stack on hero_detail_container's
        # own bottom pad and lift the panel above the character list
        # beside it, whose canvas sits flush against the container edge.
        gear_outer_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        self._gear_outer_frame = gear_outer_frame  # fixed-size target

        self.gear_cells = {}

        gear_grid = ttk.Frame(gear_outer_frame)
        gear_grid.pack(fill=tk.BOTH, expand=True)

        # Slot positions matching original: (slot_num, row, col)
        slot_positions = [
            (3, 0, 0), (4, 0, 1),
            (2, 1, 0), (5, 1, 1),
            (1, 2, 0), (6, 2, 1),
        ]

        for slot_num, row, col in slot_positions:
            # ONE Text per cell, where this was eleven widgets: a frame,
            # three inner frames, six labels and a Text per substat. Every
            # one of them repainted on every selection, and the repaint --
            # not the work behind it -- is what made moving through the
            # combatant list stutter. Columns are tab stops now and the
            # colours are tags; the Character and Partner cards beside it
            # are built the same way.
            cell = tk.Text(
                gear_grid, font=("Segoe UI", 9), wrap=tk.WORD,
                bg=self.colors["bg_light"], fg=self.colors["fg"],
                relief=tk.RIDGE, bd=1, highlightthickness=0,
                # spacing: frame edge -> first non-button element
                # padx is symmetric, so it sets the LEFT inset and part of
                # the right one; GEAR_TAB_SLOT carries the rest.
                # spacing: text label row -> text label row
                # spacing3 is the gap BELOW each line, which is what
                # separates one row of the cell from the next. spacing1
                # would add to the top inset above instead.
                padx=5, pady=2, spacing3=4,
                # Selectable but never focusable, and no insertion cursor:
                # the text can be copied, and nothing about it invites
                # typing into it.
                takefocus=0, insertwidth=0, cursor="arrow",
            )
            # spacing: content frame -> content frame
            # padx is asymmetric on purpose: the LabelFrame title above
            # starts inset from the frame's left edge, so an even split
            # put the cells right of their own title. The trailing side
            # takes the difference back, leaving the gap BETWEEN columns
            # unchanged.
            # No pady BELOW the last row: a symmetric value there is
            # trailing space inside the frame, which left the bottom row
            # of cells short of the panel's bottom edge. Rows above keep
            # both halves, so the gap BETWEEN rows is unchanged.
            cell.grid(row=row, column=col, padx=(0, 4),
                      pady=(2, 2) if row < 2 else (2, 0), sticky="nsew")

            # Colours. `rarity` is the only one re-set per render -- it
            # carries the fragment's rarity, which the slot name and the
            # main stat both take.
            cell.tag_configure("rarity", font=("Segoe UI", 9, "bold"))
            cell.tag_configure("gs", foreground=self.colors["accent"],
                               font=("Segoe UI", 9, "bold"))
            cell.tag_configure("pot", foreground=self.colors["fg_dim"])
            cell.tag_configure("quality", foreground=self.colors["accent"])
            cell.tag_configure("default", foreground=self.colors["fg"])
            cell.tag_configure("added", foreground=self.colors["fg"])
            cell.tag_configure("max_roll", foreground=self.colors["green"])
            cell.tag_configure("min_roll", foreground=self.colors["red"])
            cell.tag_configure("normal", foreground=self.colors["yellow"])
            cell.tag_configure("set_live", foreground=self.colors["fg"])
            cell.tag_configure("set_dim", foreground=self.colors["fg_dim"])

            # Columns. A right-aligned stop sits at the END of its column.
            cell.tag_configure(
                "toprow",
                tabs=(GEAR_TAB_GS, "center", GEAR_TAB_SLOT, "right"))
            cell.tag_configure(
                "subrow",
                tabs=(GEAR_TAB_QUALITY, "right", GEAR_TAB_SUB, "left"))

            # Nothing in the UI says what the quality number is, and
            # "close to a Gear Score, beside a Gear Score" is the wrong
            # guess to leave available.
            self._gear_tooltip.bind_tag(
                cell, "quality",
                "How close to perfect this substat rolled (%). "
                "Not Gear Score.")

            cell.config(state=tk.DISABLED)
            self.gear_cells[slot_num] = cell

        gear_grid.columnconfigure(0, weight=1)
        gear_grid.columnconfigure(1, weight=1)
        gear_grid.rowconfigure(0, weight=1)
        gear_grid.rowconfigure(1, weight=1)
        gear_grid.rowconfigure(2, weight=1)

    # Public API
    def display_signature(self):
        """A cheap hashable summary of everything this tab renders.

        Compared across a snapshot reload to decide whether a rebuild is
        worth its cost: most live capture events (upgrading, forging or
        dismantling a fragment that nobody has equipped) change nothing
        here, and refresh_heroes is expensive -- it destroys and recreates
        every row's labels and re-measures the detail pane's fixed sizes.

        Covers the user line, every field of CharacterInfo the rows or the
        detail pane read, and the identity + level of each EQUIPPED
        fragment (a level is the only thing that changes a fragment's
        substats, and hence its Gear Score). Sorted, so a reordered
        `characters` payload doesn't read as a change.

        Anything not covered here goes stale silently, so callers treat a
        raised exception as "changed" and rebuild.
        """
        u = self.optimizer.user_info
        chars = sorted(
            (
                name, ci.res_id, ci.level, ci.max_level, ci.limit_break,
                ci.exp, ci.friendship_index,
                ci.potential_50_level, ci.potential_60_level,
                ci.partner_id, ci.partner_res_id, ci.partner_name,
                ci.partner_level, ci.partner_max_level,
                ci.partner_limit_break,
            )
            for name, ci in self.optimizer.character_info.items()
        )
        gear = sorted(
            (f.equipped_to, getattr(f, "id", 0) or 0, f.slot_num, f.level)
            for f in self.optimizer.fragments if f.equipped_to
        )
        return (
            (u.nickname, u.level, u.login_total, u.login_continuous,
             u.login_highest_continuous),
            tuple(chars),
            tuple(gear),
        )

    def refresh_heroes(self):
        """Refresh the heroes list."""
        # Clear existing rows. One call, where the hand-rolled list had
        # to destroy every label it had made.
        self.hero_tree.delete(*self.hero_tree.get_children())
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

            preset_name = self._get_assigned_preset(hero)
            gs = self._hero_gs(gear, preset_name)
            preset_display = "-" if preset_name is None else preset_name

            hero_data = get_character_by_name(hero)
            grade = hero_data.get("grade", 0)
            attribute = hero_data.get("attribute", "Unknown")
            hero_class = hero_data.get("class", "Unknown")

            if char_info:
                level = char_info.level
                max_level = char_info.max_level
                ego = char_info.limit_break
                affinity = char_info.friendship_index
                res_id = char_info.res_id
                exp = char_info.exp
                # Partner column: name + level. Unknown equipped partners
                # show "#res_id" (matching the detail card's fallback);
                # no partner -> "-". Pure attribute access on the already-
                # parsed CharacterInfo -- no table scans, so no caching
                # needed in this loop.
                if char_info.partner_id:
                    pname = char_info.partner_name
                    if not pname or pname == "Unknown":
                        pname = (f"#{char_info.partner_res_id}"
                                 if char_info.partner_res_id else "?")
                    partner_str = f"{pname} {char_info.partner_level}"
                    partner_name_part = pname
                    partner_level_part = str(char_info.partner_level)
                else:
                    partner_str = "-"
                    partner_name_part = "-"
                    partner_level_part = ""
            else:
                level = 0
                max_level = 0
                ego = 0
                affinity = 0
                res_id = 0
                exp = 0
                partner_str = "-"
                partner_name_part = "-"
                partner_level_part = ""

            self.hero_data_list.append({
                "name": hero,
                "grade": grade,
                "attribute": attribute,
                "class": hero_class,
                "level": level,
                "max_level": max_level,
                "ego": ego,
                "affinity": affinity,
                "gs": gs,
                "partner": partner_str,
                # Split parts for the two-label Partner cell (name left-
                # aligned, level right-aligned); "partner" above stays the
                # combined string for sorting.
                "partner_name_part": partner_name_part,
                "partner_level_part": partner_level_part,
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
            "affinity": lambda h: h["affinity"],
            "gs": lambda h: h["gs"],
            "partner": lambda h: h["partner_name_part"],
            "partner_level": lambda h: h["partner_level_part"],
            "preset": lambda h: h["preset"],
        }

        key_func = sort_key_map.get(self.hero_sort_col, lambda h: h["name"])
        self.hero_data_list.sort(key=key_func, reverse=self.hero_sort_reverse)

        # One insert per row. The row's iid is its index in
        # hero_data_list, so a selection maps back to its data with int().
        for i, h in enumerate(self.hero_data_list):
            level_str = str(h["level"]) if h["max_level"] > 0 else "-"
            ego_str = f"E{h['ego']}" if h['max_level'] > 0 else "-"
            gs_str = f"{h['gs']:.0f}" if h['gs'] > 0 else "-"
            affinity_str = (str(h["affinity"]) if h["max_level"] > 0 else "-")

            values = (h["name"], f"{h['grade']}*", h["attribute"], h["class"],
                      level_str, ego_str, affinity_str, gs_str,
                      h["partner_name_part"], h["partner_level_part"],
                      h["preset"])
            # The row's Element tag is what colours it. An Element the
            # program has no colour for falls back to the plain
            # foreground rather than the theme's default.
            tag = (h["attribute"] if h["attribute"] in ATTRIBUTE_COLORS
                   else HERO_TAG_UNKNOWN)
            self.hero_tree.insert("", tk.END, iid=str(i), values=values,
                                  tags=(tag,))

        if self.hero_data_list:
            self.select_hero_row(0)

        # Freeze the detail-pane frames to their data-driven max sizes now
        # that the roster is known (self-guards on no data).
        self._compute_and_apply_fixed_sizes()

    # Sorting and display
    def sort_heroes(self, col: str):
        """Sort heroes list by column"""
        if col == self.hero_sort_col:
            self.hero_sort_reverse = not self.hero_sort_reverse
        else:
            self.hero_sort_col = col
            self.hero_sort_reverse = col in ["gs", "grade", "ego", "affinity",
                                         "partner_level"]

        self.refresh_heroes()

    def _on_tree_select(self, _event=None):
        """The Treeview's selection changed -- show that combatant.

        Fires for a click, for Up/Down, and for a programmatic
        `selection_set`. select_hero_row's index guard is what stops the
        last of those recursing.
        """
        sel = self.hero_tree.selection()
        if not sel:
            return
        try:
            self.select_hero_row(int(sel[0]))
        except (TypeError, ValueError):
            pass

    def _row_index_at(self, event):
        """The hero_data_list index under the pointer, or None."""
        iid = self.hero_tree.identify_row(event.y)
        if not iid:
            return None
        try:
            return int(iid)
        except (TypeError, ValueError):
            return None

    def _on_hero_list_key(self, event):
        """Letter-key navigation: 'A' jumps to the next combatant whose
        name starts with 'A', cycling at the end. Mirror of the preset
        listbox handler in scoring_tab.

        Returns 'break' on a jump so the Treeview does not also act on the
        key. Non-alphanumeric keys fall through, which is what leaves
        Up/Down to the Treeview's own bindings.
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
                return "break"
        return "break"  # no match -- still swallow so Tk doesn't do anything

    def select_hero_row(self, index: int):
        """Select a row and show its combatant.

        Recolouring is the Treeview's own job -- the selected row takes
        the style's selected background, and the row keeps its Element
        foreground from its tag. Nothing here touches colours.

        Re-entrancy: `selection_set` fires <<TreeviewSelect>>, which calls
        straight back here. The index guard below makes the second call a
        no-op rather than a loop.
        """
        if index == self.selected_hero_index:
            return
        self.selected_hero_index = index
        if 0 <= index < len(self.hero_data_list):
            new_hero_data = self.hero_data_list[index]
            iid = str(index)

            # Two timings, because they fail differently and only one of
            # them is reachable from a headless run. `work` is everything
            # this method does; `settle` is what Tk spends afterwards on
            # layout and painting, which it defers to the idle queue. A
            # selection that stutters with a small `work` and a large
            # `settle` is a repaint cost, not a computation one.
            _perf = perf_log.is_enabled()
            _t0 = time.perf_counter() if _perf else 0.0

            if self.hero_tree.exists(iid):
                self.hero_tree.selection_set(iid)
                self.hero_tree.focus(iid)
                self.hero_tree.see(iid)

            self.show_hero_details(new_hero_data["name"])

            if _perf:
                _work = time.perf_counter() - _t0
                self.context.root.after_idle(
                    lambda n=new_hero_data["name"], w=_work, s=_t0:
                    perf_log.log("heroes:select", char=n, work=w,
                                 settle=time.perf_counter() - s - w)
                )

    def _format_char_text(self, hero_name: str) -> str:
        """Build the Character-frame text for `hero_name`.

        Extracted from show_hero_details so the fixed-size computation can
        measure the exact string that will be displayed. Returns the
        "No character data available" placeholder when the character has no
        captured CharacterInfo.
        """
        char_info = self.optimizer.character_info.get(hero_name)
        if not char_info:
            return "No character data available"
        fb = char_info.friendship_bonus
        hero_data = get_character_by_name(hero_name)
        grade = hero_data.get("grade", "?")
        attribute = hero_data.get("attribute", "Unknown")
        hero_class = hero_data.get("class", "Unknown")
        # A combatant the program has no entry for reports "Unknown" for
        # both its element and its class, and saying so twice on one line
        # tells the reader nothing the first one did not.
        header_tail = (attribute if hero_class == attribute
                       else f"{attribute}  |  {hero_class}")

        # One line per tracked node, in the same shape whether or not the
        # node is levelled, so the block does not change height between
        # combatants.
        #
        # The bracket holds the node's DESCRIPTOR -- what the node does,
        # the way the game names it. Nodes 5 and 6 raise a stat that
        # differs per character, so `(?)` stands in until the descriptors
        # for the other eight nodes are stored and every line can carry
        # its own. See docs/game_formulas.md "The potential tree".
        potential_lines = []
        for node, level in ((5, char_info.potential_50_level),
                            (6, char_info.potential_60_level)):
            potential_lines.append(
                f"{CHAR_SUBLIST_INDENT}Node {node}: Lv{level} (?)")
        potential_lines = potential_lines[:CHAR_POTENTIAL_LINES]
        potential_lines += [""] * (CHAR_POTENTIAL_LINES - len(potential_lines))
        potential_str = "\n".join(potential_lines)

        return (
            f"Grade: {grade}*  |  {header_tail}\n"
            f"Level: {char_info.level}/{char_info.max_level}\n"
            f"Ego Manifestation: E{char_info.limit_break}\n"
            f"Affinity Lv: {char_info.friendship_index}\n"
            f"  Bonus: ATK+{fb[0]}, DEF+{fb[1]}, HP+{fb[2]}\n"
            f"Potential:\n{potential_str}"
        )

    def _format_stats_text(self, stat_values: dict) -> str:
        """Build the two-column build-stat block for the Character card.

        Cells are separated by TAB characters and land on the tab stops
        configured in _compute_and_apply_fixed_sizes: value stops are
        right-aligned so the numbers line up despite the proportional
        font, name stops left-aligned. A row whose left key is None still
        emits both of the left pair's tabs, so the right-hand column stays
        on its own stops.

        stat_values maps stat key -> already-formatted string; missing
        keys render as "-", which is what an ungeared character shows.
        """
        lines = []
        for left_key, right_key in HERO_STAT_ROWS:
            if left_key is None:
                left = "\t"
            else:
                left = (f"{HERO_STAT_DISPLAY[left_key]}\t"
                        f"{stat_values.get(left_key, '-')}")
            right = ""
            if right_key is not None:
                right = (f"{HERO_STAT_DISPLAY[right_key]}\t"
                         f"{stat_values.get(right_key, '-')}")
            lines.append(f"{left}\t{right}")
        return "\n".join(lines)

    def _format_character_card(self, hero_name: str, stat_values: dict) -> str:
        """The full Character card text: details block, Sets line, stat
        block. Shared by show_hero_details and the fixed-size computation
        so both work from the same string.
        """
        return (
            f"{self._format_char_text(hero_name)}\n"
            f"Sets:\n{self._format_sets_text(hero_name)}\n"
            f"Stats:\n{self._format_stats_text(stat_values)}"
        )

    def _format_partner_text(self, char_info) -> str:
        """Build the Partner-frame text for a CharacterInfo.

        Mirrors the three partner states from show_hero_details: known
        partner -> full card; equipped-but-unknown res_id -> id line; no
        partner -> placeholder. char_info=None -> "No partner data".
        """
        if char_info is None:
            return "No partner data"
        if char_info.partner_name:
            partner_stats = get_partner_stats(char_info.partner_res_id, char_info.partner_level)
            partner_data = get_partner(char_info.partner_res_id)
            partner_grade = partner_data.get("grade", 3)
            partner_class = partner_data.get("class", "Unknown")
            passive_info = get_partner_passive_info(
                char_info.partner_res_id, char_info.partner_limit_break
            )
            # Partner res_id not in PARTNERS: get_partner falls back to the
            # DEFAULT_PARTNER placeholder whose name is "Unknown" -- show
            # the res_id AS the name so the user can identify/report the
            # missing entry (partners.py's docstring expects exactly this
            # workflow).
            display_name = char_info.partner_name
            if display_name == "Unknown" or partner_data.get("name") == "Unknown":
                display_name = f"#{char_info.partner_res_id}"
            return (
                f"{display_name}  ({partner_grade}* {partner_class})\n"
                f"Level: {char_info.partner_level}/{char_info.partner_max_level}  |  Ego: E{char_info.partner_limit_break}\n"
                f"Stats: ATK+{partner_stats['atk']}, DEF+{partner_stats['def']}, HP+{partner_stats['hp']}\n"
                f"\n{passive_info['passive_name']}\n"
                f"{passive_info['passive_desc']}\n"
                f"\n{passive_info['ego_name']} - {passive_info['ego_cost']} EP\n"
                f"{passive_info['ego_desc']}"
            )
        elif char_info.partner_id:
            if char_info.partner_res_id:
                return (f"Unknown partner "
                        f"(res_id {char_info.partner_res_id}, "
                        f"instance {char_info.partner_id})")
            return f"Unknown partner (instance {char_info.partner_id})"
        return "No partner equipped"

    def _format_sets_text(self, hero_name: str) -> str:
        """The Sets line for a character: the ACTIVE set names (those whose
        equipped count meets their piece requirement), WITHOUT piece
        counts, plus an "N Flex" token for leftover slots, comma-separated.
        Mirrors the Optimizer Results "Sets" logic.

        Shared by show_hero_details and the fixed-size computation so both
        measure the same string.
        """
        gear = self.optimizer.characters.get(hero_name, [])
        if not gear:
            return _padded_sublist(["None"])
        set_counts = {}
        for p in gear:
            set_counts[p.set_id] = set_counts.get(p.set_id, 0) + 1
        active_names = []
        flex = 0
        for sid, cnt in set_counts.items():
            sinfo = SETS.get(sid)
            if sinfo is None:
                flex += cnt
                continue
            pieces = sinfo.get("pieces", 2)
            if cnt >= pieces:
                active_names.append(sinfo["name"])
                flex += cnt - pieces
            else:
                flex += cnt
        active_names.sort()
        parts = list(active_names)
        if flex > 0:
            parts.append(f"{flex} Flex")
        return _padded_sublist(parts)

    def _compute_and_apply_fixed_sizes(self):
        """Freeze the three detail-pane frames (Character, Partner,
        Equipped Memory Fragments) to fixed pixel sizes computed
        from the WIDEST / TALLEST content across ALL captured combatants,
        measured via font metrics -- so switching combatants never resizes
        or shifts the panel.

        Per the spec, the Partner frame's HEIGHT instead tracks the
        Character frame (so the two cards stay equal height); its WIDTH is
        sized to its own widest *structured* header line (the wrapping
        passive/ego prose mustn't drive width -- an unwrapped sentence would
        be absurdly wide; it wraps inside the card, with the existing
        scrollbar for overflow).

        Every size is biased a little LARGE (generous PAD_* constants) so
        content never clips -- over-estimating just leaves a thin margin.
        Wrapped in try/except so a measurement hiccup can't break the tab;
        on failure the frames keep their natural auto-resizing behavior.
        """
        try:
            if not hasattr(self, "_char_frame"):
                return

            try:
                f_default = _default_font()
            except Exception:
                f_default = tkfont.Font(family="Segoe UI", size=9)

            line_default = f_default.metrics("linespace")

            # A STATED size, not a derived one. Deriving it meant
            # estimating the LabelFrame overhead, the wrap width and the
            # line count separately, and the three estimates disagreed --
            # the wrap estimate alone ran ~47px narrower than the real
            # frame, so every cell reserved lines it never used.
            #
            # Calibrated against the longest set description currently in
            # the game. A longer one clips rather than growing the cell,
            # so if a set is added and its description runs off, raise
            # GEAR_CELL_H here.
            cell_w, cell_h = GEAR_CELL_W, GEAR_CELL_H

            # ----- Content maxima -> OUTER frame sizes (generous pad) -----
            # spacing: frame edge -> first non-button element
            # PAD_W / PAD_H approximate the ttk LabelFrame theme overhead
            # so the right and bottom padding read like the top and left.
            # Measured against the longest set description: the right edge
            # lands on the rule's 6px, and the bottom reads 6 under a
            # descender and 9 without one -- the same 3px spread the
            # descender convention produces everywhere else. CHAR_PAD_W adds to PAD_W rather
            # than subtracting from it: the Character frame's own padding
            # is now 0, and its inset comes from the Text widget's padx on
            # both sides.
            PAD_W = 14   # LabelFrame internal padding + border + slack
            PAD_H = 33   # + title-bar height
            CHAR_PAD_W = PAD_W + 12

            # The stat block's tab stops. Four stops per row: the left
            # value (right-aligned), the right column's name, the right
            # value (right-aligned), and nothing after. A right-aligned
            # stop sits at the END of its column, so each is the running
            # total of everything to its left.
            # spacing: label ↔ its element
            # spacing: element and its label ↔ element and its label
            # Stops are PIXEL offsets, not character counts, so the 4 and
            # the 8 below are the rendered gaps themselves. `name_px` is
            # the widest label measured in this font, which is what makes
            # every value in a column start from the same place.
            # Measured PER COLUMN. One max across both columns places the
            # left column's values as if its labels were as wide as
            # `Element`, which is the right column's longest -- the left
            # labels are all three characters, so that alone put ~20px of
            # dead space between them and their values.
            # Row by row: each stat's own label plus its own widest value.
            # Taking max(label) and max(value) separately would place the
            # column for a row that does not exist -- the widest label and
            # the widest value are not on the same line.
            def _column_width(col):
                return max(
                    f_default.measure(HERO_STAT_DISPLAY[row[col]]) + 4
                    + f_default.measure(HERO_STAT_VALUE_MAXIMA[row[col]])
                    for row in HERO_STAT_ROWS if row[col]
                )
            stop_val1 = _column_width(0)
            stop_name2 = stop_val1 + 8
            stop_val2 = stop_name2 + _column_width(1)
            try:
                self.hero_char_text.configure(tabs=(
                    stop_val1, "right", stop_name2, "left",
                    stop_val2, "right",
                ))
            except (AttributeError, tk.TclError):
                pass
            # STATED, not measured. Every line in this panel is now a fixed
            # shape: the details block is a constant set of lines, Sets and
            # Potential pad themselves to CHAR_SETS_LINES and
            # CHAR_POTENTIAL_LINES, and the stat block sits on tab stops
            # derived from HERO_STAT_VALUE_MAXIMA. The only thing left that
            # varied with the data was the widest combatant name, and
            # CHAR_NAME_PX states that.
            #
            # Measuring instead is what made resizing slow: this runs from
            # <Configure>, and it walked every combatant's formatted card
            # to re-derive numbers that no longer move.
            char_W = CHAR_CONTENT_PX + CHAR_PAD_W + 4 - CHAR_WIDTH_CEDED
            row_h = CHAR_TOTAL_LINES * line_default + PAD_H

            def _fix(frame, w, h):
                frame.configure(width=int(w), height=int(h))
                frame.pack_propagate(False)

            _fix(self._char_frame, char_W, row_h)
            # char_frame is width-fixed at char_W (so its content doesn't
            # reflow per character), but fill=tk.Y lets it grow VERTICALLY
            # with info_frame -- which absorbs the detail panel's vertical
            # excess. The minimum height row_h still applies via
            # pack_propagate(False).
            self._char_frame.pack_configure(fill=tk.Y)

            # Partner frame fills the space to the Character frame's right;
            # its HEIGHT is pinned to the Character frame's height, and
            # fill=tk.BOTH lets it also grow VERTICALLY with info_frame,
            # matching the Character frame's vertical-fill behavior.
            self._partner_frame.configure(height=int(row_h))
            self._partner_frame.pack_propagate(False)
            self._partner_frame.pack_configure(fill=tk.BOTH, expand=True)

            # The gear frame is NOT pinned to a computed size: every cell
            # inside it is pinned individually just below, so its natural
            # size is already constant across combatants. Computing it here
            # instead meant guessing the LabelFrame's own overhead, and the
            # guess (sized for padding=5 plus a border) over-provisioned the
            # height once the frame went borderless with padding=0 -- which
            # showed up as a gap between the last row of cells and the
            # bottom of the panel.
            self._gear_outer_frame.pack_configure(fill=tk.NONE, expand=False, anchor=tk.W)

            # Pin every individual Slot frame to the static cell size and
            # stop the grid stretching them, so a long set description
            # wraps inside a fixed box instead of growing it (which would
            # clip GS/Potential on long-description sets like Black Wing).
            # NB: pack_propagate(False) is the correct call here -- each
            # cell uses PACK for its children, so grid_propagate would be
            # a silent no-op and the cells would stay at their natural
            # content size while the outer frame grew.
            cells = list(self.gear_cells.values())
            if cells:
                gear_grid = cells[0].master
                for cell in cells:
                    # A Text sizes in CHARACTERS unless told otherwise, so
                    # the pixel size goes on the grid cell and the widget
                    # is left to fill it.
                    cell.configure(width=1, height=1)
                gear_grid.grid_columnconfigure(0, minsize=int(cell_w))
                gear_grid.grid_columnconfigure(1, minsize=int(cell_w))
                for _r in (0, 1, 2):
                    gear_grid.grid_rowconfigure(_r, minsize=int(cell_h))
                for _c in (0, 1):
                    gear_grid.columnconfigure(_c, weight=0)
                for _r in (0, 1, 2):
                    gear_grid.rowconfigure(_r, weight=0)
        except Exception:
            pass

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
        # Text is built by shared helpers so the fixed-size computation can
        # measure the exact same strings that get displayed. The Character
        # card is written at the END of this method instead of here: it now
        # includes the build stats, which aren't known until the gear loop
        # below has run.
        partner_text = self._format_partner_text(char_info)
        self.hero_partner_text.config(state=tk.NORMAL)
        self.hero_partner_text.delete("1.0", tk.END)
        self.hero_partner_text.insert("1.0", partner_text)
        self.hero_partner_text.config(state=tk.DISABLED)

        gear = self.optimizer.characters.get(hero_name, [])
        gear_by_slot = {p.slot_num: p for p in gear}

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
            cell = self.gear_cells.get(slot_num)
            if cell is None:
                continue
            piece = gear_by_slot.get(slot_num)
            piece_gs = (compute_fragment_gs(piece, detail_weights,
                                            _bounds_for(piece))
                        if piece else 0.0)
            self._render_gear_cell(cell, slot_num, piece, gear, piece_gs)

        if gear:
            stats = self.optimizer.calculate_build_stats(gear, hero_name)

            # Element% = matching-element DMG% main(s) for this character's
            # attribute (0 for Unknown-attribute characters, since the
            # Combatants tab has no element override).
            attribute = get_character_by_name(hero_name).get("attribute", "Unknown")
            elem_pct = 0.0
            if attribute and attribute != "Unknown":
                target = f"{attribute} DMG%"
                elem_pct = sum(p.main_stat.value for p in gear
                               if p.main_stat and p.main_stat.name == target)

            stat_values = {
                "ATK": f"{stats.get('ATK', 0):.0f}",
                "DEF": f"{stats.get('DEF', 0):.0f}",
                "HP": f"{stats.get('HP', 0):.0f}",
                "Ego": f"{stats.get('Ego', 0):.0f}",
                "CRate": f"{stats.get('CRate', 0):.1f}%",
                "CDmg": f"{stats.get('CDmg', 0):.1f}%",
                "Extra DMG%": f"{stats.get('Extra DMG%', 0):.1f}%",
                "DoT%": f"{stats.get('DoT%', 0):.1f}%",
                "Element": f"{elem_pct:.1f}%",
            }
        else:
            stat_values = {}

        self.hero_char_text.config(state=tk.NORMAL)
        self.hero_char_text.delete("1.0", tk.END)
        self.hero_char_text.insert(
            "1.0", self._format_character_card(hero_name, stat_values))
        self.hero_char_text.config(state=tk.DISABLED)

    # ----- Per-character preset helpers ----------------------------------

    def _hero_gs(self, gear: list, preset_name: Optional[str]) -> float:
        """One combatant's total Gear Score under a preset's weights.

        Each fragment's bounds exclude its own main stat (Philosophy B),
        so the bounds are cached by main_stat across this combatant's
        pieces rather than recomputed per fragment. The cache is
        deliberately per-CALL: sharing it across combatants, keyed by
        (preset_name, main_stat), was tried and reverted -- in current
        use every combatant has a unique preset, so a shared cache never
        hits and only adds overhead.
        """
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
        return gs

    def _apply_preset_to_row(self, hero_name: str,
                             preset_name: Optional[str]) -> None:
        """Re-do one combatant's Preset and GS cells where they stand.

        A preset assignment moves exactly those two, and only for this
        combatant -- so the whole-list rebuild the caller used to do was
        visible as the list blinking out and back.
        """
        for index, hero in enumerate(self.hero_data_list):
            if hero["name"] == hero_name:
                break
        else:
            return

        gear = self.optimizer.characters.get(hero_name, [])
        hero["gs"] = self._hero_gs(gear, preset_name)
        hero["preset"] = "-" if preset_name is None else preset_name

        iid = str(index)
        if self.hero_tree.exists(iid):
            self.hero_tree.set(
                iid, "gs",
                f"{hero['gs']:.0f}" if hero["gs"] > 0 else "-")
            self.hero_tree.set(iid, "preset", hero["preset"])

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

        # The assignment moves this combatant's Preset and GS cells, and
        # the per-piece GS in the detail pane beside them. Sorting BY
        # either of those two columns is the one case where the row's
        # position changes as well, and only that case rebuilds.
        target_name = self._current_detail_hero
        if self.hero_sort_col in ("gs", "preset"):
            self.refresh_heroes()
            for i, h in enumerate(self.hero_data_list):
                if h["name"] == target_name:
                    self.select_hero_row(i)
                    break
        else:
            self._apply_preset_to_row(target_name, new_value)
            self.show_hero_details(target_name)

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
    def _render_gear_cell(self, cell, slot_num, piece, gear, piece_gs):
        """Draw one Equipped Memory Fragments cell into its Text widget.

        Layout, one line each:

            main stat        GS: n  Potential: a-b        Slot  +level
            q%  substat +total (base | +upg, +upg)
            ... one per substat ...
            Set name (n) bonus description, wrapped

        The columns are the `toprow` / `subrow` tags' tab stops and every
        colour is a tag. `rarity` is re-coloured per fragment, because the
        slot name and the main stat both take the fragment's rarity.
        """
        slot_name = EQUIPMENT_SLOTS.get(slot_num, f"Slot {slot_num}")
        cell.config(state=tk.NORMAL)
        cell.delete("1.0", tk.END)

        if piece is None:
            cell.tag_configure("rarity", foreground=self.colors["fg_dim"])
            line = cell.index("end-1c")
            cell.insert(tk.END, "Empty", ("rarity",))
            cell.insert(tk.END, "\t\t")
            cell.insert(tk.END, slot_name, ("rarity",))
            cell.tag_add("toprow", line, "end-1c")
            cell.config(state=tk.DISABLED, bg=self.colors["bg_light"])
            return

        rarity_color = RARITY_COLORS.get(piece.rarity_num, self.colors["fg"])
        bg_color = RARITY_BG_COLORS.get(piece.rarity_num,
                                        self.colors["bg_light"])
        cell.tag_configure("rarity", foreground=rarity_color)

        # ----- Top row -----
        line = cell.index("end-1c")
        if piece.main_stat:
            cell.insert(
                tk.END,
                f"{piece.main_stat.name}  +{piece.main_stat.format_value()}",
                ("rarity",))
        cell.insert(tk.END, "\t")
        cell.insert(tk.END, f"GS: {piece_gs:.0f}", ("gs",))
        if piece.potential_low != piece.potential_high:
            cell.insert(
                tk.END,
                f"{GEAR_GS_POT_GAP}Potential: {piece.potential_low:.0f}-"
                f"{piece.potential_high:.0f}",
                ("pot",))
        cell.insert(tk.END, "\t")
        cell.insert(tk.END, f"{slot_name}  +{piece.level}", ("rarity",))
        cell.tag_add("toprow", line, "end-1c")

        # ----- One line per substat -----
        num_starting = RARITY_STARTING_SUBSTATS.get(piece.rarity_num, 3)
        for i, sub in enumerate(piece.substats[:4]):
            cell.insert(tk.END, "\n")
            line = cell.index("end-1c")
            cell.insert(tk.END, "\t")
            cell.insert(tk.END, f"{sub.get_roll_quality_pct():.0f}",
                        ("quality",))
            cell.insert(tk.END, "\t")

            # An ADDED substat -- one the fragment gained on level-up
            # rather than starting with -- carries its own tag, the same
            # colour today and the hook if it ever stops being.
            base_tag = "added" if i >= num_starting else "default"
            roll_parts = self.format_roll_with_color(sub)

            if sub.roll_count > 1:
                cell.insert(tk.END,
                            f"{sub.name} +{sub.format_value()} (", (base_tag,))
                for idx, (roll_text, roll_color) in enumerate(roll_parts):
                    if idx == 1:
                        cell.insert(tk.END, " | ", (base_tag,))
                    elif idx > 1:
                        cell.insert(tk.END, ", ", (base_tag,))
                    cell.insert(tk.END, roll_text,
                                (self._roll_tag(roll_color, "normal"),))
                cell.insert(tk.END, ")", (base_tag,))
            else:
                cell.insert(tk.END, f"{sub.name} +", (base_tag,))
                value_tag = (self._roll_tag(roll_parts[0][1], base_tag)
                             if roll_parts else base_tag)
                cell.insert(tk.END, sub.format_value(), (value_tag,))
            cell.tag_add("subrow", line, "end-1c")

        # ----- Set line -----
        # The name shows live when this combatant has the set's required
        # pieces equipped and dim otherwise, which is the at-a-glance
        # signal for whether the bonus is actually running.
        set_info = SETS.get(piece.set_id)
        bonus_text = set_info.get("bonus", "") if set_info else ""
        required = set_info.get("pieces", 999) if set_info else 999
        equipped_in_set = sum(1 for p in gear if p.set_id == piece.set_id)
        set_tag = "set_live" if equipped_in_set >= required else "set_dim"
        cell.insert(
            tk.END,
            f"\n{piece.set_name} ({piece.get_set_pieces()}) {bonus_text}",
            (set_tag,))

        cell.config(state=tk.DISABLED, bg=bg_color)

    def _roll_tag(self, roll_color, fallback):
        """The tag that paints a roll of this colour."""
        if roll_color == self.colors["green"]:
            return "max_roll"
        if roll_color == self.colors["red"]:
            return "min_roll"
        return fallback

    def format_roll_with_color(self, sub: Stat):
        """A substat's rolls as (text, colour) pairs, one per roll."""
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
