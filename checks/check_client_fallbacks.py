"""What the game client fills where the program's own tables are silent.

Three readers ask the client for what their own table lacks, and each
must keep the order it was given: the program's own over the client's
where both hold a value, the client's over nothing.

1. **A Chaos's name** (`chaos_estimate.chaos_name`): `CHAOS_NAMES`'s
   spelling where it names the stage; the client's for one a patch
   added, which otherwise reads as its stage id.
2. **A Zero System special** (`chaos_estimate.zero_special_name`): the
   same order, then the id.
3. **Which 5-stars the Normal Rescues offer** (`gacha_history.pool_of`):
   a rates reply the account captured over the client's pools, and the
   client's over nothing. Without either, a Seasonal rerun counts on the
   rerun counter, its pulls on the wrong pity.

Held on synthetic client facts, put in place with `game_client.use` and
taken away after.
"""

from ._harness import add_source_to_path

NAME = "the game client fills what the program's tables lack, never more"


def run():
    add_source_to_path()
    import chaos_estimate as ce
    import gacha_history as gh
    import game_client

    out = []
    held_facts, held_general = game_client._facts, gh._general_units
    stage, (name, _season) = next(iter(ce.CHAOS_NAMES.items()))
    special = next(iter(ce.ZERO_SPECIALS))
    facts = {"format": game_client.CACHE_FORMAT,
             "chaos_names": {str(stage): ["The Client's Spelling", None],
                             "999999": ["Probe Chaos", "disaster_s99"]},
             "zero_specials": {special: "Client Name",
                               "zero_orb_special_probe": "Probe Special"},
             "general_units": [77001]}
    try:
        game_client.use(facts)
        if ce.chaos_name({"stage": stage}) != name:
            out.append("a Chaos CHAOS_NAMES names took the client's spelling: "
                       "the program's own names go over the client's.")
        if ce.chaos_name({"stage": 999999}) != "Probe Chaos":
            out.append("a Chaos only the client names read as "
                       f"{ce.chaos_name({'stage': 999999})!r}, not its "
                       f"client name.")
        if ce.zero_special_name(special) != ce.ZERO_SPECIALS[special]:
            out.append("a Zero System special ZERO_SPECIALS names took the "
                       "client's name.")
        if ce.zero_special_name("zero_orb_special_probe") != "Probe Special":
            out.append("a Zero System special only the client names read as "
                       "its id.")
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
    finally:
        gh._general_units = held_general
        game_client.use(held_facts)
    return out
