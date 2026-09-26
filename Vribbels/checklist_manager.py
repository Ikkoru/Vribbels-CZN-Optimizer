"""Which Checklist shop products the user is tracking, and what the
shop currencies have been earning.

Every shop product on the Checklist tab carries a checkbox. A TICKED
one is a thing the user means to buy each period, and its reading is
coloured; an unticked one sinks to the bottom of its shop and greys
out. The tab still lists it -- the shop sells it, and hiding a product
outright would leave the user wondering where it went.

Stored as JSON in `settings/checklist.json` (pure user state, no
bundled default):

    {
        "version": 1,
        "tracked": {
            "town_shop_goods_005": true,
            "town_shop_goods_009": false
        }
    }

Keyed by PRODUCT ID, which is what the wire calls a shop entry and is
stable across the item it sells changing. **An absent id reads as
`DEFAULT_TRACKED`**, so a product the game adds appears already in
whichever state suits most of them rather than needing a first tick.

`DEFAULTS` is the exception to that: a per-product starting state, for
the ones most accounts would answer differently on. It ships in the
code rather than in a file, since a shipped `settings/` file is user
state the sync would then have to reason about.

## The currency ledger

The same file also holds a per-currency record of how much has been
EARNED, one point per day:

    "currency": {
        "2000031": {"kind": "total",
                    "points": [[1027, 0], [1352, 36043]]},
        "3920007": {"kind": "shop",
                    "points": [[1027, 0], [1352, 185755]]}
    }

**A point is a lifetime EARNED total, never a holding**, so a rate over
any window is one subtraction and nothing has to reason about spending.
**And it is SEEDED at the account's creation day with a zero**, off
`user.createAt` -- an observation rather than a guess, an account
having earned nothing the day it is made. That seed is what makes a
year's reading available on the first capture rather than after a year
of them.

The two kinds differ only in where the total came from, which is
recorded because one is stated and the other is worked out:

* `total` -- the wire states it. A currency in `characters.currencies`
  carries `total_amount` beside `total_use_amount` and the holding,
  and the three reconcile exactly. Across every snapshot on hand and
  all five currencies it never steps backwards.
* `shop` -- the wire does not, and the shops account for it. Two shop
  currencies are ordinary inventory items with an `amount` and no
  lifetime anything; what is held plus everything ever bought with it
  (`shop_list[*].total_count` times the product's price) is the same
  figure. Checked against the wire's own answer for the five
  currencies that have one: exact at every reading for four of them,
  and within 300 for the fifth, only where a capture caught a
  purchase between the two payloads.

Points are kept for a year and a day. Past that the oldest fall off,
which is what turns the seeded reading into a rolling one.

## Streaks the game has said are over

    "streaks": {"event_143": true}

**A login streak's end is said ONCE and never again.** `completed`
rides the reply to the claim that finishes it; the login that follows
sends the row without it, and that row is identical to a streak merely
claimed for today -- `current_days` equal to `received_days` in both.
So a streak finished in one session would read as unfinished in the
next, for as long as its event ran.

Kept here rather than in a snapshot because it is a fact about the
PAST, which is the same reason `seen` is here -- and because this
directory is not the one a user clears when they tidy up captures.

## Events the USER has called finished

    "finished": {"event_schedule_devil_001": [21, 21]}

**The wire says an event is over for almost none of them.** What it
does say is how many rewards have been claimed and, where the shape
can be worked out, how many there are -- and a row sitting at its own
ceiling is either finished or waiting for the game to hand out more,
with nothing here able to tell which.

So the tab offers the answer to the person who can see the game, and
remembers it against the PAIR it was given for. A tick counts only
while the claimed count and the total are the two it was made at:
either of them moving is the game saying something new, and the
answer goes back to being unknown rather than standing on a reading
that no longer exists.

## How many rewards a past instalment of an event held

    "events": {"event_stock": {"event_stock_01": 17}}

**A FINISHED event's mission rows are its whole total**, where a live
one's are only what has been issued so far -- which is why almost every
event row on the tab can show a floor and nothing better. An instalment
whose window has closed is counted once and written down here, under
the family it belongs to.

Written down rather than re-derived because the game PURGES old
instalments: the rows are in `mission_entities` for a while and then
they are not, and a total nobody recorded while it was there cannot be
recovered. The record outlives them, and the next instalment of that
family is what it is for.

**Two agreeing instalments before any of it is believed.** One is not
evidence that a family repeats itself: the login streaks run 7, 10, 14
or 21 days depending on the instalment. See `event_total`.

## Event families that pay a final reward

    "finals": {"event_nodelist": ["event_nodelist_006",
                                  "event_nodelist_007"]}

**The wire says an event HAS a final reward only once it is claimed.**
The reward that unlocks after every other one -- the game's Special
Reward -- is invisible until its claim writes a completion record, and
nothing before the claim hints that it is there. So the one way to
know the next instalment has one is to remember that this one did.

Written down for the same reason as the totals: the game purges
completion records in batches, months after some of their events
ended. **One instalment is enough here**, unlike a total -- being
wrong costs a row
that asks `Finished?` over a reward that is not there, which the user
answers in one click, where missing it costs the reward.
"""

import json
from pathlib import Path

import shared_facts

CHECKLIST_VERSION = 1

# How many daily points a currency keeps. A year, plus the day at the
# far end to measure the year against.
LEDGER_DAYS = 366

# The two ways a lifetime total is arrived at. See the module note.
FROM_WIRE, FROM_SHOPS = "total", "shop"

# What an id nobody has ticked or unticked reads as.
DEFAULT_TRACKED = True

# Per-product starting states, for products the default is wrong for.
# Read off the maintainer's own account: the products they do not
# check for. Everything absent reads DEFAULT_TRACKED.
DEFAULTS = {
    # Untracked by default: bought rarely, or not worth the daily
    # check for most accounts. Everything else reads DEFAULT_TRACKED.
    'town_shop_goods_001': False,        # Multidimensional Alignment Material
    'town_shop_goods_002': False,        # Special Security Code
    'town_shop_goods_003': False,        # Research Notes
    'town_shop_goods_007': False,        # Exquisite Slice of Cake
    'town_shop_goods_008': False,        # Sweet Choconilla
    'town_shop_goods_009': False,        # Units x4000
    'town_shop_goods_011': False,        # Advanced Battle Memory x5
    'town_shop_goods_012': False,        # Advanced Support Data x5
    'gacha_duplicate_legend_10': False,  # Particles of Memory
    'gacha_duplicate_legend_11': False,  # Units x15000
    'gacha_duplicate_legend_13': False,  # Exquisite Slice of Cake
    'gacha_duplicate_legend_14': False,  # Sweet Choconilla
    'gacha_duplicate_legend_3': False,   # Great Growth Stone of Passion
    'gacha_duplicate_legend_4': False,   # Great Growth Stone of Order
    'gacha_duplicate_legend_5': False,   # Great Growth Stone of Instinct
    'gacha_duplicate_legend_6': False,   # Great Growth Stone of Void
    'gacha_duplicate_legend_7': False,   # Great Growth Stone of Justice
    'gacha_duplicate_legend_8': False,   # Advanced Battle Memory x2
    'gacha_duplicate_legend_9': False,   # Advanced Support Data x2
    'hyperspace_3': False,               # Multidimensional Alignment Material
    'card_factor_4': False,              # Prism Module - Nominate
    'assault_shop_product_7': False,     # Multidimensional Alignment Material
    # The Galactic Disaster's shelves, keyed by the OFFER rather than
    # by the product: its ids carry the season and are all renamed
    # when the next one opens. See `checklist_tab.SEASONAL_TRACKING`.
    'disaster:3210002:1:4000': False,    # Multidimensional Alignment Material
    'disaster:3100002:1:120': False,     # Advanced Battle Memory, dearest page
    'disaster:3100022:1:120': False,     # Advanced Support Data, dearest page
}


class ChecklistManager:
    """Loads and persists the Checklist's per-product tracked flags."""

    def __init__(self, base_dir: Path):
        self.settings_dir = Path(base_dir) / "settings"
        self.file = self.settings_dir / "checklist.json"
        self.tracked = {}          # product id (str) -> bool
        # row key -> [what it read, when it first read that].
        # See `first_seen`.
        self.seen = {}
        # res_id (str) -> {kind, points}. See the module note.
        self.currency = {}
        # Streak event id (str) -> True, for the ones the game has
        # said are over. See the module note.
        self.streaks = {}
        # Event family (str) -> {instalment id: how many rewards it
        # held}. Finished instalments only. See the module note.
        self.events = {}
        # Event id (str) -> [claimed, total] when the user ticked
        # `Finished?`. See the module note.
        self.finished = {}
        # Event family (str) -> [instalment ids] whose final reward the
        # game has recorded as taken. See the module note.
        self.finals = {}

    def load(self):
        """Read the flags. An unreadable file behaves like a fresh one.

        A missing or corrupt file is not an error the user can act on,
        and refusing to build the tab over it would cost them the whole
        Checklist for a bad byte.
        """
        self.tracked = {}
        if not self.file.exists():
            return
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        raw = data.get("tracked") if isinstance(data, dict) else None
        if isinstance(raw, dict):
            self.tracked = {str(k): bool(v) for k, v in raw.items()}
        seen = data.get("seen") if isinstance(data, dict) else None
        if isinstance(seen, dict):
            self.seen = {
                str(k): [str(v[0]), float(v[1])]
                for k, v in seen.items()
                if isinstance(v, (list, tuple)) and len(v) == 2
            }
        self.currency = _clean_ledger(data.get("currency")
                                      if isinstance(data, dict) else None)
        streaks = data.get("streaks") if isinstance(data, dict) else None
        if isinstance(streaks, dict):
            self.streaks = {str(k): True for k, v in streaks.items() if v}
        self.events = _clean_events(data.get("events")
                                    if isinstance(data, dict) else None)
        self.finished = _clean_finished(data.get("finished")
                                        if isinstance(data, dict) else None)
        self.finals = _clean_finals(data.get("finals")
                                    if isinstance(data, dict) else None)

    def is_tracked(self, product_id) -> bool:
        """Whether a product is ticked. Absent ids take the default."""
        product_id = str(product_id)
        if product_id in self.tracked:
            return self.tracked[product_id]
        return DEFAULTS.get(product_id, DEFAULT_TRACKED)

    def set_tracked(self, product_id, value: bool):
        """Tick or untick one product, and persist it."""
        product_id = str(product_id)
        if self.tracked.get(product_id) == bool(value):
            return
        self.tracked[product_id] = bool(value)
        self._write()

    def first_seen(self, key, reading, now):
        """When `key` FIRST read `reading`, having read it ever since.

        The clock behind the Checklist's "this looks finished but
        nothing proves it" colour. An event whose rows are all claimed
        may be finished or may be waiting for the game to hand out
        more, and the wire says which for almost none of them -- but a
        tally that has not moved in two days is evidence of a kind.

        Recorded here rather than computed because it cannot be: it is
        a fact about the PAST, and a snapshot holds only the present.
        Reading something new restarts the clock.
        """
        key, reading = str(key), str(reading)
        remembered = self.seen.get(key)
        if remembered is not None and remembered[0] == reading:
            return remembered[1]
        self.seen[key] = [reading, float(now)]
        self._write()
        return float(now)

    def forget_unseen(self, keys):
        """Drop remembered rows that are no longer on the tab.

        An event that ended takes its row with it, and its record would
        otherwise sit in the file for good.
        """
        keys = {str(k) for k in keys}
        stale = [k for k in self.seen if k not in keys]
        if not stale:
            return
        for key in stale:
            del self.seen[key]
        self._write()

    def remember_streak(self, event_id):
        """Note that the game has said this login streak is over."""
        event_id = str(event_id)
        if self.streaks.get(event_id):
            return
        self.streaks[event_id] = True
        self._write()

    def streak_finished(self, event_id):
        """Whether that has been said, in this session or an earlier one."""
        return bool(self.streaks.get(str(event_id)))

    # ------------------------------------------ what the user called done

    def call_finished(self, event_id, claimed, total, done=True):
        """Tick or untick `Finished?` for one event.

        The pair it was ticked AT is what is written down, because
        that is what the answer was about. See `called_finished`.
        """
        event_id = str(event_id)
        if not done:
            if self.finished.pop(event_id, None) is None:
                return
        else:
            pair = [int(claimed), int(total)]
            if self.finished.get(event_id) == pair:
                return
            self.finished[event_id] = pair
        self._write()

    def called_finished(self, event_id, claimed, total):
        """Whether the user's answer still stands for this reading.

        **A tick is about the reading it was given for.** Either figure
        moving is the game saying something new -- another reward
        claimed, or another one to claim -- and an answer given before
        that cannot speak for it. So the tick is not merely stale, it
        is gone: `False` here, and the caller forgets it.
        """
        held = self.finished.get(str(event_id))
        return bool(held) and held == [int(claimed), int(total)]

    # ----------------------------------------------- finished instalments

    def record_event_total(self, family, event_id, count):
        """Note how many rewards one FINISHED instalment held.

        The caller decides an instalment is finished; this only files
        the count. Re-recording the same figure writes nothing, so an
        ordinary load costs no disk.

        **The BIGGEST count for an instalment wins.** The rows are
        purged gradually, so a smaller figure later is the purge having
        started rather than a better reading, and it must not overwrite
        what was seen whole.
        """
        family, event_id = str(family), str(event_id)
        if not _is_count(count) or count <= 0:
            return
        held = self.events.setdefault(family, {})
        if count <= held.get(event_id, 0):
            return
        held[event_id] = int(count)
        self._write()

    def event_total(self, family, live_id=None, same=str, shipped=None):
        """What an instalment of `family` holds, or None.

        `shipped` is the program's own game facts (`shared_facts.py`):
        the instalments they hold vote beside the ones recorded here,
        the bigger count per instalment standing for it, so an account
        that missed a family's past instalments still has their pattern.

        Every FINISHED instalment on record has to agree, and there
        have to be at least two of them: a family that repeats itself
        says so by repeating, and one instalment is a number rather
        than a pattern -- the login streaks run 7, 10, 14 or 21 days
        depending on which one it is.

        `live_id` is left out of the count. A live instalment's rows
        are what has been issued so far, so letting it vote would be
        the floor this exists to replace, voting for itself.

        **`same` says which ids are one instalment**, and they vote
        once. The game can schedule one instalment twice --
        `event_schedule_arena_2` and `event_arena_2` are the same
        arena -- and counted as two it agrees with itself.
        """
        family = str(family)
        held = shared_facts.totals_with(
            {family: self.events.get(family) or {}}, shipped).get(family, {})
        live = same(str(live_id)) if live_id is not None else None
        votes = {}
        for event_id, count in held.items():
            key = same(event_id)
            if key != live:
                votes[key] = max(votes.get(key, 0), count)
        past = list(votes.values())
        if len(past) < 2 or len(set(past)) != 1:
            return None
        return past[0]

    # ------------------------------------------------- final rewards seen

    def remember_final(self, family, event_id):
        """Note that an instalment of `family` paid a final reward.

        Re-noting one already held writes nothing, so an ordinary load
        costs no disk.
        """
        family, event_id = str(family), str(event_id)
        held = self.finals.setdefault(family, [])
        if event_id in held:
            return
        held.append(event_id)
        held.sort()
        self._write()

    def pays_final(self, family, shipped=None):
        """Whether any instalment of `family` has paid a final reward --
        one recorded here, or one the program ships (`shared_facts.py`).
        """
        family = str(family)
        return bool(shared_facts.finals_with(
            {family: self.finals.get(family) or []}, shipped).get(family))

    # ------------------------------------------------- the currency ledger

    def record_currency(self, res_id, value, day, kind=FROM_WIRE,
                        since=None):
        """Note where one currency's lifetime total stands today.

        `value` is the lifetime EARNED total however it was arrived
        at -- stated by the wire, or worked out from the shops. `kind`
        records which, because one is a reading and the other is a
        reconstruction.

        `day` is the day the SNAPSHOT is from, not today. Loading an
        old capture file is an ordinary thing to do, and a lifetime
        total from three weeks ago written against today would read as
        three weeks of earnings undone. Against its own day it is what
        it is -- a reading of that day -- and the ledger takes it
        wherever it belongs, which is how opening an old file fills a
        gap in the record rather than spoiling it.

        `since` is the day the account was made, and seeds an empty
        ledger with a zero there. That point is a reading: a lifetime
        total was zero before there was a lifetime. Without it the
        first year of readings would have no far end to measure
        against.

        Returns the ledger's points, oldest first.
        """
        res_id, day = str(res_id), int(day)
        row = self.currency.get(res_id)
        if not isinstance(row, dict) or row.get("kind") != kind:
            row = {"kind": kind, "points": []}
            if since is not None and int(since) < day:
                row["points"].append([int(since), 0])
            self.currency[res_id] = row
        before = json.dumps(row, sort_keys=True)
        # One point per day, the higher reading winning: a day with six
        # captures is still one day's earnings, and a ledger with six
        # points on it would answer "per day" six times over. The
        # higher, because a lifetime total only rises -- so a lower
        # second reading of a day is a capture that caught the shop
        # payloads mid-purchase rather than a day that went backwards.
        by_day = {p[0]: p[1] for p in row["points"]}
        by_day[day] = max(int(value), by_day.get(day, int(value)))
        newest = max(by_day)
        row["points"] = [[d, by_day[d]] for d in sorted(by_day)
                         if d >= newest - LEDGER_DAYS]
        if json.dumps(row, sort_keys=True) != before:
            self._write()
        return [tuple(p) for p in row["points"]]

    def currency_points(self, res_id):
        """One currency's ledger, oldest first, as (day, total) pairs."""
        row = self.currency.get(str(res_id))
        points = row.get("points") if isinstance(row, dict) else None
        return [tuple(p) for p in points] if points else []

    def _write(self):
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        data = {"version": CHECKLIST_VERSION, "tracked": self.tracked,
                "seen": self.seen, "currency": self.currency,
                "streaks": self.streaks, "events": self.events,
                "finished": self.finished, "finals": self.finals}
        tmp = self.file.with_suffix(self.file.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.file)


def _is_count(value):
    """A real whole number, `True` not being one."""
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_finished(raw):
    """The user's `Finished?` answers off disk, with the rot taken out.

    A pair of counts or nothing: an entry that is not two whole
    numbers cannot be compared against a reading, and an answer that
    cannot be checked is worse than no answer.
    """
    out = {}
    for event_id, pair in (raw or {}).items() if isinstance(raw, dict) else ():
        if (isinstance(pair, (list, tuple)) and len(pair) == 2
                and all(_is_count(n) and n >= 0 for n in pair)):
            out[str(event_id)] = [int(pair[0]), int(pair[1])]
    return out


def _clean_finals(raw):
    """The final-reward record off disk, with the rot taken out.

    A list of instalment ids per family or nothing, the same contract
    as `_clean_events`.
    """
    out = {}
    for family, held in (raw or {}).items() if isinstance(raw, dict) else ():
        if not isinstance(held, list):
            continue
        ids = sorted({str(event_id) for event_id in held
                      if isinstance(event_id, str) and event_id})
        if ids:
            out[str(family)] = ids
    return out


def _clean_events(raw):
    """The finished-instalment record off disk, with the rot taken out.

    Same contract as `_clean_ledger`: a hand-edited or half-written
    file costs the entries it broke and nothing else.
    """
    out = {}
    for family, held in (raw or {}).items() if isinstance(raw, dict) else ():
        if not isinstance(held, dict):
            continue
        rows = {str(event_id): int(count) for event_id, count in held.items()
                if _is_count(count) and count > 0}
        if rows:
            out[str(family)] = rows
    return out


def _clean_ledger(raw):
    """A currency ledger read back off disk, with the rot taken out.

    A hand-edited or half-written file must not cost the user the tab,
    so anything that does not read as a point is dropped rather than
    raised on. Points come back sorted and one-per-day, which is what
    every reading off them assumes.
    """
    out = {}
    for res_id, row in (raw or {}).items() if isinstance(raw, dict) else ():
        if not isinstance(row, dict):
            continue
        kind = row.get("kind")
        if kind not in (FROM_WIRE, FROM_SHOPS):
            continue
        by_day = {}
        for point in row.get("points") or ():
            if (not isinstance(point, (list, tuple)) or len(point) != 2
                    or not all(isinstance(n, int) and not isinstance(n, bool)
                               for n in point)):
                continue
            by_day[point[0]] = point[1]
        if not by_day:
            continue
        out[str(res_id)] = {
            "kind": kind,
            "points": [[day, by_day[day]] for day in sorted(by_day)]}
    return out
