"""
Optimization engine for CZN Memory Fragment gear builds.

This module is the link between captured game data (the snapshot JSON)
and the rest of the program. It iterates the captured characters,
resolves their relationships (partner, equipped pieces, presets), and
computes the derived stats that the UI displays.

Pipeline (one call to refresh / load):
   parse snapshot -> build character_info -> calculate_build_stats

character_info is a name-keyed dict of CharacterInfo objects, each
carrying everything the UI needs to render that character's row plus
the equipped-gear detail panel.

The damage formula (Final ATK / Final DEF / Final HP)
=====================================================

The optimizer uses a LAYERED formula that distinguishes "inner" sources
(base stat, partner flat, MF%, potential% nodes, gear flat, affection
flat) from "outer" multipliers (partner %, equipment %, equipment flat):

    inner = (base_stat + partner_flat) * (1 + MF% + potential_node%)
            + gear_flat
            + affection_flat
    Final = inner * (1 + partner_pct + equipment_pct)
            + equipment_flat

Where each piece comes from:

  base_stat       Character's level-60 stat from CHARACTERS dict. (The
                  optimizer treats every character as level >=60 for
                  stat purposes regardless of actual level.)
  partner_flat    Flat ATK/DEF/HP bonus from the equipped partner
                  card's class-based stat table (PARTNER_CLASS_STATS).
  MF%             Substats and main-stat %-type values from all 6
                  Memory Fragments combined.
  potential_node% Percentage bonuses from the character's level-40,
                  -50, -60 potential nodes. Flat bonuses from nodes
                  10/20/30 don't go here -- they're inside the
                  gear_flat layer below.
  gear_flat       Flat ATK/DEF/HP bonuses: nodes 10/20/30 + the flat
                  main stat / substat values from equipped pieces.
  affection_flat  Cumulative ATK/DEF/HP from the partner's affection
                  (formerly "friendship") rewards table.
  partner_pct     Partner passive bonuses expressed as %.
  equipment_pct   Outer-layer % multipliers from equipment (rare;
                  most builds have 0 here).
  equipment_flat  Outer-layer flat bonuses from equipment (the
                  EQUIPMENT_FLAT_* constants).

Why layered? Because in-game tooltips reveal that some bonuses scale
the inner total (the "main" stat box including its substats) while
others sit outside it. The previous version of this formula treated
everything as a single big sum, which over-credited percentage bonuses
on top of percentage bonuses. The layered form matches the in-game
math closely enough to compare builds reliably.

Heuristic stats removed
=======================
A previous iteration computed derived stats like EHP, Avg DMG, Max CD,
and a Bruiser score. These were dropped because they varied unpredictably
between game versions and weren't actionable. The Final ATK/DEF/HP plus
GS columns now carry the comparison work; build-quality judgment lives
in the user's preset weights, which is where it belongs.
"""

import json
import itertools
from typing import Callable
from pathlib import Path

from models import MemoryFragment, CharacterInfo, UserInfo
from game_data import (
    get_character, get_character_by_name, get_partner,
    get_level_from_exp, get_partner_level_from_exp,
    get_friendship_bonus, parse_potential_node_ids,
    get_partner_stats, get_partner_passive_stats, get_potential_stat_bonus,
    SETS, SLOT_ORDER, ALL_STAT_NAMES
)
# Direct module-path import for the newly-added helper to avoid relying
# on game_data/__init__.py re-exporting it.
from game_data.characters import get_character_stats_at_level


class GearOptimizer:
    """
    Main optimization engine for Memory Fragment gear builds.

    Handles:
    - Loading capture data from JSON files
    - Parsing character and partner information
    - Managing gear inventory and equipped status
    - Running optimization algorithm to find best builds
    - Calculating final stats for gear combinations
    """

    def __init__(self):
        self.fragments: list[MemoryFragment] = []
        self.characters: dict[str, list[MemoryFragment]] = {}
        self.character_info: dict[str, CharacterInfo] = {}
        self.user_info: UserInfo = UserInfo()
        self.unequipped: list[MemoryFragment] = []
        self.capture_time = ""
        self.priorities: dict[str, int] = {name: 0 for name in ALL_STAT_NAMES}
        self.raw_data = {}
        # Optional reference to SettingsManager. Reserved for the future
        # Optimizer-tab "Optimize at" toggle: that tab will read its own
        # level setting from SettingsManager and pass it to
        # calculate_build_stats as the `effective_level` argument.
        # Currently unread (Combatants-tab "Calculate GS for lvl:" is
        # GS-scoped and doesn't go through this hook). Injected by
        # czn_optimizer_gui.py at startup.
        self.settings_manager = None

    def load_data(self, filepath: str):
        """
        Load capture data from JSON file.

        Parses inventory (piece_items) and character data, creating MemoryFragment
        objects and CharacterInfo objects.

        Args:
            filepath: Path to capture JSON file
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        self.raw_data = data
        self.capture_time = data.get("capture_time", "Unknown")
        self.fragments = []
        self.characters = {}
        self.character_info = {}
        self.unequipped = []

        if "inventory" in data:
            inventory = data["inventory"]
            piece_items = inventory.get("piece_items", [])
        elif "piece_items" in data:
            piece_items = data["piece_items"]
        else:
            piece_items = []

        char_data = data.get("characters", {})
        self._parse_character_data(char_data)

        for item in piece_items:
            try:
                fragment = MemoryFragment.from_json(item)
                fragment.calculate_base_score()
                fragment.calculate_potential()
                fragment.calculate_priority_score(self.priorities)
                self.fragments.append(fragment)
                if fragment.equipped_to:
                    if fragment.equipped_to not in self.characters:
                        self.characters[fragment.equipped_to] = []
                    self.characters[fragment.equipped_to].append(fragment)
                else:
                    self.unequipped.append(fragment)
            except Exception as e:
                print(f"Error parsing fragment: {e}")

        for char_gear in self.characters.values():
            char_gear.sort(key=lambda f: f.slot_num)

    def _parse_character_data(self, char_data: dict):
        """
        Parse character and partner data from capture.

        Extracts user info, character progression (level, ascension, limit break),
        partner assignments, and potential node unlocks.

        Args:
            char_data: Character data dictionary from capture
        """
        if not char_data:
            return

        user = char_data.get("user", {})
        if user:
            self.user_info = UserInfo(
                nickname=user.get("nickname", ""),
                level=user.get("lv", 1),
                login_total=user.get("login_total_count", 0),
                login_continuous=user.get("login_continuous_count", 0),
                login_highest_continuous=user.get("highest_login_continuous_count", 0),
            )

        char_items = char_data.get("characters", [])
        if isinstance(char_items, dict):
            char_items = char_items.get("characters", []) or char_items.get("char_items", [])

        partner_lookup = {}
        hero_items = []

        # Lookup keyed by *instance id* covering EVERY item in char_items —
        # used as a fallback when a character's partner_id points at a partner
        # whose res_id isn't in PARTNERS. Without this, we'd lose the partner's
        # res_id entirely (and couldn't tell the user what to add to partners.py).
        all_items_by_id = {char.get("id", 0): char for char in char_items}

        for char in char_items:
            res_id = char.get("res_id", 0)
            # Check if res_id exists in PARTNERS dict (more accurate than range check)
            partner_data = get_partner(res_id)
            if partner_data.get("name") != "Unknown":  # It's a known partner
                partner_lookup[char.get("id", 0)] = char
            else:
                hero_items.append(char)

        # Stash for any consumer that needs raw entries by instance id
        # (e.g., heroes_tab to show res_id for unknown equipped partners).
        self.all_items_by_id = all_items_by_id

        for char in hero_items:
            res_id = char.get("res_id", 0)
            char_data = get_character(res_id)
            name = char_data.get("name", f"Unknown ({res_id})")

            if not name or name == "Unknown" or name.startswith("Unknown ("):
                continue

            exp = char.get("exp", 0)
            level = get_level_from_exp(exp)
            ascend = char.get("ascend", 0)
            # Promotion (ascend) gates the level cap: each tier raises it by
            # 10. The final tier (ascend 5) was bumped from /60 to /62 in
            # a later game update, while lower tiers keep their original
            # caps. Anything beyond ascend 5 is forward-compatibility:
            # treat the same as the top tier.
            max_level = 62 if ascend >= 5 else (ascend + 1) * 10
            limit_break = char.get("limit_break", 0)
            friendship_index = char.get("friendship_reward_index", 1)
            friendship_bonus = get_friendship_bonus(friendship_index)

            partner_id = char.get("partner_id", 0) or char.get("partner", 0)
            partner_name = ""
            partner_res_id = 0
            partner_exp = 0
            partner_level = 1
            partner_ascend = 0
            partner_max_level = 10
            partner_limit_break = 0

            if partner_id and partner_id in partner_lookup:
                partner = partner_lookup[partner_id]
                partner_res_id = partner.get("res_id", 0)
                partner_data = get_partner(partner_res_id)
                partner_name = partner_data.get("name", f"Unknown ({partner_res_id})")
                partner_exp = partner.get("exp", 0)
                partner_level = get_partner_level_from_exp(partner_exp)  # Use partner exp table
                partner_ascend = partner.get("ascend", 0)
                partner_max_level = (partner_ascend + 1) * 10
                # Cap partner level at max
                partner_level = min(partner_level, partner_max_level)
                partner_limit_break = partner.get("limit_break", 0)
            elif partner_id and partner_id in all_items_by_id:
                # Equipped partner whose res_id isn't in PARTNERS: still
                # recover the res_id from the raw entry so it can be shown
                # in the UI (so the user knows what to add to partners.py).
                # partner_name stays empty -> heroes_tab renders the "Unknown
                # partner" message instead of a fake card with default values.
                partner = all_items_by_id[partner_id]
                partner_res_id = partner.get("res_id", 0)

            # Parse potential node IDs
            potential_str = char.get("potential_node_ids", "[]")
            potential_nodes = parse_potential_node_ids(potential_str, res_id)
            potential_50_level = potential_nodes.get(50, 0)
            potential_60_level = potential_nodes.get(60, 0)

            self.character_info[name] = CharacterInfo(
                res_id=res_id, name=name, exp=exp, level=level, ascend=ascend,
                max_level=max_level, limit_break=limit_break,
                friendship_index=friendship_index, friendship_bonus=friendship_bonus,
                partner_id=partner_id, partner_name=partner_name,
                partner_res_id=partner_res_id, partner_exp=partner_exp,
                partner_level=partner_level, partner_ascend=partner_ascend,
                partner_max_level=partner_max_level, partner_limit_break=partner_limit_break,
                potential_node_ids=list(potential_nodes.keys()),
                potential_50_level=potential_50_level,
                potential_60_level=potential_60_level,
            )

    def recalculate_scores(self):
        """Recalculate priority scores for all fragments."""
        for f in self.fragments:
            f.calculate_priority_score(self.priorities)

    def get_gear_by_slot(self, slot_num: int, include_equipped: bool = True,
                         exclude_char: str = None, excluded_heroes: list[str] = None,
                         required_sets: list[int] = None,
                         required_main: list[str] = None, top_percent: float = 100,
                         use_priority_score: bool = False, min_rarity: int = 2) -> list[MemoryFragment]:
        """
        Get filtered and ranked gear for a specific slot.

        Args:
            slot_num: Equipment slot (1-6)
            include_equipped: Include equipped gear
            exclude_char: Exclude gear equipped to this character
            excluded_heroes: List of characters to exclude gear from
            required_sets: Filter by set IDs
            required_main: Filter by main stat names (for slots 4-6)
            top_percent: Keep only top X% by score
            use_priority_score: Use priority score instead of gear score
            min_rarity: Minimum rarity (1=Common, 2=Uncommon, 3=Rare, 4=Legendary)

        Returns:
            List of MemoryFragment objects matching filters, sorted by score
        """
        candidates = [f for f in self.fragments if f.slot_num == slot_num and f.rarity_num >= min_rarity]

        if excluded_heroes:
            candidates = [f for f in candidates if f.equipped_to not in excluded_heroes]

        if not include_equipped:
            candidates = [f for f in candidates if not f.equipped_to or f.equipped_to == exclude_char]

        if required_sets:
            candidates = [f for f in candidates if f.set_id in required_sets]

        if required_main and slot_num in [4, 5, 6]:
            candidates = [f for f in candidates if f.main_stat and f.main_stat.name in required_main]

        if use_priority_score:
            candidates.sort(key=lambda f: -f.priority_score)
        else:
            candidates.sort(key=lambda f: -f.gear_score)

        count = max(1, int(len(candidates) * top_percent / 100))
        return candidates[:count]

    # Equipment is a separate item system from Memory Fragments. The program
    # doesn't capture which Equipment a character has, so we model it as a
    # constant — Legendary tier (the most common endgame target). These values
    # can be edited if the user wants a different default.
    #   Legendary: 82 ATK / 31 DEF / 83 HP    (the values used here)
    #   Other:     74 ATK / 28 DEF / 75 HP    (lower tier)
    #              90 ATK / 34 DEF / 91 HP    (rarer/higher tier)
    EQUIPMENT_FLAT_ATK = 82
    EQUIPMENT_FLAT_DEF = 31
    EQUIPMENT_FLAT_HP = 83
    # Equipment ATK%/DEF%/HP% ranges from 0% to 18% in-game; 0% is by far the
    # most common (only some very rare Equipment provides it). Default to 0;
    # since Equipment is constant per character, this only affects displayed
    # Final ATK/DEF/HP values, not which fragment combos win in the optimizer.
    EQUIPMENT_ATK_PCT = 0.0
    EQUIPMENT_DEF_PCT = 0.0
    EQUIPMENT_HP_PCT = 0.0

    def calculate_build_stats(self, gear: list[MemoryFragment],
                               char_name: str = None,
                               effective_level: int = None) -> dict[str, float]:
        """
        Calculate final stats for a gear build.

        Implements the Final ATK / DEF / HP formula:

          inner_X = (Base X + Partner X) * (1 + Memory_Fragment_X% + Potential_X%)
                    + Gear_Flat_X + Affection_Flat_X
          Final X = inner_X * (1 + Partner_X% + Equipment_X%) + Equipment_Flat_X

        where (using ATK as an illustration; DEF and HP are analogous):
          - Base ATK            = character's base ATK at level cap
          - Partner ATK         = partner card's flat ATK contribution (level-scaled)
          - Memory Fragment ATK%= sum of substat + main-stat ATK% across all
                                  6 equipped fragments, plus set-bonus ATK%
          - Potential ATK%      = bonuses from potential nodes 50 & 60
          - Gear Flat ATK       = sum of substat + main-stat Flat ATK across
                                  all 6 equipped fragments
          - Affection Flat ATK  = the friendship/affection bonus
          - Partner ATK%        = partner's passive ATK% bonus
          - Equipment ATK%      = constant (Equipment is a separate system not
                                  captured by the optimizer)
          - Equipment Flat ATK  = constant (Legendary tier — see above)

        Args:
            gear: List of 6 MemoryFragment objects (one per slot)
            char_name: Character name (optional, for base stats)

        Returns:
            Dictionary with Final ATK/DEF/HP, CRate, CDmg, the summed substat
            % buckets (informational), and Ego / Extra DMG% / DoT%.
        """
        base_atk, base_def, base_hp, base_cr, base_cd = 0, 0, 0, 0, 125.0

        if char_name:
            char_data = get_character_by_name(char_name)
            # Resolve the level at which to read base stats.
            #
            # Priority:
            #   1. effective_level argument from the caller (this is how
            #      the future Optimizer-tab "Optimize at" toggle will pass
            #      its tab-scoped value; the Combatants-tab "Calculate GS
            #      for lvl:" setting is GS-scoped and intentionally does
            #      NOT flow through here).
            #   2. max(60, actual character level), clamped to 62.
            #   3. 60 fallback.
            #
            # Optimizer's contract: stats are computed at level >= 60. For
            # characters below 60 we still use the level-60 baseline (their
            # in-game stats would be lower, but the optimizer exists to
            # compare endgame builds, not model mid-level progression).
            if effective_level is None:
                actual_level = (self.character_info[char_name].level
                                if char_name in self.character_info else 60)
                effective_level = max(60, min(62, actual_level))
            else:
                try:
                    effective_level = max(60, min(62, int(effective_level)))
                except (ValueError, TypeError):
                    effective_level = 60
            # get_character_stats_at_level applies LEVEL_61_BONUS / LEVEL_62_BONUS
            # additions when the level is 61/62. While those bonuses are still
            # -1 placeholders this is a no-op and base stats stay at level-60
            # values; once real bonus data lands, the override starts mattering.
            scaled = get_character_stats_at_level(char_data, effective_level)
            base_atk = scaled["base_atk"]
            base_def = scaled["base_def"]
            base_hp = scaled["base_hp"]
            base_cr = char_data.get("base_crit_rate", 0)
            base_cd = char_data.get("base_crit_dmg", 125.0)

        # Affection (friendship) flat bonuses + partner-card flat stats.
        affection_atk, affection_def, affection_hp = 0, 0, 0
        partner_flat_atk, partner_flat_def, partner_flat_hp = 0, 0, 0
        partner_passive_stats = {}
        potential_stats = {}  # Potential-node bonuses

        if char_name and char_name in self.character_info:
            char_info = self.character_info[char_name]
            fb = char_info.friendship_bonus
            affection_atk, affection_def, affection_hp = fb[0], fb[1], fb[2]

            if char_info.partner_res_id:
                partner_stats = get_partner_stats(char_info.partner_res_id, char_info.partner_level)
                partner_flat_atk = partner_stats["atk"]
                partner_flat_def = partner_stats["def"]
                partner_flat_hp = partner_stats["hp"]

                partner_passive_stats = get_partner_passive_stats(
                    char_info.partner_res_id, char_info.partner_limit_break
                )

            if char_info.potential_50_level > 0:
                stat_type, bonus = get_potential_stat_bonus(
                    char_info.res_id, 50, char_info.potential_50_level
                )
                if stat_type:
                    potential_stats[stat_type] = potential_stats.get(stat_type, 0) + bonus

            if char_info.potential_60_level > 0:
                stat_type, bonus = get_potential_stat_bonus(
                    char_info.res_id, 60, char_info.potential_60_level
                )
                if stat_type:
                    potential_stats[stat_type] = potential_stats.get(stat_type, 0) + bonus

        # ----- Memory Fragment (substats + main stats) -----------------------
        # Sum % and flat contributions from the 6 fragments. Set bonuses are
        # applied below and lumped into the same "Memory Fragment %" bucket
        # since they're triggered by gear pieces.
        mf_atk_pct, mf_def_pct, mf_hp_pct = 0, 0, 0
        gear_flat_atk, gear_flat_def, gear_flat_hp = 0, 0, 0
        crit_rate, crit_dmg = 0, 0
        ego, extra_dmg, dot_dmg = 0, 0, 0

        for piece in gear:
            piece_stats = piece.get_total_stats()
            mf_atk_pct += piece_stats.get("ATK%", 0)
            mf_def_pct += piece_stats.get("DEF%", 0)
            mf_hp_pct += piece_stats.get("HP%", 0)
            gear_flat_atk += piece_stats.get("Flat ATK", 0)
            gear_flat_def += piece_stats.get("Flat DEF", 0)
            gear_flat_hp += piece_stats.get("Flat HP", 0)
            crit_rate += piece_stats.get("CRate", 0)
            crit_dmg += piece_stats.get("CDmg", 0)
            ego += piece_stats.get("Ego", 0)
            extra_dmg += piece_stats.get("Extra DMG%", 0)
            dot_dmg += piece_stats.get("DoT%", 0)

        # Set bonuses: count pieces per set, add stat bonuses from satisfied sets.
        set_counts = {}
        for piece in gear:
            set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
        for set_id, count in set_counts.items():
            if set_id in SETS:
                set_info = SETS[set_id]
                if count >= set_info["pieces"] and set_info["type"] == "stat":
                    stat = set_info.get("stat", "")
                    value = set_info.get("value", 0)
                    if stat == "ATK%":
                        mf_atk_pct += value
                    elif stat == "DEF%":
                        mf_def_pct += value
                    elif stat == "HP%":
                        mf_hp_pct += value
                    elif stat == "Crit DMG":
                        crit_dmg += value

        # Potential-node % bonuses (these go into the inner multiplier
        # alongside Memory Fragment %).
        potential_atk_pct = potential_stats.get("ATK%", 0)
        potential_def_pct = potential_stats.get("DEF%", 0)
        potential_hp_pct  = potential_stats.get("HP%", 0)
        # Potential-node CRate/CDmg are flat additions (not part of the new
        # ATK/DEF/HP formula structure).
        crit_rate += potential_stats.get("CRate", 0)
        crit_dmg  += potential_stats.get("CDmg", 0)

        # Partner passive % bonuses (these go into the OUTER multiplier
        # alongside Equipment %).
        partner_atk_pct = partner_passive_stats.get("ATK%", 0)
        partner_def_pct = partner_passive_stats.get("DEF%", 0)
        partner_hp_pct  = partner_passive_stats.get("HP%", 0)
        crit_dmg  += partner_passive_stats.get("CDmg", 0)
        extra_dmg += partner_passive_stats.get("Extra DMG%", 0)

        # ----- Apply the layered Final ATK/DEF/HP formulas -------------------
        # Final X = ((Base X + Partner X) × (1 + MF X% + Potential X%)
        #            + Gear Flat X + Affection Flat X)
        #         × (1 + Partner X% + Equipment X%)
        #         + Equipment Flat X
        def _final(base, partner_flat, mf_pct, pot_pct, gear_flat, affection_flat,
                   partner_pct, equip_pct, equip_flat):
            inner_mult = 1 + (mf_pct + pot_pct) / 100
            outer_mult = 1 + (partner_pct + equip_pct) / 100
            inner = (base + partner_flat) * inner_mult + gear_flat + affection_flat
            return inner * outer_mult + equip_flat

        total_atk = _final(
            base_atk, partner_flat_atk, mf_atk_pct, potential_atk_pct,
            gear_flat_atk, affection_atk,
            partner_atk_pct, self.EQUIPMENT_ATK_PCT, self.EQUIPMENT_FLAT_ATK,
        )
        total_def = _final(
            base_def, partner_flat_def, mf_def_pct, potential_def_pct,
            gear_flat_def, affection_def,
            partner_def_pct, self.EQUIPMENT_DEF_PCT, self.EQUIPMENT_FLAT_DEF,
        )
        total_hp = _final(
            base_hp, partner_flat_hp, mf_hp_pct, potential_hp_pct,
            gear_flat_hp, affection_hp,
            partner_hp_pct, self.EQUIPMENT_HP_PCT, self.EQUIPMENT_FLAT_HP,
        )
        total_cr = base_cr + crit_rate
        total_cd = base_cd + crit_dmg

        return {
            "ATK": total_atk, "DEF": total_def, "HP": total_hp,
            "CRate": total_cr, "CDmg": total_cd,
            # Summed % buckets — informational; reflects total % from MF+
            # potential+partner+equipment so the user can see what's
            # contributing. The Final ATK/DEF/HP above already account for
            # the layered formula.
            "ATK%": mf_atk_pct + potential_atk_pct + partner_atk_pct + self.EQUIPMENT_ATK_PCT,
            "DEF%": mf_def_pct + potential_def_pct + partner_def_pct + self.EQUIPMENT_DEF_PCT,
            "HP%":  mf_hp_pct  + potential_hp_pct  + partner_hp_pct  + self.EQUIPMENT_HP_PCT,
            "Ego": ego, "Extra DMG%": extra_dmg, "DoT%": dot_dmg,
        }

    def optimize(self, char_name: str, settings: dict, progress_callback: Callable = None,
                 cancel_flag: list = None) -> list[tuple[list[MemoryFragment], float, dict]]:
        """
        Find optimal gear combinations for a character.

        Uses brute-force enumeration with filtering to find the best gear builds
        that satisfy set bonus requirements and main stat constraints.

        Args:
            char_name: Character name to optimize for
            settings: Dictionary with optimization settings:
                - four_piece_sets: List of 4-piece set IDs (any one required)
                - two_piece_sets: List of 2-piece set IDs (all required)
                - main_stat_4/5/6: Required main stats for slots 4, 5, 6
                - top_percent: Filter to top X% of gear per slot
                - include_equipped: Include equipped gear in search
                - excluded_heroes: List of characters to exclude gear from
                - max_results: Maximum number of results to return
            progress_callback: Optional function(checked, total, results_count)
            cancel_flag: Optional list with single boolean element for cancellation

        Returns:
            List of tuples: (gear_list, total_score, final_stats)
            Sorted by score (highest first), limited to max_results
        """
        required_4pc_list = settings.get("four_piece_sets", [])  # Now a list for multi-select
        required_2pc = settings.get("two_piece_sets", [])
        main_stat_4 = settings.get("main_stat_4", [])
        main_stat_5 = settings.get("main_stat_5", [])
        main_stat_6 = settings.get("main_stat_6", [])
        top_percent = settings.get("top_percent", 100)
        include_equipped = settings.get("include_equipped", True)
        excluded_heroes = settings.get("excluded_heroes", [])
        max_results = settings.get("max_results", 100)

        use_priority = any(v != 0 for v in self.priorities.values())

        # Combine all required sets for initial filtering
        all_required_sets = []
        for s in required_4pc_list:
            if s and s not in all_required_sets:
                all_required_sets.append(s)
        for s in required_2pc:
            if s and s not in all_required_sets:
                all_required_sets.append(s)

        slot_candidates = {}
        for slot_num in SLOT_ORDER:
            main_filter = None
            if slot_num == 4 and main_stat_4:
                main_filter = main_stat_4
            elif slot_num == 5 and main_stat_5:
                main_filter = main_stat_5
            elif slot_num == 6 and main_stat_6:
                main_filter = main_stat_6

            candidates = self.get_gear_by_slot(
                slot_num,
                include_equipped=include_equipped,
                exclude_char=char_name,
                excluded_heroes=excluded_heroes,
                required_sets=all_required_sets if all_required_sets else None,
                required_main=main_filter,
                top_percent=top_percent,
                use_priority_score=use_priority,
                min_rarity=3  # Only Rare+ for optimizer
            )
            slot_candidates[slot_num] = candidates if candidates else []

        for slot_num in SLOT_ORDER:
            if not slot_candidates[slot_num]:
                return []

        total_perms = 1
        for slot_num in SLOT_ORDER:
            total_perms *= len(slot_candidates[slot_num])

        results = []
        checked = 0

        for combo in itertools.product(*[slot_candidates[s] for s in SLOT_ORDER]):
            if cancel_flag and cancel_flag[0]:
                break

            checked += 1

            piece_ids = [p.id for p in combo]
            if len(piece_ids) != len(set(piece_ids)):
                continue

            set_counts = {}
            for piece in combo:
                set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1

            # Check 4-piece set requirement (any of the selected 4-sets)
            if required_4pc_list:
                has_any_4pc = any(set_counts.get(req_set, 0) >= 4 for req_set in required_4pc_list)
                if not has_any_4pc:
                    continue

            # Check 2-piece requirements
            valid = True
            for req_set in required_2pc:
                if req_set and set_counts.get(req_set, 0) < 2:
                    valid = False
                    break
            if not valid:
                continue

            if use_priority:
                total_score = sum(p.priority_score for p in combo)
            else:
                total_score = sum(p.gear_score for p in combo)
            stats = self.calculate_build_stats(list(combo), char_name)

            results.append((list(combo), total_score, stats))

            if progress_callback and checked % 5000 == 0:
                progress_callback(checked, total_perms, len(results))

            if len(results) > max_results * 10:
                results.sort(key=lambda x: -x[1])
                results = results[:max_results]

        results.sort(key=lambda x: -x[1])
        return results[:max_results]
