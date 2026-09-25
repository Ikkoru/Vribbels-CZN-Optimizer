"""Facts about the GAME that a player's captures hold, as against facts
about the player's account: which ship with the program, which a
player could add, and the file they send in.

Five kinds, each something the game stops listing after a while, so a
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

**A whitelist.** `collect` names every field it copies and `clean`
checks every value's shape, so a field the wire adds later cannot reach
a file by default -- and nothing about the account ever does: no id, no
name, no rank or score of its own. An id must look like one of the
game's (`ID`), which keeps text of any other kind out of every key.

**Read beside the user's own, never merged into it.** The shipped copy
is `default_settings/shared_facts.json`, read-only, and each reader
combines it with what the account holds, in memory -- `with_rates`,
`with_slots`, `totals_with`, `finals_with`, `tops_with`. The account's
files are never rewritten with it, so a wrong shipped fact goes away
with the release that fixes it and leaves nothing behind.

**The tops are per server.** The two rank different players, so a
field size read on one is wrong on the other; every other kind is the
same game on both. A sample the capture stamped names its server, and
one from before the stamp takes the newest snapshot's.

`missing` is what the panel asks and the export writes: what the
account holds that the shipped file does not. `fold` is the
maintainer's merge of the account's own facts and of the files players
send, run by `default_settings/normalize/fold_shared_facts.py`.
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
KINDS = (RATES, SLOTS, TOTALS, FINALS, TOPS)

# What each kind is called, one and many, in the order the Share Game
# Data panel names them.
WORDS = {RATES: ("banner's rates", "banners' rates"),
         SLOTS: ("Combatant Trial slot", "Combatant Trial slots"),
         TOTALS: ("event reward total", "event reward totals"),
         FINALS: ("final reward", "final rewards"),
         TOPS: ("Great Rift division top", "Great Rift division tops")}

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

# A top's sample: where it stands, what it scored and when it was read.
# The rank and the moment are what a sample IS; a score is optional,
# as the capture's own samples allow.
TOP_FIELDS = ("rank", "best_score", "read_at")

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
    return {RATES: _clean_rates(facts.get(RATES)),
            SLOTS: _clean_lists(facts.get(SLOTS)),
            TOTALS: _clean_totals(facts.get(TOTALS)),
            FINALS: _clean_lists(facts.get(FINALS)),
            TOPS: _clean_tops(facts.get(TOPS))}


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


def _clean_sample(sample):
    if not isinstance(sample, dict):
        return None
    rank, read_at = sample.get("rank"), sample.get("read_at")
    if not (_is_int(rank) and rank > 0 and _is_int(read_at) and read_at > 0):
        return None
    score = sample.get("best_score")
    return {"rank": rank, "read_at": read_at,
            "best_score": score if _is_int(score) and score >= 0 else None}


def _clean_tops(raw):
    """{server: {season: {half: {subdivision: sample}}}}."""
    out = {}
    for region, seasons in _items(raw):
        if region not in REGIONS:
            continue
        for season, halves in _items(seasons):
            for half, tops in _items(halves):
                for rank_id, sample in _items(tops):
                    sample = _clean_sample(sample)
                    if sample and all(map(_is_id, (season, half, rank_id))):
                        out.setdefault(region, {}).setdefault(
                            season, {}).setdefault(half, {})[rank_id] = sample
    return out


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
    return clean({
        RATES: captured.get("rates"),
        SLOTS: raw.get("combatant_trial_slots"),
        TOTALS: checklist.get("events"),
        FINALS: checklist.get("finals"),
        TOPS: _tops_by_region(raw, history),
    })


def _tops_by_region(raw, history):
    """The latest sample of each subdivision's top, by server.

    Read through `stats_history.merged`, the way the Stats lists read
    them, so a top only an old debug capture held is shared too. A
    sample without a server of its own -- read before the capture
    stamped one, or out of an old log -- takes the snapshot's.
    """
    import stats_history
    fallback = raw.get("detected_region")
    out = {}
    tops = stats_history.merged(raw, history, "disaster_boss_rank_tops")
    for season, halves in _items(tops):
        for half, subdivisions in _items(halves):
            for rank_id, samples in _items(subdivisions):
                for sample in samples if isinstance(samples, list) else ():
                    region = (sample.get("region") if isinstance(
                        sample, dict) else None) or fallback
                    kept = _clean_sample(sample)
                    if kept is None or region not in REGIONS:
                        continue
                    held = out.setdefault(region, {}).setdefault(
                        str(season), {}).setdefault(str(half), {})
                    if _later(kept, held.get(str(rank_id))):
                        held[str(rank_id)] = kept
    return out


def _later(sample, than):
    return than is None or sample["read_at"] > than["read_at"]


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

def missing(mine, shipped):
    """What `mine` holds that `shipped` does not: the facts worth sending.

    A key the shipped facts lack, or an instalment total bigger than the
    one they hold. **A later sample of a top they already hold is not
    missing**: every active account reads one every week, and counting
    it would ask all of them to send the same half again.
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
    for region, seasons in mine[TOPS].items():
        for season, halves in seasons.items():
            for half, tops in halves.items():
                have = shipped[TOPS].get(region, {}).get(
                    season, {}).get(half, {})
                new = {r: s for r, s in tops.items() if r not in have}
                if new:
                    out[TOPS].setdefault(region, {}).setdefault(
                        season, {})[half] = new
    return out


def tally(facts):
    """{kind: how many entries of it}, the tops counted a subdivision
    each and the lists an id each."""
    facts = clean(facts)
    return {RATES: len(facts[RATES]),
            SLOTS: sum(map(len, facts[SLOTS].values())),
            TOTALS: sum(map(len, facts[TOTALS].values())),
            FINALS: sum(map(len, facts[FINALS].values())),
            TOPS: sum(len(tops) for seasons in facts[TOPS].values()
                      for halves in seasons.values()
                      for tops in halves.values())}


def describe(counts):
    """`2 banners' rates, 1 Great Rift division top`, or '' for none."""
    return ", ".join("%d %s" % (counts[kind], WORDS[kind][counts[kind] != 1])
                     for kind in KINDS if counts.get(kind))


# -------------------------------------------------------------- folding

def fold(into, facts):
    """`facts` folded into `into`: (the result, [what it added],
    [what it refused]).

    Slots and final rewards are unioned, the bigger instalment total
    wins and a later sample of a top replaces an earlier one. **A
    banner already held with DIFFERENT rates is refused rather than
    replaced**: the same banner read two ways is a question for the
    maintainer, not an update. Folding the same facts twice changes
    nothing the second time.
    """
    out, facts = clean(into), clean(facts)
    added, refused = [], []
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
    for region, seasons in facts[TOPS].items():
        for season, halves in seasons.items():
            for half, tops in halves.items():
                held = out[TOPS].setdefault(region, {}).setdefault(
                    season, {}).setdefault(half, {})
                for rank_id, sample in tops.items():
                    if _later(sample, held.get(rank_id)):
                        added.append("%s top of %s, %s" % (
                            region, rank_id, "new" if rank_id not in held
                            else "a later reading"))
                        held[rank_id] = sample
    return clean(out), added, refused


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
    for season, halves in seasons.items():
        for half, subdivisions in halves.items():
            for rank_id, sample in subdivisions.items():
                samples = out.setdefault(season, {}).setdefault(
                    half, {}).setdefault(rank_id, [])
                if sample["read_at"] not in {s.get("read_at")
                                             for s in samples}:
                    samples.append(dict(sample))
                    samples.sort(key=lambda s: s.get("read_at") or 0)
    return out
