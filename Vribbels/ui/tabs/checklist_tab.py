"""Checklist tab: what resets, and how often.

Four headed columns, one per reset period, each listing the things that
come back on it, with what is left to do beside it. Green is nothing
left, red is something, and a dash is a question the snapshot cannot
answer -- which is a THIRD state and not a zero.

Each row reads its own field, and they have almost nothing in common:
a claim stamp, a currency balance, a daily counter, a login streak, a
set of puzzle pieces. `_readings` is where every one of them is, keyed
by the row rather than by its words, and `docs/wire_hunt.md` records
what each field means and which readings are exact.

**A reading that can only be a FLOOR never goes green.** The game
issues a mission row when it issues the mission, so counting the rows
in hand understates an event that has not finished handing them out --
and a checklist saying done when it is not is worse than one saying
nothing.

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
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

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
# a `$hop`, and it takes its own colour.
#
# (what the heading contains, the palette key). These colour the
# LABEL; a row's reading keeps the red/green that says what is left.
SHOP_LABEL_COLOURS = (
    ("Traveler", "yellow"),
    ("Nono's Shop", "blue_light"),
    ("$hop", "purple"),
)

# ---- the two specimen rows, TEMPORARY ------------------------------
#
# One line of prose in each of the two faces the app sets 11pt text in,
# full width and unwrapped, so the maintainer can compare them side by
# side on a real window. **Delete this block and its three constants
# when the comparison is done.**
SPECIMEN_ROWS = True
SPECIMEN_FONTS = (("Segoe UI Variable Small", 11), ("Segoe UI", 11))
SPECIMEN_TEXT = (
    "Lorem ipsum dolor sit amet consectetur adipiscing elit. Animi "
    "deleniti at consequat id consectetur eiusmod non est ut accusamus "
    "quidem dolore. Tempore ut corrupti id odio in tempore consectetur. "
    "Soluta in est omnis et enim. Culpa tempore occaecat nam "
    "exercitation exercitation dignissimos repellendus accusamus."
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
# part of it -- and dropped to sit on the heading's own baseline, a
# 14pt box being taller than a 9pt one.
HEADING_COUNTDOWN_FONT = ("Segoe UI", 9)
HEADING_COUNTDOWN_GAP = 6   # spacing: heading ↔ element -- heading, label ↔
HEADING_COUNTDOWN_DROP = 3  # spacing: heading ↔ element -- heading, label ↕


# Which `event_schedules` group dates each row, and so what its
# countdown counts down to. **The lengths used to be guesses in the
# labels** -- `(21 days)`, `(84? days)` -- and the wire carries the
# real window for every one of them.
COUNTDOWNS = {
    "basin": "HYPER_SPACE_SEASON",
    "matrix": "ZERO_REWARD_LIST",
    "offensive": "REMNANTS_BOSS_PENALTY",
    "supply_season": "SEASON_PASS",
    "galactic_disaster": "DISASTER_SEASON",
    "shophead:shop_assault/none": "ASSAULT_SCHEDULE",
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
        if product_id in HIDDEN_PRODUCTS:
            continue
        limit = define.get("limit_count")
        out.append((SHOP_KEY_PREFIX + product_id,
                    product_label(define),
                    "%d/%d" % (limit, limit)))
    return tuple(out)


def event_rows(raw, now=None):
    """`(key, id, widest)` for every event running now, soonest first.

    Read straight off `event_schedules`: an event the game adds turns
    up with no edit, and one that ends drops out. The ORDER is by
    deadline, which is what a checklist is about.
    """
    now = time.time() if now is None else now
    found = []
    for group in EVENT_GROUPS:
        # EVERY instance, not one per group: three events overlapped
        # under `EVENT_SCHEDULE` in one capture.
        for name, window in schedules.all_live(group, raw, now):
            found.append((window["end_time"], name))
    return tuple((EVENT_KEY_PREFIX + name, event_label(name),
                  with_countdown(EVENT_CLAIMED))
                 for _end, name in sorted(found))


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


def event_label(name):
    """What an event row is called: its id without the common prefix.

    Every id starts `event_`, so the word says nothing and costs a
    column's width. An id that does not is left alone.
    """
    return name[len(EVENT_ID_PREFIX):] if name.startswith(
        EVENT_ID_PREFIX) else name


def _event_attendance(raw, name, window, _now):
    """[(words, state)] for a login-streak event's rewards taken."""
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
    taken = row.get("received_days")
    if not _is_count(taken):
        return []
    return [("%d/%d" % (taken, ATTENDANCE_DAYS),
             _done(taken >= ATTENDANCE_DAYS))]


def _event_overclock(raw, name, _window, now):
    """[(words, state)] for an Overclock event's doubled runs LEFT.

    Never green: a run not taken today is work left, and one taken is
    a bonus spent rather than a task finished.
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
            used = row["count"]
    left = max(0, OVERCLOCK_USES - used)
    return [("%d/%d" % (left, OVERCLOCK_USES),
             TODO if left else WARN)]


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


def _event_missions(raw, name, _window, _now):
    """[(words, state)] for an event scored by its own missions."""
    return _event_progress(raw, name)


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

    **So this never reads green.** Twice it called an event finished
    that was not -- a summer event with a wave unissued, and a daily
    one on its first day -- and a checklist that says done when it is
    not is worse than one that says nothing. The reading is marked
    `FLOOR` for that reason, and the tab colours it orange once it has
    stood still long enough to mean something.
    """
    missions = (raw or {}).get(PASS_MISSION_FIELD)
    if not isinstance(missions, dict):
        return []
    override = EVENT_MISSIONS.get(name)
    if override:
        rows = [row for res_id, row in missions.items()
                if str(res_id).startswith(override) and isinstance(row, dict)]
    else:
        want = _event_key(name)
        rows = [row for res_id, row in missions.items()
                if isinstance(row, dict) and _under(_event_key(res_id), want)]
    if not rows:
        return []
    claimed = sum(1 for row in rows if row.get("complete_time"))
    return [("%d/%d" % (claimed, len(rows)), FLOOR)]


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
EVENT_NOISE_WORDS = ("schedule", "mission")

# Events the rule cannot reach, as {event id: mission id prefix}. Empty
# because nothing has needed one; an event whose missions are named
# unlike its schedule goes here, and one that is simply unmapped shows
# its deadline and no tally.
EVENT_MISSIONS = {}

# **Progress is read per GROUP, not per event.** Each kind of event
# keeps its state somewhere else entirely -- missions, a login streak,
# a daily counter -- so what an event row can say is decided by which
# group it came from, and a new event in a known group needs no edit.
# `EVENT_READERS` below maps the group to the function that reads it.

# A login-streak event: `attendance_entities` counts the days shown up
# and the days whose reward was taken. Its rows are numbered nothing
# like the schedule's, so the row is the FIRST one started after the
# event was -- the streak begins on the first login into it.
ATTENDANCE_FIELD = "attendance_entities"
ATTENDANCE_DAYS = 7

# An Overclock event doubles the day's first two Simulation rewards.
# `overclock_entities` counts what has been taken, daily, and a row
# exists only once one has been -- so no row is a full two.
#
# **The cap is not on the wire.** Two is this event's, stated by the
# game's own wording; older Overclock events ran at six, and their
# rows still read `count` against whatever theirs was.
OVERCLOCK_FIELD = "overclock_entities"
OVERCLOCK_USES = 2

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

# What an event with every reward taken reads instead of a tally.
EVENT_CLAIMED = "All Claimed"


# The columns, as a skeleton. Each is `(heading, rows, shops, events)`:
# `rows` are the fixed ones, `shops` names the shop screens whose
# products are folded in under a heading each, and `events` is a
# trailing heading of every live event (or None for no such block).
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
        ("activity", "Activity (Dailies)", "100/100 Claimed"),
        ("supply_daily", "Arkhianon Supply", "3/3"),
        ("excursions", "Excursions", "5/5"),
        ("chaos_delegation", "Chaos Delegation", "Go run!"),
    ), (), None),
    ("Weekly", (
        ("supply_weekly", "Arkhianon Supply", "10000/10000"),
        ("simulation", "Simulation Challenges", "3/3"),
        ("chaos_currency", "Chaos Currency", "99"),
        ("modules_soon", "Delegation Module", "99 expiring within 24h!"),
        ("modules_week", "Delegation Module", "99 expiring within 7 days"),
        ("sortie_currency", "Sortie Currency", "99/9"),
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
            head = SHOP_HEAD_PREFIX + "/".join(shop)
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


# The rows' face. The headings use the shared helper's own.
ROW_FONT = ("Segoe UI", 9)

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
ACTIVITY_UNCLAIMED = "Unclaimed"
ACTIVITY_CLAIMED = "All Claimed"
ACTIVITY_PARTIAL = "%d/%d Claimed"

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
        if SPECIMEN_ROWS:
            self._build_specimens()

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
            drawn = tuple(self._line(key, label, readings)
                          for key, label, _w in rows)
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

    def _build_specimens(self):
        """The two prose rows at the bottom. See SPECIMEN_ROWS."""
        # spacing: out of scope -- two specimen rows, for comparing one size in two faces
        block = ttk.Frame(self.frame)
        block.pack(side=tk.BOTTOM, fill=tk.X, anchor=tk.W,
                   padx=px(4), pady=px((0, 4)))
        for face in SPECIMEN_FONTS:
            # `wraplength=0` is Tk's own "do not wrap", and `anchor=W`
            # keeps the line at the left edge of a frame that fills.
            ttk.Label(block, text=SPECIMEN_TEXT, font=face,
                      wraplength=0, anchor=tk.W,
                      justify=tk.LEFT).pack(fill=tk.X, anchor=tk.W)

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
        # A floor draws red like any other unfinished row; one that
        # has stood at its ceiling for two days draws orange. See
        # `FLOOR`.
        text.tag_configure(FLOOR, foreground=self.colors["red"])
        text.tag_configure(STALE_FLOOR,
                           foreground=self.colors["orange"])
        text.tag_configure(MUTED, foreground=self.colors["fg_dim"])
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
        readings = self._settle_floors(_readings(raw))
        # A rebuilt column is filled inside the rebuild, before it is
        # shown; this fills the ones that were left standing.
        self._rebuild_columns(raw, readings)
        for title, (text, rows) in self.column_texts.items():
            self._fill(title, text, rows, readings)
        self._fill_period_headings(raw)

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
        with `window_create`. The widget goes in at the line's start,
        so the line's own `lmargin1` indents the checkbox itself and
        its left edge lands where an ordinary row's words do.
        """
        drawn = tuple(self._line(key, label, readings) for key, label, _w
                      in rows)
        was = self._rendered.get(title)
        if drawn == was:
            return
        self._rendered[title] = drawn
        if _same_rows(was, drawn):
            text.config(state=tk.NORMAL)
            for index, (before, after) in enumerate(zip(was, drawn)):
                if before != after:
                    _patch_value(text, index + 1, after)
            text.config(state=tk.DISABLED)
            return
        for box in self._boxes.pop(title, ()):
            box.destroy()
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        for index, ((key, label, _tracked, segments), line,
                    label_tag) in enumerate(drawn):
            if index:
                text.insert(tk.END, LINE_SEP, line)
            if _is_shop(key):
                head = segments[0][1] if segments else UNKNOWN
                text.window_create(tk.END, window=self._checkbox(
                    title, text, key, label, head))
            else:
                text.insert(tk.END, label, line + label_tag)
            for at, (words, state) in enumerate(segments):
                text.insert(tk.END, (COLUMN_SEP if not at else SEGMENT_GAP)
                            + words, line + ((state,) if state else ()))
        text.config(state=tk.DISABLED)

    def _line(self, key, label, readings):
        """One row's drawn form: its words, its readings, its tags.

        Everything that decides what the line LOOKS like, and nothing
        else, so two of these comparing equal means the column can be
        left alone. `tracked` is carried even though it shows only
        through the segment colours: it also colours the CHECKBOX, and
        a value patch does not repaint that.
        """
        tracked = not _is_shop(key) or self._tracked(_product_of(key))
        segments = tuple(readings.get(key) or ())
        if not tracked:
            # An untracked product says so in its colour: every segment
            # greys, red and green being about work left and a product
            # nobody tracks having none.
            segments = tuple((words, MUTED) for words, _s in segments)
        line = ("row", "indent") if _is_shop(key) else ("row",)
        return (key, label, tracked, segments), line, _label_tag(key, label)

    def _checkbox(self, title, parent, key, label, state):
        """One shop product's checkbox, kept alive on the tab.

        Held in `_boxes` under its own column because a Text does not
        own an embedded window: dropping the reference leaves the
        widget parented and undestroyed on the next rewrite.
        """
        product_id = _product_of(key)
        variable = tk.BooleanVar(value=self._tracked(product_id))
        box = make_checkbox(
            parent, self.colors, text=label, variable=variable,
            compact=True,
            fg=self.colors["fg_dim"] if state is MUTED else None,
            command=lambda p=product_id, v=variable: self._toggle(p, v))
        self._boxes.setdefault(title, []).append(box)
        return box



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


def _at_ceiling(words):
    """Whether an `n/m` reading has n equal to m."""
    parts = str(words).split("/")
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
    return all(before[0][:3] == after[0][:3]
               for before, after in zip(was, drawn))


def _patch_value(text, lineno, drawn):
    """Rewrite one line's reading, leaving the rest of the line alone.

    The reading is everything from the row's tab to the end of the
    line, so the label -- or the embedded checkbox standing in for one
    -- is never touched. Destroying and recreating an embedded window
    is what makes the block visibly reflow.
    """
    (_key, _label, _tracked, segments), line, _label_tag = drawn
    end = "%d.end" % lineno
    at = text.search(COLUMN_SEP, "%d.0" % lineno, end)
    if at:
        text.delete(at, end)
    for index, (words, state) in enumerate(segments):
        text.insert(end, (COLUMN_SEP if not index else SEGMENT_GAP) + words,
                    line + ((state,) if state else ()))


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
        out["activity"] = _one(ACTIVITY_CLAIMED, DONE)
    else:
        # Claimed, but against fewer than the day's full points -- so
        # more will have come due since.
        out["activity"] = _one(ACTIVITY_PARTIAL % (day, ACTIVITY_FULL), TODO)

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
    cards = amounts.get(CHAOS_CURRENCY, 0)
    out["chaos_currency"] = _one("%d" % cards, _done(cards == 0))
    reason = amounts.get(SORTIE_CURRENCY, 0)
    out["sortie_currency"] = _one("%d/%d" % (reason, SORTIE_CAP),
                              _done(reason == 0))

    # The Great Rift's weekly score against the threshold that pays.
    # **Capped in the DISPLAY**, because the figure runs to seven digits
    # and the row is about whether the threshold is cleared. A capped
    # reading carries `GREAT_RIFT_OVER` so it cannot be read as a score
    # that landed exactly on the bar.
    score, target = _great_rift(raw)
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
    week_full = _is_count(week_exp) and week_exp >= PASS_WEEK_EXP_FULL
    missions = raw.get(PASS_MISSION_FIELD)
    if isinstance(missions, dict):
        since = weekly_reset.last_daily_reset(now)
        claimed = sum(1 for res_id, row in missions.items()
                      if _pass_daily_number(res_id)
                      and _is_count(row.get("complete_time"))
                      and row["complete_time"] >= since)
        out["supply_daily"] = _one(
            "%d/%d" % (claimed, PASS_DAILY_COUNT),
            _done(week_full or claimed >= PASS_DAILY_COUNT))
    else:
        out["supply_daily"] = _one("%s/%d" % (NO_DATA, PASS_DAILY_COUNT), UNKNOWN)

    # The week's EXP and the pass's level, both off the pass's own
    # record. EXP rather than a mission count, because only one of the
    # twelve weekly missions has been identified.
    if _is_count(week_exp):
        out["supply_weekly"] = _one(
            "%d/%d" % (min(week_exp, PASS_WEEK_EXP_FULL), PASS_WEEK_EXP_FULL),
            _done(week_exp >= PASS_WEEK_EXP_FULL))
    else:
        out["supply_weekly"] = _one("%s/%d" % (NO_DATA, PASS_WEEK_EXP_FULL),
                                UNKNOWN)
    level = record.get("free_reward_rank")
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
    score = _chaos_progress(raw)
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
    return out


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


def _chaos_progress(raw):
    """The live season's weekly chaos score, or None.

    Every season the account has played keeps a row, so the live one is
    the latest `week_id` -- past seasons sit at their own full 8000.
    """
    rows = raw.get(DISASTER_FIELD)
    live = None
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict) or not _is_count(
                row.get("week_clear_score")):
            continue
        week = row.get("week_id") or 0
        if live is None or week > live[0]:
            live = (week, row["week_clear_score"])
    return live[1] if live else None


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
