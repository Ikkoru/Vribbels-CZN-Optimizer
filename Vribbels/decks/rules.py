"""What a deck weighs, and the deck-building rules it breaks.

`weight` prices a deck the way the game does. Every figure is a
`savedata_point_define` row read through the catalogue, so a patch that
reprices one moves the program with it; which row prices what is the
program's own reading, held against every captured Save Data's recorded
weight by `checks/check_deck_rules.py` (docs/decks.md, *Deck points*).

`warnings` lists the rules a deck breaks: the cap, who may hold a card
or take an Epiphany, the per-deck limits, and a partner whose passive
needs another class (docs/decks.md, *Deck-building rules*). They warn
and never block: a deck the game accepted under rules since changed
still loads.
"""

from collections import Counter
from dataclasses import dataclass, field

from .model import desire_of

# The figures `savedata_point_define` holds are tens of the points the
# game shows.
POINT_UNIT = 10
# The most a deck may weigh, in the client's unit: the 180 points the
# game's help gives for editing a Save Data (`tt_pg@desc@savedata@020`).
CAP = 18

# Card kinds the Neutral row prices: Neutral cards, and the Event
# Neutral cards an encounter gives.
NEUTRAL_SORTS = frozenset({"SORT_NEUTRAL", "SORT_ETC"})
MONSTER_SORT = "SORT_MONSTER_UNIQUE"
# Card kinds no row prices that cost nothing, as Save Data holding them
# confirm: a Combatant's own, season 4's Desire, season 5's Memory. Any
# other kind with no `cd_get_<sort>` row is free by assumption, and
# `Weight.assumed` says so.
FREE_SORTS = frozenset({"SORT_START", "SORT_UNIQUE", "SORT_DESIRE",
                        "SORT_MEMORY"})
# The preset cards whose deletion is charged: the three Basic cards and
# the preset Signature card. Deleting another Signature card is free.
PRESET_CARDS = ("srt1", "srt2", "srt3", "srt4")

# Per-deck limits the game's help states in words (`@015`, `@016`).
MAX_COPIES = 3
MAX_REMOVALS = 5
# The card kinds a deck holds one of at most, and the game's words.
ONE_PER_DECK = {"SORT_EIDOLON": "Persona", "SORT_DESIRE": "Desire",
                "SORT_MEMORY": "Memory"}
# "Only 1 of each Unique card can be included in the Deck."
UNIQUE = "TALENT_ORIGIN"
# Keywords that forbid a duplicate of their card.
NO_COPY_TALENTS = frozenset({"TALENT_MEMORY", "TALENT_MEMORY_SHARD"})


@dataclass
class Weight:
    """A deck's weight, in the client's unit, and what makes it up."""

    total: int = 0
    # (what, id, figure), one per charge that is not free. `what` is
    # "delete" (a preset card gone), "add" (a card not the Combatant's
    # own, every copy too), "copy" (the surcharge on a copy, by its
    # number), "divine", "convert", "removal" (the surcharge on a
    # removal, by its number), "hammer" or "buff".
    parts: list = field(default_factory=list)
    # The cards priced as free only because nothing prices their kind:
    # a new season's, or one the client's tables lack.
    assumed: list = field(default_factory=list)

    @property
    def points(self):
        """The total as the game shows it."""
        return self.total * POINT_UNIT


def _by_count(figures, count):
    """What each of `count` things costs where the i-th costs
    `figures[i]` and the last figure stands for every one past the
    list: [0, 0, 4] would make two free, then 4 each."""
    if not isinstance(figures, list):
        figures = [figures]
    if not figures:
        return [0] * count
    return [figures[min(i, len(figures) - 1)] for i in range(count)]


def add_cost(card, catalogue):
    """What putting a card that is not the Combatant's own into a deck
    costs, and whether that is assumed: (figure, assumed). `card` is the
    catalogue's entry, {} for one it lacks."""
    sort = card.get("sort", "")
    if sort in NEUTRAL_SORTS:
        row = "cd_get_job"
    elif sort == MONSTER_SORT:
        rarity = card.get("rarity", "").replace("RARITY_", "").lower()
        row = f"cd_get_sort_monster_{rarity}"
    else:
        row = "cd_get_" + sort.replace("SORT_", "").lower()
    if row in catalogue.points:
        return catalogue.point(row), False
    return 0, sort not in FREE_SORTS


def weight(deck, catalogue):
    """What `deck` weighs by the client's figures, as a `Weight`."""
    out = Weight()

    def charge(what, held_id, figure):
        if figure:
            out.parts.append((what, held_id, figure))
            out.total += figure

    present = deck.present()
    copies = []
    for held in present:
        if held.divine:
            charge("divine", held.card, catalogue.point("god_r_spark"))
        if held.converted:
            charge("convert", held.card,
                   catalogue.point("cd_transform_default_point"))
        if held.copy:
            copies.append(held.card)
        if held.own:
            continue
        figure, assumed = add_cost(catalogue.card(held.card) or {}, catalogue)
        charge("add", held.card, figure)
        if assumed:
            out.assumed.append(held.card)
    for card_id, figure in zip(copies, _by_count(
            catalogue.point("cd_copy_revise_by_count", []), len(copies))):
        charge("copy", card_id, figure)

    held_ids = {held.card for held in present}
    for kind in PRESET_CARDS:
        card_id = f"c_{deck.combatant}_{kind}"
        if card_id not in held_ids:
            charge("delete", card_id, catalogue.point("cd_remove_start"))
    # No Save Data shows which removals the removal surcharge reads;
    # these are the ones MAX_REMOVALS counts.
    removals = own_removals(deck)
    for card_id, figure in zip(removals, _by_count(
            catalogue.point("cd_remove_revise_by_count", []), len(removals))):
        charge("removal", card_id, figure)

    for piece in deck.equipment:
        if piece.blessings:
            charge("hammer", piece.relic, catalogue.point("cd_relic_hammer"))
        for buff in piece.buffs:
            kind = (catalogue.buffs.get(buff) or {}).get("type", "")
            charge("buff", buff, catalogue.point(f"relic_reinforce_{kind.lower()}"))
    return out


def own_removals(deck):
    """The deck's removals that count against MAX_REMOVALS: the
    Combatant's own cards in its removal record. A Desire card's never
    counts (help `@022`), nor a removed card the run had added."""
    return [card_id for card_id in deck.removed if card_id.startswith("c_")]


# -------------------- the deck-building rules --------------------

@dataclass
class DeckWarning:
    """One rule a deck breaks. `rule` is "unknown", "cap", "class",
    "neutral", "divine", "persona", "desire", "one_per_deck", "copies",
    "no_copy", "unique", "removals" or "partner"."""

    rule: str
    text: str
    # The card's index in `Deck.cards`, where it is about one card.
    card: int | None = None


def _misfits(rule, card, klass, costs, tags=True):
    """The conditions of `rule`, an Epiphany or a Persona effect, that
    `card` fails, in words; [] where it fits at one of `costs`. With no
    class known (an unknown Combatant, already warned of), the class
    condition is not held."""
    talents = set(card.get("talents", ()))
    held_tags = set(card.get("tags", ()))

    def at(cost):
        out = []
        if rule.get("classes") and klass and klass not in rule["classes"]:
            out.append("class")
        if rule.get("categories") and card.get("category") not in rule["categories"]:
            out.append("card type")
        low, high = rule.get("cost_min", -1), rule.get("cost_max", -1)
        if (low >= 0 and cost < low) or (high >= 0 and cost > high):
            out.append("cost")
        include = set(rule.get("include_talents", ()))
        if (include and not include & talents) \
                or talents & set(rule.get("exclude_talents", ())):
            out.append("keywords")
        need = set(rule.get("tags", ()))
        if tags and ((need and not need & held_tags)
                     or held_tags & set(rule.get("exclude_tags", ()))):
            out.append("tags")
        return out

    tried = [at(cost) for cost in costs]
    return [] if any(not misfit for misfit in tried) else tried[0]


def warnings(deck, catalogue, owned=None):
    """Every rule `deck` breaks, as `DeckWarning`s; [] for a deck the
    game would accept. `owned` holds the owned Combatants' captured
    state, whose partner stands where the deck names none (plan D8)."""
    out = []

    def warn(rule, text, index=None):
        out.append(DeckWarning(rule, text, index))

    combatant = catalogue.combatant(deck.combatant)
    klass = combatant.get("class") if combatant else None
    if combatant is None:
        warn("unknown", f"Combatant {deck.combatant} is not in the game "
                        f"client's tables.")
    weighs = weight(deck, catalogue)
    if weighs.total > CAP:
        warn("cap", f"the deck weighs {weighs.points} points, over the "
                    f"{CAP * POINT_UNIT}-point cap.")

    kinds = Counter()
    uniques = Counter()
    copies = 0
    for index, held in enumerate(deck.cards):
        if held.removed:
            continue
        card = catalogue.card(held.card)
        if card is None:
            warn("unknown", f"card {held.card} is not in the game client's "
                            f"tables.", index)
            continue
        name = card.get("name") or held.card
        version = card
        if held.version:
            version = catalogue.card(catalogue.version(held.card, held.version))
            if version is None:
                warn("unknown", f"{name} has no Signature Epiphany "
                                f"{held.version} in the game client's tables.",
                     index)
                version = card
        if klass and card["classes"] and klass not in card["classes"]:
            warn("class", f"{name} may not be held by a "
                          f"{catalogue.class_name(klass)} Combatant.", index)
        if held.neutral:
            rule = catalogue.epiphanies.get(held.neutral)
            if rule is None:
                warn("unknown", f"{name}'s Neutral Epiphany {held.neutral} is "
                                f"not in the game client's tables.", index)
            else:
                misfit = _misfits(rule, card, klass,
                                  card["replace_cost"] or [card["cost"]])
                if misfit:
                    warn("neutral", f"{name} may not take Neutral Epiphany "
                                    f"{held.neutral}: its "
                                    f"{', '.join(misfit)}.", index)
        if held.divine:
            rule = catalogue.epiphanies.get(held.divine)
            if rule is None:
                warn("unknown", f"{name}'s Divine Epiphany {held.divine} is "
                                f"not in the game client's tables.", index)
            else:
                misfit = _misfits(rule, version, klass, [version["cost"]])
                if misfit:
                    warn("divine", f"{name} may not take Divine Epiphany "
                                   f"{held.divine}: its "
                                   f"{', '.join(misfit)}.", index)
        if held.persona:
            slots = catalogue.persona.get("slots", {}).get(held.card) or {}
            if len(held.persona) > slots.get("count", 0):
                warn("persona", f"{name} holds {len(held.persona)} Persona "
                                f"effects in {slots.get('count', 0)} slots.",
                     index)
            for effect_id in held.persona:
                effect = catalogue.persona.get("effects", {}).get(effect_id)
                if effect is None:
                    warn("unknown", f"{name}'s Persona effect {effect_id} is "
                                    f"not in the game client's tables.", index)
                    continue
                # A Persona effect's own tags are no condition: Save
                # Data hold effects that share a tag with their card.
                misfit = _misfits(effect, card, klass, [card["cost"]], tags=False)
                if misfit:
                    warn("persona", f"{name} may not take Persona effect "
                                    f"{effect_id}: its {', '.join(misfit)}.",
                         index)
        desire = desire_of(held.card)
        if desire and sum(held.desire.values()) != desire[1]:
            warn("desire", f"{name}'s Desire points add up to "
                           f"{sum(held.desire.values())}, not its level, "
                           f"{desire[1]}.", index)
        if card["sort"] in ONE_PER_DECK:
            kinds[card["sort"]] += 1
            if kinds[card["sort"]] == 2:
                warn("one_per_deck", f"{name} is the deck's second "
                                     f"{ONE_PER_DECK[card['sort']]} card.",
                     index)
        # Unique counts by the base card, read off each copy's own
        # version: two versions of one card may not both be in a deck
        # when both are Unique, and one that is not does not count.
        if UNIQUE in version.get("talents", ()):
            uniques[held.card] += 1
            if uniques[held.card] == 2:
                warn("unique", f"{name} is Unique and in the deck twice.", index)
        if held.copy:
            copies += 1
            if NO_COPY_TALENTS & set(card["talents"]):
                warn("no_copy", f"{name} may not be Duplicated.", index)
    if copies > MAX_COPIES:
        warn("copies", f"the deck holds {copies} duplicates; at most "
                       f"{MAX_COPIES} are allowed.")
    removals = own_removals(deck)
    if len(removals) > MAX_REMOVALS:
        warn("removals", f"the deck had {len(removals)} cards removed; at "
                         f"most {MAX_REMOVALS} are allowed.")

    for piece in deck.equipment:
        if piece.relic not in catalogue.equipment:
            warn("unknown", f"Equipment {piece.relic} is not in the game "
                            f"client's tables.")
        for buff in piece.buffs:
            if buff not in catalogue.buffs:
                warn("unknown", f"Equipment Buff {buff} is not in the game "
                                f"client's tables.")
        for blessing in piece.blessings:
            if blessing not in catalogue.equipment:
                warn("unknown", f"Equipment {piece.relic}'s hammer blessing, "
                                f"{blessing}, is not in the game client's "
                                f"tables.")
    if deck.mutation and deck.mutation not in catalogue.mutations:
        warn("unknown", f"Mutation {deck.mutation} is not in the game "
                        f"client's tables.")
    partner_id = deck.state(owned).partner
    partner = catalogue.partner(partner_id)
    if partner_id and partner is None:
        warn("unknown", f"partner {partner_id} is not in the game client's "
                        f"tables.")
    elif partner and klass and partner["class"] and partner["class"] != klass:
        warn("partner", f"{partner['name']}'s passive works only with a "
                        f"{catalogue.class_name(partner['class'])} Combatant.")
    return out
