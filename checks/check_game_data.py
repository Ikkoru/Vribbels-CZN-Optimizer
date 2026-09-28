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
    """Levels 61 and 62 add the combatant's own gain, else their class
    and grade's, else nothing -- and 62 adds 61's first. A lookup that
    stops at the combatant's own key gives every combatant without one
    the level-60 base, which reads as a plausible stat."""
    from game_data.characters import (LEVEL_BONUS_BY_CLASS,
                                      get_character_stats_at_level)
    out = []
    known = next(k for k, v in LEVEL_BONUS_BY_CLASS.items() if v[61])
    unknown = next((k for k, v in LEVEL_BONUS_BY_CLASS.items()
                    if not v[61]), None)
    gain = LEVEL_BONUS_BY_CLASS[known][61]
    entry = {"class": known[0], "grade": known[1], "base_atk": 400,
             "base_def": 150, "base_hp": 300}
    at = get_character_stats_at_level
    if at(entry, 61)["base_atk"] != 400 + gain["atk"]:
        out.append(f"a {known[0]} grade {known[1]} combatant with no gain "
                   f"of their own gets {at(entry, 61)['base_atk']} ATK at "
                   f"61, not {400 + gain['atk']}: the pair's gain is not "
                   f"read. See `level_bonus` in game_data/characters.py.")
    own = dict(entry, level_61_bonus={"atk": 1, "def": 1, "hp": 1})
    if at(own, 61)["base_atk"] != 401:
        out.append("a combatant's own level_61_bonus does not override "
                   "their class and grade's.")
    if at(entry, 60) != {"base_atk": 400, "base_def": 150, "base_hp": 300}:
        out.append("level 60 is not the base unchanged.")
    both = dict(entry, level_62_bonus={"atk": 2, "def": 2, "hp": 2})
    if at(both, 62)["base_atk"] != 400 + gain["atk"] + 2:
        out.append("level 62 does not add both levels' gains.")
    if unknown is not None:
        blank = dict(entry, **{"class": unknown[0], "grade": unknown[1]})
        if at(blank, 62) != at(blank, 60):
            out.append("a pair whose gains are unknown adds something at "
                       "61 or 62.")
    return out


def _level_rules_report():
    """The data check reports an own gain that differs from its pair's,
    one whose pair is unknown, and a combatant with no pair row -- each
    against a copy of the real data, put back after."""
    import game_data_validator as v
    from game_data import CHARACTERS
    from game_data.characters import LEVEL_BONUS_BY_CLASS
    out = []
    rid, entry = next((k, c) for k, c in CHARACTERS.items()
                      if isinstance(c, dict) and c.get("level_61_bonus"))
    pair_key = (entry["class"], entry["grade"])
    saved_entry = dict(entry)
    saved_pair = LEVEL_BONUS_BY_CLASS[pair_key]
    cases = (
        ("an own gain unlike its pair's", "differs from",
         lambda: entry.update(level_61_bonus=dict(
             entry["level_61_bonus"],
             atk=entry["level_61_bonus"]["atk"] - 1))),
        ("an own gain beside an unknown pair", "fill the pair",
         lambda: LEVEL_BONUS_BY_CLASS.__setitem__(
             pair_key, {61: None, 62: None})),
        ("a combatant with no pair row", "no LEVEL_BONUS_BY_CLASS row",
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
