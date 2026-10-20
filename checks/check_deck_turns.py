"""What each card costs, draws and gives in AP per play, and which turns
it counts in, as `decks.turns` reads it off the client's effects.

The reading is the program's own: which effect is a draw, when a cost
cut is AP gained, what waits for the battle. A misread changes every
deck's draw and AP sums quietly. So each rule is held to a card built to
exercise it, on a catalogue of the check's own; and the cards whose
figures the maintainer's own spreadsheet gives (its Deck Calcs tab,
`_tmp/deck_calcs_review.py`) are read off the installed client and held
to those figures.
"""

from ._harness import add_source_to_path, note

NAME = "per-card cost, draw and AP gain"

# (card id, Signature Epiphany, cost, draw, AP gain): what the Deck Calcs
# tab gives for a card and the program reads off it as printed.
DECK_CALCS = [
    ("c_1003_uni3", 0, 0, 1, 0), ("c_1003_uni3", 1, 0, 2, 0),
    ("c_1005_srt4", 4, 0, 0, 0), ("c_1008_uni3", 0, 1, 1, 0),
    ("c_1012_srt4", 3, 3, 0, 0), ("c_1012_uni1", 0, 1, 0, 0),
    ("c_1012_uni4", 0, 2, 0, 0), ("c_1024_uni4", 0, 1, 0, 0),
    ("c_1028_srt1", 0, 1, 0, 0), ("c_1033_uni1", 1, 0, 2, 0),
    ("c_1049_uni1", 5, 0, 1, 0), ("c_1049_uni2", 0, 1, 0, 0),
    ("c_1049_uni2", 4, 0, 0, 0), ("c_1052_uni1", 2, 0, 0, 2),
    ("c_1055_uni2_mut1", 0, 0, 0, 0), ("c_1055_uni2_mut2", 0, 0, 0, 0),
    ("c_1055_uni3", 4, 0, 0, 0), ("c_1056_srt4", 0, 1, 0, 0),
    ("c_1056_uni4", 0, 1, 0, 0), ("c_1057_srt2", 0, 2, 0, 0),
    ("c_1057_uni4", 0, 1, 0, 0), ("c_1060_srt1", 0, 1, 0, 0),
    ("c_1060_uni4", 0, 1, 0, 0), ("c_1062_srt2", 0, 2, 0, 0),
    ("c_1062_uni1", 0, 0, 0, 0), ("c_1062_uni3", 3, 1, 0, 0),
    ("c_1062_uni4", 0, 0, 0, 0), ("c_1069_uni1", 2, 1, 0, 0),
    ("c_1069_uni1", 3, 2, 0, 0), ("c_1069_uni2", 3, 1, 2, 0),
    ("c_1069_uni4", 0, 1, 0, 0), ("c_30048_uni1", 1, 0, 3, 0),
    ("c_30048_uni2", 0, 0, 0, 0), ("c_30093_srt1", 0, 1, 0, 0),
    ("c_30093_srt4", 0, 1, 0, 0), ("c_30093_uni1", 0, 0, 3, 0),
    ("c_30093_uni2", 0, 1, 0, 0), ("c_30093_uni2", 3, 0, 0, 0),
    ("c_30093_uni3", 0, 0, 0, 0), ("c_30093_uni4", 0, 0, 0, 0),
    ("c_30097_srt4", 0, 1, 0, 0), ("c_30097_uni4", 0, 0, 0, 0),
    ("c_30113_srt4", 1, 1, 1, 0), ("c_30113_uni1", 0, 1, 0, 0),
    ("c_30113_uni1", 2, 1, 1, 0), ("c_30113_uni2", 0, 1, 2, 0),
    ("c_30113_uni4", 0, 1, 3, 0), ("c_30115_srt4", 4, 1, 2, 0),
    ("c_30115_uni1", 0, 0, 0, 0), ("c_30115_uni3", 2, 1, 1, 0),
    ("c_30117_uni1", 0, 1, 0, 0), ("c_30117_uni2", 1, 0, 0, 0),
    ("c_30117_uni4", 0, 1, 0, 0), ("card_arena_00005", 0, 0, 0, 0),
    ("card_arena_00006", 0, 0, 0, 0), ("card_ds04_des_30021", 0, 1, 0, 0),
    ("card_ds04_des_30031", 0, 1, 0, 0), ("card_ds04_des_40041", 0, 1, 0, 0),
    ("card_ne_00038", 0, 1, 1, 0), ("card_ne_00042", 0, 2, 1, 0),
]


def _card(category="CARD_SKILL", cost=1, effects=(), talents=(), name="Fixture"):
    return {"name": name, "sort": "SORT_UNIQUE", "category": category,
            "rarity": "", "cost": cost, "talents": list(talents), "classes": [],
            "replace_cost": [], "tags": [], "effects": list(effects)}


def _effect(eff, value=1, operation="OPERATION_ACTIVE", **columns):
    return {"eff": eff, "eff_value": str(value), "operation": operation,
            "eff_value_type_1": columns.pop("value_type", "VALUE_COMMON"),
            "eff_value_math_sign": columns.pop("sign", "MATHSIGN_NONE"),
            **columns}


def _condition(card_part):
    return [{"type": "stack", "and_or": "AND", "cards": [card_part], "units": [],
             "timings": [], "battle_timing": []}]


DRAW, ENERGY = "SKILL_EFF_CARD_DRAW", "SKILL_EFF_ENERGY_CHANGE"
STATUS, MOVE = "SKILL_EFF_CS_SET_ADD", "SKILL_EFF_CARD_MOVE_TO"
COST_CUT = "SKILL_EFF_CARD_COST_CHANGE"
LESS = "MATHSIGN_SUBTRACT_MIN_0"


def _catalogue():
    from decks.catalogue import Catalogue
    effects = {
        "draw1": _effect(DRAW), "ap1": _effect(ENERGY, sign="MATHSIGN_ADD"),
        "draw2": _effect(DRAW, 2),
        "pile": _effect(DRAW, eff_link_condition_id="cd_pile"),
        "battle": _effect(DRAW, eff_link_condition_id="cd_battle"),
        "trigger": _effect(DRAW, operation="OPERATION_TRIGGER"),
        "xdraw": _effect(DRAW, value_type="VALUE_BEFORE_EFF_TARGET_COUNT_ADD"),
        "move": _effect(MOVE, eff_card_place="CARD_PLACE_HAND",
                        target_card_set="CARD_SET_ALL",
                        target_card_set_list_card_place="CARD_PLACE_DECK"),
        "self_on": _effect(STATUS, operation="OPERATION_PASSIVE",
                           target_card_set="CARD_SET_THIS_CARD", link_cs_id="[st_self]"),
        "self_move": _effect(MOVE, operation="OPERATION_TRIGGER",
                             eff_card_place="CARD_PLACE_HAND",
                             target_card_set="CARD_SET_THIS_CARD"),
        "cut_put": _effect(STATUS, target_card_set="CARD_SET_ALL",
                           target_card_set_list_card_place="CARD_PLACE_HAND",
                           eff_card_target_count="2", link_cs_id="[st_cut]"),
        "cut": _effect(COST_CUT, operation="OPERATION_PASSIVE", sign=LESS,
                       target_card_set="CARD_SET_THIS_CARD"),
        "unit_put": _effect(STATUS, target_card_set="CARD_SET_NONE", link_cs_id="[st_unit]"),
        "unit_cut": _effect("SKILL_EFF_CARD_COST_CHANGE_PASSIVE", operation="OPERATION_PASSIVE",
                            sign=LESS, target_card_set="CARD_SET_ALL"),
        "uses_put": _effect(STATUS, 2, target_card_set="CARD_SET_NONE", link_cs_id="[st_uses]"),
        "own_on": _effect(STATUS, operation="OPERATION_PASSIVE",
                          target_card_set="CARD_SET_THIS_CARD", link_cs_id="[st_own]"),
        "own_cut": _effect(COST_CUT, operation="OPERATION_TRIGGER", sign=LESS,
                           target_card_set="CARD_SET_THIS_CARD"),
        "lasting_put": _effect(STATUS, target_card_set="CARD_SET_NONE",
                               link_cs_id="[st_lasting]"),
        "lasting_ap": _effect(ENERGY, operation="OPERATION_TRIGGER", sign="MATHSIGN_ADD"),
        "choose": _effect("SKILL_EFF_CARD_OPTION_SELECT",
                          eff_opt_multiple_link="[c_9_opt1,c_9_opt2]"),
    }
    statuses = {
        "st_self": {"link_skill_eff_id": "[self_move]", "term_type_1": "TERM_BATTLE"},
        "st_cut": {"link_skill_eff_id": "[cut]", "term_type_1": "TERM_TURN_VALUE"},
        "st_unit": {"link_skill_eff_id": "[unit_cut]", "term_type_1": "TERM_PASSIVE_WHOLE"},
        "st_uses": {"link_skill_eff_id": "[trigger]", "term_type_1": "TERM_EFF_WHOLE"},
        "st_own": {"link_skill_eff_id": "[own_cut]", "term_type_1": "TERM_BATTLE"},
        "st_lasting": {"link_skill_eff_id": "[lasting_ap]", "term_type_1": "TERM_BATTLE"},
    }
    conditions = {
        "cd_pile": _condition({"condition_card": "CONDITION_CARD_AMOUNT",
                               "condition_card_card_place": "CARD_PLACE_DECK_DISCARD",
                               "condition_card_value_ineq": "INEQUALITY_GE",
                               "condition_card_value": "1"}),
        "cd_battle": _condition({"condition_card": "CONDITION_CARD_USE",
                                 "condition_card_card_place": "CARD_PLACE_NONE",
                                 "condition_card_value_ineq": "INEQUALITY_GE",
                                 "condition_card_value": "1"}),
    }
    cards = {
        "c_9_plain": _card(effects=["draw1", "ap1"]),
        "c_9_pile": _card(effects=["pile"]),
        "c_9_battle": _card(effects=["battle"]),
        "c_9_trigger": _card(effects=["trigger"]),
        "c_9_xdraw": _card(effects=["xdraw"]),
        "c_9_x": _card(cost=-1),
        "c_9_upgrade": _card(category="CARD_POWER"),
        "c_9_exhaust": _card(talents=["TALENT_EXHAUST_2"]),
        "c_9_neither": _card(talents=["TALENT_UNPLAYABLE", "TALENT_ETHEREAL"]),
        "c_9_opener": _card(talents=["TALENT_OPENING"]),
        "c_9_quietus": _card(cost=2, talents=["TALENT_TESTAMENT"]),
        "c_9_ignite": _card(talents=["TALENT_IGNITE"]),
        "c_9_move": _card(effects=["move"]),
        "c_9_self": _card(effects=["self_on"]),
        "c_9_cut": _card(effects=["cut_put"]),
        "c_9_unitcut": _card(effects=["unit_put"]),
        "c_9_uses": _card(effects=["uses_put"]),
        "c_9_owncost": _card(cost=3, effects=["own_on"]),
        "c_9_lasting": _card(category="CARD_POWER", effects=["lasting_put"]),
        "c_9_choice": _card(effects=["choose"]),
        "c_9_opt1": _card(effects=["draw2"]), "c_9_opt2": _card(effects=["ap1"]),
        "c_9_base": _card(cost=2),
        "c_9_base_rsp1": _card(cost=0, effects=["draw1"]),
    }
    return Catalogue({
        "cards": cards, "effects": effects, "statuses": statuses,
        "conditions": conditions,
        "versions": {"c_9_base": {"1": "c_9_base_rsp1"}},
        "epiphanies": {
            "n_draw": {"god": None, "effects": ["draw1"], "talents": [],
                       "add_cost": 0, "add_cost_sign": "MATHSIGN_NONE"},
            "n_exhaust": {"god": None, "effects": [], "talents": ["TALENT_EXHAUST"],
                          "add_cost": 0, "add_cost_sign": "MATHSIGN_NONE"},
            "d_cheaper": {"god": "vitor", "effects": [], "talents": [],
                          "add_cost": 1, "add_cost_sign": LESS},
        },
        "persona": {"effects": {"p_dearer": {"effects": ["ap1"],
                                             "add_talents": ["TALENT_RETAIN"],
                                             "add_cost": 1,
                                             "add_cost_sign": "MATHSIGN_ADD"}}},
    })


# (what, card, DeckCard fields, (cost, draw, AP gain), (cost, draw,
# AP gain) once every conditional part counts, turns, a piece of a note
# that must be there or "")
CASES = [
    ("a plain draw and AP gain", "c_9_plain", {}, (1, 1, 1), (1, 1, 1), "regular", ""),
    ("a draw needing a card in the pile", "c_9_pile", {}, (1, 1, 0), (1, 1, 0), "regular", ""),
    ("a draw the battle's condition gates", "c_9_battle", {}, (1, 0, 0), (1, 1, 0),
     "regular", ""),
    ("a triggered draw", "c_9_trigger", {}, (1, 0, 0), (1, 1, 0), "regular", ""),
    ("a draw by a count the battle makes", "c_9_xdraw", {}, (1, 0, 0), (1, 0, 0),
     "regular", ""),
    ("an X card", "c_9_x", {}, (0, 0, 0), (0, 0, 0), "regular", ""),
    ("an Upgrade", "c_9_upgrade", {}, (1, 0, 0), (1, 0, 0), "setup", ""),
    ("an Exhaust 2 card", "c_9_exhaust", {}, (1, 0, 0), (1, 0, 0), "setup", ""),
    ("an Unusable Ephemeral card", "c_9_neither", {}, (1, 0, 0), (1, 0, 0), "neither", ""),
    ("a Quietus card", "c_9_quietus", {}, (0, 0, 0), (0, 0, 0), "regular", "Quietus"),
    ("an Ignition card", "c_9_ignite", {}, (1, 0, 0), (0, 0, 0), "regular", ""),
    ("a card taken from the draw pile to hand", "c_9_move", {}, (1, 1, 0), (1, 1, 0),
     "regular", ""),
    ("a card that moves itself to hand", "c_9_self", {}, (1, 0, 0), (1, 1, 0), "regular", ""),
    ("a cost cut on two cards in hand", "c_9_cut", {}, (1, 0, 2), (1, 0, 2), "regular", ""),
    ("a cost cut on the unit's next card", "c_9_unitcut", {}, (1, 0, 1), (1, 0, 1),
     "regular", ""),
    ("a triggered draw on a two-use status", "c_9_uses", {}, (1, 0, 0), (1, 2, 0),
     "regular", ""),
    ("a cost the battle lowers", "c_9_owncost", {}, (3, 0, 0), (2, 0, 0), "regular", ""),
    ("an Upgrade's lasting AP gain", "c_9_lasting", {}, (1, 0, 0), (1, 0, 1), "setup", ""),
    ("a choice", "c_9_choice", {}, (1, 2, 0), (1, 2, 0), "regular", "first option"),
    ("a Signature Epiphany version", "c_9_base", {"version": 1}, (0, 1, 0), (0, 1, 0),
     "regular", ""),
    ("a Neutral Epiphany's draw", "c_9_base", {"neutral": "n_draw"}, (2, 1, 0), (2, 1, 0),
     "regular", ""),
    ("a Neutral Epiphany's Exhaust", "c_9_base", {"neutral": "n_exhaust"}, (2, 0, 0),
     (2, 0, 0), "setup", ""),
    ("a Divine Epiphany's cost cut", "c_9_base", {"divine": "d_cheaper"}, (1, 0, 0),
     (1, 0, 0), "regular", ""),
    ("a Persona effect's cost and AP", "c_9_base", {"persona": ("p_dearer",)}, (3, 0, 1),
     (3, 0, 1), "regular", ""),
]


def _figures(played):
    return ((played.cost.value, played.draw.value, played.ap.value),
            (played.cost.at_most(), played.draw.at_most(), played.ap.at_most()))


def _rules_report():
    """Each reading rule on the card built for it."""
    from decks import turns
    from decks.model import DeckCard
    catalogue = _catalogue()
    out = []
    for what, card, fields, plain, most, turns_in, noted in CASES:
        played = turns.played(DeckCard(card, **fields), catalogue)
        got, got_most = _figures(played)
        if got != plain:
            out.append(f"{what}: reads as cost, draw, AP gain {got}, not {plain}. "
                       f"See `played` and `_Reader` in decks/turns.py.")
        if got_most != most:
            out.append(f"{what}: with its conditional parts, {got_most}, not {most}: "
                       f"what the battle decides is misread.")
        if played.turns != turns_in:
            out.append(f"{what}: counts in {played.turns} turns, not {turns_in}.")
        if noted and not any(noted in n for n in played.notes):
            out.append(f"{what}: no note says {noted!r}; the user would not know "
                       f"what was assumed.")
    x_card = turns.played(DeckCard("c_9_x"), catalogue)
    if not x_card.cost.unknown or x_card.cost.at_most() != 0:
        out.append("an X card's cost is not shown as the battle's to decide.")
    if not turns.played(DeckCard("c_9_opener"), catalogue).opener:
        out.append("an Opener card is not marked as one: its cost would not "
                   "come out of the setup turn (plan D18).")
    if turns.played(DeckCard("c_9_quietus"), catalogue).printed_cost != 2:
        out.append("a Quietus card's printed cost is lost, so the user cannot "
                   "go back to it.")
    if str(turns.played(DeckCard("c_9_battle"), catalogue).draw) != "?":
        out.append("a draw the battle decides does not show as ?.")
    return out


def _deck_calcs_report():
    """The cards the maintainer's Deck Calcs prices, read off the
    installed client."""
    import game_client
    from decks import catalogue, turns
    from decks.model import DeckCard
    install = game_client.find_install()
    if install is None:
        note("no game client installed, so no card was held to the Deck Calcs figures")
        return []
    cat = catalogue.Catalogue(catalogue.read(game_client.Client(install)))
    out = []
    for card, version, *want in DECK_CALCS:
        played = turns.played(DeckCard(card, version=version), cat)
        if played is None:
            out.append(f"{card} is gone from the client's tables.")
            continue
        got = [played.cost.value, played.draw.value, played.ap.value]
        if got != want:
            out.append(f"{played.name} ({card}, Epiphany {version}) reads as cost, "
                       f"draw, AP gain {got}; the maintainer's Deck Calcs gives {want}. "
                       f"Either decks/turns.py misreads its effects, or a patch changed "
                       f"the card: its text says which.")
    return out


def run():
    add_source_to_path()
    return _rules_report() + _deck_calcs_report()


FAULTS = [
    ("a pile condition read as the battle's", "decks.turns:available",
     'or part.get("condition_card_card_place") not in PILES', "or True",
     "a draw needing a card in the pile"),
    ("a trigger read as plain", "decks.turns:_Reader.walk",
     'if effect.get("operation") not in STEADY:', "if False:", "a triggered draw"),
    ("a battle condition read as plain", "decks.turns:available",
     "if not controls:", "if True:\n        return True\n    if not controls:",
     "a draw the battle's condition gates"),
    ("a count the battle makes read as plain", "decks.turns:_Reader.read",
     'plain_value = effect.get("eff_value_type_1", PLAIN) == PLAIN',
     "plain_value = True", "a draw by a count the battle makes"),
    ("an Exhaust 2 card read as regular", "decks.turns:_keyword",
     'return any(t == family or t.startswith(family + "_") for t in talents)',
     "return family in talents", "an Exhaust 2 card"),
    ("Quietus cards priced as printed", "decks.turns:played",
     "if QUIETUS in talents and priced:", "if False:", "a Quietus card"),
    ("a card from the draw pile not a draw", "decks.turns:_Reader.read",
     'elif effect.get("target_card_set_list_card_place") in DRAW_PILES:', "elif False:",
     "a card taken from the draw pile to hand"),
    ("a card that moves itself to hand not a draw", "decks.turns:_Reader.read",
     'self.draw.add(1, plain, f"1 draw: it moves to hand {reason}".rstrip())', "pass",
     "a card that moves itself to hand"),
    ("other cards' cost cut not counted per card", "decks.turns:_holder",
     'return OTHERS, max(1, _number(effect.get("eff_card_target_count"), 1))',
     "return OTHERS, 1", "a cost cut on two cards in hand"),
    ("a unit's cost cut not AP", "decks.turns:_Reader.read",
     "elif kind in COST_CHANGE and not on_this:", "elif False:",
     "a cost cut on the unit's next card"),
    ("a status's uses ignored", "decks.turns:_uses",
     'if (status.get("term_type_1") or "").startswith(USES_TERMS):', "if False:",
     "a triggered draw on a two-use status"),
    ("a choice's option not read", "decks.turns:_Reader.read",
     'self.walk(option["effects"], holder, count, steady, why)', "pass", "a choice"),
    ("an Epiphany's added effects ignored", "decks.turns:played",
     'effects += epiphany["effects"]', "pass", "a Neutral Epiphany's draw"),
    ("a Divine Epiphany's cost cut ignored", "decks.turns:_cost_change",
     "if not amount or sign in (\"\", \"MATHSIGN_NONE\"):", "if True:",
     "a Divine Epiphany's cost cut"),
    ("a Persona effect ignored", "decks.turns:played",
     'effects += effect["effects"]', "pass", "a Persona effect's cost and AP"),
]
