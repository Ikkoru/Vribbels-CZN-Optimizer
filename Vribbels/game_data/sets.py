"""Memory Fragment set definitions.

Entry shape
===========
::

    SETS[set_id] = {
      "name":     "Black Wing",
      "pieces":   2,               # 2 or 4, pieces needed to complete
      "bonus":    "+12% Attack",   # optional: the maintainer's own short
                                   # wording, shown in the UI (`set_bonus`)
      "type":     "unconditional", # or "conditional"
      "stat":     "ATK%",          # see the vocabulary below
      "value":    12,              # magnitude, in that stat's own units
      "elements": ["Void"],        # optional, cosmetic: the Set
                                   # Configuration rows colour by it.
                                   # No formula reads it.
    }

**A set with several bonuses** lists them as `effects` in place of
`stat` and `value`: ``"effects": [{"stat": "DMG multi", "value": 30},
{"stat": "Crit DMG", "value": 15}]``. Each lands as a set of one bonus
would, all under the set's `type` and, where conditional, its one
effect share. `set_effects` is the one accessor: every formula reads a
set's bonuses through it.

- **`unconditional`** — always active once the set is complete. `stat`
  and `value` say where to add the bonus, typically a Final stat.
- **`conditional`** — triggers only under the in-game condition
  described by `bonus`. The optimizer cannot evaluate that, so it
  applies the bonus weighted by the set's own effect share (the Effect %
  spinbox in Set Configuration, per combatant; absent = 0 = contributes
  nothing, though the set still counts for set-locking).

Full treatment: `docs/game_formulas.md` §5.

The wording
===========

**`bonus` is the maintainer's own shortening** of the game's text,
and the game's text is the fallback: a set without one, or one the
program has no entry for, shows the game client's words
(`game_client.known_set_effects`) until it gets one. `set_bonus` is
the one accessor. `checks/check_set_wordings.py` notes each set still
on the game's words, and where a patch changed a set's text, says
whether it moved only the figures (the wording wants new figures) or
reworded the effect (the wording wants rewriting).

**A set's name is the program's too**, and the game client's names a
set only where there is no entry here (`set_name`): a shortening such
as `Snowflake of OFM` is the maintainer's choice, so nothing holds the
entries to the client's names or figures. What is reported is the
CLIENT changing: `docs/client_tables.py --ship` and `--audit` name each
set whose name, pieces, plain stat or wording a newer client changed
from the copy the program shipped (`client_tables.set_changes`), and
`check_set_wordings` holds the installed client to that copy.

Stat-name vocabulary
====================

**The optimizer consumes ONLY the exact strings below** (mapping:
`SET_STAT_NAME_MAP`, below). Any other value is silently
ignored — no error, no effect — so a typo costs the set its bonus while
leaving set-locking working, which is easy to miss.

These names match neither the program's internal vocabulary nor
`partners.py`: the crit stats are `Crit DMG` / `Crit Rate` here and
`CDmg` / `CRate` everywhere else.

    In-game stat        "stat" value   Internal   Where it lands
    -----------------   ------------   --------   --------------------
    Attack %            "ATK%"         ATK%       inner ATK multiplier, same bucket as a fragment's ATK%
    Defense %           "DEF%"         DEF%       inner DEF multiplier
    Health %            "HP%"          HP%        inner HP multiplier
    Crit DMG (CDMG)     "Crit DMG"     CDmg       flat addition to Final CDmg
    Crit Chance (Crit%) "Crit Rate"    CRate      flat addition to Final CRate
    Damage, multiplied  "DMG multi"    --         Multiplicative_Buffs in the DAMAGE card multiplier
    Damage, added       "DMG add"      --         Additive_Buffs in the DAMAGE card multiplier

**`DMG multi` / `DMG add` have no Final-stat equivalent**, so they are
absent from `SET_STAT_NAME_MAP` and never reach the stat sheet; and they
work on CONDITIONAL sets only — the card-multiplier walk skips
unconditional ones, so an unconditional set carrying either name
contributes nothing at all. Neither touches the shield/heal side.

There is deliberately **no spelling for Extra DMG%, DoT%, Ego or a flat
ATK/DEF/HP bonus**: no set grants one, and `core.compute_build_stats`
has no bucket for them. A set needing one means adding that bucket, not
inventing a string here.
"""

# Set definitions
SETS = {
    6: {
        "name": "Conqueror's Aspect",
        "pieces": 4,
        "bonus": "+35% Crit DMG to 1-cost Cards",
        "type": "conditional",
        "stat": "Crit DMG",
        "value": 35
    },
    7: {
        "name": "Tetra's Authority",
        "pieces": 2,
        "bonus": "+12% Defense",
        "type": "unconditional",
        "stat": "DEF%",
        "value": 12
    },
    8: {
        "name": "Healer's Journey",
        "pieces": 2,
        "bonus": "+12% Max HP",
        "type": "unconditional",
        "stat": "HP%",
        "value": 12
    },
    9: {
        "name": "Black Wing",
        "pieces": 2,
        "bonus": "+12% Attack",
        "type": "unconditional",
        "stat": "ATK%",
        "value": 12
    },
    10: {
        "name": "Seth's Scarab",
        "pieces": 2,
        "bonus": "Increase Basic Card DMG, Shield & Healing by 20%",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 20
    },
    11: {
        "name": "Executioner's Tool",
        "pieces": 2,
        "bonus": "+25% Crit Damage",
        "type": "unconditional",
        "stat": "Crit DMG",
        "value": 25
    },
    12: {
        "name": "Instinctual Growth",
        "pieces": 4,
        "bonus": "Increase Instinct Card DMG by 20% when 3+ Cards in hand",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 20,
        "elements": ["Instinct"]
    },
    15: {
        "name": "Bullet of Order",
        "pieces": 4,
        "bonus": "Increase Order Card DMG by 10% after Attack Card used for 1 turn (max 2 per turn)",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 20,
        "elements": ["Order"]
    },
    16: {
        "name": "Offering of the Void",
        "pieces": 4,
        "bonus": "Increase Void Card DMG by 20% after Exhaust for 1 turn (max 1 per turn)",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 20,
        "elements": ["Void"]
    },
    18: {
        "name": "Spark of Passion",
        "pieces": 4,
        "bonus": "Increase Passion Card DMG by 20% after Upgrade used (max 1)",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 20,
        "elements": ["Passion"]
    },
    19: {
        "name": "Cursed Corpse",
        "pieces": 2,
        "bonus": "Increase DMG by 10% to targets afflicted by Agony",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 10
    },
    20: {
        "name": "Line of Justice",
        "pieces": 4,
        "bonus": "+20% Crit Rate for 2+ cost Cards",
        "type": "conditional",
        "stat": "Crit Rate",
        "value": 20
    },
    22: {
        "name": "Orb of Inhibition",
        "pieces": 4,
        "bonus": "+30% Void Card DMG for Cards with 2 or more Hits",
        "type": "conditional",
        "stat": "DMG add",
        "value": 30,
        "elements": ["Void"]
    },
    23: {
        "name": "Judgment's Flames",
        "pieces": 4,
        "bonus": "+50% Instinct Card DMG to Ravaged targets",
        "type": "conditional",
        "stat": "DMG add",
        "value": 50,
        "elements": ["Instinct"]
    },
    24: {
        "name": "Beast's Yearning",
        "pieces": 4,
        "bonus": "Increase Justice and Order Exhaust Attack Card DMG by 30% (max 5 per turn)",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 30,
        "elements": ["Justice", "Order"]
    },
    25: {
        "name": "Glory's Reign",
        "pieces": 4,
        "bonus": "Increase ally DMG by 5% on Exhaust Skill Card create/use (max 15%)",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 15
    },
    26: {
        "name": "Prelude to a Hero",
        "pieces": 4,
        "bonus": "+15% Crit Rate when a Passion or Void Attack Card of this unit is Discarded for 1 turn (max 15%; max 2 stacks)",
        "type": "conditional",
        "stat": "Crit Rate",
        "value": 15,
        "elements": ["Passion", "Void"]
    },
    27: {
        "name": "Starlight and Dreams",
        "pieces": 4,
        "bonus": "Increase ally Counterattack and Extra Attack DMG by 5% when Shield is gained through an ability (max 25%)",
        "type": "conditional",
        "stat": "DMG multi",
        "value": 25
    },
    28: {
        "name": "Battlefield Evolution",
        "pieces": 4,
        "bonus": "On Extra Attack / Attack Card created in Draw Pile / Draw via Attack Card: +10% Critical Damage (each source max 1 time). When 3 stacks are reached add an additional +5% Critical Damage",
        "type": "conditional",
        "stat": "Crit DMG",
        "value": 35
    },
    29: {
        "name": "Sanguine Thorn",
        "pieces": 4,
        "bonus": "When Fracture via card, +25% Critical Damage for 1 turn (max 25%, max 2 stacks). When 10+ Fractures via cards, +15% Critical Damage to DoTs (max 15%)",
        "type": "conditional",
        "stat": "Crit DMG",
        "value": 40
    },
    30: {
        "name": "Veiled Radiance",
        "pieces": 4,
        "bonus": "When a Justice Attribute card is stacked, +8% Critical Chance to Attack Cards (max 2 stacks)",
        "type": "conditional",
        "stat": "Crit Rate",
        "value": 16,
        "elements": ["Justice"]
    },
    31: {
        "name": "Snowflake of OFM",
        "pieces": 4,
        "bonus": "When Bind card stacked, 1 Powder Snow (1 per Combatant). Increase ally Attack Card DMG by 10% per Powder Snow. If Justice Attribute, increase by additional 5% (max 2 stacks). 2 stacks: ally Justice Attack Cards +15% Critical Damage",
        "type": "conditional",
        # For a Justice wearer: (10% + 5%) a Powder Snow at its 2 stacks,
        # and the 2-stack Critical Damage, which only Justice cards get.
        "effects": [{"stat": "DMG multi", "value": 30},
                    {"stat": "Crit DMG", "value": 15}],
        "elements": ["Justice"]
    },
}


def set_effects(info) -> list:
    """[(stat, value), ...]: a set entry's bonuses, its `effects` where
    it lists them, else its one `stat` and `value`; empty for a set with
    none, such as one only the game client knows."""
    if not isinstance(info, dict):
        return []
    if "effects" in info:
        return [(e.get("stat", ""), e.get("value", 0))
                for e in info.get("effects") or () if isinstance(e, dict)]
    if "stat" in info:
        return [(info.get("stat", ""), info.get("value", 0))]
    return []


def set_name(set_id) -> str:
    """A set's name: the program's own entry's, else the game client's,
    else its number -- which says what to look for to identify it."""
    own = (SETS.get(set_id) or {}).get("name")
    if own:
        return own
    import game_client
    effect = game_client.known_set_effects().get(set_id)
    named = effect[0] if effect else ""
    return named if game_client.NAMING.search(named) else str(set_id)


def set_named(name):
    """The set id `set_name` gives `name`, or None."""
    for set_id, entry in SETS.items():
        if entry.get("name") == name:
            return set_id
    import game_client
    for set_id, effect in game_client.known_set_effects().items():
        if set_id not in SETS and effect[0] == name:
            return set_id
    return int(name) if str(name).isdigit() else None


def set_pieces(set_id):
    """How many pieces complete a set: the program's entry's, else the
    game client's, else None."""
    own = (SETS.get(set_id) or {}).get("pieces")
    if own:
        return own
    import game_client
    effect = game_client.known_set_effects().get(set_id)
    return effect[1] if effect and isinstance(effect[1], int) else None


def named_sets():
    """Every set id `set_name` names: the program's entries, and the
    client's sets it has none for, a placeholder not naming one."""
    import game_client
    return set(SETS) | {set_id for set_id, effect
                        in game_client.known_set_effects().items()
                        if game_client.NAMING.search(effect[0])}


def set_bonus(set_id) -> str:
    """The words a set's effect is shown in: the maintainer's own
    `bonus`, else the game client's, else nothing."""
    own = (SETS.get(set_id) or {}).get("bonus")
    if own:
        return own
    import game_client
    effect = game_client.known_set_effects().get(set_id)
    return effect[2] if effect else ""


TWO_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 2]
FOUR_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 4]

# Mapping from the `stat` field above to the program's internal stat-name
# vocabulary. Some names match exactly (ATK%, DEF%, HP%); the crit stats
# differ ("Crit DMG" -> CDmg, "Crit Rate" -> CRate). `DMG multi` and
# `DMG add` are deliberately absent: they have no Final-stat equivalent
# and are accumulated straight into the damage card multiplier's
# Multiplicative_Buffs / Additive_Buffs buckets instead.
#
# ADD A NEWLY-RELEASED SET STAT HERE. This is the single source of truth
# for which `stat` spellings reach the formulas -- optimizer/core.py
# imports it, and the launch-time data check validates against it, so a
# name missing here is silently ignored everywhere.
# Canonical description: docs/game_formulas.md §5.
SET_STAT_NAME_MAP = {
    "ATK%":      "ATK%",
    "DEF%":      "DEF%",
    "HP%":       "HP%",
    "Crit DMG":  "CDmg",
    "Crit Rate": "CRate",
}

# The two `stat` values that take effect on CONDITIONAL sets only, by
# feeding the damage card multiplier rather than a Final stat.
SET_CARD_MULT_STATS = ("DMG multi", "DMG add")
