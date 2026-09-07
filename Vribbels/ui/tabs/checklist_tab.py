"""Checklist tab: what resets, and how often.

Four headed columns, one per reset period, each listing the things that
come back on it. Some rows are LABELS ONLY: what they are waiting for
is completion status, and the capture carries the first pieces of it --
`point_entity` for the daily and weekly activity totals,
`mission_entities` for a per-mission `complete_time`, and
`season_pass_entity` for the Arkhianon Supply's rank. See
`docs/capture_pipeline.md`.

The rows that DO read a value get it from `_readings`, one place, keyed
by the row's own key rather than by its words -- two rows share the
words `Delegation Module` and differ only in the deadline they count
to.

The columns are built the way the Materials tab's are: content in the
EVEN grid columns with an empty expanding one between each pair, so the
block spans the window and the gaps across it stay equal. A row is one
Text per column rather than a Label per line -- a tab switch re-runs
the geometry managers over every widget on the page, and forty labels
is forty of them.
"""

import math
import time
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

import excursions
import item_amounts
import period_items
import shop_stock

from ..base_tab import BaseTab
from ..utils.scrolled_text import make_scrolled_text
from ..utils.tab_header import make_heading
from ui.scaling import px


# Each column's heading and its rows, left to right. Read off the
# game: the wording is the game's own where it has one, and `$hop`
# marks a shop tab rather than a currency.
#
# A row is `(key, label, widest)`. The KEY is what `_readings` answers
# to and is unique across the tab -- `Delegation Module` appears twice
# and `Nono's Shop` in two columns, so the words cannot serve. `widest`
# is the longest reading that row can show, which is what the column
# reserves room for; `None` is a row that shows none.
#
# **A column's rows are its own.** `Arkhianon Supply` appears under
# three headings because it resets three ways -- a daily set of
# missions, a weekly set, and the pass itself -- and they are three
# different things to check rather than one row repeated.
#
# The three constants below come first because `_shop_products` builds
# part of that table and reads them.

# What a shop sub-row's key is built from: the prefix, then the product
# id. The id has to be recoverable from the key, since that is what
# `_readings` looks the product up by.
SHOP_KEY_PREFIX = "shop:"

# How far a shop's products are indented under the shop's own row.
SHOP_INDENT = 27        # spacing: unique -- a shop's products under the shop -- run, run ↔

# What a value says about the row it sits on. GREEN is nothing left to
# do, RED is something left, and a row whose source a snapshot cannot
# answer for is neither.
DONE, TODO, UNKNOWN = "done", "todo", None


def _shop_products(prefix, period):
    """The sub-rows for one shop's products in one period.

    `(key, label, widest)` per product. Read from
    `shop_stock.PRODUCTS` rather than listed here: that table
    is where an identification lands, and a product gaining a name or a
    period should not also need a row typed out.

    **This is INCOMPLETE by design.** Only products that table names
    appear; the rest are in `docs/wire_hunt.tsv` waiting to be
    identified, so a shop's row set grows as they are.
    """
    return tuple(
        (SHOP_KEY_PREFIX + product_id, name, "%d/%d" % (limit, limit))
        for product_id, (name, limit, its_period)
        in sorted(shop_stock.PRODUCTS.items())
        if its_period == period and product_id.rsplit("_", 1)[0] == prefix)


COLUMNS = (
    ("Daily", (
        ("coffee", "Coffee", "Go drink!"),
        ("activity", "Activity (Dailies)", "100/100"),
        ("supply_daily", "Arkhianon Supply", None),
        ("excursions", "Excursions", "5/5"),
        ("chaos_delegation", "Chaos Delegation", None),
        ("other_daily", "Other Events", None),
    )),
    ("Weekly", (
        ("nono_weekly", "Nono's Shop", None),
    ) + _shop_products("town_shop_goods", "weekly") + (
        ("archive_weekly", "$hop - Memory Archive - Traveler", None),
        ("supply_weekly", "Arkhianon Supply", None),
        ("simulation", "Simulation Challenges", None),
        ("chaos_currency", "Chaos Currency", "99"),
        ("modules_soon", "Delegation Module", "99 expiring within 24h!"),
        ("modules_week", "Delegation Module", "99 expiring within 7 days"),
        ("sortie_currency", "Sortie Currency", "99/9"),
        ("seasonal_event", "Seasonal Event(s)", None),
        ("seasonal_shop", "Seasonal Shop", None),
        ("seasonal_score", "Seasonal Accumulated Score", "300000+/300000"),
    )),
    ("Monthly", (
        ("nono_monthly", "Nono's Shop", None),
    ) + _shop_products("town_shop_goods", "monthly") + (
        ("archive_monthly", "$hop - Memory Archive - Traveler", None),
        ("zeronium", "$hop - Zeronium Shop", None),
        ("blackhorn", "$hop - Blackhorn Trade", None),
        ("prism", "$hop - Exchange Shop - Prism Module", None),
    )),
    ("Other", (
        ("basin", "Basin of Hyperspace (21 days)", None),
        ("matrix", "Zero System Chaos Matrix (84? days)", None),
        ("supply_season", "Arkhianon Supply (42? days)", None),
        ("seasonal_event_other", "Seasonal Event (21 + 21 + 21 days)", None),
        ("sortie_other", "Sortie (21 days)", None),
        ("other_events_other", "Other Events", None),
    )),
)

# The rows' face. The headings use the shared helper's own.
ROW_FONT = ("Segoe UI", 9)

# `point_entity.day_point` is the day's ACTIVITY total and a hundred is
# a full day; anything short is drawn in the alert colour, which is the
# whole of what that row says.
ACTIVITY_FULL = 100
POINT_FIELD = "point_entity"

# The two weekly currencies, and the cap the game states for the second.
# The Card states one too -- four -- but a row that only ever reads
# `0`..`4` says as much without it, where Reason is spent in sevens and
# the ceiling is what says whether a run is affordable.
CHAOS_CURRENCY = 2000027        # Loot Certification Card
SORTIE_CURRENCY = 2000036       # Reason
SORTIE_CAP = 9

# The period item the two module rows count copies of, and the two
# windows they count it in. ROLLING, from the moment the tab is drawn
# -- not to the game's next reset. A copy expires on the stamp it
# carries, fourteen days after it was acquired, and no reset moves it.
#
# `(span in seconds, row key, words, unit, what the words divide by)`.
# The words take (how many, how long the last of them has, the unit),
# so a row reads `2 expiring within 6h!` where both copies are due
# today -- the window bounds what is counted, the words say what is
# actually about to go.
MODULE_ITEM = 3920026           # Time-Limited Command Delegation Module
MODULE_WINDOWS = (
    (24 * 3600, "modules_soon", "%d expiring within %d%s!", "h", 3600),
    (7 * 24 * 3600, "modules_week", "%d expiring within %d %s", "days",
     24 * 3600),
)

# Today's coffee: a CAPABILITY, so the row inverts it. The two words
# are the whole of what that row says.
COFFEE_PATH = ("characters", "town_data", "day_changeable_data",
               "is_coffee_possible")
COFFEE_TODO = "Go drink!"
COFFEE_DONE = "Tasty~"

# The Great Rift's weekly score. The standings nest season -> rank
# slot -> record, and the threshold that pays out rides in the same
# record -- `GREAT_RIFT_TARGET` is only what stands in when it does not.
GREAT_RIFT_FIELD = "disaster_boss_rank_entities"
GREAT_RIFT_TARGET = 300000

# What a score PAST the threshold reads as. The figure runs to seven
# digits where the row is about clearing a bar, so it is capped -- and
# the sign is what keeps a capped reading from being mistaken for one
# that landed exactly on it.
GREAT_RIFT_OVER = "+"


# What a value reads before any snapshot has reached the tab. NOT `0`,
# which is what an untouched day reads: nothing claimed and nothing
# recorded are different answers.
NO_DATA = "-"

# What separates one row from the next, as `spacing1` on every line
# after the first. A lever a rendered distance short of the rule: a
# Text line's own box already carries part of the pitch, and unlike a
# padding this cannot go negative.
ROW_PITCH = 4           # spacing: label row -> label row -- run, run ↕

# A row's words against its value, which is a left TAB STOP. A lever
# short of the rule, the words stopping inside their own advance.
LABEL_TO_VALUE = 6      # spacing: label ↔ its element -- run, run ↔

# The heading of a column against the first row under it. The gap runs
# from the heading's BASELINE to the row's CAPITAL, with the heading's
# box below its baseline and the row's box above its capital both
# inside it -- which is why the lever is at its floor.
HEADING_GAP = 0         # spacing: panel ↕ unrelated label -- heading, frame ↕

# What a Text puts around its own content, both sides together. Its
# `width` is in CHARACTERS and this block is sized in pixels, so the
# holder is fixed and the Text fills it.
TEXT_INSET = 2

# ---- the mission listing, TEMPORARY --------------------------------
#
# Every mission the capture carries, with what it reports, so the ids
# can be read off the screen and written into `docs/missions_id.tsv`.
# **Delete this block and its five constants once the missions are
# identified**; the rows above are what the tab is for.
DEBUG_MISSIONS = True
DEBUG_TITLE = "Mission ids (temporary)"
DEBUG_ROWS = 12         # visible lines; the rest scroll
DEBUG_COLS = 40         # characters, which is the widest line plus room
DEBUG_FONT = ("Consolas", 9)

# The field the missions arrive under, and what a row says when it has
# been finished. A `content_*` row never carries `complete_time` at
# all, so the two readings are not "done" and "not done" -- they are
# "reported done" and "said nothing".
MISSION_FIELD = "mission_entities"
DONE = "done"
NOT_DONE = "-"


class ChecklistTab(BaseTab):
    """The recurring-task columns."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        # (Text, rows) per column heading, for the refresh to rewrite.
        self.column_texts = {}
        # The temporary mission listing, or None while it is switched off.
        self.mission_text = None
        self.setup_ui()
        # Drawn once with nothing, so the tab is its rows rather than a
        # blank before the first capture.
        self.refresh_checklist()

        # And again whenever the tab is shown. Both load paths already
        # call the refresh, so this catches only the case where one of
        # them did not run -- and the cost of a redraw nobody needed is
        # four small Texts rewritten while the user is looking at them.
        notebook = getattr(self.context, "notebook", None)
        if notebook is not None:
            notebook.bind("<<NotebookTabChanged>>",
                          self._on_tab_changed, add="+")

    def _on_tab_changed(self, _event=None):
        """Redraw when this tab becomes the visible one."""
        try:
            current = self.notebook.nametowidget(self.notebook.select())
        except (tk.TclError, KeyError):
            return
        if current is self.frame:
            self.refresh_checklist()

    # ------------------------------------------------------------ build

    def setup_ui(self):
        """Build the Checklist tab UI."""
        # **Created before anything else on the tab.** The audit reaches
        # the columns through the tab's FIRST CHILD, and `winfo_children`
        # is in creation order -- so a block built ahead of this one
        # takes that position and every Checklist entry skips, silently.
        # `checks/check_tabs_build.py` holds it there.
        columns = ttk.Frame(self.frame)

        # Packed before the columns, which is a separate order: pack
        # hands each widget its requested size in turn and only then
        # gives the leftover to whatever expands.
        if DEBUG_MISSIONS:
            self._build_mission_list()

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        columns.pack(fill=tk.BOTH, expand=True, padx=px(2), pady=px((0, 2)))

        # Content in the EVEN grid columns, an empty expanding one
        # between each pair. Given to spacers of one uniform group the
        # leftover width lands as equal gaps with the block flush
        # against both edges; shared out inside the content cells it
        # lands unequally, the widest column keeping the least.
        for index in range(len(COLUMNS) + 1):
            columns.grid_columnconfigure(2 * index, weight=0)
        for index in range(len(COLUMNS)):
            # spacing: content frame -> content frame -- frame, frame ↔
            # NOT TRACKED: the distance is whatever the tab has spare
            # divided four ways, so it moves with the window. What is
            # fixed is that the four are equal.
            columns.grid_columnconfigure(2 * index + 1, weight=1,
                                         uniform="checklist")
        columns.grid_rowconfigure(0, weight=1)

        for index, (title, rows) in enumerate(COLUMNS):
            column = ttk.Frame(columns)
            column.grid(row=0, column=2 * index, sticky="nsew")
            self._build_column(column, title, rows)

    def _build_column(self, parent, title, rows):
        """One heading and the rows under it."""
        make_heading(parent, title).pack(anchor=tk.CENTER)

        font = tkfont.Font(font=ROW_FONT)
        # The words, plus a column reserved for the widest reading any
        # row in this column can show. RESERVED rather than fitted: a
        # column that sized to its content would move every row's words
        # the moment a figure gained a digit.
        #
        # A shop's products are indented under it, so their labels
        # reach further right than their words alone say.
        labels = max(font.measure(label) + (px(SHOP_INDENT)
                                            if _is_shop(key) else 0)
                     for key, label, _w in rows)
        stop = labels + TEXT_INSET + LABEL_TO_VALUE
        widest = max([font.measure(w) for _k, _l, w in rows if w] or [0])
        holder = tk.Frame(parent, width=stop + widest,
                          height=self._block_height(len(rows)),
                          bg=self.colors["bg"])
        holder.pack_propagate(False)
        # spacing: panel ↕ unrelated label -- heading, frame ↕
        holder.pack(anchor=tk.N, pady=px((HEADING_GAP, 0)))

        text = tk.Text(
            holder, wrap=tk.NONE, bd=0, highlightthickness=px(0),
            padx=px(0), pady=px(0),
            bg=self.colors["bg"], fg=self.colors["fg"], font=ROW_FONT,
            # Selectable but never focusable, and no insertion cursor:
            # the rows can be copied, and nothing about them invites
            # typing.
            takefocus=0, insertwidth=px(0), cursor="arrow",
            # A LEFT stop: a row's reading sits beside its own words
            # rather than at the block's far edge, where it would read
            # as belonging to the column instead of to the row.
            tabs=(stop,),
        )
        text.pack(fill=tk.BOTH, expand=True)
        # spacing: label row -> label row -- run, run ↕
        text.tag_configure("row", spacing1=px(ROW_PITCH))
        # A shop's products, indented under the shop's own row. In
        # PIXELS, on the line: a run of spaces is whatever the font
        # makes it, and this is a distance.
        # spacing: unique -- a shop's products under the shop -- run, run ↔
        text.tag_configure("indent", lmargin1=px(SHOP_INDENT))
        # Green is nothing left to do on that row, red is something
        # left. A row a snapshot cannot answer for takes neither.
        text.tag_configure(DONE, foreground=self.colors["green"])
        text.tag_configure(TODO, foreground=self.colors["red"])
        self.column_texts[title] = (text, rows)

    def _build_mission_list(self):
        """The temporary mission listing, bottom left. See DEBUG_MISSIONS."""
        # spacing: out of scope -- a temporary listing of mission ids, deleted once they are identified
        block = ttk.Frame(self.frame)
        block.pack(side=tk.BOTTOM, anchor=tk.W, padx=px(4), pady=px((0, 4)))
        ttk.Label(block, text=DEBUG_TITLE,
                  foreground=self.colors["fg_dim"]).pack(anchor=tk.W)
        self.mission_text = make_scrolled_text(
            block, self.colors, width=DEBUG_COLS, height=DEBUG_ROWS,
            wrap=tk.NONE, font=DEBUG_FONT, takefocus=0)
        self.mission_text.pack(anchor=tk.W)

    @staticmethod
    def _block_height(rows):
        """A column's height: its rows and the pitch between them.

        Measured off the face rather than multiplied by a guess -- a
        Text sizes in LINES and this block is pinned in pixels, so the
        two have to be reconciled somewhere.
        """
        # `rows` pitches, not `rows - 1`: `spacing1` is drawn above
        # EVERY line including the first, so a block sized for the gaps
        # BETWEEN rows is one pitch short and clips its last line.
        return rows * (tkfont.Font(font=ROW_FONT).metrics("linespace")
                       + px(ROW_PITCH))

    # ----------------------------------------------------------- update

    def refresh_checklist(self):
        """Redraw every reading from the loaded snapshot.

        Called automatically after data loads.
        """
        if not self.column_texts:
            return
        raw = getattr(self.optimizer, "raw_data", None) or {}
        readings = _readings(raw)
        for text, rows in self.column_texts.values():
            self._fill(text, rows, readings)
        if self.mission_text is not None:
            self._fill_missions(raw.get(MISSION_FIELD))

    @staticmethod
    def _fill(text, rows, readings):
        """Rewrite one column: its rows, and any reading beside one.

        Written whole rather than patched line by line -- a Text has no
        per-line assignment, and the block is small.
        """
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        for index, (key, label, _widest) in enumerate(rows):
            value, state = readings.get(key, (None, UNKNOWN))
            line = ("row", "indent") if _is_shop(key) else ("row",)
            text.insert(tk.END, (LINE_SEP if index else "") + label, line)
            if value is not None:
                text.insert(tk.END, COLUMN_SEP + value,
                            line + ((state,) if state else ()))
        text.config(state=tk.DISABLED)

    def _fill_missions(self, missions):
        """Rewrite the temporary mission listing. See DEBUG_MISSIONS.

        Takes either shape the field comes in: the addon's cache, keyed
        by res_id, or a bare list off the wire.
        """
        rows = missions.values() if isinstance(missions, dict) else missions
        lines = []
        for row in rows or ():
            if not isinstance(row, dict) or not row.get("res_id"):
                continue
            res_id = str(row["res_id"])
            lines.append((_family(res_id), res_id,
                          "%-24s %8s  %s" % (
                              res_id, row.get("score", ""),
                              DONE if row.get("complete_time") else NOT_DONE)))
        lines.sort()
        body = (LINE_SEP.join(line for _, _, line in lines) if lines
                else "no missions in this snapshot")
        self.mission_text.config(state=tk.NORMAL)
        self.mission_text.delete("1.0", tk.END)
        self.mission_text.insert(tk.END, body)
        self.mission_text.config(state=tk.DISABLED)


# What separates one row from the next, and a row from its value.
# Named because a Text's columns ARE its tabs and its rows ARE its
# newlines -- so these two characters are structure rather than
# punctuation.
LINE_SEP = "\n"
COLUMN_SEP = "\t"


def _readings(raw, now=None):
    """{row key: (text, alert)} for every row that shows a value.

    One place for all of them, and pure but for the clock, so the whole
    set can be exercised from a snapshot without a window. `now` is
    epoch seconds, defaulting to the real clock.

    A row whose source is missing reads `-` rather than `0`: nothing
    claimed and nothing recorded are different answers.
    """
    now = time.time() if now is None else now
    amounts = item_amounts.held(raw)
    expiries = period_items.held(raw.get("inventory") or {}).get(
        MODULE_ITEM, ())

    out = {}

    # The day's ACTIVITY total.
    point = raw.get(POINT_FIELD)
    day = point.get("day_point") if isinstance(point, dict) else None
    if _is_count(day):
        out["activity"] = ("%d/%d" % (day, ACTIVITY_FULL),
                           _done(day >= ACTIVITY_FULL))
    else:
        out["activity"] = ("%s/%d" % (NO_DATA, ACTIVITY_FULL), UNKNOWN)

    # Today's coffee. **The field is a CAPABILITY, so the row inverts
    # it**: `is_coffee_possible` true means one is still going begging.
    possible = _dig(raw, COFFEE_PATH)
    if isinstance(possible, bool):
        out["coffee"] = (COFFEE_TODO if possible else COFFEE_DONE,
                         _done(not possible))
    else:
        out["coffee"] = (NO_DATA, UNKNOWN)

    # Communication Passes left today. Not an item and not a currency --
    # `excursions.passes_left` says why that reading is the only one a
    # snapshot allows.
    left = excursions.passes_left(raw)
    out["excursions"] = (
        "%s/%d" % (NO_DATA if left is None else left, excursions.DAILY_PASSES),
        UNKNOWN if left is None else _done(left == 0))

    # Both weekly currencies are things to SPEND, so a holding is work
    # left rather than a stock to be pleased about.
    cards = amounts.get(CHAOS_CURRENCY, 0)
    out["chaos_currency"] = ("%d" % cards, _done(cards == 0))
    reason = amounts.get(SORTIE_CURRENCY, 0)
    out["sortie_currency"] = ("%d/%d" % (reason, SORTIE_CAP),
                              _done(reason == 0))

    # The Great Rift's weekly score against the threshold that pays.
    # **Capped in the DISPLAY**, because the figure runs to seven digits
    # and the row is about whether the threshold is cleared. A capped
    # reading carries `GREAT_RIFT_OVER` so it cannot be read as a score
    # that landed exactly on the bar.
    score, target = _great_rift(raw)
    if score is None:
        out["seasonal_score"] = ("%s/%d" % (NO_DATA, target), UNKNOWN)
    else:
        over = GREAT_RIFT_OVER if score > target else ""
        out["seasonal_score"] = ("%d%s/%d" % (min(score, target), over,
                                              target),
                                 _done(score >= target))

    # The modules, by how long each copy has left. **The two windows
    # NEST**: everything inside 24 hours is inside seven days, so the
    # second count includes the first. That is what the two lines say,
    # and it is the opposite of the Materials tab's module buckets,
    # which partition.
    #
    # The number in the WORDS is the longest any counted copy has left,
    # not the window itself -- three copies all due in six hours read
    # `within 6h!` rather than `within 24h!`. Rounded UP, so a copy is
    # never promised time it has already spent. With none counted there
    # is no longest, and the window's own bound stands in.
    for span, key, words, unit, divisor in MODULE_WINDOWS:
        inside = [end for end in expiries if end <= now + span]
        edge = (max(inside) - now) if inside else span
        out[key] = (words % (len(inside),
                             max(1, math.ceil(edge / divisor)), unit),
                    _done(not inside))

    # The shops, one sub-row per product. `-` where the field cannot be
    # read honestly -- see `shop_stock.remaining`.
    for key, product_id in _shop_rows():
        stock, limit = shop_stock.remaining(product_id, raw)
        if limit is None:
            out[key] = (NO_DATA, UNKNOWN)
        elif stock is None:
            out[key] = ("%s/%d" % (NO_DATA, limit), UNKNOWN)
        else:
            out[key] = ("%d/%d" % (stock, limit), _done(stock == 0))
    return out


def _great_rift(raw):
    """(this week's score, the threshold that pays it out).

    The standings nest season -> rank slot -> record, and every season
    the account has played keeps its row -- so the live one is picked
    by the LATEST `score_week_id`, not by the biggest score. Past
    seasons carry higher totals than the current week does, and their
    thresholds differ too: the older ones ask 500000 where this one
    asks 300000.

    The threshold rides in the chosen row; `GREAT_RIFT_TARGET` stands
    in only where it does not.
    """
    seasons = raw.get(GREAT_RIFT_FIELD)
    live = None
    for slots in (seasons or {}).values() if isinstance(seasons, dict) else ():
        for row in (slots or {}).values() if isinstance(slots, dict) else ():
            if not isinstance(row, dict) or not _is_count(
                    row.get("week_total_score")):
                continue
            # Latest week first, then the higher score of that week's
            # rank slots -- the account holds one row per slot and they
            # report the same week differently.
            rank = (row.get("score_week_id") or 0, row["week_total_score"])
            if live is None or rank > live[0]:
                live = (rank, row)
    if live is None:
        return None, GREAT_RIFT_TARGET
    row = live[1]
    target = row.get("week_total_score_reward")
    return row["week_total_score"], (target if _is_count(target)
                                     else GREAT_RIFT_TARGET)


def _shop_rows():
    """[(row key, product id)] for every shop sub-row on the tab."""
    return [(key, key.split(":", 1)[1])
            for _title, rows in COLUMNS for key, _label, _w in rows
            if key.startswith(SHOP_KEY_PREFIX)]


def _expiring_by(expiries, deadline):
    """How many copies expire at or before `deadline`, epoch seconds."""
    return sum(1 for end in expiries if end <= deadline)


def _is_count(value):
    """True for a plain int. `bool` is an int and is not a count."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_shop(key):
    """True for a row that is one shop product under its shop."""
    return key.startswith(SHOP_KEY_PREFIX)


def _done(finished):
    """`DONE` or `TODO`, which is what a value's colour comes from."""
    return DONE if finished else TODO


def _dig(node, path):
    """The value at a path of dict keys, or None where it is not there."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _family(res_id):
    """The id's leading words, which is the set it belongs to.

    Groups the listing the way `docs/missions_id_dump.py` groups the
    file it is read into. Split at the first NUMBERED segment: the
    numbers are the mission within its set, and how many of them an id
    carries varies between sets.
    """
    parts = []
    for part in res_id.split("_"):
        if part.isdigit():
            break
        parts.append(part)
    return "_".join(parts) or res_id
