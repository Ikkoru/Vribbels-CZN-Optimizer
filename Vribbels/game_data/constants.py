"""
Game constants for CZN.

This module is the single source of truth for game-rule data that
doesn't live on individual characters / partners / fragments:

  - Experience -> level tables for characters and partners (CHARACTER_EXP_TABLE,
    PARTNER_EXP_TABLE) plus the get_level_from_exp / get_partner_level_from_exp
    helpers. Both tables have firm and estimated entries; provenance is
    annotated at each table.

  - Affinity reward bonuses (FRIENDSHIP_BONUSES)
    and the closed-form get_friendship_bonus extrapolation. Each entry
    is the cumulative TOTAL (ATK, DEF, HP) at that level, NOT the
    increment.

  - Equipment slot definitions (EQUIPMENT_SLOTS / SLOT_ORDER) and rarity
    tables (RARITY, RARITY_COLORS, RARITY_BG_COLORS, RARITY_ICONS,
    RARITY_STARTING_SUBSTATS, UPGRADES_PER_RARITY).

  - CLASSES, the six combatant/partner classes. Both characters.py and
    partners.py use these strings; this is the only list of them.

  - Stat definitions (STATS dict) -- the central registry that maps the
    raw enum keys from the captured data to display names, percentage
    flags, and (for substat-eligible stats) per-roll min/max values.
    Main-stat-only stats (elemental DMG%) are marked with max_roll=0 as
    a sentinel; consumers iterating STATS for substat math skip these.

  - SLOT_MAIN_STATS for slot-eligible main stat names; MAX_LEVEL and
    UPGRADES_PER_RARITY for fragment-upgrade math.

  - GROWTH_STONES for the leveling-item registry used by the materials
    display (UI sugar; not part of stat math).


Note on capture-related constants
=================================
GAME_HOSTS, GAME_PORT, PROXY_PORT, OUTPUT_DIR and HOSTS_PATH live in
capture/constants.py: they are about the capture pipeline rather than
about the game's data.
"""

from pathlib import Path
from typing import NamedTuple

# The six combatant/partner classes. Characters (characters.py) and
# partner cards (partners.py) both use these exact strings, and
# PARTNER_CLASS_STATS is keyed by (grade, class).
#
# ADD A NEWLY-RELEASED CLASS HERE. This is the only list of them, and
# the launch-time data check validates every character's and partner's
# `class` against it.
CLASSES = (
    "Controller",
    "Hunter",
    "Psionic",
    "Ranger",
    "Striker",
    "Vanguard",
)

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
# Every checkpoint below was read from the game. Do not interpolate
CHARACTER_EXP_TABLE = [
    (0, 1),       (100, 2),     (200, 3),     (400, 4),     (600, 5),
    (900, 6),     (1300, 7),    (1700, 8),    (2200, 9),    (2800, 10),
    (3400, 11),   (4100, 12),   (4900, 13),   (5700, 14),   (6600, 15),
    (7600, 16),   (8700, 17),   (9900, 18),   (11200, 19),  (12600, 20),
    (14100, 21),  (16200, 22),  (19000, 23),  (22400, 24),  (26400, 25),
    (31100, 26),  (36400, 27),  (42300, 28),  (48800, 29),  (56000, 30),
    (63900, 31),  (72000, 32),  (80300, 33),  (88800, 34),  (97500, 35),
    (106400, 36), (115500, 37), (124800, 38), (134300, 39), (144000, 40),
    (154800, 41), (167100, 42), (180900, 43), (196200, 44), (213000, 45),
    (231400, 46), (251300, 47), (272700, 48), (295600, 49), (320000, 50),
    (346000, 51), (374900, 52), (407100, 53), (442400, 54), (480800, 55),
    (522400, 56), (567100, 57), (614900, 58), (665900, 59), (720000, 60),
    (778200, 61),
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

# Affinity bonus rewards. The game calls this Affinity; the
# identifiers here say FRIENDSHIP, inherited from upstream. Keep
# user-visible text on the game's word.
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

# Capture-related constants (GAME_HOSTS, GAME_PORT, PROXY_PORT,
# OUTPUT_DIR, HOSTS_PATH) live in capture/constants.py, not here.

EQUIPMENT_SLOTS = {
    1: "I Shock",
    2: "II Suppression",
    3: "III Denial",
    4: "IV Ideal",
    5: "V Desire",
    6: "VI Imagination",
}

SLOT_ORDER = [1, 2, 3, 4, 5, 6]

# In-game rarity tiers, highest to lowest: Mythic, Legendary, Rare,
# Uncommon, Normal. Memory Fragments only ever come in the middle three
# -- Mythic and Normal exist in the game but not for MFs -- so the tiers
# tracked here stop at 4. Nearly every account uses Legendary MFs
# exclusively; they're easy to obtain.
RARITY = {1: "Normal", 2: "Uncommon", 3: "Rare", 4: "Legendary"}

# Legendary reads as gold in-game; orange is used here because it stays
# legible on the dark background.
RARITY_COLORS = {
    1: "#888888",      # Normal - Gray
    2: "#50C878",      # Uncommon - Green
    3: "#00BFFF",      # Rare - Blue
    4: "#FF8C00",      # Legendary - Orange (gold in-game)
}

RARITY_BG_COLORS = {
    1: "#1e1e2e",
    2: "#1e2e1e",      # Uncommon - Green tint
    3: "#1e2535",      # Rare - Blue tint
    4: "#2e2518",      # Legendary - Orange tint
}

RARITY_ICONS = {1: "[N]", 2: "[U]", 3: "[R]", 4: "[L]"}

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
# Display-name overrides
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
# Not every tab translates: grep for DISPLAY_NAMES to see which do.
# A tab that doesn't shows the internal key instead, which is a display
# inconsistency rather than a fault.
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

# Main stats for each slot.
# DEF% appears as a main stat on slot 6 ONLY -- the game has never
# offered it on slots 4 or 5, however plausible that looks. See
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

# MAX_LEVEL is LEGENDARY's cap. The cap is rarity-dependent: Legendary 5,
# Rare 4, Uncommon 3 -- each rarity starts with one fewer substat and
# gets one fewer level-up, so every rarity converges on 4 substats at max
# level. See MAX_LEVEL_PER_RARITY and docs/game_formulas.md §2.
MAX_LEVEL = 5
MAX_LEVEL_PER_RARITY = {2: 3, 3: 4, 4: 5}
# Level-ups that roll into an EXISTING substat, i.e. the level-ups left
# after the fragment has gained its fourth substat:
#   max_level - (4 - starting_substats)
# Only `max(values())` is consumed now (as the GS bounds anchor in
# models/memory_fragment.py); remaining-upgrade counts come from
# MAX_LEVEL_PER_RARITY minus the fragment's level instead, which is exact.
UPGRADES_PER_RARITY = {2: 0, 3: 2, 4: 4}

# Growth Stone items - maps res_id to (attribute, quality, icon_filename)
GROWTH_STONES = {
    # Passion stones
    3120001: ("Passion", "Common", "icon_item_card_levelup_love_1.png"),
    3120002: ("Passion", "Great", "icon_item_card_levelup_love_2.png"),
    3120003: ("Passion", "Premium", "icon_item_card_levelup_love_3.png"),
    # Instinct stones
    3120011: ("Instinct", "Common", "icon_item_card_levelup_instinct_1.png"),
    3120012: ("Instinct", "Great", "icon_item_card_levelup_instinct_2.png"),
    3120013: ("Instinct", "Premium", "icon_item_card_levelup_instinct_3.png"),
    # Void stones
    3120021: ("Void", "Common", "icon_item_card_levelup_creed_1.png"),
    3120022: ("Void", "Great", "icon_item_card_levelup_creed_2.png"),
    3120023: ("Void", "Premium", "icon_item_card_levelup_creed_3.png"),
    # Order stones
    3120031: ("Order", "Common", "icon_item_card_levelup_norms_1.png"),
    3120032: ("Order", "Great", "icon_item_card_levelup_norms_2.png"),
    3120033: ("Order", "Premium", "icon_item_card_levelup_norms_3.png"),
    # Justice stones
    3120051: ("Justice", "Common", "icon_item_card_levelup_narcissism_1.png"),
    3120052: ("Justice", "Great", "icon_item_card_levelup_narcissism_2.png"),
    3120053: ("Justice", "Premium", "icon_item_card_levelup_narcissism_3.png"),
}

# The tables below name the same shape as GROWTH_STONES: a res_id, what
# distinguishes it inside its family, and the icon file that draws it.
#
# **A res_id's own digits carry the family, the group and the tier**, as
# `FFFF0GT` -- so `3130043` is family 313 (Combatant promotion), group 4
# and tier 3. The group is the CLASS in the promotion families where it
# is the Element in the stones above, which is why those have six groups
# and the stones five.
#
# The icon names are the game's own. Two classes are spelled differently
# there than in game: `defender` draws Vanguard and `psionics` draws
# Psionic. Nothing in the assets says so -- what settles it is the class
# digit against the six class names in `characters.py`, plus in-game
# counts read against the ids.

# Combatant promotion materials - res_id to (class, tier, icon_filename).
COMBATANT_PROMOTION = {
    # Striker
    3130001: ("Striker", "Common", "icon_item_char_ascend_striker_1.png"),
    3130002: ("Striker", "Advanced", "icon_item_char_ascend_striker_2.png"),
    3130003: ("Striker", "Premium", "icon_item_char_ascend_striker_3.png"),
    # Vanguard
    3130011: ("Vanguard", "Common", "icon_item_char_ascend_defender_1.png"),
    3130012: ("Vanguard", "Advanced", "icon_item_char_ascend_defender_2.png"),
    3130013: ("Vanguard", "Premium", "icon_item_char_ascend_defender_3.png"),
    # Hunter
    3130021: ("Hunter", "Common", "icon_item_char_ascend_hunter_1.png"),
    3130022: ("Hunter", "Advanced", "icon_item_char_ascend_hunter_2.png"),
    3130023: ("Hunter", "Premium", "icon_item_char_ascend_hunter_3.png"),
    # Ranger
    3130031: ("Ranger", "Common", "icon_item_char_ascend_ranger_1.png"),
    3130032: ("Ranger", "Advanced", "icon_item_char_ascend_ranger_2.png"),
    3130033: ("Ranger", "Premium", "icon_item_char_ascend_ranger_3.png"),
    # Psionic
    3130041: ("Psionic", "Common", "icon_item_char_ascend_psionics_1.png"),
    3130042: ("Psionic", "Advanced", "icon_item_char_ascend_psionics_2.png"),
    3130043: ("Psionic", "Premium", "icon_item_char_ascend_psionics_3.png"),
    # Controller
    3130051: ("Controller", "Common", "icon_item_char_ascend_controller_1.png"),
    3130052: ("Controller", "Advanced", "icon_item_char_ascend_controller_2.png"),
    3130053: ("Controller", "Premium", "icon_item_char_ascend_controller_3.png"),
}

# Partner promotion materials - res_id to (class, tier, icon_filename).
PARTNER_PROMOTION = {
    # Striker
    3140001: ("Striker", "Common", "icon_item_supporter_classup_striker_1.png"),
    3140002: ("Striker", "Advanced", "icon_item_supporter_classup_striker_2.png"),
    3140003: ("Striker", "Premium", "icon_item_supporter_classup_striker_3.png"),
    # Vanguard
    3140011: ("Vanguard", "Common", "icon_item_supporter_classup_defender_1.png"),
    3140012: ("Vanguard", "Advanced", "icon_item_supporter_classup_defender_2.png"),
    3140013: ("Vanguard", "Premium", "icon_item_supporter_classup_defender_3.png"),
    # Hunter
    3140021: ("Hunter", "Common", "icon_item_supporter_classup_hunter_1.png"),
    3140022: ("Hunter", "Advanced", "icon_item_supporter_classup_hunter_2.png"),
    3140023: ("Hunter", "Premium", "icon_item_supporter_classup_hunter_3.png"),
    # Ranger
    3140031: ("Ranger", "Common", "icon_item_supporter_classup_ranger_1.png"),
    3140032: ("Ranger", "Advanced", "icon_item_supporter_classup_ranger_2.png"),
    3140033: ("Ranger", "Premium", "icon_item_supporter_classup_ranger_3.png"),
    # Psionic
    3140041: ("Psionic", "Common", "icon_item_supporter_classup_psionics_1.png"),
    3140042: ("Psionic", "Advanced", "icon_item_supporter_classup_psionics_2.png"),
    3140043: ("Psionic", "Premium", "icon_item_supporter_classup_psionics_3.png"),
    # Controller
    3140051: ("Controller", "Common", "icon_item_supporter_classup_controller_1.png"),
    3140052: ("Controller", "Advanced", "icon_item_supporter_classup_controller_2.png"),
    3140053: ("Controller", "Premium", "icon_item_supporter_classup_controller_3.png"),
}

# Levelling materials - res_id to (what it levels, tier, icon_filename).
EXP_MATERIALS = {
    # Battle Memory, for Combatants
    3100001: ("Combatant", "Basic", "icon_item_char_level_materal_1.png"),
    3100002: ("Combatant", "Advanced", "icon_item_char_level_materal_2.png"),
    3100003: ("Combatant", "Premium", "icon_item_char_level_materal_3.png"),
    # Support Data, for Partners
    3100021: ("Partner", "Basic", "icon_item_supporter_level_materal_1.png"),
    3100022: ("Partner", "Advanced", "icon_item_supporter_level_materal_2.png"),
    3100023: ("Partner", "Premium", "icon_item_supporter_level_materal_3.png"),
}

# Everything else identified so far - res_id to (name, icon_filename).
# These have no group and no tier: each is one item, and the first
# three are held as CURRENCIES rather than in the item list.
NAMED_MATERIALS = {
    2000001: ("Units", "currency_unit.png"),
    2100001: ("Universal Tactical Certificate", "currency_combatant_ascend_public.png"), # Equivalent to Common Manual of any class (Combatant Promotion material)
    2100002: ("Universal Support Certificate", "currency_supporter_ascend_public.png"),  # Equivalent to Common Certificate of any class (Partner Promotion material)
    2100003: ("Potential Disk", "currency_ego_tree_public.png"),                         # Equivalent to Common Growth Stone of any Element (Potential leveling material)
    2000027: ("Loot Certification Card", "currency_chaos_week_reward.png"), # Used to exchange for Chaos run rewards. Max 4 stored. 4 granted every Sunday 18:00 UTC
    2000036: ("Reason", "currency_chaos_assault_stamina.png"),              # Used to exchange for Sortie run rewards. Max 9 stored. 3 granted every Sunday 18:00 UTC
    3000003: ("Undetermined Ego Crystal", "icon_item_card_levelup_all_1.png"), # Used for the final level of specific Potential Nodes
    3110001: ("Eye of Wailing Prodigal", "icon_item_akcalion_3.png"),          # Used for the final several levels of specific Potential Nodes
    3110004: ("Shards of Condemnation", "currency_chaos.png"),                 # Used for the final several levels of specific Potential Nodes
}

#
# Items held with an EXPIRY rather than as a count - res_id to
# (name, icon_filename).
#
# These live in `inventory.period_items`, not in the item list, and are
# nested one level deeper than everything else: the entry is the ITEM
# and its `value` lists the COPIES, one per copy with its own
# `end_time`. So the number held is the length of that inner list, and
# there is no `amount` anywhere to read it from. `period_items.held` is
# what knows the shape.
PERIOD_ITEMS = {
    3920026: ("Time-Limited Command Delegation Module - 14 Days",
              "currency_chaos_delegation_module.png"),  # Used to speed up Chaos runs. Expire 14 days after acquisition.
}

# TODO: `Great Rift Weekly Score` is NOT IN THE SNAPSHOT either. The
# server sends it and the addon does not keep it -- the debug log has
# it under two paths of one `disaster` payload, both reading the same
# figure today:
#
#   /disaster_boss_rank_entities/disaster_s04/disaster_s04_rank_01/week_total_score
#   /disaster_boss_rank_entities/disaster_s04/disaster_s04_rank_01/best_score
#
# `week_total_score` is the one the name matches; `best_score` sharing
# its value is what a first week looks like, not evidence. Reaching
# either means the addon storing `disaster_boss_rank_entities`.

# The Communication Pass -- `currency_town_visit.png`, used for
# Counseling and Excursions -- HAS NO ID. It is not an item and not a
# currency: a debug capture taken while one was spent shows the
# `town / run_visit` reply carrying what the visit GAVE and debiting
# nothing, with no negative `diff` anywhere and no id moving between
# the captures either side of it.
#
# **The count is DERIVED, not stored.** It is the daily allowance less
# what has been spent today:
#
#   5 - characters.town_data.day_changeable_data.use_town_visit_count
#
# Read against two readings off the screen: 0 spent showed 5 passes and
# 1 spent showed 4. The counter agrees with the `town_visit_info`
# board's own visited flags in every snapshot, and
# `town_visit_reset_time` beside it is when it goes back to 0 -- 18:00
# UTC, which is when the game says the allowance is granted.

# TODO: name the twenty ARCHIVE GIFT items, res_id 3300001-3300020.
# What they are is settled: `characters.archive_gift_data` is keyed by
# combatant and lists exactly these ids in its `item_id_list`, with
# `reward_received_item_id_list` saying which have been handed over.
# What is missing is each one's NAME and icon, which no payload spells.


# Item rarity, rarest last, mapped to the plate that draws it. Two of
# the five are spelled differently by the assets than by the game --
# `legend` draws Legendary and `unique` draws Mythic -- which is why
# the tables carry the game's word and this turns it into a filename.
#
# NOT the same vocabulary as RARITY_COLORS further up: that is Memory
# Fragments, four grades starting at Normal, against five here.
RARITY_PLATES = {
    "Common": "common",
    "Uncommon": "uncommon",
    "Rare": "rare",
    "Legendary": "legend",
    "Mythic": "unique",
}

# What a TIER word is worth as a rarity. Every shaped table states a
# tier in its second field, so a stone, a manual and a battle memory of
# the same tier plate alike and none of the 57 rows has to say so.
#
# Uncommon is absent deliberately: no item in these tables is one.
TIER_RARITY = {
    "Common": "Common",
    "Basic": "Common",
    "Great": "Rare",
    "Advanced": "Rare",
    "Premium": "Legendary",
}

# The items with no tier for the table above to read, by name.
NAME_RARITY = {
    "Units": "Common",
    "Universal Tactical Certificate": "Legendary",
    "Universal Support Certificate": "Legendary",
    "Potential Disk": "Legendary",
    "Loot Certification Card": "Legendary",
    "Reason": "Legendary",
    "Eye of Wailing Prodigal": "Legendary",
    "Shards of Condemnation": "Legendary",
    "Undetermined Ego Crystal": "Mythic",
    "Time-Limited Command Delegation Module - 14 Days": "Mythic",
}


# Every table above, in the order a lookup should try them. The five
# differ in what their second field means -- an Element, a class, what
# a material levels, or nothing at all -- so a caller wanting only the
# art goes through `item_art` rather than unpacking a row itself.
ITEM_TABLES = (GROWTH_STONES, COMBATANT_PROMOTION, PARTNER_PROMOTION,
               EXP_MATERIALS, NAMED_MATERIALS, PERIOD_ITEMS)


class ItemArt(NamedTuple):
    """What draws one item: its icon, and the plate behind it.

    `rarity` is the game's word, which `RARITY_PLATES` turns into a
    filename. "" where nothing names one.
    """
    icon: str
    rarity: str = ""

    @property
    def plate(self):
        """The plate's filename, or "" for an item with no rarity."""
        word = RARITY_PLATES.get(self.rarity)
        return f"bg_item_rarity_{word}.png" if word else ""


def item_art(res_id):
    """The art for an id from any of the item tables, or None.

    The icon is the first field naming a `.png`; what comes before it
    says what the item is, and what comes after it -- if anything --
    states a rarity outright.

    **A row states its rarity only where nothing can derive it.** A
    shaped row carries a TIER, and `TIER_RARITY` prices every tier
    word; a named row carries a NAME, and `NAME_RARITY` prices those.
    So adding a rarity to a table is adding a word to one of those two
    rather than editing 61 rows, and a row that does state one wins
    over both.
    """
    for table in ITEM_TABLES:
        row = table.get(res_id)
        if row is None:
            continue
        icons = [i for i, field in enumerate(row)
                 if isinstance(field, str) and field.endswith(".png")]
        if not icons:
            return None
        at = icons[0]
        after = row[at + 1:]
        if after:
            rarity = after[0]
        elif at >= 2:
            rarity = TIER_RARITY.get(row[1], "")
        else:
            rarity = NAME_RARITY.get(row[0], "")
        return ItemArt(row[at], rarity)
    return None

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
        exp_table = CHARACTER_EXP_TABLE

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

    # Past the table -- return the highest level it DOCUMENTS, not a
    # hardcoded cap. Adding level-61/62 thresholds to the table extends
    # this to whatever its top entry is, with nothing here to update.
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
    return get_level_from_exp(exp, PARTNER_EXP_TABLE)


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
