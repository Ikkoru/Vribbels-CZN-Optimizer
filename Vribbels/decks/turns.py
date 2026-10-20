"""What a card in a deck costs, draws and gives in AP each time it is
played, and which turns it counts in (docs/decks.md, *The turn*).

A card's effects are walked as the client chains them: an effect can
put a status on the card itself, on other cards or on a unit, and a
status holds effects of its own. What an effect does depends on who
holds it, and a figure is plain only where nothing on the way to it
waits for the battle: no trigger, and no condition but a matching card
being in the pile.

A figure the battle decides, such as a draw for each card discarded or
an X card's cost, counts as 0, and the figure names it in `unknown`
with its amount where the data gives one, for the user to give a number
(plan D12).
"""

from dataclasses import dataclass, field

from .catalogue import _list

DRAW = "SKILL_EFF_CARD_DRAW"
ENERGY = "SKILL_EFF_ENERGY_CHANGE"
MOVE = "SKILL_EFF_CARD_MOVE_TO"
COST_CHANGE = ("SKILL_EFF_CARD_COST_CHANGE", "SKILL_EFF_CARD_COST_CHANGE_PASSIVE")
CHOICE = "SKILL_EFF_CARD_OPTION_SELECT"
# The operations a figure can be plain through: on play, and while a
# status is held. A trigger waits for the battle.
STEADY = ("OPERATION_ACTIVE", "OPERATION_PASSIVE")
PLAIN = "VALUE_COMMON"
SUBTRACT = ("MATHSIGN_SUBTRACT", "MATHSIGN_SUBTRACT_MIN_0")
THIS_CARD = "CARD_SET_THIS_CARD"
NO_CARDS = "CARD_SET_NONE"
HAND = "CARD_PLACE_HAND"
# The piles a draw takes from.
DRAW_PILES = ("CARD_PLACE_DECK", "CARD_PLACE_DECK_TOP", "CARD_PLACE_DECK_BOTTOM")
# Costs the client stores that are no AP figure: an X card's, which
# spends the AP left, and a card's that is never played from hand.
X_COST, NO_COST = -1, -2

UPGRADE = "CARD_POWER"
EXHAUST = "TALENT_EXHAUST"
REMOVE = "TALENT_REMOVE"
UNUSABLE = "TALENT_UNPLAYABLE"
EPHEMERAL = "TALENT_ETHEREAL"
OPENER = "TALENT_OPENING"
# "When this card is Discarded, proc this card": a deck procs it by
# discarding it, for no AP (plan D67).
QUIETUS = "TALENT_TESTAMENT"
# Keywords whose cost the battle lowers (plan D19): Ignition, once a
# card is Exhausted, and Lead, by chance at the start of the turn.
COST_KEYWORDS = {"TALENT_IGNITE": "Ignition: 1 less once a card is Exhausted",
                 "TALENT_LEAD": "Lead: by chance 1 less at the start of the turn"}

SETUP, REGULAR, NEITHER = "setup", "regular", "neither"

# A condition that only asks for a matching card in the draw pile, or
# the draw and discard piles, is met each time by a deck that holds
# one: "Draw 1 Attack Card of this unit". Any other, the battle decides.
PILES = ("CARD_PLACE_DECK", "CARD_PLACE_DECK_DISCARD")

# Who holds an effect: the card, a status on the card itself, a status
# on other cards, or a status on a unit.
CARD, SELF, OTHERS, UNIT = "card", "self", "others", "unit"


@dataclass
class Figure:
    """A per-play figure: what the data states plainly, and each part
    the battle decides, as (its amount where the data gives one, else
    None; why the battle decides it)."""

    value: int = 0
    unknown: list = field(default_factory=list)

    def __str__(self):
        if not self.unknown:
            return str(self.value)
        return f"{self.value}+?" if self.value else "?"

    def at_most(self):
        """The figure with every conditional part counted that has an
        amount: what it comes to when the battle grants them all."""
        return self.value + sum(amount for amount, _why in self.unknown
                                if amount is not None)

    def add(self, amount, plain, why):
        if plain:
            self.value += amount
        else:
            self.unknown.append((amount, why))


@dataclass
class Played:
    """One card in a deck, as it plays."""

    card: str
    name: str
    cost: Figure
    draw: Figure
    ap: Figure
    talents: tuple
    turns: str
    # The cost the card prints, where the calculator counts another
    # (a Quietus card's 0).
    printed_cost: int | None = None
    # Played by itself at the start of battle, for AP (plan D18).
    opener: bool = False
    # What was assumed, such as a choice's first option.
    notes: list = field(default_factory=list)


def _keyword(talents, family):
    """Whether `talents` holds a keyword of `family`: Exhaust, Exhaust 2
    and the rest."""
    return any(t == family or t.startswith(family + "_") for t in talents)


def _cost_change(cost, amount, sign):
    if not amount or sign in ("", "MATHSIGN_NONE"):
        return cost
    if sign in SUBTRACT:
        return max(0, cost - amount) if sign.endswith("MIN_0") else cost - amount
    return cost + amount


def available(condition_id, catalogue):
    """Whether a condition only asks that a matching card be in the draw
    pile, or the draw and discard piles: one a deck holding such a card
    meets each time."""
    controls = catalogue.conditions.get(condition_id)
    if not controls:
        return False
    for control in controls:
        if control["type"] != "stack" or control["units"] or control["timings"]:
            return False
        for part in control["cards"]:
            if (part.get("condition_card") != "CONDITION_CARD_AMOUNT"
                    or part.get("card_opt_negate_flag") == "YES"
                    or part.get("condition_card_card_place") not in PILES
                    or part.get("condition_card_value_ineq") != "INEQUALITY_GE"
                    or int(part.get("condition_card_value") or 0) > 1):
                return False
    return True


def _number(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _amount(effect):
    """An effect's figure, negative where it subtracts."""
    amount = _number(effect.get("eff_value"))
    return -amount if effect.get("eff_value_math_sign") in SUBTRACT else amount


def _holder(effect):
    """Who holds the statuses `effect` puts on, and on how many cards."""
    if effect.get("target_card_set") == THIS_CARD:
        return SELF, 1
    if effect.get("target_card_set", NO_CARDS) != NO_CARDS \
            or effect.get("target_card_set_list_card_place", "CARD_PLACE_NONE") \
            != "CARD_PLACE_NONE":
        return OTHERS, max(1, _number(effect.get("eff_card_target_count"), 1))
    return UNIT, 1


# A status that lasts a number of uses takes it from the effect that puts
# it on: "the next 2 times", "Draw 2 next turn" put a 2-use status on.
USES_TERMS = ("TERM_EFF", "TERM_CARD_USE")


def _uses(effect, status):
    if (status.get("term_type_1") or "").startswith(USES_TERMS):
        return max(1, _number(effect.get("eff_value"), 1))
    return 1


class _Reader:
    """Walks one card's effects into its figures."""

    def __init__(self, catalogue, cost):
        self.catalogue = catalogue
        self.cost = cost
        self.draw = Figure()
        self.ap = Figure()
        self.notes = []
        self.seen = set()

    def walk(self, effect_ids, holder=CARD, count=1, steady=True, why=""):
        """Read `effect_ids`, held by `holder` (on `count` cards where
        it is OTHERS); `steady` is False once a trigger, or a condition
        the battle decides, lies on the way, and `why` names the first."""
        for effect_id in effect_ids:
            key = (effect_id, holder)
            effect = self.catalogue.effects.get(effect_id)
            if effect is None or key in self.seen:
                continue
            self.seen.add(key)
            here_steady, here_why = steady, why
            if effect.get("operation") not in STEADY:
                here_steady = False
                here_why = here_why or f"when triggered ({effect_id})"
            condition = effect.get("eff_link_condition_id")
            if condition and not available(condition, self.catalogue):
                here_steady = False
                here_why = here_why or f"if {condition}"
            self.read(effect, effect_id, holder, count, here_steady, here_why)
            for status_id in _list(effect.get("link_cs_id")):
                status = self.catalogue.statuses.get(status_id, {})
                held, n = _holder(effect)
                self.walk(_list(status.get("link_skill_eff_id")), held,
                          n * count * _uses(effect, status), here_steady,
                          here_why or "")

    def read(self, effect, effect_id, holder, count, steady, why):
        """What one effect adds to the figures. `count` multiplies what
        it gives: the uses its status lasts, and for a status on other
        cards, how many cards hold it."""
        kind = effect.get("eff")
        plain_value = effect.get("eff_value_type_1", PLAIN) == PLAIN
        each = _amount(effect) if plain_value else None
        amount = each * count if plain_value else None
        plain = steady and plain_value
        reason = why or (f"by {effect.get('eff_value_type_1')}" if not plain_value else "")
        on_this = effect.get("target_card_set") == THIS_CARD
        if kind == CHOICE:
            options = _list(effect.get("eff_opt_multiple_link"))
            option = self.catalogue.card(options[0]) if options else None
            if option is not None:
                self.notes.append(f"a choice: its first option, "
                                  f"{option['name'] or options[0]}, assumed")
                self.walk(option["effects"], holder, count, steady, why)
        elif holder == OTHERS and kind in COST_CHANGE and on_this:
            # Another card's cost cut is AP gained (plan D68).
            gain = -amount if amount is not None else None
            self.ap.add(gain, plain, f"{gain} AP: other cards' cost cut {reason}".rstrip())
        elif holder == OTHERS:
            return                  # what another card does when it plays
        elif kind == DRAW:
            self.draw.add(amount, plain, f"{amount} draw {reason}".rstrip())
        elif kind == ENERGY:
            self.ap.add(amount, plain, f"{amount} AP {reason}".rstrip())
        elif kind == MOVE and effect.get("eff_card_place") == HAND:
            if on_this:
                # Comes to hand by itself, needing no draw (plan D69).
                self.draw.add(1, plain, f"1 draw: it moves to hand {reason}".rstrip())
            elif effect.get("target_card_set_list_card_place") in DRAW_PILES:
                self.draw.add(amount, plain, f"{amount} draw from the draw pile "
                              f"{reason}".rstrip())
        elif kind in COST_CHANGE and holder == SELF and on_this:
            self.cost.unknown.append((each, f"its cost changes by {each} in "
                                      f"battle {reason}".rstrip()))
        elif kind in COST_CHANGE and not on_this:
            # Cards the effect names, or every card a unit holds: their
            # cost cut is AP gained (plan D68).
            gain = -amount if amount is not None else None
            self.ap.add(gain, plain, f"{gain} AP: other cards' cost cut {reason}".rstrip())


def played(held, catalogue):
    """`held`, a `model.DeckCard`, as it plays: a `Played`, or None for
    a card the catalogue lacks."""
    base = catalogue.card(held.card)
    if base is None:
        return None
    card_id = held.held_id(catalogue)
    card = catalogue.card(card_id) or base
    talents = list(card["talents"])
    cost = Figure()
    if card["cost"] == X_COST:
        cost.unknown.append((None, "an X card: it spends the AP left"))
    elif card["cost"] == NO_COST:
        cost.unknown.append((None, "the client gives it no cost"))
    else:
        cost.value = card["cost"]
    effects = list(card["effects"])
    changes = []
    for epiphany_id in (held.neutral, held.divine):
        epiphany = catalogue.epiphanies.get(epiphany_id) if epiphany_id else None
        if epiphany is not None:
            effects += epiphany["effects"]
            talents += epiphany["talents"]
            changes.append((epiphany["add_cost"], epiphany["add_cost_sign"]))
    for effect_id in held.persona:
        effect = catalogue.persona.get("effects", {}).get(effect_id)
        if effect is not None:
            effects += effect["effects"]
            talents += effect["add_talents"]
            changes.append((effect["add_cost"], effect["add_cost_sign"]))
    if not cost.unknown:
        for amount, sign in changes:
            cost.value = _cost_change(cost.value, amount, sign)
    reader = _Reader(catalogue, cost)
    reader.walk(effects)
    priced = card["cost"] not in (X_COST, NO_COST)
    for keyword, why in COST_KEYWORDS.items():
        if keyword in talents and priced:
            cost.unknown.append((-1, why))
    printed = None
    if QUIETUS in talents and priced:
        printed, cost.value = cost.value, 0
        reader.notes.append(f"Quietus: procced by a discard, for no AP "
                            f"(it prints {printed})")
    if UNUSABLE in talents and EPHEMERAL in talents:
        turns = NEITHER
    elif card["category"] == UPGRADE or _keyword(talents, EXHAUST) \
            or _keyword(talents, REMOVE):
        turns = SETUP
    else:
        turns = REGULAR
    return Played(card=card_id, name=base["name"] or held.card, cost=cost,
                  draw=reader.draw, ap=reader.ap,
                  talents=tuple(dict.fromkeys(talents)), turns=turns,
                  printed_cost=printed, opener=OPENER in talents,
                  notes=reader.notes)
