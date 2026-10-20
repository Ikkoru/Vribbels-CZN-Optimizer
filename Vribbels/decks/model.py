"""A deck and a team, as the Deck Builder holds them: what a Save Data
or a deck built in the program says, with nothing the client already
knows copied in. `catalogue.Catalogue` answers for the cards; `rules`
weighs a deck and says what it breaks.

A card is held by its BASE id (`c_1004_srt4`, `card_ne_00001`), the
way the wire sends it, with what was done to it beside the id: its
Signature Epiphany as a number, its Neutral and Divine Epiphanies,
whether it is a duplicate, and the season mechanics' choices. A Memory
card (season 5) and a Desire card's level (season 4) are the exception:
the client gives each grade, variant and level an id of its own, and
that id is held.
"""

import re
from dataclasses import dataclass, field

# The keywords a run adds, as the wire numbers them; the client's tables
# never use these numbers (docs/decks.md, *The wire*).
WIRE_TALENTS = {32: "TALENT_REPLICATION", 48: "TALENT_EXPLORATION",
                49: "TALENT_CONTROL", 50: "TALENT_POSSESSION",
                51: "TALENT_SURVIVAL"}
# Season 4's Desire keywords, the wire's numbers for its points, in the
# order a Desire card's id numbers them.
DESIRE_TALENTS = (48, 49, 50, 51)
# A Desire card's id: `card_ds04_des_<keyword><card><level>`, its own
# keyword 1 to 4 and its level 1 to 3.
DESIRE_ID = re.compile(r"^card_ds04_des_([1-4])\d{3}(\d)$")


def desire_of(card_id):
    """A Desire card's own keyword, as the wire numbers it, and its
    level: (keyword, level). None for any other card."""
    found = DESIRE_ID.match(card_id or "")
    if not found:
        return None
    return DESIRE_TALENTS[int(found.group(1)) - 1], int(found.group(2))


@dataclass
class DeckCard:
    """One card in a deck."""

    card: str
    # The Signature Epiphany, 1 to 5; 0 the card as it starts.
    version: int = 0
    # A Neutral Epiphany's id (`r_spark@r_spark`, no god), and a Divine
    # one's (a god's).
    neutral: str | None = None
    divine: str | None = None
    # A duplicate: a further copy of a card already in the deck.
    copy: bool = False
    # Listed with the cards yet out of the deck (`remove_by_count`),
    # such as the card a Conversion replaced. Not in the deck's removal
    # record, `Deck.removed`.
    removed: bool = False
    # A Persona's effects (season 3), one per slot.
    persona: tuple = ()
    # A Desire card's points per keyword (season 4), the wire's numbers.
    desire: dict = field(default_factory=dict)
    # Keywords the run added, as the wire numbers them.
    added_talents: tuple = ()
    # A Conversion (the game's "Convert") made this card
    # (`is_transform_card`), or replaced it (`is_erased_transform_card`).
    # `conversion` is the wire's number for it (`transform_card_id`),
    # which is no card's id.
    converted: bool = False
    converted_away: bool = False
    conversion: int | None = None

    @property
    def own(self):
        """Whether it is one of the Combatant's own cards."""
        return self.card.startswith("c_")

    def held_id(self, catalogue):
        """The card's id as it plays: its Signature Epiphany version's
        where it has one the client knows, else its own."""
        if self.version:
            return catalogue.version(self.card, self.version) or self.card
        return self.card


@dataclass
class Equipment:
    """One Equipment piece."""

    relic: str
    stars: int = 1
    # Equipment Buffs (`relic_reinforce`) and season 2's hammer
    # blessings: another piece's effect added.
    buffs: tuple = ()
    blessings: tuple = ()


@dataclass
class Deck:
    """One Combatant's deck."""

    combatant: int
    cards: list = field(default_factory=list)
    # The cards deleted, by id, as the Save Data lists them: the record
    # the five-removal rule counts.
    removed: list = field(default_factory=list)
    equipment: list = field(default_factory=list)
    mutation: str | None = None
    name: str = ""
    note: str = ""
    # Where it came from: "save data", "built"; and its id there.
    source: str = "built"
    source_id: str = ""
    chaos: str | None = None
    # What the game recorded it weighing, and the run's cap, in the
    # client's unit (tens of the points the game shows).
    recorded_weight: int | None = None
    recorded_cap: int | None = None
    created_at: int | None = None

    def present(self):
        """The cards that are in it: every card but those listed as out."""
        return [card for card in self.cards if not card.removed]


@dataclass
class Team:
    """Three Combatants' decks, played together."""

    decks: list = field(default_factory=list)
    name: str = ""
    note: str = ""
