"""
Game data module for CZN Optimizer.
Exports all game data dictionaries, constants, and helper functions.
"""

from .characters import (
    DEFAULT_CHARACTER,
    CHARACTERS,
    CHARACTERS_BY_NAME,
    POTENTIAL_STAT_VALUES,
    ATTRIBUTE_COLORS,
    get_potential_stat_bonus,
    parse_potential_node_ids,
    get_character,
    get_character_name,
    get_character_by_name,
)

from .partners import (
    DEFAULT_PARTNER,
    PARTNERS,
    PARTNER_CLASS_STATS,
    get_partner,
    get_value_for_ego_level,
    get_partner_base_stats,
    get_partner_stats,
    get_partner_passive_stats,
    format_passive_description,
    get_partner_passive_info,
)

from .sets import (
    SETS,
    TWO_PIECE_SETS,
    FOUR_PIECE_SETS,
)

from .constants import (
    CHARACTER_EXP_TABLE,
    PARTNER_EXP_TABLE,
    FRIENDSHIP_BONUSES,
    # Note: GAME_HOSTS, GAME_PORT, PROXY_PORT, OUTPUT_DIR, HOSTS_PATH moved to capture module
    EQUIPMENT_SLOTS,
    SLOT_ORDER,
    RARITY,
    RARITY_COLORS,
    RARITY_BG_COLORS,
    RARITY_ICONS,
    RARITY_STARTING_SUBSTATS,
    STATS,
    STAT_SHORT_NAMES,
    ALL_STAT_NAMES,
    SLOT_MAIN_STATS,
    MAIN_STAT_VALUES,
    MAX_LEVEL,
    UPGRADES_PER_RARITY,
    GROWTH_STONES,
    get_level_from_exp,
    get_partner_level_from_exp,
    get_friendship_bonus,
)

__all__ = [
    # Characters
    'DEFAULT_CHARACTER',
    'CHARACTERS',
    'CHARACTERS_BY_NAME',
    'POTENTIAL_STAT_VALUES',
    'ATTRIBUTE_COLORS',
    'get_potential_stat_bonus',
    'parse_potential_node_ids',
    'get_character',
    'get_character_name',
    'get_character_by_name',

    # Partners
    'DEFAULT_PARTNER',
    'PARTNERS',
    'PARTNER_CLASS_STATS',
    'get_partner',
    'get_value_for_ego_level',
    'get_partner_base_stats',
    'get_partner_stats',
    'get_partner_passive_stats',
    'format_passive_description',
    'get_partner_passive_info',

    # Sets
    'SETS',
    'TWO_PIECE_SETS',
    'FOUR_PIECE_SETS',

    # Constants
    'CHARACTER_EXP_TABLE',
    'PARTNER_EXP_TABLE',
    'FRIENDSHIP_BONUSES',
    # Note: GAME_HOSTS, GAME_PORT, PROXY_PORT, OUTPUT_DIR, HOSTS_PATH moved to capture module
    'EQUIPMENT_SLOTS',
    'SLOT_ORDER',
    'RARITY',
    'RARITY_COLORS',
    'RARITY_BG_COLORS',
    'RARITY_ICONS',
    'RARITY_STARTING_SUBSTATS',
    'STATS',
    'STAT_SHORT_NAMES',
    'ALL_STAT_NAMES',
    'SLOT_MAIN_STATS',
    'MAIN_STAT_VALUES',
    'MAX_LEVEL',
    'UPGRADES_PER_RARITY',
    'GROWTH_STONES',
    'get_level_from_exp',
    'get_partner_level_from_exp',
    'get_friendship_bonus',
]
