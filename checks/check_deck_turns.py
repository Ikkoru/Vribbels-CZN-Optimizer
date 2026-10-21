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
# tab gives for a card and the program reads off it, as printed or as
# decks/exceptions.py prices it.
DECK_CALCS = [
    ("c_1003_srt4", 0, 1, 1, 0),
    ("c_1003_uni3", 0, 0, 1, 0), ("c_1003_uni3", 1, 0, 2, 0),
    ("c_1003_uni4_lbk", 0, 0, 1, 0),
    ("c_1005_srt4", 4, 0, 0, 0), ("c_1008_uni3", 0, 1, 1, 0),
    ("c_1012_srt4", 3, 3, 0, 0), ("c_1012_uni1", 0, 1, 0, 0),
    ("c_1012_uni2", 2, 0, 2, 2),
    ("c_1012_uni4", 0, 2, 0, 0), ("c_1024_uni4", 0, 1, 0, 0),
    ("c_1028_srt1", 0, 1, 0, 0), ("c_1033_uni1", 1, 0, 2, 0),
    ("c_1049_uni1", 5, 0, 1, 0), ("c_1049_uni2", 0, 1, 0, 0),
    ("c_1049_uni2", 4, 0, 0, 0), ("c_1052_uni1", 2, 0, 0, 2),
    ("c_1052_uni4", 0, 0, 0, 0),
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


def _checked_at(battle_timing, first_turn=False):
    """A condition testing nothing, checked at `battle_timing`, and in
    turn 1 only where `first_turn`."""
    timings = ([{"condition_timing": "TIMING_TURN", "condition_timing_value": "1",
                 "condition_timing_value_ineq": "INEQUALITY_EQ"}] if first_turn else [])
    return [{"type": "stack", "and_or": "AND", "cards": [], "units": [],
             "timings": timings, "battle_timing": list(battle_timing)}]


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
        # From the Discard pile, as good as drawn; from any pile but the
        # Exhaust pile, the Used pile among them, mostly a card played
        # again.
        "move_discard": _effect(MOVE, eff_card_place="CARD_PLACE_HAND",
                                target_card_set="CARD_SET_ALL",
                                target_card_set_list_card_place="CARD_PLACE_DISCARD"),
        "move_used": _effect(MOVE, eff_card_place="CARD_PLACE_HAND",
                             target_card_set="CARD_SET_ALL",
                             target_card_set_list_card_place="CARD_PLACE_DECK_DISCARD_USED"),
        "free_used": _effect("SKILL_EFF_CARD_USE", target_card_set="CARD_SET_ALL",
                             target_card_set_list_card_place="CARD_PLACE_DISCARD_USED"),
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
        # When effects fire: at the next turn's start, each turn, at the
        # start of battle, by chance.
        "next_turn_put": _effect(STATUS, 2, target_card_set="CARD_SET_NONE",
                                 link_cs_id="[st_next_turn]"),
        "turn_draw": _effect(DRAW, operation="OPERATION_TRIGGER",
                             eff_link_condition_id="cd_turn"),
        "each_turn_put": _effect(STATUS, target_card_set="CARD_SET_NONE",
                                 link_cs_id="[st_each_turn]"),
        "turn_ap": _effect(ENERGY, operation="OPERATION_TRIGGER", sign="MATHSIGN_ADD",
                           eff_link_condition_id="cd_turn"),
        "start_draw": _effect(DRAW, operation="OPERATION_TRIGGER",
                              eff_link_condition_id="cd_start"),
        "start_ap": _effect(ENERGY, operation="OPERATION_TRIGGER", sign="MATHSIGN_ADD",
                            eff_link_condition_id="cd_start"),
        "battle_draw": _effect(DRAW, operation="OPERATION_TRIGGER",
                               eff_link_condition_id="cd_battle"),
        "chance": _effect(DRAW, run_pct="30"),
        "testament": _effect("SKILL_EFF_CARD_TESTAMENT", operation="OPERATION_PASSIVE"),
        "free_deck": _effect("SKILL_EFF_CARD_USE", target_card_set="CARD_SET_ALL",
                             target_card_set_list_card_place="CARD_PLACE_DECK"),
        "free_hand": _effect("SKILL_EFF_CARD_USE", target_card_set="CARD_SET_ALL",
                             target_card_set_list_card_place="CARD_PLACE_HAND"),
        # What statuses held for the battle make and give: a card at the
        # start of battle, one when the battle triggers it, 2 AP at each
        # turn's start.
        "start_make": _make("[c_9_temp]", operation="OPERATION_TRIGGER",
                            eff_link_condition_id="cd_battle_start"),
        "battle_make": _make("[c_9_temp]", operation="OPERATION_TRIGGER",
                             eff_link_condition_id="cd_battle"),
        "turn_ap2": _effect(ENERGY, 2, operation="OPERATION_TRIGGER", sign="MATHSIGN_ADD",
                            eff_link_condition_id="cd_turn"),
        "make_made": _make("[c_9_made]"),
        "make_dirge": _make("[c_1041_cre1]"),
        # Attunement: a status on the card itself, drawing 1 and giving 1
        # AP each time it is drawn; and the same status on other cards and
        # on the unit.
        "attune_put": _effect(STATUS, operation="OPERATION_PASSIVE",
                              target_card_set="CARD_SET_THIS_CARD", link_cs_id="[st_attuned]"),
        "attune_others": _effect(STATUS, target_card_set="CARD_SET_ALL",
                                 target_card_set_list_card_place="CARD_PLACE_HAND",
                                 link_cs_id="[st_attuned]"),
        "attune_unit": _effect(STATUS, target_card_set="CARD_SET_NONE",
                               link_cs_id="[st_attuned]"),
        "attune_draw": _effect(DRAW, operation="OPERATION_TRIGGER",
                               eff_link_condition_id="cd_attuned"),
        "attune_ap": _effect(ENERGY, operation="OPERATION_TRIGGER", sign="MATHSIGN_ADD",
                             eff_link_condition_id="cd_attuned"),
        "hit": _effect("SKILL_EFF_DMG", 100),
        # A discard whose follow-ups make a card, on the discard being
        # done, and draw, on the battle's condition.
        "discard_then": _effect("SKILL_EFF_CARD_DISCARD", target_card_set="CARD_SET_ALL",
                                target_card_set_list_card_place="CARD_PLACE_HAND",
                                during_eff_0_link_skill_eff_id="make_temp_hand",
                                during_eff_0_link_condition_id="cd_by_this",
                                during_eff_1_link_skill_eff_id="draw1",
                                during_eff_1_link_condition_id="cd_battle"),
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
        "st_next_turn": {"link_skill_eff_id": "[turn_draw]", "term_type_1": "TERM_EFF_WHOLE"},
        "st_each_turn": {"link_skill_eff_id": "[turn_ap]", "term_type_1": "TERM_BATTLE"},
        "st_eq_turn": {"link_skill_eff_id": "[turn_ap]", "term_type_1": "TERM_BATTLE"},
        "st_eq_start": {"link_skill_eff_id": "[start_draw,start_ap]",
                        "term_type_1": "TERM_BATTLE"},
        "st_eq_battle": {"link_skill_eff_id": "[battle_draw]", "term_type_1": "TERM_BATTLE"},
        # The pool's cap is not the game's 6, so a 6 typed in shows.
        "cs01_0878": {"overlay_value_max": "5", "term_type_1": "TERM_EFF_WHOLE_FINALLY"},
        # Ego Manifestation's battle statuses: 1 AP each turn at level 2,
        # a card made at the start of battle at 4, and at 6 2 AP each
        # turn in place of both.
        "st_lb2": {"link_skill_eff_id": "[turn_ap]", "term_type_1": "TERM_BATTLE"},
        "st_lb4": {"link_skill_eff_id": "[start_make]", "term_type_1": "TERM_BATTLE"},
        "st_lb6": {"link_skill_eff_id": "[turn_ap2]", "term_type_1": "TERM_BATTLE"},
        "st_eq_maker": {"link_skill_eff_id": "[battle_make]", "term_type_1": "TERM_BATTLE"},
        "st_attuned": {"link_skill_eff_id": "[attune_draw,attune_ap]", "term_type_1": "TERM_BATTLE"},
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
        # A turn's start: nothing to test, starting over after the draw.
        "cd_turn": [{"type": "reset", "and_or": "AND", "cards": [], "units": [],
                     "timings": [], "battle_timing": ["TIMING_DRAW_AFTER"]}],
        # The start of battle: turn 1, after the draw.
        "cd_start": [{"type": "stack", "and_or": "AND", "cards": [], "units": [],
                      "timings": [{"condition_timing": "TIMING_TURN",
                                   "condition_timing_value": "1",
                                   "condition_timing_value_ineq": "INEQUALITY_EQ"}],
                      "battle_timing": []},
                     {"type": "reset", "and_or": "AND", "cards": [], "units": [],
                      "timings": [], "battle_timing": ["TIMING_DRAW_AFTER"]}],
        # A stack control's battle timing is when it is checked: the
        # battle's start, a turn's start, a card's use; and a card's use
        # in turn 1, which the battle decides as well.
        "cd_battle_start": _checked_at(["TIMING_BATTLE_START"]),
        "cd_turn_begin": _checked_at(["TIMING_TURN_BEGIN"]),
        "cd_card_use": _checked_at(["TIMING_USE_CARD_FINISH"]),
        "cd_first_turn_use": _checked_at(["TIMING_USE_CARD_FINISH"], first_turn=True),
        # Attunement's: a card holding the status is drawn. And a
        # follow-up's: a card discarded through this effect.
        "cd_attuned": _condition({"condition_card": "CONDITION_CARD_DRAW",
                                  "condition_card_opt": "[card_with_this_cs]",
                                  "condition_card_card_place": "CARD_PLACE_NONE",
                                  "condition_card_value_ineq": "INEQUALITY_EQ",
                                  "condition_card_value": "1"}),
        "cd_by_this": _condition({"condition_card": "CONDITION_CARD_DISCARD",
                                  "condition_card_opt": "[by_this_card_eff]",
                                  "condition_card_card_place": "CARD_PLACE_NONE",
                                  "condition_card_value_ineq": "INEQUALITY_EQ",
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
        "c_9_move_discard": _card(effects=["move_discard"]),
        "c_9_move_used": _card(effects=["move_used"]),
        "c_9_free_used": _card(effects=["free_used"]),
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
        "c_9_next_turn": _card(cost=0, effects=["next_turn_put"]),
        "c_9_upgrade_each_turn": _card(category="CARD_POWER", effects=["each_turn_put"]),
        "c_9_regular_each_turn": _card(effects=["each_turn_put"]),
        "c_9_chance": _card(effects=["chance"]),
        "c_9_free_deck": _card(effects=["free_deck"]),
        "c_9_free_hand": _card(effects=["free_hand"]),
        "card_ds04_des_10012": _card(name="Desire"),
        # Rita's AP pool (plan D47), under her own ids, which the pool's
        # table names.
        "c_30097_srt4": _card(category="CARD_POWER", name="Chrono Archon"),
        "c_30097_srt1": _card(cost=3, category="CARD_ATK", name="Time Acceleration"),
        # A Combatant's progress (plan D8): a Basic card a Potential node
        # upgrades, a Signature card and the Ego skill Ego Manifestation
        # levels upgrade, and made cards the node upgrades, one an
        # exception names.
        "c_9_srt1": _card(cost=2, name="Basic"),
        "c_9_srt1_pot": _card(cost=1, effects=["draw1"], name="Basic"),
        "c_9_uni4": _card(cost=2, name="Signature"),
        "c_9_uni4_lbk": _card(cost=0, name="Signature"),
        "c_9_made": _card(name="Made"),
        "c_9_made_pot": _card(cost=0, effects=["ap1"], name="Made"),
        "c_9_made_maker": _card(effects=["make_made"]),
        "c_1041_cre1": _card(cost=2, talents=["TALENT_EXHAUST"], name="Dirge Bullet"),
        "c_1041_cre1_pot": _card(cost=2, talents=["TALENT_EXHAUST"], name="Dirge Bullet"),
        "c_9_dirge_maker": _card(effects=["make_dirge"]),
        # The Ego skills (plan D2, D40), each costing Ego Points: the
        # Combatant's draws 2 and makes two cards that leave after use
        # and one that stays, its upgrade draws 1, the partner's gives 1
        # AP.
        "c_9_eps": _card(category="CARD_ATK", cost=5, name="Ego",
                         effects=["draw2", "make_temp_hand", "make_stay"]),
        "c_9_eps_lbk": _card(category="CARD_ATK", cost=4, effects=["draw1"], name="Ego"),
        "p_7": _card(cost=3, effects=["ap1"], name="Partner Ego"),
        # Attunement: a card drawn for it and never played (an Exhaust
        # Skill, as Forbidden: Eternal Hunger is), one played as well, and
        # one putting it on other cards; Mealtime, which the exceptions
        # table prices at 0, and its Ego Manifestation version.
        "c_9_attuned": _card(cost=0, effects=["attune_put"], talents=["TALENT_EXHAUST"],
                             name="Attuned"),
        "c_9_attuned_attack": _card(category="CARD_ATK", effects=["hit", "attune_put"],
                                    name="Attuned Attack"),
        "c_9_attunes_others": _card(effects=["attune_others"], name="Attunes Others"),
        "c_9_attunes_unit": _card(effects=["attune_unit"], name="Attunes Unit"),
        "c_1052_uni4": _card(category="CARD_ATK", cost=6, name="Mealtime"),
        "c_1052_uni4_lbk": _card(category="CARD_ATK", cost=6, name="Mealtime"),
        # The discard's follow-ups, on a card played every turn and on one
        # played once.
        "c_9_discarder": _card(cost=0, effects=["discard_then"], name="Discarder"),
        "c_9_discarder_once": _card(cost=0, effects=["discard_then"],
                                    talents=["TALENT_EXHAUST"], name="Discarder Once"),
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
                                             "add_cost_sign": "MATHSIGN_ADD"},
                                # "When this card is Discarded, proc this
                                # card", which also adds 1 to the cost.
                                "p_discard": {"effects": ["testament"], "add_talents": [],
                                              "add_cost": 1,
                                              "add_cost_sign": "MATHSIGN_ADD"}}},
        "equipment": {
            "eq_9_turn": {"name": "Each Turn", "stars": {"1": {"statuses": ["st_eq_turn"]}}},
            # Its second star is the one that gives at the start of battle.
            "eq_9_start": {"name": "Start", "stars": {"1": {"statuses": []},
                                                      "2": {"statuses": ["st_eq_start"]}}},
            "eq_9_battle": {"name": "Battle", "stars": {"1": {"statuses": ["st_eq_battle"]}}},
            "eq_9_maker": {"name": "Maker", "stars": {"1": {"statuses": ["st_eq_maker"]}}},
        },
        "buffs": {"rr_9": {"type": "LUX", "statuses": ["st_eq_turn"]}},
        "mutations": {"mut_9": {"name": "Mutation", "statuses": ["st_eq_start"]}},
        "upgrades": {"c_9_srt1": {"pot": "c_9_srt1_pot"}, "c_9_made": {"pot": "c_9_made_pot"},
                     "c_1041_cre1": {"pot": "c_1041_cre1_pot"},
                     "c_9_uni4": {"lbk": "c_9_uni4_lbk"}, "c_9_eps": {"lbk": "c_9_eps_lbk"}},
        "combatants": {"9": {"class": "striker", "playable": True, "name": "Fixture",
                             "ego": "c_9_eps"}},
        "partners": {"7": {"name": "Partner", "card": "p_7", "class": "striker"}},
        # Potential 3.1 upgrades cards; Potential 7 gives 1 AP each turn.
        "potential": {"9": {
            "3_1": {"1": {"cards": ["c_9_srt1", "c_9_made", "c_1041_cre1"], "statuses": []}},
            "7_0": {"1": {"cards": [], "statuses": ["st_eq_turn"]}}}},
        # Level 4 names a card it makes, which has no upgrade.
        "manifestation": {"9": [
            {"level": 1, "type": "BREAK_TYPE_CARD_R_SPARK", "cards": ["c_9_uni4"],
             "statuses": []},
            {"level": 2, "type": "BREAK_TYPE_BATTLE_CS_ADD", "cards": [],
             "statuses": ["st_lb2"]},
            {"level": 3, "type": "BREAK_TYPE_CARD_R_SPARK", "cards": ["c_9_eps"],
             "statuses": []},
            {"level": 4, "type": "BREAK_TYPE_BATTLE_CS_ADD", "cards": ["c_9_temp"],
             "statuses": ["st_lb4"]},
            {"level": 6, "type": "BREAK_TYPE_BATTLE_CS_ADD_OVERWRITE", "cards": [],
             "statuses": ["st_lb6"]}]},
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
    ("a card moved to hand from the Discard pile", "c_9_move_discard", {}, (1, 1, 0),
     (1, 1, 0), "regular", ""),
    ("a card moved to hand from a pile the Used pile is among", "c_9_move_used", {},
     (1, 0, 0), (1, 1, 0), "regular", ""),
    ("a card played for free from the Graveyard", "c_9_free_used", {}, (1, 0, 0),
     (1, 1, 0), "regular", ""),
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
    ("a draw at the next turn's start, on a two-use status", "c_9_next_turn", {},
     (0, 2, 0), (0, 2, 0), "regular", ""),
    ("an Upgrade's AP each turn, apart from its play", "c_9_upgrade_each_turn", {},
     (1, 0, 0), (1, 0, 0), "setup", ""),
    ("a regular card's lasting AP each turn, which every play adds again",
     "c_9_regular_each_turn", {}, (1, 0, 0), (1, 0, 1), "regular", ""),
    ("a draw by chance", "c_9_chance", {}, (1, 0, 0), (1, 1, 0), "regular", ""),
    ("a card played for free from the draw pile", "c_9_free_deck", {}, (1, 1, 0),
     (1, 1, 0), "regular", ""),
    ("a card played for free from hand", "c_9_free_hand", {}, (1, 0, 0), (1, 0, 0),
     "regular", ""),
    ("a card a Persona effect makes procced by a discard", "c_9_base",
     {"persona": ("p_discard",)}, (0, 0, 0), (0, 0, 0), "regular", "it prints 3"),
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
    upgrade = turns.played(DeckCard("c_9_upgrade_each_turn"), catalogue)
    if (upgrade.turn_draw.value, upgrade.turn_ap.value) != (0, 1):
        out.append(f"an Upgrade's lasting AP each turn reads as draw "
                   f"{upgrade.turn_draw.value}, AP {upgrade.turn_ap.value} a turn, not "
                   f"0 and 1 (plan D42). See `fires` and `_Reader.sink` in decks/turns.py.")
    regular = turns.played(DeckCard("c_9_regular_each_turn"), catalogue)
    if regular.turn_ap.value:
        out.append("a regular card's lasting effect counts as a steady AP gain each "
                   "turn, though every play puts it on again.")
    for card in ("c_9_free_deck", "c_9_free_hand"):
        if str(turns.played(DeckCard(card), catalogue).ap) != "?":
            out.append(f"a free play's saved cost ({card}) does not show as ? AP: which "
                       f"card it plays is the battle's (plan D49).")
    return out


def _bonuses_report():
    """What Equipment at its star level, a Buff and the Mutation give,
    each turn and at the start of battle, into the deck's nets."""
    from decks import turns
    from decks.model import Deck, Equipment
    catalogue = _catalogue()
    deck = Deck(combatant=9, equipment=[
        Equipment("eq_9_turn", buffs=("rr_9",)), Equipment("eq_9_start", stars=2),
        Equipment("eq_9_battle")], mutation="mut_9")
    found = {b.source: (b.turn_draw, b.turn_ap, b.start_draw, b.start_ap, bool(b.unknown))
             for b in turns.bonuses(deck, catalogue)}
    want = {"eq_9_turn": (0, 1, 0, 0, False), "rr_9": (0, 1, 0, 0, False),
            "eq_9_start": (0, 0, 1, 1, False), "eq_9_battle": (0, 0, 0, 0, True),
            "mut_9": (0, 0, 1, 1, False)}
    out = []
    if found != want:
        out.append(f"the deck's Equipment, Buff and Mutation give "
                   f"{found}, not {want}: (draw, AP each turn, draw, AP at the start "
                   f"of battle, some part the battle's). See `bonuses` in "
                   f"decks/turns.py and plan.md D21.")
    first_star = turns.bonuses(Deck(combatant=9, equipment=[Equipment("eq_9_start")]),
                               catalogue)
    if first_star:
        out.append("an Equipment piece gives what another star level of it does.")
    held = turns.deck_turns(deck, catalogue)
    if held.turn_ap != 2:
        out.append(f"the deck's Equipment and Buff give {held.turn_ap} AP a turn in its "
                   f"nets, not 2.")
    return out


def _pool_report():
    """Rita's own AP pool (plan D47) and the Ravages a turn (plan D48)."""
    from decks import turns
    from decks.model import Deck, DeckCard, Team
    catalogue = _catalogue()
    out = []
    rita = [DeckCard("c_30097_srt4"), DeckCard("c_30097_srt1"), DeckCard("c_30097_srt1")]
    held = turns.deck_turns(Deck(combatant=30097, cards=rita), catalogue)
    if (held.pool, held.pool_saving, held.net_ap) != (5, 5, -1):
        out.append(f"Rita's deck has a pool of {held.pool} paying {held.pool_saving} AP, "
                   f"net AP {held.net_ap}, not 5, 5 and -1: the pool, capped by the "
                   f"client's status, pays for her own cards first. See `_pool_of` and "
                   f"`DeckTurns.pool_saving` in decks/turns.py.")
    mine = turns.deck_turns(Deck(combatant=30097, cards=rita, ap_pool=2), catalogue)
    if mine.pool_saving != 2:
        out.append("the user's own pool figure for Rita's deck is not the one counted.")
    if turns.deck_turns(Deck(combatant=30097, cards=rita[1:]), catalogue).pool:
        out.append("Rita's pool counts without Chrono Archon in the deck, which switches it on.")
    switch = _card_like("switch", 1)
    switch.pool_switch = 5
    own = _card_like("own", 3)
    own.pool_paid = True
    plan = turns.plan_setup([switch, own], [], draw=5, energy=3)
    got = [[card.name for card in turn.setup] for turn in plan.turns]
    if got != [["switch"], ["own"]] or plan.turns[-1].ap_left != 3:
        out.append(f"with Rita's pool switched on in turn 1, setup plays {got}, leaving "
                   f"{plan.turns[-1].ap_left if plan.turns else '-'} AP: her own 3-AP card "
                   f"should be paid from the pool in turn 2, leaving 3. See `plan_setup`.")
    team = turns.team_turns(Team(decks=[Deck(combatant=9, cards=[DeckCard("c_9_plain")])]),
                            catalogue, ravages=2)
    plain = turns.team_turns(Team(decks=[Deck(combatant=9, cards=[DeckCard("c_9_plain")])]),
                             catalogue)
    if team.ap_surplus - plain.ap_surplus != 2:
        out.append(f"two Ravages a turn add {team.ap_surplus - plain.ap_surplus} AP to the "
                   f"surplus, not 2 (plan D48). See `team_turns`.")
    desire = turns.team_turns(Team(decks=[
        Deck(combatant=9, cards=[DeckCard("card_ds04_des_10012", desire={48: 2, 50: 1})]),
        Deck(combatant=9, cards=[DeckCard("card_ds04_des_10012", desire={48: 3})])]),
        catalogue)
    if desire.desire != {"Inquiry": 5, "Claim": 1}:
        out.append(f"the team's Desire points sum to {desire.desire}, not Inquiry 5 and "
                   f"Claim 1 (plan D26). See `team_turns` in decks/turns.py.")
    if not any(note.startswith("Inquiry 5") for note in desire.notes):
        out.append("Inquiry at 5 points does not note its draw per debuff (plan D26).")
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


def _progress_report():
    """What a Combatant's Potential nodes and Ego Manifestation do to its
    deck (plan D8), from the deck's own state or the owned Combatant's,
    and when a stack control's battle timing fires."""
    from decks import turns
    from decks.model import CombatantState, Deck, DeckCard, Equipment
    catalogue = _catalogue()
    out = []
    cards = [DeckCard("c_9_srt1"), DeckCard("c_9_uni4")]
    upgraded = {"c_9_srt1_pot": 1, "c_9_uni4_lbk": 0}
    plain = {"c_9_srt1": 2, "c_9_uni4": 2}

    def costs(deck, owned=None):
        return {p.card: p.cost.value for _h, p in turns.deck_turns(deck, catalogue, owned).played}

    got = costs(Deck(combatant=9, cards=cards, potential={31: 1}, manifestation=1))
    if got != upgraded:
        out.append(f"with Potential 3.1 and Ego Manifestation 1, the deck plays {got}, "
                   f"not the Basic card's `pot` version at 1 and the Signature card's "
                   f"`lbk` one at 0. See `upgrades_of` in decks/turns.py.")
    got = costs(Deck(combatant=9, cards=cards, potential={31: 0}, manifestation=0))
    if got != plain:
        out.append(f"with neither the node nor the level reached, the deck plays {got}: "
                   f"an upgrade applied that the Combatant has not reached.")
    owned = {9: CombatantState(potential={31: 1}, manifestation=1)}
    got = costs(Deck(combatant=9, cards=cards), owned)
    if got != upgraded:
        out.append(f"an owned Combatant's captured progress is not what its deck plays "
                   f"with where the deck sets none: {got} (plan D8). See `Deck.state` in "
                   f"decks/model.py.")
    got = costs(Deck(combatant=9, cards=cards, potential={}, manifestation=0), owned)
    if got != plain:
        out.append(f"the deck's own progress does not stand over the owned Combatant's: "
                   f"{got}.")
    held = turns.deck_turns(Deck(combatant=9, cards=[DeckCard("c_9_made_maker"),
                                                     DeckCard("c_9_dirge_maker")],
                                 potential={31: 1}), catalogue)
    made = {card.card: card.played.cost.value for card in held.created}
    if made != {"c_9_made_pot": 0, "c_1041_cre1_pot": 0}:
        out.append(f"cards made in battle under Potential 3.1 are {made}, not the `pot` "
                   f"versions, Dirge Bullet's at its exception's 0: the upgrade reaches "
                   f"made cards, and an exception its card's upgrade. See `_place` in "
                   f"decks/created.py.")

    def gives(level, nodes=None):
        deck = Deck(combatant=9, potential=nodes or {}, manifestation=level)
        return {b.source: (b.turn_ap, [(c.card, c.turns) for c in b.created])
                for b in turns.bonuses(deck, catalogue, deck.state())}

    got = gives(4, {70: 1})
    want = {"potential_70": (1, []), "manifestation_2": (1, []),
            "manifestation_4": (0, [("c_9_temp", "setup")])}
    if got != want:
        out.append(f"what a Combatant's progress gives at Potential 7 and Ego "
                   f"Manifestation 4 is {got}, not {want}: (AP each turn, the cards made "
                   f"and their list), a card made at the start of battle made once. See "
                   f"`_progress_sources` in decks/turns.py and `status_cards` in "
                   f"decks/created.py.")
    got = gives(6)
    if got != {"manifestation_6": (2, [])}:
        out.append(f"at Ego Manifestation 6, whose battle status replaces the levels "
                   f"below it, progress gives {got}, not 2 AP each turn alone.")
    piece = Deck(combatant=9, equipment=[Equipment("eq_9_maker")])
    held = turns.deck_turns(piece, catalogue)
    made = [(c.card, c.turns, any("once a turn" in n for n in c.notes)) for c in held.created]
    if made != [("c_9_temp", "regular", True)] or held.regular.cost != 1:
        out.append(f"an Equipment piece's card made when the battle triggers it is {made}, "
                   f"costing the regular turn {held.regular.cost}: it should count once a "
                   f"turn in the regular list, as a maker that is not a card does (plan "
                   f"D14), with a note saying so.")
    timing = {condition: turns.fires(condition, catalogue)
              for condition in ("cd_battle_start", "cd_turn_begin", "cd_card_use",
                                "cd_first_turn_use")}
    want = {"cd_battle_start": turns.AT_START, "cd_turn_begin": turns.EACH_TURN,
            "cd_card_use": turns.BATTLE, "cd_first_turn_use": turns.BATTLE}
    if timing != want:
        out.append(f"a trigger checked at the battle's start, a turn's start, a card's use "
                   f"and a card's use in turn 1 fires {timing}, not {want}. See `fires` in "
                   f"decks/turns.py.")
    moved = turns.played(DeckCard("c_9_regular_each_turn", overrides={"turns": "setup"}),
                         catalogue)
    if moved.turn_ap.value != 1:
        out.append("a card the user moves to setup keeps its lasting AP as the battle's, "
                   "where once played its status gives 1 AP each turn (plan D42).")
    return out


def _replays_report():
    """Attunement, a card's plays and draws a turn, follow-up effects,
    and an exception priced for a deck card."""
    from decks import created, turns
    from decks.model import Deck, DeckCard
    catalogue = _catalogue()
    out = []
    if turns.fires("cd_attuned", catalogue) != turns.DRAWN:
        out.append("Attunement's condition (a card holding the status is drawn) does not "
                   "read as firing each time the card is drawn. See `fires` and "
                   "`_attunement` in decks/turns.py.")
    hunger = turns.played(DeckCard("c_9_attuned", overrides={"drawn": 3}), catalogue)
    got = (hunger.unplayed, hunger.turns, hunger.per_turn())
    if got != (True, "regular", (3, 0, 3, 3)):
        out.append(f"a card drawn for its Attunement alone, 3 times a turn, reads as "
                   f"(never played, list, (cards, cost, draw, AP a turn)) {got}, not (True, "
                   f"'regular', (3, 0, 3, 3)): each draw takes a draw and gives its own, "
                   f"and it is never played. See `played` in decks/turns.py.")
    attack = turns.played(DeckCard("c_9_attuned_attack"), catalogue)
    if (attack.unplayed, attack.per_turn()) != (False, (1, 1, 1, 1)):
        out.append(f"a card played that is also attuned reads as never played "
                   f"{attack.unplayed}, a turn {attack.per_turn()}, not False and (1, 1, 1, 1).")
    for card in ("c_9_attunes_others", "c_9_attunes_unit"):
        others = turns.played(DeckCard(card), catalogue)
        if others.drawn_draw.value or others.draw.value:
            out.append(f"an Attunement put on other cards or the unit ({card}) counts as "
                       f"this card's own draw: theirs fires on another card's draw.")
    replayed = turns.played(DeckCard("c_9_plain", overrides={"plays": 3}), catalogue)
    if replayed.per_turn() != (1, 3, 3, 3):
        out.append(f"a card played 3 times a turn reads a turn as {replayed.per_turn()}, not "
                   f"(1, 3, 3, 3): its cost, draw and AP times its plays, one draw.")
    held = turns.deck_turns(Deck(combatant=9, cards=[DeckCard("c_9_maker_hand",
                                                              overrides={"plays": 2})]),
                            catalogue)
    temps = sum(1 for card in held.regular_cards if card.card == "c_9_temp")
    if temps != 4:
        out.append(f"a card played twice a turn, making 2 cards each time, puts {temps} of "
                   f"them in the regular list, not 4. See `deck_turns` in decks/turns.py.")
    mealtime = turns.played(DeckCard("c_1052_uni4"), catalogue,
                            {"c_1052_uni4": "c_1052_uni4_lbk"})
    if (mealtime.card, mealtime.cost.value) != ("c_1052_uni4_lbk", 0):
        out.append(f"Mealtime, upgraded, costs {mealtime.cost.value}: the exceptions "
                   f"table's practical cost holds for a deck card and its upgrade. See "
                   f"`played` in decks/turns.py and decks/exceptions.py.")
    discarder = turns.played(DeckCard("c_9_discarder"), catalogue)
    made = created.created_cards(DeckCard("c_9_discarder"), discarder, catalogue)
    if [m.card for m in made] != ["c_9_temp"] or str(discarder.draw) != "?":
        out.append(f"a discard's follow-ups read as making {[m.card for m in made]} and "
                   f"drawing {discarder.draw}, not one Temp card, made on the discard being "
                   f"done, and a draw the battle decides. See `chained` in "
                   f"decks/catalogue.py and `by_this_effect` in decks/turns.py.")
    held = DeckCard("c_9_discarder_once")
    made = [(m.card, m.every_time)
            for m in created.created_cards(held, turns.played(held, catalogue), catalogue)]
    if made != [("c_9_temp", False)]:
        out.append(f"a card played once, whose discard's follow-up makes a card, reads as "
                   f"making {made}, not one Temp card made once: that follow-up waits on "
                   f"the discard alone, not on its sibling's condition of the battle's. "
                   f"See `creations` in decks/created.py.")
    upgrade = turns.deck_turns(Deck(combatant=9, cards=[DeckCard("c_9_upgrade_hand",
                                                                 overrides={"plays": 2})]),
                               catalogue)
    temps = sum(1 for card in upgrade.setup_cards if card.card == "c_9_temp")
    if temps != 2:
        out.append(f"an Upgrade played twice a turn, making 2 cards once, puts {temps} of "
                   f"them in the setup list, not 2: its plays multiply only what it makes "
                   f"every time.")
    return out


def _ego_report():
    """The Ego skills behind the team's options (plan D2, D40): used once,
    in setup turn 1, for Ego Points, and what the Combatant's makes,
    placed as a card made once."""
    from decks import turns
    from decks.model import Deck, DeckCard, Team
    catalogue = _catalogue()
    out = []
    team = Team(decks=[Deck(combatant=9, cards=[DeckCard("c_9_upgrade")], partner=7)])
    off = turns.team_turns(team, catalogue)
    if off.decks[0].ego or [c.card for c in off.setup.turns[0].setup] != ["c_9_upgrade"]:
        out.append("an Ego skill counts with the team's options off (plan D2, D40).")
    on = turns.team_turns(team, catalogue, partner_ego=True, combatant_ego=True)
    held = on.decks[0]
    skills = sorted(skill.card for skill in held.ego)
    if skills != ["c_9_eps", "p_7"]:
        out.append(f"the Ego skills counted are {skills}, not the Combatant's and the "
                   f"partner's. See `ego_skills` in decks/turns.py.")
    if any(skill.cost.value or skill.needs_draw for skill in held.ego):
        out.append("an Ego skill costs AP or needs a draw; it costs Ego Points and is "
                   "never drawn.")
    made = sorted((c.card, c.turns, c.needs_draw) for c in held.created)
    want = [("c_9_stay", "regular", True), ("c_9_temp", "setup", False)]
    if made != want:
        out.append(f"the Ego skill's cards are {made}, not {want}: one that leaves after "
                   f"use in setup, needing no draw, one that stays in the regular list "
                   f"(plan D40).")
    first = on.setup.turns[0] if on.setup.turns else None
    played = [c.card for c in first.setup] if first else []
    left = (first.draw_left, first.ap_left) if first else None
    if played != ["p_7", "c_9_eps", "c_9_temp", "c_9_temp", "c_9_upgrade"] or left != (8, 1):
        out.append(f"setup turn 1 plays {played}, leaving {left}: both Ego skills first, "
                   f"for no AP, their 2 draws and 1 AP paying for the rest, leaving (8, "
                   f"1). See `plan_setup` in decks/turns.py.")
    upgraded = turns.deck_turns(Deck(combatant=9, manifestation=3), catalogue,
                                combatant_ego=True)
    if [skill.card for skill in upgraded.ego] != ["c_9_eps_lbk"]:
        out.append("at Ego Manifestation 3 the Ego skill is not its upgrade, c_9_eps_lbk.")
    return out


def _card_like(name, cost=0, draw=0, ap=0, opener=False, turn_ap=0):
    from decks import turns
    return turns.Played(card=name, name=name, cost=turns.Figure(cost),
                        draw=turns.Figure(draw), ap=turns.Figure(ap), talents=(),
                        turns="setup", opener=opener, turn_ap=turns.Figure(turn_ap))


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
        ("an Upgrade's lasting AP paying for the next turn's setup",
         [up("lasting", 1, turn_ap=1), up("u4", 4)], [], [],
         [["lasting"], ["u4"]], (4, 2), []),
        ("a start-of-battle bonus in turn 1", [up("u4", 4)], [], [],
         [["u4"]], (4, 0), [], {"start_ap": 1}),
        ("a bonus every turn", [up("u4a", 4), up("u4b", 4)], [], [],
         [["u4a"], ["u4b"]], (4, 0), [], {"bonus_ap": 1}),
    ]


def _setup_report():
    """The setup plan (plan D72), on cards built for each step."""
    from decks import turns
    out = []
    for what, setup, regular, openers, played, left, stuck, *extra in _setup_cases():
        plan = turns.plan_setup(setup, regular, draw=5, energy=3, openers=openers,
                                **(extra[0] if extra else {}))
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
    return (_rules_report() + _totals_report() + _bonuses_report() + _pool_report()
            + _setup_report() + _created_report() + _progress_report() + _ego_report()
            + _replays_report() + _deck_calcs_report())


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
     "if quietus and priced:", "if False:", "a Quietus card"),
    ("a card from the draw pile not a draw", "decks.turns:_Reader.read",
     "if place in DRAWN_FROM:", "if False:", "a card taken from the draw pile to hand"),
    ("a card from the Discard pile not a draw", "decks.turns:DRAWN_FROM",
     '+ ("CARD_PLACE_DECK_DISCARD", "CARD_PLACE_DISCARD")', "+ ()",
     "a card moved to hand from the Discard pile"),
    ("a card that may be played again counted drawn", "decks.turns:_Reader.read",
     "if place in DRAWN_FROM:", "if place in DRAWN_FROM or 'USED' in place:",
     "a pile the Used pile is among"),
    ("a card that may be played again left unshown", "decks.turns:_Reader.read",
     "elif any(pile in place for pile in PILE_WORDS):", "elif False:",
     "played for free from the Graveyard"),
    ("a card that moves itself to hand not a draw", "decks.turns:_Reader.read",
     'add("draw", 1, "1 draw: it moves to hand")', "pass",
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
     'self.walk(option["effects"], holder, count, mode, why, lasting)', "pass",
     "a choice"),
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
     "self.cards += cards", "pass", "a deck's regular list sums"),
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
     "at_start = [card for card in setup if card.opener or card.ego]", "at_start = []",
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
     "every_time=fired or via_lasting or not once_by_kind", "every_time=True",
     "an Upgrade's card made into hand once"),
    ("a card made into hand needing a draw", "decks.created:_place",
     "needs_draw = not (gone and creation.to_hand)", "needs_draw = True",
     "a card made into hand, leaving after use"),
    ("a maker's keywords ignored", "decks.created:_place",
     "talents = tuple(dict.fromkeys(made.talents + creation.talents))",
     "talents = made.talents", "a card its maker gives Exhaust"),
    ("the Graveyard's keeping ignored", "decks.created:_gone",
     'if effect.get("eff") == NOT_SHUFFLE:', "if False:", "stays in the Graveyard"),
    ("a lasting status's cards made once", "decks.created:creations",
     'lasting = status.get("term_type_1") in LASTING', "lasting = False",
     "an Upgrade's lasting status"),
    ("a made card that changes nothing counted", "decks.created:_place",
     "idle = (creation.to_hand and made.cost.value == 0",
     "idle = (False and made.cost.value == 0", "a made card that changes nothing"),
    ("the exceptions table ignored", "decks.created:_place",
     "exception = EXCEPTIONS.get(card_id) or EXCEPTIONS.get(base_id, {})", "exception = {}",
     "an exception the maintainer ignores"),
    ("a made card's copies counted once", "decks.turns:deck_turns",
     "listed[made.turns].extend([copy] * made.copies * times)",
     "listed[made.turns].extend([copy] * times)",
     "a deck whose card makes two cards into hand"),
    ("a growing deck not flagged", "decks.created:_place",
     "grows=every_time and not gone", "grows=False",
     "a card that stays, made on every play"),
    ("one of several not noted", "decks.created:_place",
     "if creation.pick or creation.pool:", "if False:", "one of two cards made"),
    ("an exception's practical cost ignored", "decks.created:_place",
     'if "cost" in exception:', "if False:", "Dirge Bullet's at its exception's 0"),
    ("hidden and idle made cards counted", "decks.turns:deck_turns",
     "if made.hidden or made.idle or made.turns not in listed:",
     "if made.turns not in listed:", "is counted in a list"),
    ("the start of battle read as every turn", "decks.turns:fires",
     '_number(part.get("condition_timing_value")) == 1):\n                first_turn = True',
     '_number(part.get("condition_timing_value")) == 1):\n                pass',
     "the deck's Equipment, Buff and Mutation give"),
    ("each turn's start read as the battle's", "decks.turns:fires",
     "return EACH_TURN if turn_start else BATTLE", "return BATTLE",
     "a draw at the next turn's start"),
    ("a lasting status not tracked", "decks.turns:_Reader.walk",
     'lasting or status.get("term_type_1") in LASTING)', "lasting)",
     "an Upgrade's lasting AP each turn reads as"),
    ("a regular card's lasting gain counted steady", "decks.turns:played",
     "if turns != SETUP and (lasting[key].value or lasting[key].unknown):", "if False:",
     "a regular card's lasting effect counts"),
    ("a chance read as plain", "decks.turns:_Reader.walk",
     'if _number(effect.get("run_pct"), 100) < 100:', "if False:", "a draw by chance"),
    ("the bonuses left out of a deck", "decks.turns:deck_turns",
     "out.bonuses = bonuses(deck, catalogue, out.state, out.upgrades)", "out.bonuses = []",
     "Equipment and Buff give 0 AP a turn"),
    ("an Equipment piece's star level ignored", "decks.turns:bonuses",
     'star = held["stars"].get(str(piece.stars)) or held["stars"].get("1", {})',
     'star = held["stars"].get("1", {})', "the deck's Equipment, Buff and Mutation give"),
    ("the start bonus left out of turn 1", "decks.turns:plan_setup",
     "hand, ap = hand + start_draw, ap + start_ap", "pass",
     "a start-of-battle bonus in turn 1"),
    ("an Upgrade's gains left out of later turns", "decks.turns:plan_setup",
     "gained_ap += sum(card.turn_ap.value for card in now)", "pass",
     "an Upgrade's lasting AP paying"),
    ("the turn bonus left out of setup", "decks.turns:plan_setup",
     "hand, ap = draw + bonus_draw + gained_draw, energy + bonus_ap + gained_ap",
     "hand, ap = draw + gained_draw, energy + gained_ap", "a bonus every turn"),
    ("the pool's cap typed in", "decks.turns:_pool_of",
     'cap = _number(catalogue.statuses.get(held["status"], {}).get("overlay_value_max"))',
     "cap = 6", "the pool, capped by the client's status"),
    ("the user's pool ignored", "decks.turns:_pool_of",
     'return (deck.ap_pool if deck.ap_pool is not None else cap), card.card, held["pays"]',
     'return cap, card.card, held["pays"]', "the user's own pool figure"),
    ("the pool saving nothing", "decks.turns:DeckTurns.pool_saving",
     "return min(self.pool, sum(card.per_turn()[1] for card in self.regular_cards",
     "return 0 * min(self.pool, sum(card.per_turn()[1] for card in self.regular_cards",
     "the pool, capped by the client's status"),
    ("the pool unused in setup", "decks.turns:plan_setup",
     "paid = min(pool, card.per_turn()[1]) if card.pool_paid else 0", "paid = 0",
     "with Rita's pool switched on"),
    ("the pool never switched on in setup", "decks.turns:plan_setup",
     "gained_pool += sum(card.pool_switch for card in now)", "pass",
     "with Rita's pool switched on"),
    ("Ravages ignored", "decks.turns:team_turns",
     'energy = catalogue.constants.get("energy", 3) + ravages * RAVAGE_AP',
     'energy = catalogue.constants.get("energy", 3)', "two Ravages a turn"),
    ("a free play from the draw pile not a draw", "decks.turns:_Reader.read",
     'taken("played for free")', "pass", "a card played for free from the draw pile"),
    ("a free play's saved cost not shown", "decks.turns:_Reader.read",
     'self.ap.unknown.append((None, "AP: the cost of each card it plays for free"))',
     "pass", "a free play's saved cost"),
    ("a Persona's discard proc priced", "decks.turns:played",
     'catalogue.effects.get(effect, {}).get("eff") == TESTAMENT for effect in effects)',
     "False for effect in effects)", "procced by a discard"),
    ("the team's Desire points not summed", "decks.turns:team_turns",
     "points[keyword] = points.get(keyword, 0) + held_points", "pass",
     "the team's Desire points sum"),
    ("Inquiry's draw not noted", "decks.turns:_desire_notes",
     "if points.get(48, 0) >= INQUIRY_DRAW_AT:", "if False:", "Inquiry at 5 points"),
    ("a Potential node's upgrade ignored", "decks.turns:upgrades_of",
     'upgraded = catalogue.upgrades.get(card, {}).get("pot")', "upgraded = None",
     "with Potential 3.1 and Ego Manifestation 1"),
    ("an Ego Manifestation upgrade ignored", "decks.turns:upgrades_of",
     'upgraded = catalogue.upgrades.get(card, {}).get("lbk")', "upgraded = None",
     "with Potential 3.1 and Ego Manifestation 1"),
    ("a node's level ignored", "decks.turns:upgrades_of",
     "if _number(at) <= level:", "if True:", "an upgrade applied that the Combatant"),
    ("an Ego Manifestation level ignored", "decks.turns:upgrades_of",
     'if held["level"] <= state.manifestation:', "if True:",
     "an upgrade applied that the Combatant"),
    ("the upgrades not played", "decks.turns:played",
     "card_id = upgrades.get(card_id, card_id)", "pass",
     "with Potential 3.1 and Ego Manifestation 1"),
    ("the owned Combatant's progress ignored", "decks.model:Deck.state",
     "held = (owned or {}).get(self.combatant) or CombatantState()",
     "held = CombatantState()", "an owned Combatant's captured progress"),
    ("the deck's own progress ignored", "decks.model:Deck.state",
     "potential=held.potential if self.potential is None else self.potential,",
     "potential=held.potential,", "the deck's own progress does not stand"),
    ("a made card not upgraded", "decks.created:_place",
     "card_id = upgrades.get(base_id, base_id)", "card_id = base_id",
     "cards made in battle under Potential 3.1"),
    ("an exception not held for its card's upgrade", "decks.created:_place",
     "exception = EXCEPTIONS.get(card_id) or EXCEPTIONS.get(base_id, {})",
     "exception = EXCEPTIONS.get(card_id, {})", "cards made in battle under Potential 3.1"),
    ("progress statuses not read", "decks.turns:bonuses",
     "sources += _progress_sources(deck.combatant, state, catalogue)", "pass",
     "at Potential 7 and Ego Manifestation 4"),
    ("a node's statuses not read", "decks.turns:_progress_sources",
     "if reached:", "if False:", "at Potential 7 and Ego Manifestation 4"),
    ("an overwrite adding to the levels below", "decks.turns:_progress_sources",
     'if held["type"] == OVERWRITE:', "if False:", "at Ego Manifestation 6"),
    ("cards statuses make not read", "decks.turns:bonuses",
     "bonus.created = status_cards(source, name, statuses, catalogue, upgrades)",
     "bonus.created = []", "an Equipment piece's card made"),
    ("cards statuses make left out of the lists", "decks.turns:deck_turns",
     "for made in bonus.created:", "for made in ():", "an Equipment piece's card made"),
    ("a card made at the start of battle made every turn", "decks.created:status_cards",
     "once = creation.when in (PLAY, AT_START)", "once = False",
     "at Potential 7 and Ego Manifestation 4"),
    ("the battle's start read as a turn's", "decks.turns:fires",
     "elif timings == {BATTLE_START}:", "elif False:", "a trigger checked at"),
    ("a turn's start checked by a stack control read as the battle's",
     "decks.turns:fires", "turn_start = turn_start or bool(timings)", "pass",
     "a trigger checked at"),
    ("any battle timing read as a turn's start", "decks.turns:fires",
     "elif timings <= set(TURN_START) | {BATTLE_START}:", "elif True:",
     "a trigger checked at"),
    ("the user's list placed after the lasting effects", "decks.turns:played",
     'turns = held.overrides.get("turns", turns)', "pass",
     "a card the user moves to setup"),
    ("the Combatant's Ego skill never counted", "decks.turns:ego_skills",
     'ids.append(own["ego"])', "pass", "the Ego skills counted"),
    ("the partner's Ego skill never counted", "decks.turns:ego_skills",
     'ids.append(held["card"])', "pass", "the Ego skills counted"),
    ("an Ego skill priced in AP", "decks.turns:ego_skills",
     "out.append(replace(skill, cost=Figure(), needs_draw=False,",
     "out.append(replace(skill, needs_draw=False,", "costs AP or needs a draw"),
    ("an Ego skill drawn", "decks.turns:ego_skills",
     "cost=Figure(), needs_draw=False,", "cost=Figure(), needs_draw=True,",
     "costs AP or needs a draw"),
    ("an Ego skill's cards made every turn", "decks.turns:ego_skills",
     'skill = played(DeckCard(card_id, overrides={"turns": SETUP}), catalogue, upgrades)',
     "skill = played(DeckCard(card_id), catalogue, upgrades)", "the Ego skill's cards"),
    ("an Ego skill waiting for a hand", "decks.turns:plan_setup",
     "at_start = [card for card in setup if card.opener or card.ego]",
     "at_start = [card for card in setup if card.opener]", "setup turn 1 plays"),
    ("an Ego skill left out of setup", "decks.turns:deck_turns",
     "out.setup_cards.append(skill)", "pass", "setup turn 1 plays"),
    ("an Ego skill's cards not made", "decks.turns:deck_turns",
     "for made in created_cards(DeckCard(skill.card), skill, catalogue,",
     "for made in [] and created_cards(DeckCard(skill.card), skill, catalogue,",
     "the Ego skill's cards"),
    ("Attunement not read", "decks.turns:fires",
     "if len(controls) == 1 and _attunement(controls[0]):", "if False:",
     "Attunement's condition"),
    ("an Attunement on the unit read as this card's", "decks.turns:_Reader.walk",
     "if timing == DRAWN and holder != SELF:", "if False:",
     "an Attunement put on other cards or the unit"),
    ("a card drawn for its Attunement read as played", "decks.turns:played",
     "unplayed = any(f.value or f.unknown for f in drawn.values()) and not any(",
     "unplayed = False and not any(", "drawn for its Attunement alone"),
    ("a card drawn for its Attunement left in setup", "decks.turns:played",
     "if unplayed:\n        turns = REGULAR", "if unplayed:\n        turns = SETUP",
     "drawn for its Attunement alone"),
    ("a card's plays a turn ignored", "decks.turns:Played.per_turn",
     "plays = 0 if self.unplayed else self.plays", "plays = 0 if self.unplayed else 1",
     "a card played 3 times a turn"),
    ("a card's draws a turn ignored", "decks.turns:Played.per_turn",
     "cards = self.drawn if self.needs_draw else 0", "cards = 1 if self.needs_draw else 0",
     "drawn for its Attunement alone"),
    ("an Attunement's draw ignored", "decks.turns:Played.per_turn",
     "self.draw.value * plays + self.drawn_draw.value * self.drawn",
     "self.draw.value * plays", "drawn for its Attunement alone"),
    ("the user's plays a turn not read", "decks.turns:played",
     'plays=int(held.overrides.get("plays", 1))', "plays=1",
     "a card played 3 times a turn"),
    ("the user's draws a turn not read", "decks.turns:played",
     'drawn=int(held.overrides.get("drawn", 1))', "drawn=1",
     "drawn for its Attunement alone"),
    ("a maker's plays not multiplying what it makes", "decks.turns:deck_turns",
     "times = plays if made.every_time else 1", "times = 1",
     "a card played twice a turn, making 2 cards"),
    ("a maker's plays multiplying what it makes once", "decks.turns:deck_turns",
     "times = plays if made.every_time else 1", "times = plays",
     "an Upgrade played twice a turn"),
    ("a maker's plays not passed on", "decks.turns:deck_turns",
     "place(made, played_card.plays)", "place(made)",
     "a card played twice a turn, making 2 cards"),
    ("the exceptions table ignored for a deck card", "decks.turns:played",
     "exception = EXCEPTIONS.get(card_id) or EXCEPTIONS.get(held.card, {})",
     "exception = {}", "Mealtime, upgraded, costs"),
    ("an exception not held for a deck card's upgrade", "decks.turns:played",
     "exception = EXCEPTIONS.get(card_id) or EXCEPTIONS.get(held.card, {})",
     "exception = EXCEPTIONS.get(card_id, {})", "Mealtime, upgraded, costs"),
    ("follow-ups not read", "decks.turns:_Reader.walk",
     "for follow_condition, follow in chained(effect):",
     "for follow_condition, follow in ():", "a discard's follow-ups"),
    ("a follow-up the battle decides read as met", "decks.turns:_Reader.walk",
     "mode_now = BATTLE", "pass", "a discard's follow-ups"),
    ("follow-ups' cards not made", "decks.created:creations",
     "for condition, follow in chained(effect):", "for condition, follow in ():",
     "a discard's follow-ups"),
    ("a follow-up met by its own effect read as the battle's", "decks.turns:by_this_effect",
     "return bool(controls) and all(", "return False and all(",
     "a card played once, whose discard's follow-up"),
    ("met follow-ups gated with their siblings", "decks.created:creations",
     "walk([follow for _condition, follow in met], via_lasting, fired, here, words)",
     "walk([follow for _condition, follow in met], via_lasting, True, BATTLE, words)",
     "a card played once, whose discard's follow-up"),
]
