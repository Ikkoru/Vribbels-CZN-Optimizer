"""The game client's combatants and partners, laid over the hand tables.

`game_data.client_overlay` writes the client's facts into `CHARACTERS`,
`PARTNERS` and `PARTNER_CLASS_STATS` in place. Four ways that goes
wrong with nothing to show for it:

1. **A fact lands on the wrong field, or a stale one stays.** Every
   later reader sees it as the table's own value. Held on synthetic
   facts: a changed figure, a combatant and a partner only the client
   knows, and a second `apply` that drops them again.
2. **An overlay undoes someone else's change.** The tables are shared;
   `apply` may put back only what an overlay laid down.
3. **A unit only the client knows breaks a reader**: a passive drawn
   with its placeholders showing, or the validator asking a generated
   entry for a hand table's companions.
4. **The client and the hand table disagree**, so the overlay changes a
   figure nobody chose. Held on the installed client: every combatant's
   and partner's field against the hand table, the known differences
   awaiting the maintainer noted rather than failed.

Skips the installed-client half where no client is installed.
"""

import copy

from ._harness import add_source_to_path, note

NAME = "the client's combatants and partners lay over the hand tables"

# Differences the maintainer has yet to settle: (res_id, field). Noted
# while they stay exactly that.
KNOWN = {
    # The client's tree gives Tiphera DEF% on node 50 and Crit Rate on
    # node 60; characters.py has them the other way round.
    (30084, "node_50"): ("CRate", "DEF%"),
    (30084, "node_60"): ("DEF%", "CRate"),
}
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
                      "level_60": {"atk": 5, "def": 44, "hp": 105}},
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
                {"atk": 5, "def": 44, "hp": 105}:
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
    if seen_known:
        note(f"awaiting the maintainer, the client's taken: "
             f"{', '.join(seen_known)}")
    return out


def run():
    add_source_to_path()
    from game_data import client_overlay
    from game_data import characters, partners
    failures = _synthetic(client_overlay, characters, partners)
    failures += _installed(characters, partners)
    return failures
