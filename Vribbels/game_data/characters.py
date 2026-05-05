"""
Character data and related functions for CZN.
Contains character definitions, potential nodes, and helper functions.
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
    "base_crit_rate": 0,
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
        "base_atk": 393,
        "base_def": 186,
        "base_hp": 383,
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
        "base_atk": 483,
        "base_def": 138,
        "base_hp": 363,
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
        "base_atk": 408,
        "base_def": 183,
        "base_hp": 493,
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
        "base_atk": 415,
        "base_def": 158,
        "base_hp": 403,
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
        "base_atk": 408,
        "base_def": 183,
        "base_hp": 493,
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
        "base_atk": 383,
        "base_def": 172,
        "base_hp": 461,
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
        "base_atk": 468,
        "base_def": 155,
        "base_hp": 446,
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
        "base_atk": 461,
        "base_def": 147,
        "base_hp": 375,
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
        "base_atk": 420,
        "base_def": 197,
        "base_hp": 406,
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
        "base_atk": 468,
        "base_def": 155,
        "base_hp": 446,
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
        "base_atk": 383,
        "base_def": 172,
        "base_hp": 461,
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
        "base_atk": 515,
        "base_def": 141,
        "base_hp": 317,
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
        "base_atk": 402,
        "base_def": 176,
        "base_hp": 388,
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
        "base_atk": 483,
        "base_def": 138,
        "base_hp": 363,
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
        "base_atk": 492,
        "base_def": 155,
        "base_hp": 399,
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
        "base_atk": 393,
        "base_def": 186,
        "base_hp": 383,
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
        "base_atk": 439,
        "base_def": 147,
        "base_hp": 418,
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
        "base_atk": 393,
        "base_def": 186,
        "base_hp": 383,
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
    },
    1062: {
        "name": "Haru",
        "grade": 5,
        "attribute": "Justice",
        "class": "Striker",
        "base_atk": 467,
        "base_def": 155,
        "base_hp": 376,
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
        "base_atk": 444,
        "base_def": 169,
        "base_hp": 426,
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
        "base_atk": 408,
        "base_def": 178,
        "base_hp": 481,
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
        "base_atk": 335,
        "base_def": 252,
        "base_hp": 256,
        "base_crit_rate": 3.0,
        "base_crit_dmg": 125.0,
        "node_50": "CRate",
        "node_60": "CDmg",
    },
    30097: {
        "name": "Rita",
        "grade": 5,
        "attribute": "Justice",
        "class": "Psionic",
        "base_atk": 354,
        "base_def": 164,
        "base_hp": 271,
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

# Potential stat values per level (levels 1-5)
# These are the stat bonus percentages/values gained at each level
# Note: Values may need adjustment based on actual game data
POTENTIAL_STAT_VALUES = {
    "HP%": (0.6, 1.2, 1.8, 2.4, 3.0),      # % HP increase per level
    "ATK%": (0.6, 1.2, 1.8, 2.4, 3.0),     # % ATK increase per level
    "DEF%": (1.6, 3.2, 4.8, 6.4, 8.0),     # % DEF increase per level
    "CRate": (2.0, 4.0, 6.0, 8.0, 10.0),   # Crit Rate % per level
    "CDmg": (2.4, 4.8, 7.2, 9.6, 12.0),    # Crit Damage % per level
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

    Args:
        potential_str: String like "[10431001,10432010,10435005]" or "[]"
        res_id: Character's res_id to validate node IDs

    Returns:
        Dict mapping node number to level, e.g., {10: 1, 20: 10, 50: 5}
    """
    result = {}

    if not potential_str or potential_str == "[]":
        return result

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
            if len(node_str) != 8:
                continue

            # Parse: XXXX YY ZZ where XXXX=res_id, YY=node, ZZ=level
            parsed_res_id = int(node_str[:4])
            node_num = int(node_str[4:6])
            node_level = int(node_str[6:8])

            # Validate res_id matches
            if parsed_res_id == res_id:
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
