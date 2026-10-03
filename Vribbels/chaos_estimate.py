"""What a Galactic Disaster season's Chaos runs pay, for the Checklist's
season estimate: the figures the program ships with, and when a
player's own recorded runs take their place.

**A run's take is set, but for its marked fights.** `docs/chaos_runs.py`
measures both halves off every run the capture records:

- each BOSS floor pays a set amount, and the amounts belong to the
  season PART: season 4 paid 172 on floors 17 and 34 in part 2, and 180
  on each plus 60 on floor 37 in part 3;
- each MARKED fight pays a set amount -- the Rare Species 60, the Aether
  Eater 90 -- and only how many a run meets is chance.

So a season pays its Chaos, at `R` runs a day,

    R * (sum over parts of bosses(part) * days(part)
         + marks per run * days of the whole season)

**The player's own runs can overrule the shipped figures**, on rules
that trust the shipped ones less the longer the program goes without an
update, counted in whole seasons (`staleness`):

1. A set amount the player saw BELOW the shipped one is ignored: a lower
   Chaos level pays less, and the estimate is for level 8 and up. One
   ABOVE it replaces it -- the mean of every payout at or above the
   shipped amount, on that floor in that part.
2. Once a whole season has run since the release, what the player saw
   the season before counts as well as this season's.
3. Once two have, a lower payout counts too, the shipped amount being
   the likelier one out of date -- unless the highest payout makes up
   `TOP_SHARE` of them, when it alone stands and the rest are taken for
   lower-level runs.
4. The marked fights a run meets are the player's own count only once
   two whole seasons have run since the release AND the player has
   `RATE_RUNS` whole runs since it, none inside a `RATE_EVENTS` window.

A mark's amount follows the bosses' rules, over the whole season rather
than a part. A part never measured borrows the nearest measured part --
the one before it, else the one after.

**A lost run counts as a whole one** when a boss had already paid and
no non-boss fight was left on its map: every mark it could meet, it met.
What it would have paid besides is `missed`.

**Only the live season's own Chaos counts** (`is_current`). A past
season's Chaos pays the live currency too, at lower amounts -- 135 a
boss and 45 a Rare Species in the past ones captured, against 180 and
60 -- and the estimate is of the live one.

No Tk: this takes plain data, and `docs/chaos_runs.py` reads it too.
"""

import collections
import datetime

from version import RELEASED_IN, RELEASED_ON

# The shipped figures, measured off the maintainer's own runs by
# `docs/chaos_runs.py` and refreshed by the release step.
#
# `bosses` is {part: {boss floor: amount}}; `marks` is {mark: (amount a
# fight, marked fights a whole run)}. Season 4's first part was never
# captured, so it borrows the second's.
SHIPPED = {
    "disaster_s04": {
        "bosses": {2: {17: 172, 34: 172},
                   3: {17: 180, 34: 180, 37: 60}},
        "marks": {"k5": (60, 1.43), "e": (90, 0.36), "b1": (0, 0.36),
                  "b1+k5": (60, 0.07)},
    },
}

# Rule 3: the share of a floor's payouts the highest must make up to
# stand alone.
TOP_SHARE = 0.7

# Rule 4: how many whole runs since the release make the player's own
# rates. A run's marks pay about 90 either side of their mean, so two
# hundred runs pin the mean to about 6 a run -- some 400 on a season.
RATE_RUNS = 200

# Every Chaos, by the stage id its clear names, and the season it came
# with: each Galactic Disaster's own, named in the game's update notes,
# then the base game's, which came with none. A Chaos keeps its stage id
# whichever door it is entered by -- its own screen, the Galactic
# Disaster's or the Zero System. Its `chaos_id` on the wire is beside
# each: a run records both.
CHAOS_NAMES = {
    50000: ("Laboratory 0", "disaster_s01"),                 # chaos_06
    60000: ("Burning Life", "disaster_s02"),                 # chaos_07
    70000: ("Theater of Illusions", "disaster_s03"),         # chaos_08
    80000: ("Kaleidoscope Hatchery", "disaster_s04"),        # chaos_09
    110000003: ("Blue Pot", None),                           # chaos_01
    115000001: ("Twin Star's Shadow", None),                 # chaos_02
    120000002: ("City of Mist", None),                       # chaos_03
    120000001: ("Swamp of Judgement", None),                 # chaos_04
    120000004: ("The Foretold Ruin", None),                  # chaos_05
}

# The Zero System's special options, which a map's codex carries, by
# what they do. Each Galactic Disaster's own is the Effect chosen when
# the codex is made, adding its Chaos's features to a base-game Chaos;
# the next season's is on offer in its preseason. Season 5's turns every
# floor after the first boss into Elite and Unidentified Area floors and
# adds a Core of Discord style boss -- fewer ordinary fights a run, so
# fewer marked ones, at an unmoved rate a fight. `v1_01` to `v1_04` are
# rolled beside the Effect, or without one; only Divine Intervention's
# is named. `docs/capture_pipeline.md`, *The Zero System's codex*.
ZERO_SPECIALS = {
    "zero_orb_special_v1_04": "Divine Intervention",
    "zero_orb_special_v1_05": "season 1 Chaos",
    "zero_orb_special_v1_06": "season 2 Chaos",
    "zero_orb_special_v1_07": "season 3 Chaos",
    "zero_orb_special_v1_08": "season 4 Chaos",
    "zero_orb_special_v1_09": "season 5 Chaos",
}

# Windows in which something raised how often the marks turn up, as
# (first day, last day, name), UTC. A run inside one says nothing about
# the ordinary rate, so the rates leave it out; `docs/chaos_runs.py`
# does the same.
RATE_EVENTS = ()

# The `chaos_runs_per_day` setting: what it falls back to, and the most
# it may say.
DEFAULT_RUNS_PER_DAY = 1
MAX_RUNS_PER_DAY = 20

BOSS = "BOSS"
DAY = 86400


def season_number(season):
    """`disaster_s04` as 4, or None."""
    text = str(season or "")
    digits = text.rsplit("_s", 1)[-1] if "_s" in text else ""
    return int(digits) if digits.isdigit() else None


def staleness(live, released_in=RELEASED_IN):
    """How many whole Galactic Disaster seasons have run since the
    release: 0 while the release's own season or the next is live, 1
    once a season has come and gone without an update. 0 where either
    season cannot be read."""
    now, then = season_number(live), season_number(released_in)
    if now is None or then is None:
        return 0
    return max(0, now - then - 1)


def runs_per_day(value):
    """The `chaos_runs_per_day` setting as a number: positive and at
    most `MAX_RUNS_PER_DAY`, else the default. A whole number comes
    back as an int, so a label prints `2`, not `2.0`."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DEFAULT_RUNS_PER_DAY
    if not 0 < number <= MAX_RUNS_PER_DAY:          # NaN fails too
        return DEFAULT_RUNS_PER_DAY
    return int(number) if number == int(number) else number


def released_at(day=RELEASED_ON):
    """`RELEASED_ON` as a UTC timestamp; 0 where it does not parse, so
    that every run counts as after it."""
    try:
        return datetime.datetime.strptime(day, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return 0


def readable(runs):
    """The recorded runs that can be read: dicts with a clear time."""
    return [run for run in runs or ()
            if isinstance(run, dict)
            and isinstance(run.get("closed"), (int, float))]


def is_current(run):
    """Whether a run was in the live season's own Chaos: entered through
    the Galactic Disaster. A past season's Chaos, entered through the
    Zero System, pays the currency too but less, and the estimate is of
    the live one. A record with no `via` came the Galactic Disaster's
    way: none other was followed when it was made."""
    return run.get("via", "disaster") == "disaster"


def chaos_name(run):
    """The Chaos a run was in, by name: its stage id's, else the
    season's own where it came in through the Galactic Disaster; `?`
    where the record cannot say."""
    named = CHAOS_NAMES.get(run.get("stage"))
    if named:
        return named[0]
    if is_current(run):
        for name, season in CHAOS_NAMES.values():
            if season == run.get("season"):
                return name
    return str(run.get("stage") or "?")


def payouts(run):
    """(floor, spot, mark, amount) for every payout a run took."""
    out = []
    for entry in run.get("paid") or ():
        if (isinstance(entry, (list, tuple)) and len(entry) >= 5
                and isinstance(entry[4], int)):
            out.append((entry[0], entry[1], entry[2] or "", entry[4]))
    return out


def is_full(run):
    """Whether a run counts as a whole one: cleared, or lost where a
    boss had already paid and no non-boss fight was left on the map.
    A run left by an escape (`gave_up`) never does: where it stopped is
    not on the wire."""
    if run.get("gave_up"):
        return False
    lost = run.get("lost")
    if not lost:
        return True
    if not isinstance(lost, (list, tuple)) or len(lost) < 4:
        return False
    floor, _spot, _mark, after = lost[:4]
    if not isinstance(floor, int) or after != 0:
        return False
    return any(spot == BOSS and isinstance(at, int) and at < floor
               for at, spot, _mark, _amount in payouts(run))


def missed(run, bosses, marks):
    """What a whole lost run did not collect: the lost fight's own
    payout -- its boss's, or its mark's -- and every boss floor after
    it. 0 for a cleared run, and for a lost one that is not whole.

    `bosses` is {floor: amount} for the run's season part, `marks`
    {mark: amount}.
    """
    lost = run.get("lost")
    if not lost or not is_full(run):
        return 0
    floor, spot, mark = lost[0], lost[1], lost[2] or ""
    if spot == BOSS:
        own = bosses.get(floor, 0)
    else:
        own = marks.get(mark, 0) if mark else 0
    return own + sum(amount for at, amount in bosses.items() if at > floor)


def part_of(when, starts):
    """Which season part `when` falls in, by when each part opened: 1
    from the first, 0 before it, None without dates."""
    if not starts:
        return None
    return sum(1 for start in starts if start <= when)


def run_part(run, live, starts):
    """A run's season part: dated by `starts` when it is from the live
    season -- the Checklist's own dating -- else as the capture stamped
    it."""
    if starts and run.get("season") == live:
        return part_of(run["closed"], starts)
    part = run.get("part")
    return part if isinstance(part, int) else None


def shipped_entry(live, shipped=SHIPPED):
    """The shipped figures for `live`, else for the newest season before
    it, else the newest of all: a new season starts from the last one
    measured."""
    if live in shipped:
        return shipped[live]
    number = season_number(live)
    known = sorted((season_number(name), name) for name in shipped
                   if season_number(name) is not None)
    before = [name for n, name in known if number is not None and n < number]
    pick = before[-1] if before else (known[-1][1] if known else None)
    return shipped.get(pick) or {}


def shipped_bosses(entry, part):
    """The shipped {floor: amount} for a part: its own, else the nearest
    measured part before it, else after it."""
    table = entry.get("bosses") or {}
    if part in table:
        return dict(table[part])
    below = [p for p in table if p < part]
    above = [p for p in table if p > part]
    pick = max(below) if below else (min(above) if above else None)
    return dict(table[pick]) if pick is not None else {}


def settle(expected, seen, stale):
    """One set amount from the shipped one and the payouts the player
    saw -- rules 1 to 3 in the module docstring."""
    if not seen:
        return expected
    if stale >= 2:
        top = max(seen)
        if seen.count(top) >= TOP_SHARE * len(seen):
            return top
        return sum(seen) / len(seen)
    kept = [amount for amount in seen if amount >= expected]
    return sum(kept) / len(kept) if kept else expected


def _seasons_read(live, stale):
    """The season numbers a set amount is read from: the live one, and
    the one before it once a whole season has run since the release."""
    number = season_number(live)
    if number is None:
        return set()
    return {number, number - 1} if stale >= 1 else {number}


def boss_table(live, part, runs, starts=None, shipped=SHIPPED, stale=0):
    """{boss floor: amount} for one part of the live season."""
    expected = shipped_bosses(shipped_entry(live, shipped), part)
    wanted = _seasons_read(live, stale)
    seen = collections.defaultdict(list)
    for run in runs:
        if (not is_current(run)
                or season_number(run.get("season")) not in wanted
                or run_part(run, live, starts) != part):
            continue
        for floor, spot, _mark, amount in payouts(run):
            if spot == BOSS and isinstance(floor, int):
                seen[floor].append(amount)
    return {floor: settle(expected.get(floor, 0), seen.get(floor, []), stale)
            for floor in sorted(set(expected) | set(seen))}


def mark_values(live, runs, shipped=SHIPPED, stale=0):
    """{mark: amount a fight} for the live season."""
    expected = {mark: amount for mark, (amount, _rate)
                in (shipped_entry(live, shipped).get("marks") or {}).items()}
    wanted = _seasons_read(live, stale)
    seen = collections.defaultdict(list)
    for run in runs:
        if (not is_current(run)
                or season_number(run.get("season")) not in wanted):
            continue
        for _floor, spot, mark, amount in payouts(run):
            if mark and spot != BOSS:
                seen[mark].append(amount)
    return {mark: settle(expected.get(mark, 0), seen.get(mark, []), stale)
            for mark in sorted(set(expected) | set(seen))}


def in_rate_event(when):
    """The name of the `RATE_EVENTS` window `when` falls in, or None."""
    day = datetime.datetime.fromtimestamp(
        when, datetime.timezone.utc).strftime("%Y-%m-%d")
    for first, last, name in RATE_EVENTS:
        if first <= day <= last:
            return name
    return None


def mark_rates(live, runs, shipped=SHIPPED, stale=0, since=None):
    """({mark: marked fights a whole run}, how many runs made them).

    The shipped rates and None, unless rule 4 hands them to the player.
    """
    rates = {mark: rate for mark, (_amount, rate)
             in (shipped_entry(live, shipped).get("marks") or {}).items()}
    if stale < 2:
        return rates, None
    after = released_at() if since is None else since
    counted = [run for run in runs
               if run["closed"] >= after and is_current(run)
               and is_full(run) and not in_rate_event(run["closed"])]
    if len(counted) < RATE_RUNS:
        return rates, None
    marked = collections.Counter()
    for run in counted:
        for mark, n in (run.get("marked") or {}).items():
            if isinstance(n, int):
                marked[mark] += n
    return ({mark: marked[mark] / len(counted)
             for mark in sorted(set(rates) | set(marked))}, len(counted))


def season_chaos(live, runs, part_days, runs_a_day=DEFAULT_RUNS_PER_DAY,
                 starts=None, shipped=SHIPPED, released_in=RELEASED_IN,
                 since=None):
    """What the live season's Chaos pays at `runs_a_day`, or None where
    nothing has been shipped to start from.

    `runs` is the snapshot's `chaos_runs`; `part_days` the days each
    part runs, first to last; `starts` when each part opened, which
    dates the live season's runs where given.
    """
    if not shipped or not part_days:
        return None
    stale = staleness(live, released_in)
    runs = readable(runs)
    values = mark_values(live, runs, shipped, stale)
    rates, _counted = mark_rates(live, runs, shipped, stale, since)
    marks_a_run = sum(values.get(mark, 0) * rate
                      for mark, rate in rates.items())
    bosses = sum(sum(boss_table(live, part, runs, starts, shipped,
                                stale).values()) * days
                 for part, days in enumerate(part_days, start=1))
    return runs_a_day * (bosses + marks_a_run * sum(part_days))


def parts_shipped(live, shipped=SHIPPED):
    """How many parts the shipped figures give a season: the most any
    measured part reaches."""
    table = shipped_entry(live, shipped).get("bosses") or {}
    return max(table) if table else 0
