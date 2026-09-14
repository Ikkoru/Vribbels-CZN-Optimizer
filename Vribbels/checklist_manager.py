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
        "3920007": {"kind": "delta", "held": 11005,
                    "points": [[1352, 0]]}
    }

**A point is a lifetime running total, never a holding**, so a rate
over any window is one subtraction and nothing has to reason about
spending. The two kinds differ only in where that total comes from:

* `total` -- the wire states it. A currency in `characters.currencies`
  carries `total_amount`, which is lifetime GAINED and `total_use_amount`
  lifetime spent, the two differing by exactly the holding. Checked
  across 101 snapshots and five currencies: it never steps backwards.
  Such a ledger is SEEDED at the account's creation day with zero, off
  `user.createAt`, which is an observation rather than a guess -- an
  account has earned nothing the day it is made -- and so a year's
  reading is available from the first capture rather than after a year
  of them.
* `delta` -- the wire does not. Two shop currencies are ordinary
  inventory items with an `amount` and no lifetime anything, so the
  total is accumulated here from the rises in that holding, and `held`
  is what the last one is measured against. **It UNDERSTATES**: a gain
  and a spend between two captures cancel before either is seen. There
  is nothing on the wire that would do better.

Points are kept for a year and a day. Past that the oldest fall off,
which is what turns the seeded reading into a rolling one.
"""

import json
from pathlib import Path

CHECKLIST_VERSION = 1

# How many daily points a currency keeps. A year, plus the day at the
# far end to measure the year against.
LEDGER_DAYS = 366

# The two ways a lifetime total is arrived at. See the module note.
FROM_WIRE, FROM_RISES = "total", "delta"

# What an id nobody has ticked or unticked reads as.
DEFAULT_TRACKED = True

# Per-product starting states, for products the default is wrong for.
# Read off the maintainer's own account: the products they do not
# check for. Everything absent reads DEFAULT_TRACKED.
DEFAULTS = {
    # Untracked by default: bought rarely, or not worth the daily
    # check for most accounts. Everything else reads DEFAULT_TRACKED.
    'town_shop_goods_002': False,
    'town_shop_goods_003': False,
    'town_shop_goods_001': False,
    'town_shop_goods_011': False,
    'town_shop_goods_012': False,
    'town_shop_goods_007': False,
    'town_shop_goods_008': False,
    'town_shop_goods_009': False,
    'gacha_duplicate_legend_13': False,
    'gacha_duplicate_legend_14': False,
    'gacha_duplicate_legend_3': False,
    'gacha_duplicate_legend_4': False,
    'gacha_duplicate_legend_5': False,
    'gacha_duplicate_legend_6': False,
    'gacha_duplicate_legend_7': False,
    'gacha_duplicate_legend_8': False,
    'gacha_duplicate_legend_9': False,
    'gacha_duplicate_legend_10': False,
    'gacha_duplicate_legend_11': False,
    'hyperspace_3': False,
    'card_factor_4': False,
    'assault_shop_product_7': False,
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
        # res_id (str) -> {kind, points, held}. See the module note.
        self.currency = {}

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

    # ------------------------------------------------- the currency ledger

    def record_currency(self, res_id, value, day, kind=FROM_WIRE,
                        since=None):
        """Note where one currency's lifetime total stands today.

        `value` is `total_amount` off the wire for a `FROM_WIRE`
        currency, and the plain holding for a `FROM_RISES` one -- the
        running total is kept here for the second, because nothing on
        the wire keeps it.

        `day` is the day the SNAPSHOT is from, not today. Loading an
        old capture file is an ordinary thing to do, and a lifetime
        total from three weeks ago written against today would read as
        three weeks of earnings undone. Against its own day it is what
        it is -- a reading of that day -- and a `FROM_WIRE` ledger
        takes it wherever it belongs, which is how opening an old file
        fills a gap in the record rather than spoiling it.

        A `FROM_RISES` ledger cannot: its totals are accumulated
        forward, so a point can only be added at the end and an older
        snapshot is passed over.

        `since` is the day the account was made, and seeds an empty
        `FROM_WIRE` ledger with a zero there. That point is a reading:
        a lifetime total was zero before there was a lifetime. Without
        it the first year of readings would have no far end to measure
        against.

        Returns the ledger's points, oldest first.
        """
        res_id, day = str(res_id), int(day)
        row = self.currency.get(res_id)
        if not isinstance(row, dict) or row.get("kind") != kind:
            row = {"kind": kind, "points": []}
            if kind is FROM_WIRE and since is not None and int(since) < day:
                row["points"].append([int(since), 0])
            self.currency[res_id] = row
        points = row["points"]
        before = json.dumps(row, sort_keys=True)
        if kind is FROM_WIRE:
            # One point per day, the higher reading winning: a day with
            # six captures is still one day's earnings, and a ledger
            # with six points on it would answer "per day" six times.
            by_day = {p[0]: p[1] for p in points}
            by_day[day] = max(int(value), by_day.get(day, int(value)))
            newest = max(by_day)
            points = [[d, by_day[d]] for d in sorted(by_day)
                      if d >= newest - LEDGER_DAYS]
        elif not points or day >= points[-1][0]:
            held = row.get("held")
            rose = max(0, int(value) - held) if isinstance(held, int) else 0
            total = (points[-1][1] if points else 0) + rose
            row["held"] = int(value)
            if points and points[-1][0] >= day:
                points[-1] = [day, total]
            else:
                points.append([day, total])
            points = [p for p in points if p[0] >= day - LEDGER_DAYS]
        row["points"] = points
        if json.dumps(row, sort_keys=True) != before:
            self._write()
        return [tuple(p) for p in points]

    def currency_points(self, res_id):
        """One currency's ledger, oldest first, as (day, total) pairs."""
        row = self.currency.get(str(res_id))
        points = row.get("points") if isinstance(row, dict) else None
        return [tuple(p) for p in points] if points else []

    def _write(self):
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        data = {"version": CHECKLIST_VERSION, "tracked": self.tracked,
                "seen": self.seen, "currency": self.currency}
        tmp = self.file.with_suffix(self.file.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.file)


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
        if kind not in (FROM_WIRE, FROM_RISES):
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
        clean = {"kind": kind,
                 "points": [[day, by_day[day]] for day in sorted(by_day)]}
        held = row.get("held")
        if isinstance(held, int) and not isinstance(held, bool):
            clean["held"] = held
        out[str(res_id)] = clean
    return out
