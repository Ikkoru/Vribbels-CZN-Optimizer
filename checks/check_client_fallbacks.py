"""The game client's names go over the program's, and its tables fill
what the client is silent on.

A patch can give an id to another thing, so a name the program keeps
by hand would go on naming the old one: where the client names an id,
its name is the one shown, and the program's table answers only where
no client read and no shipped table does. Two readers hold that order,
and a third its own; an item's name is held by `check_event_names`.

1. **A Chaos's name** (`chaos_estimate.chaos_name`): the client's over
   `CHAOS_NAMES`, which names a stage no client read holds, and the
   stage id what neither does.
2. **A Zero System special** (`chaos_estimate.zero_special_name`): the
   same order, then the id.
3. **Which 5-stars the Normal Rescues offer** (`gacha_history.pool_of`):
   a rates reply the account captured over the client's pools, and the
   client's over nothing. Without either, a Seasonal rerun counts on the
   rerun counter, its pulls on the wrong pity.
4. **The partners' Exploration Passives, the Card Skin tables and the
   season trees' node counts** (`game_client.known_exploration_passives`,
   `known_card_skins`, `known_season_nodes`): this machine's read over
   the shipped copy, which stands for the rest.

Held on synthetic client facts, put in place with `game_client.use` and
taken away after, and on probe entries put into the program's tables
for the run.
"""

from ._harness import add_source_to_path

NAME = "the game client's names go over the program's, its tables fill the rest"

# Probe ids no table, client or shipped extract holds.
PROBE_STAGE, TABLE_STAGE = 999999, 999998
PROBE_PARTNER, PROBE_SKIN = 99999, 9899999
PROBE_SPECIAL = "zero_orb_special_probe"
PROBE_SEASON = "disaster_s99"
TABLE_SPECIAL = "zero_orb_special_table_probe"


def run():
    add_source_to_path()
    import chaos_estimate as ce
    import gacha_history as gh
    import game_client

    out = []
    held_facts, held_general = game_client._facts, gh._general_units
    stage = next(iter(ce.CHAOS_NAMES))
    special = next(iter(ce.ZERO_SPECIALS))
    facts = {"format": game_client.CACHE_FORMAT,
             "chaos_names": {str(stage): ["The Client's Spelling", None],
                             str(PROBE_STAGE): ["Probe Chaos",
                                                "disaster_s99"]},
             "zero_specials": {special: "Client Name",
                               PROBE_SPECIAL: "Probe Special"},
             "general_units": [77001]}
    try:
        ce.CHAOS_NAMES[TABLE_STAGE] = ("Table Chaos", "disaster_s98")
        ce.ZERO_SPECIALS[TABLE_SPECIAL] = "Table Special"
        game_client.use(facts)
        if ce.chaos_name({"stage": stage}) != "The Client's Spelling":
            out.append(f"a Chaos the client names read "
                       f"{ce.chaos_name({'stage': stage})!r}, not the "
                       f"client's spelling: the client's names go over "
                       f"CHAOS_NAMES.")
        if ce.chaos_name({"stage": PROBE_STAGE}) != "Probe Chaos":
            out.append("a Chaos only the client names read as "
                       f"{ce.chaos_name({'stage': PROBE_STAGE})!r}, not its "
                       f"client name.")
        if ce.chaos_name({"stage": TABLE_STAGE}) != "Table Chaos":
            out.append("a Chaos only CHAOS_NAMES names read as "
                       f"{ce.chaos_name({'stage': TABLE_STAGE})!r}, not its "
                       f"table name.")
        if ce.zero_special_name(special) != "Client Name":
            out.append("a Zero System special the client names took "
                       "ZERO_SPECIALS' name: the client's goes over it.")
        if ce.zero_special_name(PROBE_SPECIAL) != "Probe Special":
            out.append("a Zero System special only the client names read as "
                       "its id.")
        if ce.zero_special_name(TABLE_SPECIAL) != "Table Special":
            out.append("a Zero System special only ZERO_SPECIALS names read "
                       "as its id.")
        gh._general_units = None
        if gh.pool_of("gacha_pickup_combatant_77002_1") != "pickup_combatant":
            out.append("with no rates reply, a rerun of a unit the client's "
                       "Normal Rescue pools lack was not taken as Seasonal: "
                       "its pulls land on the rerun counter's pity.")
        if gh.pool_of("gacha_pickup_combatant_77001_1") != \
                "pickup_combatant_rerun":
            out.append("with no rates reply, a rerun of a unit the client's "
                       "Normal Rescue pools hold was not taken as a rerun.")
        gh._general_units = {77002}
        if gh.pool_of("gacha_pickup_combatant_77002_1") != \
                "pickup_combatant_rerun":
            out.append("a captured rates reply did not go over the client's "
                       "pools: the server's own list must win.")
        from game_data import from_client
        game_client.use(dict(facts, exploration_passives={
            str(PROBE_PARTNER): [{"name": "Probe", "assigned": True,
                                  "steps": [[0, "a"], [2, "b"]]}]},
            card_skins={"skins": {str(PROBE_SKIN): ["Probe Skin", "RARE",
                                                    1003]},
                        "packs": {"probe_pack": ["Probe Pack",
                                                 {"RARE": 0.5}, 1003]}},
            season_nodes={PROBE_SEASON: [4, 9]}))
        held = game_client.known_exploration_passives()
        kept = set(from_client.EXPLORATION_PASSIVES) <= set(held)
        from game_data.partners import get_partner_exploration
        steps = [get_partner_exploration(PROBE_PARTNER, lb) for lb in (1, 2)]
        if steps != [[("Probe", "a")], [("Probe", "b")]]:
            out.append(f"a passive rising at limit break 2 reads {steps} at "
                       f"limit breaks 1 and 2: each the words of the last "
                       f"step it rose at by then (`get_partner_exploration`).")
        if held.get(PROBE_PARTNER) != (("Probe", True, ((0, "a"), (2, "b"))),) \
                or not kept:
            out.append(f"the Exploration Passives read "
                       f"{held.get(PROBE_PARTNER)!r} for a partner only this "
                       f"client holds, the shipped ones "
                       f"{'kept' if kept else 'dropped'}: the client's read "
                       f"goes over the shipped table.")
        skins, packs = game_client.known_card_skins()
        if skins.get(PROBE_SKIN) != ("Probe Skin", "RARE", 1003) \
                or packs.get("probe_pack") != ("Probe Pack", {"RARE": 0.5},
                                               1003) \
                or not set(from_client.CARD_SKINS) <= set(skins):
            out.append("the card skins read leave out this client's skin or "
                       "pack, or the shipped ones: the client's read goes "
                       "over the shipped tables.")
        trees = game_client.known_season_nodes()
        if trees.get(PROBE_SEASON) != (4, 9) or not set(
                getattr(from_client, "SEASON_NODES", {})) <= set(trees):
            out.append(f"the season trees read {trees!r}: this client's "
                       f"{PROBE_SEASON} over the shipped trees, which stand "
                       f"for the rest.")
    finally:
        ce.CHAOS_NAMES.pop(TABLE_STAGE, None)
        ce.ZERO_SPECIALS.pop(TABLE_SPECIAL, None)
        gh._general_units = held_general
        game_client.use(held_facts)
    return out


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("CHAOS_NAMES over the client's spelling",
     "chaos_estimate:chaos_names",
     "return {**CHAOS_NAMES, **game_client.known_chaos_names()}",
     "return {**game_client.known_chaos_names(), **CHAOS_NAMES}",
     "the client's names go over CHAOS_NAMES"),
    ("a Chaos only the table names left as its id",
     "chaos_estimate:chaos_names",
     "return {**CHAOS_NAMES, **game_client.known_chaos_names()}",
     "return dict(game_client.known_chaos_names())",
     "only CHAOS_NAMES names"),
    ("ZERO_SPECIALS over the client's name",
     "chaos_estimate:zero_special_name",
     "return (game_client.known_zero_specials().get(special)\n"
     "            or ZERO_SPECIALS.get(special) or special)",
     "return (ZERO_SPECIALS.get(special)\n"
     "            or game_client.known_zero_specials().get(special) "
     "or special)",
     "the client's goes over it"),
    ("a special only the client names left as its id",
     "chaos_estimate:zero_special_name",
     "return (game_client.known_zero_specials().get(special)\n"
     "            or ZERO_SPECIALS.get(special) or special)",
     "return ZERO_SPECIALS.get(special) or special",
     "only the client names read as its id"),
    ("no client pool for the Normal Rescues",
     "game_client:known_general_units",
     "return set(units) if units else None", "return None",
     "was not taken as Seasonal"),
    ("the client's Exploration Passives not read",
     "game_client:known_exploration_passives",
     "out[int(key)] = tuple(", "out[-1] = tuple(", "the Exploration Passives"),
    ("the shipped Card Skins dropped", "game_client:known_card_skins",
     'skins = dict(getattr(from_client, "CARD_SKINS", {}))', "skins = {}",
     "the card skins read"),
    ("this client's season tree not read", "game_client:known_season_nodes",
     "out[str(season)] = tuple(counts)", "pass", "the season trees read"),
    ("a passive's step taken a limit break late",
     "game_data.partners:get_partner_exploration",
     "if rise <= (limit_break or 0)", "if rise < (limit_break or 0)",
     "a passive rising at limit break 2"),
]
