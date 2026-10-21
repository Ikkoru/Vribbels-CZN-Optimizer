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

from dataclasses import dataclass, field, replace

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
    # It must be drawn to be played; a card made into hand need not be
    # (plan D15).
    needs_draw: bool = True


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


def _say(amount):
    """An amount leading a sentence, or nothing where the data gives none."""
    return "" if amount is None else f"{amount} "


def _by(amount):
    return "" if amount is None else f"by {amount} "


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
            self.ap.add(gain, plain, f"{_say(gain)}AP: other cards' cost cut "
                        f"{reason}".rstrip())
        elif holder == OTHERS:
            return                  # what another card does when it plays
        elif kind == DRAW:
            self.draw.add(amount, plain, f"{_say(amount)}draw {reason}".rstrip())
        elif kind == ENERGY:
            self.ap.add(amount, plain, f"{_say(amount)}AP {reason}".rstrip())
        elif kind == MOVE and effect.get("eff_card_place") == HAND:
            if on_this:
                # Comes to hand by itself, needing no draw (plan D69).
                self.draw.add(1, plain, f"1 draw: it moves to hand {reason}".rstrip())
            elif effect.get("target_card_set_list_card_place") in DRAW_PILES:
                self.draw.add(amount, plain, f"{_say(amount)}draw from the draw pile "
                              f"{reason}".rstrip())
        elif kind in COST_CHANGE and holder == SELF and on_this:
            self.cost.unknown.append((each, f"its cost changes {_by(each)}in "
                                      f"battle {reason}".rstrip()))
        elif kind in COST_CHANGE and not on_this:
            # Cards the effect names, or every card a unit holds: their
            # cost cut is AP gained (plan D68).
            gain = -amount if amount is not None else None
            self.ap.add(gain, plain, f"{_say(gain)}AP: other cards' cost cut "
                        f"{reason}".rstrip())


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
    # The user's own figures stand over the read ones, "?" parts and all.
    for key, figure in (("cost", cost), ("draw", reader.draw), ("ap", reader.ap)):
        if key in held.overrides:
            figure.value, figure.unknown = int(held.overrides[key]), []
    turns = held.overrides.get("turns", turns)
    return Played(card=card_id, name=base["name"] or held.card, cost=cost,
                  draw=reader.draw, ap=reader.ap,
                  talents=tuple(dict.fromkeys(talents)), turns=turns,
                  printed_cost=printed, opener=OPENER in talents,
                  notes=reader.notes)


# -------------------- a deck's turn and the team's --------------------

@dataclass
class Sums:
    """A list of cards' totals for a turn: how many need drawing, and
    their cost, draw and AP gain. A figure's "?" parts count as 0."""

    cards: int = 0
    cost: int = 0
    draw: int = 0
    ap: int = 0
    # Whether some figure in the list is the battle's (shows as "+?").
    unknown: bool = False

    def add(self, played):
        self.cards += 1 if played.needs_draw else 0
        self.cost += played.cost.value
        self.draw += played.draw.value
        self.ap += played.ap.value
        self.unknown = self.unknown or bool(
            played.cost.unknown or played.draw.unknown or played.ap.unknown)

    @property
    def net_draw(self):
        """What the list adds to a turn's draw: its draws less the cards
        that need drawing."""
        return self.draw - self.cards

    @property
    def net_ap(self):
        return self.ap - self.cost


@dataclass
class DeckTurns:
    """One deck's cards as they play, and its lists' totals."""

    deck: object
    # (DeckCard, Played) for every card in the deck the client knows.
    played: list = field(default_factory=list)
    # The cards they make in battle (`created.CreatedCard`), hidden and
    # idle ones too.
    created: list = field(default_factory=list)
    # Every card each list counts, the deck's and those made, a made
    # card once per copy a turn.
    regular_cards: list = field(default_factory=list)
    setup_cards: list = field(default_factory=list)
    regular: Sums = field(default_factory=Sums)
    setup: Sums = field(default_factory=Sums)
    # The user's corrections a turn (plan D22), summed.
    draw_adjustment: int = 0
    ap_adjustment: int = 0
    # Cards the catalogue lacks, left out of every sum.
    unknown_cards: list = field(default_factory=list)

    @property
    def net_draw(self):
        """What the deck adds to the team's draw a regular turn (plan
        D71): the team's surplus is the turn's draw plus every deck's."""
        return self.regular.net_draw + self.draw_adjustment

    @property
    def net_ap(self):
        return self.regular.net_ap + self.ap_adjustment


def deck_turns(deck, catalogue):
    """`deck` as it plays, a `DeckTurns`: its cards and those they make
    in battle, each in its list."""
    # NOT at the top: `created` imports this module.
    from .created import created_cards
    out = DeckTurns(deck=deck)
    for held in deck.present():
        played_card = played(held, catalogue)
        if played_card is None:
            out.unknown_cards.append(held.card)
            continue
        out.played.append((held, played_card))
        listed = {REGULAR: out.regular_cards, SETUP: out.setup_cards}
        if played_card.turns in listed:
            listed[played_card.turns].append(played_card)
        for made in created_cards(held, played_card, catalogue):
            out.created.append(made)
            if made.hidden or made.idle or made.turns not in listed:
                continue
            copy = replace(made.played, needs_draw=made.needs_draw,
                           notes=made.played.notes + made.notes)
            listed[made.turns].extend([copy] * made.copies)
    for card in out.regular_cards:
        out.regular.add(card)
    for card in out.setup_cards:
        out.setup.add(card)
    for adjustment in deck.adjustments:
        out.draw_adjustment += adjustment.draw
        out.ap_adjustment += adjustment.ap
    return out


@dataclass
class SetupTurn:
    """One turn of setup: what it plays and what it leaves over."""

    setup: list = field(default_factory=list)
    # The regular cards it plays besides, for what they gain.
    regular: list = field(default_factory=list)
    draw_left: int = 0
    ap_left: int = 0


@dataclass
class SetupPlan:
    """How the setup cards get played (plan D72)."""

    turns: list = field(default_factory=list)
    # Setup cards no turn can afford.
    stuck: list = field(default_factory=list)


# More trade cards than this and the plan tries the best gainers only:
# every combination of the rest would double the search per card.
MAX_TRADES = 12


def plan_setup(setup, regular, draw=5, energy=3, openers=(), bonus_draw=0,
               bonus_ap=0):
    """Play the setup cards turn after turn, assuming the draw is
    perfect (plan D72): each turn starts with `draw` cards in hand and
    `energy` AP, plus the decks' own corrections (`bonus_draw`,
    `bonus_ap`); every regular card that gains without costing is
    played; of those that trade one for the other, the mix that lets
    the most setup cards be played is chosen, ties going to what leaves
    the most over; then the setup cards that fit, those giving the most
    first. `setup` and `regular` are `Played`s; `openers` are the
    regular Opener cards, which proc at the start of battle for AP, as
    an Opener setup card does (plan D18). A `SetupPlan`."""
    def nets(card):
        return (card.draw.value - (1 if card.needs_draw else 0),
                card.ap.value - card.cost.value)

    free = [card for card in regular
            if min(nets(card)) >= 0 and max(nets(card)) > 0]
    trades = [card for card in regular if max(nets(card)) > 0 > min(nets(card))]
    trades = sorted(trades, key=lambda c: -max(nets(c)))[:MAX_TRADES]
    at_start = [card for card in setup if card.opener]
    waiting = sorted((card for card in setup if not card.opener),
                     key=lambda c: -sum(nets(c)))
    plan = SetupPlan()
    first = True
    while waiting or (first and at_start):
        hand, ap = draw + bonus_draw, energy + bonus_ap
        if first:
            # Proc at the start of battle: AP spent, no card drawn.
            for card in list(at_start) + list(openers):
                ap += card.ap.value - card.cost.value
                hand += card.draw.value
        for card in free:
            d, a = nets(card)
            hand, ap = hand + d, ap + a
        best = None
        for mask in range(1 << len(trades)):
            chosen = [card for i, card in enumerate(trades) if mask >> i & 1]
            h, a = hand, ap
            for card in chosen:
                d, e = nets(card)
                h, a = h + d, a + e
            if h < 0 or a < 0:
                continue
            played_setup = []
            for card in waiting:
                d, e = nets(card)
                if h + d >= 0 and a + e >= 0:
                    played_setup.append(card)
                    h, a = h + d, a + e
            score = (len(played_setup), h + a)
            if best is None or score > best[0]:
                best = (score, chosen, played_setup, h, a)
        if best is None or (waiting and not best[2] and not (first and at_start)):
            plan.stuck = waiting
            break
        _score, chosen, played_setup, h, a = best
        plan.turns.append(SetupTurn(setup=(at_start if first else []) + played_setup,
                                    regular=free + chosen, draw_left=h, ap_left=a))
        waiting = [card for card in waiting if card not in played_setup]
        first = False
    return plan


@dataclass
class TeamTurns:
    """The team's turn: its decks', the surpluses and the setup plan."""

    decks: list = field(default_factory=list)
    draw_surplus: int = 0
    ap_surplus: int = 0
    # Whether some figure in the regular turns is the battle's.
    unknown: bool = False
    setup: SetupPlan = field(default_factory=SetupPlan)


def team_turns(team, catalogue):
    """`team` as it plays, a `TeamTurns`: a regular turn's draw and AP
    surplus (plan 3.1), the turn's own draw and AP plus each deck's
    nets, and how its setup cards get played."""
    draw = catalogue.constants.get("draw", 5)
    energy = catalogue.constants.get("energy", 3)
    out = TeamTurns(decks=[deck_turns(deck, catalogue) for deck in team.decks])
    out.draw_surplus = draw + sum(d.net_draw for d in out.decks)
    out.ap_surplus = energy + sum(d.net_ap for d in out.decks)
    out.unknown = any(d.regular.unknown for d in out.decks)
    regular = [p for d in out.decks for p in d.regular_cards]
    setup = [p for d in out.decks for p in d.setup_cards]
    out.setup = plan_setup(setup, regular, draw, energy,
                           openers=[p for p in regular if p.opener],
                           bonus_draw=sum(d.draw_adjustment for d in out.decks),
                           bonus_ap=sum(d.ap_adjustment for d in out.decks))
    return out
