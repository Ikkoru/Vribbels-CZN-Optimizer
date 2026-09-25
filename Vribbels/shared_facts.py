"""Facts about the GAME that a player's captures hold, as against facts
about the player's account: which ship with the program, which a
player could add, and the file they send in.

Seven kinds, each something the game stops listing after a while, so a
player who installs late or never opened the right screen can never
read it for themselves:

* `banner_rates` -- a banner's rates reply: its odds and its pools.
* `trial_slots` -- which Combatant Trial slots each trial event offers,
  which only a claim made while capturing names.
* `instalment_totals` -- how many rewards a finished event instalment
  held, before the game purged its rows.
* `final_rewards` -- which instalments paid a final reward.
* `rift_tops` -- each Great Rift subdivision's top row, per server: its
  rank and score, never who.
* `sortie_fields` -- each Sortie season's field, per server: how many
  players it ranked and its top score.
* `offensive_fields` -- each Full-Scale Offensive's field, per server:
  how many players it ranked, to the hundred.

**A whitelist.** `collect` names every field it copies and `clean`
checks every value's shape, so a field the wire adds later cannot reach
a file by default -- and nothing about the account ever does: no id, no
name, no rank or score of its own. An id must look like one of the
game's (`ID`), which keeps text of any other kind out of every key.
**The Offensive's field is worked out from the account's own rank**,
which is why it is kept to the hundred the Stats list shows: to more
than that, it and the percentage the game states would give the rank
back.

**Read beside the user's own, never merged into it.** The shipped copy
is `default_settings/shared_facts.json`, read-only, and each reader
combines it with what the account holds, in memory -- `with_rates`,
`with_slots`, `totals_with`, `finals_with`, `tops_with`,
`fields_for`. The account's files are never rewritten with it, so a
wrong shipped fact goes away with the release that fixes it and leaves
nothing behind.

**The rankings are per server.** The two rank different players, so a
field read on one is wrong on the other; every other kind is the same
game on both. A reading the capture stamped names its server, and one
from before the stamp takes the newest snapshot's.

**A later reading is news only for a season that is over**: a running
one's figures move every week, and counting each move would ask every
active account to send the same season again. Over means an older one
than the newest the two sides know of -- see `_is_news`.

`missing` is what the panel asks and the export writes: what the
account holds that the shipped file does not. `fold` is the
maintainer's merge of the account's own facts and of the files players
send, run by `default_settings/normalize/fold_shared_facts.py`; `lost`
is its guard against a fold that would drop anything.
"""

import copy
import json
import re
from pathlib import Path

FILE_NAME = "shared_facts.json"
KIND = "vribbels shared facts"
VERSION = 1

RATES = "banner_rates"
SLOTS = "trial_slots"
TOTALS = "instalment_totals"
FINALS = "final_rewards"
TOPS = "rift_tops"
SORTIE = "sortie_fields"
OFFENSIVE = "offensive_fields"
KINDS = (RATES, SLOTS, TOTALS, FINALS, TOPS, SORTIE, OFFENSIVE)
# The kinds kept per server, as {server: {season, ...: reading}}.
RANKINGS = (TOPS, SORTIE, OFFENSIVE)

# What each kind is called, one and many, in the order the Share Game
# Data panel names them.
WORDS = {RATES: ("banner's rates", "banners' rates"),
         SLOTS: ("Combatant Trial slot", "Combatant Trial slots"),
         TOTALS: ("event reward total", "event reward totals"),
         FINALS: ("final reward", "final rewards"),
         TOPS: ("Great Rift division top", "Great Rift division tops"),
         SORTIE: ("Sortie season", "Sortie seasons"),
         OFFENSIVE: ("Full-Scale Offensive", "Full-Scale Offensives")}

# `capture.constants.SERVERS`' keys, written out rather than imported:
# importing the capture package pulls in far more than this module
# needs. `check_shared_facts` holds the two to each other.
REGIONS = ("global", "asia")

# What an id may look like, as a key or in a list. The game's are
# words, digits and underscores; a URL, a sentence or a name is not
# one, and is dropped wherever it stands.
ID = re.compile(r"^[A-Za-z0-9_]{1,80}$")

# A banner's rates reply, less `seen` -- when THIS account read it.
RATE_TABLES = ("rates", "total_rate_info")
RATE_POOLS = "pools"

# What a ranking reading SAYS, per kind, as against when it was read:
# a later reading that says the same is not a new fact. A top is where
# a subdivision starts and what leads it; a field is its size and, for
# the Sortie, its top score.
SAYS = {TOPS: ("rank", "best_score"),
        SORTIE: ("players", "top_score"),
        OFFENSIVE: ("players",)}

# How many levels a ranking kind nests under its server: a top sits
# under its season, its half and its subdivision, a field under its
# season alone. The SEASON -- what is over or running -- is the first
# `UNIT` levels.
DEPTH = {TOPS: 3, SORTIE: 1, OFFENSIVE: 1}
UNIT = {TOPS: 2, SORTIE: 1, OFFENSIVE: 1}

# No instalment holds more rewards than this. A bigger count is not the
# game's, and a file claiming one is refused the entry.
MOST_REWARDS = 1000


def empty():
    return {kind: {} for kind in KINDS}


# ------------------------------------------------------------ checking

def _is_id(value):
    return isinstance(value, str) and bool(ID.match(value))


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return (isinstance(value, (int, float))
            and not isinstance(value, bool) and value == value)


def _items(value):
    return value.items() if isinstance(value, dict) else ()


def _ids(value):
    """The ids in a list, once each and in order; nothing else."""
    if not isinstance(value, list):
        return None
    return list(dict.fromkeys(v for v in value if _is_id(v)))


def clean(facts):
    """`facts` with every entry that is not well formed dropped.

    Every read of a shipped or contributed file comes through here, and
    so does everything `collect` gathers. A hand-edited or hostile file
    costs the entries it broke and nothing else, and nothing in it
    reaches a reader unchecked.
    """
    facts = facts if isinstance(facts, dict) else {}
    out = {RATES: _clean_rates(facts.get(RATES)),
           SLOTS: _clean_lists(facts.get(SLOTS)),
           TOTALS: _clean_totals(facts.get(TOTALS)),
           FINALS: _clean_lists(facts.get(FINALS))}
    for kind in RANKINGS:
        out[kind] = _clean_rankings(kind, facts.get(kind))
    return out


def _clean_rates(raw):
    """{banner: {rates, total_rate_info, pools}}, each part whole."""
    out = {}
    for banner, entry in _items(raw):
        if not _is_id(banner) or not isinstance(entry, dict):
            continue
        kept = {}
        for table in RATE_TABLES:
            values = entry.get(table)
            if not isinstance(values, dict):
                break
            kept[table] = {k: v for k, v in values.items()
                           if _is_id(k) and _is_number(v)}
        pools = entry.get(RATE_POOLS)
        if len(kept) < len(RATE_TABLES) or not isinstance(pools, dict):
            continue
        kept[RATE_POOLS] = {k: _ids(v) for k, v in pools.items()
                            if _is_id(k) and _ids(v) is not None}
        out[banner] = kept
    return out


def _clean_lists(raw):
    """{id: [id, ...]}, for the trial slots and the final rewards."""
    out = {}
    for key, value in _items(raw):
        ids = _ids(value)
        if _is_id(key) and ids:
            out[key] = ids
    return out


def _clean_totals(raw):
    """{family: {instalment: rewards}}."""
    out = {}
    for family, rows in _items(raw):
        kept = {event: count for event, count in _items(rows)
                if _is_id(event) and _is_int(count)
                and 0 < count <= MOST_REWARDS}
        if _is_id(family) and kept:
            out[family] = kept
    return out


def _count(value, least=1):
    return value if _is_int(value) and value >= least else None


def _clean_reading(kind, reading):
    """One ranking reading with only its kind's fields, or None."""
    if not isinstance(reading, dict):
        return None
    read_at = _count(reading.get("read_at"))
    if read_at is None:
        return None
    if kind == TOPS:
        rank = _count(reading.get("rank"))
        return None if rank is None else {
            "rank": rank, "read_at": read_at,
            "best_score": _count(reading.get("best_score"), 0)}
    players = _count(reading.get("players"))
    if players is None:
        return None
    out = {"players": players, "read_at": read_at}
    if kind == SORTIE:
        out["top_score"] = _count(reading.get("top_score"), 0)
    return out


def _clean_rankings(kind, raw):
    """{server: {season, ...: reading}}, `DEPTH[kind]` levels deep."""
    out = {}
    for region, tree in _items(raw):
        if region not in REGIONS:
            continue
        for path, reading in _walk(tree, DEPTH[kind]):
            reading = _clean_reading(kind, reading)
            if reading and all(map(_is_id, path)):
                _put(out.setdefault(region, {}), path, reading)
    return out


def _walk(tree, depth, path=()):
    """(path, leaf) for every leaf `depth` levels into nested dicts."""
    for key, value in _items(tree):
        if depth == 1:
            yield path + (key,), value
        else:
            yield from _walk(value, depth - 1, path + (key,))


def _put(tree, path, value):
    for key in path[:-1]:
        tree = tree.setdefault(key, {})
    tree[path[-1]] = value


def _get(tree, path):
    for key in path:
        tree = tree.get(key) if isinstance(tree, dict) else None
    return tree


# ----------------------------------------------------------- gathering

def collect(raw, history, captured, checklist):
    """The account's facts, through the whitelist.

    `raw` is the newest snapshot, `history` `stats_history.json`,
    `captured` the Gacha History's `captured.json` and `checklist`
    `checklist.json` -- each as loaded, and any of them None.
    """
    raw = raw if isinstance(raw, dict) else {}
    captured = captured if isinstance(captured, dict) else {}
    checklist = checklist if isinstance(checklist, dict) else {}
    facts = {RATES: captured.get("rates"),
             SLOTS: raw.get("combatant_trial_slots"),
             TOTALS: checklist.get("events"),
             FINALS: checklist.get("finals")}
    facts.update(_rankings_by_region(raw, history))
    return clean(facts)


# Where each ranking kind comes from, in a snapshot and in
# `stats_history.json` alike.
SOURCES = {TOPS: "disaster_boss_rank_tops",
           SORTIE: "chaos_assault_rankings",
           OFFENSIVE: "remnants_rankings"}


def _rankings_by_region(raw, history):
    """The latest reading of each season's field and each subdivision's
    top, by server.

    Read through `stats_history.merged`, the way the Stats lists read
    them, so what only an old debug capture held is shared too. A
    reading without a server of its own -- read before the capture
    stamped one, or out of an old log -- takes the snapshot's.
    """
    import stats_history
    fallback = raw.get("detected_region")
    out = {kind: {} for kind in RANKINGS}
    for kind in RANKINGS:
        merged = stats_history.merged(raw, history, SOURCES[kind])
        for path, readings in _ranking_readings(kind, merged):
            for reading in readings:
                region = reading.get("region") or fallback
                kept = _clean_reading(kind, _field_of(kind, reading))
                if kept is None or region not in REGIONS:
                    continue
                held = out[kind].setdefault(region, {})
                if _later(kept, _get(held, path)):
                    _put(held, path, kept)
    return out


def _ranking_readings(kind, merged):
    """(path, [readings]) out of one kind's merged history."""
    if kind == TOPS:
        for path, samples in _walk(merged, 3):
            yield tuple(map(str, path)), [
                s for s in (samples if isinstance(samples, list) else ())
                if isinstance(s, dict)]
        return
    for season, held in _items(merged):
        readings = held.get("readings") if isinstance(held, dict) else None
        yield (str(season),), [r for r in readings or ()
                               if isinstance(r, dict)]


def _field_of(kind, reading):
    """What a reading says about the whole field -- never the
    account's own place in it."""
    if kind == TOPS:
        return reading
    if kind == SORTIE:
        return {"players": reading.get("total_count"),
                "top_score": reading.get("top_score"),
                "read_at": reading.get("read_at")}
    rank, percent = reading.get("rank"), reading.get("rank_percent")
    players = None
    if _count(rank) and _is_number(percent) and percent > 0:
        players = int(round(rank * 100.0 / percent, -2))
    return {"players": players, "read_at": reading.get("read_at")}


def _later(reading, than):
    return than is None or reading["read_at"] > than["read_at"]


def collect_from(program_dir, raw=None):
    """`collect` over the files under `program_dir` -- the folder that
    holds `settings/` and `snapshots/`. `raw` is the snapshot already
    loaded; without one the newest in `snapshots/` is read."""
    import gacha_history
    import stats_history
    program_dir = Path(program_dir)
    settings, snapshots = program_dir / "settings", program_dir / "snapshots"
    if raw is None:
        newest = sorted(snapshots.glob("memory_fragments_*.json"))
        raw = _read_json(newest[-1]) if newest else None
    captured, _note = gacha_history.read_store(
        gacha_history.folder_in(snapshots) / gacha_history.CAPTURED)
    return collect(raw, stats_history.load(settings), captured,
                   _read_json(settings / "checklist.json"))


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------ comparing

def _season_order(kind, path):
    """Where a season stands among its kind's, as a tuple to compare,
    or None where its ids say nothing."""
    if kind == TOPS:
        season = re.search(r"_s(\d+)$", path[0])
        half = re.search(r"_rank_(\d+)$", path[1])
        return ((int(season.group(1)), int(half.group(1)))
                if season and half else None)
    found = re.search(r"(\d+)$", path[0])
    return (int(found.group(1)),) if found else None


def _newest(kind, trees):
    """The newest season any of `trees` -- one server's readings of one
    kind -- knows of, or None."""
    orders = [_season_order(kind, path[:UNIT[kind]])
              for tree in trees for path, _r in _walk(tree, DEPTH[kind])]
    orders = [order for order in orders if order is not None]
    return max(orders) if orders else None


def _is_news(kind, path, reading, held, newest):
    """Whether `reading` tells anything `held` does not.

    A season `held` has no reading of is news. **So is a later reading
    that says something different, but only of a season that is
    over**: one older than `newest`. The season running has figures
    that move every week, and counting those would make the same
    season news again every week. None for `newest` counts every
    season as over -- the maintainer's fold, where a later figure of
    the season running is the one to ship.
    """
    if held is None:
        return True
    if reading["read_at"] <= held["read_at"]:
        return False
    if [reading.get(f) for f in SAYS[kind]] == [held.get(f)
                                                for f in SAYS[kind]]:
        return False
    if newest is None:
        return True
    order = _season_order(kind, path[:UNIT[kind]])
    return order is not None and order < newest


def missing(mine, shipped):
    """What `mine` holds that `shipped` does not: the facts worth sending.

    A key the shipped facts lack, a bigger instalment total, or a
    later reading that says something new of a season that is over --
    see `_is_news`.
    """
    mine, shipped = clean(mine), clean(shipped)
    out = empty()
    out[RATES] = {banner: entry for banner, entry in mine[RATES].items()
                  if banner not in shipped[RATES]}
    for kind in (SLOTS, FINALS):
        for key, ids in mine[kind].items():
            have = set(shipped[kind].get(key, ()))
            new = [i for i in ids if i not in have]
            if new:
                out[kind][key] = new
    for family, rows in mine[TOTALS].items():
        have = shipped[TOTALS].get(family, {})
        new = {e: c for e, c in rows.items() if c > have.get(e, 0)}
        if new:
            out[TOTALS][family] = new
    for kind in RANKINGS:
        for region, tree in mine[kind].items():
            held = shipped[kind].get(region, {})
            newest = _newest(kind, (tree, held))
            for path, reading in _walk(tree, DEPTH[kind]):
                if _is_news(kind, path, reading, _get(held, path), newest):
                    _put(out[kind].setdefault(region, {}), path, reading)
    return out


def tally(facts):
    """{kind: how many entries of it}: a banner, an id in a list, an
    instalment, a subdivision's top or a season's field each."""
    facts = clean(facts)
    counts = {RATES: len(facts[RATES]),
              SLOTS: sum(map(len, facts[SLOTS].values())),
              TOTALS: sum(map(len, facts[TOTALS].values())),
              FINALS: sum(map(len, facts[FINALS].values()))}
    for kind in RANKINGS:
        counts[kind] = sum(len(list(_walk(tree, DEPTH[kind])))
                           for tree in facts[kind].values())
    return counts


def describe(counts):
    """`2 banners' rates, 1 Great Rift division top`, or '' for none."""
    return ", ".join("%d %s" % (counts[kind], WORDS[kind][counts[kind] != 1])
                     for kind in KINDS if counts.get(kind))


# -------------------------------------------------------------- folding

def _change(kind, before, reading):
    """(`players 19552 -> 19716`, whether any figure went down)."""
    parts, down = [], False
    for field in SAYS[kind]:
        old, new = before.get(field), reading.get(field)
        if old != new:
            parts.append("%s %s -> %s" % (field, old, new))
            down = down or (_is_int(old) and _is_int(new) and new < old)
    return ", ".join(parts), down


def fold(into, facts):
    """`facts` folded into `into`: (the result, [what it added],
    [what it refused], [what went down]).

    Slots and final rewards are unioned, the bigger instalment total
    wins, and a later reading that says something different replaces
    an earlier one -- of a running season too, whose latest figure is
    the one to ship. **A banner already held with DIFFERENT rates is
    refused rather than replaced**: the same banner read two ways is a
    question for the maintainer, not an update. Folding the same facts
    twice changes nothing the second time, and nothing held is ever
    dropped -- `lost` holds a fold to that.

    **A later reading whose figures went DOWN is folded and listed
    apart.** Every ranking figure kept -- a field's size, a top score, a
    subdivision's starting rank -- only grows while a season runs,
    except when the game bans players, which is real. A reading from
    the wrong server or a doctored file looks the same, and only the
    maintainer can tell them apart, so it is said rather than refused.
    """
    out, facts = clean(into), clean(facts)
    added, refused, down = [], [], []
    for banner, entry in facts[RATES].items():
        held = out[RATES].get(banner)
        if held is None:
            out[RATES][banner] = entry
            added.append("rates of %s" % banner)
        elif held != entry:
            refused.append("rates of %s differ from the ones held" % banner)
    for kind in (SLOTS, FINALS):
        for key, ids in facts[kind].items():
            held = out[kind].setdefault(key, [])
            for i in ids:
                if i not in held:
                    held.append(i)
                    added.append("%s %s of %s" % (WORDS[kind][0], i, key))
    for family, rows in facts[TOTALS].items():
        held = out[TOTALS].setdefault(family, {})
        for event, count in rows.items():
            if count > held.get(event, 0):
                added.append("%s: %d rewards%s" % (
                    event, count, "" if event not in held
                    else " (was %d)" % held[event]))
                held[event] = count
    for kind in RANKINGS:
        for region, tree in facts[kind].items():
            held = out[kind].setdefault(region, {})
            for path, reading in _walk(tree, DEPTH[kind]):
                before = _get(held, path)
                if not _is_news(kind, path, reading, before, None):
                    continue
                line = "%s %s of %s" % (region, WORDS[kind][0],
                                        "/".join(path))
                if before is None:
                    added.append(line + ", new")
                else:
                    change, fell = _change(kind, before, reading)
                    (down if fell else added).append(
                        "%s: %s" % (line, change))
                _put(held, path, reading)
    return clean(out), added, refused, down


def lost(before, after):
    """What `before` held that `after` does not, or holds less of: a
    banner, an id, an instalment count, a reading now older. Empty for
    any fold -- the guard is against the code, not the data."""
    before, after = clean(before), clean(after)
    gone = ["rates of %s" % banner for banner in before[RATES]
            if banner not in after[RATES]]
    for kind in (SLOTS, FINALS):
        for key, ids in before[kind].items():
            gone += ["%s %s of %s" % (WORDS[kind][0], i, key) for i in ids
                     if i not in after[kind].get(key, ())]
    for family, rows in before[TOTALS].items():
        gone += ["%s: %d rewards" % (event, count)
                 for event, count in rows.items()
                 if after[TOTALS].get(family, {}).get(event, 0) < count]
    for kind in RANKINGS:
        for region, tree in before[kind].items():
            for path, reading in _walk(tree, DEPTH[kind]):
                now = _get(after[kind].get(region, {}), path)
                if now is None or now["read_at"] < reading["read_at"]:
                    gone.append("%s %s of %s" % (
                        region, WORDS[kind][0], "/".join(path)))
    return gone


# ---------------------------------------------------------------- files

def document(facts, **about):
    """The file's contents: the facts, and what `about` says of them --
    the program's version, the server, the day."""
    data = {"kind": KIND, "version": VERSION}
    data.update(about)
    data["facts"] = clean(facts)
    return data


def read_document(data):
    """The facts a shared file holds, or None where it is not one."""
    if not isinstance(data, dict) or data.get("kind") != KIND \
            or data.get("version") != VERSION:
        return None
    return clean(data.get("facts"))


def whole(data):
    """Whether a shared facts file loses nothing through `clean`: of
    its kind and version, every kind it holds one `clean` knows, every
    entry kept. A kind it does not hold is only older than this code."""
    facts = read_document(data)
    stored = data.get("facts") if isinstance(data, dict) else None
    return (facts is not None and isinstance(stored, dict)
            and all(kind in facts and facts[kind] == value
                    for kind, value in stored.items()))


def load(path):
    """The facts in the file at `path`; none where it is missing or is
    not one."""
    return read_document(_read_json(path)) or empty()


def write(path, data):
    """Write through a temp copy, so a half-written file never stands
    where a whole one did."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def shipped_path(defaults_dir):
    return Path(defaults_dir) / FILE_NAME


# ------------------------------------------------------------- reading

def with_rates(own, shipped):
    """The account's banner rates, and the shipped ones for banners it
    has none of."""
    out = dict((shipped or {}).get(RATES) or {})
    out.update(own if isinstance(own, dict) else {})
    return out


def with_slots(own, shipped):
    """The account's trial slots, with the shipped ones added."""
    out = {key: list(ids) for key, ids in _items(own)
           if isinstance(ids, list)}
    for key, ids in _items((shipped or {}).get(SLOTS)):
        held = out.setdefault(key, [])
        held.extend(i for i in ids if i not in held)
    return out


def totals_with(own, shipped):
    """The account's instalment totals and the shipped ones: the bigger
    count per instalment, as the account's own record keeps."""
    out = {family: dict(rows) for family, rows in _items(own)}
    for family, rows in _items((shipped or {}).get(TOTALS)):
        held = out.setdefault(family, {})
        for event, count in rows.items():
            held[event] = max(count, held.get(event, 0))
    return out


def finals_with(own, shipped):
    """The account's final-reward instalments and the shipped ones."""
    return with_slots(own, {SLOTS: (shipped or {}).get(FINALS)})


def tops_with(tops, shipped, region):
    """`tops` -- {season: {half: {subdivision: [samples]}}}, as
    `stats_history.merged` gives them -- with the shipped samples for
    `region` joined in, oldest first. A reader takes the LAST sample,
    so the later of the account's and the shipped one is the one read.
    """
    out = copy.deepcopy(tops) if isinstance(tops, dict) else {}
    seasons = ((shipped or {}).get(TOPS) or {}).get(region) or {}
    for path, sample in _walk(seasons, DEPTH[TOPS]):
        samples = out.setdefault(path[0], {}).setdefault(
            path[1], {}).setdefault(path[2], [])
        if sample["read_at"] not in {s.get("read_at") for s in samples}:
            samples.append(dict(sample))
            samples.sort(key=lambda s: s.get("read_at") or 0)
    return out


def fields_for(shipped, kind, region):
    """{season: reading} of `kind` -- `SORTIE` or `OFFENSIVE` -- that
    the program ships for `region`."""
    return dict(((shipped or {}).get(kind) or {}).get(region) or {})
