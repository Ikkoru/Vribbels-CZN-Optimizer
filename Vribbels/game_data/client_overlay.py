"""The game client's facts, laid over the hand tables.

What the client states of a combatant or a partner wins over what
`characters.py` and `partners.py` type by hand, its exp to each level,
each Affinity level and the main stats each Memory Fragment slot
carries over `constants.py`'s tables, and its name for each Memory
Fragment set over `sets.py`'s; the hand tables are the fallback, for
whatever the client does not hold. The order, the first that knows a
fact winning (`docs/client_data.md`):

1. this machine's client read (`game_client.use`): the read of this
   build, its cache, or the last cache of an earlier build;
2. the shipped extract, `from_client.py`, as of the build the program
   shipped with: its exp, Affinity and Memory Fragment tables and its
   set names. It holds no combatants or partners -- `docs/client_tables.py
   --ship` writes the ones the hand tables lack into them
   (`client_sync`), so for those the hand tables are the shipped copy;
3. the hand tables as typed.

The server's own readings still go over all three where they exist
(`game_data.learned`, asked by `get_character_stats_at_level` and
`get_partner_stats`).

**Laid over in place.** The tables are read in many places, every one
holding the same dict, so the facts are written into it field by field;
an exp, Affinity or slot table, which the client gives whole, has its
contents swapped inside the same list or dict. `apply` first puts back
every field, entry and table an earlier `apply` laid down, then lays
down the sources again, so it can run any number of times and a field
nothing laid over is never touched.

**What stays the program's own** in an entry the client fills: what the
client holds no value for -- a partner's conditional effects
(`stats_conditional`), its `passive_desc` template and `values`, and the
maintainer's markers. A plain stat line of a partner's passive is the
client's (`game_client._passive_stats`). Of a set, only the name is the
client's: its `bonus` is the maintainer's own wording, and its pieces,
`type`, `stat` and `value` are the model the optimizer weighs it by
(`docs/client_tables.py --audit` holds the pieces, and a plain stat's
figure, to the client's).

**A unit only the client knows** gets an entry built from the client
alone, marked `from_client`, so it shows by name with its stats instead
of as Unknown: one a patch after the last `--ship` added, which the hand
tables do not hold yet. `game_data_validator` checks the hand tables as
typed (`hand`), so such an entry never asks for a hand table's
companions, such as a Potential 7 entry; nor does one `--ship` wrote
into them, which carries the same mark.
"""

import copy
import re

from .characters import CHARACTERS, CHARACTERS_BY_NAME, DEFAULT_CHARACTER
from .constants import (AFFINITY_TO_NEXT, CHARACTER_EXP_TABLE,
                        FRIENDSHIP_BONUSES, PARTNER_EXP_TABLE,
                        SLOT_MAIN_STATS, SLOT_ORDER, STATS, SUBSTAT_DRAW)
from .partners import DEFAULT_PARTNER, PARTNERS, PARTNER_CLASS_STATS
from .sets import SETS

_TABLES = {"CHARACTERS": CHARACTERS, "PARTNERS": PARTNERS,
           "PARTNER_CLASS_STATS": PARTNER_CLASS_STATS,
           "CHARACTER_EXP_TABLE": CHARACTER_EXP_TABLE,
           "PARTNER_EXP_TABLE": PARTNER_EXP_TABLE,
           "AFFINITY_TO_NEXT": AFFINITY_TO_NEXT,
           "FRIENDSHIP_BONUSES": FRIENDSHIP_BONUSES,
           "SLOT_MAIN_STATS": SLOT_MAIN_STATS,
           "SUBSTAT_DRAW": SUBSTAT_DRAW,
           "STATS": STATS,
           "SETS": SETS}
# The hand tables as typed, before anything is laid over them: what the
# validator checks and the audit holds the client against.
_HAND = copy.deepcopy(_TABLES)
# Each exp table by the kind `game_client.exp_tables` names it.
EXP_TABLES = {"combatant": "CHARACTER_EXP_TABLE",
              "partner": "PARTNER_EXP_TABLE"}

# The fields the client fills, where it states them.
COMBATANT_FIELDS = ("name", "grade", "class", "attribute", "base_atk",
                    "base_def", "base_hp", "base_crit_rate", "base_crit_dmg",
                    "node_50", "node_60")
PARTNER_FIELDS = ("name", "grade", "class", "passive_name", "ego_name",
                  "ego_cost")
# A figure in a passive's line, for the template a client-only partner's
# passive is drawn from.
FIGURE = re.compile(r"\d+(?:\.\d+)?")

_MISSING = object()
# (table, key, field) -> what the field held before the first overlay
# that touched it; field None is the whole entry of a table of dicts.
_saved = {}
# (table, key) of every entry an overlay added.
_added = []
# table -> (what it held before the first overlay that replaced it, what
# the last one laid down), for the tables the client gives whole.
_replaced = {}


def hand(name):
    """A table as typed by hand, by its name in `_TABLES`. Never laid
    over; never change it."""
    return _HAND[name]


def _set(name, key, field, value):
    table = _TABLES[name]
    mark = (name, key, field)
    if field is None:
        if mark not in _saved:
            _saved[mark] = table.get(key, _MISSING)
        table[key] = value
        return
    entry = table[key]
    if mark not in _saved:
        _saved[mark] = entry.get(field, _MISSING)
    entry[field] = value


def _add(name, key, entry):
    _TABLES[name][key] = entry
    _added.append((name, key))


def _fill(table, contents):
    """Swap `table`'s contents for `contents`, keeping the object every
    importer holds."""
    if isinstance(table, dict):
        table.clear()
        table.update(contents)
    else:
        table[:] = contents


def _replace(name, contents):
    table = _TABLES[name]
    before = _replaced[name][0] if name in _replaced else copy.copy(table)
    _fill(table, contents)
    _replaced[name] = (before, copy.copy(table))


def _undo():
    """Put back every field, entry and table an overlay laid down."""
    for name, (before, laid) in _replaced.items():
        # Changed since by someone else: theirs, and left alone.
        if _TABLES[name] == laid:
            _fill(_TABLES[name], before)
    _replaced.clear()
    for (name, key, field), old in _saved.items():
        table = _TABLES[name]
        if field is None:
            if old is _MISSING:
                table.pop(key, None)
            else:
                table[key] = old
            continue
        entry = table.get(key)
        if not isinstance(entry, dict):
            continue
        if old is _MISSING:
            entry.pop(field, None)
        else:
            entry[field] = old
    for name, key in _added:
        _TABLES[name].pop(key, None)
    _saved.clear()
    _added.clear()


def _number(value):
    return int(value) if isinstance(value, float) and value.is_integer() \
        else value


def _gains(held):
    """`level_gains` as `level_bonus` reads it: {61: {...}, 62: {...}},
    whatever the keys came back as from JSON."""
    gains = {}
    for level, steps in (held or {}).items():
        if isinstance(steps, dict):
            gains[int(level)] = {stat: steps.get(stat, 0)
                                 for stat in ("atk", "def", "hp")}
    return gains


def _combatants(facts):
    for key, fact in facts.items():
        rid = int(key)
        known = {field: fact.get(field) for field in COMBATANT_FIELDS
                 if fact.get(field) is not None}
        gains = _gains(fact.get("level_gains"))
        if isinstance(CHARACTERS.get(rid), dict):
            for field, value in known.items():
                _set("CHARACTERS", rid, field, value)
            if gains:
                _set("CHARACTERS", rid, "level_gains", gains)
        elif rid and "name" in known and rid not in CHARACTERS:
            _add("CHARACTERS", rid, {**DEFAULT_CHARACTER, **known,
                                     "level_gains": gains,
                                     "from_client": True})


def passive_template(lines):
    """A client-only partner's `passive_desc` and `values` from its lines
    at each level: a figure that moves with the level becomes a
    placeholder holding its five values, one that does not stays as
    written. A line whose levels disagree in shape is shown at level 1."""
    desc, values = [], {}
    for line in lines:
        figures = [FIGURE.findall(text) for text in line]
        if not line or not line[0] or any(len(f) != len(figures[0])
                                           for f in figures):
            desc.append(line[0] if line else "")
            continue
        parts, at = [], 0
        for i, match in enumerate(FIGURE.finditer(line[0])):
            column = [float(f[i]) for f in figures]
            parts.append(line[0][at:match.start()])
            if len(set(column)) > 1:
                key = f"v{len(values) + 1}"
                values[key] = tuple(_number(v) for v in column)
                parts.append("{%s}" % key)
            else:
                parts.append(match.group())
            at = match.end()
        parts.append(line[0][at:])
        desc.append("".join(parts))
    return "\n".join(desc), values


def _partners(facts):
    by_class = {}
    for key, fact in facts.items():
        rid = int(key)
        known = {field: fact.get(field) for field in PARTNER_FIELDS
                 if fact.get(field) is not None}
        stats = {stat: tuple(_number(v) for v in steps)
                 for stat, steps in (fact.get("stats") or {}).items()}
        if isinstance(PARTNERS.get(rid), dict):
            for field, value in known.items():
                _set("PARTNERS", rid, field, value)
            if stats:
                merged = dict(PARTNERS[rid].get("stats") or {})
                merged.update(stats)
                _set("PARTNERS", rid, "stats", merged)
        elif "name" in known:
            desc, values = passive_template(fact.get("passive_lines") or [])
            _add("PARTNERS", rid, {**copy.deepcopy(DEFAULT_PARTNER), **known,
                                   "passive_desc": desc, "values": values,
                                   "stats": stats,
                                   "ego_desc": fact.get("ego_desc") or "",
                                   "from_client": True})
        flat = fact.get("level_60")
        if isinstance(flat, dict) and "grade" in known and "class" in known:
            by_class.setdefault((known["grade"], known["class"]), []).append(
                {stat: flat.get(stat, 0) for stat in ("atk", "def", "hp")})
    # A class's figures are every partner of that grade and class's; a
    # pair whose partners disagree is left to the hand table.
    for pair, seen in by_class.items():
        if all(stats == seen[0] for stats in seen):
            _set("PARTNER_CLASS_STATS", pair, None, seen[0])


def _ints(values):
    return all(isinstance(v, int) and not isinstance(v, bool) for v in values)


def _numbers(values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool)
               for v in values)


def _exp(tables):
    """Each exp table the client gives, as (exp, level) rows from level
    1: thresholds that start at 0 and never fall. Anything else is left
    to the hand table."""
    for kind, name in EXP_TABLES.items():
        reached = (tables or {}).get(kind)
        if (isinstance(reached, (list, tuple)) and len(reached) > 1
                and _ints(reached) and reached[0] == 0
                and all(a <= b for a, b in zip(reached, reached[1:]))):
            _replace(name, [(exp, level)
                            for level, exp in enumerate(reached, 1)])


def _affinity(held):
    """Affinity's exp to each next level, and its bonuses, where each
    runs unbroken from level 1."""
    held = held or {}
    to_next = {}
    for level, exp in (held.get("to_next") or {}).items():
        if str(level).isdigit() and isinstance(exp, int) and exp > 0:
            to_next[int(level)] = exp
    if to_next and sorted(to_next) == list(range(1, len(to_next) + 1)):
        _replace("AFFINITY_TO_NEXT", to_next)
    bonuses = [tuple(row) for row in held.get("bonuses") or ()
               if isinstance(row, (list, tuple)) and len(row) == 4
               and _ints(row)]
    if len(bonuses) > 1 and [row[0] for row in bonuses] == \
            list(range(1, len(bonuses) + 1)):
        _replace("FRIENDSHIP_BONUSES", bonuses)


def _fragments(held):
    """The main stats each slot carries, by the client's stat ids in
    `STATS`' names, each substat's weight in a new one's draw, and its
    roll bounds. A
    stat `STATS` lacks is left out, the program having no name or roll
    for it; a slot left with none, or missing, leaves the hand table
    standing whole, and so does a set of draw weights that is not one
    for every substat `STATS` rolls."""
    mains = (held or {}).get("mains") or {}
    slots = {}
    for slot, options in mains.items():
        if str(slot).isdigit() and isinstance(options, (list, tuple)):
            slots[int(slot)] = [STATS[option[0]][0] for option in options
                                if isinstance(option, (list, tuple))
                                and option and option[0] in STATS]
    if sorted(slots) == sorted(SLOT_ORDER) and all(slots.values()):
        _replace("SLOT_MAIN_STATS", slots)
    # The draw weights only whole: one substat missing would leave it to
    # the Potential math's default weight beside the client's others.
    draws = (held or {}).get("draws") or {}
    rolled = {stat for stat, info in STATS.items() if info[3] > 0}
    if set(draws) == rolled and all(
            isinstance(share, (int, float)) and not isinstance(share, bool)
            and share > 0 for share in draws.values()):
        _replace("SUBSTAT_DRAW", dict(draws))
    # A substat's roll bounds, its lowest and highest roll: what the Gear
    # Score divides by, and what the presets were derived with
    # (`preset_derivation.rework` re-works them where these move). A
    # stat STATS cannot roll, or rolls the client gives no positive
    # figures for, keeps its own.
    for stat, values in ((held or {}).get("rolls") or {}).items():
        info = STATS.get(stat)
        if not info or info[3] <= 0 or not isinstance(values, (list, tuple)) \
                or not values or not _numbers(values) or min(values) <= 0:
            continue
        bounds = (float(max(values)), float(min(values)))
        if bounds != (float(info[3]), float(info[4])):
            _set("STATS", stat, None, tuple(info[:3]) + bounds)


def _rebuild_by_name():
    CHARACTERS_BY_NAME.clear()
    CHARACTERS_BY_NAME.update({data["name"]: data
                               for data in CHARACTERS.values()
                               if isinstance(data, dict)})


def apply(facts=None):
    """Lay the client's facts over the hand tables: the shipped extract,
    then `facts` (a client read, as `game_client.read_facts` gives it),
    after putting back whatever an earlier call laid down. None lays the
    shipped extract alone."""
    from . import from_client
    _undo()
    for source in ({"combatants": getattr(from_client, "COMBATANTS", {}),
                    "partners": getattr(from_client, "PARTNERS", {}),
                    "exp_tables": getattr(from_client, "EXP_TABLES", {}),
                    "affinity": getattr(from_client, "AFFINITY", {}),
                    "fragment_stats": getattr(from_client, "FRAGMENT_STATS",
                                              {})},
                   facts or {}):
        _combatants(source.get("combatants") or {})
        _partners(source.get("partners") or {})
        _exp(source.get("exp_tables"))
        _affinity(source.get("affinity"))
        _fragments(source.get("fragment_stats"))
    _rebuild_by_name()
