"""What a Galactic Disaster season's Chaos runs pay, for the Checklist's
season estimate: the figures the program ships with, and when a
player's own recorded runs take their place.

**A run's take is set, but for its marked fights.** `docs/chaos_runs.py`
measures it off every run the capture records:

- each BOSS floor pays a set amount, and the floors belong to the season
  PART: season 4's part 2 had bosses on floors 17 and 34, its part 3 a
  third on floor 37;
- each MARKED fight pays a set amount -- the Rare Species 48, the Aether
  Eater 72 -- and only how many a run meets is chance;
- **each Memory Resonance Amplification node** of the season's skill
  tree, the Environment Variables, adds 1% to every payout, rounded up
  (`amplified`) -- every one but the bosses the season marks `flat`:
  season 5's floor-31 boss paid 60 at 0 nodes and at 5, where the
  floor-17 boss paid 144 and then 152.

**The shipped figures are at base**, no node bought, and every run of a
part counts at the nodes the part's tree holds by its end
(`season_nodes`). The nodes are bought with Memory of Light, which the
runs pay, and a part's are bought within its first few runs; those few
runs short of the whole are left out, under 1% of a season at one run a
day. So a season pays its Chaos, at `R` runs a day,

    R * sum over parts of days(part) * (bosses(part) + marks per run),
        each payout at the part's nodes

**A part's nodes** are the game client's tree, which says which part
each node opens with; past the parts it lists, what the season before
added at those parts; with no tree read, the shipped `nodes`, the same
way. A part's own runs raise its count to the most nodes one had: every
run records the nodes in force (`run_nodes`).

**The player's own runs can overrule the shipped figures**, each payout
read back to base at its own run's nodes first (`base_of`), so a run
made at 5 nodes speaks for a part at 13. On rules that trust the shipped
figures less the longer the program goes without an update, counted in
whole seasons (`staleness`):

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
5. A season no figures were shipped for borrows the newest one's, a map
   of another season: its marked fights are the player's own count once
   they have `UNSHIPPED_RATE_RUNS` whole runs of it, none inside a
   `RATE_EVENTS` window.

A mark's amount follows the bosses' rules, over the whole season rather
than a part. A part never measured borrows the nearest measured part --
the one before it, else the one after.

**A lost run counts as a whole one** when a boss had already paid and
no non-boss fight was left on its map: every mark it could meet, it met.
What it would have paid besides is `missed`.

**Only the live season's own Chaos counts** (`is_current`). A past
season's Chaos pays the live currency too, at lower amounts -- 135 a
boss and 45 a Rare Species in the past ones captured in season 4, at
its 25 nodes, against 180 and 60 -- and the estimate is of the live
one.

No Tk: this takes plain data, and `docs/chaos_runs.py` reads it too.
"""

import collections
import datetime
import math
import re

from game_client import AMPLIFY_GROUP
from version import RELEASED_IN, RELEASED_ON

# The shipped figures at base, no amplification node bought, measured
# off the maintainer's own runs by `docs/chaos_runs.py` and refreshed by
# the release step.
#
# `bosses` is {part: {boss floor: amount}}; `flat` the boss floors no
# node amplifies; `nodes` the amplification nodes the season's tree
# holds by the end of each part, part 1 first, for where no client tree
# is read (`season_nodes`); `marks` is {mark: (amount a fight, marked
# fights a whole run)}. Season 4's first part was never captured, so it
# borrows the second's.
SHIPPED = {
    "disaster_s04": {
        "bosses": {2: {17: 144, 34: 144},
                   3: {17: 144, 34: 144, 37: 60}},
        "flat": (37,),
        "nodes": (13, 19, 25),
        "marks": {"k5": (48, 1.43), "e": (72, 0.36), "b1": (0, 0.36),
                  "b1+k5": (48, 0.07)},
    },
    "disaster_s05": {
        "bosses": {1: {17: 144, 28: 144, 31: 60}},
        "flat": (31,),
        "nodes": (13,),
        # Over 3 whole runs of part 1.
        "marks": {"k5": (48, 1.67), "b1": (0, 0.67), "b1+k5": (48, 0.33)},
    },
}

# A run's Memory Resonance Amplification nodes, off the Zero System
# effects it records (`capture.manager._zero_effects`): the group the
# client's amplification nodes carry (`game_client.AMPLIFY_GROUP`), of
# its own season's tree, `zero_season_s<N>_skill_...` -- a past season's
# Chaos carries that season's tree, which raises nothing of the live
# currency. Each node is one effect.
SEASON_SKILL = re.compile(r"zero_season_s(\d+)_skill_")

# Rule 3: the share of a floor's payouts the highest must make up to
# stand alone.
TOP_SHARE = 0.7

# Rule 4: how many whole runs since the release make the player's own
# rates. A run's marks pay about 90 either side of their mean, so two
# hundred runs pin the mean to about 6 a run -- some 400 on a season.
RATE_RUNS = 200

# Rule 5: how many whole runs of a season no figures were shipped for
# make the player's own rates. Fewer than rule 4 asks: the borrowed
# rates are another map's -- season 4 met 1.43 Rare Species a run and
# season 5 3.0, some 75 a run apart -- where thirty runs pin the mean
# to about 16 a run, at rule 4's 90 either side.
UNSHIPPED_RATE_RUNS = 30

# Every Chaos, by the stage id its clear names, and the season it came
# with: each Galactic Disaster's own, named in the game's update notes,
# then the base game's, which came with none. A Chaos keeps its stage id
# whichever door it is entered by -- its own screen, the Galactic
# Disaster's or the Zero System. Its `chaos_id` on the wire is beside
# each: a run records both. The game client's names go over these
# (`chaos_names`); these name what no client read holds.
CHAOS_NAMES = {
    50000: ("Laboratory 0", "disaster_s01"),                 # chaos_06
    60000: ("Burning Life", "disaster_s02"),                 # chaos_07
    70000: ("Theater of Illusions", "disaster_s03"),         # chaos_08
    80000: ("The Kaleidoscope Hatchery", "disaster_s04"),    # chaos_09
    100000: ("Celestial Bulwark", "disaster_s05"),           # chaos_10
    110000003: ("The Blue Pot", None),                       # chaos_01
    115000001: ("Twin Star's Shadow", None),                 # chaos_02
    120000002: ("City of Mist", None),                       # chaos_03
    120000001: ("Swamp of Judgment", None),                  # chaos_04
    120000004: ("The Foretold Ruin", None),                  # chaos_05
}

# The Zero System's special options, which a map's codex carries, by
# what they do. Each Galactic Disaster's own is the Effect chosen when
# the codex is made, adding its Chaos's features to a base-game Chaos;
# the next season's is on offer in its preseason. Season 5's turns every
# floor after the first boss into Elite and Unidentified Area floors and
# adds a Core of Discord style boss -- fewer ordinary fights a run, so
# fewer marked ones, at an unmoved rate a fight. `v1_01` to `v1_04` are
# Divine Intervention, one god's each, beside the Effect or without one;
# the wire spells Kyrken `circen` and Sekred `secred`. `v1_05` to `v1_09`
# are seasons 1 to 5's Effects. Each by the game's name for it, which
# the client's own goes over (`zero_special_name`).
# `docs/capture_pipeline.md`, *The Zero System's codex*.
ZERO_SPECIALS = {
    "zero_orb_special_v1_01": "Kyrken's Oracle",
    "zero_orb_special_v1_02": "Diallos's Glory",
    "zero_orb_special_v1_03": "Sekred's Breath",
    "zero_orb_special_v1_04": "Nihilum's Gaze",
    "zero_orb_special_v1_05": "Forbidden Catalyst",
    "zero_orb_special_v1_06": "Seed of Karmic Fire",
    "zero_orb_special_v1_07": "A Song Rippling Through the Stars",
    "zero_orb_special_v1_08": "Shattered Light and Claw",
    "zero_orb_special_v1_09": "Promise Upon the Snow",
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


def chaos_names():
    """{stage id: (name, season)}: the game client's
    (`game_client.known_chaos_names`) over `CHAOS_NAMES`, so a stage a
    patch adds or renames reads as the game names it, and the table
    names what no client read and no shipped table holds."""
    import game_client
    return {**CHAOS_NAMES, **game_client.known_chaos_names()}


def chaos_name(run):
    """The Chaos a run was in, by name: its stage id's, else the
    season's own where it came in through the Galactic Disaster; `?`
    where the record cannot say."""
    names = chaos_names()
    named = names.get(run.get("stage"))
    if named:
        return named[0]
    if is_current(run):
        for name, season in names.values():
            if season == run.get("season"):
                return name
    return str(run.get("stage") or "?")


def zero_special_name(special):
    """A Zero System special option by name: the game client's, else
    `ZERO_SPECIALS`', else its id."""
    import game_client
    return (game_client.known_zero_specials().get(special)
            or ZERO_SPECIALS.get(special) or special)


def payouts(run):
    """(floor, spot, mark, amount) for every payout a run took."""
    out = []
    for entry in run.get("paid") or ():
        if (isinstance(entry, (list, tuple)) and len(entry) >= 5
                and isinstance(entry[4], int)):
            out.append((entry[0], entry[1], entry[2] or "", entry[4]))
    return out


def payout_kinds(runs, season):
    """{amount: {(spot, mark), ...}}: what each amount was seen paying
    for in the season's runs -- a boss (`BOSS`, "") or a marked fight
    (its spot, its mark). What `recovery` reads an unseen payout by."""
    kinds = collections.defaultdict(set)
    for run in readable(runs):
        if run.get("season") != season:
            continue
        for _floor, spot, mark, amount in payouts(run):
            kinds[amount].add((BOSS, "") if spot == BOSS else (spot, mark))
    return dict(kinds)


# A spot `unseen` holds that can be a fight with a mark: a boss is
# placed by its amount alone.
UNSEEN_FIGHTS = ("BATTLE", "ELITE", "UNKNOWN")


def recovery(run, kinds):
    """(recovered, unknown) for a run some of which no capture saw.

    **The clear restates what the run paid** (`restated`), so every
    amount it holds and no capture saw was taken while none watched.
    Each is read by `kinds` (`payout_kinds`): one paid only at bosses
    goes on an unseen boss, placed on its floor; one paid only on a
    mark is that mark's, on a fight no capture saw. `recovered` is
    those as payouts, `(floor or None, spot, mark, amount)`.

    `unknown` says what stays unknown, in words: an amount nothing
    explains or that could be either, and each fight no capture saw
    that no recovered payout accounts for -- one can carry a mark
    that pays nothing (`b1`), so its marks are not known, and its run
    is partial for the mark rates (`is_partial`). A run whose clear
    restated nothing recovers nothing."""
    recovered, unknown = [], []
    restated = run.get("restated")
    unseen = [tuple(row) for row in run.get("unseen") or ()
              if isinstance(row, (list, tuple)) and len(row) >= 3]
    bosses = [row for row in unseen if row[2] == BOSS]
    fights = [row for row in unseen if row[2] in UNSEEN_FIGHTS]
    if isinstance(restated, list):
        seen = collections.Counter(amount for *_rest, amount in payouts(run))
        for amount in restated:
            if seen[amount]:
                seen[amount] -= 1
                continue
            options = kinds.get(amount) or set()
            marks = sorted(option for option in options if option[0] != BOSS)
            if (BOSS, "") in options and not marks and bosses:
                row = bosses.pop(0)
                recovered.append((row[1], BOSS, "", amount))
            elif marks and (BOSS, "") not in options and fights:
                spot, mark = marks[0]
                fights.pop(0)
                recovered.append((None, spot, mark, amount))
            else:
                unknown.append("%d unexplained" % amount)
    if fights:
        unknown.append("%d fight(s) unseen (%s)" % (len(fights), ", ".join(
            "%s %s" % (row[1], row[2].lower()) for row in fights)))
    return recovered, unknown


def is_partial(run):
    """Whether a run's fights are not all known: some were fought while
    no capture watched and nothing accounts for them (`recovery`). Its
    marks are then not all counted, and a mark's rate leaves it out."""
    return any(isinstance(row, (list, tuple)) and len(row) >= 3
               and row[2] in UNSEEN_FIGHTS for row in run.get("unseen") or ())


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
    """The shipped {floor: amount} for a part, at base: its own, else the
    nearest measured part before it, else after it."""
    table = entry.get("bosses") or {}
    if part in table:
        return dict(table[part])
    below = [p for p in table if p < part]
    above = [p for p in table if p > part]
    pick = max(below) if below else (min(above) if above else None)
    return dict(table[pick]) if pick is not None else {}


def flat_floors(season, shipped=SHIPPED):
    """The boss floors of `season`'s Chaos no node amplifies: its shipped
    entry's `flat`, or the entry it borrows."""
    return set(shipped_entry(season, shipped).get("flat") or ())


def amplified(amount, nodes):
    """What `amount` at base pays with `nodes` amplification nodes in
    force: 1% a node, rounded up -- `ceil(base * (100 + n) / 100)`,
    which every captured payout fits."""
    if not nodes:
        return amount
    # Rounded first: a settled amount can be a mean, and a mean times
    # the factor can land a hair above a whole number in floating
    # point, which a bare ceil takes one higher.
    return math.ceil(round(amount * (100 + nodes) / 100, 6))


def base_of(amount, nodes):
    """The base a payout at `nodes` nodes was amplified from: the whole
    amount `amplified` takes to it, else the plain quotient, for a payout
    the rule does not fit."""
    if not nodes:
        return amount
    whole = math.floor(amount * 100 / (100 + nodes))
    if amplified(whole, nodes) == amount:
        return whole
    return amount * 100 / (100 + nodes)


def run_nodes(run, number=None):
    """How many of its own season's amplification nodes a run had in
    force (`AMPLIFY_GROUP`), the season `number` where given; None for a
    run filed before runs kept their effects."""
    if "effects" not in run:
        return None
    number = season_number(run.get("season")) if number is None else number
    held = 0
    for entry in run.get("effects") or ():
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        own = SEASON_SKILL.match(str(entry[1]))
        if entry[0] == AMPLIFY_GROUP and own and int(own.group(1)) == number:
            held += 1
    return held


def _tree(season, shipped):
    """[a season's amplification nodes by the end of each part]: the
    game client's tree, else the shipped `nodes` of the season's own
    entry; empty where neither holds one."""
    import game_client
    held = game_client.known_season_nodes().get(season)
    if held:
        return list(held)
    return list((shipped.get(season) or {}).get("nodes") or ())


def _extended(season, shipped):
    """[a season's amplification nodes by the end of each part]: its tree
    (`_tree`), and past the parts it lists, the last one plus what the
    nearest earlier season with a tree added at those parts, that one
    extended the same way. With no tree of its own, that season's counts
    whole. Empty where no season has a tree."""
    own, before = _tree(season, shipped), []
    number = season_number(season)
    for earlier in range((number or 1) - 1, 0, -1):
        if _tree("disaster_s%02d" % earlier, shipped):
            before = _extended("disaster_s%02d" % earlier, shipped)
            break
    if not own:
        return before
    for part in range(len(own) + 1, len(before) + 1):
        own.append(own[-1] + before[part - 1] - before[part - 2])
    return own


def season_nodes(live, parts=None, runs=(), starts=None, shipped=SHIPPED):
    """[the amplification nodes each of `live`'s parts holds by its end],
    parts 1 to `parts` (default: as many as `_extended` gives, at least
    1): the client's tree or the shipped `nodes`, carried past the parts
    they list by the season before. A part's own runs (`runs`, dated by
    `starts`) raise its count to the most nodes one had, and a part
    never holds fewer than the one before; a part past every count
    holds the last."""
    counts = _extended(live, shipped)
    parts = parts or max(len(counts), 1)
    seen = collections.defaultdict(int)
    for run in readable(runs):
        held = run_nodes(run) if is_current(run) \
            and run.get("season") == live else None
        part = run_part(run, live, starts) if held else None
        if part:
            seen[part] = max(seen[part], held)
    out = []
    for part in range(1, parts + 1):
        count = counts[min(part, len(counts)) - 1] if counts else 0
        out.append(max(count, seen.get(part, 0), out[-1] if out else 0))
    return out


def _nodes_of(run, live, starts, shipped, counts):
    """The nodes a run's payouts were made at: its own record of them,
    else its part's count -- one filed before runs kept their effects
    was most likely made with its part's tree bought. `counts` caches
    `season_nodes` by season."""
    held = run_nodes(run)
    if held is not None:
        return held
    season = run.get("season")
    if season not in counts:
        counts[season] = season_nodes(season, None, (), None, shipped)
    part = run_part(run, live, starts)
    tree = counts[season]
    if not isinstance(part, int) or part < 1 or not tree:
        return 0
    return tree[min(part, len(tree)) - 1]


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
    """{boss floor: amount at base} for one part of the live season, each
    payout the player saw read back to base at its own run's nodes."""
    expected = shipped_bosses(shipped_entry(live, shipped), part)
    wanted = _seasons_read(live, stale)
    seen, counts = collections.defaultdict(list), {}
    for run in runs:
        if (not is_current(run)
                or season_number(run.get("season")) not in wanted
                or run_part(run, live, starts) != part):
            continue
        nodes = _nodes_of(run, live, starts, shipped, counts)
        flat = flat_floors(run.get("season"), shipped)
        for floor, spot, _mark, amount in payouts(run):
            if spot == BOSS and isinstance(floor, int):
                seen[floor].append(amount if floor in flat
                                   else base_of(amount, nodes))
    return {floor: settle(expected.get(floor, 0), seen.get(floor, []), stale)
            for floor in sorted(set(expected) | set(seen))}


def mark_values(live, runs, shipped=SHIPPED, stale=0, starts=None):
    """{mark: amount a fight at base} for the live season, each payout
    the player saw read back to base at its own run's nodes."""
    expected = {mark: amount for mark, (amount, _rate)
                in (shipped_entry(live, shipped).get("marks") or {}).items()}
    wanted = _seasons_read(live, stale)
    seen, counts = collections.defaultdict(list), {}
    for run in runs:
        if (not is_current(run)
                or season_number(run.get("season")) not in wanted):
            continue
        nodes = _nodes_of(run, live, starts, shipped, counts)
        for _floor, spot, mark, amount in payouts(run):
            if mark and spot != BOSS:
                seen[mark].append(base_of(amount, nodes))
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


def _counted(runs):
    """The runs a mark's rate is counted over: whole, of the live
    season's own Chaos, every fight known, none inside a `RATE_EVENTS`
    window."""
    return [run for run in runs
            if is_current(run) and is_full(run) and not is_partial(run)
            and not in_rate_event(run["closed"])]


def mark_rates(live, runs, shipped=SHIPPED, stale=0, since=None):
    """({mark: marked fights a whole run}, how many runs made them).

    The shipped rates and None, unless rule 4 or rule 5 hands them to
    the player.
    """
    rates = {mark: rate for mark, (_amount, rate)
             in (shipped_entry(live, shipped).get("marks") or {}).items()}
    counted = []
    if stale >= 2:
        after = released_at() if since is None else since
        counted = [run for run in _counted(runs) if run["closed"] >= after]
    if len(counted) < RATE_RUNS:
        unshipped = live not in shipped
        counted = [run for run in _counted(runs)
                   if unshipped and run.get("season") == live]
        if len(counted) < UNSHIPPED_RATE_RUNS:
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
    dates the live season's runs where given. Every payout is at its
    part's nodes (`season_nodes`), the `flat` bosses at base.
    """
    if not shipped or not part_days:
        return None
    stale = staleness(live, released_in)
    runs = readable(runs)
    values = mark_values(live, runs, shipped, stale, starts)
    rates, _counted = mark_rates(live, runs, shipped, stale, since)
    nodes = season_nodes(live, len(part_days), runs, starts, shipped)
    flat = flat_floors(live, shipped)
    total = 0
    for part, days in enumerate(part_days, start=1):
        held = nodes[part - 1]
        bosses = sum(amount if floor in flat else amplified(amount, held)
                     for floor, amount in boss_table(
                         live, part, runs, starts, shipped, stale).items())
        marks = sum(amplified(values.get(mark, 0), held) * rate
                    for mark, rate in rates.items())
        total += (bosses + marks) * days
    return runs_a_day * total


def parts_shipped(live, shipped=SHIPPED):
    """How many parts a season is given where nothing dates them: the
    most its measured bosses or its node counts reach (`_extended`), so
    a season whose tree lists one part so far runs as many as the season
    before it."""
    table = shipped_entry(live, shipped).get("bosses") or {}
    measured = max(table) if table else 0
    return max(measured, len(_extended(live, shipped)))
