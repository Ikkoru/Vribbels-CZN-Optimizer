"""Checklist tab: what resets, and how often.

Four headed columns, one per reset period, each listing the things that
come back on it, with what is left to do beside it. Green is nothing
left, red is something, and a dash is a question the snapshot cannot
answer -- which is a THIRD state and not a zero.

**The Events block is its own subject**, and `docs/events.md` is the
write-up: what kinds of event there are, how to tell them apart, and
what each kind's row is allowed to claim.

Each row reads its own field, and they have almost nothing in common:
a claim stamp, a currency balance, a daily counter, a login streak, a
set of puzzle pieces. `_readings` is where every one of them is, keyed
by the row's own key rather than by its words -- two rows share the
words `Delegation Module` and differ only in the deadline they count
to. `docs/wire_hunt.md` records what each field means and which
readings are exact.

**A reading that can only be a FLOOR says so, and does not go green
on its own.** The game issues a mission row when it issues the
mission, so counting the rows in hand understates an event still
handing them out -- and a checklist saying done when it is not is
worse than one saying nothing. Such a row prints `UNKNOWN_MORE` after
its total and turns green only where the game itself says the event
is over.

**An event's own family is what knows its total.** A finished
instalment's mission rows are all the rows it ever had, so they are
counted and written down; a live instalment of a family whose past
agrees with itself reads against that instead of against a floor. It
still goes green only on the game's own word. See
`_recall_event_totals`.

**A number worked out rather than read carries `EXPECTED_VALUE`.**
Two rows do: a weekly allowance the game has not topped up yet is the
week's own rule applied to last week's leftover, not a reading, and
the mark comes off as soon as a capture sees the real figure.

**A shop's rows are read off the wire, not written here.**
`shop_res_data` carries every product's item, cap, period, price and
display order, so a column's shop rows are rebuilt from the snapshot
whenever the set changes -- a product the game adds appears with no
edit. `shop_stock` is what reads it.

**A shop's own heading reads what clearing it costs**, the currency on
hand over the bill for the ticked products still on its shelves. That
one sits at a stop of its own, off the heading's words rather than in
the column of readings, because it answers for the shop rather than
for a row, and it is inked a shade apart for the same reason. See
`_add_shop_totals`.

**Hovering a shop says what its currency EARNS**, and what a full
period of it costs. Both rates are per ROTATION of that shop and
differ only in how far back they look; they come off a ledger the
manager keeps, since a snapshot holds only the present and a rate is a
fact about the past. `ChecklistManager` is the write-up, `shop_rates`
and `shop_full_cost` the wording.

**Deadlines line up in a column of their own**, and there are two of
them: the rows above the Sortie shop and the Events block below it,
each measured against its own members so a long reading in one does
not push the other's across. A shop heading is in neither -- its line
hangs off its own words. See `countdown_group`.

**And the Events block asks the one question the wire cannot answer.**
A row at its own ceiling that the game has not called finished is
either finished or waiting for more, so the tab offers a `Finished?`
checkbox at the end of it and remembers the answer against the reading
it was given for: another reward claimed, or another one to claim,
retires the answer and asks again. See `_mark_finished`.

The columns are built the way the Materials tab's are: content in the
EVEN grid columns with an empty expanding one between each pair, so the
block spans the window and the gaps across it stay equal. A row is one
Text per column rather than a Label per line -- a tab switch re-runs
the geometry managers over every widget on the page, and forty labels
is forty of them.
"""

import math
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

import checklist_manager
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
from ..utils.tooltip import Tooltip
from ui.scaling import px


# Each column's heading and its rows, left to right. Read off the
# game: the wording is the game's own where it has one, and `Shop`
# marks a shop tab rather than a currency.
#
# A row is `(key, label, widest)`. The KEY is what `_readings` answers
# to and is unique across the tab -- `Delegation Module` appears twice
# and `Nono's Shop` in two columns, so the words cannot serve, and a
# shop's heading carries its PERIOD for the same reason. `widest` is
# the longest reading that row can show, which is what the column
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

# What a shop heading's own reading answers to. A shop is on the tab
# under as many PERIODS as it sells caps for -- Nono's is both a weekly
# and a monthly shelf -- so the period is part of the heading's key,
# and without it one shop's two rows would read each other's totals.
SHOP_TOTAL_PREFIX = "shoptotal:"

# The widest a shop heading's total can render, which is what the
# column reserves room for. Six figures a side: the largest bill any
# shop can present is five, and the reserve is static so that a total
# gaining a digit cannot outrun a block that is only rebuilt when the
# row SET changes.
SHOP_TOTAL_WIDEST = "999999/999999"

# What a shop heading's hover is tagged with, plus its key. Covers the
# shop's NAME and its total and nothing else on the line -- the Sortie
# shop's heading also carries a countdown, which the rates say nothing
# about.
SHOP_TIP_PREFIX = "shoptip:"

# How long each shop period runs and what to call one, as
# `(the word, days)`. The LENGTH is read off the wire where the wire
# states it -- `month_start`/`month_end` bound a month, and the Sortie
# season is a schedule of its own -- so these are the fallback for a
# snapshot carrying neither, and the word is what the tip says.
SHOP_PERIODS = {"weekly": ("week", 7), "monthly": ("month", 30),
                "account": ("season", 21)}

# **Both lines answer in the shop's own period** -- what a rotation is
# worth -- and differ only in how far back the daily rate behind them
# was measured. That is the whole point of showing two: the same
# question asked of recent play and of the long run, so a gap between
# them says something happened rather than being arithmetic.
#
# How many of the shop's own periods the SHORT one rolls over. One is
# a single observation rather than an average -- a week's income swings
# with what content ran that week -- so this trades that noise for lag.
SHOP_RATE_ROLL = 4

# And how far back the LONG one reaches, in days. Capped at the
# ledger's own span: an account younger than that is measured over its
# whole life, which is what makes this an answer on the first capture
# rather than in a year's time.
SHOP_RATE_YEAR = 365

# The least a ledger may span before a rate off it is shown at all.
# A WEEK, which is the shortest cycle the game runs on: under that,
# what the window holds is which content happened to fall in it.
#
# The currencies the wire keeps a lifetime total for clear this on the
# first capture, their ledger reaching back to the account's creation.
# The two that are ordinary items have to earn it a day at a time.
SHOP_RATE_FLOOR = 7

# What each line says. `%s` is the shop's period -- `week`, `month`,
# `season` -- so a monthly shop does not claim a weekly rate. Both
# lines answer in that same unit and name only which window they came
# from, not how many days that was.
#
# **A `recent` line can be measured over fewer days than it asked
# for**, where the ledger does not reach back that far, and says
# nothing about it. What stops that reading as a four-week figure on a
# ledger three days old is `SHOP_RATE_FLOOR`, plus the rule that two
# windows landing on the same days print once.
RATE_RECENT_LABEL = "Average per %s, recent:"
RATE_LONG_LABEL = "Average per %s, long run:"

# And what a full period of the shop costs, which is the figure those
# two are worth comparing against.
#
# **The whole cap, not what is left of it.** The heading's own reading
# already says what finishing THIS period costs; this one says what the
# period costs from empty, so it does not move as the shelves are
# bought out and can be read against a rate.
FULL_COST_LABEL = "Full cost of selected items:"

# What a rate reads as with a value and a name beside it.
RATE_VALUE = "%s %s"

# What a compact `tk.Checkbutton` costs beyond the width of its own
# words: its indicator, and the gap Tk puts between the two. The column
# reserves it so a checkbox row's words stop where a plain row's do.
#
# **Measured from the widget's leftmost pixel to its TEXT's leftmost
# pixel**, off the screen, which is the offset this is about: where a
# checkbox row's words START. The widget's requested WIDTH is two more
# than that -- trailing padding past the end of the text -- and taking
# that instead pushes the reading column two right of where the words
# need it.
#
# The same at any font size: the indicator and its gap are the
# widget's own, so this does not follow `ROW_FONT`.
CHECKBOX_OVERHEAD = 21

# What a value says about the row it sits on. GREEN is nothing left to
# do, RED is something left, and a row whose source a snapshot cannot
# answer for is neither.
DONE, TODO, UNKNOWN = "done", "todo", None

# The same two answers, drawn a little darker and a little stronger,
# for a SHOP HEADING's total. It answers for every product beneath it
# rather than for a row of its own, and the shade is what keeps the
# two apart without a second colour to learn.
#
# Mapped at drawing time rather than carried in the reading: a total
# says DONE or TODO like anything else on the tab, and only the ink
# differs.
HEAD_STATE_TAGS = {DONE: "headdone", TODO: "headtodo"}

# A reading that CANNOT SAY whether its work is finished, because its
# denominator is only what the game has handed out so far. It draws red
# like any other unfinished row -- until it has stood at its own
# ceiling long enough to be evidence, and then orange.
#
# **The row still is not green.** Orange says "this looks finished and
# nothing here can prove it", which is a third answer and the honest
# one for an event whose true total the wire never states.
FLOOR = "floor"
STALE_FLOOR = "floor_stale"

# A FORCED DAILY event's day is finished -- today's doubled runs taken.
# Orange rather than green, and not because anything is unproven: the
# rewards refresh tomorrow and today's are gone, so claiming them all
# does not finish the event and a green row would read as one less
# thing to think about for the rest of its run.
# See `EVENT_CATEGORIES`.
CYCLE_DONE = "cycle_done"

# What an EVENT row must read on every segment before it sorts to
# the bottom of the Events block. See `_event_settled`.
EVENT_SETTLED_STATES = frozenset({DONE, CYCLE_DONE})

# How long a floor must stand at its ceiling before it goes orange, and
# what it takes to reset that. Two days: an event that hands out more
# does so daily, so a tally unmoved across two of them has either
# finished or stopped.
FLOOR_SETTLES_AFTER = 48 * 3600

# A countdown's own colours, by how long is left. Nothing to do with
# whether the row's work is done -- a finished content still runs out.
# (hours under which it applies, the state). Read top down.
SOON, WARN, LATER = "soon", "warn", "later"
COUNTDOWN_STATES = ((24, SOON), (72, WARN), (None, LATER))

# What a countdown segment says before its time.
ENDS_IN = "Ends in "

# Two spaces between a row's value and its countdown, so the two read
# as separate answers rather than one sentence.
SEGMENT_GAP = "  "

# The widest a countdown can render, for the columns that reserve room
# for one. BUILT from the words it is made of rather than typed out, so
# a change to either cannot leave the reserve behind.
WIDEST_COUNTDOWN = ENDS_IN + "99 days"


def with_countdown(widest):
    """A reserve wide enough for `widest` and a countdown beside it."""
    return widest + SEGMENT_GAP + WIDEST_COUNTDOWN

# What an UNTRACKED shop product's reading is drawn in: the dim colour
# explanation text uses. Red and green say what is left to do, and a
# product the user is not tracking has nothing to say either way.
MUTED = "muted"

# A shop heading's own colour, so the shops can be told apart at a
# glance down a column of otherwise identical rows. Matched on the
# words, longest first, and the FIRST match wins -- `Traveler` is also
# a `Shop`, and it takes its own colour.
#
# (what the heading contains, the palette key). These colour the
# LABEL; a row's reading keeps the red/green that says what is left.
SHOP_LABEL_COLOURS = (
    ("Traveler", "yellow"),
    ("Nono's Shop", "blue_light"),
    ("Shop", "purple"),
)

# How long each column's own period runs, and what its heading counts
# down to. The Monthly one is None because a month is not a fixed
# length -- the wire's `month_start` and `month_end` bound it, and the
# quarters are quarters of THAT.
PERIOD_LENGTHS = {"Daily": 24 * 3600, "Weekly": 7 * 24 * 3600,
                  "Monthly": None}

# A heading countdown's colour, by how much of its period is left. The
# period splits into four equal parts: the first quarter spent is
# green, the last is red.
#
# (share of the period still to run, the state). Read top down.
HEADING_BANDS = ((0.75, "period_full"), (0.5, "period_most"),
                 (0.25, "period_some"), (0.0, "period_last"))

# What each band is drawn in, as a palette key. Most of the period
# still to run is green; the last quarter is red.
PERIOD_COLOURS = {"period_full": "green", "period_most": "yellow",
                  "period_some": "orange", "period_last": "red"}

# What a heading countdown says: `18h left`, `5d left`.
HEADING_LEFT = " left"

# The countdown's own face and where it sits against the heading. The
# subtext face, so it reads as a note on the heading rather than as
# part of it.
#
# **The drop seats it on the heading's own baseline**, and it is a
# BOTTOM pad under `anchor=S`, so it lifts: a 14pt box is taller than
# the subtext's and the difference is what has to come back. At 9pt
# that was three; a point larger it is none, and the lever is at its
# floor -- a pad cannot go negative, so a subtext that ever sat too
# LOW would need the heading padded instead.
HEADING_COUNTDOWN_FONT = ("Segoe UI", 10)
HEADING_COUNTDOWN_GAP = 6   # spacing: heading ↔ element -- heading, label ↔
HEADING_COUNTDOWN_DROP = 0  # spacing: heading ↔ element -- heading, label ↕


# Which `event_schedules` group dates each row, and so what its
# countdown counts down to. **The wire carries the real window for
# every one of them**, so no row's length is written down here.
COUNTDOWNS = {
    "basin": "HYPER_SPACE_SEASON",
    "matrix": "ZERO_REWARD_LIST",
    "offensive": "REMNANTS_BOSS_PENALTY",
    "supply_season": "SEASON_PASS",
    "galactic_disaster": "DISASTER_SEASON",
    "shophead:shop_assault/none/account": "ASSAULT_SCHEDULE",
}

# Shops whose products are kept PER SEASON, and where the live season
# comes from. Every season the account has played keeps its products in
# the table, so one screen offering one Tear of God reads as three.
SEASONAL_SHOP_CATEGORY = "shop_disaster"

# Shop products the tab does not list, by the id the wire gives them.
# The shop rows are built from `shop_res_data` whole, so this is the
# only way to leave one out -- untracking a product mutes it and keeps
# the row, which is a different thing.
#
# Each entry says what it is, since the id alone says nothing.
HIDDEN_PRODUCTS = {
    "card_factor_4",        # Prism Module - Nominate, item 5210000
}


def shop_head_key(shop, period):
    """The key of one shop's own heading row. See `SHOP_TOTAL_PREFIX`."""
    return SHOP_HEAD_PREFIX + "/".join(shop + (period,))


def shop_products(shop, period, raw):
    """[(product id, definition)] the tab lists for one shop and period.

    `shop_stock.products` minus the ones this tab does not show: the
    hidden ones, and every season but the live one where the shop
    keeps its shelves per season.
    """
    prefix = (_live_season(raw) if shop[0] == SEASONAL_SHOP_CATEGORY
              else None)
    if shop[0] == SEASONAL_SHOP_CATEGORY and not prefix:
        # Without a live season every season's products would show.
        return ()
    return tuple((product_id, define)
                 for product_id, define
                 in shop_stock.products(shop, period, raw, prefix)
                 if product_id not in HIDDEN_PRODUCTS)


def shop_currency(shop, period, raw):
    """The res_id one shop sells for, or None where it has no one.

    **A shop sells for ONE currency** -- the same `price_link_item_id`
    on every product of a screen, checked across all seven the tab
    lists. Two ways to get None, and both are readings rather than
    failures: the seasonal supplies are free and carry no price item,
    and a shop reading as more than one has nothing a single holding
    could be compared against.
    """
    money = {define.get("price_link_item_id")
             for _pid, define in shop_products(shop, period, raw)}
    one = money.pop() if len(money) == 1 else None
    return one if _is_count(one) else None


def shop_period(period, raw, now):
    """`(what to call one of this shop's periods, how many days it is)`.

    Off the wire where the wire states it: a month is however long
    `month_start` to `month_end` runs, and an `account` shelf refreshes
    with the Sortie SEASON rather than on any calendar. The written
    lengths stand in where a snapshot carries neither.
    """
    word, days = SHOP_PERIODS.get(period, (period, 0))
    if period == "monthly":
        start, end = (raw or {}).get("month_start"), (raw or {}).get("month_end")
        if _is_count(start) and _is_count(end) and end > start:
            days = int(round((end - start) / 86400.0))
    elif period == "account":
        _name, window = schedules.current(
            shop_stock.ACCOUNT_SEASON_GROUP, raw, now)
        if isinstance(window, dict):
            span = (window.get("end_time") or 0) - (window.get("start_time") or 0)
            if span > 0:
                days = int(round(span / 86400.0))
    return word, max(1, days)


def shop_rows(shop, period, raw):
    """The sub-rows for one shop's products in one period.

    `(key, label, widest)` per product, straight off the wire: the
    shop's own `sort` gives the order, `limit_count` the reserve, and
    the item the product gives its name. Nothing is hand-written any
    more -- a product the game adds appears the next time the login
    burst is captured.
    """
    out = []
    for product_id, define in shop_products(shop, period, raw):
        limit = define.get("limit_count")
        out.append((SHOP_KEY_PREFIX + product_id,
                    product_label(define),
                    "%d/%d" % (limit, limit)))
    return tuple(out)


def _event_settled(raw, name, group, window, now):
    """Whether an event's row has nothing outstanding on it.

    Every segment its reader produces has to say so, and only the two
    states that mean "nothing to do" count: finished, and a Forced
    Daily whose day is taken.

    **A settled FLOOR does not.** Orange there means the row looks
    finished and nothing can prove it, so it belongs with the work
    rather than with the events that are over. An event nobody has
    mapped does not either: it shows a deadline and no reading, which
    is a question rather than an answer.
    """
    # The user's own answer settles a row as surely as the game's:
    # see `EVENT_FINISHED_FIELD`. Checked first, because the reader
    # below knows nothing about it.
    if str(name) in ((raw or {}).get(EVENT_FINISHED_FIELD) or ()):
        return True
    reader = EVENT_READERS.get(group)
    if reader is None:
        return False
    segments = list(reader(raw, name, window, now))
    return bool(segments) and all(state in EVENT_SETTLED_STATES
                                  for _words, state in segments)


def event_rows(raw, now=None):
    """`(key, id, widest)` for every event running now.

    Read straight off `event_schedules`: an event the game adds turns
    up with no edit, and one that ends drops out.

    **Anything still owed comes first**, and within each half the order
    is by deadline, which is what a checklist is about. Same shape as
    an untracked shop product sinking to the bottom of its shop: the
    rows that need a decision are the ones at the top.
    """
    now = time.time() if now is None else now
    found = []
    for group in EVENT_GROUPS:
        # EVERY instance, not one per group: three events overlapped
        # under `EVENT_SCHEDULE` in one capture.
        for name, window in schedules.all_live(group, raw, now):
            found.append((_event_settled(raw, name, group, window, now),
                          window["end_time"], name))
    return tuple((EVENT_KEY_PREFIX + name, event_label(name),
                  with_countdown(EVENT_WIDEST))
                 for _settled, _end, name in sorted(found))


def _event_key(name):
    """An event or mission id with the differences between the two
    normalised away. See `EVENT_NOISE_WORDS`."""
    parts = [part for part in str(name).split("_")
             if part not in EVENT_NOISE_WORDS]
    return "_".join(part.lstrip("0") or "0" if part.isdigit() else part
                    for part in parts)


def _under(mission, event):
    """Whether a normalised mission id belongs to a normalised event.

    On a SEGMENT boundary, so `event_daily_1` does not swallow
    `event_daily_12`'s missions -- the ids differ by a digit and
    a plain prefix test cannot tell them apart.
    """
    return mission == event or mission.startswith(event + "_")


def _stem(key):
    """A normalised event key without its own index.

    `event_devil_1` -> `event_devil`. Unchanged where the key does not
    end in a number, which is what stops a stem being taken off an id
    that never had one.
    """
    parts = key.split("_")
    return "_".join(parts[:-1]) if parts and parts[-1].isdigit() else key


def _event_rows(raw, name):
    """The mission ids belonging to one event, as a sorted list.

    **An event's index does not always appear in its missions' ids.**
    Most families repeat it -- `event_summer_01` owns
    `event_summer_mission_01_*`, `event_bartender_01` owns
    `event_bartender_1_*` -- so a prefix match on the normalised key
    finds them. `event_devil_*` does not: its schedule is
    `event_schedule_devil_001` and its missions are
    `event_devil_<day>_<task>`, where that `01` is DAY one. Matching on
    the key alone took day one and silently dropped days two to seven,
    which is how a 21-reward event read `3/3` for a week.

    So where the key matches something, the STEM is tried as well --
    the key without its own index -- and the extra rows are taken
    unless some other event's key claims them. That exclusion is what
    keeps `event_schedule_policy_005` off `event_policy_4_*`: a past
    instalment shares the stem and is still in `event_schedules`.

    **The key must match first.** A stem on its own is far too greedy:
    `event_2` stems to `event` and would take every event mission the
    account holds, and `event_schedule_chaos_mission_5` stems to
    `event_chaos` and would take the Sortie's. Requiring one row under
    the full key rules both out, because neither has any.
    """
    missions = (raw or {}).get(PASS_MISSION_FIELD)
    missions = missions if isinstance(missions, dict) else {}
    want = _event_key(name)
    keyed = {res_id for res_id in missions
             if _under(_event_key(res_id), want)}
    if not keyed:
        return sorted(keyed)
    root = _stem(want)
    if root == want:
        return sorted(keyed)
    others = {_event_key(other)
              for group in ((raw or {}).get("event_schedules") or {}).values()
              if isinstance(group, dict) for other in group}
    others.discard(want)
    for res_id in missions:
        if res_id in keyed:
            continue
        key = _event_key(res_id)
        if not _under(key, root):
            continue
        if any(_under(key, other) for other in others):
            continue
        keyed.add(res_id)
    return sorted(keyed)


def event_label(name):
    """What an event row is called: its id without the common prefix.

    Every id starts `event_`, so the word says nothing and costs a
    column's width. An id that does not is left alone.
    """
    return name[len(EVENT_ID_PREFIX):] if name.startswith(
        EVENT_ID_PREFIX) else name


def _event_attendance(raw, name, window, now):
    """[(words, state)] for a login-streak event's rewards taken.

    **A reward is waiting when `current_days` is ahead of
    `received_days`** -- days shown up for against days claimed. Not
    `last_dayid`, which looks like a claim stamp and is not: the
    record read `2/1/1348` and then `2/2/1348` across a claim, so the
    stamp moves on the LOGIN.

    **And never by more than one.** A claim advances the streak by
    exactly one -- `received_days_before` 6 to `received_days_after` 7
    -- and the record has never been caught more than one apart. So
    the ceiling shown is one past what is claimed, whatever
    `current_days` says: on the launch login event it says fifty-six
    against seven claimed, its rewards being finite and its day count
    not, and a row reading `7/56` would be a tally of nothing.

    Three answers. A day to claim is red; everything claimed is ORANGE
    while the streak may still have days in it -- the same answer a
    Forced Daily's finished day gets -- and green only where the game
    has said the streak is over. See `ATTENDANCE_OVER`.

    **The launch event reads red for a day that is not there.** Its
    `received_days` has sat at seven across every capture while
    `current_days` climbed, so it looks like a streak one day behind
    for ever, and no field in the record tells the two apart -- a day
    left unclaimed included, which the record already holds and which
    writes the live streak the same way. `docs/events.md` has what has
    been ruled out.
    """
    rows = (raw or {}).get(ATTENDANCE_FIELD)
    if not isinstance(rows, list) or not isinstance(window, dict):
        return []
    began = window.get("start_time")
    mine = [row for row in rows
            if isinstance(row, dict) and _is_count(row.get("start_time"))
            and _is_count(began) and row["start_time"] >= began]
    if not mine:
        return []
    row = min(mine, key=lambda r: r["start_time"])
    taken, shown = row.get(ATTENDANCE_TAKEN), row.get(ATTENDANCE_SHOWN)
    if not _is_count(taken):
        return []
    if row.get(ATTENDANCE_OVER):
        return [("%d/%d" % (taken, taken), DONE)]
    # **A total written down here beats the streak's own reading**,
    # while the record has not disproved it. See `WRITTEN_TOTALS`: the
    # launch event's seven are all it ever had, and counting its days
    # instead reports a reward waiting that cannot be claimed.
    written = written_total(name, taken)
    if written is not None:
        return [("%d/%d" % (taken, written),
                 DONE if taken >= written else TODO)]
    waiting = _is_count(shown) and shown > taken
    return [("%d/%d%s" % (taken, taken + (1 if waiting else 0),
                          UNKNOWN_MORE),
             TODO if waiting else CYCLE_DONE)]


def _overclock_cap(rows, name):
    """How many doubled runs one Overclock event's day holds.

    **The cap is not stated.** What the wire does state is the SET of
    caps the game uses: `overclock_entities` keeps every Overclock
    event the account has ever played, and a row's `count` is that
    event's own daily tally. Two shapes across thirteen events, six a
    day and two, and the current one is a two.

    So the cap is the smallest shape that still fits today's count. A
    six-shape event's third run then reads `3/6`, where a written-down
    two would have clamped it to `2/2` and called the day finished with
    three runs still on offer.

    A shape counts only if it recurs. A row is left where its event
    ended mid-day, so a final `count` can be a part-day that was never
    the cap -- and a part-day is one account's accident where a shape
    is the game's, showing up across events. `OVERCLOCK_USES` is the
    floor for an account with no history at all.
    """
    seen = {}
    for key, row in rows.items():
        if key == name or not isinstance(row, dict):
            continue
        if _is_count(row.get("count")) and row["count"] > 0:
            seen[row["count"]] = seen.get(row["count"], 0) + 1
    return sorted(shape for shape, times in seen.items()
                  if times >= OVERCLOCK_SHAPE_SIGHTINGS)


def _event_overclock(raw, name, window, now):
    """[(words, state)] for an Overclock event's doubled runs TAKEN.

    **Taken, not left**, because every other row on the tab counts what
    is done out of what there is -- and a row that counted the other
    way read `2/2` on a day nothing had been used, which is exactly
    what a finished row looks like everywhere else.

    FORCED DAILY, so a finished day is orange rather than green: the
    two come back tomorrow and today's are gone. It is also GENERIC,
    which is why a cap the wire never states can be answered from the
    shapes the game has used before. See `EVENT_CATEGORIES`.

    **On the LAST day it goes green.** Orange says the row will be
    back tomorrow, and on the final day there is no tomorrow -- taking
    the day's runs finishes the event outright, which is what green is
    for. The event's own window says which day that is.
    """
    rows = (raw or {}).get(OVERCLOCK_FIELD)
    rows = rows if isinstance(rows, dict) else {}
    row = rows.get(name)
    used = 0
    if isinstance(row, dict) and _is_count(row.get("count")):
        touched = row.get("reset_time")
        # Daily, and reset lazily: a count stamped before today's
        # reset is yesterday's and today has taken none.
        if not (_is_count(touched)
                and touched < weekly_reset.last_daily_reset(now)):
            used = max(row["count"], 0)
    cap = max(OVERCLOCK_USES, used)
    for shape in _overclock_cap(rows, name):
        if shape >= used:
            cap = shape
            break
    if used < cap:
        return [("%d/%d" % (used, cap), TODO)]
    return [("%d/%d" % (used, cap),
             DONE if _last_cycle(window, now) else CYCLE_DONE)]


def _last_cycle(window, now):
    """Whether the event ends before its rewards would come back.

    A Forced Daily event's rewards refresh at the daily reset, so the
    day that reaches the event's end is its last -- nothing comes back
    after it and a full row is genuinely finished.

    Unknown where the window is missing, and the answer is then NO: a
    row that goes green a day early costs the user the last day's
    rewards, where one that stays orange costs nothing.
    """
    ends = (window or {}).get("end_time")
    if not _is_count(ends):
        return False
    return ends <= weekly_reset.last_daily_reset(now) + weekly_reset.DAY


def _trial_banners(raw, window):
    """The combatant ids whose banner runs on exactly this window.

    **A trial event and a banner are the same period.** Every one of
    the eight in a capture matched a `gacha_pickup_combatant_*` window
    to the second, which is what pairs the two without either naming
    the other -- and where two banners share a window they share the
    trial event, which is then twice the size.
    """
    if not isinstance(window, dict):
        return []
    span = (window.get("start_time"), window.get("end_time"))
    out = []
    for name, banner in schedules.groups(raw).get(BANNER_GROUP, {}).items():
        if not isinstance(banner, dict) or not name.startswith(BANNER_PREFIX):
            continue
        if (banner.get("start_time"), banner.get("end_time")) == span:
            out.append(name[len(BANNER_PREFIX):].split("_")[0])
    return out


def _trial_count(raw, window):
    """How many trials a Combatant Trial event offers."""
    return TRIAL_PER_BANNER * max(1, len(_trial_banners(raw, window)))


def _trial_claims(raw, name, window, now):
    """How many of a live trial event's rewards have been taken.

    **Derived, where nothing states it.** Which three slots an event
    offers is in the client's own data and on no message but the claim
    -- so the count comes from the stamps instead: a slot claimed
    inside this event's window was claimed for this event.

    Two events overlap for the last week of each, and a claim then
    falls inside both windows. What separates them is that each event's
    window names a banner, and a slot named for the OTHER event's
    banner combatant is that event's; the rest is capped at this
    event's own size so an overlap cannot read as more than a full one.
    """
    mine = {TRIAL_SLOT_PREFIX + c for c in _trial_banners(raw, window)}
    others = set()
    for other, window_of in schedules.all_live(TRIAL_GROUP, raw, now):
        if other != name:
            others |= {TRIAL_SLOT_PREFIX + c
                       for c in _trial_banners(raw, window_of)}
    began, ends = window.get("start_time"), window.get("end_time")
    claimed = 0
    for row in (raw or {}).get(TRIAL_FIELD) or []:
        if not isinstance(row, dict):
            continue
        slot = row.get("event_combatant_trial_slot_id")
        when = row.get("complete_time")
        if not _is_count(when) or not (began <= when <= ends):
            continue
        if slot in others - mine:
            continue
        claimed += 1
    return claimed


def _event_trials(raw, name, window, now):
    """[(words, state)] for a Combatant Trial event's rewards claimed.

    Claimed THIS CYCLE. A slot's stamp is rewritten every time its
    trial comes round again, so a claim counts only where it falls
    inside this event's own window -- and an older window cannot be
    reconstructed at all, the stamps that were in it having moved on.

    **The slot list is preferred where a capture has seen a claim**
    (`TRIAL_SLOTS_FIELD`), since it names the three exactly. Without
    one the count is derived -- see `_trial_claims` -- which needs no
    history and is right except during the week two events overlap.
    """
    if not isinstance(window, dict) or not _is_count(window.get("start_time")):
        return []
    most = _trial_count(raw, window)
    pairs = (raw or {}).get(TRIAL_SLOTS_FIELD)
    slots = pairs.get(name) if isinstance(pairs, dict) else None
    if slots:
        began, ends = window["start_time"], window.get("end_time")
        stamps = {row.get("event_combatant_trial_slot_id"):
                  row.get("complete_time")
                  for row in ((raw or {}).get(TRIAL_FIELD) or [])
                  if isinstance(row, dict)}
        claimed = sum(1 for slot in slots
                      if _is_count(stamps.get(slot))
                      and began <= stamps[slot] <= ends)
        most = max(most, len(slots))
    else:
        claimed = min(_trial_claims(raw, name, window, now), most)
    return [("%d/%d" % (claimed, most), _done(claimed >= most))]


def _event_finished(raw, name):
    """Whether the game itself says this event is finished.

    **`event_mission_reward_entities` is the only place it does.** One
    row per event the account has a completion record for, and
    `event_achieve_state` is 1 once the event's own final reward --
    the one that unlocks after every other -- has been taken.
    `event_bartender_1`'s is the worked example.

    Everything else about an event is a count of what has been handed
    out, which is a floor and can never prove completion. This can,
    which is what takes `UNKNOWN_MORE` off the row and lets it
    go green.

    The record's id is the event's own rather than the schedule's, so
    it goes through `_event_key` like every other pairing here.
    """
    rows = (raw or {}).get(EVENT_DONE_FIELD)
    rows = rows if isinstance(rows, list) else []
    want = _event_key(name)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _event_key(row.get("res_id")) == want:
            return row.get(EVENT_DONE_FLAG) == EVENT_DONE_VALUE
    return False


def _event_missions(raw, name, _window, _now):
    """[(words, state)] for an event scored by its own missions."""
    return _event_progress(raw, name)


# What a schedule group IS. **A group can be several of these at
# once**, so the value is a SET -- an Overclock event is both Generic
# and Forced Daily, and the two say different things about it.
# `docs/events.md` holds the table: how to classify one, and what each
# costs.
#
#   TALLIED       its total is knowable, so its row can go green.
#   GENERIC       a TALLIED event that comes back later largely
#                 unchanged. What cannot be derived about one may be
#                 written down, because next time it will be the same
#                 number -- the only kind of hardcoding that does not
#                 go stale. Watch for the game changing it anyway.
#   FORCED_DAILY  its rewards refresh each day of its run and are gone
#                 if not taken that day. Claiming them all does not
#                 finish it, so a full row is ORANGE rather than green.
#   OPEN_ENDED    only a floor is knowable. Red, and orange once the
#                 floor has stopped moving -- see `FLOOR`.
#
# A group with no entry has no reader either and shows its deadline
# alone, which is the honest reading for an event nobody has mapped.
TALLIED = "tallied"
GENERIC = "generic"
FORCED_DAILY = "forced-daily"
OPEN_ENDED = "open-ended"

EVENT_CATEGORIES = {
    # Generic: the same event returns every few weeks in one of two
    # shapes, and the ended rows of both are still on the wire -- which
    # is what lets `_overclock_cap` read a cap nothing states. Forced
    # Daily: the day's runs come back tomorrow and yesterday's are
    # gone, so a finished day is not a finished event.
    "EVENT_OVERCLOCK": frozenset({GENERIC, FORCED_DAILY}),
    "EVENT_DAILY_CHECK": frozenset({TALLIED}),
    "EVENT_COMBATANT_TRIAL": frozenset({TALLIED, GENERIC}),
    "EVENT_SCHEDULE": frozenset({OPEN_ENDED}),
    "EVENT_NODELIST_PAGE": frozenset({OPEN_ENDED}),
}


# Kinds that imply another: {kind: what being it also makes you}.
# GENERIC is a TALLIED event that comes back, so anything generic is
# tallied whether or not the table says so twice.
EVENT_IMPLIES = {GENERIC: TALLIED}


# **A total nothing states, written down anyway** -- and written down
# so that the wire can take it back. An event here reads as TALLIED
# against the number below, and reverts to whatever its group really
# is the moment a reward past that number turns up. See
# `written_total`.
#
# `event_daily_1`, the launch login event, is the one that needs it:
# its seven rewards are a new account's first week, nothing has moved
# since, and no field separates it from a streak genuinely a day
# behind. Its `current_days` climbs for ever, so what the row would
# otherwise show is a reward waiting that nobody can claim.
#
# Keyed by the NORMALISED event key, so an instalment's spelling does
# not matter. The value is REWARDS, not days.
WRITTEN_DOWN = "written-down"
WRITTEN_TOTALS = {"event_daily_1": 7}


def written_total(name, taken):
    """The total written down for an event, while it still holds.

    `taken` is what the account has actually had out of it. **A reward
    past the write-down disproves it**, and the answer is then None:
    the row goes back to reading the way its group reads, floor and
    all. A number typed into the program is only a claim about what
    the wire has not said yet.
    """
    total = WRITTEN_TOTALS.get(_event_key(name))
    if total is None or not _is_count(taken) or taken > total:
        return None
    return total


def event_is(group, category):
    """Whether a schedule group is of a kind. See `EVENT_CATEGORIES`."""
    kinds = set(EVENT_CATEGORIES.get(group, ()))
    for kind in tuple(kinds):
        implied = EVENT_IMPLIES.get(kind)
        if implied is not None:
            kinds.add(implied)
    return category in kinds


# Which reader answers for each schedule group. A group with no entry
# shows its deadline and no tally.
EVENT_READERS = {
    "EVENT_SCHEDULE": _event_missions,
    "EVENT_NODELIST_PAGE": _event_missions,
    "EVENT_DAILY_CHECK": _event_attendance,
    "EVENT_OVERCLOCK": _event_overclock,
    "EVENT_COMBATANT_TRIAL": _event_trials,
}


def _event_progress(raw, name):
    """[(words, state)] for one event's rewards, or [] where unmapped.

    `complete_time` on a mission means its reward was TAKEN. The
    denominator is the rows the account HOLDS, which is a floor: the
    game issues a mission row when it issues the mission, so an event
    dripping three tasks a day for a week reads three of three on its
    first afternoon.

    **So this normally cannot read green**, and says so: the total
    carries `UNKNOWN_MORE` after it, because a denominator that
    is only a floor is a different claim from one that is a total.
    Twice a bare tally called an event finished that was not -- a
    summer event with a wave unissued, and a daily one on its first
    day -- and a checklist that says done when it is not is worse than
    one that says nothing. The reading is marked `FLOOR`, and the tab
    colours it orange once it has stood still long enough to mean
    something.

    The exception is an event the game itself calls finished. See
    `_event_finished`: the suffix comes off and the row goes green,
    because the question has an answer rather than an estimate.
    """
    rows = _event_mission_rows(raw, name)
    if not rows:
        return []
    claimed = sum(1 for row in rows if row.get("complete_time"))
    if claimed >= len(rows) and _event_finished(raw, name):
        return [("%d/%d" % (claimed, len(rows)), DONE)]
    # **What the family's finished instalments held**, where two of
    # them agree -- see `ChecklistManager.event_total`. Taken only
    # where it is BIGGER than the rows in hand, so the reading can
    # only ever say more work is coming, never less, and marked
    # `EXPECTED_VALUE` because it is the past speaking for the
    # present. It does not go green on that: `_event_finished` is
    # still the only thing that ends an event.
    # A total written down for this event, while the rows in hand have
    # not gone past it. See `WRITTEN_TOTALS`.
    written = written_total(name, len(rows))
    if written is not None:
        return [("%d/%d" % (claimed, written),
                 DONE if claimed >= written else TODO)]
    # **A rectangular family states its own size**, from the ids and
    # their issue stamps and nothing else -- see `_grid_total`. Above
    # the family's history because it is THIS instalment speaking.
    grid = _grid_total(rows)
    if grid is not None:
        return [("%d/%d" % (claimed, grid), FLOOR)]
    total = ((raw or {}).get(EVENT_TOTALS_FIELD) or {}).get(name)
    if _is_count(total) and total > len(rows):
        return [("%s%d/%d" % (EXPECTED_VALUE, claimed, total), TODO)]
    # **Every page issued WHOLE makes the denominator a statement**,
    # so the floor mark comes off -- see `_page_totals`. The row is
    # still not green on it: a page nobody has been issued yet is
    # invisible here, and an event can pay outside its mission rows
    # (`event_bartender_1`'s final reward is not one). `_event_finished` is
    # what ends an event.
    whole, trickling = _page_totals(rows)
    if whole and not trickling:
        return [("%d/%d" % (claimed, whole), FLOOR)]
    return [("%d/%d%s" % (claimed, len(rows), UNKNOWN_MORE), FLOOR)]


def _grid_total(rows):
    """What a RECTANGULAR family holds, or None.

    **Some events are a grid**: the same few tasks repeating per day,
    ids `event_devil_<day>_<task>`. The game issues such a family a
    ROW AT A TIME along one axis and all of the other at once -- so a
    same-second batch that varies the DAY while holding the task says
    both how many days the event has and that the shape is a grid.
    Total is then the two axes multiplied.

    `docs/events.md` has the measurement: over the eleven families in
    the account's mission table it finds two grids and leaves nine
    ragged, with no crossing either way. The two it answers --
    `event_schedule_devil_001`'s 21 and the node list's 25 -- are the
    numbers the game's own screens state.

    **It answers on the event's first afternoon**, which is the only
    time an answer is worth anything: on `event_schedule_devil_001`'s
    opening day, with 12 of its 21 rows in hand, the batch already
    spanned all seven days.

    None where the rows do not look rectangular, or where there are
    already more of them than the shape allows -- a grid that has been
    outgrown was never one.
    """
    pairs = []
    for row in rows:
        parts = str(row.get("res_id") or "").split("_")
        if len(parts) < 3:
            return None
        pairs.append((parts[-2], parts[-1], row.get("issued_time")))
    batches = {}
    for page, index, stamp in pairs:
        batches.setdefault(stamp, []).append((page, index))
    spanning = False
    for stamp, rows_in in batches.items():
        if not stamp or len(rows_in) < 2:
            continue
        if len({p for p, _i in rows_in}) > 1 and len({i for _p, i in rows_in}) == 1:
            spanning = True
    if not spanning:
        return None
    total = len({p for p, _i, _s in pairs}) * len({i for _p, i, _s in pairs})
    return total if total >= len(pairs) else None


def _page_totals(rows):
    """(rewards a page KNOWS it holds, rewards only issued so far).

    **A mission id's middle segment is its PAGE**, and a page is one
    kind of task -- `event_bartender_1_02_*` is the guestbook ladder,
    `_01_*` one reward per day of the event. `docs/events.md` has the
    write-up.

    A page whose rows all carry ONE `issued_time` was issued in a
    single act, so its row count is what that page holds and not what
    has been handed out so far. A page whose rows trickle in is a
    floor, and stays one.

    In the account's whole mission table the two sort perfectly: every
    page issued whole is a ladder of strictly increasing thresholds
    (three of them), and not one of the twenty-four pages that trickle
    is. **What this cannot see is a page that has not been issued at
    all** -- an event that opens a fourth page in its second week is
    an event whose pages all read whole in its first.
    """
    pages = {}
    for row in rows:
        res_id = str(row.get("res_id") or "")
        parts = res_id.split("_")
        page = "_".join(parts[:-1]) if len(parts) > 1 else res_id
        pages.setdefault(page, []).append(row.get("issued_time"))
    whole = trickling = 0
    for stamps in pages.values():
        seen = set(stamps)
        if len(seen) == 1 and all(seen):
            whole += len(stamps)
        else:
            trickling += len(stamps)
    return whole, trickling


def _event_mission_rows(raw, name):
    """One event's mission rows, live or long over.

    The same route `_event_progress` scores an event by, so what a
    finished instalment is recorded as holding and what a live one is
    measured against are counted the same way.
    """
    missions = (raw or {}).get(PASS_MISSION_FIELD)
    if not isinstance(missions, dict):
        return []
    override = EVENT_MISSIONS.get(name)
    if override:
        return [row for res_id, row in missions.items()
                if str(res_id).startswith(override) and isinstance(row, dict)]
    return [missions[res_id] for res_id in _event_rows(raw, name)
            if isinstance(missions.get(res_id), dict)]


# Items whose name is longer than a Checklist column wants to be, and
# what this tab calls them instead. **The full name is on the row's own
# tooltip**, so the words are still there to read -- see `_checkbox`.
#
# Keyed by res_id rather than by the words, so the pair is tied to the
# product and survives a rename in `item_names`. The shortening is this
# tab's alone: everywhere else the item keeps its name.
SHORT_NAMES = {
    3210002: "Multidimensional...",      # Multidimensional Alignment Material
}


def product_label(define):
    """What to call a product: the item it gives, and how many.

    `x1` is left off, being the common case and no information. An item
    no table names falls back to its id, which is the same marking the
    Capture Log uses -- a number on screen is an invitation to identify
    it, where a blank is a bug nobody can see.

    A name in `SHORT_NAMES` is cut down to fit the column.
    """
    res_id = define.get("product_link_item_id")
    return _product_words(define, SHORT_NAMES.get(res_id))


def product_tip(define):
    """A product's FULL label, or None where its row already shows it.

    What the checkbox's tooltip says, and only the shortened rows get
    one: a tip repeating the words under the pointer is noise.
    """
    if define.get("product_link_item_id") not in SHORT_NAMES:
        return None
    return _product_words(define, None)


def _product_words(define, name):
    """A product's label built on `name`, or on the item's own."""
    res_id = define.get("product_link_item_id")
    name = name or ITEM_NAMES.get(res_id) or str(res_id)
    count = define.get("product_count")
    return name if count in (1, None) else "%s x%s" % (name, count)


# Every id the build can name, built once. A shaped row's name is
# SPELLED OUT there -- reading `row[0]` off a table gives the group
# (`Combatant`, `Passion`), not a name.
ITEM_NAMES = item_names()


# What the Other column's trailing block of live events is headed, and
# where its rows come from. **The wire names an event by its ID and
# nothing else** -- `event_summer_01`, `event_schedule_policy_005` --
# so that is what the rows read. A display name would have to come
# from a localisation table the client already holds and the server
# never sends.
EVENTS_HEADING = "Events"
EVENT_GROUPS = ("EVENT_SCHEDULE", "EVENT_COMBATANT_TRIAL",
                "EVENT_NODELIST_PAGE", "EVENT_DAILY_CHECK",
                "EVENT_RHYTHM_GAME", "EVENT_ARENA", "EVENT_OVERCLOCK",
                "EVENT_TRAUMA_CODE", "EVENT_DISASTER_MARBLE",
                "EVENT_OPERATION")

# What an event row's key is built from.
EVENT_KEY_PREFIX = "event:"

# What every event id starts with, and what the ROW LABEL drops. The
# key keeps the whole id -- that is what the readers look the event up
# by -- so only the words on screen lose it.
EVENT_ID_PREFIX = "event_"

# An event's id and its missions' ids differ, but only in ways that can
# be normalised away -- so the pairing is DERIVED rather than listed.
# Two differences, and no others across every pair read off a capture:
#
#   `event_schedule_policy_005` -> `event_policy_5_*`      a spare word
#   `event_summer_01`           -> `event_summer_mission_01_*`   ditto
#   `event_schedule_love_4`     -> `event_love_04_*`     zero padding
#   `event_schedule_devil_001`  -> `event_devil_01_*`         ditto
#   `event_stock_01`            -> `event_stock_1_01_*`        ditto
#
# Dropping the spare words and the padding makes each pair identical up
# to the mission's own numbering. **This is what keeps the numbers
# following the game**: an event that returns as `..._006` finds
# `..._6_*` with no edit here.
EVENT_NOISE_WORDS = ("schedule", "mission", "season")

# What marks a number the snapshot can only put a FLOOR under: "this
# much, and an unknown amount more". An event's total reads `16/20+?`,
# where the twenty is what the account has been handed and not what
# the event holds -- a bare `16/20` would read as four left when it
# may be eight.
#
# It comes off only where `_event_finished` can say the event is over,
# which is also the only way such a row goes green.
UNKNOWN_MORE = "+?"

# What marks a number WORKED OUT from a rule rather than read off the
# wire: `~4`, `~8/9`. A different claim from the one above -- not "at
# least this" but "this, unless something the snapshot cannot see has
# happened". The weekly allowances are the only rows that use it, and
# only until a capture has seen the week's real figure.
EXPECTED_VALUE = "~"

# The field the wire stamps the week on. Not universal -- a disaster
# season's standings spell it `score_week_id` -- so the readers that
# need the other one pass it. See `_this_week`.
WEEK_STAMP = "week_id"

# Where the game states that an event is FINISHED, and what saying so
# looks like. One row per event, `res_id` naming the event and
# `event_achieve_state` flipping to 1 once its final reward is taken.
#
# The same row carries `reward_step` and `version`, which look like a
# reward track's size and how much of it is claimed -- across every
# row ever captured the state is 1 exactly when the two are equal.
# NOT READ, because a second reading fits the same numbers; the
# measurement that separates them is in `docs/events.md`.
EVENT_DONE_FIELD = "event_mission_reward_entities"
EVENT_DONE_FLAG = "event_achieve_state"
EVENT_DONE_VALUE = 1

# Events the rule cannot reach, as {event id: mission id prefix}. Empty
# because nothing has needed one; an event whose missions are named
# unlike its schedule goes here, and one that is simply unmapped shows
# its deadline and no tally.
EVENT_MISSIONS = {}

# Where `_recall_event_totals` leaves what a live event is expected to
# hold, as {event id: rewards}. **This program's own key, not the
# wire's** -- it is written onto the loaded snapshot in memory so the
# readers can take it off `raw` like anything else, the way a recalled
# streak is written back onto its row. Nothing saves it.
EVENT_TOTALS_FIELD = "_checklist_event_totals"

# **Progress is read per GROUP, not per event.** Each kind of event
# keeps its state somewhere else entirely -- missions, a login streak,
# a daily counter -- so what an event row can say is decided by which
# group it came from, and a new event in a known group needs no edit.
# `EVENT_READERS` below maps the group to the function that reads it.

# A login-streak event: `attendance_entities` counts the days shown up
# and the days whose reward was taken. Its rows are numbered nothing
# like the schedule's, so the row is the FIRST one started after the
# event was -- the streak begins on the first login into it.
#
# **A streak's LENGTH is per event and the wire never states it.** One
# account's twenty-four of them ran 7 days nineteen times, 14 twice,
# 21 twice and 10 once, so a written-down seven is the commonest
# answer rather than the rule. What the row does state exactly is how
# many days have been shown up for and how many claimed, and the gap
# between those is the only thing a checklist needs: whether there is
# a reward waiting right now.
ATTENDANCE_FIELD = "attendance_entities"

# Days shown up for, days claimed, and whether the streak is OVER.
#
# **The last is not in the record.** A finished streak and one claimed
# for today are written identically -- shown-up equal to claimed in
# both -- and the game says which only on the claim that ends it, in
# the reply's own `completed`. The capture keeps that on the row; see
# `ChecklistManager`'s neighbour in `capture/manager.py`.
ATTENDANCE_SHOWN = "current_days"
ATTENDANCE_TAKEN = "received_days"
ATTENDANCE_OVER = "completed"


# An Overclock event doubles the day's first Simulation rewards.
# `overclock_entities` keeps one row per event, ended ones included:
# `count` is what today took, `total_count` the event's lifetime tally,
# and `reset_time` when the day's tally was last written. A row exists
# only once a run has been taken.
#
# **The cap is not on the wire, but the shapes are** -- every ended
# row's `count` is that event's own, and `_overclock_cap` reads the
# live one's out of them. Two shapes so far, six a day and two.
OVERCLOCK_FIELD = "overclock_entities"

# What to fall back on where no shape has been seen often enough: the
# smaller of the two the game uses, so a fresh account reads a two-shape
# event right and a six-shape one grows into its own count.
OVERCLOCK_USES = 2

# How many events must share a `count` before it counts as a shape
# rather than as one account's part-day. Two: a shape recurs across
# events, an interrupted final day does not.
OVERCLOCK_SHAPE_SIGHTINGS = 2

# A Combatant Trial event offers three trials, and what matters is the
# REWARD: a slot's `complete_time` is when its reward was last claimed,
# rewritten each time the trial comes round again.
#
# **Which slots an event offers is not on the wire.** Two trial events
# run at once and their windows overlap, so a claim cannot be assigned
# to one by its date. The pairing is learned from the claim itself --
# `reward_combatant_trial` names both ids -- and the capture keeps it
# under `combatant_trial_slots`. Until a slot has been claimed once
# with a capture running, the row shows its deadline alone.
TRIAL_SLOTS_FIELD = "combatant_trial_slots"
TRIAL_FIELD = "combat_trial_entities"

# Three trials PER COMBATANT BANNER running: the event offers the
# banner combatants, so a second banner doubles the trials. Counted off
# the live pickup banners rather than stated, which is what keeps it
# right when a second one opens.
TRIAL_PER_BANNER = 3
BANNER_GROUP = "GACHA"
BANNER_PREFIX = "gacha_pickup_combatant_"
TRIAL_SLOT_PREFIX = "combatant_trial_"
TRIAL_GROUP = "EVENT_COMBATANT_TRIAL"

# The widest reading an event row can produce. RESERVED rather than
# fitted, so a figure gaining a digit does not move every row's
# words -- and written as the reading itself rather than as a
# phrase, because that is what an event row ever draws.
#
# Two digits each side: the largest event yet held 23 rewards, and
# the `+?` is on every reading whose total is only a floor. Widen
# it the day an event issues a hundred.
EVENT_WIDEST = "99/99" + UNKNOWN_MORE


# The columns, as a skeleton. Each is `(heading, rows, shops, events)`:
# `rows` are the fixed ones, `shops` names the shop screens whose
# products are folded in under a heading each, and `events` is a
# trailing heading of every live event (or None for no such block).
#
# A row is `(key, label, widest)`. The KEY is what `_readings` answers
# to and is unique across the tab -- `Delegation Module` appears twice
# and `Nono's Shop` in two columns, so the words cannot serve, and a
# shop's heading carries its PERIOD for the same reason. `widest` is
# the longest reading that row can show, which is what the column
# reserves room for; `None` is a row that shows none.
#
# **A column's rows are its own.** `Arkhianon Supply` appears under
# three headings because it resets three ways -- a daily set of
# missions, a weekly set, and the pass itself -- and they are three
# different things to check rather than one row repeated.
COLUMNS = (
    ("Daily", (
        ("coffee", "Coffee", "Go drink!"),
        ("activity", "Activity (Dailies)", "100/100 Claimed"),
        ("supply_daily", "Arkhianon Supply", "3/3"),
        ("excursions", "Excursions", "5/5"),
        ("chaos_delegation", "Chaos Delegation", "Go run!"),
    ), (), None),
    ("Weekly", (
        ("supply_weekly", "Arkhianon Supply", "10000/10000"),
        ("simulation", "Simulation Challenges", "3/3"),
        ("chaos_currency", "Chaos Currency",
         EXPECTED_VALUE + "99/4"),
        ("modules_soon", "Delegation Module", "7 expiring within 24h!"),
        ("modules_week", "Delegation Module", "7 expiring within 7 days"),
        ("sortie_currency", "Sortie Currency",
         EXPECTED_VALUE + "99/9"),
        ("chaos_progress", "Galactic Disaster - Chaos", "8000/8000"),
        ("seasonal_score", "Seasonal Accumulated Score", "300000+/300000"),
    ), (("shop_town", "none"),
        ("shop_gacha_dup", "shop_gacha_dup_legend"),
        ("shop_disaster", "shop_disaster_1")), None),
    ("Monthly", (), (("shop_town", "none"),
                     ("shop_gacha_dup", "shop_gacha_dup_legend"),
                     ("shop_hyperspace", "none"),
                     ("shop_chaos", "none"),
                     ("shop_exchange_product", "shop_card_factor")), None),
    ("Other", (
        ("basin", "Basin of Hyperspace", with_countdown("99/99")),
        ("matrix", "Zero System Chaos Matrix",
         with_countdown("100/100")),
        ("offensive", "Full-Scale Offensive", with_countdown("9/9")),
        ("supply_season", "Arkhianon Supply", with_countdown("70/70")),
        ("galactic_disaster", "Galactic Disaster (Seasonal)",
         WIDEST_COUNTDOWN),
    ), (("shop_assault", "none"),), EVENTS_HEADING),
)

# Which period each column's shop products are taken from.
PERIOD_BY_COLUMN = {"Weekly": "weekly", "Monthly": "monthly",
                    "Other": "account"}


# **Countdowns line up in a column of their own**, and there are TWO
# of them: the rows above the Sortie shop and the Events block below
# it. Each is measured against its own members, so a long reading in
# one does not push the other's deadlines across.
#
# The groups are taken from the reserves in `COLUMNS` rather than
# listed: a row that reserves room for a countdown is a row that has
# one, and a row added there joins its group with no edit here.
# **The one answer the wire cannot give**, offered to the person who
# can see the game. A row sitting at its own ceiling is either finished
# or waiting for the game to hand out more, and almost no event ever
# says which -- so the tab asks, on a checkbox at the end of the row,
# and remembers the answer against the reading it was given for. See
# `ChecklistManager.called_finished`.
#
# Written onto the loaded snapshot for the readers to find, the way a
# recalled streak is. This program's own key, not the wire's.
EVENT_FINISHED_FIELD = "_checklist_finished"
FINISHED_LABEL = "Finished?"

COUNTDOWN_STOP_PREFIX = "endsat:"
COUNTDOWN_FIXED, COUNTDOWN_EVENTS = "fixed", "events"
COUNTDOWN_ROWS = frozenset(
    key for _title, fixed, _shops, _events in COLUMNS
    for key, _label, widest in fixed
    if widest and widest.endswith(WIDEST_COUNTDOWN))


def countdown_group(key):
    """Which column of deadlines a row's countdown belongs in, or None.

    An event row is in the Events group whatever it reserves; every
    other row that reserves a countdown is in the one above the shops.
    A shop heading is in NEITHER -- its countdown hangs off its own
    words, at a stop of its own, and it is the boundary the two groups
    sit either side of.
    """
    if str(key).startswith(EVENT_KEY_PREFIX):
        return COUNTDOWN_EVENTS
    return COUNTDOWN_FIXED if key in COUNTDOWN_ROWS else None


def countdown_reserve(widest):
    """What a row reserves for its reading ALONE, countdown aside."""
    if not widest:
        return ""
    if widest == WIDEST_COUNTDOWN:
        return ""
    if widest.endswith(SEGMENT_GAP + WIDEST_COUNTDOWN):
        return widest[:-len(SEGMENT_GAP + WIDEST_COUNTDOWN)]
    return widest


def columns_for(raw, tracked=None, now=None, definitions=None):
    """The four columns' rows for one snapshot.

    The shop rows are rebuilt from the wire every time, so a product
    the game adds or a cap it changes reaches the tab with no edit.

    `tracked` is a predicate on a product id. **An untracked product
    sinks to the bottom of its own shop** rather than leaving the tab:
    the shop still sells it, and a row that vanished would read as a
    bug. Ticking it puts it back where the shop keeps it.

    `definitions` stands in for `shop_res_data` where the snapshot
    carries none. **A session's FIRST snapshot has none**: the capture
    saves as soon as the inventory arrives -- dozens of frames before
    the shops do -- so the row set would collapse the moment a capture
    started and come back on the next save. What is remembered is which
    rows EXIST; every reading still comes from the snapshot, so a row
    whose source has not arrived reads its dash.
    """
    if definitions and not shop_stock.definitions(raw):
        raw = dict(raw or {})
        raw[shop_stock.DEFINITIONS_FIELD] = definitions
    out = []
    for title, fixed, shops, events in COLUMNS:
        rows = list(fixed)
        period = PERIOD_BY_COLUMN.get(title)
        # **The shop's own heading goes in whether or not its products
        # do.** A snapshot from before `shop_res_data` was captured
        # knows no products, and a column that emptied itself would
        # read as a broken tab rather than as data not yet arrived.
        for shop in shops if period else ():
            head = shop_head_key(shop, period)
            rows.append((head, shop_stock.SHOPS[shop],
                         WIDEST_COUNTDOWN if head in COUNTDOWNS else None))
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
        if events:
            live = event_rows(raw, now)
            if live:
                rows.append((EVENT_KEY_PREFIX, events, None))
                rows.extend(live)
        out.append((title, tuple(rows)))
    return tuple(out)


# The rows' face -- a point above the app's body text, this tab being
# read rather than scanned. The column HEADINGS are not this: they come
# from the shared helper and keep its own face.
#
# Everything the block is sized and spaced by is measured off this, so
# changing it moves the rows, the stops and the block's height
# together. The one thing that does not follow is `CHECKBOX_OVERHEAD`,
# which is the widget's own and the same at any size.
ROW_FONT = ("Segoe UI", 10)

# The Activities row reads `point_entity`, which the game writes ONLY
# when the day's reward is claimed (`guide_system` / `point_reward`).
# Nothing rolls it at reset, so:
#
#   `day_id` == today  ->  claimed today
#   `day_id` <  today  ->  yesterday's record, so today is unclaimed
#
# **`day_point` belongs to `day_id`, not to now.** It is the point
# total the claim was paid against and it freezes there, so on a stale
# record it is yesterday's figure and on a fresh one it is whatever the
# day stood at when the claim went in. It says nothing about progress
# since, which is why the row shows it only where it is also the
# finished reading.
ACTIVITY_FULL = 100
POINT_FIELD = "point_entity"
# **The claimed state shows its numbers rather than a word.** The
# record is written only by the claim and never rolled, so a stale one
# carries yesterday's points -- and a row that always prints the
# figures is one where a wrong answer can be SEEN against the game. A
# word cannot be checked against anything.
ACTIVITY_UNCLAIMED = "Unclaimed"
ACTIVITY_CLAIMED = "%d/%d Claimed"

# The two weekly currencies, and the cap the game states for the second.
# The Card states one too -- four -- but a row that only ever reads
# `0`..`4` says as much without it, where Reason is spent in sevens and
# the ceiling is what says whether a run is affordable.
CHAOS_CURRENCY = 2000027        # Loot Certification Card
SORTIE_CURRENCY = 2000036       # Reason
SORTIE_CAP = 9
CHAOS_CAP = 4

# What each gains at the Sunday reset, and the ceiling that gain stops
# at. **Not on the wire in any form**, and the only two numbers on this
# tab that are the game's rule rather than a reading -- so the row they
# produce is marked as an expectation with `EXPECTED_VALUE` until a
# capture replaces it with the real figure. See `_weekly_stock`.
#
# The grants are the game's own wording, and they match what the
# account did: `total_amount` moved by exactly these across each of the
# last four week boundaries. The Card's grant equals its cap, which is
# why it reads as a reset to four rather than a top-up.
#
# **Neither cap is a hard one.** 60 Aether buys one of either with no
# limit on the exchanges, so a holding can sit above the cap and must
# not be pulled back down to it.
CHAOS_WEEKLY_GRANT = 4
SORTIE_WEEKLY_GRANT = 3

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

# The town's daily block: the coffee flag and the day's Communication
# Passes. **Neither carries a date of its own**, so nothing in them
# says which day they belong to -- and a snapshot taken yesterday read
# as a coffee already drunk today, green, for as long as the app was
# left open.
#
# `town_visit_reset_time` is the block's own stamp: the moment the
# game granted the day, lazily, at the first login after the reset. A
# block stamped before the LAST reset belongs to a day that is over,
# and everything in it is a past day's answer.
DAY_BLOCK_PATH = ("characters", "town_data", "day_changeable_data")
DAY_BLOCK_STAMP = "town_visit_reset_time"

# Today's coffee: a CAPABILITY, so the row inverts it. The two words
# are the whole of what that row says.
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

# How many daily missions the pass hands out, and which they are: the
# LOWEST numbered, `_01` through `_06`. The count is not derivable --
# the game issues a mission lazily, so the rows carrying today's
# `issued_time` are the ones handed out so far and counting them
# understates the day. Read off the game's own screen.
#
# **Being issued today does not make a mission daily.** A patch added
# `pass_mission_008_28`, a one-off issued and claimed the same day,
# which a test on `issued_time` counted as a seventh daily and read a
# five-of-six day as finished. The number is what separates them; the
# season in the middle of the id changes and this does not.
PASS_DAILY_COUNT = 6

# The stage whose per-period run limit IS the Simulation Challenges,
# and how many runs a week allows. Same shape as a shop row: `count` is
# the runs TAKEN and `reset_time` is when it last moved, so it goes
# stale across a reset the same way.
SIMULATION_FIELD = "stage_limit_entities"
SIMULATION_STAGE = "content_boss"
SIMULATION_RUNS = 3

# Today's Chaos Delegation, read off the free daily entry it costs.
# Holding one means the run is still there to do.
#
# **`last_update` does not answer this**, though it looks as though it
# should: the daily entry is GRANTED lazily, at the first login after
# the reset, and the grant stamps that field exactly as spending it
# does. In one capture the balance went 0 -> 1 six seconds after login
# with `last_update` jumping to 19:45 against an 18:00 reset -- nothing
# had been run, and a reading off the stamp alone said it had.
#
# So the balance is the reading, and the stamp only settles the case it
# cannot: an empty balance from BEFORE the day's reset is a grant that
# has not happened yet, not an entry that was spent.
DELEGATION_CURRENCY = 2000048
DELEGATION_PATH = ("characters", "currencies", str(DELEGATION_CURRENCY))
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

# How many of a Basin season's star rewards have been claimed, one row
# per season keyed by the season id. The objectives and the rewards are
# separate: every objective can be scored with none of the rewards
# taken, and that is not a finished row.
BASIN_REWARD_FIELD = "reward_entities"

# The Full-Scale Offensive: one `remnants_entities` row per stage, each
# with a `star_count` out of three and a `best_score`. Three stages of
# three stars is the nine the screen shows, and the denominator is
# counted from the rows so a fourth stage needs no edit.
OFFENSIVE_FIELD = "remnants_entities"
OFFENSIVE_STARS = 3

# The Zero System Chaos Matrix: `reward_level` is how far up its reward
# track the account has claimed, out of a hundred. The same record's
# `chaos_orb_count` is the currency it is claimed with, which is a
# balance rather than a task and has no row.
MATRIX_FIELD = "zero_orb_entity"
MATRIX_LEVELS = 100

# The Galactic Disaster's weekly CHAOS progress, and its ceiling. The
# score is not capped on the wire -- `week_clear_score` reads 8000 with
# the screen showing 8000/8000 -- so the cap is stated and the display
# clamps to it, marking a reading that went over.
DISASTER_FIELD = "disaster_entities"
CHAOS_PROGRESS_FULL = 8000

# The Great Rift's weekly score. The standings nest season -> rank
# slot -> record, and the threshold that pays out rides in the same
# record -- `GREAT_RIFT_TARGET` is only what stands in when it does not.
GREAT_RIFT_FIELD = "disaster_boss_rank_entities"
GREAT_RIFT_TARGET = 300000

# The standings spell the week stamp their own way, where every other
# weekly record uses `WEEK_STAMP`.
GREAT_RIFT_WEEK_STAMP = "score_week_id"

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
ROW_PITCH = 4           # spacing: exception -- label row -> label row -- run, run ↕

# The same, for a row whose label is a CHECKBOX. Its own lever because
# a checkbox is taller than a text line, so the two cannot answer to
# one number.
#
# **This is the distance between the boxes, and a checkbox paints
# inset from its own**, so what the eye sees is this plus that inset
# twice over. Measured: the box-to-box gap is exactly `spacing1`,
# with nothing else of the widget's in it.
CHECKBOX_PITCH = 2      # spacing: exception -- label row -> label row -- checkbox, checkbox ↕

# And the FIRST product of a shop, which sits under the heading's words
# rather than under another box. A heading's ink stops at its baseline
# where a checkbox's stops at its own edge, so the same `spacing1`
# reads two wider there -- this is the two, given back.
CHECKBOX_UNDER_HEAD = 0  # spacing: exception -- label row -> label row -- heading, checkbox ↕

# What sets a block apart from the rows around it: extra space on the
# row that crosses a BOUNDARY -- the first row of a shop or of the
# Events list, and the first ordinary row after one.
#
# **Charged once per boundary, and only above.** Paying it below a
# block as well doubled it wherever two blocks touch, which on this tab
# is most of them -- every shop is followed by another. And the row at
# the TOP of a column crosses nothing: the Monthly column starts on a
# shop, and charging it there dropped that column below the other
# three for a gap with nothing on the other side of it.
BLOCK_PAD = 4           # spacing: exception -- label row -> label row -- run, run ↕

# And the same boundary crossed from a CHECKBOX row, which needs two
# more to read the same. Measured across every boundary on the tab: a
# heading under an ordinary row sat at 16 and one under a shop product
# at 14, the widget's ink reaching lower in its line than a glyph's
# does. Both are the one distance the eye is meant to see.
BLOCK_PAD_FROM_BOX = 6  # spacing: exception -- label row -> label row -- run, run ↕

# **A row with a checkbox at the END of it stands taller than its
# words.** The widget sets the line's height and its ink sits inside
# that, so the gap above such a row and the gap below it each read a
# pixel wider than the same `spacing1` between two rows of text.
# Measured down the Events block: 13 under a heading, 14 between two
# asking rows, 13 back to a row that is not asking, 12 between two
# that are not.
BOX_ROW_SLACK = 1

# What each line tag's `spacing1` is set from. The tags are configured
# on the Text and `_block_height` has to add the same numbers up, so
# one table serves both -- a pitch changed in one place and not the
# other sizes the block for rows it does not draw, and Tk clips the
# difference off the bottom without a word.
ROW_TAG_PITCH = {"row": ROW_PITCH, "blockrow": ROW_PITCH + BLOCK_PAD,
                 "boxblockrow": ROW_PITCH + BLOCK_PAD_FROM_BOX,
                 "boxrow": CHECKBOX_PITCH,
                 "boxheadrow": CHECKBOX_UNDER_HEAD,
                 # An ordinary row beside one asking `Finished?`, and
                 # one between two of them. See `BOX_ROW_SLACK`.
                 "row_beside_box": ROW_PITCH - BOX_ROW_SLACK,
                 "row_between_boxes": ROW_PITCH - 2 * BOX_ROW_SLACK}

# A row's words against its value, which is a left TAB STOP. A lever
# short of the rule, the words stopping inside their own advance.
#
# **A shop heading's total hangs off the same lever**, at a stop of its
# own so that it follows the heading's words rather than the column --
# see `_head_stop`.
LABEL_TO_VALUE = 6      # spacing: label ↔ its element -- run, run ↔

# The heading of a column against the first row under it. The gap runs
# from the heading's BASELINE to the row's CAPITAL, with the heading's
# box below its baseline and the row's box above its capital both
# inside it -- so most of the distance is already spent before this
# lever adds anything, and it cannot go below zero to take any back.
HEADING_GAP = 2         # spacing: exception -- panel ↕ unrelated label -- heading, frame ↕

# What a Text puts around its own content, both sides together. Its
# `width` is in CHARACTERS and this block is sized in pixels, so the
# holder is fixed and the Text fills it.
TEXT_INSET = 2

# What a shop heading's total is tagged with, plus the heading's key.
# Each heading gets a tab stop of its OWN -- the stop is a tag option
# and a tag is shared by every line that carries it, so one stop per
# heading means one tag per heading.
SHOP_STOP_PREFIX = "headstop:"


def _head_stop(font, label):
    """Where a shop heading's total starts, in pixels from the left.

    Off the heading's OWN words rather than off the column's
    label/value stop: the total belongs to the shop it names, not to
    the column of readings beside it. Same lever and so the same gap,
    which is why a heading that IS its column's longest label lands on
    that stop exactly -- there is nowhere else the gap could put it.
    """
    # spacing: label ↔ its element -- run, run ↔
    return font.measure(label) + TEXT_INSET + LABEL_TO_VALUE



class ChecklistTab(BaseTab):
    """The recurring-task columns."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        # (Text, rows) per column heading, for the refresh to rewrite,
        # and the row set they were built for. A snapshot that changes
        # the set -- a shop gaining a product -- rebuilds them.
        self.column_texts = {}
        # **Kept PER COLUMN, and that is what stops the tab flashing.**
        # A redraw that rewrote all four destroyed and recreated every
        # embedded checkbox each time a capture saved or a box was
        # ticked. `_rendered` is what each column actually has drawn in
        # it, and the only thing a redraw is decided on: identical
        # leaves it alone, a reading moved patches that line, anything
        # else builds the column again.
        self._rendered = {}
        # The shop checkboxes embedded in each column, so a toggle can
        # find the widget it came from. Not owned: Tk destroys an
        # embedded window along with the Text holding it.
        self._boxes = {}
        # The last `shop_res_data` seen. A capture's first snapshot is
        # written before the shops arrive, and without this the whole
        # shop half of the tab vanishes until the next save.
        self._definitions = None
        # The countdown beside each period column's heading.
        self._period_labels = {}
        # How tall a line holding a checkbox is. See `_checkbox_line`.
        self._box_line = None
        # The full name behind a shortened product row, and the rates
        # behind a shop heading. One instance serves every target.
        self._tips = Tooltip(self.colors)
        # heading key -> the (label, value) rows its tip shows. Read at
        # HOVER time rather than at bind time, so a tip put on a tag
        # when the column was built still says what the tab says now.
        self._shop_tips = {}
        # {row key: (claimed, total, ticked)} for the event rows the
        # `Finished?` question is open on. See `_mark_finished`.
        self._finishable = {}
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
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        columns.pack(fill=tk.BOTH, expand=True, padx=px(4),
                     pady=px((0, 2)))

        # Content in the EVEN grid columns, an empty expanding one
        # between each pair. Given to spacers of one uniform group the
        # leftover width lands as equal gaps with the block flush
        # against both edges; shared out inside the content cells it
        # lands unequally, the widest column keeping the least.
        for index in range(len(COLUMNS)):
            columns.grid_columnconfigure(2 * index, weight=0)
        # BETWEEN the columns only -- `len(COLUMNS) - 1` of them. A
        # trailing spacer would take the whole leftover width itself
        # and leave the last column a hundred pixels short of the
        # edge the first one is four from.
        for index in range(len(COLUMNS) - 1):
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

    def _rebuild_columns(self, raw, readings):
        """(Re)build the heading and rows of any column that changed.

        **One column at a time.** A rebuild destroys a Text and every
        checkbox embedded in it, so rebuilding the four together made
        the whole tab flash for a change in one of them -- and ticking
        a box changes exactly one column, since an untracked product
        sinks within its own shop.

        **And the replacement is built and filled before the column it
        replaces is dropped**, all of it unmapped, so the swap is one
        paint rather than a Text appearing empty and filling in. See
        `_build_column`.

        **Anything `_fill` cannot patch is rebuilt here**, which is the
        whole of the rule: a patch rewrites a line's reading and
        touches no widget, and everything else needs new checkboxes.
        Deciding on the row keys alone left one case behind -- ticking
        a product already at the bottom of its shop changes its COLOUR
        and moves nothing, so the keys matched, no rebuild ran, and the
        rewrite landed on the Text that was already on screen.
        """
        # The shop DEFINITIONS are remembered across snapshots, so a
        # capture's first save -- written before the shop payloads
        # arrive -- cannot empty the tab. See `columns_for`.
        seen = shop_stock.definitions(raw)
        if seen:
            self._definitions = seen
        built = columns_for(raw, self._tracked, time.time(),
                            self._definitions)
        for frame, (title, rows) in zip(self._column_frames, built):
            drawn = self._draw(rows, readings)
            if _same_rows(self._rendered.get(title), drawn):
                continue                    # `_fill` patches or skips
            outgoing = list(frame.winfo_children())
            # The old column's own state goes with it. The checkboxes
            # need no destroying: Tk destroys an embedded window with
            # the Text that holds it.
            self._boxes.pop(title, None)
            self._rendered.pop(title, None)
            self._period_labels.pop(title, None)
            # Dropped rather than overwritten: a column with no rows
            # builds no Text at all, and the old entry would otherwise
            # keep pointing at the one just destroyed.
            self.column_texts.pop(title, None)
            show = self._build_column(frame, title, rows)
            text = self.column_texts.get(title)
            if text is not None:
                self._fill(title, text[0], rows, readings)
            for child in outgoing:
                child.destroy()
            show()

    def _build_column(self, parent, title, rows):
        """One heading and the rows under it, BUILT BUT NOT SHOWN.

        Returns the callable that shows it. Nothing here is packed:
        a widget with no geometry manager is never mapped, and neither
        are its children, so the whole column -- Text, embedded
        checkboxes and all -- is assembled without a single paint. The
        caller fills it, drops the column it replaces, and only then
        calls what comes back.

        That is what stops the flash. Tk destroys an embedded window
        when its text is deleted, so a rewrite has no choice but to
        build new checkboxes, and a checkbox built inside a MAPPED Text
        shows up at the widget's origin for the frame before
        `window_create` places it -- a white dot at the top left of the
        column, once per box.
        """
        show = []
        # The heading and its countdown travel together and the pair is
        # centred, so the heading itself sits a little left of centre.
        head = ttk.Frame(parent)
        show.append(lambda: head.pack(anchor=tk.CENTER))
        make_heading(head, title).pack(side=tk.LEFT, anchor=tk.S)
        if title in PERIOD_LENGTHS:
            # spacing: heading ↔ element -- heading, label ↕
            label = ttk.Label(head, text="", font=HEADING_COUNTDOWN_FONT)
            label.pack(side=tk.LEFT, anchor=tk.S,
                       padx=px((HEADING_COUNTDOWN_GAP, 0)),
                       pady=px((0, HEADING_COUNTDOWN_DROP)))
            self._period_labels[title] = label

        if not rows:
            return lambda: [do() for do in show]
        font = tkfont.Font(font=ROW_FONT)
        # The words, plus a column reserved for the widest reading any
        # row in this column can show. RESERVED rather than fitted: a
        # column that sized to its content would move every row's words
        # the moment a figure gained a digit.
        #
        # A shop product's label is a CHECKBOX, so it reaches further
        # right than its words alone say.
        #
        # **A row showing NO value has no say in where the value column
        # sits.** A shop heading is the long one -- `Shop - Exchange
        # Shop - Prism Module` -- and its total hangs off its own words
        # rather than standing in the column, so letting it vote pushed
        # every reading beside it right for a column it does not use.
        # Shop PRODUCTS still vote: their counts are in that column.
        measured = [(key, label) for key, label, w in rows if w] or \
            [(key, label) for key, label, _w in rows]
        labels = max(font.measure(label)
                     + (px(CHECKBOX_OVERHEAD) if _is_shop(key) else 0)
                     for key, label in measured)
        stop = labels + TEXT_INSET + LABEL_TO_VALUE
        widest = max([font.measure(w) for _k, _l, w in rows if w] or [0])
        # **A shop heading's line is outside that column**, hanging off
        # its own words: its total, then its reserve, then anything
        # else the heading shows. So the block is as wide as whichever
        # reaches further, the readings at the stop or the longest
        # heading here.
        reach = max([_head_stop(font, label)
                     + font.measure(SHOP_TOTAL_WIDEST)
                     + (font.measure(w) if w else 0)
                     for key, label, w in rows
                     if key.startswith(SHOP_HEAD_PREFIX)] or [0])
        # **A stop per group of countdowns**, measured against that
        # group's own readings: the rows above the shops and the
        # Events block below them each line their deadlines up on
        # their own, so a long reading in one does not push the
        # other's across. See `countdown_group`.
        #
        # The gap before the column is the width of `SEGMENT_GAP` in
        # the rows' own face, MEASURED rather than scaled: the font
        # scaling has already carried it, and two spaces is the
        # narrowest a reading and a deadline may sit.
        group_stops = {}
        for group in sorted({countdown_group(key) for key, _l, _w in rows}
                            - {None}):
            reserve = max([font.measure(countdown_reserve(w))
                           for key, _l, w in rows
                           if countdown_group(key) == group] or [0])
            at = stop + reserve + font.measure(SEGMENT_GAP)
            stops = [at]
            # **And the Events group has one more**, for the
            # `Finished?` box at the end of a row whose ceiling nothing
            # proves. Room is reserved whether or not any row is
            # asking today: a column that widened the moment a question
            # opened would move every row beside it.
            if group == COUNTDOWN_EVENTS:
                stops.append(at + font.measure(WIDEST_COUNTDOWN)
                             + font.measure(SEGMENT_GAP))
            group_stops[group] = tuple(stops)
            reach = max(reach, stops[-1] + font.measure(WIDEST_COUNTDOWN)
                        if len(stops) == 1 else
                        stops[-1] + font.measure(FINISHED_LABEL)
                        + px(CHECKBOX_OVERHEAD))
        holder = tk.Frame(parent, width=max(stop + widest, reach),
                          height=self._block_height(
                              [key for key, _l, _w in rows]),
                          bg=self.colors["bg"])
        holder.pack_propagate(False)
        # spacing: panel ↕ unrelated label -- heading, frame ↕
        # Packed LAST of the three, so it never maps as an empty
        # block waiting for its Text: a child packed into an unmapped
        # parent maps with it, all at once.
        pack_holder = lambda: holder.pack(anchor=tk.N,
                                          pady=px((HEADING_GAP, 0)))

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
        show.append(lambda: text.pack(fill=tk.BOTH, expand=True))
        show.append(pack_holder)
        # Exactly ONE of these per line. Tk resolves two tags setting
        # the same option by priority rather than by sum, so a pad
        # stacked on top of `row` would depend on the order the tags
        # were created in -- which is not a thing to lay a gap on.
        # spacing: exception -- label row -> label row -- run, run ↕
        # spacing: exception -- label row -> label row -- checkbox, checkbox ↕
        # spacing: exception -- label row -> label row -- heading, checkbox ↕
        for tag, pitch in ROW_TAG_PITCH.items():
            text.tag_configure(tag, spacing1=px(pitch))
        for group, stops in group_stops.items():
            text.tag_configure(COUNTDOWN_STOP_PREFIX + group,
                               tabs=(stop,) + stops)
        # A tab stop per shop heading, for the total beside it. A
        # line's stops come from the tags on its FIRST character, so
        # each heading needs a tag of its own -- one stop cannot serve
        # two headings of different lengths.
        for key, label, _w in rows:
            if not key.startswith(SHOP_HEAD_PREFIX):
                continue
            own = _head_stop(font, label)
            # Two stops, both the heading's own: the total, and
            # whatever follows it. **The second cannot be the column's
            # stop.** A total is wider than the gap between a heading
            # and that stop, so a tab aiming there is already behind
            # the cursor -- and Tk then falls through to a spacing of
            # its own devising, which is not a thing to lay a gap on.
            # So a shop heading's line hangs entirely off its words.
            text.tag_configure(
                SHOP_STOP_PREFIX + key,
                tabs=(own, own + font.measure(SHOP_TOTAL_WIDEST)))
            # What the shop's currency has been earning. Bound to the
            # TAG rather than to the words, and reading the rows back
            # when the pointer stops rather than now: the tag outlives
            # every rewrite of the line it covers, and the figures do
            # not.
            self._tips.bind_tag(
                text, SHOP_TIP_PREFIX + key,
                lambda k=key: self._shop_tips.get(k))
        # Green is nothing left to do on that row, red is something
        # left. A row a snapshot cannot answer for takes neither.
        text.tag_configure(DONE, foreground=self.colors["green"])
        text.tag_configure(TODO, foreground=self.colors["red"])
        # A floor draws red like any other unfinished row; one that
        # has stood at its ceiling for two days draws orange. See
        # `FLOOR`.
        text.tag_configure(FLOOR, foreground=self.colors["red"])
        text.tag_configure(STALE_FLOOR,
                           foreground=self.colors["orange"])
        text.tag_configure(CYCLE_DONE, foreground=self.colors["orange"])
        text.tag_configure(MUTED, foreground=self.colors["fg_dim"])
        # A shop heading's total, in the same yes and no a hair darker
        # and a hair stronger. It answers for the whole block under it,
        # so it reads as the block's verdict rather than as one more
        # row's. See `HEAD_STATE_TAGS`.
        for state, tag in HEAD_STATE_TAGS.items():
            text.tag_configure(tag, foreground=self.colors[
                "green_deep" if state is DONE else "red_deep"])
        # A shop heading's own colour. See `SHOP_LABEL_COLOURS`.
        for _words, colour in SHOP_LABEL_COLOURS:
            text.tag_configure(colour, foreground=self.colors[colour])
        # A countdown reddens as it runs out. The middle band is the
        # Materials tab's own warning colour, so the two agree.
        text.tag_configure(SOON, foreground=self.colors["red"])
        text.tag_configure(WARN, foreground=self.colors["orange"])
        text.tag_configure(LATER, foreground=self.colors["yellow"])
        self.column_texts[title] = (text, rows)
        return lambda: [do() for do in show]

    def _checkbox_line(self):
        """How tall a line holding a checkbox is, MEASURED once.

        **A `tk.Checkbutton` is taller than the text line it sits in**
        -- its indicator sets the height, not the words -- and Tk grows
        the line to fit the window embedded in it. So a block sized on
        the font's `linespace` alone comes up short by the difference
        on every checkbox row it holds, and `pack_propagate(False)`
        clips the shortfall off the bottom without a word: the shops at
        the foot of a column simply stop being drawn.

        Not written down as a number: it moves with the face and with
        the display scale, and a stale one here LOSES rows.

        The probe is never given a geometry manager, so it is built and
        destroyed without ever being mapped.
        """
        if self._box_line is None:
            # **In the rows' own face.** A checkbox a point smaller than
            # the rows it sits among is a pixel shorter, and a block
            # sized off that probe clips one pixel per checkbox row --
            # which the column's foot pays all at once.
            probe = make_checkbox(self.frame, self.colors, text="Ag",
                                  compact=True, font=ROW_FONT)
            self._box_line = probe.winfo_reqheight()
            probe.destroy()
        return max(tkfont.Font(font=ROW_FONT).metrics("linespace"),
                   self._box_line)

    def _block_height(self, keys):
        """A column's height: its rows and the space around each.

        Measured off the face rather than multiplied by a guess -- a
        Text sizes in LINES and this block is pinned in pixels, so the
        two have to be reconciled somewhere.

        **Every row's OWN height and pitch**, not one figure times the
        row count: a checkbox row, a block boundary and an ordinary row
        differ in both, and a block sized on the ordinary one clips
        however many lines the difference adds up to.

        **An event row asking `Finished?` is a checkbox row too.** Its
        words are ordinary text, but the box embedded at the end of the
        line sets the line's height the same way a shop product's does
        -- and a block that counted it as text came up short by the
        difference, per asking row, and clipped the foot of the column.
        """
        # Each row's pitch counts, not each gap BETWEEN rows:
        # `spacing1` is drawn above EVERY line including the first, so
        # a block sized for the gaps alone is one pitch short and clips
        # its last line.
        line = tkfont.Font(font=ROW_FONT).metrics("linespace")
        box = self._checkbox_line()
        total, above = 0, None
        for key in keys:
            total += (box if _is_shop(key) or key in self._finishable
                      else line)
            total += px(ROW_TAG_PITCH[
                _row_tags(key, above, self._finishable)[0]])
            above = key
        return total

    # ----------------------------------------------------------- update

    def refresh_checklist(self):
        """Redraw every reading from the loaded snapshot.

        Called automatically after data loads.
        """
        raw = getattr(self.optimizer, "raw_data", None) or {}
        self._recall_streaks(raw)
        self._recall_event_totals(raw, time.time())
        readings = self._settle_floors(
            _readings(raw, tracked=self._tracked))
        # Before the columns are built: the sort reads the answers off
        # `raw`, and the rows are built from that.
        self._finishable = self._mark_finished(raw, readings)
        self._shop_tips = self._rates(raw, time.time())
        # A rebuilt column is filled inside the rebuild, before it is
        # shown; this fills the ones that were left standing.
        self._rebuild_columns(raw, readings)
        for title, (text, rows) in self.column_texts.items():
            self._fill(title, text, rows, readings)
        self._fill_period_headings(raw)

    def _recall_event_totals(self, raw, now):
        """Record what ended events held, and say what live ones hold.

        **A finished instalment's mission rows are its whole total.**
        A live event's are only what has been issued so far, which is
        why nearly every event row on the tab can show a floor and
        nothing better -- and the same family's last instalment is the
        one thing that knows more.

        Recording is the half that cannot wait: the game purges old
        instalments, and a count nobody wrote down while the rows were
        there is gone. So every ended event is counted on every load,
        whether or not anything is live to use it.

        What comes back is written onto `raw` under
        `EVENT_TOTALS_FIELD`, where the readers take it off the
        snapshot like any other field. Only families whose finished
        instalments AGREE are in it -- see
        `ChecklistManager.event_total`.
        """
        manager = getattr(self.context, "checklist_manager", None)
        if manager is None or not isinstance(raw, dict):
            return
        for group in EVENT_GROUPS:
            for name, _window in schedules.ended(group, raw, now):
                rows = _event_mission_rows(raw, name)
                if rows:
                    manager.record_event_total(
                        _stem(_event_key(name)), name, len(rows))
        totals = {}
        for group in EVENT_GROUPS:
            for name, _window in schedules.all_live(group, raw, now):
                total = manager.event_total(_stem(_event_key(name)), name)
                if total is not None:
                    totals[name] = total
        raw[EVENT_TOTALS_FIELD] = totals

    def _mark_finished(self, raw, readings):
        """Fold the user's `Finished?` answers into the readings.

        Returns `{row key: (claimed, total, ticked)}` for every event
        row the question is open on -- which is what the column draws
        a checkbox for, ticked or not.

        **A ticked row reads GREEN and sorts down with the finished**,
        because the person who ticked it can see the game and this
        program cannot. The answer is written onto `raw` as well, for
        the sort: `event_rows` is built before these readings are.

        **An answer whose reading has moved is gone, not stale.** Every
        tick is remembered against the pair it was given for, so
        another reward claimed or another one to claim retires it --
        and the row goes back to red with the box unticked. A row not
        on the tab at all is left alone: its event may simply be over,
        and a tab with no snapshot behind it would otherwise wipe
        every answer at once.
        """
        manager = getattr(self.context, "checklist_manager", None)
        out = {}
        for key, segments in list(readings.items()):
            if not str(key).startswith(EVENT_KEY_PREFIX):
                continue
            name = key[len(EVENT_KEY_PREFIX):]
            pair = unsure_ceiling(segments)
            if pair is None:
                # The row exists and is not at an unproven ceiling, so
                # an answer about it is about a reading that is gone.
                if manager is not None and name in manager.finished:
                    manager.call_finished(name, 0, 0, done=False)
                continue
            ticked = bool(manager is not None
                          and manager.called_finished(name, *pair))
            if not ticked and manager is not None and name in manager.finished:
                manager.call_finished(name, 0, 0, done=False)
            out[key] = pair + (ticked,)
            if ticked:
                readings[key] = ((segments[0][0], DONE),) + tuple(segments[1:])
        if isinstance(raw, dict):
            raw[EVENT_FINISHED_FIELD] = frozenset(
                key[len(EVENT_KEY_PREFIX):] for key, row in out.items()
                if row[2])
        return out

    def _recall_streaks(self, raw):
        """Put `completed` back on a streak the game has ended.

        **The game says a streak is over exactly once**, on the reply
        to the claim that finishes it. The login that follows sends
        the row without it, and that row cannot be told from a streak
        merely claimed for today -- so the answer has to be kept, or
        every finished streak reads unfinished from the next session
        until its event ends.

        The manager keeps it; this hands it back. Written onto the row
        rather than passed beside it because it IS the row's own field
        and the readers already know what it means -- the capture does
        the same thing one level down, carrying `completed` across the
        login that would otherwise overwrite it.

        Recording and recalling in one pass, so a streak finished this
        session is remembered for the next.
        """
        manager = getattr(self.context, "checklist_manager", None)
        rows = (raw or {}).get(ATTENDANCE_FIELD)
        if manager is None or not isinstance(rows, list):
            return
        for row in rows:
            event_id = row.get("event_id") if isinstance(row, dict) else None
            if event_id is None:
                continue
            if row.get(ATTENDANCE_OVER):
                manager.remember_streak(event_id)
            elif manager.streak_finished(event_id):
                row[ATTENDANCE_OVER] = True

    def _rates(self, raw, now):
        """{heading key: the rows its tip shows}, the ledger updated.

        **Recording and reading in one pass**, because the reading is
        of the record: today's point has to be in the ledger before a
        rate off it can include today. See `ChecklistManager`.

        A shop with no single currency gets no tip -- there is no
        holding for a rate to be a rate of.

        **Dated by the SNAPSHOT, not by the clock.** Opening an old
        capture file is an ordinary thing to do, and its figures belong
        to the day it was taken; written against today they would read
        as weeks of earnings undone. `now` only stands in where a
        snapshot carries no time of its own.
        """
        manager = getattr(self.context, "checklist_manager", None)
        if manager is None:
            return {}
        taken = _dig(raw, ("characters", "server_time"))
        day = weekly_reset.day_index(taken if taken else now)
        made = _dig(raw, ("characters", "user", "createAt"))
        since = weekly_reset.day_index(made) if _is_count(made) and made else None
        out = {}
        for title, _fixed, shops, _events in COLUMNS:
            period = PERIOD_BY_COLUMN.get(title)
            for shop in shops if period else ():
                # **The seasonal shop has no rate to give.** Its
                # currency is wiped at the end of every season, so what
                # was earned of it last season says nothing about this
                # one and a lifetime total spans several wipes.
                if shop[0] == SEASONAL_SHOP_CATEGORY:
                    continue
                money = shop_currency(shop, period, raw)
                if money is None:
                    continue
                value, kind = currency_earned(raw, money)
                if value is None:
                    points = manager.currency_points(money)
                else:
                    points = manager.record_currency(
                        money, value, day, kind, since)
                word, days = shop_period(period, raw, now)
                name = ITEM_NAMES.get(money) or str(money)
                # The rates first, then what a full period costs --
                # which is the figure they are worth reading against,
                # and which is there even on a ledger too young to
                # give a rate at all.
                rows = shop_rates(points, word, days, name) + (
                    (FULL_COST_LABEL,
                     RATE_VALUE % (shop_full_cost(shop, period, raw,
                                                  self._tracked), name)),)
                out[shop_head_key(shop, period)] = rows
        return out

    def _settle_floors(self, readings):
        """Turn a floor that has stopped moving orange.

        A `FLOOR` reading cannot say whether its work is finished --
        see the constant. What it CAN say is that it has not moved:
        the manager remembers when each row last read something new,
        and a row sitting at its own ceiling for two days has either
        finished or stopped being handed more. Neither is red, and
        neither is green.

        A row below its ceiling is still work, however long it has sat
        there, so only a full one settles.
        """
        manager = getattr(self.context, "checklist_manager", None)
        if manager is None:
            return readings
        now = time.time()
        for key, segments in readings.items():
            for at, (words, state) in enumerate(segments):
                if state is not FLOOR:
                    continue
                since = manager.first_seen(key, words, now)
                if _at_ceiling(words) and now - since >= FLOOR_SETTLES_AFTER:
                    segments[at] = (words, STALE_FLOOR)
        manager.forget_unseen(readings)
        return readings

    def _fill_period_headings(self, raw):
        """Rewrite the countdown beside each period column's heading."""
        now = time.time()
        for title, label in self._period_labels.items():
            left, length = _period_left(title, raw, now)
            if left is None:
                label.config(text="")
                continue
            label.config(text=_period_words(left),
                         foreground=self.colors[
                             PERIOD_COLOURS[_period_band(left, length)]])

    def _fill(self, title, text, rows, readings):
        """Rewrite one column: its rows, and any reading beside one.

        **Nothing happens when the column already reads that way.**
        The rewrite destroys and recreates every checkbox in the block,
        which reflows the Text visibly, and most refreshes -- a capture
        saving, the tab being shown again -- change nothing at all.

        **And when only the numbers moved, only the numbers are
        rewritten.** A countdown ticking over would otherwise rewrite
        the whole block, checkboxes and all, for a line of digits.

        **A shop product's label is a CHECKBOX**, embedded in the line
        with `window_create`, and its left edge lands where an ordinary
        row's words do.
        """
        drawn = self._draw(rows, readings)
        was = self._rendered.get(title)
        if drawn == was:
            return
        self._rendered[title] = drawn
        moved = [(index, after) for index, (before, after)
                 in enumerate(zip(was or (), drawn)) if before != after]
        # **A line holding a `Finished?` box is never patched.** The
        # patch rewrites everything from the row's first tab to the end
        # of the line, and the box is in that stretch -- so a countdown
        # ticking over would take the checkbox with it.
        if _same_rows(was, drawn) and not any(after[0][4] for _i, after in moved):
            text.config(state=tk.NORMAL)
            for index, after in moved:
                _patch_value(text, index + 1, after)
            text.config(state=tk.DISABLED)
            return
        for box in self._boxes.pop(title, ()):
            box.destroy()
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        for index, ((key, label, _tracked, segments, box), line,
                    label_tag, total) in enumerate(drawn):
            if index:
                text.insert(tk.END, LINE_SEP, line)
            if _is_shop(key):
                head = segments[0][1] if segments else UNKNOWN
                # **`window_create` takes no tags**, and a line reads
                # its own `spacing1` and its tab stops off its FIRST
                # character -- which for one of these rows is the
                # untagged character the window leaves behind. So the
                # tags on the rest of the line styled the words and
                # nothing else: a checkbox row took none of the pitch
                # above it, and changing that moved nothing on screen.
                # The window lands where `end` was before the call.
                at = text.index(tk.END + "-1c")
                text.window_create(tk.END, window=self._checkbox(
                    title, text, key, label, head))
                for tag in line:
                    text.tag_add(tag, at, at + "+1c")
            else:
                text.insert(tk.END, label, line + label_tag
                            + ((SHOP_TIP_PREFIX + key,)
                               if key.startswith(SHOP_HEAD_PREFIX) else ()))
            _insert_value(text, key, line, total, segments)
            # **The one question the program cannot answer**, at the
            # end of the row and at a stop of its own. Only where it
            # is open: a row the game has called finished, or one with
            # work left, is not asked about. See `_mark_finished`.
            if box is not None:
                text.insert(tk.END, COLUMN_SEP, line)
                text.window_create(tk.END, window=self._finished_box(
                    title, text, key, box))
        text.config(state=tk.DISABLED)

    def _draw(self, rows, readings):
        """Every row's drawn form, each told what precedes it.

        One place, because the column is built from this twice -- once
        to decide whether anything changed and once to write it -- and
        two loops that drifted apart would compare a column against a
        different column and rewrite it every refresh.
        """
        above = None
        out = []
        for key, label, _widest in rows:
            out.append(self._line(key, label, readings, above))
            above = key
        return tuple(out)

    def _line(self, key, label, readings, above=None):
        """One row's drawn form: its words, its readings, its tags.

        Everything that decides what the line LOOKS like, and nothing
        else, so two of these comparing equal means the column can be
        left alone. `tracked` is carried even though it shows only
        through the segment colours: it also colours the CHECKBOX, and
        a value patch does not repaint that.

        `above` is the key of the row OVER this one, or None at the top
        of the column, and it is what says whether this row pays the
        pad that sets a block apart -- see `_row_tags`.

        The fourth field is a shop heading's own total, which sits at a
        stop of its own rather than in the column of readings.
        """
        tracked = not _is_shop(key) or self._tracked(_product_of(key))
        segments = tuple(readings.get(key) or ())
        if not tracked:
            # An untracked product says so in its colour: every segment
            # greys, red and green being about work left and a product
            # nobody tracks having none.
            segments = tuple((words, MUTED) for words, _s in segments)
        total = readings.get(SHOP_TOTAL_PREFIX + key)
        # The fifth field is the row's `Finished?` state, which is a
        # WIDGET rather than a reading: a value patch cannot repaint
        # it, so it belongs in what says whether the line is the same.
        return ((key, label, tracked, segments, self._finishable.get(key)),
                _row_tags(key, above, self._finishable),
                _label_tag(key, label), total[0] if total else None)

    def _checkbox(self, title, parent, key, label, state):
        """One shop product's checkbox, kept alive on the tab.

        Held in `_boxes` under its own column because a Text does not
        own an embedded window: dropping the reference leaves the
        widget parented and undestroyed on the next rewrite.

        **The tip is bound to the WIDGET**, so a row whose words are
        cut short carries its full name wherever ticking sorts it --
        the box is rebuilt in its new place with the same binding.
        """
        product_id = _product_of(key)
        variable = tk.BooleanVar(value=self._tracked(product_id))
        box = make_checkbox(
            parent, self.colors, text=label, variable=variable,
            compact=True, font=ROW_FONT,
            fg=self.colors["fg_dim"] if state is MUTED else None,
            command=lambda p=product_id, v=variable: self._toggle(p, v))
        tip = self._product_tip(product_id)
        if tip:
            self._tips.bind(box, tip)
        self._boxes.setdefault(title, []).append(box)
        return box

    def _finished_box(self, title, parent, key, state):
        """One event row's `Finished?` checkbox, kept alive on the tab.

        YELLOW while the question is open and ORANGE once answered:
        the reading beside it has gone green, and the answer is the
        user's rather than the game's -- which is a different kind of
        green from an event the wire called over.

        Held in `_boxes` with the shop ones, for the same reason: a
        Text does not own an embedded window.
        """
        claimed, total, ticked = state
        name = key[len(EVENT_KEY_PREFIX):]
        variable = tk.BooleanVar(value=ticked)
        box = make_checkbox(
            parent, self.colors, text=FINISHED_LABEL, variable=variable,
            compact=True, font=ROW_FONT,
            fg=self.colors["orange" if ticked else "yellow"],
            command=lambda n=name, c=claimed, t=total, v=variable:
                self._toggle_finished(n, c, t, v))
        self._boxes.setdefault(title, []).append(box)
        return box

    def _toggle_finished(self, name, claimed, total, variable):
        """Persist one `Finished?` answer, then redraw.

        **Redrawn on an idle callback, never here.** Answering moves
        the row down among the finished ones, so the redraw destroys
        every widget in the column -- this checkbox among them.
        """
        manager = getattr(self.context, "checklist_manager", None)
        if manager is not None:
            manager.call_finished(name, claimed, total,
                                  done=bool(variable.get()))
        self.frame.after_idle(self.refresh_checklist)

    def _product_tip(self, product_id):
        """One product's full name, or None where its row shows it.

        Off the remembered definitions rather than off the snapshot:
        the rows are built from those too, so a tip cannot go missing
        on a capture's first save while its row is still drawn.
        """
        for defines in (self._definitions or {}).values():
            define = (defines or {}).get(product_id) if isinstance(
                defines, dict) else None
            if isinstance(define, dict):
                return product_tip(define)
        return None



# What separates one row from the next, and a row from its value.
# Named because a Text's columns ARE its tabs and its rows ARE its
# newlines -- so these two characters are structure rather than
# punctuation.
LINE_SEP = "\n"
COLUMN_SEP = "\t"


def _pass_daily_number(res_id):
    """Whether a mission id is one of the pass's DAILY ones.

    `pass_mission_<season>_NN` with NN in the first six. The season sits
    in the middle and changes; the trailing number does not.
    """
    text = str(res_id)
    if not text.startswith(PASS_MISSION_PREFIX):
        return False
    tail = text.rsplit("_", 1)[-1]
    return tail.isdigit() and 1 <= int(tail) <= PASS_DAILY_COUNT


def _this_week(record, now, field=WEEK_STAMP):
    """Whether a weekly record belongs to the week `now` falls in.

    **A weekly record is written lazily, exactly like a daily one.**
    Nothing zeroes it at the reset: last week's EXP, score and clear
    total survive untouched into the new week, and only the `week_id`
    beside them says which week they are. So the STAMP is the reading
    -- a number below this week's means the figures next to it belong
    to last week and this week's are all zero.

    A record with no stamp is taken at face value: nothing about it
    can say otherwise, and refusing to read it would blank a row that
    may be perfectly current.
    """
    stamp = (record or {}).get(field) if isinstance(record, dict) else None
    if not _is_count(stamp):
        return True
    return stamp >= weekly_reset.week_index(now)


def _weekly_stock(raw, res_id, grant, cap, now):
    """(how much of a weekly allowance is on hand, whether that is exact).

    These two are TOPPED UP at the reset rather than zeroed, and the
    top-up is applied lazily -- the record still carries last week's
    leftover until something in game touches that content. So once the
    week has rolled past the record, what it holds is not the stock
    and the stock has to be worked out:

        min(leftover + grant, cap)

    `grant` and `cap` are the game's own rule for the currency and are
    written down beside it. **The cap is HARD** -- the maintainer has
    tested that no amount of buying takes a holding past it -- so the
    top-up simply stops there.

    **The answer is then EXPECTED rather than read**, and the row says
    so with `EXPECTED_VALUE` until a capture replaces it with the real
    figure. Buying more with Aether is what can move it in between,
    which is also why a record that has been written this week is
    taken at face value however odd it looks.

    `last_update` is what dates the record. It is not a write stamp --
    spending the currency does not move it -- but it does move when
    the currency is GAINED, which is what the week's top-up is.
    """
    currencies = ((raw or {}).get("characters") or {}).get("currencies") or {}
    doc = currencies.get(str(res_id))
    doc = doc if isinstance(doc, dict) else {}
    amount = doc.get("amount")
    amount = amount if _is_count(amount) else 0
    touched = doc.get("last_update")
    if not _is_count(touched) or not touched:
        return amount, True
    if touched >= weekly_reset.last_weekly_reset(now):
        return amount, True
    return min(amount + grant, cap), False


def _tally(words):
    """`(claimed, total)` off an `n/m` reading, or None.

    The marks a reading can carry come off first: `UNKNOWN_MORE` says
    the total is a floor and `EXPECTED_VALUE` says it was worked out,
    and neither changes what the two numbers are.
    """
    words = str(words)
    if words.endswith(UNKNOWN_MORE):
        words = words[:-len(UNKNOWN_MORE)]
    if words.startswith(EXPECTED_VALUE):
        words = words[len(EXPECTED_VALUE):]
    parts = words.split("/")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1])


def unsure_ceiling(segments):
    """`(claimed, total)` where a row is at a ceiling nothing proves.

    **The question the checkbox asks.** Everything claimed that the
    program can see, and no word from the game that the event is over
    -- which is the one state a person looking at the game can settle
    and this program cannot.

    A row the game HAS called finished is not asked about, and neither
    is one with work left to do.
    """
    if not segments:
        return None
    words, state = segments[0]
    if state is DONE:
        return None
    pair = _tally(words)
    if pair is None or pair[0] < pair[1]:
        return None
    return pair


def _at_ceiling(words):
    """Whether an `n/m` reading has n equal to m.

    `UNKNOWN_MORE` comes off first: a floor's `16/20+?` is at
    its ceiling on exactly the same terms as a plain `20/20`, and that
    suffix is the whole reason such a row can settle at all.
    """
    words = str(words)
    if words.endswith(UNKNOWN_MORE):
        words = words[:-len(UNKNOWN_MORE)]
    parts = words.split("/")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        return False
    return int(parts[0]) >= int(parts[1])


def _day_block(raw, now):
    """(the town's daily block, whether it is TODAY's).

    See `DAY_BLOCK_PATH`. A block stamped before the last reset is a
    finished day's, and its readings have all come back -- so the
    caller answers from the reset rather than from the block.

    Where the stamp is missing, the CAPTURE's own time stands in: a
    snapshot written before the last reset cannot hold today's answers
    whatever it says. That is also what makes the rows come back with
    no capture running -- the clock moves and the snapshot does not.
    """
    block = _dig(raw, DAY_BLOCK_PATH)
    if not isinstance(block, dict):
        # **None is not a rolled day.** A snapshot that never carried
        # the block cannot say the coffee is waiting either, and a row
        # with no source reads its dash.
        return None, False
    since = weekly_reset.last_daily_reset(now)
    stamped = block.get(DAY_BLOCK_STAMP)
    if _is_count(stamped):
        return block, stamped >= since
    taken = _capture_time(raw)
    return block, taken is None or taken >= since


def _capture_time(raw):
    """When the snapshot was written, epoch seconds, or None.

    `capture_time` is a naive local timestamp, which is what the
    machine reading it runs on too, so it converts without a zone.
    """
    stamp = (raw or {}).get("capture_time")
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None


def _label_tag(key, label):
    """The tag a row's own words take, as a tuple for concatenation.

    Only a SHOP HEADING gets one -- see `SHOP_LABEL_COLOURS`. The
    products under it keep the ordinary foreground, so the heading is
    what the eye lands on when scanning for a shop.
    """
    if not key.startswith(SHOP_HEAD_PREFIX):
        return ()
    for words, colour in SHOP_LABEL_COLOURS:
        if words in label:
            return (colour,)
    return ()


def _same_rows(was, drawn):
    """True where two drawn columns differ only in their READINGS.

    That is the case a value can be patched into: the rows are the same
    things in the same order, each still tracked the way it was, so
    every line's label -- and any checkbox embedded in it -- already
    says what it should.
    """
    if was is None or len(was) != len(drawn):
        return False
    return all(before[0][:3] == after[0][:3] and before[0][4] == after[0][4]
               for before, after in zip(was, drawn))


def _patch_value(text, lineno, drawn):
    """Rewrite one line's reading, leaving the rest of the line alone.

    The reading is everything from the row's FIRST tab to the end of
    the line, so the label -- or the embedded checkbox standing in for
    one -- is never touched. Destroying and recreating an embedded
    window is what makes the block visibly reflow.

    A shop heading's total is inside that stretch and is rewritten
    with the rest: it is a reading too, and it moves for the same
    reasons.
    """
    (key, _label, _tracked, segments, _box), line, _label_tag, total = drawn
    end = "%d.end" % lineno
    at = text.search(COLUMN_SEP, "%d.0" % lineno, end)
    if at:
        text.delete(at, end)
    _insert_value(text, key, line, total, segments, at="%d.end" % lineno)


def _insert_value(text, key, line, total, segments, at=tk.END):
    """Write a row's total and readings onto the end of its line.

    One place, because the line is written twice -- built whole, and
    patched when only its numbers moved -- and the two drifting apart
    would put a heading's total at a different stop each way.

    **The total goes in FIRST and takes the line's own first tab.** On
    a shop heading both stops are the heading's own, so a heading
    carrying a countdown as well reads name, total, countdown, each at
    a fixed distance from the words rather than from the column.

    Only a total takes the heading's shade and its hover; the segments
    after it are the row's own readings and keep the ordinary ones.
    """
    if total:
        words, state = total
        text.insert(at, COLUMN_SEP + words, line + _head_tags(key, state))
    # **A countdown in a group goes to that group's STOP.** Written
    # after a tab rather than after two spaces, so every deadline in
    # the group starts at one x however long the readings beside them
    # are -- and a row with no reading at all still lands there.
    aligned = any(str(tag).startswith(COUNTDOWN_STOP_PREFIX) for tag in line)
    for index, (words, state) in enumerate(segments):
        if aligned and str(words).startswith(ENDS_IN):
            # TWO tabs where the row has no reading at all: the first
            # takes the reading's stop and the second the group's, so
            # a row that is only a deadline still lines up with the
            # deadlines beside it.
            gap = COLUMN_SEP * (2 if not index else 1)
        else:
            gap = COLUMN_SEP if not index else SEGMENT_GAP
        text.insert(at, gap + words, line + ((state,) if state else ()))


def _head_tags(key, state):
    """The tags a shop heading's own total takes."""
    return ((HEAD_STATE_TAGS.get(state, state),) if state else ()) \
        + (SHOP_TIP_PREFIX + key,)


def _readings(raw, now=None, tracked=None):
    """{row key: (text, alert)} for every row that shows a value.

    One place for all of them, and pure but for the clock, so the whole
    set can be exercised from a snapshot without a window. `now` is
    epoch seconds, defaulting to the real clock.

    A row whose source is missing reads `-` rather than `0`: nothing
    claimed and nothing recorded are different answers.

    `tracked` is a predicate on a shop product id, and only the shop
    HEADINGS use it -- a shop's bill is what its ticked products cost.
    None means everything is ticked, which is also what the tab reads
    before a settings manager exists.
    """
    now = time.time() if now is None else now
    amounts = item_amounts.held(raw)
    expiries = period_items.held(raw.get("inventory") or {}).get(
        MODULE_ITEM, ())

    out = {}

    # Whether today's Activities reward has been taken. See
    # `POINT_FIELD`: a record stamped with an earlier day is one the
    # claim has not rewritten, so today is untouched.
    point = raw.get(POINT_FIELD)
    point = point if isinstance(point, dict) else {}
    day_id, day = point.get("day_id"), point.get("day_point")
    if not _is_count(day_id) or not _is_count(day):
        out["activity"] = _one(NO_DATA, UNKNOWN)
    elif day_id < weekly_reset.day_index(now):
        out["activity"] = _one(ACTIVITY_UNCLAIMED, TODO)
    elif day >= ACTIVITY_FULL:
        out["activity"] = _one(
            ACTIVITY_CLAIMED % (day, ACTIVITY_FULL), DONE)
    else:
        # Claimed, but against fewer than the day's full points -- so
        # more will have come due since.
        out["activity"] = _one(
            ACTIVITY_CLAIMED % (day, ACTIVITY_FULL), TODO)

    # Today's coffee. **The field is a CAPABILITY, so the row inverts
    # it**: `is_coffee_possible` true means one is still going begging.
    block, fresh = _day_block(raw, now)
    # A day that has rolled since the block was written has a coffee
    # waiting whatever the stale flag says.
    possible = None if block is None else (
        block.get("is_coffee_possible") if fresh else True)
    if isinstance(possible, bool):
        out["coffee"] = _one(COFFEE_TODO if possible else COFFEE_DONE,
                         _done(not possible))
    else:
        out["coffee"] = _one(NO_DATA, UNKNOWN)

    # Today's Chaos Delegation. See `DELEGATION_CURRENCY`: an entry in
    # hand is a run still to do, and an empty balance is only a run
    # taken if the balance was written since the day's reset.
    entry = _dig(raw, DELEGATION_PATH)
    entry = entry if isinstance(entry, dict) else {}
    held, stamped = entry.get("amount"), entry.get("last_update")
    if not _is_count(held):
        out["chaos_delegation"] = _one(NO_DATA, UNKNOWN)
    else:
        ran = (held == 0 and _is_count(stamped)
               and stamped >= weekly_reset.last_daily_reset(now))
        out["chaos_delegation"] = _one(DELEGATION_DONE if ran
                                   else DELEGATION_TODO, _done(ran))

    # Communication Passes left today. Not an item and not a currency --
    # `excursions.passes_left` says why that reading is the only one a
    # snapshot allows.
    # A day that has rolled brings the whole allowance back, and
    # the stale count says none of it was spent today.
    left = (excursions.passes_left(raw) if fresh or block is None
            else excursions.DAILY_PASSES)
    out["excursions"] = _one(
        "%s/%d" % (NO_DATA if left is None else left, excursions.DAILY_PASSES),
        UNKNOWN if left is None else _done(left == 0))

    # Both weekly currencies are things to SPEND, so a holding is work
    # left rather than a stock to be pleased about.
    #
    # **Topped up weekly, and lazily.** A record the week has rolled
    # past still carries last week's leftover, so the row shows what
    # the week's rule says to EXPECT, marked as worked out rather
    # than read. See `_weekly_stock`.
    cards, exact = _weekly_stock(raw, CHAOS_CURRENCY, CHAOS_WEEKLY_GRANT,
                                 CHAOS_CAP, now)
    out["chaos_currency"] = _one(
        "%s%d/%d" % ("" if exact else EXPECTED_VALUE, cards, CHAOS_CAP),
        _done(cards == 0))
    reason, exact = _weekly_stock(raw, SORTIE_CURRENCY, SORTIE_WEEKLY_GRANT,
                                  SORTIE_CAP, now)
    out["sortie_currency"] = _one(
        "%s%d/%d" % ("" if exact else EXPECTED_VALUE, reason, SORTIE_CAP),
        _done(reason == 0))

    # The Great Rift's weekly score against the threshold that pays.
    # **Capped in the DISPLAY**, because the figure runs to seven digits
    # and the row is about whether the threshold is cleared. A capped
    # reading carries `GREAT_RIFT_OVER` so it cannot be read as a score
    # that landed exactly on the bar.
    score, target = _great_rift(raw, now)
    if score is None:
        out["seasonal_score"] = _one("%s/%d" % (NO_DATA, target), UNKNOWN)
    else:
        over = GREAT_RIFT_OVER if score > target else ""
        out["seasonal_score"] = _one("%d%s/%d" % (min(score, target), over,
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
        out[key] = _one(words % (len(inside),
                             max(1, math.ceil(edge / divisor)), unit),
                    _done(not inside))

    # The Arkhianon Supply, three ways. A mission's `complete_time` is
    # set when its reward is CLAIMED, so a finished-but-unclaimed
    # mission still reads as work left -- which it is.
    # A DAILY mission is one of the six lowest-numbered, CLAIMED since
    # the day's own reset. See `PASS_DAILY_COUNT`.
    #
    # **A full WEEK finishes the row too.** The dailies exist to feed
    # the week's exp, so once that is capped there is nothing left for
    # them to earn and the day's remainder is not work owed.
    record = _live_pass(raw)
    week_exp = record.get("week_exp")
    # The pass's own `week_id` says which week that EXP belongs to.
    # Nothing zeroes it at the reset, so last week's full 10000 reads
    # as a finished week into a week with nothing done in it.
    if _is_count(week_exp) and not _this_week(record, now):
        week_exp = 0
    week_full = _is_count(week_exp) and week_exp >= PASS_WEEK_EXP_FULL
    # A maxed pass ends the whole ladder: the dailies feed the week and
    # the week feeds the level, so once the level is full there is
    # nothing either of them can still earn. Read before the rows that
    # use it, the same way `week_full` already settles the dailies.
    level = record.get("free_reward_rank")
    season_full = _is_count(level) and level >= PASS_LEVEL_FULL
    missions = raw.get(PASS_MISSION_FIELD)
    if isinstance(missions, dict):
        since = weekly_reset.last_daily_reset(now)
        claimed = sum(1 for res_id, row in missions.items()
                      if _pass_daily_number(res_id)
                      and _is_count(row.get("complete_time"))
                      and row["complete_time"] >= since)
        out["supply_daily"] = _one(
            "%d/%d" % (claimed, PASS_DAILY_COUNT),
            _done(season_full or week_full
                  or claimed >= PASS_DAILY_COUNT))
    else:
        out["supply_daily"] = _one("%s/%d" % (NO_DATA, PASS_DAILY_COUNT), UNKNOWN)

    # The week's EXP and the pass's level, both off the pass's own
    # record. EXP rather than a mission count, because only one of the
    # twelve weekly missions has been identified.
    if _is_count(week_exp):
        out["supply_weekly"] = _one(
            "%d/%d" % (min(week_exp, PASS_WEEK_EXP_FULL), PASS_WEEK_EXP_FULL),
            _done(season_full or week_exp >= PASS_WEEK_EXP_FULL))
    else:
        out["supply_weekly"] = _one("%s/%d" % (NO_DATA, PASS_WEEK_EXP_FULL),
                                UNKNOWN)
    if _is_count(level):
        out["supply_season"] = _one("%d/%d" % (min(level, PASS_LEVEL_FULL),
                                           PASS_LEVEL_FULL),
                                _done(level >= PASS_LEVEL_FULL))
    else:
        out["supply_season"] = _one("%s/%d" % (NO_DATA, PASS_LEVEL_FULL), UNKNOWN)

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
        out["simulation"] = _one("%s/%d" % (NO_DATA, SIMULATION_RUNS), UNKNOWN)
    else:
        out["simulation"] = _one("%d/%d" % (left, SIMULATION_RUNS),
                             _done(left == 0))

    # The Basin of Hyperspace: objectives done, out of the season's own
    # total. Nothing states the total, so it is how many the season
    # holds -- which is the same figure the game shows.
    # The Chaos Matrix's reward track, in levels claimed.
    matrix = raw.get(MATRIX_FIELD)
    claimed = matrix.get("reward_level") if isinstance(matrix, dict) else None
    if not _is_count(claimed):
        out["matrix"] = _one(NO_DATA, UNKNOWN)
    else:
        out["matrix"] = _one("%d/%d" % (claimed, MATRIX_LEVELS),
                             _done(claimed >= MATRIX_LEVELS))

    # The Full-Scale Offensive, scored in STARS. Each of its stages
    # carries a `star_count` out of three and its own `best_score`; the
    # screen's total score is those scores summed, which is a figure
    # this row has no room for and no deadline to measure it against.
    stages = raw.get(OFFENSIVE_FIELD)
    stages = [row for row in (stages or {}).values()
              if isinstance(row, dict)] if isinstance(stages, dict) else []
    if not stages:
        out["offensive"] = _one(NO_DATA, UNKNOWN)
    else:
        stars = sum(row.get("star_count") or 0 for row in stages)
        most = OFFENSIVE_STARS * len(stages)
        out["offensive"] = _one("%d/%d" % (stars, most),
                                _done(stars >= most))

    # **Green means nothing left to CLAIM**, not nothing left to do.
    # The objectives can all be scored with every star reward still
    # sitting there, which is a finished-looking row and a trip to the
    # game still owed.
    done, total, claimed = _basin(raw, now)
    if total is None:
        out["basin"] = _one(NO_DATA, UNKNOWN)
    else:
        out["basin"] = _one("%d/%d" % (done, total),
                            _done(done >= total and claimed >= done))

    # The shops, one sub-row per product. `-` where the field cannot be
    # read honestly -- see `shop_stock.remaining`.
    # The Galactic Disaster's weekly chaos progress, against a ceiling
    # the wire does not carry.
    score = _chaos_progress(raw, now)
    if score is None:
        out["chaos_progress"] = _one("%s/%d" % (NO_DATA, CHAOS_PROGRESS_FULL),
                                     UNKNOWN)
    else:
        over = GREAT_RIFT_OVER if score > CHAOS_PROGRESS_FULL else ""
        out["chaos_progress"] = _one(
            "%d%s/%d" % (min(score, CHAOS_PROGRESS_FULL), over,
                         CHAOS_PROGRESS_FULL),
            _done(score >= CHAOS_PROGRESS_FULL))

    # Every live event: what is left to claim of it, and how long it
    # has. See `EVENT_MISSIONS` -- an event nobody has mapped shows the
    # deadline alone.
    live_events = {}
    for group in EVENT_GROUPS:
        for name, window in schedules.all_live(group, raw, now):
            live_events[name] = (group, window)
    for key, _label, _widest in event_rows(raw, now):
        # The ID, not the label: the label drops the common
        # prefix and every reader looks the event up by its id.
        name = key[len(EVENT_KEY_PREFIX):]
        group, window = live_events.get(name, (None, {}))
        seconds = max(0, window.get("end_time", now) - now)
        reader = EVENT_READERS.get(group)
        segments = list(reader(raw, name, window, now)) if reader else []
        segments.append((ENDS_IN + schedules.countdown(seconds),
                         _countdown_state(seconds)))
        out[key] = segments

    _add_countdowns(out, raw, now)

    for key, product_id, define in _shop_rows(raw):
        stock, limit = shop_stock.remaining(product_id, define, raw, now)
        if limit is None:
            # No cap: it can always be bought, so nothing counts down
            # and nothing is finished. Such a product gets no ROW
            # either -- this is only here for a reading asked of one.
            continue
        elif stock is None:
            out[key] = _one("%s/%d" % (NO_DATA, limit), UNKNOWN)
        else:
            out[key] = _one("%d/%d" % (stock, limit), _done(stock == 0))

    _add_shop_totals(out, raw, amounts, tracked, now)
    return out


def _add_shop_totals(out, raw, amounts, tracked, now):
    """Fold each shop heading's own reading into `out`.

    `<currency on hand>/<what clearing the ticked products costs>`, so
    one glance says whether a shop can be finished this period.

    A shop with no single currency to its name has no total -- see
    `shop_currency`, which is where that is decided.

    **Only the TICKED products are billed.** The row answers "can I
    clear what I care about", and an untracked product is one the user
    has said they do not.

    A product whose remaining count the snapshot cannot give is left
    out of the bill, which then understates: such a total carries
    `UNKNOWN_MORE` and stays red, affordable-looking or not.
    """
    for title, _fixed, shops, _events in COLUMNS:
        period = PERIOD_BY_COLUMN.get(title)
        for shop in shops if period else ():
            bill, unknown = 0, False
            for product_id, define in shop_products(shop, period, raw):
                if tracked is not None and not tracked(product_id):
                    continue
                left, _cap = shop_stock.remaining(
                    product_id, define, raw, now)
                price = define.get("price_count")
                if left is None or not _is_count(price):
                    unknown = True
                    continue
                bill += left * price
            currency = shop_currency(shop, period, raw)
            if currency is None:
                continue
            held = amounts.get(currency)
            held = held if _is_count(held) else 0
            out[SHOP_TOTAL_PREFIX + shop_head_key(shop, period)] = _one(
                "%d/%d%s" % (held, bill, UNKNOWN_MORE if unknown else ""),
                _done(not unknown and held >= bill))


def currency_earned(raw, res_id):
    """`(what has ever been earned of it, how that was arrived at)`.

    Two sources, and the first is simply read:

    * a currency in `characters.currencies` states its own lifetime
      gained as `total_amount`;
    * an ordinary inventory item states none, and the SHOPS account
      for it -- what is held plus everything ever bought with it, which
      is `shop_list[*].total_count` times each product's price.

    **The second is checked against the first.** For the five
    currencies carrying a `total_amount`, the shop sum reproduces it
    exactly at every reading of four of them, and within 300 in three
    readings of thirty-six for the fifth -- a capture that caught a
    purchase between the two payloads. So it is a reconstruction rather
    than a reading, and the ledger records which it got.

    `(None, None)` where the snapshot carries the id nowhere, which is
    not zero: a currency never held and one a capture has not reached
    look the same from here, and recording a zero for either would put
    a false floor in the ledger.
    """
    doc = ((raw or {}).get("characters") or {}).get("currencies") or {}
    doc = doc.get(str(res_id))
    if isinstance(doc, dict) and _is_count(doc.get("total_amount")):
        return doc["total_amount"], checklist_manager.FROM_WIRE
    held = item_amounts.held(raw).get(res_id)
    if not _is_count(held):
        return None, None
    bought = shop_stock.stock(raw)
    if not bought:
        # No `shop_list` is not "nothing bought": it is the payload not
        # having arrived. Recording the holding alone would put a total
        # in the ledger that every later reading has to climb back over.
        return None, None
    spent = 0
    for _category, defines in shop_stock.definitions(raw).items():
        for product_id, define in (defines or {}).items():
            if (not isinstance(define, dict)
                    or define.get("price_link_item_id") != res_id):
                continue
            price = define.get("price_count")
            count = (bought.get(product_id) or {}).get("total_count")
            if _is_count(price) and _is_count(count):
                spent += price * count
    return held + spent, checklist_manager.FROM_SHOPS


def currency_rate(points, window):
    """`(earned per day, the days that covers)` over the last `window`.

    Points are `(day, lifetime total)` oldest first, so a rate is one
    subtraction across the pair that brackets the window -- no sum, and
    nothing to say about what was spent in between.

    **The window is what is ASKED FOR, and what comes back is what was
    available.** The far end is the recorded day NEAREST the one the
    window names, on either side of it -- so a ledger holding a seed at
    the account's creation and a week of recent days answers a
    four-week question with the week it has, rather than with the three
    hundred days the seed would drag in. The days actually covered come
    back beside the rate, and every caller states them.
    """
    if len(points) < 2:
        return None, 0
    last_day, last_total = points[-1]
    want = last_day - window
    first = min(points[:-1], key=lambda p: abs(p[0] - want))
    days = last_day - first[0]
    if days <= 0:
        return None, 0
    return (last_total - first[1]) / float(days), days


def shop_full_cost(shop, period, raw, tracked=None):
    """What a full period of one shop's ticked products costs.

    Every ticked product's cap times its price, whether or not any of
    it has been bought. **Distinct from the heading's own reading**,
    which is what finishing the period from HERE costs: this one does
    not move as the shelves empty, which is what makes it comparable
    against a rate.
    """
    total = 0
    for product_id, define in shop_products(shop, period, raw):
        if tracked is not None and not tracked(product_id):
            continue
        cap, price = define.get("limit_count"), define.get("price_count")
        if _is_count(cap) and _is_count(price):
            total += cap * price
    return total


def shop_rates(points, word, days, name):
    """A shop heading tip's two RATE lines, or `()`.

    `(label, value)` a row, which is what the tip draws as two aligned
    columns. **Both are per ROTATION of this shop** -- an average
    earned per day, times the days the shop's period runs -- and they
    differ in how far back that per-day figure was measured:
    `SHOP_RATE_ROLL` of the shop's own periods, and `SHOP_RATE_YEAR`
    days, each reaching for the recorded day nearest the one it wants.

    **ONE line where both windows land on the same days**, and it is
    the LONG one. A young ledger cannot tell recent from long-run -- it
    holds one stretch of record and both readings are of that stretch
    -- so printing two would present one measurement as two that agree,
    and calling that one `recent` would name a window it did not use.
    The second line appears when there is something for it to say.

    Nothing at all until the ledger spans `SHOP_RATE_FLOOR` days. A tip
    has to be worth stopping for, and a rate off two days is which
    content ran on them.
    """
    rows = []
    for label, window in ((RATE_RECENT_LABEL, days * SHOP_RATE_ROLL),
                          (RATE_LONG_LABEL, SHOP_RATE_YEAR)):
        rate, covered = currency_rate(points, window)
        if rate is None or covered < SHOP_RATE_FLOOR:
            continue
        rows.append((label % word,
                     RATE_VALUE % ("%d" % round(rate * days), name),
                     covered))
    if len(rows) == 2 and rows[0][2] == rows[1][2]:
        rows = rows[1:]
    return tuple((label, value) for label, value, _covered in rows)


def _period_left(title, raw, now):
    """(seconds left of this column's period, the period's length).

    A month is not a fixed length, so its bounds are the wire's own
    `month_start` and `month_end` -- and DERIVED where a snapshot
    carries neither, which is every fresh install until the first
    capture. The two agree: see `weekly_reset.month_bounds`.
    """
    length = PERIOD_LENGTHS.get(title)
    if title == "Daily":
        return weekly_reset.last_daily_reset(now) + length - now, length
    if title == "Weekly":
        return weekly_reset.next_reset(now) - now, length
    start = (raw or {}).get(shop_stock.MONTH_START_FIELD)
    end = (raw or {}).get("month_end")
    if not _is_count(start) or not _is_count(end) or end <= start:
        start, end = weekly_reset.month_bounds(now)
    return end - now, end - start


def _period_band(left, length):
    """Which quarter of its period a countdown is in."""
    share = max(0.0, left) / float(length) if length else 0.0
    for above, band in HEADING_BANDS:
        if share > above:
            return band
    return HEADING_BANDS[-1][1]


def _period_words(left):
    """`18h left` under a day, `5d left` above it. Rounded DOWN."""
    left = max(0, int(left))
    if left >= 24 * 3600:
        return "%dd%s" % (left // (24 * 3600), HEADING_LEFT)
    return "%dh%s" % (left // 3600, HEADING_LEFT)


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


def _basin_claimed(raw, season):
    """How many of a Basin season's star rewards have been taken.

    `reward_entities` carries one row per season and only once
    something has been claimed from it, so an absent row is none.
    """
    for row in (raw or {}).get(BASIN_REWARD_FIELD) or []:
        if isinstance(row, dict) and row.get("res_id") == season:
            count = row.get("count")
            return count if _is_count(count) else 0
    return 0


def _basin(raw, now):
    """(objectives done this season, objectives in a season, rewards
    claimed of them), or (0, None, 0).

    **A season's own row count is not its size.** The game issues an
    objective lazily, so the live season carries only the ones it has
    got to -- fifteen rows, all fifteen scored, for a season of
    twenty-six. Read straight off, that is a finished season.

    So the numerator is the live season's and the denominator is the
    largest any season has reached, which a completed one states
    exactly. Both move to the season's real size as the rows arrive.
    """
    seasons = raw.get(BASIN_FIELD)
    if not isinstance(seasons, dict) or not seasons:
        return 0, None, 0
    sized = {name: rows for name, rows in seasons.items()
             if isinstance(rows, dict) and rows}
    if not sized:
        return 0, None, 0
    total = max(len(rows) for rows in sized.values())
    name, _window = schedules.current(COUNTDOWNS["basin"], raw, now)
    if name not in sized:
        # No schedule for it: the last season the account has rows for.
        name = sorted(sized)[-1]
    done = sum(1 for row in sized[name].values()
               if isinstance(row, dict) and row.get("score"))
    return done, total, _basin_claimed(raw, name)


def _one(text, state):
    """One reading, as the single segment a row usually has."""
    return [(text, state)]


def _countdown_state(seconds):
    """What colour a countdown is drawn in, by how long is left."""
    hours = seconds / 3600.0
    for under, state in COUNTDOWN_STATES:
        if under is None or hours < under:
            return state
    return LATER


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
        seconds = schedules.remaining(group, raw, now)
        left = schedules.countdown(seconds)
        if not left:
            out.setdefault(key, _one(NO_DATA, UNKNOWN))
            continue
        # The dash is a stand-in for a reading, not a reading -- a row
        # whose only other segment is one drops it rather than saying
        # "nothing, ends in three days".
        rest = [pair for pair in out.get(key, ()) if pair[0] != NO_DATA]
        out[key] = rest + [(ENDS_IN + left, _countdown_state(seconds))]


def _chaos_progress(raw, now):
    """The live season's weekly chaos score, or None.

    Every season the account has played keeps a row, so the live one is
    the latest `week_id` -- past seasons sit at their own full 8000.

    That same stamp says whether the score is THIS week's. It is not
    zeroed at the reset, so a row left over from last week reads a full
    8000 into a week nothing has been cleared in -- see `_this_week`.
    """
    rows = raw.get(DISASTER_FIELD)
    live = None
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict) or not _is_count(
                row.get("week_clear_score")):
            continue
        week = row.get("week_id") or 0
        if live is None or week > live[0]:
            live = (week, row)
    if live is None:
        return None
    row = live[1]
    return row["week_clear_score"] if _this_week(row, now) else 0


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


def _great_rift(raw, now):
    """(this week's score, the threshold that pays it out).

    The standings nest season -> rank slot -> record, and every season
    the account has played keeps its row -- so the live one is picked
    by the LATEST `score_week_id`, not by the biggest score. Past
    seasons carry higher totals than the current week does, and their
    thresholds differ too: the older ones ask 500000 where this one
    asks 300000.

    **A row is not zeroed at the reset**, so the latest one can still
    be last week's: its `score_week_id` is what says which, and a stale
    one scores nothing this week. See `_this_week`.

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
    score = row["week_total_score"] if _this_week(
        row, now, GREAT_RIFT_WEEK_STAMP) else 0
    return score, (target if _is_count(target) else GREAT_RIFT_TARGET)


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


def _heads_a_block(key):
    """Whether a row introduces a block of rows below it.

    Every shop's heading, and the Events one. They read as titles
    rather than as tasks, so they take the extra space above that
    separates one block from the rows before it.
    """
    return key.startswith(SHOP_HEAD_PREFIX) or key == EVENT_KEY_PREFIX


def _crosses_a_block(above, key):
    """Whether the gap between two rows is a block's own edge.

    True where `key` opens a block, and true where `above` closed one
    -- a shop's last product followed by anything that is not another
    of its products. **Once either way**: charging the pad on both
    sides of a boundary doubles it wherever two blocks touch, which on
    this tab is every shop but the first in its column.
    """
    if above is None:
        return False                # the top of a column crosses nothing
    return _heads_a_block(key) or (_is_shop(above) and not _is_shop(key))


def _row_tags(key, above, boxed=()):
    """The line tags one row takes, beyond its own colours.

    **Exactly one pitch tag per line.** Tk resolves two tags setting
    the same option by tag PRIORITY rather than by adding them, so
    stacking a pad on top of `row` would give a gap that depends on
    the order the tags happened to be created in.

    `above` is the key of the row OVER this one, or None at the top of
    the column. The block pad rides the row below a boundary, so that
    is what says whether this row pays it.

    `boxed` is the keys of the rows carrying a checkbox at the END of
    the line -- the ones asking `Finished?`. Such a row stands taller
    than its words, so it and the row under it both sit closer.

    A shop heading also carries the tab stop its own total sits at --
    see `SHOP_STOP_PREFIX`. That tag holds no pitch, and the pitch tag
    stays first: callers read `[0]` for it.
    """
    if _is_shop(key):
        # The first product of a shop sits under WORDS rather than
        # under another box, which the same `spacing1` reads two wider
        # under. See `CHECKBOX_UNDER_HEAD`.
        return ("boxheadrow" if str(above or "").startswith(SHOP_HEAD_PREFIX)
                else "boxrow",)
    # **A boundary crossed from a checkbox row pays more.** The
    # widget's ink sits lower in its line than a glyph's, so the same
    # `spacing1` reads two tighter under one. See `BLOCK_PAD_FROM_BOX`.
    if _crosses_a_block(above, key):
        pitch = "boxblockrow" if _is_shop(above) else "blockrow"
    else:
        # A row asking `Finished?` carries a checkbox at the end of it
        # and stands taller than its words, which widens the gap on
        # both sides of it. See `BOX_ROW_SLACK`.
        slack = (key in boxed) + (above in boxed)
        pitch = ("row", "row_beside_box", "row_between_boxes")[slack]
    if key.startswith(SHOP_HEAD_PREFIX):
        return (pitch, SHOP_STOP_PREFIX + key)
    # The stop its countdown lines up at, where it is in a group that
    # has one. See `countdown_group`.
    group = countdown_group(key)
    if group is not None:
        return (pitch, COUNTDOWN_STOP_PREFIX + group)
    return (pitch,)


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
