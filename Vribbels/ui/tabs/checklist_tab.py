"""Checklist tab: what resets, and how often.

Four headed columns, one per reset period, each listing the things that
come back on it. Some rows are LABELS ONLY: what they are waiting for
is completion status, and the capture carries the first pieces of it --
`point_entity` for the daily and weekly activity totals,
`mission_entities` for a per-mission `complete_time`, and
`season_pass_entity` for the Arkhianon Supply's rank. See
`docs/capture_pipeline.md`.

**A shop's rows are read off the wire, not written here.**
`shop_res_data` carries every product's item, cap, period, price and
display order, so a column's shop rows are rebuilt from the snapshot
whenever the set changes -- a product the game adds appears with no
edit. `shop_stock` is what reads it.

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

from datetime import datetime, timezone

import excursions
import item_amounts
import period_items
import schedules
import shop_stock
import weekly_reset
from game_data.constants import item_names

from ..base_tab import BaseTab
from ..utils.checkbox import make_checkbox
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
# `_readings` looks the product up by. A shop's own heading row takes
# the second prefix, so the two cannot collide.
SHOP_KEY_PREFIX = "shop:"
SHOP_HEAD_PREFIX = "shophead:"

# How far a shop's products are indented under the shop's own row.
SHOP_INDENT = 27        # spacing: unique -- a shop's products under the shop -- run, run ↔

# What a compact `tk.Checkbutton` costs beyond the width of its own
# words: its indicator, and the gap Tk puts between the two. MEASURED
# once and written down -- it is the widget's own, the same on every
# label, and not readable before the widget exists. The column reserves
# it so a checkbox row's words stop where a plain row's do.
CHECKBOX_OVERHEAD = 23

# What a value says about the row it sits on. GREEN is nothing left to
# do, RED is something left, and a row whose source a snapshot cannot
# answer for is neither.
DONE, TODO, UNKNOWN = "done", "todo", None

# What an UNTRACKED shop product's reading is drawn in: the dim colour
# explanation text uses. Red and green say what is left to do, and a
# product the user is not tracking has nothing to say either way.
MUTED = "muted"

# What a shop product with no per-period cap reads. It can always be
# bought, so there is nothing to count down and nothing to finish.
NO_LIMIT = "unlimited"


# Which `event_schedules` group dates each row, and so what its
# countdown counts down to. **The lengths used to be guesses in the
# labels** -- `(21 days)`, `(84? days)` -- and the wire carries the
# real window for every one of them.
COUNTDOWNS = {
    "basin": "HYPER_SPACE_SEASON",
    "matrix": "ZERO_REWARD_LIST",
    "supply_season": "SEASON_PASS",
    # `EVENT_SCHEDULE` is NOT here. It holds several unrelated events
    # at once -- a policy event, a stock event and the seasonal one --
    # and nothing in the window says which is which, so taking the
    # soonest picks whichever happens to end first.
    "shophead:shop_assault/none": "ASSAULT_SCHEDULE",
}

# Shops whose products are kept PER SEASON, and where the live season
# comes from. Every season the account has played keeps its products in
# the table, so one screen offering one Tear of God reads as three.
SEASONAL_SHOP_CATEGORY = "shop_disaster"


def shop_rows(shop, period, raw):
    """The sub-rows for one shop's products in one period.

    `(key, label, widest)` per product, straight off the wire: the
    shop's own `sort` gives the order, `limit_count` the reserve, and
    the item the product gives its name. Nothing is hand-written any
    more -- a product the game adds appears the next time the login
    burst is captured.
    """
    prefix = (_live_season(raw) if shop[0] == SEASONAL_SHOP_CATEGORY
              else None)
    if shop[0] == SEASONAL_SHOP_CATEGORY and not prefix:
        # Without a live season every season's products would show.
        return ()
    out = []
    for product_id, define in shop_stock.products(shop, period, raw, prefix):
        limit = define.get("limit_count")
        out.append((SHOP_KEY_PREFIX + product_id,
                    product_label(define),
                    "%d/%d" % (limit, limit)))
    return tuple(out)


def product_label(define):
    """What to call a product: the item it gives, and how many.

    `x1` is left off, being the common case and no information. An item
    no table names falls back to its id, which is the same marking the
    Capture Log uses -- a number on screen is an invitation to identify
    it, where a blank is a bug nobody can see.
    """
    res_id = define.get("product_link_item_id")
    name = ITEM_NAMES.get(res_id) or str(res_id)
    count = define.get("product_count")
    return name if count in (1, None) else "%s x%s" % (name, count)


# Every id the build can name, built once. A shaped row's name is
# SPELLED OUT there -- reading `row[0]` off a table gives the group
# (`Combatant`, `Passion`), not a name.
ITEM_NAMES = item_names()


# The columns, as a skeleton. Each is `(heading, rows, shops)`: `rows`
# are the fixed ones and `shops` names the shop categories whose
# products are folded in, each under a heading of its own.
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
COLUMNS = (
    ("Daily", (
        ("coffee", "Coffee", "Go drink!"),
        ("activity", "Activity (Dailies)", "100/100 Unclaimed"),
        ("supply_daily", "Arkhianon Supply", "3/3"),
        ("excursions", "Excursions", "5/5"),
        ("chaos_delegation", "Chaos Delegation", "Go run!"),
        ("other_daily", "Other Events", None),
    ), ()),
    ("Weekly", (
        ("supply_weekly", "Arkhianon Supply", "10000/10000"),
        ("simulation", "Simulation Challenges", "3/3"),
        ("chaos_currency", "Chaos Currency", "99"),
        ("modules_soon", "Delegation Module", "99 expiring within 24h!"),
        ("modules_week", "Delegation Module", "99 expiring within 7 days"),
        ("sortie_currency", "Sortie Currency", "99/9"),
        ("seasonal_event", "Seasonal Event(s)", None),
        ("seasonal_score", "Seasonal Accumulated Score", "300000+/300000"),
    ), (("shop_town", "none"),
        ("shop_gacha_dup", "shop_gacha_dup_legend"),
        ("shop_disaster", "shop_disaster_1"))),
    ("Monthly", (), (("shop_town", "none"),
                     ("shop_gacha_dup", "shop_gacha_dup_legend"),
                     ("shop_hyperspace", "none"),
                     ("shop_chaos", "none"),
                     ("shop_exchange_product", "shop_card_factor"))),
    ("Other", (
        ("basin", "Basin of Hyperspace", "99/99, 99 days"),
        ("matrix", "Zero System Chaos Matrix", "99 days"),
        ("supply_season", "Arkhianon Supply", "70/70, 99 days"),
        ("seasonal_event_other", "Seasonal Event", None),
        ("other_events_other", "Other Events", None),
    ), (("shop_assault", "none"),)),
)

# Which period each column's shop products are taken from.
PERIOD_BY_COLUMN = {"Weekly": "weekly", "Monthly": "monthly",
                    "Other": "account"}


def columns_for(raw, tracked=None):
    """The four columns' rows for one snapshot.

    The shop rows are rebuilt from the wire every time, so a product
    the game adds or a cap it changes reaches the tab with no edit.

    `tracked` is a predicate on a product id. **An untracked product
    sinks to the bottom of its own shop** rather than leaving the tab:
    the shop still sells it, and a row that vanished would read as a
    bug. Ticking it puts it back where the shop keeps it.
    """
    out = []
    for title, fixed, shops in COLUMNS:
        rows = list(fixed)
        period = PERIOD_BY_COLUMN.get(title)
        # **The shop's own heading goes in whether or not its products
        # do.** A snapshot from before `shop_res_data` was captured
        # knows no products, and a column that emptied itself would
        # read as a broken tab rather than as data not yet arrived.
        for shop in shops if period else ():
            head = SHOP_HEAD_PREFIX + "/".join(shop)
            rows.append((head, shop_stock.SHOPS[shop],
                         "99 days" if head in COUNTDOWNS else None))
            products = shop_rows(shop, period, raw)
            if tracked is not None:
                # Stable within each half: the shop's own order is kept
                # on both sides of the split, so ticking one product
                # moves that product and nothing else.
                products = ([row for row in products
                             if tracked(_product_of(row[0]))]
                            + [row for row in products
                               if not tracked(_product_of(row[0]))])
            rows.extend(products)
        out.append((title, tuple(rows)))
    return tuple(out)


# The rows' face. The headings use the shared helper's own.
ROW_FONT = ("Segoe UI", 9)

# `point_entity.day_point` is the day's ACTIVITY total and a hundred is
# a full day; anything short is drawn in the alert colour, which is the
# whole of what that row says.
ACTIVITY_FULL = 100
POINT_FIELD = "point_entity"

# **`day_point` is the points EARNED, not the reward claimed.** It
# already read 100 before Claim All and did not move when the rewards
# landed, so a full day and a CLAIMED day are two readings and only the
# first is on the wire.
#
# Until the claim flag is found, the claim is inferred from its
# payout: the day's rewards are 60 Crystals, so a Crystal gain of
# exactly that on a day already at 100 is taken as the claim. **A
# GUESS, and a coarse one** -- 60 Crystals from anywhere else on a full
# day reads the same. `docs/wire_hunt.tsv` carries the hunt for the
# real flag.
ACTIVITY_CLAIM_ITEM = 2000004        # Crystal
ACTIVITY_CLAIM_PAYOUT = 60
ACTIVITY_UNCLAIMED = " Unclaimed"
ACTIVITY_CLAIMED = "All Claimed"

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

# The Arkhianon Supply. Its own record carries the pass level and the
# week's EXP; the missions are rows in `mission_entities`, and a row's
# `complete_time` is set when its REWARD IS CLAIMED, not when the task
# is finished -- which is what a checklist wants to know.
#
# The three daily ids were established by claiming them one at a time
# and reading the id off the request. **The weekly set is not here**:
# only one of the twelve has been identified, so the weekly row counts
# EXP instead, which needs no id at all.
PASS_FIELD = "season_pass_entity"
PASS_LIST_FIELD = "season_pass_entities"
PASS_MISSION_FIELD = "mission_entities"
PASS_MISSION_PREFIX = "pass_mission"
PASS_WEEK_EXP_FULL = 10000
PASS_LEVEL_FULL = 70

# How many daily missions the pass hands out. **Not derivable**: the
# game issues a mission lazily, so the rows carrying today's
# `issued_time` are the ones handed out SO FAR and counting them
# understates the day. Read off the game's own screen.
PASS_DAILY_COUNT = 6

# The stage whose per-period run limit IS the Simulation Challenges,
# and how many runs a week allows. Same shape as a shop row: `count` is
# the runs TAKEN and `reset_time` is when it last moved, so it goes
# stale across a reset the same way.
SIMULATION_FIELD = "stage_limit_entities"
SIMULATION_STAGE = "content_boss"
SIMULATION_RUNS = 3

# Today's Chaos Delegation. **There is no balance to read**: the free
# daily entry is granted and spent in the same transaction, so the
# currency's `amount` sits at 0 either way and only `total_use_amount`
# moves. What says whether it went today is `last_update` -- the moment
# that currency last changed -- against the day's own reset.
#
# Evidence, from one capture and on both sides of the boundary: at
# login it read 13:14 UTC against an 18:00 reset (not used today), and
# after entering a chaos stage 19:51 (used).
DELEGATION_CURRENCY = 2000048
DELEGATION_PATH = ("characters", "currencies", str(DELEGATION_CURRENCY),
                   "last_update")
DELEGATION_TODO = "Go run!"
DELEGATION_DONE = "Done"

# The Basin of Hyperspace. Its progress is its OBJECTIVES, not its
# stages: `mission_seasson_entities` (the game's own spelling) holds
# them per Basin season, and a scored row is one done.
#
# **Two seasons run at once**, and the game shows one figure. The row
# reports the LEAST complete of them -- the one with work left -- so a
# fresh season shows through beside a finished one. With all of them
# done every choice reads the same.
BASIN_FIELD = "mission_seasson_entities"

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



class ChecklistTab(BaseTab):
    """The recurring-task columns."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        # (Text, rows) per column heading, for the refresh to rewrite,
        # and the row set they were built for. A snapshot that changes
        # the set -- a shop gaining a product -- rebuilds them.
        self.column_texts = {}
        self._built_signature = None
        # The shop checkboxes embedded in the columns. A Text does not
        # own an embedded window, so they are held here and destroyed
        # on the next rewrite.
        self._boxes = []
        # The day the Activities reward was last seen being claimed, and
        # what the Crystal balance read on the previous refresh. See
        # `ACTIVITY_CLAIM_ITEM`: the claim is inferred from its payout
        # because nothing on the wire states it, so it has to be caught
        # as it happens and remembered.
        self._activity_claimed_day = None
        self._crystals = None
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

        # One frame per column, EMPTY. What goes in them depends on the
        # snapshot -- a shop's products are read off the wire -- so the
        # contents are built on the first refresh and rebuilt whenever
        # the row set changes. The frames themselves never move: the
        # audit reaches a column through its position among these.
        self._column_frames = []
        for index in range(len(COLUMNS)):
            column = ttk.Frame(columns)
            column.grid(row=0, column=2 * index, sticky="nsew")
            self._column_frames.append(column)

    def _tracked(self, product_id):
        """Whether the user ticked one shop product. See ChecklistManager."""
        manager = getattr(self.context, "checklist_manager", None)
        return manager.is_tracked(product_id) if manager else True

    def _toggle(self, product_id, variable):
        """Persist one checkbox, then redraw.

        **Redrawn on an idle callback, never here.** Ticking changes
        the row ORDER, so the redraw destroys every widget in the
        column -- this checkbox among them -- and doing that inside its
        own command is how Tk gets a callback on a dead widget.
        """
        manager = getattr(self.context, "checklist_manager", None)
        if manager is not None:
            manager.set_tracked(product_id, bool(variable.get()))
        self.frame.after_idle(self.refresh_checklist)

    def _rebuild_columns(self, raw):
        """(Re)build every column's heading and rows for one snapshot.

        Only when the row set actually changed: a rebuild destroys and
        recreates four Texts, and the ordinary case is a refresh where
        nothing but the numbers moved.
        """
        built = columns_for(raw, self._tracked)
        signature = tuple((title, tuple(key for key, _l, _w in rows))
                          for title, rows in built)
        # Ticking the LAST product of a shop changes no order, so the
        # keys alone would not notice it -- and its colour still has to
        # change. The tracked set goes in the signature too.
        signature += (tuple(sorted(
            product_id for _k, product_id, _d in _shop_rows(raw)
            if self._tracked(product_id))),)
        if signature == self._built_signature:
            return
        self._built_signature = signature
        self.column_texts = {}
        for frame, (title, rows) in zip(self._column_frames, built):
            for child in frame.winfo_children():
                child.destroy()
            self._build_column(frame, title, rows)

    def _build_column(self, parent, title, rows):
        """One heading and the rows under it."""
        make_heading(parent, title).pack(anchor=tk.CENTER)

        if not rows:
            return
        font = tkfont.Font(font=ROW_FONT)
        # The words, plus a column reserved for the widest reading any
        # row in this column can show. RESERVED rather than fitted: a
        # column that sized to its content would move every row's words
        # the moment a figure gained a digit.
        #
        # A shop's products are indented under it, so their labels
        # reach further right than their words alone say.
        labels = max(font.measure(label)
                     + (px(SHOP_INDENT) + px(CHECKBOX_OVERHEAD)
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
        text.tag_configure(MUTED, foreground=self.colors["fg_dim"])
        self.column_texts[title] = (text, rows)

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
        raw = getattr(self.optimizer, "raw_data", None) or {}
        self._rebuild_columns(raw)
        readings = _readings(raw, claimed=self._activity_claim(raw))
        # **Cleared ONCE, not per column.** `_fill` runs four times and
        # every checkbox on the tab is in one list, so clearing inside
        # it made each column destroy the one before -- leaving only
        # the last column's boxes alive and the rest blank.
        for box in self._boxes:
            box.destroy()
        self._boxes = []
        for text, rows in self.column_texts.values():
            self._fill(text, rows, readings)

    def _activity_claim(self, raw):
        """Whether today's Activities reward has been taken.

        **Inferred from the payout**, because nothing on the wire says.
        A Crystal balance that rises by exactly the day's reward while
        the day is already full is taken as the claim, and the day it
        happened on is remembered so the row does not revert on the
        next refresh. A new `day_id` clears it.

        Returns False until a rise is actually seen, so a session that
        starts after the claim reads `Unclaimed` until the next one.
        That is the cost of not having the flag.
        """
        point = raw.get(POINT_FIELD)
        point = point if isinstance(point, dict) else {}
        day_id, day = point.get("day_id"), point.get("day_point")
        if self._activity_claimed_day != day_id:
            self._activity_claimed_day = None
        crystals = item_amounts.held(raw).get(ACTIVITY_CLAIM_ITEM)
        before, self._crystals = self._crystals, crystals
        if (self._activity_claimed_day is None
                and _is_count(day) and day >= ACTIVITY_FULL
                and _is_count(before) and _is_count(crystals)
                and crystals - before == ACTIVITY_CLAIM_PAYOUT):
            self._activity_claimed_day = day_id
        return self._activity_claimed_day is not None

    def _fill(self, text, rows, readings):
        """Rewrite one column: its rows, and any reading beside one.

        Written whole rather than patched line by line -- a Text has no
        per-line assignment, and the block is small.

        **A shop product's label is a CHECKBOX**, embedded in the line
        with `window_create`. The widget goes in at the line's start,
        so the line's own `lmargin1` indents the checkbox itself and
        its left edge lands where an ordinary row's words do.
        """
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        for index, (key, label, _widest) in enumerate(rows):
            value, state = readings.get(key, (None, UNKNOWN))
            line = ("row", "indent") if _is_shop(key) else ("row",)
            if index:
                text.insert(tk.END, LINE_SEP, line)
            if _is_shop(key):
                # An untracked product says so in its colour: the
                # reading is greyed like explanation text and the row
                # takes neither red nor green.
                if not self._tracked(_product_of(key)):
                    state = MUTED
                text.window_create(tk.END, window=self._checkbox(text, key,
                                                                 label, state))
            else:
                text.insert(tk.END, label, line)
            if value is not None:
                text.insert(tk.END, COLUMN_SEP + value,
                            line + ((state,) if state else ()))
        text.config(state=tk.DISABLED)

    def _checkbox(self, parent, key, label, state):
        """One shop product's checkbox, kept alive on the tab.

        Held in `_boxes` because a Text does not own an embedded
        window: dropping the reference leaves the widget parented and
        undestroyed on the next rewrite.
        """
        product_id = _product_of(key)
        variable = tk.BooleanVar(value=self._tracked(product_id))
        box = make_checkbox(
            parent, self.colors, text=label, variable=variable,
            compact=True,
            fg=self.colors["fg_dim"] if state is MUTED else None,
            command=lambda p=product_id, v=variable: self._toggle(p, v))
        self._boxes.append(box)
        return box



# What separates one row from the next, and a row from its value.
# Named because a Text's columns ARE its tabs and its rows ARE its
# newlines -- so these two characters are structure rather than
# punctuation.
LINE_SEP = "\n"
COLUMN_SEP = "\t"


def _readings(raw, now=None, claimed=False):
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

    # The day's ACTIVITY total, and whether its rewards were taken.
    point = raw.get(POINT_FIELD)
    day = point.get("day_point") if isinstance(point, dict) else None
    if not _is_count(day):
        out["activity"] = ("%s/%d" % (NO_DATA, ACTIVITY_FULL), UNKNOWN)
    elif claimed:
        out["activity"] = (ACTIVITY_CLAIMED, DONE)
    else:
        out["activity"] = ("%d/%d%s" % (day, ACTIVITY_FULL,
                                        ACTIVITY_UNCLAIMED), TODO)

    # Today's coffee. **The field is a CAPABILITY, so the row inverts
    # it**: `is_coffee_possible` true means one is still going begging.
    possible = _dig(raw, COFFEE_PATH)
    if isinstance(possible, bool):
        out["coffee"] = (COFFEE_TODO if possible else COFFEE_DONE,
                         _done(not possible))
    else:
        out["coffee"] = (NO_DATA, UNKNOWN)

    # Today's Chaos Delegation, off when its currency last moved. The
    # daily boundary is the weekly one's hour on any day, so the reset
    # BEFORE now is what a stamp is measured against.
    used = _dig(raw, DELEGATION_PATH)
    if _is_count(used):
        today = used >= _last_daily_reset(now)
        out["chaos_delegation"] = (DELEGATION_DONE if today
                                   else DELEGATION_TODO, _done(today))
    else:
        out["chaos_delegation"] = (NO_DATA, UNKNOWN)

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

    # The Arkhianon Supply, three ways. A mission's `complete_time` is
    # set when its reward is CLAIMED, so a finished-but-unclaimed
    # mission still reads as work left -- which it is.
    # A DAILY mission is one the pass issued since the day's own reset,
    # which is what tells it from a weekly without an id list -- and an
    # id list would not survive the season number changing anyway.
    missions = raw.get(PASS_MISSION_FIELD)
    if isinstance(missions, dict):
        since = _last_daily_reset(now)
        claimed = sum(1 for res_id, row in missions.items()
                      if str(res_id).startswith(PASS_MISSION_PREFIX)
                      and _is_count(row.get("issued_time"))
                      and row["issued_time"] >= since
                      and row.get("complete_time"))
        out["supply_daily"] = ("%d/%d" % (claimed, PASS_DAILY_COUNT),
                               _done(claimed >= PASS_DAILY_COUNT))
    else:
        out["supply_daily"] = ("%s/%d" % (NO_DATA, PASS_DAILY_COUNT), UNKNOWN)

    # The week's EXP and the pass's level, both off the pass's own
    # record. EXP rather than a mission count, because only one of the
    # twelve weekly missions has been identified.
    record = _live_pass(raw)
    week_exp = record.get("week_exp")
    if _is_count(week_exp):
        out["supply_weekly"] = (
            "%d/%d" % (min(week_exp, PASS_WEEK_EXP_FULL), PASS_WEEK_EXP_FULL),
            _done(week_exp >= PASS_WEEK_EXP_FULL))
    else:
        out["supply_weekly"] = ("%s/%d" % (NO_DATA, PASS_WEEK_EXP_FULL),
                                UNKNOWN)
    level = record.get("free_reward_rank")
    if _is_count(level):
        out["supply_season"] = ("%d/%d" % (min(level, PASS_LEVEL_FULL),
                                           PASS_LEVEL_FULL),
                                _done(level >= PASS_LEVEL_FULL))
    else:
        out["supply_season"] = ("%s/%d" % (NO_DATA, PASS_LEVEL_FULL), UNKNOWN)

    # Simulation Challenges: the runs LEFT this week. Stale across a
    # reset the same way a shop row is, and read through the same
    # boundary.
    stage = (raw.get(SIMULATION_FIELD) or {}).get(SIMULATION_STAGE)         if isinstance(raw.get(SIMULATION_FIELD), dict) else None
    left = None
    if isinstance(stage, dict) and _is_count(stage.get("count")):
        started = shop_stock.period_start("weekly", raw, now)
        touched = stage.get("reset_time")
        stale = isinstance(touched, int) and touched < started
        left = SIMULATION_RUNS if stale else max(
            0, SIMULATION_RUNS - stage["count"])
    if left is None:
        out["simulation"] = ("%s/%d" % (NO_DATA, SIMULATION_RUNS), UNKNOWN)
    else:
        out["simulation"] = ("%d/%d" % (left, SIMULATION_RUNS),
                             _done(left == 0))

    # The Basin of Hyperspace: objectives done, out of the season's own
    # total. Nothing states the total, so it is how many the season
    # holds -- which is the same figure the game shows.
    done, total = _basin(raw)
    if total is None:
        out["basin"] = (NO_DATA, UNKNOWN)
    else:
        out["basin"] = ("%d/%d" % (done, total), _done(done >= total))

    # The shops, one sub-row per product. `-` where the field cannot be
    # read honestly -- see `shop_stock.remaining`.
    _add_countdowns(out, raw, now)

    for key, product_id, define in _shop_rows(raw):
        stock, limit = shop_stock.remaining(product_id, define, raw, now)
        if limit is None:
            # No cap: it can always be bought, so nothing counts down
            # and nothing is finished. Such a product gets no ROW
            # either -- this is only here for a reading asked of one.
            continue
        elif stock is None:
            out[key] = ("%s/%d" % (NO_DATA, limit), UNKNOWN)
        else:
            out[key] = ("%d/%d" % (stock, limit), _done(stock == 0))
    return out


def _last_daily_reset(now):
    """The 18:00 UTC boundary before `now`, epoch seconds.

    The same hour the week turns on, which is why `weekly_reset` owns
    it -- `RESET_HOUR` is the one number, and correcting the game's
    reset time stays one edit.
    """
    at = datetime.fromtimestamp(now, timezone.utc).replace(
        hour=weekly_reset.RESET_HOUR, minute=0, second=0, microsecond=0)
    stamp = at.timestamp()
    return stamp if stamp <= now else stamp - 24 * 3600


def _live_pass(raw):
    """The Arkhianon Supply's own record, or {}.

    Two shapes: a claim reply sends the ONE live pass as
    `season_pass_entity`, and the login burst sends every pass the
    account has played as a LIST. Past passes sit at their full 70 and
    10000, so taking the wrong one reads as a finished week -- the live
    one is the latest `week_id`.
    """
    record = raw.get(PASS_FIELD)
    if isinstance(record, dict) and record:
        return record
    live = None
    for row in raw.get(PASS_LIST_FIELD) or []:
        if not isinstance(row, dict):
            continue
        week = row.get("week_id") or 0
        if live is None or week >= live[0]:
            live = (week, row)
    return live[1] if live else {}


def _basin(raw):
    """(objectives done, objectives in the season), or (0, None).

    The LEAST complete season, which is the one with work left. Ties go
    to whichever sorts last, so two finished seasons read the same
    either way.
    """
    seasons = raw.get(BASIN_FIELD)
    best = None
    for name in sorted(seasons or {}) if isinstance(seasons, dict) else ():
        rows = seasons[name]
        if not isinstance(rows, dict) or not rows:
            continue
        done = sum(1 for row in rows.values()
                   if isinstance(row, dict) and row.get("score"))
        if best is None or done - len(rows) <= best[0] - best[1]:
            best = (done, len(rows))
    return best if best else (0, None)


def _add_countdowns(out, raw, now):
    """Fold each dated content's remaining time into its own row.

    APPENDED to whatever the row already reads rather than replacing
    it: the Basin says how many objectives are done AND how long is
    left, and the pass says its level and its season's end. A row with
    no other reading takes the time alone.

    A content whose window the snapshot does not carry is left as it
    was -- no window is not the same as no time left.
    """
    for key, group in COUNTDOWNS.items():
        left = schedules.countdown(schedules.remaining(group, raw, now))
        if not left:
            out.setdefault(key, (NO_DATA, UNKNOWN))
            continue
        text, state = out.get(key, (None, UNKNOWN))
        out[key] = (left if text in (None, NO_DATA)
                    else "%s, %s" % (text, left), state)


def _live_season(raw):
    """The live disaster season's id, or None.

    The standings keep a row per season the account has played, so the
    live one is the latest `score_week_id` -- the same reading the
    Great Rift row makes, and for the same reason.
    """
    seasons = raw.get(GREAT_RIFT_FIELD)
    live = None
    for name, slots in (seasons or {}).items() if isinstance(
            seasons, dict) else ():
        for row in (slots or {}).values() if isinstance(slots, dict) else ():
            if not isinstance(row, dict):
                continue
            week = row.get("score_week_id") or 0
            if live is None or week > live[0]:
                live = (week, name)
    return live[1] if live else None


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


def _product_of(key):
    """The product id inside a shop row's key."""
    return key[len(SHOP_KEY_PREFIX):]


def _shop_rows(raw):
    """[(row key, product id, definition)] for every shop sub-row."""
    out = []
    for category, defines in shop_stock.definitions(raw).items():
        for product_id, define in defines.items():
            if not isinstance(define, dict):
                continue
            shop = (category, define.get("link_shop_sub_category_id"))
            if shop in shop_stock.SHOPS:
                out.append((SHOP_KEY_PREFIX + product_id, product_id, define))
    return out


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
