"""Stats & Gacha History tab: every pull the game has listed, how lucky
it was, and the account's Sortie, Great Rift and Full-Scale Offensive
standings.

`gacha_history.py` does the gacha reading and arithmetic, and
`stats_history.py` the standings'; this draws them. Two lists side by
side: one row per banner family with its luck on the left, and the pulls
of whichever family is selected, newest first. Under the banners, the
gacha figures across banners, and beside them a list per standing with
a column per season.

**Nothing is read until the tab is first shown.** The luck figures are
an exact convolution over every 5-star the history holds, which is a
few tenths of a second the first time -- spent at startup, that would
be on every launch whether or not anyone opens the tab.
"""

import json
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from types import SimpleNamespace

import gacha_history as gh
import stats_history as sh
from capture.constants import OUTPUT_DIR
from game_data.constants import RARITY_COLORS
from ui.scaling import px, px_after
from ..base_tab import BaseTab
from ..utils.button_width import BUTTON_W_MEDIUM
from ..utils.panel_title import panel_title_style
from ..utils.style_once import first_time
from ..utils.tooltip import HOVER_CURSOR, Tooltip

# The instructions under the tab strip, in the Optimizer's explanation
# style. `HELP_WRAPLENGTH` is where the text starts wrapped: wider than
# its longest line, so the default window shows the three lines whole
# and the first rewrap moves nothing. A narrower window rewraps.
HELP_WRAPLENGTH = 900
HELP_TEXT = (
    "Important! The game erases records that are older than about half "
    "a year! You can import hub-czn's Export JSON.\n"
    "To use: Start a capture. In game open each banner's Probability "
    "Info > Rescue Records. Page through to the last page! Do this for "
    "each banner: they are separate!"
)

# (label, the rarities it shows). None shows everything.
FILTERS = (("All pulls", None), ("4★ and 5★", {4, 5}),
           ("5★ only", {5}))

def _unit_names():
    """Every name a unit column can show, for sizing one."""
    from game_data import CHARACTERS, PARTNERS
    return [unit["name"] for table in (CHARACTERS, PARTNERS)
            for unit in table.values()
            if isinstance(unit, dict) and unit.get("name")] + ["#99999"]


# (id, heading, the widest things it will hold, anchor). **Widths are
# MEASURED** from those, in the list's own fonts, so a column fits its
# text at either scale and nothing here is a pixel count. A callable is
# read when the list is built. The LAST column of each list stretches.
SUMMARY_COLUMNS = (
    ("banner", "Banner", tuple(gh.POOL_LABELS.values()) + (gh.SKIN_LABEL,),
     tk.W),
    ("pulls", "Pulls", ("99,999",), tk.E),
    ("fives", "5★", ("999",), tk.E),
    ("avg", "Avg 5★ pull", ("99.9",), tk.E),
    ("game", "Expected avg", ("99.9",), tk.E),
    ("luck", "Luck", ("Bottom 50%", "Bottom 0.1%", "Bottom <0.1%"), tk.E),
    ("fifty", "50/50 won", ("99 of 99",), tk.E),
    ("fours", "4★", ("9999",), tk.E),
    ("four_avg", "Avg 4★ pull", ("99.9",), tk.E),
    ("pity", "Pity now", ("99",), tk.E),
    ("read", "Last read", ("0000-00-00 00:00",), tk.W),
)
PULL_COLUMNS = (
    ("number", "#", ("99999",), tk.E),
    ("unit", "Unit", _unit_names, tk.W),
    ("stars", "Rarity", ("5★",), tk.CENTER),
    ("pull", "Pull", ("70",), tk.E),
    ("featured", "Rate-up", _unit_names, tk.W),
    ("outcome", "50/50", (gh.WON, gh.LOST, gh.GUARANTEED, gh.RATE_UP,
                          gh.UNKNOWN, gh.DUPLICATE), tk.W),
    ("time", "Time", ("0000-00-00 00:00",), tk.W),
)

# This tab's lists, styled apart from every other list in the app. Text
# sits TEXT_INSET in from its column's edges, in a cell and a heading
# alike, so a heading lines up with its cells.
#
# **Between two columns sits an empty one, COLUMN_GAP wide.** Tk's
# padding is one pair of values for every column of a list, so it
# cannot keep the outermost columns close to the list's edges and the
# rest far apart; a spacer can. A column is exactly as wide as its
# widest text plus the inset on both sides, so the tightest two columns'
# text is `2 * TEXT_INSET + COLUMN_GAP` apart. Any column's slack lands
# on the side away from its anchor, and only widens that.
TREE_STYLE = "GachaHistory.Treeview"
TEXT_INSET = 3
COLUMN_GAP = 18
# The Pulls list's spacer, narrower: the width it gives up goes to the
# Banners list's last column (`_fit_banners`), and so to the gacha sheet
# and the standings under it.
PULLS_COLUMN_GAP = 4
# The standings' spacer, narrower: their columns are short figures that
# read as one table, where the banners' are separate facts.
STANDINGS_COLUMN_GAP = 8
# The heading's height is left as the shared style has it.
HEADING_INSET_V = 3
# This tab's rows are shorter than every other list's: it is what lets
# the standings fit under the gacha sheet in the default window. Still
# clear of Segoe UI 9's 15px line box, below which a row clips its text.
LIST_ROW_HEIGHT = 19
# The Banners list shows at most this many rows and scrolls past them:
# with every banner family listed, the standings under it would run past
# the default window's bottom edge.
BANNER_ROWS = 6

# Row colours by rarity. A unit's stars index the rarity table
# directly -- 5 Mythic, 4 Legendary, 3 Rare. A unit neither the game's
# rate lists nor the tables know is drawn loudly, in a colour no
# rarity has: its pity, and every pity after it, rest on nobody
# knowing whether it was a 5-star.
STAR_COLOURS = {stars: RARITY_COLORS[stars] for stars in (5, 4, 3)}
UNKNOWN_COLOUR = "red"

NO_VALUE = "-"

# A banner type the game has newer pulls for is drawn orange, and red
# where its records were last read more than `URGENT_AFTER_DAYS` ago --
# the pulls it is missing may be halfway to the game erasing them. A
# line at the toolbar's right end says what each colour means. A
# coloured row rather than words in `Last read`: at this tab's column
# inset, the width those words took was what kept the two lists from
# fitting the default window.
BEHIND_TAG = "behind"
URGENT_TAG = "urgent"
BEHIND_NOTE = "Orange banners have unread pulls"
# A banner whose records were read without reaching the ones kept is
# drawn the same orange: the pulls between are as unread.
GAP_NOTE = ("Orange banners may be missing pulls: their Rescue Records "
            "were read without reaching the ones kept. Scroll them back "
            "further.")
URGENT_NOTE = ("⚠ Red banners were last read over %d days ago.\n"
               "Read them NOW, before the game erases their history!"
               % gh.URGENT_AFTER_DAYS)
URGENT_FONT = ("Segoe UI", 9, "bold")

# Where the status lines wrap, so a long one takes height from the
# toolbar rather than width from the help text beside it.
STATUS_WRAPLENGTH = 320
# The status lines' label style: a `TLabel`'s own inset above and below,
# none at the sides. They end the toolbar at the window's right edge,
# and a plain `TLabel` would set their text 2px short of the pads that
# put it the window-edge rule's distance in.
STATUS_STYLE = "GachaHistory.Status.TLabel"

# The figures across banners, under the Banners list: (figure, value,
# units, date) rows in three sections, each opened by a bold heading.
# `gh.Overall` says why the Prism Module is kept apart.
#
# **A Text, not a list**, because these are label rows: rows sit
# `label row -> label row` apart and a heading further from the row
# above it, where a Treeview's rows are all one height and nothing
# reaches between them. The columns are TAB STOPS, measured from what
# the sheet holds and each only from the rows with something after it:
# a luck row's long value has nothing beside it, so it does not push
# the units column out.
OVERALL_TITLE = "Overall Gacha Stats"
WITHOUT_PRISM = "Combatant & Partner banners"
PRISM_ONLY = "Prism Module"
WITH_PRISM = "+Prism Module"
WITH_SKINS = "+Card Skins"
SKINS_ONLY = gh.SKIN_LABEL
# Beside the Card Skin Packs' heading, as a standings title's note: what
# to open in game to fill their records.
SKINS_NOTE = "Shop > Lumina Theater > Probability Info > Pack Purchase History"
HEADING_FONT = ("Segoe UI", 9, "bold")
STREAK = "Most 5★ in %d pulls"
# The room every section's columns keep (`_reserve`): a record's widest
# value, then this many ties, each a date and units as wide as one of
# the longest combatant names, the longest first. A section's columns
# sit at least that far apart whatever it holds, so the second column
# stays put as the records change, and a tie past the room runs under
# the Pulls list.
WIDEST_COUNT = "99 pulls"
WIDEST_DATE = "0000-00-00"
SET_NAMES = 3

# Under it, the account's standings: three lists with a column per
# season, newest first, and the rows' names held still at the left --
# the Great Rift's up to the Banners list's width, then the Full-Scale
# Offensive's and the Sortie's side by side at the window's foot, each
# showing as many seasons as the other (`_share`). The
# tables are `sh.sortie_table`, `sh.rift_table` and `sh.offensive_table`,
# over the loaded snapshot's ranking history and whatever
# `stats_history.py` read out of the captures from before snapshots
# kept it.
#
# **A list grows a column a season and stops at its room**, past which
# its seasons scroll sideways. Held at its room instead, a list of two
# seasons is mostly empty heading, with a scrollbar under it that has
# nothing to scroll.
SORTIE_TITLE = "Sortie Stats"
RIFT_TITLE = "Great Rift Stats"
OFFENSIVE_TITLE = "Full-Scale Offensive Stats"
# Beside each title: what to open in game to fill the list.
SORTIE_NOTE = ("Start a capture. Open Sortie. Press Hardcore Rankings, "
               "then Previous Sortie Ranking.")
RIFT_NOTE = ("Start a capture. Go to the Great Rift. Open Merit Ranking. "
             "Press each division.")
OFFENSIVE_NOTE = "Start a capture. Open the Full-Scale Offensive."
# A Great Rift division's row, in the division's colour -- lightened
# where the plain one reads dim on this background.
DIVISION_COLOURS = {"Master": "#ee62c0", "Diamond": "#b998fa",
                    "Platinum": "#bbddaa", "Gold": "#f5d7a2",
                    "Silver": "#6cb6f0", "Bronze": "#d68c79"}
DIVISION_TAG = "division_%s"
# The heading over the rows' names, which says what the columns are.
SEASON_HEADING = "Season"
# A row's tip, by the row's name: the score each star of an Offensive
# stage asks for, once, on the first stage's row.
ROW_TIPS = {sh.OFFENSIVE_ROWS[-sh.OFFENSIVE_STAGES]: "\n".join(
    "%s %s Score" % (sh.STARS % stars, format(score, ","))
    for stars, score in sh.OFFENSIVE_STAR_SCORES)}
# What underlines a row's name where it has a tip: the mark
# `Tooltip.mark` gives a widget, on a row.
TIP_TAG = "tipped"
# A title's leading pad against the panel above it, the lever on
# `panel ↕ unrelated label`. Under the gacha sheet it is less than
# under a list: the sheet's last line box already reaches past its
# baseline by more than a list does past its last row. Under the sheet
# it is also 4 past the rule, as the sheet's own title is (`_make_sheet`).
UNDER_SHEET_PAD = 6    # spacing: exception -- panel ↕ unrelated label -- run, title ↕
UNDER_LIST_PAD = 5     # spacing: panel ↕ unrelated label -- panel, title ↕

# One pitch tag per line, setting its `spacing1` -- the line's own word
# for what sits above it. Tk resolves two tags setting one option by
# priority rather than by sum, so a pad stacked on another tag would
# hang on the order the tags were made in. The first heading takes
# `TOP_TAG`: it crosses nothing, so nothing is charged above it.
ROW_TAG = "row"
HEADING_TAG = "heading"
TOP_TAG = "top"
BOLD_TAG = "bold"
# A noted heading's note, in a standings title's note's colour.
NOTE_TAG = "note"
# A `Beside` line's own stops, one tag per line.
BESIDE_TAG = "beside%d"

# Levers a rendered distance short of their rules: a Text line's box
# already carries part of the gap, and `spacing1` cannot go negative.
ROW_PITCH = 4           # spacing: label row -> label row -- run, run ↕
# A heading stands 4 further from the row above it than rows do from
# one another, so each section reads as a block of its own.
HEADING_PAD = 4         # spacing: exception -- label row -> label row -- run, run ↕
# The panel's title against the first heading, read as two label rows.
TITLE_GAP = 2           # spacing: label row -> label row -- title, run ↕

# The columns. A record is followed by every tie for it as a (units,
# date) pair, the units labelling their date and one pair sitting
# beside the next -- as many pairs as fit the Banners list's width,
# oldest first.
FIGURE_TO_VALUE = 5     # spacing: label ↔ its element -- run, run ↔
VALUE_TO_UNITS = 8      # spacing: element and its label ↔ element and its label -- run, run ↔
UNITS_TO_DATE = 5       # spacing: label ↔ its element -- run, run ↔
TIE_TO_TIE = 8          # spacing: element and its label ↔ element and its label -- run, run ↔
# A section set beside another on the same lines -- every banner's, by
# the first section's opening lines -- starts this far past the furthest
# of them, and its own rows keep the sheet's figure-to-value gap.
BESIDE_GAP = 16         # spacing: control group ↔ control group -- run, run ↔
# A noted heading's note, past the heading as a standings title's note
# sits past its title.
NOTE_GAP = 14           # spacing: header subtext -- label, label ↔


class Beside:
    """One line of the gacha sheet holding several sections' lines side
    by side: `parts`, each a heading's string or a row's fields. The
    first keeps the sheet's stops; each after it starts past the one
    before, on stops the line carries itself, and a run of these lines
    is laid out together (`GachaHistoryTab._overall_layout`)."""

    def __init__(self, *parts):
        self.parts = parts

    @property
    def left(self):
        return self.parts[0]


class Paired:
    """A line of the gacha sheet with a part in its second column as
    well: `left` any line, `right` a heading, a `Noted` heading or a
    row's fields. The second column holds the Prism Module's records on
    the Combatant & Partner banners' first lines and the Card Skin
    Packs' on their last. It starts `right_width` short of the sheet's
    room, at a width measured once (`_right_width`)."""

    def __init__(self, left, right):
        self.left, self.right = left, right


def _paired(rows, top, bottom):
    """`rows` with `top`'s parts paired onto the first of them and
    `bottom`'s onto the last, line for line, so the second column starts
    and ends on the first column's lines. A block that would overlap the
    one above it starts under it instead, and a part past the last row
    is left out."""
    first = max(len(top), len(rows) - len(bottom))
    right = dict(enumerate(top))
    right.update({first + n: part for n, part in enumerate(bottom)})
    return tuple(Paired(row, right[n]) if n in right else row
                 for n, row in enumerate(rows))


def _left(row):
    """A line's first-column part: itself unless it is `Paired`."""
    return row.left if isinstance(row, Paired) else row


class Noted:
    """A heading of the gacha sheet with a note beside it, in a
    standings title's note's colour and gap: `NOTE_TAG`, `NOTE_GAP`."""

    def __init__(self, heading, note):
        self.heading, self.note = heading, note


def _heading(part):
    """Whether a sheet part is a heading, noted or not."""
    return isinstance(part, (str, Noted))


def _stars(stars):
    return "%d★" % stars if stars else "?"


def _number(value, digits=1):
    return NO_VALUE if value is None else "%.*f" % (digits, value)


def _when(epoch):
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def _rank(luckier):
    return gh.luck_rank(luckier) or NO_VALUE


def _standout(records, streak=False):
    """(value, units, date, units, date, ...) for one of `gh.Overall`'s
    records: its value once, then a pair for every tie, oldest first. A
    streak counts 5-stars; the rest count pulls. A date is its last
    5-star's, when the record was set."""
    if not records:
        return (NO_VALUE,)
    count = records[0].count
    value = str(count) if streak else "%d pull%s" % (
        count, "" if count == 1 else "s")
    pairs = ()
    for record in records:
        day = datetime.fromtimestamp(record.pulls[-1].at).strftime(
            "%Y-%m-%d")
        pairs += (_units(record.pulls), day)
    return (value,) + pairs


def _units(pulls):
    """`Diana x2, Heidemarie`: each unit once, in the order it first
    came, counted where it came more than once."""
    counts = {}
    for pull in pulls:
        name = gh.unit_name(gh.skin_wearer(pull.res_id)
                            if pull.pool == gh.SKIN_POOL else pull.res_id)
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(name if n == 1 else "%s x%d" % (name, n)
                     for name, n in counts.items())


def _style_status():
    """The status lines' label style, once per interpreter -- see
    `ui/utils/style_once.py`.

    A layout's `border` is a flag -- the element surrounds its
    children -- and the inset is the style's `padding`: here a label's
    own 2 above and below, and none at the sides. No `try`: a refused
    layout leaves the dotted name on `TLabel`'s, which looks like no
    change at all.
    """
    style = ttk.Style()
    if not first_time(style, STATUS_STYLE):
        return
    style.layout(STATUS_STYLE, [("Label.padding", {
        "sticky": "nswe", "border": "1",
        "children": [("Label.label", {"sticky": "nswe"})]})])
    # spacing: unique -- a label's own inset, a style option -- label, label ↕
    style.configure(STATUS_STYLE, padding=px((0, 2)))


def register_styles():
    """Every style this tab defines, for the app to define at startup,
    before anything is laid out. See `ui/utils/style_once.py`."""
    _style_status()
    GachaHistoryTab._style_lists()


class GachaHistoryTab(BaseTab):
    """The Stats & Gacha History tab."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.history = None
        # What `stats_history.py` read out of old captures, or None.
        self.stats = None
        self._loaded = False
        self._pool = None               # the family the pulls list shows
        self._natural = {}              # see `_make_tree`
        self._body_width = None         # see `_share_excess`
        self.tooltip = Tooltip(self.colors)
        self._tip_font = None           # see `_underlined`
        self._row_tip_at = None         # see `_row_tip`
        self._right_cached = None       # see `_right_width`
        self._reserve_cached = None     # see `_reserve`
        self._wide = False              # see `_place_pair`
        self.setup_ui()
        self.frame.bind("<Map>", self._first_show, add="+")

    # ------------------------------------------------------------ layout

    def setup_ui(self):
        # Built inside an unmapped container and packed last, so the tab
        # appears once, settled -- see the Optimizer's setup_ui.
        content = ttk.Frame(self.frame)

        toolbar = ttk.Frame(content)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # A pad that ENDS a run another began -- content's 2 at the tab's
        # edges, a neighbour's 2 or 5 between panels -- takes `px_after`
        # here and below, so each gap is scaled once.
        toolbar.pack(fill=tk.X, padx=(px_after(2, 2), px_after(2, 2)),
                     pady=px((0, 0)))

        # The buttons and the filter as one group, so its top pad is the
        # whole lever on their distance from the tab list. On the
        # toolbar it would move the help text too, which its own line
        # box already seats where the rule wants it. Its bottom pad is
        # the lever on the Banners and Pulls titles under it -- the
        # gacha sheet's pads against the banners, since both a button
        # and a list end in a painted edge -- while the help text beside
        # it is no taller than the group.
        controls = ttk.Frame(toolbar)
        # spacing: tab list -> first element -- tab, button ↕
        # spacing: tab list -> first element -- tab, dropdown ↕
        # spacing: panel ↕ unrelated label -- button, title ↕
        controls.pack(side=tk.LEFT, anchor=tk.N,
                      pady=(px_after(1, 5), px(5)))

        import_btn = ttk.Button(controls, text="Import JSON",
                                command=self._import, width=BUTTON_W_MEDIUM)
        # spacing: button -> button -- button, button ↔
        import_btn.pack(side=tk.LEFT, anchor=tk.N, padx=px((0, 4)))
        ttk.Button(controls, text="Export JSON", command=self._export,
                   width=BUTTON_W_MEDIUM).pack(side=tk.LEFT, anchor=tk.N)

        show = ttk.Frame(controls)
        # spacing: control group ↔ control group -- button, label ↔
        show.pack(side=tk.LEFT, anchor=tk.N, padx=px((14, 0)))
        ttk.Label(show, text="Show:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value=FILTERS[0][0])
        filter_box = ttk.Combobox(
            show, textvariable=self.filter_var, state="readonly",
            values=[word for word, _stars in FILTERS],
            width=max(len(word) for word, _stars in FILTERS) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        filter_box.pack(side=tk.LEFT, padx=px((2, 0)))
        filter_box.bind("<<ComboboxSelected>>",
                        lambda _e: self._fill_pulls())

        # The status lines, stacked at the toolbar's right end: the two
        # warnings, most severe first, then anything else there is to
        # say. `_show_status` packs only those with something to say.
        status = ttk.Frame(toolbar)
        status.pack(side=tk.RIGHT, anchor=tk.N)
        # A layout's `border` is a flag -- the element surrounds its
        # children -- and the inset is the style's `padding`: here a
        # label's own 2 above and below, and none at the sides. No `try`:
        # a refused layout leaves the dotted name on `TLabel`'s, which
        # looks like no change at all.
        _style_status()
        self.urgent_label = ttk.Label(
            status, text="", font=URGENT_FONT, style=STATUS_STYLE,
            foreground=self.colors["red"],
            wraplength=px(STATUS_WRAPLENGTH))
        self.behind_label = ttk.Label(
            status, text="", style=STATUS_STYLE,
            foreground=self.colors["orange"],
            wraplength=px(STATUS_WRAPLENGTH))
        self.gap_label = ttk.Label(
            status, text="", style=STATUS_STYLE,
            foreground=self.colors["orange"],
            wraplength=px(STATUS_WRAPLENGTH))
        self.status_label = ttk.Label(
            status, text="", style=STATUS_STYLE,
            foreground=self.colors["fg_dim"],
            wraplength=px(STATUS_WRAPLENGTH))

        help_label = ttk.Label(
            toolbar, text=HELP_TEXT, justify=tk.LEFT,
            foreground=self.colors["fg_dim"],
            wraplength=px(HELP_WRAPLENGTH))
        # spacing: control group ↔ control group -- dropdown, label ↔
        help_label.pack(side=tk.LEFT, padx=px((14, 0)), fill=tk.X,
                        expand=True, anchor=tk.N)
        help_label.bind("<Configure>", self._rewrap)

        # The two lists side by side: the banners at their own width on
        # the left with the figures across them beneath, the pulls taking
        # whatever the window has left. The Great Rift's row takes the
        # slack, so the figures and that list sit right under the
        # banners, and the Offensive's and the Sortie's lists at the
        # window's foot -- under the pulls list too where their seasons
        # need the room (`_place_pair`).
        body = ttk.Frame(content)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(2, weight=1)
        body.bind("<Configure>", self._share_excess, add="+")

        summary_frame = ttk.LabelFrame(body, text="Banners",
                                       padding=px(0),
                                       style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- label, title ↕
        summary_frame.grid(row=0, column=0, sticky="nw",
                           padx=(px_after(2, 2), px(2)),
                           pady=(px_after(5, 2), px(2)))
        self.summary_tree = self._make_tree(summary_frame, SUMMARY_COLUMNS,
                                            height=1)
        self.summary_tree.pack(side=tk.LEFT, fill=tk.X)
        # Packed only while there are more families than `BANNER_ROWS`.
        self.summary_scroll = ttk.Scrollbar(
            summary_frame, orient=tk.VERTICAL,
            command=self.summary_tree.yview)
        self.summary_tree.configure(yscrollcommand=self.summary_scroll.set)
        self.summary_tree.bind("<<TreeviewSelect>>", self._on_pick)
        self.summary_tree.tag_configure(BEHIND_TAG,
                                        foreground=self.colors["orange"])
        self.summary_tree.tag_configure(URGENT_TAG,
                                        foreground=self.colors["red"])

        self.overall_holder, self.overall_text = self._make_sheet(body,
                                                                  row=1)
        self.rift_list = self._make_standings(
            body, RIFT_TITLE, RIFT_NOTE, row=2, column=0,
            top=UNDER_SHEET_PAD)
        # The Offensive's and the Sortie's lists share a row of their
        # own at the foot, their tops level: the Offensive's, the taller,
        # ends at the window's foot. Unpadded -- the panels in it carry
        # their pads, so they line up with the banners' edges.
        self.pair = ttk.Frame(body)
        self.pair.grid(row=3, column=0, sticky="sw")
        self.offensive_list = self._make_standings(
            self.pair, OFFENSIVE_TITLE, OFFENSIVE_NOTE, row=0, column=0,
            top=UNDER_LIST_PAD, last=True)
        self.sortie_list = self._make_standings(
            self.pair, SORTIE_TITLE, SORTIE_NOTE, row=0, column=1,
            top=UNDER_LIST_PAD, last=True)
        # Written now, with nothing read. The gacha sheet is then already
        # its full height, and only its width moves when the history
        # arrives; the standings are always as tall as their rows.
        self._fill_overall()
        self._fill_standings()

        self.pulls_frame = ttk.LabelFrame(body, text="Pulls",
                                          padding=px(0),
                                          style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- label, title ↕
        self.pulls_frame.grid(row=0, column=1, rowspan=4, sticky="nsew",
                              padx=(px_after(2, 2), px_after(2, 2)),
                              pady=(px_after(5, 2), px_after(2, 2)))
        self.pulls_tree = self._make_tree(self.pulls_frame, PULL_COLUMNS,
                                          height=20, gap=PULLS_COLUMN_GAP)
        self.pulls_scroll = ttk.Scrollbar(self.pulls_frame,
                                          orient=tk.VERTICAL,
                                          command=self.pulls_tree.yview)
        self.pulls_tree.configure(yscrollcommand=self.pulls_scroll.set)
        # The scrollbar first (`docs/ui_runtime.md`): a list packed
        # before it takes its width wherever the list is too wide.
        self.pulls_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.pulls_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for stars, colour in STAR_COLOURS.items():
            self.pulls_tree.tag_configure(self._star_tag(stars),
                                          foreground=colour)
        self.pulls_tree.tag_configure(
            self._star_tag(None), foreground=self.colors[UNKNOWN_COLOUR])

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        content.pack(fill=tk.BOTH, expand=True, padx=px(2), pady=px((1, 2)))

    def _make_sheet(self, parent, row):
        """(holder, Text) for the gacha sheet under the banners."""
        frame = ttk.LabelFrame(parent, text=OVERALL_TITLE, padding=px(0),
                               style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: exception -- panel ↕ unrelated label -- panel, title ↕
        # The leading pad is the lever on the gap from the panel above
        # to this title; the banners keep the 2 every panel on this tab
        # has. 4 past the rule, as the title of the Great Rift's list
        # under the sheet is (`UNDER_SHEET_PAD`): the sheet is label rows
        # on the window's own background, and at the rule its title and
        # the Great Rift's read as two more of its rows.
        frame.grid(row=row, column=0, sticky="nw",
                   padx=(px_after(2, 2), px(2)),
                   pady=(px_after(2, 9), px(2)))
        # A Text sizes in characters and lines, and a sheet is sized in
        # pixels -- its rows carry `spacing1` a line count cannot see --
        # so the holder is sized and the Text fills it. See
        # `_write_sheet`.
        holder = tk.Frame(frame, bg=self.colors["bg"], width=1, height=1)
        holder.pack_propagate(False)
        # spacing: label row -> label row -- title, run ↕
        holder.pack(anchor=tk.W, pady=px((TITLE_GAP, 0)))
        text = tk.Text(
            holder, wrap=tk.NONE, bd=0,
            highlightthickness=px(0), padx=px(0), pady=px(0),
            bg=self.colors["bg"], fg=self.colors["fg"],
            font="TkDefaultFont", takefocus=0, insertwidth=px(0),
            cursor="arrow", selectbackground=self.colors["select"],
            selectforeground=self.colors["fg"])
        text.pack(fill=tk.BOTH, expand=True)
        # spacing: label row -> label row -- run, run ↕
        text.tag_configure(ROW_TAG, spacing1=px(ROW_PITCH))
        # spacing: exception -- label row -> label row -- run, run ↕
        text.tag_configure(HEADING_TAG, spacing1=px(ROW_PITCH + HEADING_PAD))
        text.tag_configure(TOP_TAG, spacing1=px(0))
        text.tag_configure(BOLD_TAG, font=HEADING_FONT)
        text.tag_configure(NOTE_TAG, foreground=self.colors["fg_dim"])
        return holder, text

    def _make_standings(self, parent, title, note, row, column, top,
                        last=False):
        """One standings list, as its parts: the rows' names in a list of
        their own, and the seasons in a list beside it that scrolls
        sideways once it reaches its room. Two lists, because a Treeview
        cannot hold one column still while the rest scroll; they share
        this tab's list style, so their rows and headings line up.
        """
        self._style_lists()
        frame = ttk.LabelFrame(parent, padding=px(0),
                               style="Borderless.TLabelframe")
        # A labelwidget, so the note sits on the title's line. It
        # bypasses the label style, so the title's colour is set here,
        # as the Optimizer's Results panel does -- and both labels take
        # the panel title style, which seats the title where a `text=`
        # title sits (`ui/utils/panel_title.py`).
        header = ttk.Frame(frame)
        ttk.Label(header, text=title, style=panel_title_style(),
                  foreground=self.colors["accent"]).pack(side=tk.LEFT)
        hint = ttk.Label(header, text=note, style=panel_title_style(),
                         foreground=self.colors["fg_dim"])
        # The whole gap between the two: neither label insets its text.
        # spacing: header subtext -- label, label ↔
        hint.pack(side=tk.LEFT, padx=px((14, 0)))
        frame.configure(labelwidget=header)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # `top` is the lever on this title against the panel above it,
        # which differs by what that panel ends in -- see
        # `UNDER_SHEET_PAD`.
        # `last`: the bottom row, whose trailing pad follows content's.
        frame.grid(row=row, column=column, sticky="nw",
                   padx=(px_after(2, 2), px(2)),
                   pady=(px_after(2, top),
                         px_after(2, 2) if last else px(2)))
        lists = ttk.Frame(frame)
        # spacing: title above, element below -- title, tree ↕
        lists.pack(anchor=tk.W, pady=px((0, 0)))
        labels = ttk.Treeview(lists, columns=("label", "gap"),
                              show="headings", height=1, selectmode="none",
                              style=TREE_STYLE, takefocus=0)
        labels.heading("label", text=SEASON_HEADING, anchor=tk.W)
        labels.heading("gap", text="")
        labels.column("label", anchor=tk.W, stretch=False)
        # The spacer every two columns of this tab's lists have, here
        # between the names and the first season.
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
        labels.column("gap", width=px(STANDINGS_COLUMN_GAP),
                      minwidth=px(STANDINGS_COLUMN_GAP), stretch=False)
        labels.grid(row=0, column=0, sticky="nw")
        labels.tag_configure(TIP_TAG, font=self._underlined())
        labels.bind("<Motion>", lambda e, t=labels: self._row_tip(t, e.y),
                    add="+")
        labels.bind("<Leave>", lambda e, t=labels: self._row_tip(t, None),
                    add="+")
        # The seasons' list is as wide as its holder, which
        # `_size_standings` sets: narrower than its columns, it scrolls.
        holder = tk.Frame(lists, bg=self.colors["bg"], width=1, height=1)
        holder.pack_propagate(False)
        holder.grid(row=0, column=1, sticky="nw")
        data = ttk.Treeview(holder, show="headings", height=1,
                            selectmode="none", style=TREE_STYLE, takefocus=0)
        data.pack(fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(lists, orient=tk.HORIZONTAL,
                               command=data.xview)
        data.configure(xscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ew")
        scroll.grid_remove()
        for tree in (labels, data):
            for division, colour in DIVISION_COLOURS.items():
                tree.tag_configure(DIVISION_TAG % division,
                                   foreground=colour)
        return SimpleNamespace(frame=frame, header=header, labels=labels,
                               holder=holder, data=data, scroll=scroll)

    def _underlined(self):
        """The lists' row font, underlined. Held, as `Tooltip.mark`
        holds its own: Tk deletes a named font once its Python object
        is collected, and the row would fall back to a default face."""
        if self._tip_font is None:
            spec = ttk.Style().lookup(TREE_STYLE, "font") or "TkDefaultFont"
            self._tip_font = tkfont.Font(root=self.frame, font=spec)
            self._tip_font.configure(underline=True)
        return self._tip_font

    def _row_tip(self, tree, y):
        """Put up, or take down, the tip of the row under the pointer.

        A row is neither a widget nor a tagged range of a Text, so its
        hover is followed through `<Motion>`, as a Memory Fragments
        heading's is, and the pointer turns to `HOVER_CURSOR` over it.
        `y` None is the pointer leaving the list.
        """
        row = tree.identify_row(y) if y is not None else ""
        tip = ROW_TIPS.get(tree.set(row, "label")) if row else None
        at = (tree, row) if tip else None
        if at == self._row_tip_at:
            return
        self._row_tip_at = at
        self.tooltip.hide()
        tree.configure(cursor=HOVER_CURSOR if tip else "")
        if tip:
            self.tooltip.schedule(tree, tip)

    @staticmethod
    def _style_lists():
        """This tab's list style: the shared one, with its own text
        insets and row height. Everything else, the layout and colours
        included, falls through to `Treeview` and `Treeview.Heading`.

        **An empty foreground map, and NOT a no-op.** A style's state
        map outranks a row's tag colour, and `Treeview` maps `selected`
        to the plain foreground -- so without this a selected row loses
        its rarity or warning colour. The first style in the chain that
        maps an option answers for it alone, so an empty map here stops
        the lookup before it reaches `Treeview`'s. Removing the line
        changes nothing `style.map` can show; the check probes the
        lookup itself.
        """
        style = ttk.Style()
        # Once per interpreter, and at startup in the app: see
        # `ui/utils/style_once.py` for what a second definition costs
        # every tab already laid out.
        if not first_time(style, TREE_STYLE):
            return
        style.map(TREE_STYLE, foreground=[])
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
        style.configure(TREE_STYLE,
                        padding=px((TEXT_INSET, 0, TEXT_INSET, 0)))
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↕
        style.configure(TREE_STYLE, rowheight=px(LIST_ROW_HEIGHT))
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
        style.configure(TREE_STYLE + ".Heading",
                        padding=px((TEXT_INSET, HEADING_INSET_V,
                                    TEXT_INSET, HEADING_INSET_V)))

    def _make_tree(self, parent, columns, height, gap=COLUMN_GAP):
        """A list of `columns`, each `gap` from the next."""
        self._style_lists()
        ids = []
        for index, (col, _title, _samples, _anchor) in enumerate(columns):
            if index:
                ids.append(self._spacer(index))
            ids.append(col)
        tree = ttk.Treeview(parent, columns=ids, show="headings",
                            height=height, selectmode="browse",
                            style=TREE_STYLE)
        # Measured, so no `px()` on the text's share -- the fonts already
        # carry the scale. The inset is a distance and takes it.
        cell = tkfont.nametofont("TkDefaultFont")
        head = tkfont.nametofont("TkHeadingFont")
        for index, (col, title, samples, anchor) in enumerate(columns):
            samples = samples() if callable(samples) else samples
            width = max([head.measure(title)]
                        + [cell.measure(text) for text in samples]) \
                + px(2 * TEXT_INSET)
            # A heading takes its column's anchor: left to Tk it centres
            # over a right-aligned number.
            tree.heading(col, text=title, anchor=anchor)
            tree.column(col, width=width, anchor=anchor,
                        stretch=index == len(columns) - 1)
            if index:
                spacer = self._spacer(index)
                tree.heading(spacer, text="")
                # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
                tree.column(spacer, width=px(gap), minwidth=px(gap),
                            stretch=False)
        # (last column, its measured width, every column's): what
        # `_fit_banners` works the window's spare width out from.
        self._natural[str(tree)] = (columns[-1][0], width,
                                    self._columns_width(tree))
        return tree

    @staticmethod
    def _spacer(index):
        return "gap%d" % index

    @staticmethod
    def _spaced(values):
        """A row's values with the empty spacer cells between them."""
        out = []
        for index, value in enumerate(values):
            if index:
                out.append("")
            out.append(value)
        return tuple(out)

    def _rewrap(self, event):
        """Keep the help text wrapped to the width its row gives it.

        `event.width` is measured, so it is already at the active scale
        and does not go through `px`. Only a CHANGE is written: setting
        `wraplength` moves the label's requested width, and a handler
        that writes every time can bounce the row's layout.
        """
        new = max(px(200), event.width - px(10))
        label = event.widget
        try:
            if int(str(label.cget("wraplength"))) == new:
                return
        except (ValueError, tk.TclError):
            pass
        label.configure(wraplength=new)

    @staticmethod
    def _star_tag(stars):
        return "stars_%s" % (stars or "unknown")

    # ------------------------------------------------------------ reading

    def _folder(self):
        return gh.folder_in(OUTPUT_DIR)

    def _first_show(self, _event):
        if not self._loaded:
            self.refresh()
            self.refresh_standings()

    def refresh_standings(self):
        """Redraw the standings lists from the loaded
        snapshot and the file of old captures.

        Called after every snapshot load and after the old captures have
        been read. A tab never shown yet does nothing: it reads them the
        first time it is.
        """
        if not self._loaded:
            return
        folder = getattr(self.context, "stats_dir", None)
        self.stats = sh.load(folder) if folder else None
        self._fill_standings()

    def on_capture_update(self):
        """The capture wrote the history file. Only a tab that has
        already been shown re-reads it; one that has not reads it the
        first time it is."""
        if self._loaded:
            self.refresh()

    def refresh(self):
        """Read the history folder again and redraw both lists."""
        self._loaded = True
        try:
            self.history = gh.load(self._folder())
        except Exception as e:                       # noqa: BLE001
            self.history = None
            self._show_status("The history could not be read: %s" % e,
                              "red")
            self._fill_summary()
            self._fill_overall()
            self._fill_pulls()
            return
        notes = self.history.notes
        if notes:
            # Yellow, not red: red is the urgent banners' colour.
            self._show_status("; ".join(notes), "yellow")
        elif any(pool.stats.behind or pool.stats.gap
                 for pool in self._shown_pools()):
            # The pull count gives way to the warnings, which keeps the
            # toolbar within the help text's height.
            self._show_status("", "fg_dim")
        elif self.history.total:
            self._show_status(
                "%s pulls kept" % format(self.history.total, ","),
                "fg_dim")
        else:
            self._show_status("No history yet", "fg_dim")
        self._fill_summary()
        self._fill_overall()
        self._fill_pulls()

    def _show_status(self, text, colour):
        """Set the status lines: the warnings the shown banners call
        for, then `text`. A line with nothing to say is not packed, so
        it leaves no blank line behind."""
        pools = self._shown_pools()
        lines = (
            (self.urgent_label, URGENT_NOTE
             if any(p.stats.urgent for p in pools) else ""),
            (self.behind_label, BEHIND_NOTE
             if any(p.stats.behind and not p.stats.urgent for p in pools)
             else ""),
            (self.gap_label, GAP_NOTE
             if any(p.stats.gap and not p.stats.urgent for p in pools)
             else ""),
            (self.status_label, text))
        self.status_label.configure(foreground=self.colors[colour])
        for label, line in lines:
            label.pack_forget()
            label.configure(text=line)
        for label, line in lines:
            if line:
                label.pack(side=tk.TOP, anchor=tk.W)

    def _shown_pools(self):
        """Families with pulls, and families whose records have been
        opened -- one never opened and never pulled on is nothing to
        show."""
        if self.history is None:
            return []
        return [pool for pool in self.history.ordered()
                if pool.pulls or pool.stats.read_at]

    def _fill_summary(self):
        tree = self.summary_tree
        tree.delete(*tree.get_children())
        pools = self._shown_pools()
        for pool in pools:
            tree.insert("", tk.END, iid=pool.pool,
                        values=self._spaced(self._summary_row(pool)),
                        tags=self._summary_tags(pool))
        self._show_banner_rows(len(pools))
        keep = self._pool if self._pool in {p.pool for p in pools} else (
            pools[0].pool if pools else None)
        self._pool = keep
        if keep:
            tree.selection_set(keep)

    def _show_banner_rows(self, count):
        """Size the Banners list to `count` families, up to `BANNER_ROWS`
        with a scrollbar past them -- which widens the list, so the
        standings under it are fitted again."""
        self.summary_tree.configure(height=max(1, min(count, BANNER_ROWS)))
        if count > BANNER_ROWS:
            self.summary_scroll.pack(side=tk.LEFT, fill=tk.Y)
        else:
            self.summary_scroll.pack_forget()
        self._fit_banners()

    def _share_excess(self, event):
        """The body has a new width: share it out again, and lay the
        gacha sheet out to the Banners list's new width -- its second
        column and its holder follow that width, and a holder left at the
        old one clips the second column short of the Pulls list. Only on
        a change -- widening the Banners list lays the body out again
        and comes back here at the same width."""
        if event.width != self._body_width:
            self._body_width = event.width
            self._fit_banners()
            if self._loaded:
                self._fill_overall()

    def _fit_banners(self):
        """Give the Banners list all the width the window leaves beyond
        what both lists measure, in its LAST column, so every column
        before it keeps its measured width: the standings under it grow
        to its width, and the pulls list has nothing to gain from more.
        Then the standings are fitted again.
        """
        if self._body_width is not None:
            banners, pulls = self.summary_tree, self.pulls_tree
            column, width, measured = self._natural[str(banners)]
            used = (measured + self._natural[str(pulls)][2]
                    + self.pulls_scroll.winfo_reqwidth())
            if self.summary_scroll.winfo_manager():
                used += self.summary_scroll.winfo_reqwidth()
            # Both panels' pads, either side of each.
            spare = self._body_width - used - 4 * px(2)
            banners.column(column, width=width + max(0, spare))
            # NOT redundant: a mapped Treeview asks for a new width only
            # on `configure` (docs/ui_runtime.md), so without it the
            # column widens inside a list that stays its old size.
            banners.configure(height=banners.cget("height"))
        self._size_standings()

    @staticmethod
    def _summary_tags(pool):
        if pool.stats.urgent:
            return (URGENT_TAG,)
        if pool.stats.behind or pool.stats.gap:
            return (BEHIND_TAG,)
        return ()

    def _summary_row(self, pool):
        s = pool.stats
        fifty = NO_VALUE
        if s.won is not None and (s.won or s.lost):
            fifty = "%d of %d" % (s.won, s.won + s.lost)
        pity = s.game_pity if s.game_pity is not None else s.pity_now
        read = NO_VALUE
        if s.read_at:
            read = s.read_at.replace("T", " ")[:16]
        return (pool.label, format(s.pulls, ","), s.fives,
                _number(s.avg_pity), _number(s.expected_pity),
                gh.luck_rank(s.luckier_than) or NO_VALUE,
                fifty, s.fours, _number(s.four_avg), pity, read)

    def _overall_rows(self):
        """The Overall Gacha Stats sheet, top to bottom: a section's name
        as a bare string, every other row (figure, value), a record's
        followed by a (units, date) pair for each tie, and a line holding
        two of those side by side a `Beside`."""
        o = self.history.overall if self.history is not None \
            else gh.Overall()
        # The 50/50s' luck stands in the column the pulls' luck does.
        fifty = (NO_VALUE,)
        if o.fifty_won or o.fifty_lost:
            fifty = ("%d of %d" % (o.fifty_won,
                                   o.fifty_won + o.fifty_lost),)
            if o.fifty_luck is not None:
                fifty += (gh.luck_rank(o.fifty_luck),)
        per = NO_VALUE
        if o.rate_up_avg is not None:
            per = _number(o.rate_up_avg)
            if o.rate_up_expected is not None:
                per += " (expected avg %s)" % _number(o.rate_up_expected)
        streak = STREAK % gh.STREAK_PULLS
        return _paired((
            # The wider sections are a heading and a luck each, which sit
            # beside the first section's rather than a section down.
            Beside(WITHOUT_PRISM, WITH_PRISM, WITH_SKINS),
            Beside(("Pulls", format(o.pulls_without_prism, ","),
                    _rank(o.luck_without_prism)),
                   ("Luck", _rank(o.luck_with_prism)),
                   ("Luck", _rank(o.luck_with_skins))),
            ("50/50s won",) + fifty,
            ("Rate-Up pulls avg", per),
            ("Fastest 5★",) + _standout(o.fastest),
            ("Slowest 5★",) + _standout(o.slowest),
            ("Fastest rate-up",) + _standout(o.fastest_rate_up),
            ("Slowest rate-up",) + _standout(o.slowest_rate_up),
            (streak,) + _standout(o.streak, streak=True),
        ), (
            # The second column: the Prism Module's records at the top,
            # the Card Skin Packs' at the foot, a Super Rare as a 5-star.
            PRISM_ONLY,
            ("Fastest 5★",) + _standout(o.prism_fastest),
            ("Slowest 5★",) + _standout(o.prism_slowest),
            (streak,) + _standout(o.prism_streak, streak=True),
        ), (
            Noted(SKINS_ONLY, SKINS_NOTE),
            ("Fastest 5★",) + _standout(o.skin_fastest),
            ("Slowest 5★",) + _standout(o.skin_slowest),
            (streak,) + _standout(o.skin_streak, streak=True),
        ))

    def _reserve(self):
        """The record every section's columns make room for: the streak's
        figure, the widest value, then a tie for each of the `SET_NAMES`
        longest combatant names, longest first, each with a date. Worked
        out once and kept."""
        if self._reserve_cached is None:
            from game_data import CHARACTERS
            font = tkfont.nametofont("TkDefaultFont")
            names = sorted({unit["name"] for unit in CHARACTERS.values()
                            if isinstance(unit, dict) and unit.get("name")},
                           key=font.measure, reverse=True)[:SET_NAMES]
            names += ["#99999"] * (SET_NAMES - len(names))
            ties = ()
            for name in names:
                ties += (name, WIDEST_DATE)
            self._reserve_cached = (STREAK % gh.STREAK_PULLS,
                                    WIDEST_COUNT) + ties
        return self._reserve_cached

    def _right_width(self):
        """The sheet's second column's width: the reserved record
        (`_reserve`) at the sheet's gaps, or the Card Skin Packs' heading
        and note where that is wider. Measured the first time it is
        asked for and kept, so neither a resize nor a refill moves the
        column."""
        if self._right_cached is None:
            font = tkfont.nametofont("TkDefaultFont")
            bold = tkfont.Font(font=HEADING_FONT)
            reserve = self._reserve()
            record = (self._column_stops([reserve], font)[-1]
                      + font.measure(reserve[-1]))
            # spacing: header subtext -- label, label ↔
            noted = (bold.measure(SKINS_ONLY) + px(NOTE_GAP)
                     + font.measure(SKINS_NOTE))
            self._right_cached = max(record, noted)
        return self._right_cached

    def _fill_overall(self):
        """Write the gacha sheet, its first column's ties cut short of
        the second column (`_fit_ties`)."""
        font = tkfont.nametofont("TkDefaultFont")
        bold = tkfont.Font(font=HEADING_FONT)
        self._write_sheet(self.overall_text, self.overall_holder,
                          self._fit_ties(self._overall_rows(), font, bold))

    def _fill_standings(self):
        """Write the three standings lists from what is loaded."""
        # The shipped facts add a column for every season they know of
        # on the account's server, and fill what its own readings lack.
        raw, shipped = self._raw(), self._shipped()
        for parts, table in ((self.sortie_list, sh.sortie_table),
                             (self.rift_list, sh.rift_table),
                             (self.offensive_list, sh.offensive_table)):
            self._write_standings(parts, *table(raw, self.stats, shipped))
        self._size_standings()

    def _shipped(self):
        """The program's own game facts, or None -- see shared_facts.py."""
        return getattr(self.context, "shared_facts", None)

    def _raw(self):
        return getattr(self.optimizer, "raw_data", None) or {}

    def _banners_width(self):
        """The Banners list's width, which the column under it keeps to:
        its scrollbar's too, while it has one. The list's own rather than
        its panel's: a Treeview's is known as soon as its columns are,
        where a frame's waits for Tk to lay it out."""
        width = self.summary_tree.winfo_reqwidth()
        if self.summary_scroll.winfo_manager():
            width += self.summary_scroll.winfo_reqwidth()
        return width

    @staticmethod
    def _columns_width(tree):
        """A list's columns, summed: its width in this tab's list style,
        which draws no edge -- and known whatever the list last asked
        for."""
        return sum(int(tree.column(column, "width"))
                   for column in tree["columns"])

    def _panel_edges(self):
        """What a panel on this tab adds to its content's width: nothing
        where the borderless style is configured, as it is in the app,
        and a border where a theme draws one. Read off the Banners
        panel, whose content keeps one width once built."""
        return max(0, self.summary_tree.master.winfo_reqwidth()
                   - self._banners_width())

    def _write_standings(self, parts, rows, columns):
        """Write one standings list: the rows' names, then a column per
        season with a spacer between every two, each column as wide as
        its widest text -- `_make_tree`'s arithmetic. A list with nothing
        read keeps one empty column, so it still reads as a table."""
        font = tkfont.nametofont("TkDefaultFont")
        head = tkfont.nametofont("TkHeadingFont")
        labels, data = parts.labels, parts.data
        # Measured, so no `px()` on the text's share -- the fonts already
        # carry the scale. The inset is a distance and takes it.
        width = max([head.measure(SEASON_HEADING)]
                    + [font.measure(name) for name in rows]) \
            + px(2 * TEXT_INSET)
        labels.column("label", width=width, minwidth=width)
        # **NOT redundant** when the row count is unchanged: a mapped
        # Treeview asks for a new size only on `configure`, never on a
        # column's new width. Without it a longer row name -- the own
        # division's, when it changes -- is cut off at the old width.
        # `check_tabs_build` pins it.
        labels.configure(height=len(rows))
        labels.delete(*labels.get_children())
        # A division's row takes its colour in both lists, name and
        # seasons alike.
        tags = [(DIVISION_TAG % sh.RIFT_DIVISION_ROWS[name],)
                if name in sh.RIFT_DIVISION_ROWS else () for name in rows]
        for name, tag in zip(rows, tags, strict=True):
            labels.insert("", tk.END, values=(name, ""),
                          tags=tag + ((TIP_TAG,) if name in ROW_TIPS else ()))
        columns = columns or [(NO_VALUE, [None] * len(rows))]
        ids = []
        for index in range(len(columns)):
            if index:
                ids.append(self._spacer(index))
            ids.append("season%d" % index)
        data.configure(columns=ids)
        for index, (heading, cells) in enumerate(columns):
            column = "season%d" % index
            width = max([head.measure(heading)]
                        + [font.measure(cell or NO_VALUE) for cell in cells]) \
                + px(2 * TEXT_INSET)
            data.heading(column, text=heading, anchor=tk.E)
            data.column(column, width=width, minwidth=width, anchor=tk.E,
                        stretch=False)
            if index:
                gap = self._spacer(index)
                data.heading(gap, text="")
                # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
                data.column(gap, width=px(STANDINGS_COLUMN_GAP),
                            minwidth=px(STANDINGS_COLUMN_GAP), stretch=False)
        # After the widths, for the reason above -- and reassigning
        # `columns` on a mapped list asks for 200 a column meanwhile.
        data.configure(height=len(rows))
        data.delete(*data.get_children())
        for row in range(len(rows)):
            data.insert("", tk.END, values=self._spaced(
                [cells[row] or NO_VALUE for _heading, cells in columns]),
                tags=tags[row])

    def _size_standings(self):
        """Fit each standings list to its room. The Great Rift's is the
        Banners list's width. The Offensive's and the Sortie's share
        theirs so that each shows as many seasons as the other (`_share`):
        under the banners while both fit there whole, else across the
        window's whole width, under the pulls list (`_place_pair`). A
        list is as wide as its seasons up to its room, and past it they
        scroll sideways under a scrollbar that shows only then -- newest
        first, so what scrolls out of sight is the oldest."""
        width, edges = self._banners_width(), self._panel_edges()
        pair = (self.offensive_list, self.sortie_list)
        natural = [self._columns_width(p.data) for p in pair]
        wide = (self._body_width is not None
                and self._pair_width(natural) > width)
        # The pair's room spans the window but for the pads at its two
        # ends, as the Banners list's does its column.
        room = max(width, self._body_width - 2 * px(2)) if wide else width
        self._place_pair(wide)
        shown = self._share(room)
        for parts, room_ in ((self.rift_list, width),):
            space = max(1, room_ - edges - self._columns_width(parts.labels))
            shown_rift = min(self._columns_width(parts.data), space)
            self._fit_list(parts, shown_rift)
        for parts, width_ in zip(pair, shown, strict=True):
            self._fit_list(parts, width_)

    def _fit_list(self, parts, shown):
        """One standings list's seasons `shown` pixels wide, scrolling
        past them."""
        natural = self._columns_width(parts.data)
        shown = max(1, min(natural, shown))
        parts.holder.configure(width=shown,
                               height=parts.data.winfo_reqheight())
        if natural > shown:
            parts.scroll.grid()
        else:
            parts.scroll.grid_remove()
            parts.data.xview_moveto(0)

    def _pair_width(self, shown):
        """The Offensive's and the Sortie's panels side by side, their
        seasons `shown` pixels wide each: a panel is as wide as its list
        or its title and note, whichever is wider, and two pads sit
        between them."""
        edges = self._panel_edges()
        return sum(max(self._columns_width(p.labels) + s, p.header.winfo_reqwidth())
                   + edges for p, s in zip(
                       (self.offensive_list, self.sortie_list), shown, strict=True)) \
            + 2 * px(2)

    def _share(self, room):
        """The Offensive's and the Sortie's seasons' widths within `room`,
        so that each list shows as many seasons as the other: the same
        number `k` of each list's average season, `k` as large as the
        room allows. A list narrower than its title takes the title's
        width as well, which costs nothing, and the pixels the room has
        over go to a list that still scrolls."""
        pair = (self.offensive_list, self.sortie_list)
        natural = [self._columns_width(p.data) for p in pair]
        if self._pair_width(natural) <= room:
            return natural
        per = []
        for parts, width in zip(pair, natural, strict=True):
            count = sum(1 for c in parts.data["columns"]
                        if not str(c).startswith("gap"))
            per.append((width + px(STANDINGS_COLUMN_GAP)) / max(1, count))

        def at(k):
            return [min(n, int(k * s)) for n, s in zip(natural, per, strict=True)]

        low, high = 0.0, max(n / s for n, s in zip(natural, per, strict=True))
        for _ in range(40):
            mid = (low + high) / 2
            if self._pair_width(at(mid)) <= room:
                low = mid
            else:
                high = mid
        shown = at(low)
        free = [max(0, p.header.winfo_reqwidth()
                    - self._columns_width(p.labels)) for p in pair]
        shown = [max(s, min(n, f)) for s, n, f in zip(shown, natural, free, strict=True)]
        for i in range(len(pair)):
            left = room - self._pair_width(shown)
            if left > 0 and shown[i] < natural[i]:
                shown[i] = min(natural[i], shown[i] + left)
        return shown

    def _place_pair(self, wide):
        """Lay the Offensive's and the Sortie's lists out under the
        banners alone, or across the window, the pulls list then ending
        above them. Only a change is laid out: a resize asks every
        time."""
        if wide == self._wide:
            return
        self._wide = wide
        self.pair.grid_configure(columnspan=2 if wide else 1)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        self.pulls_frame.grid_configure(
            rowspan=3 if wide else 4,
            pady=(px_after(5, 2), px(2) if wide else px_after(2, 2)))

    def _write_sheet(self, text, holder, rows):
        """Write a sheet, set its stops from what it now holds, and size
        its holder to the result. A section's name is a bare string,
        every other row a tuple of fields, and a line holding two side by
        side a `Beside`, whose own stops a tag of its own carries."""
        font = tkfont.nametofont("TkDefaultFont")
        bold = tkfont.Font(font=HEADING_FONT)
        room = self._banners_width()
        stops, widest, beside, _ends, _left_ends = self._overall_layout(
            rows, font, bold, room, self._right_width(), self._reserve())
        text.configure(state=tk.NORMAL, tabs=tuple(stops))
        text.delete("1.0", tk.END)
        # The first line takes `TOP_TAG`, heading or row: it crosses
        # nothing, so nothing is charged above it. A line's pitch is its
        # first column's: the second column's heading sits at the row
        # pitch, its lines being the first column's.
        for n, row in enumerate(rows):
            end = "\n" if n < len(rows) - 1 else ""
            left = _left(row)
            parts = left.parts if isinstance(left, Beside) else (left,)
            if isinstance(row, Paired):
                parts += (row.right,)
            heading = _heading(parts[0])
            line = (TOP_TAG if n == 0 else HEADING_TAG if heading
                    else ROW_TAG,)
            if n in beside:
                text.tag_configure(BESIDE_TAG % n, tabs=beside[n])
                line += (BESIDE_TAG % n,)
            chunks = []
            for part in parts:
                style = (BOLD_TAG,) if _heading(part) else ()
                if isinstance(part, Noted):
                    chunks += [(part.heading, style), ("\t", ()),
                               (part.note, (NOTE_TAG,))]
                else:
                    chunks.append((part if isinstance(part, str)
                                   else "\t".join(part), style))
                chunks.append(("\t", ()))
            chunks[-1] = (end, ())
            for chunk, own in chunks:
                if chunk:
                    text.insert(tk.END, chunk, line + own)
        text.configure(state=tk.DISABLED)
        # Measured, so no `px()`: the fonts carry the scale, and the
        # lines' `spacing1` is already in the count.
        height = text.count("1.0", tk.END, "update", "ypixels")
        if isinstance(height, (tuple, list)):
            height = height[0]
        # No wider than the Banners list: the sheet sits in its column,
        # and a wider holder would widen the column and take the
        # difference from the Pulls list. What runs past is clipped.
        holder.configure(width=min(widest, room), height=height or 1)

    def _fit_ties(self, rows, font, bold):
        """`rows` with the first column's ties cut to as many pairs as
        end short of the second column, keeping the OLDEST -- on every
        line, so no line's ties run on under the second column's gap
        between its sections. The second column starts past the reserved
        record (`_reserve`) or its width short of the Banners list's,
        whichever is further, so the first keeps the reserved record's
        ties at least. Without a second column, the cut is to the
        Banners list's width.

        The second column's ties are never cut: past the Banners list's
        width they run under the Pulls list, which clips them
        (`_write_sheet`).

        Every record keeps its first pair, which is the record itself;
        only its ties are ever cut.
        """
        available = self._banners_width()
        right_width = self._right_width()
        reserve = self._reserve()

        def parts(row):
            left = _left(row)
            return left.parts if isinstance(left, Beside) else (left,)

        def cut(part, pairs):
            return part if _heading(part) else part[:2 + 2 * pairs]

        def rebuilt(row, full):
            if isinstance(row, Paired):
                return Paired(rebuilt(row.left, full), row.right)
            if isinstance(row, Beside):
                return Beside(*(cut(part, full) for part in row.parts))
            return cut(row, full)

        full = max([(len(part) - 2) // 2 for row in rows
                    for part in parts(row) if not _heading(part)] + [1])
        paired = any(isinstance(row, Paired) for row in rows)
        while True:
            out = [rebuilt(row, full) for row in rows]
            layout = self._overall_layout(out, font, bold, available,
                                          right_width, reserve)
            stops, left_ends = layout[0], layout[4]
            limit = available
            if paired:
                held = stops[len(reserve) - 2] + font.measure(reserve[-1])
                # spacing: heading ↔ element -- run, run ↔
                limit = max(held, available - right_width - px(BESIDE_GAP))
            if full > 1 and max(left_ends + [0]) > limit:
                full -= 1
            else:
                return out

    @staticmethod
    def _column_stops(cells, font, origin=0):
        """The stops of rows of fields set from `origin`: each column as
        wide as its widest text among the rows with something AFTER it
        -- a row that ends at a column puts no tab after it, so its
        width stops nobody -- then its gap. The gaps are distances and
        take `px()`; the text is measured and does not."""
        stops, start = [], origin
        for column in range(max([len(row) for row in cells] + [1]) - 1):
            if column == 0:
                gap = FIGURE_TO_VALUE
            elif column == 1:
                gap = VALUE_TO_UNITS
            else:
                # A pair's units against its date; a date against the
                # next pair.
                gap = UNITS_TO_DATE if column % 2 == 0 else TIE_TO_TIE
            widest = max(font.measure(row[column]) for row in cells
                         if len(row) > column + 1)
            # spacing: label ↔ its element -- run, run ↔
            # spacing: element and its label ↔ element and its label -- run, run ↔
            start += widest + px(gap)
            stops.append(start)
        return stops

    @staticmethod
    def _beside_runs(rows):
        """The line numbers of each run of consecutive `Beside` lines:
        what `_overall_layout` lays out together."""
        runs = []
        for n, row in enumerate(rows):
            if not isinstance(row, Beside):
                continue
            if runs and runs[-1][-1] == n - 1:
                runs[-1].append(n)
            else:
                runs.append([n])
        return runs

    @classmethod
    def _overall_layout(cls, rows, font, bold, room=None, right_width=None,
                        reserve=None):
        """(tab stops, widest line, {line: its own stops}, each line's
        end, each line's first column's end), in pixels from the line's
        start. The rows' columns are `_column_stops`', each column at
        least as wide as `reserve`'s field in it.

        A `Beside` line's first part is one of those rows. A run of such
        lines is laid out together, part by part: each part starts
        `BESIDE_GAP` past the furthest end of the part before it on any
        line of the run, and its rows' columns are their own, set from
        there. So those lines carry stops of their own: the sheet's up
        to their first part's last field, then each part's.

        A `Paired` line's second part starts the second column:
        `right_width` short of `room`, or `BESIDE_GAP` past the furthest
        first column of the paired lines and of `reserve` where that is
        further. Its rows' columns are their own, set from there, and
        those lines carry them after their first column's stops. What
        runs past `room` is clipped there (`_write_sheet`).
        """
        sides = [_left(row) for row in rows]
        lefts = [row.parts[0] if isinstance(row, Beside) else row
                 for row in sides]
        reserved = [reserve] if reserve else []
        stops = cls._column_stops(
            [row for row in lefts if not _heading(row)] + reserved, font)

        def note_at(part, start):
            # spacing: header subtext -- label, label ↔
            return start + bold.measure(part.heading) + px(NOTE_GAP)

        def finish(part, start, local):
            if isinstance(part, Noted):
                return note_at(part, start) + font.measure(part.note)
            if isinstance(part, str):
                return start + bold.measure(part)
            return ((local[len(part) - 2] if len(part) > 1 else start)
                    + font.measure(part[-1]))

        def placed(own, part, start, local):
            if isinstance(part, Noted):
                own += [start, note_at(part, start)]
            elif isinstance(part, str):
                own.append(start)
            else:
                own += [start] + local[:len(part) - 1]

        ends = [finish(part, 0, stops) for part in lefts]
        beside = {}
        for run in cls._beside_runs(sides):
            own = {n: [] if _heading(sides[n].parts[0])
                   else stops[:len(sides[n].parts[0]) - 1] for n in run}
            for k in range(1, max(len(sides[n].parts) for n in run)):
                lines = [n for n in run if len(sides[n].parts) > k]
                # spacing: heading ↔ element -- run, run ↔
                start = max(ends[n] for n in lines) + px(BESIDE_GAP)
                local = cls._column_stops(
                    [sides[n].parts[k] for n in lines
                     if not _heading(sides[n].parts[k])], font, start)
                for n in lines:
                    part = sides[n].parts[k]
                    placed(own[n], part, start, local)
                    ends[n] = finish(part, start, local)
            for n in run:
                beside[n] = tuple(own[n])
        left_ends = list(ends)
        paired = [n for n, row in enumerate(rows) if isinstance(row, Paired)]
        if paired:
            # The first column's lines, and its reserved record, which
            # keeps the column clear of the second however short its
            # records' units are.
            furthest = [ends[n] for n in paired]
            if reserve:
                furthest.append(finish(reserve, 0, stops))
            # spacing: heading ↔ element -- run, run ↔
            start = max(furthest) + px(BESIDE_GAP)
            if room and right_width:
                start = max(start, room - right_width)
            local = cls._column_stops(
                [rows[n].right for n in paired
                 if not _heading(rows[n].right)] + reserved, font, start)
            for n in paired:
                own = list(beside[n]) if n in beside else (
                    [] if _heading(lefts[n]) else stops[:len(lefts[n]) - 1])
                placed(own, rows[n].right, start, local)
                beside[n] = tuple(own)
                ends[n] = finish(rows[n].right, start, local)
        return stops, max(ends + [1]), beside, ends, left_ends

    def _on_pick(self, _event):
        chosen = self.summary_tree.selection()
        if chosen and chosen[0] != self._pool:
            self._pool = chosen[0]
            self._fill_pulls()

    def _fill_pulls(self):
        tree = self.pulls_tree
        tree.delete(*tree.get_children())
        pool = (self.history.pools.get(self._pool)
                if self.history is not None and self._pool else None)
        if pool is None:
            self.pulls_frame.configure(text="Pulls")
            return
        self.pulls_frame.configure(text="Pulls: %s" % pool.label)
        wanted = dict(FILTERS).get(self.filter_var.get())
        # A Card Skin is named by the combatant it is for, and its pack's
        # rate-up is the combatant its Super Rare is for.
        skins = pool.pool == gh.SKIN_POOL
        for pull in reversed(pool.pulls):
            if wanted is not None and pull.stars not in wanted:
                continue
            unit = gh.skin_wearer(pull.res_id) if skins else pull.res_id
            tree.insert("", tk.END, tags=(self._star_tag(pull.stars),),
                        values=self._spaced((
                            pull.number, gh.unit_name(unit),
                            _stars(pull.stars), pull.pity,
                            gh.unit_name(pull.featured)
                            if pull.featured else "",
                            pull.outcome or "", _when(pull.at))))

    # ------------------------------------------------------ import/export

    def _import(self):
        path = filedialog.askopenfilename(
            title="Import JSON", initialdir=str(OUTPUT_DIR),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        name = Path(path).name
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            batches, skipped = gh.parse_import(data, name)
            skins, skin_names = gh.parse_skin_import(data)
        except (OSError, ValueError) as e:
            # ImportRejected is a ValueError, and says what it expected.
            messagebox.showerror("Import JSON", "%s: %s" % (name, e))
            return
        before = gh.load(self._folder()).total
        try:
            gh.merge_import(self._folder(), batches, skins, skin_names)
        except (gh.StoreError, OSError) as e:
            messagebox.showerror("Import JSON", str(e))
            return
        self.refresh()
        after = self.history.total if self.history is not None else before
        read = sum(len(b["reward"]) for b in batches) + gh.skin_pull_count(
            skins)
        text = "Read %s pulls from %s. %s of them were new to the history." \
            % (format(read, ","), name, format(max(0, after - before), ","))
        if skipped:
            text += "\n\n%s could not be placed in time and were left out." \
                % format(skipped, ",")
        messagebox.showinfo("Import JSON", text)

    def _export(self):
        if self.history is None or not self.history.total:
            messagebox.showinfo("Export JSON", "There is no history to "
                                "export yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Export JSON", defaultextension=".json",
            initialdir=str(OUTPUT_DIR),
            initialfile="gacha_history_%s.json"
            % datetime.now().strftime("%Y%m%d"),
            filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            count = gh.export(self.history, path)
        except OSError as e:
            messagebox.showerror("Export JSON", str(e))
            return
        messagebox.showinfo("Export JSON", "Exported %s pulls to %s."
                            % (format(count, ","), path))
