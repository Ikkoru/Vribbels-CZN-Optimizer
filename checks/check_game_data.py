"""Run the launch-time game-data validator without launching.

Both layers, the same ones `czn_optimizer_gui.py` runs: the text/AST
layer that catches syntax errors and duplicate dict keys, and the value
layer that checks ranges, vocabularies and shapes.

The value layer is advisory in the app -- the data still loads and the
scores are simply wrong -- which is exactly why it is worth failing on
here, where nobody is waiting to use the program.
"""

from ._harness import add_source_to_path

NAME = "game data"


def _level_gains_follow_their_pair():
    """Levels 61 and 62 add the gains of the curve the combatant
    follows -- their `level_curve`, else their own class and grade's --
    and 62 adds 61's first. A lookup that misses gives the level-60
    base, which reads as a plausible stat."""
    from game_data.characters import (LEVEL_BONUS_BY_CLASS,
                                      table_stats_at_level)
    out = []
    # Two pairs whose ATK gains differ, so a curve read off the wrong
    # one shows.
    known = next(iter(LEVEL_BONUS_BY_CLASS))
    gain = LEVEL_BONUS_BY_CLASS[known]
    other = next(k for k, v in LEVEL_BONUS_BY_CLASS.items()
                 if v[61]["atk"] != gain[61]["atk"])
    entry = {"class": known[0], "grade": known[1], "base_atk": 400,
             "base_def": 150, "base_hp": 300}
    at = table_stats_at_level
    if at(entry, 61)["base_atk"] != 400 + gain[61]["atk"]:
        out.append(f"a {known[0]} grade {known[1]} combatant gets "
                   f"{at(entry, 61)['base_atk']} ATK at 61, not "
                   f"{400 + gain[61]['atk']}: the pair's gain is not "
                   f"read. See `level_bonus` in game_data/characters.py.")
    moved = dict(entry, level_curve=other)
    if at(moved, 61)["base_atk"] != 400 + LEVEL_BONUS_BY_CLASS[other][61][
            "atk"]:
        out.append("a combatant's level_curve does not put them on that "
                   "pair's gains. See `level_curve` in "
                   "game_data/characters.py.")
    if at(entry, 60) != {"base_atk": 400, "base_def": 150, "base_hp": 300}:
        out.append("level 60 is not the base unchanged.")
    if at(entry, 62)["base_atk"] != 400 + gain[61]["atk"] + gain[62]["atk"]:
        out.append("level 62 does not add both levels' gains.")
    blank = dict(entry, grade=0)
    if at(blank, 62) != at(blank, 60):
        out.append("a pair with no row adds something at 61 or 62.")
    return out


def _level_rules_report():
    """The data check reports a gain key nothing reads, a level_curve
    that is not a pair, and a curve with no pair row -- each against a
    copy of the real data, put back after."""
    import game_data_validator as v
    from game_data.characters import LEVEL_BONUS_BY_CLASS, level_curve
    # The validator checks the table as typed, under the client's facts
    # (`game_data.client_overlay`), so the faults go into that one.
    from game_data.client_overlay import hand
    CHARACTERS = hand("CHARACTERS")
    out = []
    rid, entry = next((k, c) for k, c in CHARACTERS.items()
                      if isinstance(c, dict) and c.get("level_curve"))
    pair_key = level_curve(entry)
    saved_entry = dict(entry)
    saved_pair = LEVEL_BONUS_BY_CLASS[pair_key]
    cases = (
        ("a level_61_bonus key, which nothing reads", "is not read",
         lambda: entry.update(level_61_bonus={"atk": 1, "def": 1,
                                              "hp": 1})),
        ("a level_curve that is not a pair", "is not a (class, grade)",
         lambda: entry.update(level_curve="Vanguard")),
        ("a curve with no pair row", "no LEVEL_BONUS_BY_CLASS row",
         lambda: LEVEL_BONUS_BY_CLASS.pop(pair_key)),
    )
    try:
        for what, needle, breaks in cases:
            breaks()
            if not any(needle in p for p in v.find_data_problems()):
                out.append(f"the data check stays quiet about {what}. See "
                           f"`_check_characters` in game_data_validator.py.")
            entry.clear()
            entry.update(saved_entry)
            LEVEL_BONUS_BY_CLASS[pair_key] = saved_pair
    finally:
        entry.clear()
        entry.update(saved_entry)
        LEVEL_BONUS_BY_CLASS[pair_key] = saved_pair
    return out


def run():
    failures = []
    add_source_to_path()
    import game_data_validator as v
    failures.extend(_level_gains_follow_their_pair())
    failures.extend(_level_rules_report())

    if not v.check_data_files():
        failures.append(
            "check_data_files() failed: a game_data file has a syntax "
            "error or a duplicate dict key. The app would refuse to start."
        )

    problems = v.find_data_problems()
    for p in problems[:12]:
        failures.append(f"data: {p}")
    if len(problems) > 12:
        failures.append(f"... and {len(problems) - 12} more data problems")
    return failures
