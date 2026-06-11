"""
Game constants for CZN.

This module is the single source of truth for game-rule data that
doesn't live on individual characters / partners / fragments:

  - Experience -> level tables for characters and partners (CHARACTER_EXP_TABLE,
    PARTNER_EXP_TABLE) plus the get_level_from_exp / get_partner_level_from_exp
    helpers. Both tables have firm and estimated entries; provenance is
    annotated at each table.

  - Affection (formerly "friendship") reward bonuses (FRIENDSHIP_BONUSES)
    and the closed-form get_friendship_bonus extrapolation. Each entry
    is the cumulative TOTAL (ATK, DEF, HP) at that level, NOT the
    increment.

  - Equipment slot definitions (EQUIPMENT_SLOTS / SLOT_ORDER) and rarity
    tables (RARITY, RARITY_COLORS, RARITY_BG_COLORS, RARITY_ICONS,
    RARITY_STARTING_SUBSTATS, UPGRADES_PER_RARITY).

  - Stat definitions (STATS dict) -- the central registry that maps the
    raw enum keys from the captured data to display names, percentage
    flags, and (for substat-eligible stats) per-roll min/max values.
    Main-stat-only stats (elemental DMG%) are marked with max_roll=0 as
    a sentinel; consumers iterating STATS for substat math skip these.

  - SLOT_MAIN_STATS for slot-eligible main stat names; MAX_LEVEL and
    UPGRADES_PER_RARITY for fragment-upgrade math.

  - GROWTH_STONES for the leveling-item registry used by the materials
    display (UI sugar; not part of stat math).

Active-table indirection
========================
_active_character_exp_table and _active_partner_exp_table are mutable
module-level references that LevelDataManager.apply_to_constants()
rewrites at startup to include user-confirmed (exp, level) checkpoints.
The base CHARACTER_EXP_TABLE / PARTNER_EXP_TABLE stay pristine so the
hardcoded data can always be distinguished from user augmentation.

Note on capture-related constants
=================================
GAME_HOSTS, GAME_PORT, PROXY_PORT, OUTPUT_DIR, HOSTS_PATH used to live
here. They've been moved to capture/constants.py because they're
specifically about the capture pipeline.
"""

from pathlib import Path

# Experience thresholds for character levels (heroes).
#
# Each row is (cumulative_exp_required_to_reach_this_level, level).
# Levels are discrete in-game: a character with exp >= a checkpoint is at
# (at least) that level, until they accumulate enough for the next.
#
# Provenance (which checkpoints are firm vs. estimated):
#   confirmed:  every level 1–40 — from the in-game progression panel
#                (per-level exp deltas read off and summed into cumulative
#                totals; verified the level-40 total matches the prior
#                known value of 144000).
#               (154800, 41) through (295600, 49) — Amir, levels 41-49,
#                              read off snapshots over multiple sessions
#               (213000, 45) -- replaces the prior estimate of 200000
#               (320000, 50) -- Amir at promotion 4/5, in-game level 50
#               (346000, 51) through (665900, 59) -- Amir, levels 51-59,
#                              read off snapshots over multiple sessions
#               (720000, 60) -- all max-level heroes in May 11 snapshot
#               (778200, 61) -- Amir, level 61 (confirmed checkpoint)
#
# History: pre-v1.1.0 had estimated round-number checkpoints for many
# of the levels under 40 (e.g. (500, 5), (8000, 15), (20000, 20)). Those
# were significantly off vs. the actual game data; replaced wholesale
# below.
CHARACTER_EXP_TABLE = [
    (0, 1),       (100, 2),     (200, 3),     (400, 4),     (600, 5),
    (900, 6),     (1300, 7),    (1700, 8),    (2200, 9),    (2800, 10),
    (3400, 11),   (4100, 12),   (4900, 13),   (5700, 14),   (6600, 15),
    (7600, 16),   (8700, 17),   (9900, 18),   (11200, 19),  (12600, 20),
    (14100, 21),  (16200, 22),  (19000, 23),  (22400, 24),  (26400, 25),
    (31100, 26),  (36400, 27),  (42300, 28),  (48800, 29),  (56000, 30),
    (63900, 31),  (72000, 32),  (80300, 33),  (88800, 34),  (97500, 35),
    (106400, 36), (115500, 37), (124800, 38), (134300, 39), (144000, 40),
    (154800, 41), (167100, 42), (180900, 43), (196200, 44),
    (213000, 45), (231400, 46), (251300, 47), (272700, 48), (295600, 49),
    (320000, 50),
    (346000, 51), (374900, 52), (407100, 53), (442400, 54),
    (480800, 55), (522400, 56), (567100, 57), (614900, 58),
    (665900, 59),
    (720000, 60), (778200, 61),
]

# Partner card exp table (separate progression from heroes).
# Confirmed grade-independent: a May 11 snapshot has 20 max-level partners
# across grades 4, 4.5, and 5 all at exactly exp=346,000.
#
# Provenance:
#   confirmed:  (100, 2)     — Douglas at promotion 0/5, in-game level 2
#               (1800, 10)   — Zatera at promotion 0/5, in-game level 10
#               (36300, 30)  — Raidel at promotion 2/5, in-game level 30
#               (93500, 40)  — Yvonne at promotion 3/5, in-game level 40
#               (181000, 50) — Anteia at promotion 4/5, in-game level 50
#               (346000, 60) — every max-level partner (May 11 snapshot)
#   estimated:  the level-5 / -15 / -20 / -25 / -35 / -45 / -55 rows
PARTNER_EXP_TABLE = [
    (0, 1), (100, 2), (1000, 5), (1800, 10), (12000, 15),
    (20000, 20), (28000, 25), (36300, 30), (70000, 35),
    (93500, 40), (145000, 45), (181000, 50), (251000, 55), (346000, 60),
]

# Runtime-active exp tables. These start as copies of the base tables and
# may be rewritten (in place of the references, not by mutation) by
# LevelDataManager.apply_to_constants() to incorporate user-confirmed
# checkpoints. The base CHARACTER_EXP_TABLE / PARTNER_EXP_TABLE above stay
# pristine so we can always see what was hardcoded vs. user-augmented.
#
# get_level_from_exp consults _active_character_exp_table by default;
# get_partner_level_from_exp explicitly passes _active_partner_exp_table.
_active_character_exp_table = list(CHARACTER_EXP_TABLE)
_active_partner_exp_table = list(PARTNER_EXP_TABLE)

# Affection (formerly "friendship") bonus rewards.
#
# Each row is the CUMULATIVE TOTAL (level, ATK, DEF, HP) at that affection
# level — NOT an increment. The function below just looks up by level for
# values within the table and extrapolates for anything beyond it.
#
# In-game cycle (starting at level 2): +3 ATK -> +1 DEF -> +3 HP, repeat.
#   Level 2 +3 ATK -> totals (3, 0, 0)
#   Level 3 +1 DEF -> totals (3, 1, 0)
#   Level 4 +3 HP  -> totals (3, 1, 3)
#   Level 5 +3 ATK -> totals (6, 1, 3)
#   ... and so on.
FRIENDSHIP_BONUSES = [
    (1, 0, 0, 0),
    (2, 3, 0, 0), (3, 3, 1, 0), (4, 3, 1, 3),
    (5, 6, 1, 3), (6, 6, 2, 3), (7, 6, 2, 6),
    (8, 9, 2, 6), (9, 9, 3, 6), (10, 9, 3, 9),
    (11, 12, 3, 9), (12, 12, 4, 9), (13, 12, 4, 12),
    (14, 15, 4, 12), (15, 15, 5, 12), (16, 15, 5, 15),
    (17, 18, 5, 15), (18, 18, 6, 15), (19, 18, 6, 18),
    (20, 21, 6, 18), (21, 21, 7, 18), (22, 21, 7, 21),
    (23, 24, 7, 21), (24, 24, 8, 21), (25, 24, 8, 24),
    (26, 27, 8, 24), (27, 27, 9, 24), (28, 27, 9, 27),
    (29, 30, 9, 27), (30, 30, 10, 27), (31, 30, 10, 30),
    (32, 33, 10, 30), (33, 33, 11, 30), (34, 33, 11, 33),
    (35, 36, 11, 33), (36, 36, 12, 33), (37, 36, 12, 36),
    (38, 39, 12, 36), (39, 39, 13, 36), (40, 39, 13, 39),
]

# Note: Capture-related constants (GAME_HOSTS, GAME_PORT, PROXY_PORT, OUTPUT_DIR, HOSTS_PATH)
# have been moved to the capture module (capture/constants.py)

EQUIPMENT_SLOTS = {
    1: "I Shock",
    2: "II Suppression",
    3: "III Denial",
    4: "IV Ideal",
    5: "V Desire",
    6: "VI Imagination",
}

SLOT_ORDER = [1, 2, 3, 4, 5, 6]

RARITY = {1: "Common", 2: "Uncommon", 3: "Rare", 4: "Legendary"}

# Updated colors: Orange for Legendary, Blue for Rare, Green for Uncommon
RARITY_COLORS = {
    1: "#888888",      # Common - Gray
    2: "#50C878",      # Uncommon - Green
    3: "#00BFFF",      # Rare - Blue
    4: "#FF8C00",      # Legendary - Orange
}

RARITY_BG_COLORS = {
    1: "#1e1e2e",
    2: "#1e2e1e",      # Uncommon - Green tint
    3: "#1e2535",      # Rare - Blue tint
    4: "#2e2518",      # Legendary - Orange tint
}

RARITY_ICONS = {1: "[C]", 2: "[U]", 3: "[R]", 4: "[L]"}

RARITY_STARTING_SUBSTATS = {
    1: 0, 2: 1, 3: 2, 4: 3,
}

# Stat definitions with min/max roll values
#
# (display_name, short_name, is_percentage, max_roll, min_roll)
#
# A note on roll bounds:
#  - For substat-eligible stats, max_roll/min_roll are the actual per-roll
#    range as observed in-game.
#  - For MAIN-STAT-ONLY stats (the elemental DMG% block below), the values
#    are 0 / 0 as a sentinel meaning "this stat does not roll as a substat."
#    Every consumer that iterates STATS for substat-related work
#    (compute_gs_bounds, calculate_potential's candidate pool,
#    _raw_substat_score) skips entries whose max_roll <= 0, so these can
#    coexist in the dict without polluting GS calculations.
#  - The elemental DMG% values are determined by the fragment's level
#    instead of rolling: starts at +5%, gains a flat +2.2% per Legendary
#    level-up. The optimizer reads the resulting value straight from the
#    captured data; it does not need to compute it.
STATS = {
    "S_ATK_INC_ADD_OUT": ("Flat ATK", "Flat ATK", False, 8.0, 5.0),
    "S_ATK_INC_RATE_OUT": ("ATK%", "ATK%", True, 1.3, 0.8),
    "S_ADDI_ATK_DMG_RATE_INC_ADD": ("Extra DMG%", "Extra DMG%", True, 3.4, 2.7),
    "S_DEF_INC_ADD_OUT": ("Flat DEF", "Flat DEF", False, 5.0, 3.0),
    "S_DEF_INC_RATE_OUT": ("DEF%", "DEF%", True, 1.3, 0.8),
    "S_HP_INC_ADD_OUT": ("Flat HP", "Flat HP", False, 12.0, 10.0),
    "S_HP_INC_RATE_OUT": ("HP%", "HP%", True, 1.3, 0.8),
    "S_CRI_INC_ADD": ("CRate", "CRate", True, 2.0, 1.2),
    "S_CRI_DMG_RATE_INC_ADD": ("CDmg", "CDmg", True, 4.0, 2.4),
    "S_CHARGING_POWER_INC_ADD": ("Ego", "Ego", False, 5.0, 2.0),
    "S_DOT_ATK_DMG_RATE_INC_ADD": ("DoT%", "DoT%", True, 3.4, 2.7),
    # ---- Main-stat-only (slot 5). Not rollable; 0/0 is the sentinel. ----
    "S_RED_DMG_RATE_INC_ADD":    ("Passion DMG%",  "Passion",  True, 0, 0),
    "S_GREEN_DMG_RATE_INC_ADD":  ("Order DMG%",    "Order",    True, 0, 0),
    "S_BLUE_DMG_RATE_INC_ADD":   ("Justice DMG%",  "Justice",  True, 0, 0),
    "S_PURPLE_DMG_RATE_INC_ADD": ("Void DMG%",     "Void",     True, 0, 0),
    "S_ORANGE_DMG_RATE_INC_ADD": ("Instinct DMG%", "Instinct", True, 0, 0),
}

STAT_SHORT_NAMES = {info[0]: info[1] for info in STATS.values()}
ALL_STAT_NAMES = [s[0] for s in STATS.values()]


# ============================================================================
# Display-name overrides (v1.1.0 polish round 3, Item 3)
# ============================================================================
#
# Maps an internal STATS .name (the canonical key used in captured-data
# dicts, set definitions, calculate_build_stats, preset weights, etc.)
# to its user-facing label.
#
# Code that's READING captured data or LOOKING UP in stat dicts continues
# to use the internal key. Code that DISPLAYS a stat name to the user
# should translate through this mapping:
#
#     label = DISPLAY_NAMES.get(stat_key, stat_key)
#
# (The .get() with the key as default makes it safe for stats not in this
# table -- they'll display their internal name unchanged.)
#
# Why this layer instead of renaming STATS directly? Renaming STATS keys
# would cascade through every saved scoring preset, every optimizer
# settings entry, and every set-effect definition; this lookup layer lets
# the rename land in the UI immediately while the data model stays
# backward-compatible. A future change could promote these to the canonical
# names everywhere (with a migration step in PresetManager / OptimizerSettings
# .load to translate old keys to new) -- this dict is the migration map
# when that day comes.
#
# Tabs migrated so far: Optimizer.
# Tabs still showing internal names: Combatants, Memory Fragments,
#   Gear Score / Scoring tab.
DISPLAY_NAMES = {
    "Flat ATK":      "ATK Flat",
    "Flat DEF":      "DEF Flat",
    "Flat HP":       "HP Flat",
    "CRate":         "Crit%",
    "CDmg":          "CDMG%",
    "Extra DMG%":    "Extra%",
    "Passion DMG%":  "Passion%",
    "Order DMG%":    "Order%",
    "Justice DMG%":  "Justice%",
    "Void DMG%":     "Void%",
    "Instinct DMG%": "Instinct%",
}

# Main stats for each slot (using updated names).
# Note: DEF% as a main stat ONLY appears on slot 6 -- corrected in v1.1.0.
# Pre-1.1.0 versions of this file listed DEF% under slots 4 and 5 as well,
# which was incorrect (the in-game data has never had those options). See
# docs/game_formulas.md §2 for the canonical main-stat table.
SLOT_MAIN_STATS = {
    1: ["Flat ATK"],
    2: ["Flat DEF"],
    3: ["Flat HP"],
    4: ["ATK%", "HP%", "CRate", "CDmg"],
    5: ["ATK%", "HP%", "Passion DMG%", "Order DMG%", "Justice DMG%", "Void DMG%", "Instinct DMG%"],
    6: ["ATK%", "DEF%", "HP%", "Ego"],
}

# Maximum main stat values per (slot, stat_name) at Legendary max level.
#
# Read off in-game; documents what `fragment.main_stat.value` should
# converge to for a maxed Legendary fragment. The optimizer doesn't read
# this directly -- it uses fragment.main_stat.value from captured data --
# but the table is useful for:
#   - Reference documentation (see docs/game_formulas.md §2)
#   - Sanity-checking captured values
#   - Future UI affordances (e.g. "this fragment's main stat is at X% of
#     its ceiling")
#
# DEF% only appears on slot 6 (game data confirmed).
MAIN_STAT_VALUES = {
    (1, "Flat ATK"):       22,
    (2, "Flat DEF"):       22,
    (3, "Flat HP"):        37,
    (4, "ATK%"):           25,
    (4, "HP%"):            25,
    (4, "CRate"):          27,
    (4, "CDmg"):           40.8,
    (5, "ATK%"):           25,
    (5, "HP%"):            25,
    (5, "Passion DMG%"):   16,
    (5, "Order DMG%"):     16,
    (5, "Justice DMG%"):   16,
    (5, "Void DMG%"):      16,
    (5, "Instinct DMG%"):  16,
    (6, "ATK%"):           25,
    (6, "DEF%"):           25,
    (6, "HP%"):            25,
    (6, "Ego"):            40,
}

MAX_LEVEL = 5
UPGRADES_PER_RARITY = {3: 3, 4: 4}

# Growth Stone items - maps res_id to (attribute, quality, icon_filename)
GROWTH_STONES = {
    # Passion stones
    3120001: ("Passion", "Common", "growth_stone_passion_common.png"),
    3120002: ("Passion", "Great", "growth_stone_passion_great.png"),
    3120003: ("Passion", "Premium", "growth_stone_passion_premium.png"),
    # Instinct stones
    3120011: ("Instinct", "Common", "growth_stone_instinct_common.png"),
    3120012: ("Instinct", "Great", "growth_stone_instinct_great.png"),
    3120013: ("Instinct", "Premium", "growth_stone_instinct_premium.png"),
    # Void stones
    3120021: ("Void", "Common", "growth_stone_void_common.png"),
    3120022: ("Void", "Great", "growth_stone_void_great.png"),
    3120023: ("Void", "Premium", "growth_stone_void_premium.png"),
    # Order stones
    3120031: ("Order", "Common", "growth_stone_order_common.png"),
    3120032: ("Order", "Great", "growth_stone_order_great.png"),
    3120033: ("Order", "Premium", "growth_stone_order_premium.png"),
    # Justice stones
    3120051: ("Justice", "Common", "growth_stone_justice_common.png"),
    3120052: ("Justice", "Great", "growth_stone_justice_great.png"),
    3120053: ("Justice", "Premium", "growth_stone_justice_premium.png"),
}


def get_level_from_exp(exp: int, exp_table: list = None) -> int:
    """Convert experience points to level with interpolation between
    the table's checkpoints.

    Uses floor semantics (truncation toward zero, equivalent for the
    positive values involved): a character whose exp interpolates to
    "level 59.95" is still in-game level 59, since leveling is discrete.
    The character only reaches level 60 when their exp meets the actual
    level-60 threshold. With every level's checkpoint firmly known there'd
    be no interpolation at all -- table look-ups would suffice -- but for
    the levels we haven't yet confirmed, floored interpolation gives the
    most defensible estimate (a strict lower bound on the level).
    """
    if exp_table is None:
        exp_table = _active_character_exp_table

    if exp <= 0:
        return 1

    prev_exp, prev_level = 0, 1
    for min_exp, lvl in exp_table:
        if exp < min_exp:
            if min_exp > prev_exp:
                progress = (exp - prev_exp) / (min_exp - prev_exp)
                # int() floors for non-negative values, which is what we want.
                return prev_level + int(progress * (lvl - prev_level))
            return prev_level
        prev_exp, prev_level = min_exp, lvl

    # Past the table -- return the highest level it documents. With the
    # built-in tables that's 60; when level-61/62 thresholds are added
    # (manually or via user-confirmed checkpoints flowing through
    # level_data_manager) this naturally extends to whatever the table's
    # top entry is. Previously hardcoded to 60, which capped levels above
    # 60 even when the table knew about them.
    return prev_level


def get_partner_level_from_exp(exp: int) -> int:
    """Convert partner card experience to level via PARTNER_EXP_TABLE.

    Note: a previous version short-circuited exp < 4000 to a linear
    formula (~180 exp/level). That shortcut predated our firm low-end
    data (Douglas at exp=100 = level 2, Zatera at exp=1800 = level 10),
    both of which the linear formula gets wrong. The table now covers
    every level we have data for, so a straight table lookup is correct
    across the full exp range.
    """
    return get_level_from_exp(exp, _active_partner_exp_table)


def get_friendship_bonus(index: int) -> tuple[int, int, int]:
    """Cumulative (ATK, DEF, HP) bonus at the given affection level.

    Looks up the FRIENDSHIP_BONUSES table first (covers the in-game range,
    currently up to level 40); for levels above the table, derives the
    answer from the +3 ATK / +1 DEF / +3 HP cycle.

    Cycle math: counting cumulative bumps as the level increases,
        ATK steps fire at every 3rd level starting from 2: 2, 5, 8, ...
        DEF steps fire at every 3rd level starting from 3: 3, 6, 9, ...
        HP  steps fire at every 3rd level starting from 4: 4, 7, 10, ...
    yielding the closed-form expressions used below.
    """
    if index <= 1:
        return (0, 0, 0)
    for level, atk, def_, hp in FRIENDSHIP_BONUSES:
        if level == index:
            return (atk, def_, hp)
    # Beyond the table — extrapolate from the cycle. Verified against
    # the table's level-40 row (39, 13, 39): ATK=3*((40+1)//3)=39,
    # DEF=40//3=13, HP=3*((40-1)//3)=39.
    atk = 3 * ((index + 1) // 3)
    def_ = index // 3
    hp = 3 * ((index - 1) // 3)
    return (atk, def_, hp)
