"""What the server has said about the game's own tables, used where the
tables are silent or wrong: combatants' bases at levels 60 to 62, the
level gains that follow from them, and partners' flat stats per level.

Empty until `install`. The app fills it on every snapshot load from the
player's own readings (`base_stats_store`) and the shipped shared facts
(`shared_facts`), the newest reading of each winning. From then on
`characters.get_character_stats_at_level` and
`partners.get_partner_stats` answer with the server's figure where one
is known -- so the program stays right after a patch it was never
updated for, and fills a level gain nobody typed in.

**The tables are still read directly** through
`characters.table_stats_at_level`, `characters.level_bonus` and
`partners.table_partner_stats`, which never look here. That is what
`base_stats_store.audit`, the launch-time validator and the checks hold
the server against: through the overlay they would be comparing the
server with itself, and every disagreement would read as agreement.

**Process-wide state.** `checks/run_all.py` clears it after every
check, so a check that installs it cannot change what a later one sees.
"""

# Combatant name -> {level: (atk, def, hp)}.
BASES = {}
# (class, grade) -> {level: {"atk", "def", "hp"}}: the gain every
# combatant of the pair with readings at both levels agrees on.
GAINS = {}
# Partner res_id -> {level: (atk, def, hp)}.
PARTNER_FLATS = {}


def install(bases, partner_flats):
    """Replace what is known.

    `bases` is {res_id: {level: [atk, def, hp]}} and `partner_flats`
    {partner res_id: {level: [atk, def, hp]}}; ids and levels may be
    strings, as a JSON file holds them. A combatant `CHARACTERS` does
    not name is skipped: the program has no class or grade for it.
    """
    from game_data.characters import CHARACTERS
    names = {}
    for rid, levels in (bases or {}).items():
        char = CHARACTERS.get(_int(rid))
        if isinstance(char, dict):
            names[char["name"]] = _levels(levels)
    flats = {_int(pid): _levels(levels)
             for pid, levels in (partner_flats or {}).items()
             if _int(pid) is not None}
    gains = _class_gains(names)
    BASES.clear()
    BASES.update(names)
    GAINS.clear()
    GAINS.update(gains)
    PARTNER_FLATS.clear()
    PARTNER_FLATS.update(flats)


def clear():
    install({}, {})


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _levels(levels):
    out = {}
    for level, values in (levels or {}).items():
        if _int(level) is not None and isinstance(values, (list, tuple)) \
                and len(values) == 3:
            out[_int(level)] = tuple(values)
    return out


def _class_gains(names):
    """{(class, grade): {level: gain}} where every combatant of the pair
    with readings at both levels shows the same gain. A combatant with
    a gain of its own in characters.py does not vote: it is the one
    known to differ from its pair."""
    from game_data.characters import CHARACTERS_BY_NAME
    seen = {}
    for name, levels in names.items():
        char = CHARACTERS_BY_NAME.get(name)
        if not isinstance(char, dict):
            continue
        for step in (61, 62):
            if step in levels and step - 1 in levels \
                    and char.get("level_%d_bonus" % step) is None:
                gain = tuple(a - b for a, b in zip(levels[step],
                                                   levels[step - 1]))
                seen.setdefault((char.get("class"), char.get("grade"), step),
                                set()).add(gain)
    out = {}
    for (cls, grade, step), found in seen.items():
        if len(found) == 1:
            atk, def_, hp = next(iter(found))
            out.setdefault((cls, grade), {})[step] = {
                "atk": atk, "def": def_, "hp": hp}
    return out
