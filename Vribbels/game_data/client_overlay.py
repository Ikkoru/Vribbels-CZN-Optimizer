"""The game client's facts, laid over the hand tables.

What the client states of a combatant or a partner wins over what
`characters.py` and `partners.py` type by hand; the hand tables are the
fallback, for whatever the client does not hold. The order, the first
that knows a fact winning (`docs/client_data.md`):

1. this machine's client read (`game_client.use`): the read of this
   build, its cache, or the last cache of an earlier build;
2. the shipped extract, `from_client.py`, as of the build the program
   shipped with;
3. the hand tables as typed.

The server's own readings still go over all three where they exist
(`game_data.learned`, asked by `get_character_stats_at_level` and
`get_partner_stats`).

**Laid over in place.** The tables are read in many places, every one
holding the same dict, so the facts are written into it field by field;
`apply` first puts back every field and entry an earlier `apply` laid
down, then lays down the sources again, so it can run any number of
times and a field nothing laid over is never touched.

**What stays the program's own** in an entry the client fills: what the
client holds no value for -- a partner's conditional effects
(`stats_conditional`), its `passive_desc` template and `values`, and the
maintainer's markers. A plain stat line of a partner's passive is the
client's (`game_client._passive_stats`).

**A unit only the client knows** gets an entry built from the client
alone, marked `from_client`, so it shows by name with its stats instead
of as Unknown. `game_data_validator` checks the hand tables as typed
(`hand`), so such an entry never asks for a hand table's companions,
such as a Potential 7 entry.
"""

import copy
import re

from .characters import CHARACTERS, CHARACTERS_BY_NAME, DEFAULT_CHARACTER
from .partners import DEFAULT_PARTNER, PARTNERS, PARTNER_CLASS_STATS

# The hand tables as typed, before anything is laid over them: what the
# validator checks and the audit holds the client against.
_HAND = {"CHARACTERS": copy.deepcopy(CHARACTERS),
         "PARTNERS": copy.deepcopy(PARTNERS),
         "PARTNER_CLASS_STATS": copy.deepcopy(PARTNER_CLASS_STATS)}
_TABLES = {"CHARACTERS": CHARACTERS, "PARTNERS": PARTNERS,
           "PARTNER_CLASS_STATS": PARTNER_CLASS_STATS}

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


def hand(name):
    """A table as typed by hand: CHARACTERS, PARTNERS or
    PARTNER_CLASS_STATS. Never laid over; never change it."""
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


def _undo():
    """Put back every field and entry an overlay laid down."""
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


def _template(lines):
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
            desc, values = _template(fact.get("passive_lines") or [])
            _add("PARTNERS", rid, {**copy.deepcopy(DEFAULT_PARTNER), **known,
                                   "passive_desc": desc, "values": values,
                                   "stats": stats, "ego_desc": "",
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
                    "partners": getattr(from_client, "PARTNERS", {})},
                   facts or {}):
        _combatants(source.get("combatants") or {})
        _partners(source.get("partners") or {})
    _rebuild_by_name()
