"""Materials tab: upgrade material by class and Element.

Three headed columns -- Combatant promotion, Partner promotion,
potential growth -- and a fourth at the far right holding placeholder
tiles, reserving the shape another family would take. The first and
last sit at their cells' outer edges rather than centred, so the block
spans the window; the leftover width goes to spacers between the
columns, which is what keeps the gaps across it equal.

A data row is a name, its figures, and its three tiers as icons, the
leftmost the most valuable. Its figures come from THAT ROW's three
counts and no others: each tier priced in bottom-tier equivalents and
the three summed. **The pricing is the ROW's, not the tab's** -- a
promotion family runs 9/3/1 and an EXP material 20/5/1, and both spell
their top tier `Premium`.

**A `Level 50:` figure means one of two things.** On a promotion row it
is the cost of unlocking that level ceiling; on an EXP row it is the
cost of the levelling itself. Different items, different tables and
different numbers, which is why the two carry separate targets.

**Each column ends in a GENERIC item** -- one that stands in for the
bottom tier of any row in its column. It sits under the last row in the
rightmost icon position, beside a checkbox that adds its count to the
promotion rows' totals. Off by default: the stock is shared between the
rows, so adding it to each of them counts it once per row rather than
once. The EXP row is never one of them -- a Certificate raises a
ceiling and buys no exp.

Three kinds of row depart from that shape, and all of them count
something other than one item's holdings. The EXP row under each
promotion column's generic is priced in its own material. The stones
column's ADVANCED row is three figure columns wide, one per item, none
of the three substituting for another. Its GACHA row counts PULLS,
which is neither of its currencies' own unit.

Rows are pinned by their RIGHT edge for that reason: every row ends in
its icons, so one needing more room takes it on the left.

**The reserved column carries one item per row and no words.** Its
last four rows all draw the Command Delegation Module, each showing
the copies expiring inside its own window -- a period item's copies
are listed with their expiries rather than counted, so no single
number would say what is worth using today.
"""

import time
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from pathlib import Path

from typing import NamedTuple

from game_data import (
    ATTRIBUTE_COLORS, CHARACTER_EXP_TABLE, COMBATANT_PROMOTION,
    EXP_MATERIALS, GROWTH_STONES, PARTNER_EXP_TABLE, PARTNER_PROMOTION,
)
from game_data.constants import item_art, rarity_plate
import period_items
from ..base_tab import BaseTab
from ..utils.checkbox import make_checkbox
from ..utils.image_utils import (
    ICON_SIZE, RARITY_DIR, create_icon_with_quantity, create_plate_icon,
)
from ..utils.tab_header import make_heading
from ..utils.tooltip import Tooltip


# Where each column's checkbox state is kept, by the column's own key.
# NOT `combatants_show_missing`, which the Combatants tab's checkbox
# already owns -- sharing it would tie two unrelated switches together.
#
# One key per column rather than one for all three: a column's generic
# stands in for that column's bottom tier and nothing else, so the
# three switches answer three separate questions.
def include_generic_key(column_key):
    return f"materials_include_generic_{column_key}"

# The six classes, in the order the game lists them. NOT the order of
# their res_id group digits, which runs Striker, Vanguard, Hunter,
# Ranger, Psionic, Controller -- Hunter and Ranger swap.
CLASS_ORDER = ("Striker", "Vanguard", "Ranger", "Hunter", "Psionic",
               "Controller")
ELEMENT_ORDER = ("Passion", "Instinct", "Void", "Order", "Justice")

# What each tier of a PROMOTION family is worth in bottom-tier
# equivalents. Keyed by tier word, because the three families spell
# their middle tier differently.
TIER_WEIGHTS = {"Premium": 9, "Great": 3, "Advanced": 3, "Common": 1}

# What one EXP material is worth. The game states these by RARITY --
# Common 100, Rare 500, Legendary 2000 -- and `TIER_RARITY` is what
# pairs those words with the tiers named here.
EXP_PER_TIER = {"Basic": 100, "Advanced": 500, "Premium": 2000}

# The same in bottom-tier equivalents, which is what every figure on
# the tab counts in. SEPARATE from `TIER_WEIGHTS` and not a rewording
# of it: `Premium` is worth nine of its family's bottom tier on a
# promotion row and twenty on an EXP row, so one table keyed by tier
# word would price one of the two wrong and nothing would say so.
EXP_WEIGHTS = {tier: exp // EXP_PER_TIER["Basic"]
               for tier, exp in EXP_PER_TIER.items()}

# The Common-equivalent cost of taking one Element's potential nodes to
# each of three levels. The rows read as increasing ambition, so each
# denominator is larger than the one above it and the same total scores
# lower against each in turn.
#
# (label, cost). The label ends in the colon the column is aligned on.
STONE_TARGETS = (
    ("Max best:", 2887),
    ("+Neutral:", 3178),
    ("+Node 5.1 & 5.2:", 3682),
)

TOTAL_LABEL = "Total:"

# The Common-equivalent cost of PROMOTING one Combatant or Partner far
# enough to raise its level ceiling. `Level 50:` here reads "unlock the
# ability to level to 50" and prices Manuals or Certificates; the cost
# of the levelling itself is the EXP row's, below.
#
# (label, cost). **A cost of None is a figure nobody has priced yet**:
# the row is built and reads `-` until one is given, rather than being
# left out and having to be threaded back through the layout later.
PROMOTION_TARGETS = (("Level 50:", 293), ("Level 60:", 617))


def _exp_targets(table, levels):
    """(label, cost) per level, in bottom-tier EXP materials.

    Derived from the exp table rather than stated: the cost of taking
    one Combatant or Partner to a level IS that level's cumulative exp,
    and the only conversion is what the bottom tier is worth. So a
    corrected checkpoint moves the target with it.

    Rounded UP, no material being divisible. A level the table does not
    document costs None so that the tab still builds; that reads as an
    unpriced target when it means the level does not exist for this
    kind, so `check_materials_targets` names any column relying on it.
    """
    per = EXP_PER_TIER["Basic"]
    by_level = {level: exp for exp, level in table}
    return tuple(
        (f"Level {level}:",
         -(-by_level[level] // per) if level in by_level else None)
        for level in levels
    )


# **A Partner has no level 61.** The row exists for Combatants because
# `CHARACTER_EXP_TABLE` documents a level-61 checkpoint, and is absent
# for Partners because `PARTNER_EXP_TABLE` ends at 60.
COMBATANT_EXP_TARGETS = _exp_targets(CHARACTER_EXP_TABLE, (50, 60, 61))
PARTNER_EXP_TARGETS = _exp_targets(PARTNER_EXP_TABLE, (50, 60))


# The ADVANCED potential materials, left to right as the row draws
# them: Eye of Wailing Prodigal, Shards of Condemnation, Undetermined
# Ego Crystal. Each levels a node without being a Growth Stone.
ADVANCED_ITEMS = (3110001, 3110004, 3000003)
ADVANCED_LABEL = "Advanced"

# (label, one cost per item above, in that order) for each target.
#
# **A row states what THAT STEP alone costs.** What the row reports is
# the running total from the top down -- see `advanced_costs` -- since
# reaching `+Node 5.2` means having paid for everything above it.
#
# `None` is a step needing none of that item. It adds nothing to the
# running total, and is not the same as an unpriced figure: every step
# here is priced.
#
# The three items never mix. Each column accumulates its OWN item and
# is read against that item's own stock, because none of the three
# substitutes for another and the column's Potential Disk substitutes
# for none of them.
ADVANCED_TARGETS = (
    ("Max best:", (4, 6, 2)),
    ("+Neutral:", (8, None, None)),
    ("+5.1:", (None, 2, None)),
    ("+5.2:", (4, 2, None)),
)


def advanced_costs():
    """`ADVANCED_TARGETS` with each item's costs accumulated downward.

    Per ITEM and never across them: a column's running total is its own
    item's, so `+Node 5.2` reads what that item costs to reach node 5.2
    having already paid for everything above.

    A running total of 0 means the item is not wanted up to there at
    all, which the row reads as `-` -- there is no ratio to take.
    """
    running = [0] * len(ADVANCED_ITEMS)
    out = []
    for label, costs in ADVANCED_TARGETS:
        running = [total + (cost or 0)
                   for total, cost in zip(running, costs)]
        out.append((label, tuple(running)))
    return tuple(out)


def _module_buckets(expiries, now):
    """How many copies fall in each of `MODULE_BUCKETS`, and none twice.

    A copy is counted in the FIRST window it falls inside, so the
    counts sum to what is held. One already past its expiry lands in
    the soonest window, which is where a copy needing attention
    belongs.
    """
    counts = [0] * len(MODULE_BUCKETS)
    for end in expiries:
        hours = (end - now) / 3600
        for index, (limit, _caption) in enumerate(MODULE_BUCKETS):
            if limit is None or hours < limit:
                counts[index] += 1
                break
    return counts


def gacha_pulls(quantities):
    """What the gacha currencies come to in PULLS.

    Each item's holding buys whole pulls on its own before the two are
    added: 159 Crystals and one Anchor is one pull, not one and a bit,
    because a part-paid pull buys nothing.
    """
    return sum(quantities.get(res_id, 0) // per
               for res_id, per in zip(GACHA_ITEMS, GACHA_PER_PULL))


def _rounded_percent(part, whole):
    """`part` as a percentage of `whole`, half away from zero.

    Python's own `round` goes to even, which reports 50.5 as 50 and
    51.5 as 52 -- a spreadsheet takes both up, and these figures are
    read beside one.
    """
    return int(100 * part / whole + 0.5) if whole else 0


# What a reserved tile is drawn as: a rarity plate with nothing on it.
# UNCOMMON because no item table prices anything at that rarity, so a
# plate in it cannot be read as a real item whose icon failed to load.
RESERVED_RARITY = "Uncommon"

# The gacha currencies, left to right beside their figures, under the
# Growth Stones column's Advanced row.
GACHA_ITEMS = (2000004, 2000010)
GACHA_LABEL = "Gacha Pulls"

# What one pull costs in each, same order. An Anchor IS a pull;
# Crystals buy whole ones, so each item's share floors before they are
# added -- 159 Crystals and an Anchor is one pull, not one and a bit.
GACHA_PER_PULL = (160, 1)

# (label, pulls it takes, what its tooltip says). The figure is the
# share of that many pulls the holdings cover.
GACHA_TARGETS = (
    ("Decent luck:", 64, "64 pulls and win the 50/50"),
    ("Poor luck:", 128, "128 pulls"),
)

# The reserved column, top to bottom. `None` is a row still reserved,
# which draws the plate alone.
RESERVED_ITEMS = (2000001, 2000027, 2000036, None)

# Under them, the Command Delegation Module split by how soon a copy
# expires. **The windows do not overlap**: a copy is counted in the
# first it falls inside and no other, so the four rows sum to what is
# held rather than each containing the ones above it.
#
# (hours, caption), the last taking everything past the one before it.
# The caption is drawn over the icon's top-left corner.
MODULE_ITEM = 3920026
MODULE_BUCKETS = (
    (24, "<24h!!!"),
    (48, "<2 days"),
    (72, "<3 days"),
    (None, "3+ days"),
)


class Column(NamedTuple):
    """One column of the tab.

    `targets` prices this column's PROMOTION rows; `levelling` is the
    extra row under the generic -- the EXP material for that column's
    kind, with its own tiers and its own targets, since the two answer
    different questions about the same level number. Empty for a
    column with no such material.

    `advanced` is a row whose figures are THREE columns wide -- one
    per item beside it, each held against its own stock. `gacha` is a
    row of currencies whose figures count PULLS rather than the items
    themselves.
    """
    key: str
    title: str
    names: tuple
    table: dict
    tiers: tuple
    generic: int
    targets: tuple
    levelling: tuple = ()
    advanced: tuple = ()
    gacha: tuple = ()


COLUMNS = (
    Column("combatant", "Combatant Upgrade Material", CLASS_ORDER,
           COMBATANT_PROMOTION, ("Premium", "Advanced", "Common"),
           2100001, PROMOTION_TARGETS,
           ("Battle Memory", EXP_MATERIALS, "Combatant",
            ("Premium", "Advanced", "Basic"), COMBATANT_EXP_TARGETS)),
    Column("partner", "Partner Upgrade Material", CLASS_ORDER,
           PARTNER_PROMOTION, ("Premium", "Advanced", "Common"),
           2100002, PROMOTION_TARGETS,
           ("Support Data", EXP_MATERIALS, "Partner",
            ("Premium", "Advanced", "Basic"), PARTNER_EXP_TARGETS)),
    # No PROMOTION_TARGETS here: a level is a Combatant's or a
    # Partner's, and a potential node has none.
    Column("stones", "Potential Growth Stones", ELEMENT_ORDER,
           GROWTH_STONES, ("Premium", "Great", "Common"),
           2100003, STONE_TARGETS, advanced=ADVANCED_ITEMS,
           gacha=GACHA_ITEMS),
)

# The far-right column carries one icon per row and no words -- no
# heading, no names, no figures. **ONE icon wide, and that is a width
# the tab cannot spare more of**: the three real columns take what
# they need and this gets the remainder, so a second icon here would
# push the four past the window and grid would clip the last icon off
# every row. Widening it means narrowing the icons, or a wider window.
#
# Its rows are `RESERVED_ITEMS` then `MODULE_BUCKETS`, and the two
# together come to as many rows as the tallest column beside it, so
# the block ends level with them rather than short.
RESERVED_ROWS = max(len(spec.names) + 1 + (1 if spec.levelling else 0)
                    for spec in COLUMNS)

# The stat lines under a row's name. Small, because they are a readout
# under a heading rather than content in their own right.
STAT_FONT = ("Segoe UI", 9)
NAME_FONT = ("Segoe UI", 12, "bold")

# A caption's size in PIXELS, which is what PIL takes where `NAME_FONT`
# states points. 96dpi is what Tk assumes on Windows.
CORNER_FONT_PX = round(NAME_FONT[1] * 96 / 72)

# Between the icons of a row, and between one row of icons and the next.
ICON_GAP_HALF = 0       # spacing: content frame -> content frame -- frame, frame ↔
# 2 for a rendered 4 while `ICON_EDGE` reads INK: an icon's art
# stops inside its own box top and bottom, so two of the four sit
# inside the icons rather than between them.
ROW_GAP = 2             # spacing: content frame -> content frame -- frame, frame ↕

# The heading of a column against the first row under it. The gap runs
# from the heading's BASELINE to the row name's CAPITAL, and three
# things sit in it: five rows of heading box below the baseline, this
# pad, and seven rows of name box above the capital.
#
# **The heading's five cannot be trimmed away.** Two of these three
# titles carry descenders -- `Upgrade` has a `p` and a `g` -- and the
# box below the baseline is what draws them: a `bottom_trim` past
# `HEADING_PAD_BOTTOM` takes the box under the font's linespace and Tk
# clips the glyphs. So the pad goes to its floor and the rest comes off
# the NAME's box instead.
HEADING_GAP = 0         # spacing: panel ↕ unrelated label -- heading, frame ↕

# The row name's own box, above its capital and below its baseline. The
# top is the heading gap's last two pixels; taking them here lifts the
# figures block two off the icons beside it, which is the smallest
# disturbance of the three places the distance could come from.
NAME_PAD_TOP = -2
# A row's name against the first figure under it. A lever one short of
# the rule, the name's box ending past its own baseline.
NAME_PAD_BOTTOM = -1    # spacing: label row -> label row -- label, label ↕

# A row's text block against the icons beside it, and a stat line's
# label against its value. Both are levers a rendered distance short of
# the rule, because a ttk.Label's glyphs stop inside its own box and
# these pads start at the box.
#
# The figures' block ends on a RIGHT-ALIGNED value, so the gap after it
# is the SMALLEST across the rows -- a value narrower than the reserved
# column starts further right and leaves the difference as slack.
#
# The icons' box and not their art: every icon carries a transparent
# border so that its art is centred the way the game centres it, and
# the border is part of the icon rather than part of the gap.
TEXT_TO_ICONS = 2       # spacing: label ↔ its element -- label, frame ↔
# The labels all end in a colon, whose ink stops inside its advance --
# so the pad is the rule's 5 less that and the box inset.
LABEL_TO_VALUE = 2      # spacing: label ↔ its element -- label, label ↔

# The generic row's checkbox against the icon beside it.
GENERIC_TO_CHECKBOX = 5  # spacing: label ↔ its element -- frame, checkbox ↔

# How wide the figures' column is held, in digits. RESERVED rather than
# fitted: right-aligned values in a column that sizes to its content
# would move the labels beside them every time a figure gained or lost
# a digit, and each row has its own grid, so the blocks would stop
# lining up with each other.
#
# `400%` is the other thing the column has to hold, and a percent sign
# is wider than a digit -- so the reservation is the larger of the two
# rather than the digits alone.
VALUE_DIGITS = 4
VALUE_WIDEST = "400%"

# What a ttk.Label adds around its own text, both sides together. Its
# `minsize` is a box width and the reservation above is an ink width,
# so one has to be restated as the other. Measured at Segoe UI 9 and
# constant across every string tried.
LABEL_INSET_PX = 4

# What a figure reads before any snapshot has been loaded.
NO_DATA = "-"


class MaterialsTab(BaseTab):
    """Upgrade material by class and Element, with its totals."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.material_icons = {}     # res_id -> the Label drawing it
        # (column index, row name) -> (value labels, targets, table, tiers)
        self.material_stats = {}
        # column index -> ({label: [one value Label per item]}, res_ids)
        # for the Advanced row, whose figures are three columns wide
        # and so do not fit `material_stats`.
        self.advanced_stats = {}
        self._column_generics = {}   # column index -> generic res_id
        self.include_generic_vars = {}   # column index -> its BooleanVar
        # The last counts drawn, so the checkbox can redraw the figures
        # without a snapshot being reloaded under it.
        self._quantities = {}
        # Every copy's expiry, by res_id. Period items carry no amount
        # -- their copies are listed -- so the counts on the reserved
        # column come from here rather than from the item list.
        self._expiries = {}
        # One instance for the whole tab, which is how every other tab
        # uses it: the hover state belongs to the pointer, not to a
        # widget.
        self._tooltip = Tooltip(self.colors)
        self.setup_ui()
        # Drawn at once with zero counts, so the tab is icons rather
        # than a wall of text before the first capture -- the images
        # are static assets and only the numbers need data.
        self._render_icons({})

    # ------------------------------------------------------------ build

    def setup_ui(self):
        """Setup the Materials tab UI."""
        columns = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        # ASYMMETRIC, because the two edges meet different things. On
        # the left the block starts with a row's TEXT, whose glyphs
        # begin inside a Label's own inset; on the right it ends with a
        # reserved tile, whose outline is drawn at its box edge. Same
        # rule, and the pad that satisfies it differs by the inset.
        columns.pack(fill=tk.BOTH, expand=True, padx=(1, 4), pady=(0, 2))
        # Content in the EVEN grid columns, an empty expanding one
        # between each pair. Where the tab's leftover width goes is the
        # whole of this arrangement: shared out inside the content
        # cells it lands unequally -- the widest column keeps the least
        # -- and the gaps across the block then run 31, 19 and 5. Given
        # instead to three spacers of one uniform group it lands as
        # three EQUAL gaps, with the block flush against both edges.
        #
        # No widget in a spacer. An empty grid column still takes its
        # share as long as its index falls inside the range the content
        # columns span, and a frame there would show up in every walk
        # of this tab's children.
        for index in range(len(COLUMNS) + 1):
            columns.grid_columnconfigure(2 * index, weight=0)
        for index in range(len(COLUMNS)):
            # spacing: content frame -> content frame -- frame, frame ↔
            # NOT TRACKED: the distance is whatever the tab has spare
            # divided three ways, so it moves with the window. The
            # audit compares against a number; what is fixed here is
            # that the three are equal, which `check_tabs_build` holds.
            columns.grid_columnconfigure(
                2 * index + 1, weight=1, uniform="materials")
        columns.grid_rowconfigure(0, weight=1)

        # One image for every reserved tile on the tab: the art is the
        # same empty plate wherever it appears and carries no count, so
        # there is nothing to draw per tile. Built before the columns
        # because a column's specials row uses it too.
        self._reserved_tile = create_plate_icon(
            str(Path(__file__).parent.parent.parent / "images" / RARITY_DIR
                / rarity_plate(RESERVED_RARITY)),
            background=self.colors["bg"])

        for index, spec in enumerate(COLUMNS):
            column = ttk.Frame(columns)
            column.grid(row=0, column=2 * index, sticky="nsew")
            self._build_column(column, index, spec)

        reserved = ttk.Frame(columns)
        reserved.grid(row=0, column=2 * len(COLUMNS), sticky="nsew")
        self._build_reserved_column(reserved)

    def _build_column(self, column, index, spec):
        """One column: a heading, its rows, its generic, its levelling."""
        sm = self.context.settings_manager
        self.include_generic_vars[index] = tk.BooleanVar(
            value=bool(sm.get(include_generic_key(spec.key), False))
            if sm is not None else False)

        # No `bottom_trim`: see HEADING_GAP. These titles have
        # descenders and the box below the baseline is what draws them.
        make_heading(column, spec.title).pack(anchor=tk.CENTER)

        # `anchor=N` rather than a fill: the rows sit at the top of the
        # column, so its leftover height falls below them rather than
        # being shared out between them.
        rows = ttk.Frame(column)
        rows.pack(anchor=tk.N, pady=(HEADING_GAP, 0))

        text_width, label_width = self._text_block_px(spec)

        def add_row(first=False):
            """The next row down, right-anchored.

            **`anchor=E`, not CENTER.** Every row ends in its icons and
            what has to line up is those, so the right edges are what
            the rows are pinned by -- which lets a row needing more
            room than its neighbours take it on the LEFT, where there
            is nothing to disturb. Two rows do: the specials row runs
            an icon wider, and the Advanced row's figures are three
            columns instead of one.
            """
            row = ttk.Frame(rows)
            row.pack(anchor=tk.E, pady=(0 if first else ROW_GAP, 0))
            return row

        for position, name in enumerate(spec.names):
            self._build_row(add_row(first=position == 0), index, name,
                            spec.table, spec.tiers, spec.targets,
                            TIER_WEIGHTS, label_width)

        self._column_generics[index] = spec.generic
        self._build_generic_row(add_row(), index, spec, text_width)

        if spec.levelling:
            name, table, group, tiers, targets = spec.levelling
            # `EXP_WEIGHTS`, not `TIER_WEIGHTS`: an EXP material is not
            # three of the tier below it, and the two families spell
            # their tiers alike.
            self._build_row(add_row(), index, group, table, tiers, targets,
                            EXP_WEIGHTS, label_width, label=name,
                            takes_generic=False)

        if spec.advanced:
            self._build_advanced_row(add_row(), index, spec)

        if spec.gacha:
            self._build_gacha_row(add_row(), spec)

    def _build_row(self, row, index, name, table, tiers, targets,
                   weights, label_width, label=None, takes_generic=True):
        """One class, Element or material: its name, figures, icons.

        `weights` prices this row's tiers in bottom-tier equivalents.
        It comes from the caller rather than a lookup here because the
        promotion and EXP families share tier words and disagree about
        what they are worth.

        `takes_generic` says whether the column's checkbox can add its
        stand-in to this row. The generic substitutes for a PROMOTION
        family's bottom tier and buys no exp at all, so the EXP row
        never takes it however the checkbox is set.

        `label` overrides the heading, for a row whose group name
        is not what the user calls it.
        """
        text = ttk.Frame(row)
        text.pack(side=tk.LEFT, anchor=tk.N)
        # The figures' column, held at its reserved width. `minsize` is
        # a floor, so a value wider than the reservation still widens
        # it -- which is why the reservation covers the widest form the
        # column can hold rather than four digits alone.
        text.grid_columnconfigure(1, minsize=self._value_column_px())
        # And the label column at the column's own width, so every row
        # in it reserves the same block and their icons line up.
        text.grid_columnconfigure(0, minsize=label_width)

        # Spanning both columns with no sticky, which centres it over
        # the figures. The columns are left to size to their own
        # content: giving them weights would split the block evenly and
        # pull the colons off the value column.
        ttk.Label(text, text=label or name, font=NAME_FONT,
                  foreground=ATTRIBUTE_COLORS.get(name, self.colors["fg"]),
                  padding=(0, NAME_PAD_TOP, 0, NAME_PAD_BOTTOM),
                  ).grid(row=0, column=0, columnspan=2)

        values = {}
        # `figure`, not `label`: the parameter of that name is the
        # row's heading, and a loop variable shadowing it registered
        # every row under the last figure's name instead of its own.
        for line, figure in enumerate(
                (TOTAL_LABEL, *(word for word, _cost in targets)), start=1):
            # The colons line up because the labels are right-aligned
            # in their own column and the values left-aligned in
            # theirs; the pad is the whole of the gap between them.
            ttk.Label(text, text=figure, font=STAT_FONT).grid(
                row=line, column=0, sticky="e", padx=(0, LABEL_TO_VALUE))
            # `sticky=ew` with `anchor=e`: the widget fills the column
            # and the digits sit at its right. Sticking it east instead
            # would right-align the WIDGET, which is the same thing to
            # look at and leaves nothing at the column's left edge --
            # and that edge is where the label beside it is spaced from,
            # so it has to be a real one.
            value = ttk.Label(text, text=NO_DATA, font=STAT_FONT,
                              anchor=tk.E)
            value.grid(row=line, column=1, sticky="ew")
            values[figure] = value
        self.material_stats[(index, label or name)] = (
            values, targets, table, name, tiers, weights, takes_generic)

        icons = ttk.Frame(row)
        icons.pack(side=tk.LEFT, anchor=tk.N, padx=(TEXT_TO_ICONS, 0))
        for position, tier in enumerate(tiers):
            label = self._make_icon_label(icons)
            # Half each side, so two neighbours sum to the rule.
            label.grid(row=0, column=position, padx=ICON_GAP_HALF)
            res_id = self._res_id_for(table, name, tier)
            if res_id is not None:
                self.material_icons[res_id] = label

    def _build_advanced_row(self, row, index, spec):
        """The materials that level a node without being a stone.

        Its figures are THREE columns, one per item beside it and in
        the same left-to-right order, because none of the three stands
        in for another -- each reads against its own stock. That makes
        the block wider than any other row's, which is what the rows'
        right-anchoring is for: the extra comes off the LEFT and the
        icons still line up.

        The label column is this row's OWN width rather than the
        column's: its labels are shorter than `+Node 5.1 & 5.2:` above,
        and holding it to that width would push the block wider still
        for no reason.
        """
        text = ttk.Frame(row)
        text.pack(side=tk.LEFT, anchor=tk.N)
        stat = tkfont.Font(font=STAT_FONT)
        value_px = self._value_column_px()
        text.grid_columnconfigure(
            0, minsize=max(stat.measure(word) for word, _costs
                           in ADVANCED_TARGETS) + LABEL_INSET_PX)
        for position in range(len(spec.advanced)):
            text.grid_columnconfigure(1 + position, minsize=value_px)

        span = 1 + len(spec.advanced)
        ttk.Label(text, text=ADVANCED_LABEL, font=NAME_FONT,
                  foreground=self.colors["fg"],
                  padding=(0, NAME_PAD_TOP, 0, NAME_PAD_BOTTOM),
                  ).grid(row=0, column=0, columnspan=span)

        values = {}
        for line, (word, _costs) in enumerate(ADVANCED_TARGETS, start=1):
            ttk.Label(text, text=word, font=STAT_FONT).grid(
                row=line, column=0, sticky="e", padx=(0, LABEL_TO_VALUE))
            values[word] = []
            for position in range(len(spec.advanced)):
                value = ttk.Label(text, text=NO_DATA, font=STAT_FONT,
                                  anchor=tk.E)
                value.grid(row=line, column=1 + position, sticky="ew")
                values[word].append(value)
        self.advanced_stats[index] = (values, spec.advanced)

        icons = ttk.Frame(row)
        icons.pack(side=tk.LEFT, anchor=tk.N, padx=(TEXT_TO_ICONS, 0))
        for position, res_id in enumerate(spec.advanced):
            label = self._make_icon_label(icons)
            label.grid(row=0, column=position, padx=ICON_GAP_HALF)
            self.material_icons[res_id] = label

    def _build_gacha_row(self, row, spec):
        """The gacha currencies, and what they come to in PULLS.

        Its figures count something neither item is: a pull costs 160
        of one or 1 of the other, so the block totals what the two buy
        rather than how many are held. That is why it does not go
        through `_build_row`, whose totals are in an item's own units.
        """
        text = ttk.Frame(row)
        text.pack(side=tk.LEFT, anchor=tk.N)
        stat = tkfont.Font(font=STAT_FONT)
        text.grid_columnconfigure(1, minsize=self._value_column_px())
        text.grid_columnconfigure(
            0, minsize=max(stat.measure(word) for word, _p, _t
                           in GACHA_TARGETS) + LABEL_INSET_PX)

        ttk.Label(text, text=GACHA_LABEL, font=NAME_FONT,
                  foreground=self.colors["fg"],
                  padding=(0, NAME_PAD_TOP, 0, NAME_PAD_BOTTOM),
                  ).grid(row=0, column=0, columnspan=2)

        self.gacha_values = {}
        rows = ((TOTAL_LABEL, ""),
                *((word, tip) for word, _pulls, tip in GACHA_TARGETS))
        for line, (word, tip) in enumerate(rows, start=1):
            label = ttk.Label(text, text=word, font=STAT_FONT)
            label.grid(row=line, column=0, sticky="e",
                       padx=(0, LABEL_TO_VALUE))
            if tip:
                # On the LABEL, not the value: the words are what the
                # tooltip explains, and a value column reserved four
                # digits wide is mostly empty to hover over.
                self._tooltip.bind(label, tip)
            value = ttk.Label(text, text=NO_DATA, font=STAT_FONT,
                              anchor=tk.E)
            value.grid(row=line, column=1, sticky="ew")
            self.gacha_values[word] = value

        icons = ttk.Frame(row)
        icons.pack(side=tk.LEFT, anchor=tk.N, padx=(TEXT_TO_ICONS, 0))
        for position, res_id in enumerate(spec.gacha):
            label = self._make_icon_label(icons)
            label.grid(row=0, column=position, padx=ICON_GAP_HALF)
            self.material_icons[res_id] = label

    def _build_reserved_column(self, column):
        """The far-right column: one item per row, and no words beside.

        ONE child, not two. Both the spacing audit and
        `check_tabs_build` walk a column as `[heading, rows]` and read
        its title off the first child, so a column with no title stays
        out of their way by having no heading at all rather than by a
        special case in each of them.

        Its rows still line up with the icons beside them, and the
        leading pad is what does it: the height a heading takes plus
        the gap under one, read off a heading built and dropped rather
        than restated here as a number.

        The four MODULE rows all draw the same item and cannot go in
        `material_icons`, which is keyed by res_id -- each shows a
        different slice of the same holding, so they are kept in their
        own list against the window each counts.
        """
        probe = make_heading(column, "")
        top = probe.winfo_reqheight() + HEADING_GAP
        probe.destroy()

        rows = ttk.Frame(column)
        rows.pack(anchor=tk.N, pady=(top, 0))
        self.module_labels = []

        def add(line):
            row = ttk.Frame(rows)
            row.pack(anchor=tk.CENTER, pady=(0 if line == 0 else ROW_GAP, 0))
            label = self._make_icon_label(row)
            label.grid(row=0, column=0, padx=ICON_GAP_HALF)
            return label

        line = 0
        for res_id in RESERVED_ITEMS:
            label = add(line)
            if res_id is None:
                if self._reserved_tile is not None:
                    label.config(image=self._reserved_tile)
            else:
                self.material_icons[res_id] = label
            line += 1
        for hours, caption in MODULE_BUCKETS:
            self.module_labels.append((add(line), hours, caption))
            line += 1

    def _build_generic_row(self, row, index, spec, text_width):
        """The column's stand-in item, under its last row.

        The icon goes in the LAST icon column, under the bottom
        tier it substitutes for, and the checkbox sits immediately
        left of it. The cells before them are held open by empty
        frames of an icon's width, so the icon lands under that
        tier rather than at the row's left edge.
        """
        # Stands in for the figures block the data rows carry, so this
        # row is as wide as they are and its icon lands under the tier
        # it substitutes for.
        ttk.Frame(row, width=text_width, height=1).pack(
            side=tk.LEFT, anchor=tk.N)

        icons = ttk.Frame(row)
        icons.pack(side=tk.LEFT, anchor=tk.N, padx=(TEXT_TO_ICONS, 0))
        last = len(spec.tiers) - 1
        # Every cell the width an ICON's cell takes -- its own width
        # and the pad on both sides. A narrower cell would pull the
        # icon after it left of the tier it stands in for, which is the
        # column it has to sit under; `minsize` is a floor and a
        # checkbox does not reach it on its own.
        for position in range(last + 1):
            icons.grid_columnconfigure(
                position, minsize=ICON_SIZE[0] + 2 * ICON_GAP_HALF)
        for position in range(last):
            if position == last - 1:
                # spacing: label ↔ its element -- checkbox, frame ↔
                # Pushed against the icon rather than centred in
                # its own cell, so it reads as belonging to that
                # icon rather than to the row.
                make_checkbox(
                    icons, self.colors, text="Add to totals",
                    variable=self.include_generic_vars[index],
                    command=lambda i=index:
                        self._on_include_generic_toggle(i),
                ).grid(row=0, column=position, sticky="e",
                       padx=(ICON_GAP_HALF, GENERIC_TO_CHECKBOX))
                continue
            ttk.Frame(icons, width=ICON_SIZE[0], height=1).grid(
                row=0, column=position, padx=ICON_GAP_HALF)

        label = self._make_icon_label(icons)
        label.grid(row=0, column=last, padx=ICON_GAP_HALF)
        self.material_icons[spec.generic] = label

    def _make_icon_label(self, parent):
        """A Label carrying nothing of its own around the icon.

        `tk.Label` defaults to a 2px border and a pixel of padding on
        each side, all of it drawn in whatever the widget's background
        is -- which is the pale edge these icons had, and which no
        change to the assets would have removed.
        """
        return tk.Label(parent, bg=self.colors["bg"], fg=self.colors["fg"],
                        bd=0, highlightthickness=0, padx=0, pady=0)

    @staticmethod
    def _text_block_px(spec):
        """(the whole figures block, its label column) for one column.

        COMPUTED, not measured. Rows are right-anchored, so a block
        of the wrong width moves its row's icons off the tier columns
        above. Measuring the built rows cannot do it: a frame reports a
        requested width of 1 until Tk has processed the geometry, and
        forcing that mid-build means painting a half-built window.

        The widest of two things: the label column plus the reserved
        value column, and the row NAME above them, which spans both.
        """
        stat = tkfont.Font(font=STAT_FONT)
        name_font = tkfont.Font(font=NAME_FONT)
        figures = [TOTAL_LABEL] + [word for word, _cost in spec.targets]
        names = list(spec.names)
        if spec.levelling:
            label, _table, _group, _tiers, targets = spec.levelling
            figures += [word for word, _cost in targets]
            names.append(label)
        labels = max(stat.measure(word) for word in figures) + LABEL_INSET_PX
        widest_name = (max(name_font.measure(word) for word in names)
                       + LABEL_INSET_PX)
        value = MaterialsTab._value_column_px()
        # The pad between label and value belongs to the LABEL column:
        # it is that widget's `padx`, so grid counts it as content
        # there rather than adding it to the row. Computing the block
        # as `labels + pad + value` and the column as `block - pad -
        # value` looks like the same arithmetic and leaves the two two
        # pixels apart -- which is a row of icons two pixels out.
        label_column = max(labels + LABEL_TO_VALUE, widest_name - value)
        return label_column + value, label_column

    @staticmethod
    def _value_column_px():
        """The reserved width of the figures' column, in pixels.

        Measured rather than stated: a digit's advance is the font's,
        and the column has to hold `VALUE_DIGITS` of them plus the
        Label's own inset around them.
        """
        font = tkfont.Font(font=STAT_FONT)
        widest = max(font.measure("0" * VALUE_DIGITS),
                     font.measure(VALUE_WIDEST))
        return widest + LABEL_INSET_PX

    @staticmethod
    def _res_id_for(table, group, tier):
        """A table's id for one group and tier, or None."""
        for res_id, row in table.items():
            if row[0] == group and row[1] == tier:
                return res_id
        return None

    # ----------------------------------------------------------- update

    def _on_include_generic_toggle(self, index):
        """Remember one column's checkbox and redraw its figures."""
        sm = self.context.settings_manager
        if sm is not None:
            sm.set(include_generic_key(COLUMNS[index].key),
                   bool(self.include_generic_vars[index].get()))
        self._render_stats(self._quantities)

    def refresh_materials(self):
        """Redraw counts and figures from the loaded snapshot.

        Called automatically after data loads.
        """
        if not self.optimizer.raw_data:
            return
        inventory = self.optimizer.raw_data.get("inventory", {})
        quantities = {}
        for item in inventory.get("items", []):
            res_id = item.get("res_id")
            if res_id:
                quantities[res_id] = item.get("amount", 0)
        # The three generic items are CURRENCIES, which a snapshot
        # keeps apart from its item list -- so a column's stand-in
        # reads 0 from `items` alone however many are held.
        currencies = (self.optimizer.raw_data.get("characters")
                      or {}).get("currencies") or {}
        for key, record in currencies.items():
            try:
                quantities[int(key)] = record.get("amount", 0)
            except (TypeError, ValueError):
                continue
        # Period items carry no amount at all -- their copies are
        # LISTED, each with its own expiry -- so they come through
        # `period_items` rather than either source above.
        self._expiries = period_items.held(inventory)
        self._render_icons(quantities)

    def _render_icons(self, item_quantities: dict):
        """(Re)draw every icon and every figure beside it.

        `item_quantities` maps res_id -> owned amount; a missing entry
        is 0, which is also how the tab looks before any snapshot is
        loaded.
        """
        self._quantities = item_quantities
        for res_id, label in self.material_icons.items():
            self._draw_icon(label, res_id, item_quantities.get(res_id, 0))

        # The module's copies, split by how soon each expires. One
        # `now` for every bucket: reading the clock per row could put
        # a copy in two windows or in none.
        counts = _module_buckets(self._expiries.get(MODULE_ITEM, ()),
                                 time.time())
        for (label, _hours, caption), held in zip(self.module_labels, counts):
            self._draw_icon(label, MODULE_ITEM, held, caption)

        self._render_stats(item_quantities)

    def _draw_icon(self, label, res_id, quantity, caption=""):
        """One item's icon, its count, and any words over its corner.

        Through `item_art` rather than off a table row: the tables
        disagree about what their first fields mean and a row may or
        may not state a rarity, so the art is read by the one accessor
        that knows every shape.

        An item whose art is not in the repo draws its PLATE alone and
        still carries its count -- `item_art` gives it an empty icon
        name, which is not the same as an id no table knows.
        """
        images_dir = Path(__file__).parent.parent.parent / "images"
        art = item_art(res_id)
        icon_path = images_dir / art.icon if art and art.icon else None
        plate = (images_dir / RARITY_DIR / art.plate
                 if art and art.plate else None)
        drawable = art is not None and (icon_path is None
                                        or icon_path.exists())
        photo = (create_icon_with_quantity(
            str(icon_path) if icon_path else "", quantity,
            background=self.colors["bg"],
            plate_path=str(plate) if plate and plate.exists() else None,
            corner_text=caption, corner_font_px=CORNER_FONT_PX)
            if drawable else None)
        if photo is not None:
            label.config(image=photo, text="")
            label.image = photo       # Tk holds no reference of its own
        else:
            label.config(text=str(quantity), image="")

    def _render_stats(self, item_quantities: dict):
        """The figures under each row's name.

        Every one is derived from that row's own counts. The counts are
        looked up per row rather than accumulated, so a row cannot pick
        up a neighbour's holdings.

        The generic item is the exception, and only on a row that takes
        it and only when the checkbox asks: its stock is shared across
        the column, so adding it to each row counts it once per row
        rather than once. That is what the checkbox is for and why it
        is off by default. The EXP row never takes it -- a Certificate
        raises a ceiling and buys no exp.
        """
        for key, row in self.material_stats.items():
            index, _shown = key
            values, targets, table, group, tiers, weights, takes = row
            total = 0
            for tier in tiers:
                res_id = self._res_id_for(table, group, tier)
                if res_id is not None:
                    total += (weights.get(tier, 1)
                              * item_quantities.get(res_id, 0))
            var = self.include_generic_vars.get(index)
            if takes and var is not None and var.get():
                generic = self._column_generics.get(index)
                if generic is not None:
                    total += item_quantities.get(generic, 0)
            values[TOTAL_LABEL].config(text=str(total))
            for label, cost in targets:
                # An unpriced target reads `-`: a percentage of a cost
                # nobody has given is a number with nothing behind it.
                values[label].config(
                    text=NO_DATA if not cost else f"{100 * total // cost}%")

        # The gacha block counts PULLS, which is neither currency's own
        # unit -- see `gacha_pulls`.
        if getattr(self, "gacha_values", None):
            pulls = gacha_pulls(item_quantities)
            self.gacha_values[TOTAL_LABEL].config(text=str(pulls))
            for label, needed, _tip in GACHA_TARGETS:
                self.gacha_values[label].config(
                    text=f"{_rounded_percent(pulls, needed)}%")

        for values, res_ids in self.advanced_stats.values():
            for label, costs in advanced_costs():
                for cell, res_id, cost in zip(values[label], res_ids, costs):
                    # Each against its OWN stock, and against the cost
                    # ACCUMULATED down its own column. Nothing crosses
                    # between items: a total across them would price a
                    # swap that cannot be made.
                    held = item_quantities.get(res_id, 0)
                    cell.config(text=NO_DATA if not cost
                                else f"{100 * held // cost}%")
