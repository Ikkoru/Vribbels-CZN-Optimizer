"""The combatants' stats as the server states them, in a file of their
own: `snapshots/base_stats/readings.json`.

Every battle's entry (`world/get_stage_info`) sends each combatant in
it with a `status.info` block, and the partner beside them in
`enter_supporters`, at the same place in the list. The capture files
each battle (`Addon._note_base_stats`):

- per combatant, the base at their level (`BASE_S_*`), the partner's
  flat stats as the combatant's sheet counts them (`S_PARTNER_BASE_*`)
  and as the partner's own (`partner_flat`), and the partner's id,
  level and limit break;
- `inner`: `potential_base_status`, the stat or stats the combatant's
  Potential 7 check reads, with `layers`, the inner multiplier and flat
  of the same sheet;
- `effects`: the battle's Zero System effects that can move a stat.

`builds` holds, apart, each distinct build the server stated a sheet
for -- fragments, potential nodes, partner and the whole status -- for
`formula_gaps`.

**A mode can add to the base.** A Chaos stage adds its Zero System stat
nodes to every combatant alike. A Sortie multiplies the base HP, and
the week's buffed combatants' base and partner flats of the buffed
stat -- a buff list the wire never carries. So a battle without Zero
System effects is PLAIN and its bases are the combatants' own; a Chaos
stage's are worked out (`resolve`), and a Sortie's are not:

1. **The inner value solves the base.** In a Chaos stage,
   `potential_base_status` is computed without the stage's bonus, and
   the inner formula -- round((base + partner) * (1 + rate) + flat) --
   has exactly one base that gives it (`solve_base`). A Sortie's
   includes the week's buff, so it solves nothing.
2. **A Chaos stage's bonus is the same for everyone in it**, so the gap
   between a combatant's battle base and their base known another way
   -- solved, or read in a plain battle -- is the battle's bonus, and
   takes it off everyone else. Only for the groups in `ADDITIVE`; a
   battle whose combatants say different bonuses is set aside.

**A plain reading wins**; a worked-out one fills only what no plain
reading covers, the newest first. Only readings at level 60 or above
count: the program holds level 60 and up, and combatant trials and
event stories field level-20 copies.

`audit` sets what the server says against `characters.py` and
`partners.py`; `learned_bases` and `partner_flats` are what the program
uses where its tables are silent or wrong (`game_data.learned`).

Kept apart like the Chaos runs (`chaos_store.py`): a subfolder, ONE
writer, and a write that goes through a read-back copy keeping the
previous file as `<name>.bak`. No Tk: `checks/check_base_stats_on_wire`
and `docs/base_stats_backfill.py` read through this.
"""

import json
import math
from pathlib import Path

FOLDER = "base_stats"
FILE = "readings.json"
KIND = "vribbels base stat readings"
BACKUP = ".bak"

STATS = ("ATK", "DEF", "HP")

# Zero System groups that add one flat amount per stat to every
# combatant's base in the battle: a Chaos stage's stat nodes. Their
# values ride the wire; which stat each node raises does not.
ADDITIVE = ("ZERO_CHARACTER_STAT__TYPE_VALUE",)

# Readings below this level are the game's lower curve, which the
# program does not hold.
LOWEST_LEVEL = 60


def path_in(snapshots):
    """Where the readings' file sits under a snapshots folder."""
    return Path(snapshots) / FOLDER / FILE


def read_store(snapshots):
    """(battles, builds, note): every battle and build filed, and a note
    where the file had to be read from its backup or could not be read
    at all; empty lists and None where there is no file yet."""
    path = path_in(snapshots)
    tried = []
    for candidate in (path, path.with_name(path.name + BACKUP)):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            tried.append("%s: %s" % (candidate.name, e))
            continue
        battles = data.get("battles") if isinstance(data, dict) else None
        if not isinstance(battles, list):
            tried.append("%s: not a base stat readings file" % candidate.name)
            continue
        builds = data.get("builds")
        note = None
        if candidate != path:
            note = "read from the backup (%s)" % "; ".join(tried or [
                "%s missing" % path.name])
        return ([b for b in battles if isinstance(b, dict)],
                [b for b in builds or () if isinstance(b, dict)], note)
    if tried:
        return [], [], "could not be read: " + "; ".join(tried)
    return [], [], None


def read(snapshots):
    """(battles, note), as `read_store` without the builds."""
    battles, _builds, note = read_store(snapshots)
    return battles, note


# ------------------------------------------------------------ resolving

def _half_up(value):
    return int(math.floor(value + 0.5))


def solve_base(inner, partner, rate, flat):
    """The one base whose inner value -- round((base + partner) *
    (1 + rate / 100) + flat), as the server rounds it -- is `inner`;
    None unless exactly one base gives it."""
    if not all(isinstance(v, (int, float)) for v in (inner, partner, rate,
                                                      flat)):
        return None
    scale = 1 + rate / 100.0
    if scale <= 0:
        return None
    guess = int((inner - flat) / scale - partner)
    hits = [b for b in range(guess - 2, guess + 4)
            if _half_up((b + partner) * scale + flat) == inner]
    return hits[0] if len(hits) == 1 else None


def _comparable(row):
    """A reading the program's tables can be held to: level 60 or
    above."""
    return isinstance(row, dict) and isinstance(row.get("level"), int) \
        and row["level"] >= LOWEST_LEVEL \
        and isinstance(row.get("base"), list) and len(row["base"]) == 3


def plain_battles(battles):
    """The battles whose bases are the combatants' own: no Zero System
    effects."""
    return [b for b in battles if not b.get("zero_system")]


def _additive(battle):
    """Whether every stat effect of `battle` adds one amount to everyone:
    a record filed before effects were kept cannot say, and is not."""
    effects = battle.get("effects")
    return isinstance(effects, list) and bool(effects) and all(
        isinstance(e, list) and e and e[0] in ADDITIVE for e in effects)


def _solved(row):
    """{stat: base} that `row`'s inner value solves."""
    inner = row.get("inner") or {}
    layers = row.get("layers") or {}
    partner = row.get("partner") or [0, 0, 0]
    out = {}
    for i, stat in enumerate(STATS):
        value = inner.get("S_" + stat)
        if value is None:
            continue
        base = solve_base(value, partner[i] or 0,
                          layers.get("S_%s_INC_RATE_OUT" % stat, 0),
                          layers.get("S_%s_INC_ADD_OUT" % stat, 0))
        if base is not None:
            out[stat] = base
    return out


def resolve(battles):
    """({(res_id, level): {stat: (base, read_at, how)}}, [conflicts]).

    `how` is `plain`, `solved` (from the inner value) or `offset` (a
    Chaos stage's bonus taken off). A conflict is (stage, content, stat,
    [bonuses], last seen): a battle whose combatants say different
    bonuses for any stat, which gives nothing beyond what each solves
    alone.
    """
    plain, derived, conflicts = {}, {}, []

    def put(table, key, stat, value, when, how):
        held = table.setdefault(key, {}).get(stat)
        if held is None or (when or 0) >= (held[1] or 0):
            table[key][stat] = (value, when, how)

    for battle in plain_battles(battles):
        for row in battle.get("chars") or []:
            if _comparable(row):
                for i, stat in enumerate(STATS):
                    put(plain, (row.get("res_id"), row["level"]), stat,
                        row["base"][i], battle.get("last"), "plain")
    for battle in battles:
        # A Sortie's inner value carries the week's buff and its bases
        # carry a buff nobody names, so only a Chaos stage is worked out.
        if not battle.get("zero_system") or not _additive(battle):
            continue
        rows = [r for r in battle.get("chars") or [] if _comparable(r)]
        when = battle.get("last")
        bonuses = {stat: set() for stat in STATS}
        for row in rows:
            key = (row.get("res_id"), row["level"])
            for stat, base in _solved(row).items():
                put(derived, key, stat, base, when, "solved")
                bonuses[stat].add(row["base"][STATS.index(stat)] - base)
            for stat, held in (plain.get(key) or {}).items():
                bonuses[stat].add(row["base"][STATS.index(stat)] - held[0])
        split = [stat for stat in STATS if len(bonuses[stat]) > 1]
        for stat in split:
            conflicts.append((battle.get("stage"), battle.get("content"),
                              stat, sorted(bonuses[stat]), when))
        if split:
            # One stat's disagreement means a base the offsets were
            # taken from is wrong, and nothing says which: the other
            # stats' offsets came from the same combatants.
            continue
        for i, stat in enumerate(STATS):
            if not bonuses[stat]:
                continue
            bonus = next(iter(bonuses[stat]))
            for row in rows:
                key = (row.get("res_id"), row["level"])
                if stat not in (derived.get(key) or {}):
                    put(derived, key, stat, row["base"][i] - bonus, when,
                        "offset")
    out = {key: dict(stats) for key, stats in derived.items()}
    for key, stats in plain.items():
        out.setdefault(key, {}).update(stats)
    return out, conflicts


def learned_bases(battles):
    """{res_id: {level: {"base": [atk, def, hp], "read_at": t}}} for
    every combatant and level whose three bases the readings settle."""
    bases, _conflicts = resolve(battles)
    out = {}
    for (rid, level), stats in bases.items():
        if not isinstance(rid, int) or any(s not in stats for s in STATS):
            continue
        out.setdefault(rid, {})[level] = {
            "base": [stats[s][0] for s in STATS],
            "read_at": max(stats[s][1] or 0 for s in STATS)}
    return out


def partner_flats(battles):
    """{partner res_id: {level: {"flat": [atk, def, hp], "read_at": t}}}:
    each partner's own flat stats, the newest reading per level. From
    the partner's record, not the combatant's sheet, which can count
    them differently."""
    out = {}
    for battle in sorted(battles, key=lambda b: b.get("last") or 0):
        for row in battle.get("chars") or []:
            pid, level = row.get("partner_id"), row.get("partner_level")
            flat = row.get("partner_flat")
            if isinstance(pid, int) and isinstance(level, int) and \
                    isinstance(flat, list) and len(flat) == 3:
                out.setdefault(pid, {})[level] = {
                    "flat": list(flat), "read_at": battle.get("last")}
    return out


# ------------------------------------------------------------- auditing

def _name(rid):
    from game_data.characters import CHARACTERS
    char = CHARACTERS.get(rid)
    return char["name"] if isinstance(char, dict) else rid


def audit(battles):
    """Set the readings against characters.py and partners.py.

    Returns a dict of lists:

    - `differs`: (name, level, wire, program, last seen, how) for each
      combatant whose base -- newest plain reading, else worked out --
      is not what characters.py gives at that level; `wire` holds None
      for a stat nothing settled, and `how` is `plain` or `derived`;
    - `missing`: (res_id, level, wire, last seen) for a combatant the
      server sent that characters.py does not have;
    - `changed`: (name, level, older, newer, older's last, newer's
      first) where plain readings of one level disagree over time;
    - `gains`: (name, class, grade, level, wire - level-60 base) for a
      reading above 60 that characters.py cannot reproduce because a
      gain up to that level is unknown -- it says what the gain is,
      where `differs` would blame the base;
    - `conflicts`: battles whose combatants say different bonuses;
    - `partners`: (name, level, wire, program, last seen) for each
      partner whose own flat stats are not what `table_partner_stats`
      gives at that level;
    - `unseen`: names in characters.py nothing has settled.
    """
    from game_data.characters import CHARACTERS, level_bonus
    from game_data.partners import PARTNERS, table_partner_stats
    out = {"differs": [], "missing": [], "changed": [], "gains": [],
           "conflicts": [], "partners": [], "unseen": []}
    bases, out["conflicts"] = resolve(battles)

    history = {}
    for battle in sorted(plain_battles(battles),
                         key=lambda b: b.get("last") or 0):
        for row in battle.get("chars") or []:
            if _comparable(row):
                history.setdefault((row.get("res_id"), row["level"]),
                                   []).append((list(row["base"]),
                                               battle.get("first"),
                                               battle.get("last")))
    for (rid, level), rows in sorted(history.items(), key=str):
        newest = rows[-1]
        for older, _old_first, old_last in rows[:-1]:
            if older != newest[0]:
                out["changed"].append((_name(rid), level, older, newest[0],
                                       old_last, newest[1]))

    seen = set()
    for (rid, level), stats in sorted(bases.items(), key=str):
        wire = [stats[s][0] if s in stats else None for s in STATS]
        last = max(stats[s][1] or 0 for s in stats)
        how = "plain" if all(stats[s][2] == "plain" for s in stats) \
            else "derived"
        char = CHARACTERS.get(rid)
        if not isinstance(char, dict):
            if None not in wire:
                out["missing"].append((rid, level, wire, last))
            continue
        seen.add(rid)
        program = _base_at(char, level)
        if all(w is None or w == p for w, p in zip(wire, program)):
            continue
        unknown_gain = level > 60 and any(
            level_bonus(char, step) is None for step in range(61, level + 1))
        if unknown_gain and None not in wire:
            base60 = bases.get((rid, 60))
            base60 = ([base60[s][0] for s in STATS]
                      if base60 and all(s in base60 for s in STATS)
                      else _base_at(char, 60))
            out["gains"].append((char["name"], char.get("class"),
                                 char.get("grade"), level,
                                 [w - b for w, b in zip(wire, base60)]))
            continue
        out["differs"].append((char["name"], level, wire, program, last,
                               how))
    out["unseen"] = sorted(c["name"] for rid, c in CHARACTERS.items()
                           if isinstance(c, dict) and rid not in seen)

    for pid, levels in sorted(partner_flats(battles).items(), key=str):
        partner = PARTNERS.get(pid)
        for level, held in sorted(levels.items()):
            program = table_partner_stats(pid, level)
            program = [program["atk"], program["def"], program["hp"]]
            if held["flat"] != program:
                out["partners"].append((
                    partner["name"] if isinstance(partner, dict) else pid,
                    level, held["flat"], program, held["read_at"]))
    return out


def _base_at(char, level):
    from game_data.characters import table_stats_at_level
    b = table_stats_at_level(char, level or 60)
    return [b["base_atk"], b["base_def"], b["base_hp"]]


# -------------------------------------------------------------- formula

# Potential 7 bonuses the server's sheets have shown and the program
# does not model (docs/game_formulas.md, "The potential tree"), per
# res_id: `formula_gaps` passes a gap of exactly this much. Owen's is
# his node 7's once its HP check passes. Diana's +12% Extra DMG% shows
# with nothing else on her sheet to account for it, and her check reads
# CRate: her node 7's by the look of it, which the maintainer confirms.
UNMODELLED = {1050: {"ATK%": 4, "DEF%": 4}, 1061: {"Extra DMG%": 12}}

# Where each such bonus lands among the char statics.
_EXTRA_KEYS = {"ATK%": "pot_atk_pct", "DEF%": "pot_def_pct",
               "HP%": "pot_hp_pct", "CRate": "pot_crate", "CDmg": "pot_cdmg",
               "Extra DMG%": "partner_extra_dmg", "DoT%": "partner_dot"}


def formula_gaps(builds, allowed=None):
    """Where the program's stat formula, run on a build the server
    stated a sheet for, disagrees with the sheet: a list of
    (res_id, what, server, program).

    Only builds from plain battles. The server's own BASE and partner
    flats go in, so only the formula is tested here -- the tables they
    come from are `audit`'s. `allowed` is {res_id: {stat: amount}}, a
    bonus the program does not model -- `UNMODELLED` unless given. A
    value passes with it or without it, since a Potential 7 node's
    bonus applies only once the node's own check passes.

    What is held, per build:

    - `final`: each final stat is round(round(inner) * (1 + outer%))
      over the sheet's own layers -- the shape of the formula;
    - `outer %`: the partner's passive, `partners.py` at its limit break;
    - `inner %`: fragments, sets and the potential nodes;
    - `flat`: fragment flats plus one row of `FRIENDSHIP_BONUSES`;
    - CRate, CDMG, Extra DMG% and DoT%: their sums;
    - `inner`: `potential_base_status` is the program's inner value --
      the one its Potential 7 and Have-at-least comparisons read --
      rounded as the server rounds it.
    """
    from game_data import CHARACTERS, FRIENDSHIP_BONUSES
    from models.memory_fragment import MemoryFragment
    from optimizer import core
    allowed = UNMODELLED if allowed is None else allowed
    rows = [(0, 0, 0)] + [(a, d, h) for _lvl, a, d, h in FRIENDSHIP_BONUSES]
    out = []
    for build in builds:
        rid, st = build.get("res_id"), build.get("status") or {}
        char = CHARACTERS.get(rid)
        if build.get("zero_system") or not isinstance(char, dict) \
                or "BASE_S_ATK" not in st:
            continue
        gear = [MemoryFragment.from_json(p) for p in build.get("pieces") or ()
                if isinstance(p, dict)]
        cs = _statics(build, char, st)
        # The sheet's inner flat is the fragments' flats plus the
        # Affection tier's, which the build does not name: the row
        # that fits is the tier.
        flats = {s: sum(p.get_total_stats().get("Flat " + s, 0)
                        for p in gear) for s in STATS}
        tier = next((row for row in rows if all(
            _half_up(flats[s] + row[i]) == st.get("S_%s_INC_ADD_OUT" % s, 0)
            for i, s in enumerate(STATS))), None)
        if tier is None:
            out.append((rid, "flat: no Affection row fits",
                        [st.get("S_%s_INC_ADD_OUT" % s, 0) for s in STATS],
                        [round(flats[s], 2) for s in STATS]))
        else:
            cs["affection_atk"], cs["affection_def"], cs["affection_hp"] = \
                tier
        runs = [core.compute_build_stats(gear, cs, {})]
        if allowed.get(rid):
            more = dict(cs)
            for stat, amount in allowed[rid].items():
                more[_EXTRA_KEYS[stat]] += amount
            runs.append(core.compute_build_stats(gear, more, {}))

        def gap(what, server, program_of, tolerance=0.051):
            if server is None:
                return
            values = [program_of(run) for run in runs]
            if not any(abs(server - v) < tolerance for v in values):
                out.append((rid, what, server, round(values[0], 3)))

        for s in STATS:
            rate_out = st.get("S_%s_INC_RATE_OUT" % s, 0)
            rate_in = st.get("S_%s_INC_RATE_IN" % s, 0)
            inner = _half_up((st.get("BASE_S_" + s, 0)
                              + st.get("S_PARTNER_BASE_" + s, 0))
                             * (1 + rate_out / 100.0)
                             + st.get("S_%s_INC_ADD_OUT" % s, 0))
            gap("final " + s, st.get("S_" + s),
                lambda _run: _half_up(inner * (1 + rate_in / 100.0)),
                tolerance=0.5)
            gap("outer %s%%" % s, rate_in,
                lambda _run, s=s: cs["partner_%s_pct" % s.lower()])
            gap("inner %s%%" % s, rate_out,
                lambda run, s=s: run[s + "%"]
                - cs["partner_%s_pct" % s.lower()]
                - cs["equip_%s_pct" % s.lower()])
        for what, field in (("CRate", "S_CRI"), ("CDmg", "S_CRI_DMG_RATE"),
                            ("Extra DMG%", "S_ADDI_ATK_DMG_RATE"),
                            ("DoT%", "S_DOT_ATK_DMG_RATE")):
            gap(what, st.get(field), lambda run, what=what: run[what])
        for field, value in (build.get("inner") or {}).items():
            stat = field[2:] if field.startswith("S_") else field
            if stat in STATS and tier is not None:
                # The program's inner value rounded as the server rounds
                # it: the flat to a whole number first, then the sum.
                gap("inner " + stat, value,
                    lambda run, s=stat, i=STATS.index(stat): _half_up(
                        (st.get("BASE_S_" + s, 0)
                         + st.get("S_PARTNER_BASE_" + s, 0))
                        * (1 + (run[s + "%"]
                                - cs["partner_%s_pct" % s.lower()]
                                - cs["equip_%s_pct" % s.lower()]) / 100.0)
                        + _half_up(flats[s] + tier[i])))
    return out


def _statics(build, char, st):
    """The char statics of `build` for `core.compute_build_stats`, with
    the server's own base and partner flats in."""
    from game_data import (get_partner_passive_stats,
                           get_potential_stat_bonus, parse_potential_node_ids)
    from optimizer import core
    rid = build.get("res_id")
    cs = core.empty_char_static()
    for stat in STATS:
        cs["base_" + stat.lower()] = st.get("BASE_S_" + stat, 0)
        cs["partner_flat_" + stat.lower()] = st.get("S_PARTNER_BASE_" + stat,
                                                    0)
    cs["base_cr"] = char.get("base_crit_rate", 0)
    cs["base_cd"] = char.get("base_crit_dmg", 125.0)
    if isinstance(build.get("partner_id"), int):
        passive = get_partner_passive_stats(build["partner_id"],
                                            build.get("partner_lb") or 0)
        for stat, key in (("ATK%", "atk_pct"), ("DEF%", "def_pct"),
                          ("HP%", "hp_pct"), ("CDmg", "cdmg"),
                          ("Extra DMG%", "extra_dmg"), ("CRate", "crate"),
                          ("DoT%", "dot"), ("Ego", "ego")):
            cs["partner_" + key] = passive.get(stat, 0)
    nodes = parse_potential_node_ids(build.get("nodes") or [], rid)
    for node in (50, 60):
        if nodes.get(node):
            stat, bonus = get_potential_stat_bonus(rid, node, nodes[node])
            if stat in _EXTRA_KEYS and _EXTRA_KEYS[stat].startswith("pot_"):
                cs[_EXTRA_KEYS[stat]] += bonus
    return cs
