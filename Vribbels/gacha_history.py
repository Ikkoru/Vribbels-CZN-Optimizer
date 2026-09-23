"""Gacha History: every pull the game has listed, kept after the game
stops listing it.

**The game keeps about half a year.** Its Rescue records page through
each banner family's pulls newest first, and anything older is gone for
good -- so a longer history exists only if someone read it while it was
still there. This module holds what was read, merges what was imported,
and works out how lucky it all was.

Two files under `snapshots/gacha_history/`, each with ONE writer:

* `captured.json` -- the capture addon's. The game's own records, kept
  in the wire's shape and keyed by the `id` the game gives each one,
  with the banners' rates, the pity counters and when each banner's
  list was last read.
* `imported.json` -- the Import button's: batches read out of another
  program's export, or out of an earlier export of this one.

One writer per file is what makes an import safe mid-capture: neither
process can write over what the other just wrote. Both write through
`write_verified`'s checked copy and keep the previous file as
`<name>.bak`; the addon's copy of that procedure is in
`capture/manager.py` and `checks/check_gacha_history.py` drives both.

A subfolder rather than the snapshots folder itself, because that
folder is the one a user empties -- and `capture/archive.py` only ever
sweeps its top level.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

FOLDER = "gacha_history"
CAPTURED = "captured.json"
IMPORTED = "imported.json"

# Appended to the WHOLE name, so the backup of `captured.json` is
# `captured.json.bak` and still says what it is a backup of.
BACKUP = ".bak"
TEMP = ".tmp"

# What each file says it is, so an import can tell this program's own
# files from anyone else's.
STORE_KIND = "vribbels gacha history"
IMPORT_KIND = "vribbels gacha history import"
EXPORT_KIND = "vribbels gacha history export"
VERSION = 1

# A held destination refuses a rename on Windows -- the app reading the
# file, an indexer, an antivirus. Transient, so retried.
REPLACE_TRIES = 5
REPLACE_WAIT = 0.2

# About how long the game goes on listing a pull. A pool whose last pull
# is older than this cannot be caught up by reading the game again, so it
# is never reported as behind.
GAME_KEEPS_DAYS = 183

# How far the pity record's `updateAt` may run past the newest pull this
# history holds before it counts as a pull the history is missing. The
# record is stamped a second or so after the batch it counts.
BEHIND_SLACK = 10


# --------------------------------------------------------------- pools

# **Pulls are grouped by the pity counter they advance, not by banner.**
# The Probabilities notices put every banner in a category and say one
# category shares one 5-star counter, and the in-game records group the
# same way: asking for the history of `gacha_pickup_combatant_30117`
# returns every Combatant rate-up's pulls.
#
# A pickup banner names its unit in its own id, and a rerun appends a
# suffix -- `gacha_pickup_combatant_1052_1`. **A rerun is a category of
# its own** ("Normal Combatant Rate-Up") with its own counter, so the
# suffix moves it to another pool rather than being dropped.
PICKUP_ID = re.compile(
    r"^gacha_pickup_(combatant|supporter)_(\d+)((?:_\d+)*)$")

# The families whose pity record is not named after their banner's id:
# `gacha_general_first_select_1` counts on `gacha_pity_first_select`,
# `gacha_partner_reform_1` on `gacha_pity_partner_reform`. (id prefix,
# pool.)
PREFIX_POOLS = (
    ("gacha_general_first_select", "first_select"),
    ("gacha_partner_reform", "partner_reform"),
)

# The game's names for each family, as the Probabilities notices and
# the event notices spell them, in the order the tab lists them.
#
# **The last two guarantee a 5-star within 50 pulls**, which the shared
# schedule below does not describe: the Special Rescue Request is the
# beginner selection, the Partner Special Rescue an event. Neither can be
# opened once over, so their rates are never read and no luck figure is
# drawn for them; should one be, `schedule_matches` refuses it.
POOL_LABELS = {
    "pickup_combatant": "Combatant Rate-Up Rescue",
    "pickup_supporter": "Partner Rate-Up Rescue",
    "pickup_combatant_rerun": "Normal Combatant Rate-Up Rescue",
    "pickup_supporter_rerun": "Normal Partner Rate-Up Rescue",
    "general": "Normal Combatant Rescue",
    "general_supporter": "Normal Partner Rescue",
    "card_factor": "Observe Prism Module",
    "partner_reform": "Partner Special Rescue",
    "first_select": "Special Rescue Request",
}
POOL_ORDER = tuple(POOL_LABELS)


def pool_of(gacha_id):
    """The pity pool a banner's pulls count toward."""
    gacha_id = str(gacha_id or "")
    m = PICKUP_ID.match(gacha_id)
    if m:
        return "pickup_%s%s" % (m.group(1), "_rerun" if m.group(3) else "")
    for prefix, pool in PREFIX_POOLS:
        if gacha_id.startswith(prefix):
            return pool
    return gacha_id[len("gacha_"):] if gacha_id.startswith("gacha_") \
        else gacha_id


def featured_of(gacha_id):
    """The rate-up unit a pickup banner names, or None."""
    m = PICKUP_ID.match(str(gacha_id or ""))
    return int(m.group(2)) if m else None


def pool_label(pool):
    """The game's name for a pool; a family nobody has named reads as
    its own id, spaced and capitalised."""
    return POOL_LABELS.get(pool) or pool.replace("_", " ").title()


def pity_record_name(pool):
    """The `gacha_pity_*` record that counts this pool."""
    return "gacha_pity_" + pool


# ------------------------------------------------------- past banners

# **Every rate-up banner, dated, for the pulls whose file lost which
# banner they came from** -- hub-czn's export files every Combatant
# rate-up under one name, so its pulls say neither which unit was
# featured nor whether the banner was a rerun. The game's own records
# name their banner exactly and never need this. (combatant banner,
# partner banner, first day, day it closes.)
#
# **A release banner changes over at 02:00 UTC** -- 11:00 in Korea,
# which is what a banner's own definition states -- on the day one
# closes and the next opens. Every window the captured schedule reaches
# agrees with this list to the day. Where the list leaves a day between
# two banners, a pull on it belongs to neither and stays unknown.
RELEASE_BANNERS = (
    ("gacha_pickup_combatant_1062", "gacha_pickup_supporter_30045",
     "2025-10-22", "2025-11-11"),                   # Haru & Asteria
    ("gacha_pickup_combatant_1057", "gacha_pickup_supporter_30044",
     "2025-11-12", "2025-12-02"),                   # Yuki & Westmacott
    ("gacha_pickup_combatant_1060", "gacha_pickup_supporter_30046",
     "2025-12-03", "2025-12-24"),                   # Chizuru & Itsuku
    ("gacha_pickup_combatant_30075", "gacha_pickup_supporter_30076",
     "2025-12-24", "2026-01-14"),                   # Sereniel & Peko
    ("gacha_pickup_combatant_1052", "gacha_pickup_supporter_20002",
     "2026-01-14", "2026-02-04"),                   # Narja & Gaya
    ("gacha_pickup_combatant_30047", "gacha_pickup_supporter_30091",
     "2026-02-04", "2026-02-25"),                   # Nine & Alcea
    ("gacha_pickup_combatant_30084", "gacha_pickup_supporter_30085",
     "2026-02-25", "2026-03-18"),                   # Tiphera & Tiana
    ("gacha_pickup_combatant_30097", "gacha_pickup_supporter_1025",
     "2026-03-18", "2026-04-08"),                   # Rita & Ivy
    ("gacha_pickup_combatant_1061", "gacha_pickup_supporter_30053",
     "2026-04-08", "2026-05-05"),                   # Diana & Sophia
    ("gacha_pickup_combatant_30093", "gacha_pickup_supporter_30094",
     "2026-04-29", "2026-05-27"),                   # Heidemarie & Sylvia
    ("gacha_pickup_combatant_1055", "gacha_pickup_supporter_30095",
     "2026-05-27", "2026-06-17"),                   # Adelheid & Clara
    ("gacha_pickup_combatant_1069", "gacha_pickup_supporter_1070",
     "2026-06-17", "2026-07-08"),                   # Tenebria & Aria
    ("gacha_pickup_combatant_30048", "gacha_pickup_supporter_30092",
     "2026-07-08", "2026-07-29"),                   # Fei & Ruixiang
    ("gacha_pickup_combatant_30113", "gacha_pickup_supporter_30114",
     "2026-07-29", "2026-08-19"),                   # Hilde & Eunie
    ("gacha_pickup_combatant_30115", "gacha_pickup_supporter_30116",
     "2026-08-19", "2026-09-09"),                   # Arabella & Licinia
    ("gacha_pickup_combatant_30117", "gacha_pickup_supporter_30118",
     "2026-09-09", "2026-09-30"),                   # Olga & Emilie
)

# The reruns, in the same shape. **Their changeover hour varies** -- one
# opened at 02:00 UTC beside a release, the rest at 18:00 -- so a rerun
# is taken as open for the whole of its first and last day: a pull near
# one is left unknown rather than given to the release banner beside it.
RERUN_BANNERS = (
    ("gacha_pickup_combatant_1062_1", "gacha_pickup_supporter_30045_1",
     "2026-06-17", "2026-07-08"),                   # Haru & Asteria
    ("gacha_pickup_combatant_1057_2", "gacha_pickup_supporter_30044_2",
     "2026-07-21", "2026-08-11"),                   # Yuki & Westmacott
    ("gacha_pickup_combatant_1060_1", "gacha_pickup_supporter_30046_1",
     "2026-08-11", "2026-09-01"),                   # Chizuru & Itsuku
    ("gacha_pickup_combatant_1052_1", "gacha_pickup_supporter_20002_1",
     "2026-09-22", "2026-10-13"),                   # Narja & Gaya
)

CHANGEOVER_HOUR = 2        # UTC


def _utc(day, hour=0):
    return datetime.strptime(day, "%Y-%m-%d").replace(
        hour=hour, tzinfo=timezone.utc).timestamp()


def _windows(banners, opens_hour, closes_after):
    """[(pool, gacha id, opens, closes)] in epoch seconds."""
    out = []
    for combatant, supporter, first, last in banners:
        for gacha_id in (combatant, supporter):
            out.append((pool_of(gacha_id), gacha_id,
                        _utc(first, opens_hour),
                        _utc(last, opens_hour) + closes_after))
    return out


_RELEASE_WINDOWS = _windows(RELEASE_BANNERS, CHANGEOVER_HOUR, 0)
_RERUN_WINDOWS = _windows(RERUN_BANNERS, 0, 86400)


def dated_banner(pool, at):
    """The rate-up banner a pull of `pool` at `at` came from, or None.

    Only where exactly one release banner of that kind was open and no
    rerun of it ran alongside: hub-czn filed a rerun's pulls under the
    rate-up's name too, so a pull made while both were open could have
    come from either -- and the two do not share a pity counter.
    """
    if beside_a_rerun(pool, at):
        return None
    open_now = [g for p, g, opens, closes in _RELEASE_WINDOWS
                if p == pool and opens <= at < closes]
    return open_now[0] if len(open_now) == 1 else None


def beside_a_rerun(pool, at):
    """Whether a rerun of `pool`'s kind was open at `at`."""
    rerun_pool = pool + "_rerun"
    return any(p == rerun_pool and opens <= at < closes
               for p, _g, opens, closes in _RERUN_WINDOWS)


# -------------------------------------------------------------- rarity

# **The one statement of a unit's rarity the game makes.** Every
# `gacha/get_rate` reply lists what its banner can pay, grouped by tier:
# `general_ssr_c_1004`, `pickup_c_16_rateup_ssr_c_30117`,
# `general_r_s_20010`. It names a unit released last week, where the
# CHARACTERS and PARTNERS tables name only what someone has typed in --
# and a new 5-star read as a 3-star leaves every pity after it wrong.
#
# The Prism Module lists card items (`card_factor_ssr_5201083`), not
# units, with no kind letter, so its entries never match.
POOL_ENTRY = re.compile(r"_(ssr|sr|r)_[cs]_(?:\d+_)*?(\d+)$")
TIER_STARS = {"ssr": 5, "sr": 4, "r": 3}


def tiers_from_rates(rates):
    """{res_id: stars} out of every captured banner's pool lists."""
    tiers = {}
    for entry in (rates or {}).values():
        pools = entry.get("pools") if isinstance(entry, dict) else None
        if not isinstance(pools, dict):
            continue
        for ids in pools.values():
            for pool_id in ids if isinstance(ids, list) else ():
                m = POOL_ENTRY.search(str(pool_id))
                if m:
                    tiers[int(m.group(2))] = TIER_STARS[m.group(1)]
    return tiers


def _unit_tables():
    from game_data import CHARACTERS, PARTNERS
    return CHARACTERS, PARTNERS


def stars_of(res_id, tiers):
    """A unit's stars: the game's word first, the tables' second, None
    where neither knows -- never a guess, which is what made a new
    5-star count as a 3-star."""
    if res_id in tiers:
        return tiers[res_id]
    characters, partners = _unit_tables()
    unit = characters.get(res_id) or partners.get(res_id)
    grade = unit.get("grade") if isinstance(unit, dict) else None
    return grade if grade in (3, 4, 5) else None


def unit_name(res_id):
    """What the tables call a unit, or its bare id."""
    characters, partners = _unit_tables()
    unit = characters.get(res_id) or partners.get(res_id)
    name = unit.get("name") if isinstance(unit, dict) else None
    return name if name and name != "Unknown" else "#%d" % res_id


# ---------------------------------------------------------------- luck

# **The 5-star schedule every banner shares**, from the Probabilities
# notices: the base rate up to the 57th pull, 4.5 points more on each
# pull from the 58th through the 69th, and a 5-star certain on the 70th.
# Not on the wire -- so `schedule_matches` holds it to what IS: a
# banner's consolidated rate, which the schedule must reproduce before
# any luck figure is drawn from it.
#
# **Every 5-star resets the count.** The rate-up notices describe a lost
# 50/50 as the count running on to a guaranteed rate-up at the 140th,
# which reads like a count that only a rate-up resets. It is not: only a
# count reset by every 5-star reproduces the consolidated rates printed
# beside that text -- 2.14343% at a 1% base, 3.52734% at 3% -- where the
# other reading gives 2.78%. The game's own counters agree wherever the
# two readings differ.
SOFT_PITY_FROM = 58
SOFT_PITY_STEP = 0.045
HARD_PITY = 70

# A banner's rates may differ from the schedule's by rounding, and by
# nothing more.
SCHEDULE_TOLERANCE = 1e-6


def chance_at(pull, base):
    """The 5-star chance on the `pull`th pull since the last 5-star."""
    if pull >= HARD_PITY:
        return 1.0
    if pull >= SOFT_PITY_FROM:
        return min(1.0, base + SOFT_PITY_STEP * (pull - SOFT_PITY_FROM + 1))
    return base


def cycle_odds(base):
    """[P(the 5-star lands on pull n)] for n = 0..HARD_PITY."""
    odds = [0.0] * (HARD_PITY + 1)
    alive = 1.0
    for pull in range(1, HARD_PITY + 1):
        p = chance_at(pull, base)
        odds[pull] = alive * p
        alive *= 1.0 - p
    return odds


def pulls_per_five(base):
    """How many pulls a 5-star takes on average under the schedule."""
    return sum(n * p for n, p in enumerate(cycle_odds(base)))


def base_rate(rates):
    """The 5-star base chance a rates reply states, or None."""
    r = (rates or {}).get("rates") or {}
    total = r.get("total_ratio") or 0
    five = (r.get("ssr_ratio") or 0) + (r.get("ssr_rate_up_success_ratio")
                                        or 0)
    return five / total if total and five else None


def consolidated_five(rates):
    """The 5-star chance including pity, as the game states it."""
    r = (rates or {}).get("rates") or {}
    info = (rates or {}).get("total_rate_info") or {}
    total = r.get("total_ratio") or 0
    five = (info.get("total_ssr_pool_pct") or 0) + (
        info.get("total_ssr_rate_up_pool_pct") or 0)
    return five / total if total and five else None


def consolidated_four(rates):
    """The 4-star chance including pity, as the game states it."""
    r = (rates or {}).get("rates") or {}
    info = (rates or {}).get("total_rate_info") or {}
    total = r.get("total_ratio") or 0
    four = sum(info.get(key) or 0 for key in (
        "total_sr_pool_pct", "total_sr_rate_up_pool_pct",
        "total_sr_combatant_pool_pct", "total_sr_supporter_pool_pct"))
    return four / total if total and four else None


def schedule_matches(rates):
    """True when the schedule reproduces this banner's stated rate."""
    base, stated = base_rate(rates), consolidated_five(rates)
    if base is None or stated is None:
        return False
    return abs(1.0 / pulls_per_five(base) - stated) <= SCHEDULE_TOLERANCE


# The families with a 50/50, for one whose rates have not been read
# yet: the Probabilities notices give one to both Combatant rate-ups
# and to nothing else. An import read before any capture would
# otherwise count no 50/50 at all. Once a banner's rates are read,
# they decide.
FIFTY_FIFTY_POOLS = frozenset({"pickup_combatant",
                               "pickup_combatant_rerun"})


def has_fifty_fifty(rates):
    """Whether a banner splits its 5-star chance with a rate-up.

    A Combatant rate-up does, between `ssr_rate_up_success_ratio` and
    `ssr_ratio`. A Partner rate-up and the Prism Module put all of it on
    the target, and a Normal Rescue has no target to split it with.
    """
    r = (rates or {}).get("rates") or {}
    return bool(r.get("ssr_rate_up_success_ratio")) and bool(
        r.get("ssr_ratio"))


# (base rate) -> [odds of the total pulls k 5-stars took], k = 0, 1, ...
# Built one 5-star at a time and kept for the session, so a new 5-star
# costs one step rather than the whole table.
_SUM_ODDS = {}


def _sum_odds(base, count):
    table = _SUM_ODDS.setdefault(base, [[1.0]])
    step = cycle_odds(base)
    while len(table) <= count:
        prev = table[-1]
        out = [0.0] * (len(prev) + HARD_PITY)
        for total, p in enumerate(prev):
            if p < 1e-18:
                continue
            for n in range(1, HARD_PITY + 1):
                out[total + n] += p * step[n]
        table.append(out)
    return table[count]


def luckier_than(pities, base):
    """The share of players who needed MORE pulls for as many 5-stars.

    Exact under the schedule: the pulls behind `len(pities)` 5-stars are
    a sum of that many independent cycles, and this is the chance that
    sum comes out above this history's -- half of any tie counting as
    luckier, so a history that took exactly the typical number of pulls
    sits in the middle rather than at one end.
    """
    if not pities or not base:
        return None
    odds = _sum_odds(base, len(pities))
    took = sum(pities)
    above = sum(odds[took + 1:])
    same = odds[took] if took < len(odds) else 0.0
    return above + same / 2


def luck_rank(luckier):
    """`Top 12%` or `Bottom 27%`, from `luckier_than`'s share.

    **Named from whichever end the history sits nearer**, so the number
    is always the small one and the word says which way is good: a bare
    `Top 93%` would read as praise and mean the opposite. The middle
    itself is `Top 50%`. Under 1% it takes a decimal, `Top 0.4%`, and
    under a tenth reads `<0.1%` rather than rounding to a `0%` nobody
    can be in.
    """
    if luckier is None:
        return None
    word, share = ("Top", 1 - luckier) if luckier >= 0.5 else (
        "Bottom", luckier)
    # Decided on the tenths: rounding to whole percents first would put
    # 0.8% at `1%` before the decimal was ever reached.
    tenths = int(1000 * share + 0.5)
    if tenths >= 10:
        return "%s %d%%" % (word, int(100 * share + 0.5))
    return "%s %s" % (word, "<0.1%" if tenths < 1
                      else "%.1f%%" % (tenths / 10))


# ------------------------------------------------------------- the pulls

WON = "Won"
LOST = "Lost"
GUARANTEED = "Guaranteed"
# The rate-up unit, after a stretch where nobody can say whether the
# last 50/50 was lost -- a win or a guarantee, and no telling which.
RATE_UP = "Rate-up"
UNKNOWN = "?"


class Pull:
    """One pull, with everything the tab shows about it."""

    __slots__ = ("pool", "number", "at", "res_id", "stars", "pity",
                 "gacha_id", "featured", "outcome", "source")

    def __init__(self, **fields):
        for name in self.__slots__:
            setattr(self, name, fields.get(name))


class PoolStats:
    """What one pool's history adds up to."""

    def __init__(self):
        self.pulls = 0
        self.fives = 0
        self.fours = 0
        self.unknown = 0
        # Every 5-star's pity, oldest first, and whether the first of
        # them is only a floor -- a history that starts mid-cycle cannot
        # say how many pulls came before its first line.
        self.five_pities = []
        self.first_partial = True
        self.four_pities = []
        self.pity_now = 0
        self.avg_pity = None
        self.expected_pity = None
        self.luckier_than = None
        self.four_avg = None
        self.four_expected = None
        # None where the pool has no 50/50 to count.
        self.won = self.lost = self.guaranteed = None
        self.game_pity = None
        self.game_updated = None
        self.behind = False
        self.read_at = None
        self.first_at = None
        self.last_at = None


class Pool:
    def __init__(self, pool):
        self.pool = pool
        self.label = pool_label(pool)
        self.pulls = []                  # oldest first
        self.stats = PoolStats()


class History:
    """Every pool's pulls and stats, plus what went wrong reading them."""

    def __init__(self):
        self.pools = {}
        self.notes = []
        self.rates = {}
        self.pity = {}
        self.batches = []

    def ordered(self):
        known = [self.pools[p] for p in POOL_ORDER if p in self.pools]
        rest = sorted((p for p in self.pools if p not in POOL_ORDER))
        return known + [self.pools[p] for p in rest]

    @property
    def total(self):
        return sum(len(p.pulls) for p in self.pools.values())


# ------------------------------------------------------------ batches

def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _int_list(value):
    """A list of ints out of a list, or out of the JSON text the wire
    sends in its place -- `"[1009,30117]"`, not a list."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        n = _int(item)
        if isinstance(item, bool) or (not n and item not in (0, "0")):
            return []
        out.append(n)
    return out


def batch_from_record(record, source=None):
    """A wire record, or a batch already in this module's shape, as a
    batch: one `gacha/run`'s pulls, in the order they came out."""
    if not isinstance(record, dict):
        return None
    gacha_id = str(record.get("gacha_id") or "") or None
    reward = _int_list(record.get("reward"))
    at = _int(record.get("createAt"))
    pool = record.get("pool") or (pool_of(gacha_id) if gacha_id else None)
    if not reward or at <= 0 or not pool:
        return None
    prism = _int_list(record.get("prism"))
    rid = record.get("id")
    return {
        "id": str(rid) if rid not in (None, "") else None,
        "gacha_id": gacha_id,
        "pool": str(pool),
        "createAt": at,
        "reward": reward,
        "prism": prism if len(prism) == len(reward) else None,
        "from": source or record.get("from"),
    }


# hub-czn named its banners from the id, lossily: every Combatant
# rate-up, reruns included, became one name, and so did anything with
# `supporter` in it. The rest it title-cased, which reverses exactly.
HUB_CZN_POOLS = {
    "Seasonal Combatant Rescue Rate-Up": "pickup_combatant",
    "Seasonal Partner Rescue Rate-Up": "pickup_supporter",
    "Gacha Pickup Supporter": "pickup_supporter",
}


def _hub_czn_banner(name):
    """(pool, gacha_id) for one of hub-czn's banner names. The id is
    None where the name no longer carries it."""
    name = str(name or "").strip()
    if name in HUB_CZN_POOLS:
        return HUB_CZN_POOLS[name], None
    gacha_id = "_".join(name.lower().split())
    if not gacha_id:
        return None, None
    return pool_of(gacha_id), (gacha_id if gacha_id.startswith("gacha_")
                               else None)


class ImportRejected(ValueError):
    """A file this program cannot read a history out of."""


def parse_import(data, source):
    """(batches, skipped) out of any history file this program reads.

    * hub-czn's `Export JSON`: a list of banners, each with its pulls.
      Its rarities, pities and 50/50 flags are its own conclusions and
      are ignored -- every one is worked out again here.
    * A file of the game's own records: hub-czn's and its Tkinter
      predecessor's `rescue_records_*.json`, or this program's
      `captured.json` from another install.
    * This program's own export, and its `imported.json`.

    `skipped` counts pulls that could not be placed in time.
    """
    if isinstance(data, list) and data and all(
            isinstance(b, dict) and "banner_name" in b and "pulls" in b
            for b in data):
        return _parse_hub_czn(data, source)
    if isinstance(data, dict) and isinstance(data.get("batches"), list):
        rows = data["batches"]
    elif isinstance(data, dict) and isinstance(data.get("records"), list):
        rows = data["records"]
    elif isinstance(data, list) and data and all(
            isinstance(r, dict) and "gacha_id" in r for r in data):
        rows = data
    elif isinstance(data, dict) and "characters" in data and "summary" in data:
        raise ImportRejected(
            "This is hub-czn's older summary export. It lists only the "
            "4-star and 5-star pulls, so the history cannot be rebuilt "
            "from it.")
    else:
        raise ImportRejected(
            "No pull history found. Gacha History reads hub-czn's Export "
            "JSON, a file of the game's own records, or its own export.")
    batches, skipped = [], 0
    for row in rows:
        batch = batch_from_record(row, source)
        if batch is None:
            skipped += 1
        else:
            batches.append(batch)
    return batches, skipped


def _parse_hub_czn(banners, source):
    batches, skipped = [], 0
    for banner in banners:
        pool, gacha_id = _hub_czn_banner(banner.get("banner_name"))
        pulls = banner.get("pulls") if isinstance(banner.get("pulls"),
                                                  list) else []
        if pool is None:
            skipped += len(pulls)
            continue
        # A batch is every pull one banner stamped with one second, in
        # the order hub-czn numbered them -- which is the order they
        # came out of the game.
        by_second = {}
        for pull in sorted((p for p in pulls if isinstance(p, dict)),
                           key=lambda p: _int(p.get("pull_number"))):
            at, res_id = _int(pull.get("timestamp")), _int(pull.get("res_id"))
            if at <= 0 or res_id <= 0:
                skipped += 1
                continue
            by_second.setdefault(at, []).append(res_id)
        for at, reward in by_second.items():
            batches.append({"id": None, "gacha_id": gacha_id, "pool": pool,
                            "createAt": at, "reward": reward, "prism": None,
                            "from": source})
    return batches, skipped


def _batch_key(batch):
    return (batch["pool"], batch["createAt"])


def _same_content(batch):
    return (batch["createAt"], tuple(batch["reward"]))


# ----------------------------------------------------------- the files

class StoreError(Exception):
    """A history file that could not be written safely. The file on
    disk is unchanged."""


def folder_in(snapshots):
    return Path(snapshots) / FOLDER


def backup_of(path):
    return path.with_name(path.name + BACKUP)


def temp_of(path):
    return path.with_name(path.name + TEMP)


def read_store(path):
    """(data, note) for one history file.

    **Falls back to the backup** where the file is missing or will not
    parse. The write renames the file to its backup BEFORE putting the
    new copy in its place, so a crash between the two leaves only the
    backup -- and reading nothing there would show an empty history and
    let the next write start one.
    """
    path = Path(path)
    tried = []
    for candidate in (path, backup_of(path)):
        if not candidate.exists():
            continue
        try:
            with open(candidate, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            tried.append("%s: %s" % (candidate.name, e))
            continue
        if not isinstance(data, dict):
            tried.append("%s: not a history file" % candidate.name)
            continue
        note = None
        if candidate != path:
            note = ("%s is missing or unreadable; showing its backup"
                    % path.name)
        return data, note
    return {}, ("; ".join(tried) if tried else None)


def _replace(src, dst):
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(REPLACE_WAIT)


def _rows_kept(before, after, key):
    """Problems, where a row held before is missing or changed after."""
    held = {key(row): row for row in after}
    problems = []
    for row in before:
        k = key(row)
        if k not in held:
            problems.append("%r went missing" % (k,))
        elif held[k] != row:
            problems.append("%r changed" % (k,))
    return problems


def write_verified(path, data, rows_field, must_hold, key):
    """Write `data` over `path` by way of a checked copy.

    1. The merged data goes to `<name>.tmp`, flushed to disk.
    2. It is read back. It must equal what was meant to be written, and
       every row of `must_hold` -- what the file held before, and what
       was added -- must be in its `rows_field` unchanged, matched by
       `key`.
    3. `<name>` becomes `<name>.bak`. **The rename replaces the older
       backup**, which is how the older one goes: there is only ever the
       one, and it is the file as it stood before this write.
    4. The copy becomes `<name>`.

    Anything failing before step 3 leaves `<name>` exactly as it was, and
    raises StoreError saying what.
    """
    path = Path(path)
    tmp, bak = temp_of(path), backup_of(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, encoding="utf-8") as f:
            back = json.load(f)
    except (OSError, ValueError) as e:
        _discard(tmp)
        raise StoreError("the copy of %s could not be written: %s"
                         % (path.name, e))
    rows = back.get(rows_field) if isinstance(back, dict) else None
    problems = [] if back == data else ["the copy does not read back as "
                                        "what was written"]
    if not isinstance(rows, list):
        problems.append("the copy holds no %s" % rows_field)
    else:
        problems += _rows_kept(must_hold, rows, key)
    if problems:
        _discard(tmp)
        raise StoreError("the copy of %s failed its check (%s), so %s is "
                         "unchanged" % (path.name, "; ".join(problems[:3]),
                                        path.name))
    try:
        if path.exists():
            _replace(path, bak)
        _replace(tmp, path)
    except OSError as e:
        # The file went to its backup and the copy could not follow:
        # put it back rather than leave the history on the backup alone.
        if not path.exists() and bak.exists():
            try:
                _replace(bak, path)
            except OSError:
                pass
        _discard(tmp)
        raise StoreError("%s could not be replaced: %s" % (path.name, e))


def _discard(path):
    try:
        Path(path).unlink()
    except OSError:
        pass


def merge_import(folder, batches):
    """Add imported batches to `imported.json`. Returns (added, known)
    counted in PULLS: `known` were already imported."""
    path = folder_in(folder) if Path(folder).name != FOLDER else Path(folder)
    target = path / IMPORTED
    held, note = read_store(target)
    if note and not held:
        raise StoreError("%s could not be read (%s), so nothing was added "
                         "to it" % (IMPORTED, note))
    before = [b for b in (batch_from_record(r) for r in
                          held.get("batches") or []) if b is not None]
    have = {_batch_key(b) for b in before} | {
        _same_content(b) for b in before}
    fresh, known = [], 0
    for batch in batches:
        if _batch_key(batch) in have or _same_content(batch) in have:
            known += len(batch["reward"])
            continue
        have.add(_batch_key(batch))
        have.add(_same_content(batch))
        fresh.append(batch)
    if fresh:
        merged = sorted(before + fresh,
                        key=lambda b: (b["createAt"], b["pool"]))
        write_verified(target, {"kind": IMPORT_KIND, "version": VERSION,
                                "batches": merged},
                       "batches", before + fresh, _batch_key)
    return sum(len(b["reward"]) for b in fresh), known


def export(history, path):
    """Write every batch the history holds, and the rates it knows, to a
    file this program can import again."""
    data = {
        "kind": EXPORT_KIND,
        "version": VERSION,
        "exported": datetime.now().isoformat(timespec="seconds"),
        "batches": history.batches,
        "rates": history.rates,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return sum(len(b["reward"]) for b in history.batches)


# ------------------------------------------------------------- reading

def load(folder, now=None):
    """Everything in the history folder, merged and worked out.

    `folder` is the snapshots folder or the history folder itself.
    """
    folder = Path(folder)
    if folder.name != FOLDER:
        folder = folder_in(folder)
    history = History()
    captured, note = read_store(folder / CAPTURED)
    if note:
        history.notes.append(note)
    imported, note = read_store(folder / IMPORTED)
    if note:
        history.notes.append(note)

    history.rates = captured.get("rates") if isinstance(
        captured.get("rates"), dict) else {}
    history.pity = captured.get("pity") if isinstance(
        captured.get("pity"), dict) else {}
    read = captured.get("read") if isinstance(captured.get("read"),
                                              dict) else {}

    game = [b for b in (batch_from_record(r, "game") for r in
                        captured.get("records") or []) if b is not None]
    # **The game's own record wins wherever it covers the same pulls.**
    # An import is matched to a captured record by the record's id, by
    # its pool and second, or by its second and every unit in it -- the
    # last because hub-czn filed the Normal Partner Rescue under the
    # same name as the Partner rate-up, and only the units can say two
    # batches in different pools are one.
    ids = {b["id"] for b in game if b["id"]}
    slots = {_batch_key(b) for b in game}
    contents = {_same_content(b) for b in game}
    kept = []
    for raw in imported.get("batches") or []:
        batch = batch_from_record(raw)
        if batch is None:
            continue
        if (batch["id"] and batch["id"] in ids) or _batch_key(batch) in \
                slots or _same_content(batch) in contents:
            continue
        kept.append(batch)
    history.batches = sorted(game + kept, key=_order)
    # Pulls a file filed under the rate-up while a rerun ran beside it
    # may be the rerun's, whose pity is counted apart. Said, because
    # nothing in the file can settle it.
    doubtful = sum(len(b["reward"]) for b in kept
                   if not b["gacha_id"]
                   and beside_a_rerun(b["pool"], b["createAt"]))
    if doubtful:
        history.notes.append(
            "%d imported pull%s made while a rerun ran beside the "
            "rate-up, and may be the rerun's"
            % (doubtful, " was" if doubtful == 1 else "s were"))

    tiers = tiers_from_rates(history.rates)
    by_pool = {}
    for batch in history.batches:
        by_pool.setdefault(batch["pool"], []).append(batch)
    for pool, batches in by_pool.items():
        history.pools[pool] = _work_out(pool, batches, tiers, history)
    # Pools the game counts pulls for and no history has reached yet --
    # read-only knowledge of the pity, and a note that the list is
    # there to be read.
    for name in history.pity:
        pool = name[len("gacha_pity_"):] if name.startswith(
            "gacha_pity_") else None
        if pool and pool not in history.pools:
            history.pools[pool] = _work_out(pool, [], tiers, history)
    for gacha_id, when in read.items():
        entry = history.pools.get(pool_of(gacha_id))
        if entry and (entry.stats.read_at is None
                      or str(when) > entry.stats.read_at):
            entry.stats.read_at = str(when)
    now = time.time() if now is None else now
    for entry in history.pools.values():
        _judge_freshness(entry, now)
    return history


def _order(batch):
    rid = batch.get("id")
    return (batch["createAt"], _int(rid) if rid else 0)


def _pool_rates(pool, rates):
    """The newest rates any banner of this pool was read with."""
    best = None
    for gacha_id, entry in rates.items():
        if pool_of(gacha_id) != pool or not isinstance(entry, dict):
            continue
        if best is None or str(entry.get("seen") or "") > str(
                best.get("seen") or ""):
            best = entry
    return best


def _work_out(pool, batches, tiers, history):
    entry = Pool(pool)
    stats = entry.stats
    rates = _pool_rates(pool, history.rates)
    fifty = (has_fifty_fifty(rates) if rates
             else pool in FIFTY_FIFTY_POOLS)
    record = history.pity.get(pity_record_name(pool))
    if isinstance(record, dict):
        stats.game_pity = _int(record.get("pity_ssr_count"))
        stats.game_updated = _int(record.get("updateAt")) or None
        # The record is created by the pool's first pull ever, so a
        # history reaching back that far has no cycle cut short.
        created = _int(record.get("createAt"))
        if batches and created and batches[0]["createAt"] <= created + \
                BEHIND_SLACK:
            stats.first_partial = False

    pity = four = 0
    # None: nobody can say whether the last 50/50 was lost.
    guaranteed = None
    number = 0
    for batch in batches:
        # An imported batch that lost its banner is dated back to one
        # -- see `dated_banner`. The game's own records never need it.
        featured = featured_of(batch["gacha_id"] or dated_banner(
            pool, batch["createAt"]))
        for res_id in batch["reward"]:
            number += 1
            pity += 1
            four += 1
            stars = stars_of(res_id, tiers)
            outcome = None
            if stars is None:
                stats.unknown += 1
            elif stars == 5:
                stats.fives += 1
                stats.five_pities.append(pity)
                pity = 0
                if fifty:
                    outcome, guaranteed = _fifty_fifty(res_id, featured,
                                                       guaranteed)
            elif stars == 4:
                stats.fours += 1
                stats.four_pities.append(four)
                four = 0
            entry.pulls.append(Pull(
                pool=pool, number=number, at=batch["createAt"],
                res_id=res_id, stars=stars,
                pity=stats.five_pities[-1] if stars == 5 else pity,
                gacha_id=batch["gacha_id"], featured=featured,
                outcome=outcome, source=batch.get("from")))
    stats.pulls = number
    stats.pity_now = pity
    if batches:
        stats.first_at = batches[0]["createAt"]
        stats.last_at = batches[-1]["createAt"]

    complete = stats.five_pities[1:] if stats.first_partial else \
        stats.five_pities
    if complete:
        stats.avg_pity = sum(complete) / len(complete)
    fours = stats.four_pities[1:] if stats.first_partial else \
        stats.four_pities
    if fours:
        stats.four_avg = sum(fours) / len(fours)
    if schedule_matches(rates):
        base = base_rate(rates)
        stats.expected_pity = pulls_per_five(base)
        stats.luckier_than = luckier_than(complete, base)
    four_rate = consolidated_four(rates)
    if four_rate:
        stats.four_expected = 1.0 / four_rate
    if fifty:
        outcomes = [p.outcome for p in entry.pulls if p.outcome]
        stats.won = outcomes.count(WON)
        stats.lost = outcomes.count(LOST)
        stats.guaranteed = outcomes.count(GUARANTEED)
    return entry


def _fifty_fifty(res_id, featured, guaranteed):
    """(outcome, guaranteed after) for one 5-star on a 50/50 banner.

    **After a lost 50/50 the next 5-star is the rate-up**, whichever
    banner it lands on -- so that one is known to be a guarantee even
    where the history no longer says which unit its banner featured.
    One the history shows was NOT the rate-up is reported as the loss it
    is rather than as the guarantee the rule promised: the disagreement
    is worth seeing.
    """
    if featured is not None and res_id != featured:
        return LOST, True
    if guaranteed:
        return GUARANTEED, False
    if featured is None:
        return UNKNOWN, None
    return (WON if guaranteed is False else RATE_UP), False


def _judge_freshness(entry, now):
    """Mark a pool whose game counter has moved past its history.

    Only a pool whose list has been read at least once: a banner family
    nobody has opened -- a finished beginner selection, say -- may have
    no screen left to open, and asking for it would never stop.
    """
    stats = entry.stats
    if not stats.game_updated or not stats.read_at:
        return
    if now - stats.game_updated > GAME_KEEPS_DAYS * 86400:
        return
    newest = stats.last_at or 0
    stats.behind = stats.game_updated > newest + BEHIND_SLACK
