"""The cards a deck's cards create in battle, and which list each counts
in (docs/decks.md, *Created cards*; plan D14-D16, D43, D44, D51).

A creation is found on a card's effects, or on a status the card puts
on: an Upgrade's lasting effect is a status, and a status can put on
further ones. Equipment, the Mutation and a Combatant's progress hold
statuses for the battle that make cards too (`status_cards`). Where a
created card goes, whether it stays or leaves after use, and whether
its creator makes it once or every time, place it in the maintainer's
table (plan D14):

    created card     once, to hand     once, to deck    every time
    leaves           setup, no draw    setup            regular (to hand:
                                                         no draw)
    stays            regular           regular          regular, and the
                                                         deck grows (D16)
"""

from dataclasses import dataclass, field

from .catalogue import _list, chained
from .exceptions import EXCEPTIONS
from .model import DeckCard
from .turns import (AT_START, BATTLE, EPHEMERAL, EXHAUST, PLAY, REGULAR, REMOVE,
                    SETUP, UPGRADE, Figure, _keyword, _trigger_words, available,
                    by_this_effect, fires, played)

CARD_GETS = ("SKILL_EFF_CARD_GET", "SKILL_EFF_CARD_GET_IGNORE_COND",
             "SKILL_EFF_CARD_GET_USER", "SKILL_EFF_CARD_GET_REPLACED")
CHOICE = "SKILL_EFF_CARD_OPTION_SELECT"
TALENT_ADD = "SKILL_EFF_CARD_TALENT_ADD"
NOT_SHUFFLE = "SKILL_EFF_CARD_NOT_SHUFFLE"
COST_CHANGES = ("SKILL_EFF_CARD_COST_CHANGE", "SKILL_EFF_CARD_COST_CHANGE_PASSIVE")
# Effects right after a creation aimed here work on the card just made.
JUST_MADE = "CARD_SET_BEFORE_EFF_TARGET"
POOL = "CARD_SET_REWARD_ID"
HAND = "CARD_PLACE_HAND"
# A status lasting the battle makes its creations every time it fires.
LASTING = ("TERM_BATTLE", "TERM_PASSIVE", "TERM_PASSIVE_WHOLE")
PLAIN = "VALUE_COMMON"
SUBTRACT = ("MATHSIGN_SUBTRACT", "MATHSIGN_SUBTRACT_MIN_0")
# How deep created cards' own creations are followed.
CHAIN = 2


@dataclass
class Creation:
    """One way a card makes cards."""

    effect: str
    cards: list
    # One of `cards` is made, chosen or at random (plan D44); from a
    # reward pool where `pool`.
    pick: bool = False
    pool: bool = False
    # How many a creation makes; None where the battle decides.
    count: int | None = 1
    to_hand: bool = True
    # Each play or trigger, as against once (plan D14).
    every_time: bool = False
    # The keywords and cost change its creator gives the card (plan D51).
    talents: tuple = ()
    cost_change: int = 0
    # When the triggers on the way to it fire (`turns.fires`): PLAY for
    # none, AT_START, EACH_TURN or BATTLE; and a BATTLE trigger's words.
    when: str = PLAY
    trigger: str = ""


@dataclass
class CreatedCard:
    """A card a deck's card makes, as it counts."""

    creation: Creation
    by: str
    card: str
    played: object
    # It leaves after use: an Upgrade, any Exhaust or Remove, or a card
    # that stays in the Graveyard on Shuffle (plan D51).
    gone: bool = False
    turns: str = REGULAR
    # It goes to hand, so it needs no draw (plan D15).
    needs_draw: bool = True
    # How many a turn counts: a creation's count, made once a turn.
    copies: int = 1
    # Made every time its maker plays or its trigger fires, as against
    # once; and made every time and staying: the deck grows by `copies`
    # a turn (plan D16).
    every_time: bool = False
    grows: bool = False
    # It changes no sum (plan D43): to hand, free, gone by the turn's
    # end, with no draw, AP or creation of its own.
    idle: bool = False
    # Left out of the sums unless the user shows it (plan D50), or for
    # good (an exception's "ignore").
    hidden: bool = False
    notes: list = field(default_factory=list)


def _number(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _what_follows(effect_ids, index, catalogue):
    """The keywords and cost change the effects after a creation at
    `index` give the card just made, up to the next creation."""
    talents, change = [], 0
    for later in effect_ids[index + 1:]:
        effect = catalogue.effects.get(later, {})
        if effect.get("eff") in CARD_GETS:
            break
        if effect.get("target_card_set") != JUST_MADE:
            continue
        if effect.get("eff") == TALENT_ADD:
            talents += [t for t in _list(effect.get("eff_opt")) if t.startswith("TALENT_")]
        for status_id in _list(effect.get("link_cs_id")):
            for inner in _list(catalogue.statuses.get(status_id, {}).get("link_skill_eff_id")):
                held = catalogue.effects.get(inner, {})
                if held.get("eff") in COST_CHANGES:
                    amount = _number(held.get("eff_value"))
                    change += -amount if held.get("eff_value_math_sign") in SUBTRACT else amount
    return tuple(talents), change


def creations(effect_ids, catalogue, once_by_kind):
    """Every `Creation` the effects reach, directly or through the
    statuses they put on. `once_by_kind` is whether the card making
    them leaves after its play (an Upgrade or an Exhaust card), so what
    it makes on play it makes once."""
    out = []
    seen = set()

    def walk(ids, via_lasting, triggered, when, trigger):
        for index, effect_id in enumerate(ids):
            if effect_id in seen:
                continue
            seen.add(effect_id)
            effect = catalogue.effects.get(effect_id)
            if effect is None:
                continue
            here, words = when, trigger
            if effect.get("operation") == "OPERATION_TRIGGER":
                condition = effect.get("eff_link_condition_id")
                timing = fires(condition, catalogue) if condition else BATTLE
                if when not in (PLAY, timing):
                    timing = BATTLE
                if timing == BATTLE and here != BATTLE:
                    words = _trigger_words(condition, effect_id, catalogue)
                here = timing
            fired = triggered or effect.get("operation") == "OPERATION_TRIGGER"
            if effect.get("eff") in CARD_GETS:
                made = _list(effect.get("target_card_set_opt_multiple_link"))
                talents, change = _what_follows(ids, index, catalogue)
                plain = effect.get("eff_value_type_1", PLAIN) == PLAIN
                out.append(Creation(
                    effect=effect_id, cards=made,
                    pick=len(made) > 1 and _number(effect.get("eff_card_target_count"), -1) > 0,
                    pool=effect.get("target_card_set") == POOL,
                    count=_number(effect.get("eff_value"), 1) if plain else None,
                    to_hand=effect.get("eff_card_place") == HAND,
                    every_time=fired or via_lasting or not once_by_kind,
                    talents=talents, cost_change=change, when=here, trigger=words))
            if effect.get("eff") == CHOICE:
                # A choice's options are cards whose effects are what it
                # does; the first stands for it (plan D44).
                options = _list(effect.get("eff_opt_multiple_link"))
                option = catalogue.card(options[0]) if options else None
                if option is not None:
                    walk(option["effects"], via_lasting, fired, here, words)
            for status_id in _list(effect.get("link_cs_id")):
                status = catalogue.statuses.get(status_id, {})
                lasting = status.get("term_type_1") in LASTING
                walk(_list(status.get("link_skill_eff_id")), via_lasting or lasting, fired,
                     here, words)
            # Its follow-ups: those met by this effect's own work, then
            # those the battle decides. Each group is walked together so
            # the keywords a creation's follow-up gives (`_what_follows`)
            # reach the card it makes.
            met, gated = [], []
            for condition, follow in chained(effect):
                waits = condition and not by_this_effect(condition, catalogue) \
                    and not available(condition, catalogue)
                (gated if waits else met).append((condition, follow))
            walk([follow for _condition, follow in met], via_lasting, fired, here, words)
            if gated:
                walk([follow for _condition, follow in gated], via_lasting, True, BATTLE,
                     words or _trigger_words(*gated[0], catalogue))

    walk(list(effect_ids), False, False, PLAY, "")
    return out


def _gone(card_id, talents, catalogue):
    """Whether a card leaves after use: an Upgrade, any Exhaust or
    Remove keyword, or a status of its own that keeps it in the
    Graveyard on Shuffle."""
    card = catalogue.card(card_id) or {}
    if card.get("category") == UPGRADE or _keyword(talents, EXHAUST) \
            or _keyword(talents, REMOVE):
        return True
    stack, seen = list(card.get("effects", ())), set()
    while stack:
        effect_id = stack.pop()
        if effect_id in seen:
            continue
        seen.add(effect_id)
        effect = catalogue.effects.get(effect_id, {})
        if effect.get("eff") == NOT_SHUFFLE:
            return True
        for status_id in _list(effect.get("link_cs_id")):
            stack.extend(_list(catalogue.statuses.get(status_id, {}).get("link_skill_eff_id")))
    return False


def _place(creation, by, by_name, catalogue, every_time, upgrades, notes=(), depth=0):
    """The `CreatedCard` one creation makes, placed in its list (plan
    D14), and a step deep what that card makes; [] for a creation of
    no card the catalogue holds. `by` is the maker's id and `by_name`
    its name; `every_time` is whether it makes the card every time
    rather than once. A card the Combatant's progress upgrades is made
    as its upgrade, and the maintainer's exceptions for the card hold
    for its upgrade too."""
    if not creation.cards:
        return []
    base_id = creation.cards[0]
    card_id = upgrades.get(base_id, base_id)
    made = played(DeckCard(card_id), catalogue, upgrades)
    if made is None:
        return []
    notes = list(notes)
    if creation.pick or creation.pool:
        notes.append(f"one of {len(creation.cards)} made"
                     f"{' at random' if creation.pool else ''}: the first, "
                     f"{made.name}, assumed")
    talents = tuple(dict.fromkeys(made.talents + creation.talents))
    if creation.cost_change and not made.cost.unknown:
        made.cost = Figure(max(0, made.cost.value + creation.cost_change))
    exception = EXCEPTIONS.get(card_id) or EXCEPTIONS.get(base_id, {})
    # NOT a repeat of `played`'s: that one knows only the upgrade's id,
    # so misses an upgraded card's base entry, and the maker's cost
    # change comes after it. The practical cost is the final word.
    if "cost" in exception:
        made.cost = Figure(exception["cost"])
    gone = _gone(card_id, talents, catalogue) and not exception.get("cycles")
    if every_time:
        turns = REGULAR
    else:
        turns = SETUP if gone else REGULAR
    needs_draw = not (gone and creation.to_hand)
    idle = (creation.to_hand and made.cost.value == 0 and not made.cost.unknown
            and (gone or EPHEMERAL in talents)
            and not (made.draw.value or made.draw.unknown or made.ap.value
                     or made.ap.unknown)
            and not creations(catalogue.card(card_id)["effects"], catalogue, gone))
    # `played` notes a practical cost's reason already.
    if exception.get("why") and exception["why"] not in made.notes:
        notes.append(exception["why"])
    out = [CreatedCard(
        creation=creation, by=by, card=card_id, played=made,
        gone=gone, turns=turns, needs_draw=needs_draw,
        copies=creation.count if creation.count is not None else 1,
        every_time=every_time, grows=every_time and not gone, idle=idle,
        hidden=bool(exception.get("hidden") or exception.get("ignore")),
        notes=notes + ([] if creation.count is not None
                       else ["how many the battle decides: 1 assumed"]))]
    if depth < CHAIN - 1:
        for chained in created_cards(DeckCard(card_id), made, catalogue, depth + 1,
                                     upgrades):
            chained.notes.append(f"made by {made.name}, which {by_name} makes")
            out.append(chained)
    return out


def created_cards(by, by_played, catalogue, depth=0, upgrades=None):
    """The cards `by` (a `DeckCard`, playing as `by_played`) makes, each
    a `CreatedCard` placed in the setup or regular list. `upgrades` are
    what the Combatant's progress upgrades (`turns.upgrades_of`)."""
    upgrades = upgrades or {}
    effects = list(catalogue.card(by_played.card)["effects"])
    for epiphany_id in (by.neutral, by.divine):
        epiphany = catalogue.epiphanies.get(epiphany_id) if epiphany_id else None
        if epiphany is not None:
            effects += epiphany["effects"]
    for effect_id in by.persona:
        effect = catalogue.persona.get("effects", {}).get(effect_id)
        if effect is not None:
            effects += effect["effects"]
    once_by_kind = by_played.turns == SETUP
    out = []
    for creation in creations(effects, catalogue, once_by_kind):
        out += _place(creation, by_played.card, by_played.name, catalogue,
                      creation.every_time, upgrades, depth=depth)
    return out


def status_cards(by, by_name, statuses, catalogue, upgrades=None):
    """The cards statuses held for the battle make: an Equipment
    piece's, a Buff's, the Mutation's, a Potential node's, an Ego
    Manifestation level's (`by` is its id, `by_name` its name). A card
    made when the status is put on, or at the start of battle, is made
    once; on any other trigger, once a turn, as a maker that is not a
    card counts (plan D14)."""
    upgrades = upgrades or {}
    effects = [effect for status in statuses
               for effect in _list(catalogue.statuses.get(status, {}).get("link_skill_eff_id"))]
    out = []
    for creation in creations(effects, catalogue, False):
        once = creation.when in (PLAY, AT_START)
        if once:
            note = "made at the start of battle"
        elif creation.when == BATTLE:
            note = f"made {creation.trigger}: counted once a turn"
        else:
            note = "made at the start of every turn"
        out += _place(creation, by, by_name, catalogue, not once, upgrades, notes=[note])
    return out
