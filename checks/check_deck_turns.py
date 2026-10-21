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


def _make(cards, count=1, place="CARD_PLACE_HAND", operation="OPERATION_ACTIVE", **columns):
    return _effect("SKILL_EFF_CARD_GET", count, operation=operation,
                   target_card_set="CARD_SET_DESIGNED", eff_card_place=place,
                   target_card_set_opt_multiple_link=cards, **columns)


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
        "make_temp_hand": _make("[c_9_temp]", 2),
        "make_temp_deck": _make("[c_9_temp]", place="CARD_PLACE_DECK"),
        "make_stay": _make("[c_9_stay]"),
        "make_idle": _make("[c_9_idle]"),
        "make_pick": _make("[c_9_temp,c_9_stay]", eff_card_target_count="1"),
        "make_grave": _make("[c_9_grave]"),
        "add_exhaust": _effect("SKILL_EFF_CARD_TALENT_ADD", target_card_set="CARD_SET_BEFORE_EFF_TARGET",
                               eff_opt="[TALENT_EXHAUST]"),
        "lasting_make_put": _effect(STATUS, target_card_set="CARD_SET_NONE",
                                    link_cs_id="[st_lasting_make]"),
        # On no trigger: only the status lasting the battle makes it a
        # card made every time.
        "lasting_make": _make("[c_9_temp]"),
        "grave_on": _effect(STATUS, operation="OPERATION_PASSIVE",
                            target_card_set="CARD_SET_THIS_CARD", link_cs_id="[st_grave]"),
        "not_shuffle": _effect("SKILL_EFF_CARD_NOT_SHUFFLE", operation="OPERATION_PASSIVE"),
        "make_arrow": _make("[c_30113_cre1]", place="CARD_PLACE_DECK"),
        "make_flash": _make("[c_30047_srt4_rsp3_mut]"),
    }
    statuses = {
        "st_self": {"link_skill_eff_id": "[self_move]", "term_type_1": "TERM_BATTLE"},
        "st_cut": {"link_skill_eff_id": "[cut]", "term_type_1": "TERM_TURN_VALUE"},
        "st_unit": {"link_skill_eff_id": "[unit_cut]", "term_type_1": "TERM_PASSIVE_WHOLE"},
        "st_uses": {"link_skill_eff_id": "[trigger]", "term_type_1": "TERM_EFF_WHOLE"},
        "st_own": {"link_skill_eff_id": "[own_cut]", "term_type_1": "TERM_BATTLE"},
        "st_lasting": {"link_skill_eff_id": "[lasting_ap]", "term_type_1": "TERM_BATTLE"},
        "st_lasting_make": {"link_skill_eff_id": "[lasting_make]", "term_type_1": "TERM_BATTLE"},
        "st_grave": {"link_skill_eff_id": "[not_shuffle]", "term_type_1": "TERM_BATTLE"},
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
        # What makers make: a card that leaves after use, one that stays,
        # one that changes nothing, one that stays in the Graveyard, and
        # two the maintainer's exceptions name.
        "c_9_temp": _card(effects=["draw1"], talents=["TALENT_EXHAUST"], name="Temp"),
        "c_9_stay": _card(name="Stay"),
        "c_9_idle": _card(cost=0, talents=["TALENT_EXHAUST"], name="Idle"),
        "c_9_grave": _card(effects=["grave_on"], name="Grave"),
        "c_30113_cre1": _card(cost=0, talents=["TALENT_UNPLAYABLE", "TALENT_EXHAUST"],
                              effects=["draw1"], name="Homing Arrow"),
        "c_30047_srt4_rsp3_mut": _card(cost=3, talents=["TALENT_EXHAUST"], name="Hew"),
        "c_9_maker_hand": _card(effects=["make_temp_hand"]),
        "c_9_maker_deck": _card(effects=["make_temp_deck"]),
        "c_9_upgrade_hand": _card(category="CARD_POWER", effects=["make_temp_hand"]),
        "c_9_upgrade_deck": _card(category="CARD_POWER", effects=["make_temp_deck"]),
        "c_9_maker_stay": _card(effects=["make_stay"]),
        "c_9_upgrade_stay": _card(category="CARD_POWER", effects=["make_stay"]),
        "c_9_maker_idle": _card(effects=["make_idle"]),
        "c_9_maker_pick": _card(effects=["make_pick"]),
        "c_9_maker_adds": _card(effects=["make_stay", "add_exhaust"]),
        "c_9_maker_grave": _card(effects=["make_grave"]),
        "c_9_lasting_maker": _card(category="CARD_POWER", effects=["lasting_make_put"]),
        "c_9_arrow_maker": _card(effects=["make_arrow"]),
        "c_9_flash_maker": _card(effects=["make_flash"]),
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
    mine = turns.played(DeckCard("c_9_battle", overrides={"draw": 2}), catalogue)
    if (mine.draw.value, mine.draw.unknown) != (2, []):
        out.append("the user's own figure for a draw the battle decides is not "
                   "what the card counts (plan D12). See `played` in decks/turns.py.")
    moved = turns.played(DeckCard("c_9_plain", overrides={"turns": "setup"}), catalogue)
    if moved.turns != "setup":
        out.append("the user's move of a card to the setup list is lost (plan 3.2).")
    return out


def _totals_report():
    """A deck's lists and nets, and the team's surplus off the turn's
    own draw and AP, which the catalogue holds."""
    from decks import turns
    from decks.model import Adjustment, Deck, DeckCard, Team
    catalogue = _catalogue()
    # A turn that is not the game's 5 and 3, so a figure typed in where
    # the catalogue's belongs shows.
    catalogue.constants = {"draw": 6, "energy": 4}
    deck = Deck(combatant=9, cards=[DeckCard("c_9_plain"), DeckCard("c_9_plain"),
                                    DeckCard("c_9_base"), DeckCard("c_9_upgrade"),
                                    DeckCard("c_9_gone", removed=True)])
    held = turns.deck_turns(deck, catalogue)
    out = []
    regular = (held.regular.cards, held.regular.cost, held.regular.draw, held.regular.ap)
    if regular != (3, 4, 2, 2):
        out.append(f"a deck's regular list sums to cards, cost, draw, AP gain {regular}, "
                   f"not (3, 4, 2, 2). See `deck_turns` in decks/turns.py.")
    if (held.setup.cards, held.setup.cost) != (1, 1):
        out.append(f"a deck's setup list holds {held.setup.cards} cards costing "
                   f"{held.setup.cost}, not one costing 1.")
    if (held.net_draw, held.net_ap) != (-1, -2):
        out.append(f"a deck's nets are draw {held.net_draw}, AP {held.net_ap}, not -1 "
                   f"and -2: its draw less its cards, its AP gain less its cost (plan D71).")
    deck.adjustments = [Adjustment(draw=1, ap=3, note="Equipment")]
    held = turns.deck_turns(deck, catalogue)
    if (held.net_draw, held.net_ap) != (0, 1):
        out.append("the user's corrections to a deck's draw and AP are not in its "
                   "nets (plan D22).")
    team = turns.team_turns(Team(decks=[deck, Deck(combatant=9, cards=[
        DeckCard("c_9_base")])]), catalogue)
    want = (6 + 0 - 1, 4 + 1 - 2)
    if (team.draw_surplus, team.ap_surplus) != want:
        out.append(f"the team's surplus is draw {team.draw_surplus}, AP "
                   f"{team.ap_surplus}, not {want}: the catalogue's own turn draw "
                   f"and AP plus every deck's nets (plan 3.1, D71). See `team_turns` "
                   f"in decks/turns.py.")
    return out


# (what, the maker, the card made, its list, needs a draw, copies a
# turn, the deck grows, changes nothing, hidden, gone, a piece of a note
# or "")
CREATED = [
    ("a card made into hand, leaving after use, on every play", "c_9_maker_hand",
     "c_9_temp", "regular", False, 2, False, False, False, True, ""),
    ("a card made into the deck, leaving after use, on every play", "c_9_maker_deck",
     "c_9_temp", "regular", True, 1, False, False, False, True, ""),
    ("an Upgrade's card made into hand once", "c_9_upgrade_hand",
     "c_9_temp", "setup", False, 2, False, False, False, True, ""),
    ("an Upgrade's card made into the deck once", "c_9_upgrade_deck",
     "c_9_temp", "setup", True, 1, False, False, False, True, ""),
    ("a card that stays, made on every play", "c_9_maker_stay",
     "c_9_stay", "regular", True, 1, True, False, False, False, ""),
    ("a card that stays, made once", "c_9_upgrade_stay",
     "c_9_stay", "regular", True, 1, False, False, False, False, ""),
    ("a made card that changes nothing", "c_9_maker_idle",
     "c_9_idle", "regular", False, 1, False, True, False, True, ""),
    ("one of two cards made", "c_9_maker_pick",
     "c_9_temp", "regular", False, 1, False, False, False, True, "one of 2"),
    ("a card its maker gives Exhaust", "c_9_maker_adds",
     "c_9_stay", "regular", False, 1, False, False, False, True, ""),
    ("a made card that stays in the Graveyard", "c_9_maker_grave",
     "c_9_grave", "regular", False, 1, False, False, False, True, ""),
    ("an Upgrade's lasting status making a card each time", "c_9_lasting_maker",
     "c_9_temp", "regular", False, 1, False, False, False, True, ""),
    ("an exception the maintainer ignores", "c_9_arrow_maker",
     "c_30113_cre1", "regular", True, 1, False, False, True, True, "draws a card"),
]


def _created_report():
    """Each cell of plan D14's table, and what moves a card between
    them, on a maker built for it; a deck's lists with them."""
    from decks import created, turns
    from decks.model import Deck, DeckCard
    catalogue = _catalogue()
    out = []
    for what, maker, card, listed, draw, copies, grows, idle, hidden, gone, noted in CREATED:
        held = DeckCard(maker)
        made = created.created_cards(held, turns.played(held, catalogue), catalogue)
        found = [m for m in made if m.card == card]
        if not found:
            out.append(f"{what}: {maker} makes {[m.card for m in made]}, not {card}. See "
                       f"`creations` in decks/created.py.")
            continue
        m = found[0]
        got = (m.turns, m.needs_draw, m.copies, m.grows, m.idle, m.hidden, m.gone)
        want = (listed, draw, copies, grows, idle, hidden, gone)
        if got != want:
            names = ("list", "needs a draw", "copies", "grows", "changes nothing",
                     "hidden", "gone")
            wrong = [f"{n} {g!r} not {w!r}" for n, g, w in zip(names, got, want) if g != w]
            out.append(f"{what}: {'; '.join(wrong)}. See `created_cards` in "
                       f"decks/created.py and plan.md D14.")
        if noted and not any(noted in n for n in m.notes):
            out.append(f"{what}: no note says {noted!r}.")
    flash = created.created_cards(DeckCard("c_9_flash_maker"),
                                  turns.played(DeckCard("c_9_flash_maker"), catalogue),
                                  catalogue)
    if not flash or flash[0].played.cost.value != 0:
        out.append("an exception's practical cost (Hew (Flash), 0) is not what the "
                   "made card costs. See decks/exceptions.py.")
    held = turns.deck_turns(Deck(combatant=9, cards=[DeckCard("c_9_maker_hand")]), catalogue)
    sums = (held.regular.cards, held.regular.cost, held.regular.draw)
    if sums != (1, 3, 2):
        out.append(f"a deck whose card makes two cards into hand sums to cards, cost, "
                   f"draw {sums}, not (1, 3, 2): each made card counts, and needs no "
                   f"draw (plan D15). See `deck_turns` in decks/turns.py.")
    held = turns.deck_turns(Deck(combatant=9, cards=[DeckCard("c_9_maker_idle"),
                                                     DeckCard("c_9_arrow_maker")]), catalogue)
    if (held.regular.cards, held.regular.cost) != (2, 2):
        out.append("a made card that changes nothing, or one an exception hides, is "
                   "counted in a list (plan D43, D45).")
    return out


def _card_like(name, cost=0, draw=0, ap=0, opener=False):
    from decks import turns
    return turns.Played(card=name, name=name, cost=turns.Figure(cost),
                        draw=turns.Figure(draw), ap=turns.Figure(ap), talents=(),
                        turns="setup", opener=opener)


def _setup_cases():
    up = _card_like
    trade = up("trade: 1 AP for 2 more cards", cost=1, draw=3)
    return [
        ("setup that fits in turn 1, the cheaper card first",
         [up("u2", 2), up("u1", 1)], [], [], [["u1", "u2"]], (3, 0), []),
        ("setup a free AP gain pays for",
         [up("u2a", 2), up("u2b", 2)], [up("source", 0, 1, 2)], [],
         [["u2a", "u2b"]], (3, 1), []),
        ("six setup cards a trade card makes room for",
         [up(f"z{i}") for i in range(6)], [trade], [],
         [[f"z{i}" for i in range(6)]], (1, 2), []),
        ("setup over two turns", [up("u3a", 3), up("u3b", 3)], [], [],
         [["u3a"], ["u3b"]], (4, 0), []),
        ("a setup card no turn can afford", [up("u9", 9)], [], [], [], None, ["u9"]),
        ("an Opener setup card", [up("op", 1, opener=True), up("u2", 2)], [], [],
         [["op", "u2"]], (4, 0), []),
        ("trade cards played for what they leave over",
         [up("u1", 1)], [trade, up("ap", 0, 0, 2)], [],
         [["u1"]], (5, 3), []),
    ]


def _setup_report():
    """The setup plan (plan D72), on cards built for each step."""
    from decks import turns
    out = []
    for what, setup, regular, openers, played, left, stuck in _setup_cases():
        plan = turns.plan_setup(setup, regular, draw=5, energy=3, openers=openers)
        got = [[card.name for card in turn.setup] for turn in plan.turns]
        if got != played:
            out.append(f"{what}: the setup turns play {got}, not {played}. See "
                       f"`plan_setup` in decks/turns.py and plan.md D72.")
        if left is not None and plan.turns and \
                (plan.turns[0].draw_left, plan.turns[0].ap_left) != left:
            out.append(f"{what}: turn 1 leaves draw {plan.turns[0].draw_left}, AP "
                       f"{plan.turns[0].ap_left}, not {left[0]} and {left[1]}.")
        if [card.name for card in plan.stuck] != stuck:
            out.append(f"{what}: the cards no turn can afford are "
                       f"{[card.name for card in plan.stuck]}, not {stuck}.")
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
    return (_rules_report() + _totals_report() + _setup_report() + _created_report()
            + _deck_calcs_report())


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
    ("the user's figure ignored", "decks.turns:played",
     "if key in held.overrides:", "if False:", "the user's own figure"),
    ("a card left out of its list's count", "decks.turns:Sums.add",
     "self.cards += 1 if played.needs_draw else 0", "pass",
     "a deck's regular list sums"),
    ("a deck's corrections left out", "decks.turns:deck_turns",
     "out.draw_adjustment += adjustment.draw", "pass", "the user's corrections"),
    ("the turn's draw typed in", "decks.turns:team_turns",
     'draw = catalogue.constants.get("draw", 5)', "draw = 5",
     "the catalogue's own turn draw"),
    ("free gains not played in setup", "decks.turns:plan_setup",
     "if min(nets(card)) >= 0 and max(nets(card)) > 0]", "if False]",
     "a free AP gain pays for"),
    ("trade cards not tried", "decks.turns:plan_setup",
     "for mask in range(1 << len(trades)):", "for mask in range(1):",
     "a trade card makes room for"),
    ("an Opener setup card waiting for a hand", "decks.turns:plan_setup",
     "at_start = [card for card in setup if card.opener]", "at_start = []",
     "an Opener setup card"),
    ("an unaffordable setup card not reported", "decks.turns:plan_setup",
     "plan.stuck = waiting", "plan.stuck = []", "no turn can afford"),
    ("leftovers not the tie-break", "decks.turns:plan_setup",
     "score = (len(played_setup), h + a)", "score = (len(played_setup), 0)",
     "trade cards played for what they leave over"),
    ("setup cards not the cheapest first", "decks.turns:plan_setup",
     "key=lambda c: -sum(nets(c)))", "key=lambda c: sum(nets(c)))",
     "the cheaper card first"),
    ("a one-time maker's cards made every time", "decks.created:creations",
     "every_time=fires or via_lasting or not once_by_kind", "every_time=True",
     "an Upgrade's card made into hand once"),
    ("a card made into hand needing a draw", "decks.created:created_cards",
     "needs_draw = not (gone and creation.to_hand)", "needs_draw = True",
     "a card made into hand, leaving after use"),
    ("a maker's keywords ignored", "decks.created:created_cards",
     "talents = tuple(dict.fromkeys(made.talents + creation.talents))",
     "talents = made.talents", "a card its maker gives Exhaust"),
    ("the Graveyard's keeping ignored", "decks.created:_gone",
     'if effect.get("eff") == NOT_SHUFFLE:', "if False:", "stays in the Graveyard"),
    ("a lasting status's cards made once", "decks.created:creations",
     'lasting = status.get("term_type_1") in LASTING', "lasting = False",
     "an Upgrade's lasting status"),
    ("a made card that changes nothing counted", "decks.created:created_cards",
     "idle = (creation.to_hand and made.cost.value == 0",
     "idle = (False and made.cost.value == 0", "a made card that changes nothing"),
    ("the exceptions table ignored", "decks.created:created_cards",
     "exception = EXCEPTIONS.get(card_id, {})", "exception = {}",
     "an exception the maintainer ignores"),
    ("a made card's copies counted once", "decks.turns:deck_turns",
     "listed[made.turns].extend([copy] * made.copies)", "listed[made.turns].append(copy)",
     "a deck whose card makes two cards into hand"),
    ("a growing deck not flagged", "decks.created:created_cards",
     "grows=creation.every_time and not gone", "grows=False",
     "a card that stays, made on every play"),
    ("one of several not noted", "decks.created:created_cards",
     "if creation.pick or creation.pool:", "if False:", "one of two cards made"),
    ("an exception's practical cost ignored", "decks.created:created_cards",
     'if "cost" in exception:', "if False:", "an exception's practical cost"),
    ("hidden and idle made cards counted", "decks.turns:deck_turns",
     "if made.hidden or made.idle or made.turns not in listed:",
     "if made.turns not in listed:", "is counted in a list"),
]
