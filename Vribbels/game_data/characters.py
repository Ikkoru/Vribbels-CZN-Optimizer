"""Character data.

CHARACTERS
==========

res_id (int) → static properties::

    {
      "name":      "Amir",
      "grade":     5,                 # rarity / star count
      "attribute": "Order",           # Passion/Order/Justice/Void/Instinct
      "class":     "Vanguard",        # one of constants.CLASSES
      "base_atk":  ..., "base_def": ..., "base_hp": ...,   # AT LEVEL 60
      "potential_nodes": {...},
    }

**Base stats are observed at level 60 and are never scaled down.** A
character below 60 is treated as if at 60 for stat purposes — by design,
since the optimizer exists to compare endgame builds.

Potential nodes
===============

The tree has TEN nodes, wire-numbered 10, 20, 30, 31, 40, 50, 51, 52,
60, 70. `POTENTIAL_NODES` below is the whole tree -- display order,
both numberings, maxima and descriptions -- and every node's level is
kept and shown.

**Only `node_50` and `node_60` carry a STAT**, though; the rest improve
card effects or unlock a one-off, and the build score does not model
them, so a CHARACTERS entry names a stat for those two alone. Node 7
(`70`) can also move a stat, per character: `potential_7.py`.
Full table, including which in-game node each wire number is:
`docs/game_formulas.md` §1.

`POTENTIAL_STAT_VALUES` gives the FIVE bonus magnitudes for the two stat
nodes. **The tuple positions are strength tiers, NOT character levels** —
the single most likely point of confusion here. A character with HP%
tier 3 at the level-50 node gets `POTENTIAL_STAT_VALUES["HP%"][2]`.
Each character has a fixed tier per node from the data file.

Levels 61 and 62
================

Promotion 5/5 grants +2 levels over the 60 cap. What each adds is kept
per class and grade in `LEVEL_BONUS_BY_CLASS`, since every combatant of
a pair observed gains the same; a combatant's own `level_61_bonus` /
`level_62_bonus` key overrides it. `table_stats_at_level` adds nothing
for a gain nobody has observed, so missing data is a no-op.

The server's own readings
=========================

`get_character_stats_at_level`, which the program asks, answers with the
server's reading where `game_data.learned` holds one, and fills an
unknown gain from readings too; `table_stats_at_level` and
`level_bonus` are the tables alone, which the audit and the checks hold
the server against. `docs/game_data_files.md` has the order.

Lookups
=======

`CHARACTERS_BY_NAME` is the reverse index. `DEFAULT_CHARACTER` is the
fallback for unknown res_ids returned by `get_character` /
`get_character_by_name`.

`ATTRIBUTE_COLORS` is UI styling but lives here because its keys are the
canonical list of the five attributes, and the launch-time data check
validates `attribute` against them.
"""

from typing import NamedTuple

# Default character data for unknown characters
DEFAULT_CHARACTER = {
    "name": "Unknown",
    "grade": 0,
    "attribute": "Unknown",
    "class": "Unknown",
    "base_atk": 0,
    "base_def": 0,
    "base_hp": 0,
    "base_crit_rate": 3.0,
    "base_crit_dmg": 125.0,
    "node_50": None,
    "node_60": None,
}

# Unified character/hero data: res_id -> all character information
# Contains: name, grade, attribute, class, and base stats at level 60
# See get_character_stats_at_level() below for how levels 61 and 62 add
# to them.
# Note: Stats marked with # TBC or # Assumed need actual game data
CHARACTERS = {
    0: None,  # Special case for unequipped
    1017: {
        "name": "Amir",
        "grade": 4,
        "attribute": "Order",
        "class": "Vanguard",
        "base_atk": 382,
        "base_def": 172,
        "base_hp": 392,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "HP%",
    },
    1012: {
        "name": "Anika",
        "grade": 4,
        "attribute": "Order",
        "class": "Striker",
        "base_atk": 405,
        "base_def": 163,
        "base_hp": 381,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1040: {
        "name": "Beryl",
        "grade": 4,
        "attribute": "Justice",
        "class": "Ranger",
        "base_atk": 482,
        "base_def": 133,
        "base_hp": 293,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
        "level_61_bonus": {"atk": 8, "def": 2, "hp": 7},
    },
    1049: {
        "name": "Cassius",
        "grade": 4,
        "attribute": "Instinct",
        "class": "Controller",
        "base_atk": 392,
        "base_def": 186,
        "base_hp": 313,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "ATK%",
        "level_61_bonus": {"atk": 6, "def": 3, "hp": 9},
    },
    1021: {
        "name": "Lucas",
        "grade": 4,
        "attribute": "Passion",
        "class": "Hunter",
        "base_atk": 460,
        "base_def": 147,
        "base_hp": 305,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1028: {
        "name": "Maribell",
        "grade": 4,
        "attribute": "Passion",
        "class": "Vanguard",
        "base_atk": 382,
        "base_def": 172,
        "base_hp": 392,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "HP%",
        "level_61_bonus": {"atk": 6, "def": 3, "hp": 9},
    },
    1039: {
        "name": "Mika",
        "grade": 4,
        "attribute": "Justice",
        "class": "Controller",
        "base_atk": 401,
        "base_def": 176,
        "base_hp": 318,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "ATK%",
        "level_61_bonus": {"atk": 6, "def": 3, "hp": 9},
    },
    1003: {
        "name": "Nia",
        "grade": 4,
        "attribute": "Instinct",
        "class": "Controller",
        "base_atk": 392,
        "base_def": 186,
        "base_hp": 313,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "ATK%",
        "level_61_bonus": {"atk": 6, "def": 3, "hp": 9},
    },
    1050: {
        "name": "Owen",
        "grade": 4,
        "attribute": "Passion",
        "class": "Striker",
        "base_atk": 438,
        "base_def": 147,
        "base_hp": 348,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1056: {
        "name": "Rei",
        "grade": 4,
        "attribute": "Void",
        "class": "Controller",
        "base_atk": 392,
        "base_def": 186,
        "base_hp": 313,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "ATK%",
        "level_61_bonus": {"atk": 6, "def": 3, "hp": 9},
    },
    1005: {
        "name": "Selena",
        "grade": 4,
        "attribute": "Passion",
        "class": "Ranger",
        "base_atk": 482,
        "base_def": 133,
        "base_hp": 293,
        "base_crit_rate": 3,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
    },
    1009: {
        "name": "Tressa",
        "grade": 4,
        "attribute": "Void",
        "class": "Psionic",
        "base_atk": 414,
        "base_def": 158,
        "base_hp": 333,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1043: {
        "name": "Hugo",
        "grade": 5,
        "attribute": "Order",
        "class": "Ranger",
        "base_atk": 505,  # TBC
        "base_def": 146,  # TBC
        "base_hp": 320,  # TBC
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
    },
    1064: {
        "name": "Kayron",
        "grade": 5,
        "attribute": "Void",
        "class": "Psionic",
        "base_atk": 443,  # TBC
        "base_def": 169,  # TBC
        "base_hp": 356,  # TBC
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1008: {
        "name": "Khalipe",
        "grade": 5,
        "attribute": "Instinct",
        "class": "Vanguard",
        "base_atk": 407,
        "base_def": 183,
        "base_hp": 423,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "HP%",
        "level_61_bonus": {"atk": 6, "def": 4, "hp": 10},
    },
    1004: {
        "name": "Luke",
        "grade": 5,
        "attribute": "Order",
        "class": "Hunter",
        "base_atk": 491,
        "base_def": 155,
        "base_hp": 329,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1010: {
        "name": "Magna",
        "grade": 5,
        "attribute": "Justice",
        "class": "Vanguard",
        "base_atk": 407,
        "base_def": 183,
        "base_hp": 423,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "HP%",
    },
    1027: {
        "name": "Mei Lin",
        "grade": 5,
        "attribute": "Passion",
        "class": "Striker",
        "base_atk": 467,
        "base_def": 155,
        "base_hp": 376,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1024: {
        "name": "Orlea",
        "grade": 5,
        "attribute": "Instinct",
        "class": "Controller",
        "base_atk": 419,
        "base_def": 197,
        "base_hp": 336,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "ATK%",
        "level_61_bonus": {"atk": 6, "def": 4, "hp": 10},
    },
    1041: {
        "name": "Renoa",
        "grade": 5,
        "attribute": "Void",
        "class": "Hunter",
        "base_atk": 491,
        "base_def": 155,
        "base_hp": 329,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1018: {
        "name": "Rin",
        "grade": 5,
        "attribute": "Void",
        "class": "Striker",
        "base_atk": 467,
        "base_def": 155,
        "base_hp": 376,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1033: {
        "name": "Veronica",
        "grade": 5,
        "attribute": "Passion",
        "class": "Ranger",
        "base_atk": 515,
        "base_def": 141,
        "base_hp": 317,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
        "level_61_bonus": {"atk": 9, "def": 3, "hp": 7},
    },
    1062: {
        "name": "Haru",
        "grade": 5,
        "attribute": "Justice",
        "class": "Striker",
        "base_atk": 488,
        "base_def": 162,
        "base_hp": 394,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
        "level_61_bonus": {"atk": 8, "def": 3, "hp": 9},
    },
    1057: {
        "name": "Yuki",
        "grade": 5,
        "attribute": "Order",
        "class": "Striker",
        "base_atk": 467,
        "base_def": 155,
        "base_hp": 376,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1060: {
        "name": "Chizuru",
        "grade": 5,
        "attribute": "Void",
        "class": "Psionic",
        "base_atk": 443,
        "base_def": 169,
        "base_hp": 356,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
        "level_61_bonus": {"atk": 8, "def": 3, "hp": 9},
    },
    30075: {
        "name": "Sereniel",
        "grade": 5,
        "attribute": "Instinct",
        "class": "Hunter",
        "base_atk": 491,
        "base_def": 155,
        "base_hp": 329,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    1052: {
        "name": "Narja",
        "grade": 5,
        "attribute": "Instinct",
        "class": "Controller",
        "base_atk": 419,
        "base_def": 197,
        "base_hp": 336,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "DEF%",
        "node_60": "CRate",
        "level_61_bonus": {"atk": 6, "def": 4, "hp": 10},
    },
    30047: {
        "name": "Nine",
        "grade": 5,
        "attribute": "Order",
        "class": "Vanguard",
        "base_atk": 407,
        "base_def": 178,
        "base_hp": 411,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
        "level_61_bonus": {"atk": 6, "def": 4, "hp": 10},
    },
    30084: {
        "name": "Tiphera",
        "grade": 5,
        "attribute": "Order",
        "class": "Controller",
        "base_atk": 419,
        "base_def": 197,
        "base_hp": 336,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "DEF%",
        "level_61_bonus": {"atk": 6, "def": 4, "hp": 10},
    },
    30097: {
        "name": "Rita",
        "grade": 5,
        "attribute": "Justice",
        "class": "Psionic",
        "base_atk": 443,
        "base_def": 169,
        "base_hp": 356,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
        "level_61_bonus": {"atk": 8, "def": 3, "hp": 9},
    },
    1061: {
        "name": "Diana",
        "grade": 5,
        "attribute": "Passion",
        "class": "Hunter",
        "base_atk": 491,
        "base_def": 155,
        "base_hp": 329,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    30093: {
        "name": "Heidemarie",
        "grade": 5,
        "attribute": "Passion",
        "class": "Ranger",
        "base_atk": 515,
        "base_def": 141,
        "base_hp": 317,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
        "level_61_bonus": {"atk": 9, "def": 3, "hp": 7},
    },
    1055: {
        "name": "Adelheid",
        "grade": 5,
        "attribute": "Void",
        "class": "Vanguard",
        "base_atk": 407,
        "base_def": 183,
        "base_hp": 423,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "DEF%",
        "level_61_bonus": {"atk": 6, "def": 4, "hp": 10},
    },
    1069: {
        "name": "Tenebria",
        "grade": 5,
        "attribute": "Passion",
        "class": "Psionic",
        "base_atk": 443,
        "base_def": 169,
        "base_hp": 356,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
        "level_61_bonus": {"atk": 8, "def": 3, "hp": 9},
    },
    30048: {
        "name": "Fei",
        "grade": 5,
        "attribute": "Void",
        "class": "Ranger",
        "base_atk": 515,
        "base_def": 141,
        "base_hp": 317,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
        "level_61_bonus": {"atk": 9, "def": 3, "hp": 7},
    },
    30113: {
        "name": "Hilde",
        "grade": 5,
        "attribute": "Instinct",
        "class": "Ranger",
        "base_atk": 515,
        "base_def": 141,
        "base_hp": 317,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
    },
    30115: {
        "name": "Arabella",
        "grade": 5,
        "attribute": "Instinct",
        "class": "Striker",
        "base_atk": 495,
        "base_def": 146,
        "base_hp": 332,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    30117: {
        "name": "Olga",
        "grade": 5,
        "attribute": "Instinct",
        "class": "Psionic",
        "base_atk": 443,
        "base_def": 169,
        "base_hp": 356,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
        "level_61_bonus": {"atk": 8, "def": 3, "hp": 9},
    },
}

# Build reverse lookup: name -> character data (for lookups by name)
CHARACTERS_BY_NAME = {
    char_data["name"]: char_data
    for char_data in CHARACTERS.values()
    if char_data is not None
}

# Stat magnitudes for the two stat nodes, `node_50` and `node_60`. Node
# 40 is NOT one of them -- it multiplies Signature Card effects and its
# levels run to 10, so reading it through this five-tier table returns
# zero (see docs/game_formulas.md §1 "The potential tree").
# The five tuple positions are STRENGTH TIERS
# 1-5, not character levels -- each character has a fixed tier assignment
# per node (read from the source data), and the tier indexes into this
# tuple. See the module docstring for the full explanation.
#
# Example: a character with "level-50: HP% tier 3" gets
# POTENTIAL_STAT_VALUES["HP%"][2] = 4.8% HP from their level-50 node.
#
# ADD A NEWLY-RELEASED POTENTIAL-NODE STAT HERE. `node_50` / `node_60`
# on a CHARACTERS entry must name one of these keys; anything else makes
# get_potential_stat_bonus return zero silently, and the launch-time data
# check validates against exactly this dict.
POTENTIAL_STAT_VALUES = {
    "HP%": (1.6, 3.2, 4.8, 6.4, 8.0),      # % HP increase by tier (1-5)
    "ATK%": (1.6, 3.2, 4.8, 6.4, 8.0),     # % ATK increase by tier (1-5)
    "DEF%": (1.6, 3.2, 4.8, 6.4, 8.0),     # % DEF increase by tier (1-5)
    "CRate": (2.0, 4.0, 6.0, 8.0, 10.0),   # Crit Rate % by tier (1-5)
    "CDmg": (2.4, 4.8, 7.2, 9.6, 12.0),    # Crit Damage % by tier (1-5)
}

# ADD A NEWLY-RELEASED ATTRIBUTE HERE. These keys are the canonical list
# of attributes: `attribute` on a CHARACTERS entry and `elements` on a
# set must name one of them, and the launch-time data check validates
# against exactly this dict.
ATTRIBUTE_COLORS = {
    "Passion": "#FF6B6B",   # Red
    "Void": "#9B59B6",      # Purple
    "Instinct": "#FF8C00",  # Orange
    "Order": "#2ECC71",     # Green
    "Justice": "#3498DB",   # Blue
}


class PotentialNode(NamedTuple):
    """One node of the potential tree.

    `shown` is the number the GAME prints and `wire` the one a snapshot
    encodes; the two DISAGREE, and `docs/game_formulas.md` §1 is the
    canonical table of both.

    `does` is the line's parenthetical, empty where the node's name
    says enough on its own. `stat` marks the two whose effect is per
    character and read out of `POTENTIAL_STAT_VALUES` instead.
    """
    shown: str
    wire: int
    max_level: int
    does: str = ""
    stat: bool = False


# The tree, in the order the Combatants tab lists it.
#
# ONE list: the order, the numbering, the maxima and the descriptions
# all come from here, so re-ordering the display is re-ordering this
# tuple and nothing else. The descriptions live in code rather than in
# a doc on purpose -- a second copy of a string the UI already shows is
# what goes stale.
POTENTIAL_NODES = (
    PotentialNode("1",   10, 1),
    PotentialNode("2",   20, 10, "Basic Cards"),
    PotentialNode("3",   30, 10, "Neutral Cards"),
    PotentialNode("3.1", 31, 1,  "Basics Improved"),
    PotentialNode("4",   40, 10, "Signature Cards"),
    PotentialNode("5",   50, 5,  stat=True),
    PotentialNode("5.1", 51, 1,  "Basics Improved"),
    PotentialNode("5.2", 52, 1,  "Divine Epiphany%"),
    PotentialNode("6",   60, 5,  stat=True),
    PotentialNode("7",   70, 1,  "Conditional Stat Up"),
)

# The most a combatant's nodes can sum to, which is what a "42/45"
# reading counts against. Summed rather than stated: a node added to
# the tuple above moves it.
POTENTIAL_MAX_TOTAL = sum(node.max_level for node in POTENTIAL_NODES)

# Nodes one character words differently. Tiphera's 5.1 improves her
# Archetype cards where every other character's improves the Basics.
POTENTIAL_NODE_OVERRIDES = {
    30084: {51: "Archetypes +10%"},   # Tiphera
}


def get_potential_node_does(res_id: int, node) -> str:
    """The parenthetical for one node on one character. Node 7 names
    what the character's own Potential 7 raises, where it is known."""
    if node.wire == 70:
        from .potential_7 import potential_7_label
        char = CHARACTERS.get(res_id)
        label = potential_7_label(
            res_id, char.get("attribute", "") if isinstance(char, dict) else "")
        if label:
            return label
    return POTENTIAL_NODE_OVERRIDES.get(res_id, {}).get(node.wire, node.does)


def get_potential_stat(res_id: int, node: int) -> str | None:
    """The stat a potential node raises, whatever its level.

    `get_potential_stat_bonus` answers with a VALUE and so needs a level;
    an unlevelled node has no bonus and it returns nothing. Which stat
    the node would raise is a property of the character, known before
    the node is taken, and this is what reports it.

    Args:
        res_id: Character's res_id
        node: Node number (50 or 60)

    Returns:
        The stat name, or None where the character or the node is
        unknown to this build.
    """
    char_data = CHARACTERS.get(res_id)
    if not isinstance(char_data, dict):
        return None
    return char_data.get(f"node_{node}") or None


def get_potential_stat_bonus(res_id: int, node: int, level: int) -> tuple[str, float]:
    """
    Get the stat type and bonus value for a potential node at a given level.

    Args:
        res_id: Character's res_id
        node: Node number (50 or 60)
        level: Node level (1-5)

    Returns:
        Tuple of (stat_type, bonus_value) or (None, 0) if not found
    """
    if level <= 0 or level > 5:
        return (None, 0.0)

    # Look up character data from CHARACTERS dictionary
    char_data = CHARACTERS.get(res_id)
    if not char_data:
        return (None, 0.0)

    # Get the stat type for this node from character definition
    node_key = f"node_{node}"
    stat_type = char_data.get(node_key)
    if not stat_type:
        return (None, 0.0)

    stat_values = POTENTIAL_STAT_VALUES.get(stat_type)
    if not stat_values:
        return (None, 0.0)

    # Level is 1-indexed, array is 0-indexed
    bonus_value = stat_values[level - 1]
    return (stat_type, bonus_value)


def parse_potential_node_ids(potential_str: str, res_id: int) -> dict[int, int]:
    """
    Parse potential_node_ids string and extract node levels.

    Each node_id is encoded as the character's res_id digits, followed by a
    2-digit node number, followed by a 2-digit node level. So for a 4-digit
    res_id the total length is 8 characters (e.g. "10031001" -> res_id 1003,
    node 10, level 01); for a 5-digit res_id it's 9 (e.g. "300471001" ->
    res_id 30047, node 10, level 01).

    Args:
        potential_str: String like "[10431001,10432010,10435005]" or "[]"
        res_id: Character's res_id — used both to size the node prefix and
                to validate that each node belongs to this character.

    Returns:
        Dict mapping node number to level, e.g., {10: 1, 20: 10, 50: 5}
    """
    result = {}

    if not potential_str or potential_str == "[]":
        return result

    res_id_str = str(res_id)
    res_id_len = len(res_id_str)
    expected_total = res_id_len + 4   # res_id + 2-digit node + 2-digit level

    # Parse the string - remove brackets and split by comma
    try:
        # Handle both string format "[...]" and already parsed list
        if isinstance(potential_str, str):
            cleaned = potential_str.strip("[]")
            if not cleaned:
                return result
            node_ids = [int(x.strip()) for x in cleaned.split(",") if x.strip()]
        else:
            node_ids = potential_str

        for node_id in node_ids:
            node_str = str(node_id)
            # Length must match res_id_len + 4 (the 4 digits = NN node + LL level).
            if len(node_str) != expected_total:
                continue
            # Validate the node belongs to this character.
            if not node_str.startswith(res_id_str):
                continue

            node_num = int(node_str[res_id_len:res_id_len + 2])
            node_level = int(node_str[res_id_len + 2:res_id_len + 4])
            result[node_num] = node_level
    except (ValueError, TypeError):
        pass

    return result


def get_character(res_id: int) -> dict:
    """Get character data by res_id, returning DEFAULT_CHARACTER if not found."""
    char = CHARACTERS.get(res_id)
    if char is None:
        return DEFAULT_CHARACTER
    return char


def get_character_name(res_id: int) -> str:
    """Get character name by res_id, returning the ID string if unknown, or None if unequipped."""
    if res_id == 0:
        return None
    char = CHARACTERS.get(res_id)
    if char is None:
        return str(res_id)
    return char.get("name")


def get_character_by_name(name: str) -> dict:
    """Get character data by name, returning DEFAULT_CHARACTER if not found."""
    return CHARACTERS_BY_NAME.get(name, DEFAULT_CHARACTER)


# ============================================================================
# Levels 61 and 62
# ============================================================================
#
# Characters max at level 62: promotion 5/5 grants +2 levels over the
# level-60 cap. What each of the two adds to the level-60 base is the same
# for every combatant of one class and grade that has been observed, so
# it is kept per PAIR: a combatant nobody has observed at 61 takes what
# the others of their pair gain.
#
# None where no combatant of the pair has been observed at that level --
# not zeros, which would read as a known gain of nothing. An unknown gain
# leaves the level-60 base, as it would be with the level reached but its
# gain not recorded.
#
# A combatant's own `level_61_bonus` / `level_62_bonus` key, shape
# `{"atk": +X, "def": +Y, "hp": +Z}`, overrides their pair's: the room
# for an exception. The launch-time data check reports one that differs
# from its pair's, and a pair left unknown while a combatant of it has
# its own.
LEVEL_BONUS_BY_CLASS = {
    ("Controller", 4): {61: {"atk": 6, "def": 3, "hp": 9}, 62: None},
    ("Controller", 5): {61: {"atk": 6, "def": 4, "hp": 10}, 62: None},
    ("Hunter", 4): {61: None, 62: None},
    ("Hunter", 5): {61: None, 62: None},
    ("Psionic", 4): {61: None, 62: None},
    ("Psionic", 5): {61: {"atk": 8, "def": 3, "hp": 9}, 62: None},
    ("Ranger", 4): {61: {"atk": 8, "def": 2, "hp": 7}, 62: None},
    ("Ranger", 5): {61: {"atk": 9, "def": 3, "hp": 7}, 62: None},
    ("Striker", 4): {61: None, 62: None},
    ("Striker", 5): {61: {"atk": 8, "def": 3, "hp": 9}, 62: None},
    ("Vanguard", 4): {61: {"atk": 6, "def": 3, "hp": 9}, 62: None},
    ("Vanguard", 5): {61: {"atk": 6, "def": 4, "hp": 10}, 62: None},
}


def level_bonus(char_data: dict, level: int):
    """What `level` (61 or 62) adds to `char_data`'s base per the
    tables, as {"atk", "def", "hp"}: the combatant's own key, else their
    class and grade's; None where neither is known. Never the server's
    readings -- `get_character_stats_at_level` adds those."""
    own = char_data.get(f"level_{level}_bonus")
    if own is not None:
        return own
    pair = LEVEL_BONUS_BY_CLASS.get(
        (char_data.get("class"), char_data.get("grade"))) or {}
    return pair.get(level)


def table_stats_at_level(char_data: dict, level: int) -> dict:
    """(base_atk, base_def, base_hp) at `level` from the tables alone.

    For level <= 60: the level-60 base stats unchanged. Those are the
    optimizer's working baseline, and the default for any consumer that
    does not explicitly ask for a higher level.

    For level >= 61: adds what level 61 gains (and level 62's too, at
    62) on top of base, per `level_bonus`. A gain nobody has observed
    adds nothing, so the level-60 values stand in for it.

    What the audit and the checks hold the server against; the program
    itself asks `get_character_stats_at_level`.

    Args:
        char_data: a CHARACTERS-dict entry (the value, not the key).
        level: the in-game level (1-62). Levels outside [61, 62] route
               through the level-60 fallback.
    """
    base = {
        "base_atk": char_data.get("base_atk", 0),
        "base_def": char_data.get("base_def", 0),
        "base_hp":  char_data.get("base_hp", 0),
    }
    if level <= 60:
        return base

    for step in ((61, 62) if level >= 62 else (61,)):
        gain = level_bonus(char_data, step)
        if gain:
            base["base_atk"] += gain.get("atk", 0)
            base["base_def"] += gain.get("def", 0)
            base["base_hp"]  += gain.get("hp", 0)
    return base


def get_character_stats_at_level(char_data: dict, level: int) -> dict:
    """(base_atk, base_def, base_hp) at `level`: the server's reading
    where `game_data.learned` holds one, else the tables'.

    Without a reading at that level, the nearest one is walked to it by
    the level gains -- the combatant's own, read off two readings; else
    their characters.py key; else what every reading of their class and
    grade agrees on; else `LEVEL_BONUS_BY_CLASS`. A level-60 base comes
    back down from a level-61 or 62 reading only where every gain on the
    way is known. Levels below 60 read as 60, and above 62 as 62.
    """
    from game_data import learned
    known = learned.BASES.get(char_data.get("name"))
    if not known and not learned.GAINS:
        return table_stats_at_level(char_data, level)
    level = 60 if level <= 60 else min(level, 62)
    atk, def_, hp = _learned_at(char_data, level, known or {})
    return {"base_atk": atk, "base_def": def_, "base_hp": hp}


def _learned_at(char_data, level, known):
    if level in known:
        return known[level]
    if level == 60:
        for top in (61, 62):
            if top in known:
                gains = [_gain(char_data, step, known)
                         for step in range(top, 60, -1)]
                if None not in gains:
                    return tuple(v - sum(g[k] for g in gains) for v, k in
                                 zip(known[top], ("atk", "def", "hp")))
        table = table_stats_at_level(char_data, 60)
        return table["base_atk"], table["base_def"], table["base_hp"]
    below = _learned_at(char_data, level - 1, known)
    gain = _gain(char_data, level, known) or {}
    return tuple(v + gain.get(k, 0) for v, k in
                 zip(below, ("atk", "def", "hp")))


def _gain(char_data, step, known):
    """What `step` adds for `char_data`, by the order
    `get_character_stats_at_level` gives; None where nothing says."""
    from game_data import learned
    if step in known and step - 1 in known:
        return dict(zip(("atk", "def", "hp"),
                        (a - b for a, b in zip(known[step],
                                               known[step - 1]))))
    own = char_data.get(f"level_{step}_bonus")
    if own is not None:
        return own
    pair = (char_data.get("class"), char_data.get("grade"))
    agreed = (learned.GAINS.get(pair) or {}).get(step)
    if agreed is not None:
        return agreed
    return (LEVEL_BONUS_BY_CLASS.get(pair) or {}).get(step)
