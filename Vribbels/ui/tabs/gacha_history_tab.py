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
from ui.scaling import px
from ..base_tab import BaseTab
from ..utils.button_width import BUTTON_W_MEDIUM

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
    ("banner", "Banner", tuple(gh.POOL_LABELS.values()), tk.W),
    ("pulls", "Pulls", ("99,999",), tk.E),
    ("fives", "5★", ("999",), tk.E),
    ("avg", "Avg 5★ pull", ("99.9",), tk.E),
    ("game", "Expected avg", ("99.9",), tk.E),
    ("luck", "Luck", ("Bottom 50%", "Bottom 0.1%", "Bottom <0.1%"), tk.E),
    ("fifty", "50/50 won", ("99 of 99",), tk.E),
    ("fours", "4★", ("999",), tk.E),
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
                          gh.UNKNOWN), tk.W),
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
# The heading's height is left as the shared style has it.
HEADING_INSET_V = 3
# This tab's rows are shorter than every other list's: it is what lets
# the standings fit under the gacha sheet in the default window. Still
# clear of Segoe UI 9's 15px line box, below which a row clips its text.
LIST_ROW_HEIGHT = 19
# The Banners list shows at most this many rows and scrolls past them:
# with every banner family listed, the standings under it would run past
# the default window's bottom edge.
BANNER_ROWS = 7
# This tab's scrollbars: a thumb in a groove with no arrow buttons -- at
# this thickness an arrow is a few pixels of glyph, and the thumb and the
# wheel do the scrolling -- this thick. Colours are the app's own.
SCROLL_STYLE = "GachaHistory.%s.TScrollbar"
SCROLLBAR_WIDTH = 12

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
URGENT_NOTE = ("⚠ Red banners were last read over %d days ago.\n"
               "Read them NOW, before the game erases their history!"
               % gh.URGENT_AFTER_DAYS)
URGENT_FONT = ("Segoe UI", 9, "bold")

# Where the status lines wrap, so a long one takes height from the
# toolbar rather than width from the help text beside it.
STATUS_WRAPLENGTH = 320

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
WITHOUT_PRISM = "All banners, except Prism Module"
PRISM_ONLY = "Prism Module"
ALL_BANNERS = "All banners"
HEADING_FONT = ("Segoe UI", 9, "bold")

# Under it, the account's standings: three lists with a column per
# season, newest first, and the rows' names held still at the left --
# the Great Rift's as wide as the Banners list, then the Full-Scale
# Offensive's and the Sortie's side by side, half of it each. The
# tables are `sh.sortie_table`, `sh.rift_table` and `sh.offensive_table`,
# over the loaded snapshot's ranking history and whatever
# `stats_history.py` read out of the captures from before snapshots
# kept it.
#
# **The two half-width lists grow a column a season and stop at their
# half**, past which their seasons scroll sideways, as the Great Rift's
# do past the banners' edge. Held at their half instead, a list of two
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
# The heading over the rows' names, which says what the columns are.
SEASON_HEADING = "Season"
# A title's leading pad against the panel above it, the lever on
# `panel ↕ unrelated label`. Under the gacha sheet it is nothing: the
# sheet's last line box already reaches past its baseline by more than
# the banners' list does past its last row. Under the Great Rift's
# list, less than the gacha sheet's under the banners.
UNDER_SHEET_PAD = 0    # spacing: panel ↕ unrelated label -- run, title ↕
UNDER_LIST_PAD = 3     # spacing: panel ↕ unrelated label -- panel, title ↕

# One pitch tag per line, setting its `spacing1` -- the line's own word
# for what sits above it. Tk resolves two tags setting one option by
# priority rather than by sum, so a pad stacked on another tag would
# hang on the order the tags were made in. The first heading takes
# `TOP_TAG`: it crosses nothing, so nothing is charged above it.
ROW_TAG = "row"
HEADING_TAG = "heading"
TOP_TAG = "top"
BOLD_TAG = "bold"
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
# A pixel short of its rule: the widest value is always `N pulls`,
# whose `s` stops a pixel inside its own advance.
VALUE_TO_UNITS = 7      # spacing: element and its label ↔ element and its label -- run, run ↔
UNITS_TO_DATE = 5       # spacing: label ↔ its element -- run, run ↔
TIE_TO_TIE = 8          # spacing: element and its label ↔ element and its label -- run, run ↔
# A section set beside another on the same lines -- every banner's, by
# the first section's opening lines -- starts this far past the furthest
# of them, and its own rows keep the sheet's figure-to-value gap.
BESIDE_GAP = 16         # spacing: control group ↔ control group -- run, run ↔


class Beside:
    """One line of the gacha sheet holding two sections' lines side by
    side: `left` and `right`, each a heading's string or a row's
    fields. The left keeps the sheet's stops; the right starts past it,
    on stops the line carries itself (`GachaHistoryTab._overall_layout`).
    """

    def __init__(self, left, right):
        self.left, self.right = left, right


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
        name = gh.unit_name(pull.res_id)
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(name if n == 1 else "%s x%d" % (name, n)
                     for name, n in counts.items())


class GachaHistoryTab(BaseTab):
    """The Stats & Gacha History tab."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.history = None
        # What `stats_history.py` read out of old captures, or None.
        self.stats = None
        self._loaded = False
        self._pool = None               # the family the pulls list shows
        self.setup_ui()
        self.frame.bind("<Map>", self._first_show, add="+")

    # ------------------------------------------------------------ layout

    def setup_ui(self):
        # Built inside an unmapped container and packed last, so the tab
        # appears once, settled -- see the Optimizer's setup_ui.
        content = ttk.Frame(self.frame)

        toolbar = ttk.Frame(content)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        toolbar.pack(fill=tk.X, padx=px(2), pady=px((0, 0)))

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
        controls.pack(side=tk.LEFT, anchor=tk.N, pady=px((5, 5)))

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
        self.urgent_label = ttk.Label(
            status, text="", font=URGENT_FONT,
            foreground=self.colors["red"],
            wraplength=px(STATUS_WRAPLENGTH))
        self.behind_label = ttk.Label(
            status, text="", foreground=self.colors["orange"],
            wraplength=px(STATUS_WRAPLENGTH))
        self.status_label = ttk.Label(
            status, text="", foreground=self.colors["fg_dim"],
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
        # whatever the window has left. The pulls span both rows, and
        # the second takes the slack, so the figures sit right under the
        # banners however tall the pulls list is.
        body = ttk.Frame(content)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(3, weight=1)

        summary_frame = ttk.LabelFrame(body, text="Banners",
                                       padding=px(0),
                                       style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- label, title ↕
        summary_frame.grid(row=0, column=0, sticky="nw", padx=px(2),
                           pady=px(2))
        self.summary_tree = self._make_tree(summary_frame, SUMMARY_COLUMNS,
                                            height=1)
        self.summary_tree.pack(side=tk.LEFT, fill=tk.X)
        # Packed only while there are more families than `BANNER_ROWS`.
        self.summary_scroll = ttk.Scrollbar(
            summary_frame, orient=tk.VERTICAL,
            command=self.summary_tree.yview,
            style=SCROLL_STYLE % "Vertical")
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
        # The two half-width lists share a row of their own. Unpadded --
        # the panels in it carry their pads, so they line up with the
        # banners' edges.
        pair = ttk.Frame(body)
        pair.grid(row=3, column=0, sticky="nw")
        self.offensive_list = self._make_standings(
            pair, OFFENSIVE_TITLE, OFFENSIVE_NOTE, row=0, column=0,
            top=UNDER_LIST_PAD)
        self.sortie_list = self._make_standings(
            pair, SORTIE_TITLE, SORTIE_NOTE, row=0, column=1,
            top=UNDER_LIST_PAD)
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
                              padx=px(2), pady=px(2))
        self.pulls_tree = self._make_tree(self.pulls_frame, PULL_COLUMNS,
                                          height=20)
        scroll = ttk.Scrollbar(self.pulls_frame, orient=tk.VERTICAL,
                               command=self.pulls_tree.yview,
                               style=SCROLL_STYLE % "Vertical")
        self.pulls_tree.configure(yscrollcommand=scroll.set)
        self.pulls_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
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
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # The leading pad is the lever on the gap from the panel above
        # to this title, which the text rule sets; the banners keep the
        # 2 every panel on this tab has.
        frame.grid(row=row, column=0, sticky="nw", padx=px(2),
                   pady=px((5, 2)))
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
        return holder, text

    def _make_standings(self, parent, title, note, row, column, top):
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
        # as the Optimizer's Results panel does.
        header = ttk.Frame(frame)
        ttk.Label(header, text=title,
                  foreground=self.colors["accent"]).pack(side=tk.LEFT)
        hint = ttk.Label(header, text=note,
                         foreground=self.colors["fg_dim"])
        # spacing: header subtext -- label, label ↔
        hint.pack(side=tk.LEFT, padx=px((10, 0)))
        frame.configure(labelwidget=header)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # `top` is the lever on this title against the panel above it,
        # which differs by what that panel ends in -- see
        # `UNDER_SHEET_PAD`.
        frame.grid(row=row, column=column, sticky="nw", padx=px(2),
                   pady=px((top, 2)))
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
        labels.column("gap", width=px(COLUMN_GAP), minwidth=px(COLUMN_GAP),
                      stretch=False)
        labels.grid(row=0, column=0, sticky="nw")
        # The seasons' list is as wide as its holder, which
        # `_size_standings` sets: narrower than its columns, it scrolls.
        holder = tk.Frame(lists, bg=self.colors["bg"], width=1, height=1)
        holder.pack_propagate(False)
        holder.grid(row=0, column=1, sticky="nw")
        data = ttk.Treeview(holder, show="headings", height=1,
                            selectmode="none", style=TREE_STYLE, takefocus=0)
        data.pack(fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(lists, orient=tk.HORIZONTAL,
                               command=data.xview,
                               style=SCROLL_STYLE % "Horizontal")
        data.configure(xscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ew")
        scroll.grid_remove()
        return SimpleNamespace(frame=frame, header=header, labels=labels,
                               holder=holder, data=data, scroll=scroll)

    @staticmethod
    def _style_lists():
        """This tab's list style: the shared one, with wider text insets.

        **A layout with no padding element**, because the shared
        style's `padding` is two levers at once -- it insets the tree
        area as well as every cell's text -- and widened on the area it
        pulls the heading row in from both ends, leaving a strip of the
        list's background beside it. Without the element, `padding`
        reaches only the text. Everything else, colours and row height
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
        try:
            style.layout(TREE_STYLE, [
                ("Treeview.treearea", {"sticky": "nswe"})])
        except tk.TclError:
            pass
        style.map(TREE_STYLE, foreground=[])
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
        style.configure(TREE_STYLE,
                        padding=px((TEXT_INSET, 0, TEXT_INSET, 0)))
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↕
        style.configure(TREE_STYLE, rowheight=px(LIST_ROW_HEIGHT))
        for orient, across in (("Horizontal", "we"), ("Vertical", "ns")):
            name = SCROLL_STYLE % orient
            try:
                style.layout(name, [("%s.Scrollbar.trough" % orient, {
                    "sticky": across, "children": [
                        ("%s.Scrollbar.thumb" % orient,
                         {"expand": "1", "sticky": "nswe"})]})])
            except tk.TclError:
                pass
            # `arrowsize` is a clam scrollbar's thickness, arrows or not;
            # no grip lines on a thumb this narrow.
            # spacing: unique -- scrollbar thickness, a style option -- scrollbar, scrollbar ↔↕
            style.configure(name, arrowsize=px(SCROLLBAR_WIDTH), gripcount=0)
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
        style.configure(TREE_STYLE + ".Heading",
                        padding=px((TEXT_INSET, HEADING_INSET_V,
                                    TEXT_INSET, HEADING_INSET_V)))

    def _make_tree(self, parent, columns, height):
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
                gap = self._spacer(index)
                tree.heading(gap, text="")
                # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
                tree.column(gap, width=px(COLUMN_GAP),
                            minwidth=px(COLUMN_GAP), stretch=False)
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
        return "stars_%s" % (stars if stars else "unknown")

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
        elif any(pool.stats.behind for pool in self._shown_pools()):
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
        self._size_standings()

    @staticmethod
    def _summary_tags(pool):
        if pool.stats.urgent:
            return (URGENT_TAG,)
        if pool.stats.behind:
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
        streak = "Most 5★s in %d pulls" % gh.STREAK_PULLS
        return (
            # Every banner's section is its heading and its luck, which
            # sit beside the first section's rather than a section down.
            Beside(WITHOUT_PRISM, ALL_BANNERS),
            Beside(("Pulls", format(o.pulls_without_prism, ","),
                    _rank(o.luck_without_prism)),
                   ("Luck", _rank(o.luck_with_prism))),
            ("50/50s won",) + fifty,
            ("Rate-Up pulls avg", per),
            ("Fastest 5★",) + _standout(o.fastest),
            ("Slowest 5★",) + _standout(o.slowest),
            ("Fastest rate-up",) + _standout(o.fastest_rate_up),
            ("Slowest rate-up",) + _standout(o.slowest_rate_up),
            (streak,) + _standout(o.streak, streak=True),
            PRISM_ONLY,
            ("Fastest 5★",) + _standout(o.prism_fastest),
            ("Slowest 5★",) + _standout(o.prism_slowest),
            (streak,) + _standout(o.prism_streak, streak=True),
        )

    def _fill_overall(self):
        """Write the gacha sheet, its ties cut to the banners' width."""
        font = tkfont.nametofont("TkDefaultFont")
        bold = tkfont.Font(font=HEADING_FONT)
        self._write_sheet(self.overall_text, self.overall_holder,
                          self._fit_ties(self._overall_rows(), font, bold))

    def _fill_standings(self):
        """Write the three standings lists from what is loaded."""
        raw = self._raw()
        for parts, table in ((self.sortie_list, sh.sortie_table),
                             (self.rift_list, sh.rift_table),
                             (self.offensive_list, sh.offensive_table)):
            self._write_standings(parts, *table(raw, self.stats))
        self._size_standings()

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
        for name in rows:
            labels.insert("", tk.END, values=(name, ""))
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
                data.column(gap, width=px(COLUMN_GAP),
                            minwidth=px(COLUMN_GAP), stretch=False)
        # After the widths, for the reason above -- and reassigning
        # `columns` on a mapped list asks for 200 a column meanwhile.
        data.configure(height=len(rows))
        data.delete(*data.get_children())
        for row in range(len(rows)):
            data.insert("", tk.END, values=self._spaced(
                [cells[row] or NO_VALUE for _heading, cells in columns]))

    def _size_standings(self):
        """Fit each standings list to its room. The Great Rift's is the
        Banners list's width and is held there; the two beneath it have
        half of it each and are as wide as their seasons up to that. Past
        its room a list's seasons scroll sideways under a scrollbar that
        shows only then -- newest first, so what scrolls out of sight is
        the oldest."""
        width, edges = self._banners_width(), self._panel_edges()
        # Each half less its share of the two pads between the panels. A
        # title and note wider than its half takes the difference from
        # the neighbour's list, so the pair never runs past the banners.
        half = width // 2 - px(2)
        pair = (self.offensive_list, self.sortie_list)
        rooms = [(self.rift_list, width, True)]
        for parts, other in zip(pair, pair[::-1]):
            beside = max(other.header.winfo_reqwidth() + edges,
                         min(half, self._columns_width(other.labels)
                             + self._columns_width(other.data) + edges))
            rooms.append((parts, min(half, width - 2 * px(2) - beside),
                          False))
        for parts, room, held in rooms:
            natural = self._columns_width(parts.data)
            space = max(1, room - edges - self._columns_width(parts.labels))
            shown = space if held else min(natural, space)
            parts.holder.configure(width=shown,
                                   height=parts.data.winfo_reqheight())
            if natural > shown:
                parts.scroll.grid()
            else:
                parts.scroll.grid_remove()
                parts.data.xview_moveto(0)

    def _write_sheet(self, text, holder, rows):
        """Write a sheet, set its stops from what it now holds, and size
        its holder to the result. A section's name is a bare string,
        every other row a tuple of fields, and a line holding two side by
        side a `Beside`, whose own stops a tag of its own carries."""
        font = tkfont.nametofont("TkDefaultFont")
        bold = tkfont.Font(font=HEADING_FONT)
        stops, widest, beside = self._overall_layout(rows, font, bold)
        text.configure(state=tk.NORMAL, tabs=tuple(stops))
        text.delete("1.0", tk.END)
        # The first line takes `TOP_TAG`, heading or row: it crosses
        # nothing, so nothing is charged above it.
        for n, row in enumerate(rows):
            end = "\n" if n < len(rows) - 1 else ""
            parts = (row.left, row.right) if isinstance(row, Beside) \
                else (row,)
            heading = isinstance(parts[0], str)
            tags = (TOP_TAG if n == 0 else HEADING_TAG if heading
                    else ROW_TAG,) + ((BOLD_TAG,) if heading else ())
            if n in beside:
                text.tag_configure(BESIDE_TAG % n, tabs=beside[n])
                tags += (BESIDE_TAG % n,)
            text.insert(tk.END, "\t".join(
                field for part in parts
                for field in ((part,) if isinstance(part, str) else part))
                + end, tags)
        text.configure(state=tk.DISABLED)
        # Measured, so no `px()`: the fonts carry the scale, and the
        # lines' `spacing1` is already in the count.
        height = text.count("1.0", tk.END, "update", "ypixels")
        if isinstance(height, (tuple, list)):
            height = height[0]
        holder.configure(width=widest, height=height or 1)

    def _fit_ties(self, rows, font, bold):
        """`rows` with each record's ties cut to as many pairs as fit
        the Banners list's width, keeping the OLDEST. The sheet sits in
        that list's column, and a wider sheet would widen the column and
        take the difference from the pulls list beside it.

        Every record keeps its first pair, which is the record itself;
        only its ties are ever cut.
        """
        available = self._banners_width()
        pairs = max([(len(row) - 2) // 2 for row in rows
                     if not isinstance(row, (str, Beside))] + [1])
        while True:
            cut = [row if isinstance(row, (str, Beside))
                   else row[:2 + 2 * pairs] for row in rows]
            if pairs <= 1 or self._overall_layout(
                    cut, font, bold)[1] <= available:
                return cut
            pairs -= 1

    @staticmethod
    def _overall_layout(rows, font, bold):
        """(tab stops, widest line, {line: its own stops}), in pixels
        from the line's start.

        Row by row: each column is as wide as its widest text among the
        rows with something AFTER it -- a row that ends at a column puts
        no tab after it, so its width stops nobody. The gaps are
        distances and take `px()`; the text is measured and does not.

        A `Beside` line's left part is one of those rows. Its right part
        starts `BESIDE_GAP` past the furthest left part of any such line
        -- a heading, or a figure and its value -- so those lines carry
        stops of their own: the sheet's up to their left part's last
        field, then the right part's.
        """
        lefts = [row.left if isinstance(row, Beside) else row
                 for row in rows]
        cells = [row for row in lefts if not isinstance(row, str)]
        stops, start = [], 0
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
        def end(part):
            if isinstance(part, str):
                return bold.measure(part)
            return ((stops[len(part) - 2] if len(part) > 1 else 0)
                    + font.measure(part[-1]))

        ends = [end(part) for part in lefts]
        beside = {}
        pairs = [(n, row) for n, row in enumerate(rows)
                 if isinstance(row, Beside)]
        if pairs:
            # spacing: heading ↔ element -- run, run ↔
            right = max(end(row.left) for _n, row in pairs) + px(BESIDE_GAP)
            figures = [font.measure(row.right[0]) for _n, row in pairs
                       if not isinstance(row.right, str)]
            # spacing: label ↔ its element -- run, run ↔
            value = right + max(figures + [0]) + px(FIGURE_TO_VALUE)
            for n, row in pairs:
                own = [] if isinstance(row.left, str) \
                    else stops[:len(row.left) - 1]
                if isinstance(row.right, str):
                    beside[n] = tuple(own + [right])
                    ends.append(right + bold.measure(row.right))
                else:
                    beside[n] = tuple(own + [right, value])
                    ends.append(value + font.measure(row.right[-1]))
        return stops, max(ends + [1]), beside

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
        for pull in reversed(pool.pulls):
            if wanted is not None and pull.stars not in wanted:
                continue
            tree.insert("", tk.END, tags=(self._star_tag(pull.stars),),
                        values=self._spaced((
                            pull.number, gh.unit_name(pull.res_id),
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
        except (OSError, ValueError) as e:
            # ImportRejected is a ValueError, and says what it expected.
            messagebox.showerror("Import JSON", "%s: %s" % (name, e))
            return
        before = gh.load(self._folder()).total
        try:
            gh.merge_import(self._folder(), batches)
        except (gh.StoreError, OSError) as e:
            messagebox.showerror("Import JSON", str(e))
            return
        self.refresh()
        after = self.history.total if self.history is not None else before
        read = sum(len(b["reward"]) for b in batches)
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
