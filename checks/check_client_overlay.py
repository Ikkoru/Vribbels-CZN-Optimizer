"""The game client's facts, laid over the hand tables.

`game_data.client_overlay` writes the client's facts into `CHARACTERS`,
`PARTNERS` and `PARTNER_CLASS_STATS` in place, and swaps the contents
of the exp, Affinity and slot tables in `constants`. Five ways that
goes wrong with nothing to show for it:

1. **A fact lands on the wrong field, or a stale one stays.** Every
   later reader sees it as the table's own value. Held on synthetic
   facts: a changed figure, a combatant and a partner only the client
   knows, and a second `apply` that drops them again.
2. **An overlay undoes someone else's change.** The tables are shared;
   `apply` may put back only what an overlay laid down.
3. **A unit only the client knows breaks a reader**: a passive drawn
   with its placeholders showing, or the validator asking a generated
   entry for a hand table's companions.
4. **A swapped table reaches only some readers.** Its importers hold
   the list or dict itself, so a new object would leave them reading
   the hand table; and a figure worked out from one at import, such as
   the Affinity cap or the Materials tab's EXP targets, would stay the
   hand table's. A source whose levels break off must leave the hand
   table standing, not a table that reads every level above the break
   wrong.
5. **The client and the hand table disagree**, so the overlay changes a
   figure nobody chose. Held on the installed client: every combatant's
   and partner's field, every level's exp, every Affinity level, every
   Memory Fragment option, the classes and the item tables' rarities
   and icons, against the hand tables, the known differences awaiting
   the maintainer noted rather than failed. The
   fragment figures the client is not laid over -- roll bounds, a
   maxed main stat, a rarity's top level -- are held the same way, so a
   patch that moves one fails here rather than scoring on stale ones.

Skips the installed-client half where no client is installed.
"""

import copy

from ._harness import add_source_to_path, note

NAME = "the client's facts lay over the hand tables"

# Differences the maintainer has yet to settle: (res_id, field) ->
# (here, the client's). Noted while they stay exactly that.
KNOWN = {}
# The same for the exp tables: (table, level) -> (here, the client's).
KNOWN_LEVELS = {}
COMBATANT_FIELDS = ("name", "grade", "class", "attribute", "base_atk",
                    "base_def", "base_hp", "base_crit_rate", "base_crit_dmg",
                    "node_50", "node_60")
PARTNER_FIELDS = ("name", "grade", "class", "passive_name", "ego_name",
                  "ego_cost")


def _synthetic(overlay, characters, partners):
    """Complaints from an overlay of synthetic facts."""
    from game_data import CHARACTERS, CHARACTERS_BY_NAME, PARTNERS
    from game_data.partners import PARTNER_CLASS_STATS, format_passive_description
    import game_data_validator as validator
    out = []
    rid = next(k for k, v in CHARACTERS.items() if isinstance(v, dict))
    pid = next(k for k, v in PARTNERS.items() if isinstance(v, dict))
    before_c, before_p = copy.deepcopy(CHARACTERS), copy.deepcopy(PARTNERS)
    before_s = copy.deepcopy(PARTNER_CLASS_STATS)
    CHARACTERS[rid]["_probe"] = "someone else's"
    stat = next(iter(PARTNERS[pid].get("stats") or {"ATK%": ()}))
    facts = {
        "combatants": {
            str(rid): {**{f: CHARACTERS[rid].get(f) for f in COMBATANT_FIELDS},
                       "base_atk": 99999,
                       "level_gains": {"61": {"atk": 1, "def": 2, "hp": 3}}},
            "99001": {"name": "Probe Combatant", "grade": 5,
                      "class": "Striker", "attribute": "Passion",
                      "base_atk": 500, "base_def": 100, "base_hp": 400,
                      "base_crit_rate": 3.0, "base_crit_dmg": 125.0,
                      "node_50": "CRate", "node_60": "ATK%",
                      "level_gains": {}},
        },
        "partners": {
            str(pid): {**{f: PARTNERS[pid].get(f) for f in PARTNER_FIELDS},
                       "stats": {stat: [1, 2, 3, 4, 5]}},
            "99002": {"name": "Probe Partner", "grade": 4.5,
                      "class": "Vanguard", "passive_name": "Probe Passive",
                      "stats": {"DEF%": [18, 21, 24, 27, 30]},
                      "passive_lines": [
                          ["Defense by 18%.", "Defense by 21%.",
                           "Defense by 24%.", "Defense by 27%.",
                           "Defense by 30%."],
                          ["Draws a 2-Cost card, gain 25% Shield"] * 4
                          + ["Draws a 2-Cost card, gain 50% Shield"]],
                      "ego_name": "Probe Ego", "ego_cost": 2,
                      # Unlike the class's own figures, or laying them
                      # over would change nothing to see.
                      "level_60": {"atk": 7, "def": 47, "hp": 107}},
        },
    }
    try:
        overlay.apply(facts)
        if CHARACTERS[rid].get("base_atk") != 99999:
            out.append("a combatant's figure the client states was not laid "
                       "over the hand table's.")
        if (CHARACTERS[rid].get("level_gains") or {}).get(61) != \
                {"atk": 1, "def": 2, "hp": 3}:
            out.append("a combatant's own level-61 steps were not laid over, "
                       "so levels 61 and 62 take the class curve instead.")
        added = CHARACTERS.get(99001)
        if not isinstance(added, dict) or not added.get("from_client") \
                or CHARACTERS_BY_NAME.get("Probe Combatant") is not added:
            out.append("a combatant only the client knows got no entry, or "
                       "no name to be found by: it shows as Unknown.")
        if tuple(PARTNERS[pid]["stats"].get(stat, ())) != (1, 2, 3, 4, 5):
            out.append("a partner's plain stat line from the client was not "
                       "laid over its hand `stats`.")
        shown = format_passive_description(99002, 4)
        if "{" in shown or "30%" not in shown or "2-Cost" not in shown \
                or "50%" not in shown:
            out.append(f"a partner only the client knows draws its passive "
                       f"at the top level as {shown!r}: a figure that moves "
                       f"with the level must become a placeholder, one that "
                       f"does not must stay as written.")
        if PARTNER_CLASS_STATS.get((4.5, "Vanguard")) != \
                {"atk": 7, "def": 47, "hp": 107}:
            out.append("a class's level-60 flat stats from its partners were "
                       "not laid over PARTNER_CLASS_STATS.")
        problems = validator.find_data_problems()
        if problems:
            out.append(f"with the client's facts laid over, the data check "
                       f"reports {problems[:2]}: it must check the hand "
                       f"tables as typed (`client_overlay.hand`).")
        overlay.apply(None)
        if CHARACTERS[rid].get("base_atk") != before_c[rid].get("base_atk") \
                or "level_gains" in CHARACTERS[rid] and \
                "level_gains" not in before_c[rid]:
            out.append("a second apply left the first one's figures standing "
                       "on the hand table.")
        if 99001 in CHARACTERS or 99002 in PARTNERS:
            out.append("a second apply left an earlier one's units in the "
                       "tables.")
        if CHARACTERS[rid].get("_probe") != "someone else's":
            out.append("apply undid a change no overlay made: the tables are "
                       "shared, and it may put back only its own.")
        CHARACTERS[rid].pop("_probe", None)
        if CHARACTERS != before_c or PARTNERS != before_p \
                or PARTNER_CLASS_STATS != before_s:
            out.append("after the second apply the tables are not what they "
                       "were before the first.")
    finally:
        CHARACTERS[rid].pop("_probe", None)
        overlay.apply(None)
    return out


def _tables(overlay):
    """Complaints from synthetic exp, Affinity and slot tables laid
    over."""
    import game_data
    from game_data import constants
    from ui.tabs import inventory_tab, materials_tab
    out = []
    tables = {name: getattr(constants, name)
              for name in overlay.EXP_TABLES.values()}
    for name in ("AFFINITY_TO_NEXT", "FRIENDSHIP_BONUSES", "SLOT_MAIN_STATS",
                 "SUBSTAT_DRAW", "STATS"):
        tables[name] = getattr(constants, name)
    before = {name: copy.deepcopy(table) for name, table in tables.items()}
    # Level n at 100 * (n - 1) exp, to 62 for combatants and 60 for
    # partners, so every Materials target has its level; Affinity capped
    # at 3, on 30 exp; each slot's main stats in the reverse of the hand
    # table's order, slot 4's with a stat the program has no name for;
    # every substat drawn at weight 5. Keys as JSON hands them back.
    ids = {info[0]: stat for stat, info in constants.STATS.items()}
    slots = overlay.hand("SLOT_MAIN_STATS")
    draws = {stat: 5 for stat, info in constants.STATS.items() if info[3] > 0}
    facts = {
        "exp_tables": {"combatant": [100 * n for n in range(62)],
                       "partner": [100 * n for n in range(60)]},
        "affinity": {"to_next": {"1": 10, "2": 20},
                     "bonuses": [[1, 0, 0, 0], [2, 1, 2, 3], [3, 4, 5, 6]]},
        "fragment_stats": {"mains": {
            str(slot): [[ids[name], 1, 1] for name in reversed(names)]
            + ([["S_PROBE_UNNAMED", 1, 1]] if slot == 4 else [])
            for slot, names in slots.items()}, "draws": draws,
            # Crit Rate rolls 1 to 3; an element, which STATS cannot
            # roll, and a substat given a roll of 0, keep their own.
            "rolls": {"S_CRI_INC_ADD": [1.0, 2.0, 3.0],
                      "S_RED_DMG_RATE_INC_ADD": [1.0, 2.0],
                      "S_ATK_INC_RATE_OUT": [0, 1.0]}},
    }
    per = materials_tab.EXP_PER_TIER["Basic"]

    def reset():
        """The tables as typed with the shipped extract laid over, and
        the overlay's own record of them to match: as the import left
        them, which every other check expects."""
        overlay._replaced.clear()
        for name, table in tables.items():
            if isinstance(table, dict):
                table.clear()
                table.update(copy.deepcopy(overlay.hand(name)))
            else:
                table[:] = copy.deepcopy(overlay.hand(name))
        overlay.apply(None)

    try:
        overlay.apply(facts)
        if any(getattr(constants, name) is not table
               for name, table in tables.items()) \
                or game_data.CHARACTER_EXP_TABLE is not \
                tables["CHARACTER_EXP_TABLE"] \
                or inventory_tab.SLOT_MAIN_STATS is not \
                tables["SLOT_MAIN_STATS"]:
            out.append("an overlay put a new object where a table it lays "
                       "over was: whoever imported the table keeps reading "
                       "the hand one.")
        readings = (
            ("combatant level at 4950 exp", constants.get_level_from_exp(4950),
             50),
            ("combatant level past the top", constants.get_level_from_exp(
                10 ** 7), 62),
            ("partner level at 5900 exp",
             constants.get_partner_level_from_exp(5900), 60),
            ("Affinity at 30 exp, the cap", constants.affinity_level(30), 3),
            ("Affinity at 10 exp", constants.affinity_level(10), 2),
            ("the Affinity 3 bonus", constants.get_friendship_bonus(3),
             (4, 5, 6)),
            ("the Materials tab's Level 50 EXP target",
             dict(materials_tab.COMBATANT_EXP_TARGETS).get("Level 50:"),
             -(-4900 // per)),
            ("slot 4's main stats, in the client's order, a stat with no "
             "name left out", constants.SLOT_MAIN_STATS.get(4),
             list(reversed(slots[4]))),
            ("the substats' draw weights", dict(constants.SUBSTAT_DRAW),
             draws),
            ("Crit Rate's roll bounds",
             tuple(constants.STATS["S_CRI_INC_ADD"][3:]), (3.0, 1.0)),
            ("an element's roll bounds, which STATS cannot roll",
             tuple(constants.STATS["S_RED_DMG_RATE_INC_ADD"][3:]),
             tuple(overlay.hand("STATS")["S_RED_DMG_RATE_INC_ADD"][3:])),
            ("ATK%'s roll bounds, given a roll of 0",
             tuple(constants.STATS["S_ATK_INC_RATE_OUT"][3:]),
             tuple(overlay.hand("STATS")["S_ATK_INC_RATE_OUT"][3:])),
        )
        for what, got, wanted in readings:
            if got != wanted:
                out.append(f"with the client's tables laid over, {what} "
                           f"reads {got!r}, not {wanted!r}: a reader kept "
                           f"the hand table, or a figure worked out from it.")
        overlay.apply(None)
        for name, table in tables.items():
            if table != before[name]:
                out.append(f"after a second apply, {name} is not what it "
                           f"was before the first.")
        overlay.apply({
            "exp_tables": {"combatant": [0, 100, 50], "partner": [5, 10]},
            "affinity": {"to_next": {"1": 10, "3": 30},
                         "bonuses": [[1, 0, 0, 0], [3, 1, 1, 1]]},
            "fragment_stats": {"mains": {
                key: options for key, options
                in facts["fragment_stats"]["mains"].items() if key != "6"},
                "draws": {stat: share for stat, share in draws.items()
                          if stat != "S_CRI_INC_ADD"}},
        })
        for name, table in tables.items():
            if table != before[name]:
                out.append(f"a source whose {name} falls, starts above 0, "
                           f"skips a level or lacks a slot or a substat "
                           f"was laid over the hand table.")
        # Where no source lays a table again, what `apply` puts back
        # shows: the hand table, and a change made since the overlay
        # laid it must stay.
        from game_data import from_client
        shipped = from_client.AFFINITY
        from_client.AFFINITY = {}
        try:
            overlay.apply(facts)
            overlay.apply(None)
            if tables["FRIENDSHIP_BONUSES"] != \
                    overlay.hand("FRIENDSHIP_BONUSES"):
                out.append("with no source left to lay it, the Affinity "
                           "table kept an earlier overlay's rows rather "
                           "than going back to the hand table.")
            overlay.apply(facts)
            tables["FRIENDSHIP_BONUSES"].append((4, 9, 9, 9))
            overlay.apply(None)
            if tables["FRIENDSHIP_BONUSES"][-1:] != [(4, 9, 9, 9)]:
                out.append("apply put back an Affinity table someone else "
                           "had changed since the overlay laid it.")
        finally:
            from_client.AFFINITY = shipped
    finally:
        reset()
    return out


class _Rows:
    """Just enough of `game_client.Client` for the level readers."""

    def __init__(self, tables):
        self.tables = tables

    def rows(self, name):
        return self.tables.get(name, [])


def _readers():
    """Complaints from the exp and Affinity readers on synthetic tables.
    A level missing below the top, grades that level apart, an Affinity
    level missing, and combatants naming two bonus groups must each
    leave that table out, so the hand one stands: read anyway, every
    level above the break would read wrong."""
    import game_client as gc
    out = []

    def exp(skip=None, apart=False):
        rows = []
        for level, step in ((1, 100), (2, 200), (3, 300), (4, -1)):
            if level != skip:
                row = {"level": str(level)}
                row.update({column: str(step) for names
                            in gc.EXP_COLUMNS.values() for column in names})
                rows.append(row)
        if apart:
            rows[1][gc.EXP_COLUMNS["combatant"][1]] = "250"
        return _Rows({gc.EXP_TABLE: rows})

    clean = [0, 100, 300, 600]
    for what, client, wanted in (
            ("a clean table", exp(), {"combatant": clean,
                                      "partner": clean}),
            ("a level missing", exp(skip=2), {}),
            ("a combatant grade levelling apart", exp(apart=True),
             {"partner": clean})):
        if gc.exp_tables(client) != wanted:
            out.append(f"on {what}, `game_client.exp_tables` reads "
                       f"{gc.exp_tables(client)}, not {wanted}.")

    def affinity(levels, groups):
        base = [{"id": str(1001 + i), "char_use_playable": "YES"}
                for i in range(len(groups))]
        combat = [{"id": str(1001 + i), gc.AFFINITY_GROUP: group}
                  for i, group in enumerate(groups)]
        bonus = [{"group": "g", "level": "2",
                  "stat0_link_stat_list_id": "S_ATK_INC_ADD_OUT",
                  "stat0_value": "3", "stat1_link_stat_list_id": "none",
                  "stat1_value": "-1"}]
        return _Rows({gc.AFFINITY_LEVEL_TABLE: [
            {"id": str(level), "exp": str(exp)} for level, exp in levels],
            "char_base@char_base": base,
            "char_base@char_combatant": combat,
            gc.AFFINITY_BONUS_TABLE: bonus})

    whole = ((1, 10), (2, 20), (3, -1))
    for what, client, wanted in (
            ("a clean table", affinity(whole, ["g"]),
             {"to_next": {1: 10, 2: 20},
              "bonuses": [(1, 0, 0, 0), (2, 3, 0, 0)]}),
            ("an Affinity level missing",
             affinity(((1, 10), (3, 30), (4, -1)), ["g"]),
             {"bonuses": [(1, 0, 0, 0), (2, 3, 0, 0)]}),
            ("two bonus groups", affinity(whole, ["g", "h"]),
             {"to_next": {1: 10, 2: 20}})):
        if gc.affinity(client) != wanted:
            out.append(f"on {what}, `game_client.affinity` reads "
                       f"{gc.affinity(client)}, not {wanted}.")

    # A main stat is one level-0 value and one step; a cell that is not
    # a figure list is no roll.
    pieces = _Rows({
        gc.PIECE_OPTION_TABLE: [
            {"group": "main_piece_1", "link_stat_list_id": "S_ATK_INC_ADD_OUT",
             "legend_value": "[12]", "legend_reinforce_value": "[2]"},
            {"group": "main_piece_1", "link_stat_list_id": "S_DEF_INC_ADD_OUT",
             "legend_value": "[1,2]", "legend_reinforce_value": "[2]"},
            {"group": gc.PIECE_ROLL_GROUP, "link_stat_list_id": "S_CRI_INC_ADD",
             "legend_value": "[1.2,1.3]", "ratio": "70"},
            {"group": gc.PIECE_ROLL_GROUP,
             "link_stat_list_id": "S_HP_INC_ADD_OUT", "legend_value": "[x]"}],
        gc.PIECE_LEVEL_TABLE: [{"id": "reinforce_legend_0"},
                               {"id": "reinforce_legend_5"},
                               {"id": "reinforce_rare_4"}, {"id": "other"}]})
    wanted = {"mains": {1: [["S_ATK_INC_ADD_OUT", 12, 2]]},
              "rolls": {"S_CRI_INC_ADD": [1.2, 1.3]},
              "draws": {"S_CRI_INC_ADD": 70},
              "max_levels": {4: 5, 3: 4}}
    if gc.fragment_stats(pieces) != wanted:
        out.append(f"on synthetic Memory Fragment options, "
                   f"`game_client.fragment_stats` reads "
                   f"{gc.fragment_stats(pieces)}, not {wanted}.")
    return out


def _installed_tables(client, seen_known):
    """Complaints from the installed client's exp and Affinity tables
    against the hand tables."""
    import game_client
    from game_data.client_overlay import EXP_TABLES, hand
    out = []
    tables = game_client.exp_tables(client)
    for kind, name in EXP_TABLES.items():
        theirs = tables.get(kind)
        if not theirs:
            out.append(f"the client's {kind} exp was not read, its grades' "
                       f"columns disagreeing or stopping short, so {name} "
                       f"stands as typed (`game_client.exp_tables`).")
            continue
        for exp, level in hand(name):
            there = theirs[level - 1] if level <= len(theirs) else None
            if there == exp:
                continue
            if KNOWN_LEVELS.get((name, level)) == (exp, there):
                seen_known.append(f"{name} level {level}")
                continue
            out.append(f"{name}: level {level} is reached at {exp} here, "
                       f"{there} in the client. The program now uses the "
                       f"client's; settle which is right "
                       f"(`docs/client_tables.py --audit`).")
        top = max(level for _exp, level in hand(name))
        if len(theirs) > top:
            note(f"the client's {kind} levels go past {name}'s top, {top}, "
                 f"to {len(theirs)}: the program uses the client's")
    held = game_client.affinity(client)
    for name, key in (("AFFINITY_TO_NEXT", "to_next"),
                      ("FRIENDSHIP_BONUSES", "bonuses")):
        theirs, ours = held.get(key), hand(name)
        if key == "bonuses":
            theirs = [tuple(row) for row in theirs or ()]
            ours = [tuple(row) for row in ours]
        if theirs != ours:
            out.append(f"{name} as typed is not the client's Affinity table "
                       f"(`game_client.affinity`): the program now uses the "
                       f"client's, where it reads one. Settle which is right "
                       f"(`docs/client_tables.py --audit`).")
    out += _installed_fragments(client)
    out += _installed_items(client)
    return out


def _installed_items(client):
    """Complaints from the installed client's classes and item rarities
    and icons against the hand tables: a class either side lacks, or
    listed in another order than the Materials tab's; an item table's
    rarity, which the client's replaces (`constants.item_art`), or its
    icon."""
    from pathlib import Path
    import game_client
    from game_data.constants import CLASSES, ITEM_TABLES, table_art
    from ui.tabs.materials_tab import CLASS_ORDER
    out = []
    classes = tuple(game_client.class_names(client).values())
    if set(classes) != set(CLASSES):
        out.append(f"the client's classes are {classes}, constants.CLASSES "
                   f"{CLASSES}: a class the program lacks needs its tables "
                   f"(PARTNER_CLASS_STATS, the Materials tab's rows).")
    elif classes != tuple(CLASS_ORDER):
        out.append(f"the game lists the classes {classes}, the Materials "
                   f"tab {CLASS_ORDER}.")
    rarities = game_client.item_rarities(client)
    icons = {}
    for path in client.archive.files:
        if path.startswith("db/item_") and path.endswith("@item.db"):
            icons.update({r.get("id"): r.get("icon")
                          for r in client.rows(path[3:-3])})
    for table in ITEM_TABLES:
        for res_id in table:
            art = table_art(res_id)
            if art is None:
                continue
            if art.rarity != rarities.get(res_id):
                out.append(f"item {res_id} is {art.rarity!r} by the item "
                           f"tables, {rarities.get(res_id)!r} by the client. "
                           f"The program now draws the client's plate; "
                           f"settle which is right.")
            if art.icon and Path(art.icon).stem != icons.get(str(res_id)):
                out.append(f"item {res_id} draws {art.icon}, the client "
                           f"{icons.get(str(res_id))!r}.")
    return out


def _installed_fragments(client):
    """Complaints from the installed client's Memory Fragment options
    against the hand tables: the slots' main stats and a substat's roll
    bounds (`STATS`), which the client's replace, and what is held but
    never replaced -- a maxed Legendary's main stat (`MAIN_STAT_VALUES`,
    as the game draws it, rounded) and each rarity's top level
    (`MAX_LEVEL_PER_RARITY`)."""
    import game_client
    from game_data.client_overlay import hand
    from game_data.constants import MAIN_STAT_VALUES, MAX_LEVEL_PER_RARITY
    STATS = hand("STATS")
    held = game_client.fragment_stats(client)
    names = {stat: info[0] for stat, info in STATS.items()}
    top, out = held["max_levels"].get(4), []
    for slot, options in sorted(held["mains"].items()):
        theirs = [names.get(stat, stat) for stat, _start, _step in options]
        if set(theirs) != set(hand("SLOT_MAIN_STATS").get(slot, ())):
            out.append(f"slot {slot} carries {theirs} in the client, "
                       f"{hand('SLOT_MAIN_STATS').get(slot)} in "
                       f"constants.SLOT_MAIN_STATS. The program now offers "
                       f"the client's; settle which is right.")
        for stat, start, step in options:
            typed = MAIN_STAT_VALUES.get((slot, names.get(stat, stat)))
            ceiling = start + (top or 0) * step
            places = len(repr(typed).split(".")[1]) \
                if "." in repr(typed) else 0
            if typed is None or round(ceiling, places) != typed:
                out.append(f"slot {slot} {names.get(stat, stat)}: a maxed "
                           f"Legendary's main is {typed} in "
                           f"MAIN_STAT_VALUES, {ceiling:g} by the client.")
    for stat, rolls in held["rolls"].items():
        info = STATS.get(stat)
        if not info or info[3] <= 0:
            out.append(f"the client rolls {stat} as a substat ({rolls}), "
                       f"which STATS has no roll for.")
        elif (info[4], info[3]) != (min(rolls), max(rolls)):
            out.append(f"{info[0]} rolls {info[4]} to {info[3]} in STATS, "
                       f"{min(rolls)} to {max(rolls)} in the client. The "
                       f"program now scores by the client's, and re-works "
                       f"its presets for a moved top roll; update STATS and "
                       f"re-derive the presets (`docs/preset_weights.md`).")
    for stat, info in STATS.items():
        if info[3] > 0 and stat not in held["rolls"]:
            out.append(f"{info[0]} rolls in STATS and is no substat in the "
                       f"client.")
    for tier, level in sorted(MAX_LEVEL_PER_RARITY.items()):
        if held["max_levels"].get(tier) != level:
            out.append(f"rarity {tier} tops out at level {level} in "
                       f"MAX_LEVEL_PER_RARITY, "
                       f"{held['max_levels'].get(tier)} in the client.")
    if held["draws"] != hand("SUBSTAT_DRAW"):
        out.append(f"the client draws new substats by {held['draws']}, "
                   f"constants.SUBSTAT_DRAW by {hand('SUBSTAT_DRAW')}. The "
                   f"Potential math now uses the client's; settle which is "
                   f"right.")
    return out


def _installed(characters, partners):
    """Complaints from the installed client's facts against the hand
    tables."""
    import game_client
    from game_data.characters import level_bonus
    from game_data.client_overlay import hand
    install = game_client.find_install()
    if install is None:
        note("no game client installed, so its combatants and partners were "
             "not held to the hand tables")
        return []
    client = game_client.Client(install)
    out, seen_known = [], []
    hand_c, hand_p = hand("CHARACTERS"), hand("PARTNERS")
    hand_s = hand("PARTNER_CLASS_STATS")
    for rid, theirs in game_client.combatants(client).items():
        ours = hand_c.get(rid)
        if not isinstance(ours, dict):
            note(f"combatant {rid} {theirs.get('name')} is in the client and "
                 f"not in characters.py: it shows from the client's facts")
            continue
        for field in COMBATANT_FIELDS:
            pair = (ours.get(field), theirs.get(field))
            if pair[0] == pair[1]:
                continue
            if KNOWN.get((rid, field)) == pair:
                seen_known.append(f"{ours.get('name')} {field}")
                continue
            out.append(f"combatant {rid} {ours.get('name')}: {field} is "
                       f"{pair[0]!r} in characters.py, {pair[1]!r} in the "
                       f"client. The program now shows the client's; settle "
                       f"which is right (`docs/client_tables.py --audit`).")
        for level in (61, 62):
            if level_bonus(ours, level) != theirs["level_gains"][level]:
                out.append(f"combatant {rid} {ours.get('name')}: level {level} "
                           f"adds {level_bonus(ours, level)} by the class "
                           f"curve, {theirs['level_gains'][level]} by the "
                           f"client.")
    for pid, theirs in game_client.partners(client).items():
        ours = hand_p.get(pid)
        if not isinstance(ours, dict):
            note(f"partner {pid} {theirs.get('name')} is in the client and "
                 f"not in partners.py: it shows from the client's facts")
            continue
        for field in PARTNER_FIELDS:
            if ours.get(field) != theirs.get(field):
                out.append(f"partner {pid} {ours.get('name')}: {field} is "
                           f"{ours.get(field)!r} in partners.py, "
                           f"{theirs.get(field)!r} in the client.")
        for stat, steps in (theirs.get("stats") or {}).items():
            if tuple((ours.get("stats") or {}).get(stat, ())) != tuple(steps):
                out.append(f"partner {pid} {ours.get('name')}: {stat} is "
                           f"{(ours.get('stats') or {}).get(stat)} in "
                           f"partners.py, {tuple(steps)} in the client.")
        pair = (ours.get("grade"), ours.get("class"))
        if hand_s.get(pair) != theirs.get("level_60"):
            out.append(f"partner {pid} {ours.get('name')}: level-60 stats are "
                       f"{hand_s.get(pair)} for {pair} in PARTNER_CLASS_STATS, "
                       f"{theirs.get('level_60')} in the client.")
    out += _installed_tables(client, seen_known)
    if seen_known:
        note(f"awaiting the maintainer, the client's taken: "
             f"{', '.join(seen_known)}")
    return out


def run():
    add_source_to_path()
    from game_data import client_overlay
    from game_data import characters, partners
    failures = _synthetic(client_overlay, characters, partners)
    failures += _tables(client_overlay)
    failures += _readers()
    failures += _installed(characters, partners)
    return failures


def _hand(name, change):
    """Change the hand table `name` as `change` says: one typed wrong."""
    from game_data import client_overlay
    change(client_overlay.hand(name))


def _hand_exp_off():
    def change(rows):
        i = next(i for i, (_exp, level) in enumerate(rows) if level == 40)
        rows[i] = (rows[i][0] + 1, 40)
    _hand("CHARACTER_EXP_TABLE", change)


def _hand_affinity_off():
    _hand("AFFINITY_TO_NEXT", lambda table: table.update({5: 999}))


def _hand_roll_off():
    def change(stats):
        info = stats["S_CRI_INC_ADD"]
        stats["S_CRI_INC_ADD"] = info[:3] + (2.1, info[4])
    _hand("STATS", change)


def _hand_unrollable():
    def change(stats):
        stats["S_CRI_INC_ADD"] = stats["S_CRI_INC_ADD"][:3] + (0, 0)
    _hand("STATS", change)


def _hand_slot_off():
    _hand("SLOT_MAIN_STATS", lambda slots: slots[4].append("DEF%"))


def _main_value_off():
    from game_data import constants
    constants.MAIN_STAT_VALUES[(4, "CRate")] = 28


def _max_level_off():
    from game_data import constants
    constants.MAX_LEVEL_PER_RARITY[4] = 6


def _tier_rarity_off():
    from game_data import constants
    constants.TIER_RARITY["Common"] = "Uncommon"


def _class_added():
    from game_data import constants
    constants.CLASSES = constants.CLASSES + ("Sniper",)


def _class_order_off():
    from ui.tabs import materials_tab
    order = list(materials_tab.CLASS_ORDER)
    order[2], order[3] = order[3], order[2]
    materials_tab.CLASS_ORDER = tuple(order)


def _icon_off():
    from game_data import constants
    row = constants.GROWTH_STONES[3120001]
    constants.GROWTH_STONES[3120001] = row[:2] + ("icon_item_probe.png",)


def _inventory_copies():
    """The Memory Fragments tab holding a copy of the slots' main stats,
    which the overlay cannot reach."""
    from game_data import constants
    from ui.tabs import inventory_tab
    inventory_tab.SLOT_MAIN_STATS = copy.deepcopy(constants.SLOT_MAIN_STATS)


# What this check must catch, for `checks/faults.py`.
OVERLAY, CLIENT = "game_data.client_overlay", "game_client"
FAULTS = [
    ("a client-only combatant left out", f"{OVERLAY}:_combatants",
     'elif rid and "name" in known and rid not in CHARACTERS:', "elif False:",
     "a combatant only the client knows got no entry"),
    ("a class's flat stats not laid", f"{OVERLAY}:_partners",
     '_set("PARTNER_CLASS_STATS", pair, None, seen[0])', "pass",
     "a class's level-60 flat stats"),
    ("a new object for a replaced table", f"{OVERLAY}:_replace",
     "_fill(table, contents)",
     "table = type(table)(contents)\n    _TABLES[name] = table\n"
     "    from . import constants as _laid\n    setattr(_laid, name, table)",
     "an overlay put a new object"),
    ("the Memory Fragments tab's own copy", _inventory_copies, None, None,
     "an overlay put a new object"),
    ("the Materials targets worked out at import",
     "ui.tabs.materials_tab:COMBATANT_EXP_TARGETS",
     "_LiveExpTargets(CHARACTER_EXP_TABLE", "_exp_targets(CHARACTER_EXP_TABLE",
     "the Materials tab's Level 50 EXP target"),
    ("the Affinity cap fixed", "game_data.constants:affinity_level",
     "level = max(AFFINITY_TO_NEXT, default=0) + 1\n"
     "    threshold = sum(AFFINITY_TO_NEXT.values())",
     "level, threshold = 40, 14000", "Affinity at 30 exp, the cap"),
    ("a falling or late exp table laid", f"{OVERLAY}:_exp",
     "and _ints(reached) and reached[0] == 0", "and _ints(reached)",
     "starts above 0"),
    ("a slot missing laid", f"{OVERLAY}:_fragments",
     "if sorted(slots) == sorted(SLOT_ORDER) and all(slots.values()):",
     "if slots:", "lacks a slot or a substat"),
    ("a main stat with no name kept", f"{OVERLAY}:_fragments",
     ["slots[int(slot)] = [STATS[option[0]][0] for option in options",
      "and option and option[0] in STATS]"],
     ["slots[int(slot)] = [STATS.get(option[0], (option[0],))[0] "
      "for option in options", "and option]"],
     "a stat with no name left out"),
    ("a partial set of draw weights laid", f"{OVERLAY}:_fragments",
     "if set(draws) == rolled and all(", "if draws and all(",
     "lacks a slot or a substat"),
    ("the client's rolls never laid", f"{OVERLAY}:_fragments",
     'for stat, values in ((held or {}).get("rolls") or {}).items():',
     "for stat, values in {}.items():", "Crit Rate's roll bounds"),
    ("a roll of 0 laid", f"{OVERLAY}:_fragments",
     "or not values or not _numbers(values) or min(values) <= 0:",
     "or not values or not _numbers(values):", "given a roll of 0"),
    ("a table laid back over someone's change", f"{OVERLAY}:_undo",
     "        if _TABLES[name] == laid:\n"
     "            _fill(_TABLES[name], before)",
     "        _fill(_TABLES[name], before)",
     "apply put back an Affinity table someone else"),
    ("a replaced table never put back", f"{OVERLAY}:_undo",
     "if _TABLES[name] == laid:", "if False:", "with no source left to lay it"),
    ("exp summed across a gap", f"{CLIENT}:exp_columns",
     "            if not isinstance(step, int):\n"
     "                reached = None",
     "            if not isinstance(step, int) and level > 99:\n"
     "                reached = None\n"
     "            elif not isinstance(step, int):\n"
     "                level += 1",
     "on a level missing"),
    ("grades levelling apart read", f"{CLIENT}:exp_tables",
     "if tables[0] and all(table == tables[0] for table in tables):",
     "if tables[0]:", "on a combatant grade levelling apart"),
    ("an Affinity level missing read", f"{CLIENT}:affinity",
     "if to_next and sorted(to_next) == list(range(1, len(to_next) + 1)):",
     "if to_next:", "on an Affinity level missing"),
    ("two bonus groups read", f"{CLIENT}:affinity",
     "if len(groups) != 1:\n        return out\n"
     "    group, rows = groups.pop(), {}",
     "if not groups:\n        return out\n"
     "    group, rows = sorted(groups)[0], {}",
     "on two bonus groups"),
    ("a main stat of several values read", f"{CLIENT}:fragment_stats",
     "if slot and start and step and len(start) == len(step) == 1:",
     "if slot and start and step:", "on synthetic Memory Fragment options"),
    ("the hand exp table typed wrong", _hand_exp_off, None, None,
     "CHARACTER_EXP_TABLE: level 40 is reached at"),
    ("the hand Affinity table typed wrong", _hand_affinity_off, None, None,
     "AFFINITY_TO_NEXT as typed is not the client's"),
    ("a hand roll typed wrong", _hand_roll_off, None, None,
     "to 2.1 in STATS"),
    ("a hand substat with no roll", _hand_unrollable, None, None,
     "which STATS has no roll for"),
    ("a hand slot typed wrong", _hand_slot_off, None, None,
     "slot 4 carries"),
    ("a maxed main stat typed wrong", _main_value_off, None, None,
     "a maxed Legendary's main is 28"),
    ("a rarity's top level typed wrong", _max_level_off, None, None,
     "rarity 4 tops out at level 6"),
    ("a tier's rarity typed wrong", _tier_rarity_off, None, None,
     "by the item tables"),
    ("a class the client lacks", _class_added, None, None,
     "a class the program lacks needs its tables"),
    ("the classes in another order", _class_order_off, None, None,
     "the game lists the classes"),
    ("an item's icon typed wrong", _icon_off, None, None,
     "draws icon_item_probe.png"),
]
