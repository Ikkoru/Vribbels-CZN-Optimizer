"""
Character data and related functions for CZN.

Module structure
================

CHARACTERS
----------
The big one. Maps in-game character res_id (int) to a dict describing
the character's static properties:
    {
      "name":      "Amir",
      "grade":     5,                 # rarity / star count
      "attribute": "Order",           # Passion / Order / Justice / Void / Instinct
      "class":     "DPS",             # role (Tank / DPS / Support / Healer)
      "base_atk":  ..., "base_def": ..., "base_hp": ...,   # AT LEVEL 60
      "potential_nodes": {...},       # see "Potential nodes" below
    }

The base stats are observed at level 60 -- they are the canonical figures
the optimizer uses. The optimizer DOES NOT scale these down for
lower-level characters; characters below level 60 are treated as if they
were at level 60 for stat-calculation purposes. This is intentional per
the project's design (game progression is the player's job; the optimizer
exists to compare endgame builds).

Potential nodes
---------------
Each character has 6 potential-tree levels: 10, 20, 30, 40, 50, 60.
Reaching each level unlocks a stat bonus.

  - Nodes 10/20/30 are FLAT bonuses (e.g. +50 ATK, +5% HP).
  - Nodes 40/50/60 are PERCENTAGE bonuses.

POTENTIAL_STAT_VALUES gives the FIVE possible bonus magnitudes for nodes
40, 50, and 60 (each character gets a different magnitude per tier). The
tuple positions are "tier 1 through tier 5"; a character with HP% tier 3
at the level-50 node gets POTENTIAL_STAT_VALUES["HP%"][2] (zero-indexed)
which is 4.8% HP. The five tiers are NOT character levels -- this is the
single point of confusion most likely to trip future maintainers. Each
character has a fixed tier per node from the data file, so the array
index resolves a different question (which strength bracket) from the
character's own level.

Higher-level cap (61/62)
------------------------
LEVEL_61_BONUS and LEVEL_62_BONUS at the bottom of this module are
placeholder dicts (all values -1 = "unknown") for the stat additions
gained at the new 61/62 level cap. The helper get_character_stats_at_level
honors -1 as "fall back to level-60 value", so the placeholders are
no-ops until real data lands.

CHARACTERS_BY_NAME, DEFAULT_CHARACTER, helpers
----------------------------------------------
CHARACTERS_BY_NAME is the reverse index for name -> char_data lookups.
DEFAULT_CHARACTER is the fallback for unknown res_ids (returned by
get_character / get_character_by_name).

ATTRIBUTE_COLORS is UI styling; it lives here only because the attribute
strings are defined here.
"""

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
# Note: Stats marked with # TBD need actual game data
CHARACTERS = {
    0: None,  # Special case for unequipped
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
    },
    1009: {
        "name": "Tressa",
        "grade": 4,
        "attribute": "Void",
        "class": "Psionic",
        "base_atk": 494,
        "base_def": 162,
        "base_hp": 418,
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
    1024: {
        "name": "Orlea",
        "grade": 5,
        "attribute": "Justice",
        "class": "Controller",
        "base_atk": 419,
        "base_def": 197,
        "base_hp": 336,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "ATK%",
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
    1028: {
        "name": "Maribell",
        "grade": 4,
        "attribute": "Passion",
        "class": "Vanguard",
        "base_atk": 300,
        "base_def": 208,
        "base_hp": 408,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "HP%",
    },
    1033: {
        "name": "Veronica",
        "grade": 5,
        "attribute": "Passion",
        "class": "Ranger",
        "base_atk": 541,
        "base_def": 142,
        "base_hp": 344,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
    },
    1039: {
        "name": "Mika",
        "grade": 4,
        "attribute": "Justice",
        "class": "Controller",
        "base_atk": 412,
        "base_def": 176,
        "base_hp": 304,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "HP%",
        "node_60": "ATK%",
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
    1043: {
        "name": "Hugo",
        "grade": 5,
        "attribute": "Order",
        "class": "Ranger",
        "base_atk": 505,
        "base_def": 146,
        "base_hp": 320,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CDmg",
        "node_60": "CRate",
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
    },
    1057: {
        "name": "Yuki",
        "grade": 5,
        "attribute": "Order",
        "class": "Striker",
        "base_atk": 455,
        "base_def": 155,
        "base_hp": 366,
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
    },
    1061: {
        "name": "Diana",
        "grade": 5,
        "attribute": "Passion",
        "class": "Hunter",
        "base_atk": 491,
        "base_def": 161,
        "base_hp": 344,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
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
    },
    1064: {
        "name": "Kayron",
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
    },
}

# Build reverse lookup: name -> character data (for lookups by name)
CHARACTERS_BY_NAME = {
    char_data["name"]: char_data
    for char_data in CHARACTERS.values()
    if char_data is not None
}

# Potential-node stat values at level-40, level-50, level-60 nodes (the
# percentage-bonus tier). The five tuple positions are STRENGTH TIERS
# 1-5, not character levels -- each character has a fixed tier assignment
# per node (read from the source data), and the tier indexes into this
# tuple. See the module docstring for the full explanation.
#
# Example: a character with "level-50: HP% tier 3" gets
# POTENTIAL_STAT_VALUES["HP%"][2] = 4.8% HP from their level-50 node.
POTENTIAL_STAT_VALUES = {
    "HP%": (1.6, 3.2, 4.8, 6.4, 8.0),      # % HP increase by tier (1-5)
    "ATK%": (1.6, 3.2, 4.8, 6.4, 8.0),     # % ATK increase by tier (1-5)
    "DEF%": (1.6, 3.2, 4.8, 6.4, 8.0),     # % DEF increase by tier (1-5)
    "CRate": (2.0, 4.0, 6.0, 8.0, 10.0),   # Crit Rate % by tier (1-5)
    "CDmg": (2.4, 4.8, 7.2, 9.6, 12.0),    # Crit Damage % by tier (1-5)
}

ATTRIBUTE_COLORS = {
    "Passion": "#FF6B6B",   # Red
    "Void": "#9B59B6",      # Purple
    "Instinct": "#FF8C00",  # Orange
    "Order": "#2ECC71",     # Green
    "Justice": "#3498DB",   # Blue
}


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
# Levels 61 and 62 (added in a later game update; rare in practice)
# ============================================================================
#
# Characters now max at level 62 (was 60). Promotion 5/5 grants +2 effective
# levels on top of the previous cap. We don't yet have any character at level
# 61+ in the snapshots, so the per-level stat gains for these two levels are
# placeholders (-1 = "unknown, fall back to level 60").
#
# Once data is observable, replace -1 entries with the actual flat additions
# on top of the level-60 base stats. If gains turn out to differ per
# character, refactor LEVEL_61_BONUS / LEVEL_62_BONUS to per-res_id dicts.
#
# Nothing currently calls get_character_stats_at_level() with level > 60 in
# production -- the optimizer still uses the level-60 base stats directly.
# The helper is wired up for when the eventual "use 61/62 stats" UI toggle
# arrives, at which point swapping in this call is a one-line change.

LEVEL_61_BONUS = {"atk": -1, "def": -1, "hp": -1}
LEVEL_62_BONUS = {"atk": -1, "def": -1, "hp": -1}


def get_character_stats_at_level(char_data: dict, level: int) -> dict:
    """Return effective (base_atk, base_def, base_hp) at the given level.

    For level <= 60: returns the level-60 base stats unchanged. The
    optimizer has always used these as its working baseline, so this is
    the safe default for any consumer that doesn't explicitly opt in to
    higher levels.

    For level in [61, 62]: adds LEVEL_61_BONUS (and LEVEL_62_BONUS if
    level >= 62) on top of base. Any field whose bonus is -1 silently
    falls back to its level-60 value -- so until real data lands, this
    function is functionally identical to "always return level 60",
    keeping the program's behavior unchanged.

    Args:
        char_data: a CHARACTERS-dict entry (the value, not the key).
                   Reads base_atk / base_def / base_hp from it.
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

    # Apply level-61 bonus; conditionally apply level-62 bonus on top.
    bonuses = [LEVEL_61_BONUS] + ([LEVEL_62_BONUS] if level >= 62 else [])
    for bonus in bonuses:
        if bonus["atk"] != -1: base["base_atk"] += bonus["atk"]
        if bonus["def"] != -1: base["base_def"] += bonus["def"]
        if bonus["hp"]  != -1: base["base_hp"]  += bonus["hp"]
    return base
