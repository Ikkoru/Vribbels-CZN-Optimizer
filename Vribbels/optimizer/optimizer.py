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

>>> For the FULL game formula reference (damage, shield/heal, set
>>> effects, main stat values, endgame benchmarks, scoring), see
>>> docs/game_formulas.md at the project root. That file is the
>>> canonical source -- whenever the in-game math disagrees with what
>>> this module computes, FIX docs/game_formulas.md FIRST and then
>>> propagate the change into the code.

The optimizer's `calculate_build_stats` (below) implements only the
Final ATK/DEF/HP layered formula, which is one piece of the larger
picture. The v1.1.0 optimizer overhaul wires in the damage and
shield/heal scoring formulas on top of this baseline.

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
# Pure GS helper for per-character slot pre-filter sorting (v1.1.0 Phase 5).
# Optimize() resolves the character's assigned preset weights into the
# settings dict, then this gets used to score candidate fragments inside
# get_gear_by_slot without mutating their cached fragment.gear_score
# (which still reflects the globally-active preset). compute_gs_bounds is
# imported alongside since the per-slot bounds cache reuses it.
from models.memory_fragment import compute_fragment_gs, compute_gs_bounds


# Mapping from sets.py `stat` field values to the program's internal
# stat-name vocabulary. Some names match exactly (ATK%, DEF%, HP%);
# others differ ("Crit DMG" <-> CDmg, "Crit Rate" <-> CRate). DMG multi
# and DMG add are NOT in this map: they have no Final-stat equivalent
# and are accumulated separately into the damage card multiplier's
# Multiplicative_Buffs / Additive_Buffs buckets. See
# docs/game_formulas.md §5 for the canonical version of this table.
SET_STAT_NAME_MAP = {
    "ATK%":      "ATK%",
    "DEF%":      "DEF%",
    "HP%":       "HP%",
    "Crit DMG":  "CDmg",
    "Crit Rate": "CRate",
}


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

        # Task 1 (round 9): the snapshot lumps characters AND partner cards
        # into this one list with no explicit type field, so we infer which
        # entries are partners using several signals in precedence order:
        #   1. known character (res_id in CHARACTERS)            -> character
        #   2. known partner (res_id in PARTNERS)                -> partner
        #   3. instance id referenced as some char's partner_id  -> partner
        #      (only characters equip partners, so anything a partner_id
        #       points at is definitionally a partner)
        #   4. tie-break on potential-node data: characters carry a
        #      potential tree, partners don't -> has data == character.
        # (3) catches equipped unknown partners; (4) catches OWNED-BUT-
        # UNEQUIPPED unknown partners (e.g. a freshly-pulled "30095" not yet
        # in partners.py) that previously leaked into the character list.
        # A res_id range rule was deliberately avoided: some new CHARACTERS
        # also use 5-digit 30xxx ids (they appear in this snapshot's
        # counseling / archive-gift / business-card data), so a range split
        # would hide real characters. The only residual miss is a brand-new
        # unknown character with ZERO potential unlocked AND no equipped
        # partner -- vanishingly rare (node 10 unlocks almost immediately),
        # and resolved permanently once it's added to characters.py.
        referenced_partner_ids = set()
        for char in char_items:
            pid = char.get("partner_id", 0) or char.get("partner", 0)
            if pid:
                referenced_partner_ids.add(pid)

        def _has_potential_data(entry) -> bool:
            raw = entry.get("potential_node_ids")
            if not raw:
                return False
            return str(raw).strip() not in ("", "[]", "{}")

        for char in char_items:
            res_id = char.get("res_id", 0)
            inst_id = char.get("id", 0)
            known_char_data = get_character(res_id) if res_id else None
            known_char = bool(known_char_data) and known_char_data.get("name") != "Unknown"
            known_partner = get_partner(res_id).get("name") != "Unknown"
            referenced_partner = inst_id in referenced_partner_ids
            if known_char:
                hero_items.append(char)
            elif known_partner or referenced_partner:
                partner_lookup[inst_id] = char
            elif _has_potential_data(char):
                hero_items.append(char)
            else:
                partner_lookup[inst_id] = char

        # Stash for any consumer that needs raw entries by instance id
        # (e.g., heroes_tab to show res_id for unknown equipped partners).
        self.all_items_by_id = all_items_by_id

        for char in hero_items:
            res_id = char.get("res_id", 0)
            char_data = get_character(res_id)
            name = char_data.get("name", "")

            # Item 13: captured-but-unknown characters (a res_id not yet in
            # characters.py) used to be skipped here, so they only appeared
            # in the Combatants / Optimizer tabs via the `characters` dict
            # (equipped gear) -- meaning they VANISHED when their last MF
            # was unequipped. Instead, give them a CharacterInfo keyed by
            # the numeric res_id string (matching get_character_name's
            # behavior, so this character_info key lines up with the
            # `equipped_to` value used in the `characters` dict). Now they
            # show up on capture and persist regardless of equipped gear.
            # Only a falsy/zero res_id is a genuinely empty entry to skip.
            if not name or name == "Unknown" or name.startswith("Unknown ("):
                if res_id:
                    name = str(res_id)
                else:
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
                         use_priority_score: bool = False, min_rarity: int = 2,
                         score_weights: dict = None) -> list[MemoryFragment]:
        """
        Get filtered and ranked gear for a specific slot.

        Args:
            slot_num: Equipment slot (1-6)
            include_equipped: Include equipped gear
            exclude_char: Exclude gear equipped to this character
            excluded_heroes: List of characters to exclude gear from
            required_sets: Filter by set IDs
            required_main: Filter by main stat names (for slots 4-6)
            top_percent: Keep only top X% by score (with a 10-fragment floor)
            use_priority_score: Use priority score instead of gear score
            min_rarity: Minimum rarity (1=Common, 2=Uncommon, 3=Rare, 4=Legendary)
            score_weights: When provided, rank candidates by their normalized
                GS computed under THESE weights (pure, doesn't mutate
                fragment.gear_score). When None, use the cached
                fragment.gear_score which reflects the globally-active
                Scoring tab preset. v1.1.0 Phase 5 wires this to the
                CURRENT CHARACTER's assigned preset weights so the pre-
                filter heuristic matches the character's actual build
                goals rather than the global default.

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
        elif score_weights is not None:
            # Per-character pre-filter sort (v1.1.0 Phase 5). We score every
            # candidate under the character's weights using the pure helper
            # so fragment.gear_score (set by the active preset) stays intact
            # for the rest of the UI. Cache by main_stat name since bounds
            # only depend on weights + which stat is excluded; caps at ~16
            # entries regardless of fragment count.
            bounds_cache: dict = {}
            def _bounds_for(frag):
                key = frag.main_stat.name if frag.main_stat else None
                cached = bounds_cache.get(key)
                if cached is None:
                    cached = compute_gs_bounds(score_weights, exclude_stat=key)
                    bounds_cache[key] = cached
                return cached
            candidates.sort(
                key=lambda f: -compute_fragment_gs(f, score_weights, _bounds_for(f))
            )
        else:
            candidates.sort(key=lambda f: -f.gear_score)

        # Top filter: keep at least 10 fragments per slot (floor) or the top
        # `top_percent`% of available fragments, whichever is greater.
        # Rationale: the 10-floor helps small inventories that would otherwise
        # have too few candidates per slot for the optimizer to find good
        # builds; the percentage handles large inventories. v1.1.0 Phase 4
        # introduced the floor (previously the only safeguard was `max(1, ...)`,
        # which left sparse inventories starved). The cap stays at len(candidates)
        # so we never return more than we have.
        count_by_pct = int(len(candidates) * top_percent / 100)
        count = min(len(candidates), max(10, count_by_pct))
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
                               effective_level: int = None,
                               set_effect_share: float = 0.0) -> dict[str, float]:
        """
        Calculate final stats for a gear build.

        Implements the Final ATK / DEF / HP formula:

          inner_X = (Base X + Partner X) * (1 + Memory_Fragment_X% + Potential_X%)
                    + Gear_Flat_X + Affection_Flat_X
          Final X = inner_X * (1 + Partner_X% + Equipment_X%) + Equipment_Flat_X

        Also computes the v1.1.0 optimizer-scoring helper Shield_Heal_DEF
        (a Final-DEF variant where Partner_FLAT_DEF is pulled out of the
        inner multiplier; see docs/game_formulas.md §4.1) and returns it
        plus the raw Base_DEF in the result dict under underscore-prefixed
        keys. UI display code should ignore keys starting with "_".

        Args:
            gear: List of 6 MemoryFragment objects (one per slot)
            char_name: Character name (optional, for base stats)
            effective_level: If set, computes base stats at this level
                instead of using the character's actual level. Used by
                the Optimizer tab's per-character "Optimize for LVL"
                stepper.
            set_effect_share: 0.0–1.0 weight applied to conditional sets'
                Crit DMG / Crit Rate contributions (matches the
                Optimizer tab's "% of damage with set effect" slider).
                At 0 (default), no conditional set effect is applied to
                Final stats — unconditional sets still apply at full
                value. Callers outside the optimizer (Heroes tab, etc.)
                leave this at 0 since the conditional bonuses aren't
                actually always active in-game.

        Returns:
            Dictionary with Final ATK/DEF/HP, CRate, CDmg, the summed substat
            % buckets (informational), Ego / Extra DMG% / DoT%, and the
            underscore-prefixed `_base_def_for_shield` and `_shield_heal_def`
            used by _compute_optimizer_score.
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
            # get_character_stats_at_level applies the character's optional
            # level_61_bonus / level_62_bonus (per-character keys in the
            # CHARACTERS dict) when the level is 61/62. Characters without
            # those keys fall back to their level-60 base stats, so for them
            # this is a no-op.
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

        # Set bonuses: count pieces per set, route satisfied bonuses into
        # the right bucket. See docs/game_formulas.md §5 for the full taxonomy:
        #   - "unconditional" sets always apply at full value.
        #   - "conditional" sets with stat in {Crit DMG, Crit Rate} apply at
        #     value × set_effect_share (touching Final_CDmg / Final_CRate).
        #   - "conditional" sets with stat in {DMG multi, DMG add} do NOT
        #     touch Final stats; they're handled by _compute_optimizer_score
        #     (skipped here).
        set_counts = {}
        for piece in gear:
            set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
        for set_id, count in set_counts.items():
            if set_id not in SETS:
                continue
            set_info = SETS[set_id]
            if count < set_info["pieces"]:
                continue
            stype = set_info["type"]
            raw_stat = set_info.get("stat", "")
            value = set_info.get("value", 0)

            if stype == "unconditional":
                effective = value
            elif stype == "conditional" and raw_stat in ("Crit DMG", "Crit Rate"):
                effective = value * set_effect_share
            else:
                # Conditional DMG multi / DMG add: handled by the optimizer
                # score function (flows through card_mult, not Final stats).
                continue

            program_stat = SET_STAT_NAME_MAP.get(raw_stat)
            if program_stat == "ATK%":
                mf_atk_pct += effective
            elif program_stat == "DEF%":
                mf_def_pct += effective
            elif program_stat == "HP%":
                mf_hp_pct += effective
            elif program_stat == "CDmg":
                crit_dmg += effective
            elif program_stat == "CRate":
                crit_rate += effective

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
        def _inner(base, partner_flat, mf_pct, pot_pct, gear_flat, affection_flat):
            """Inner stat = the build's value BEFORE the outer multiplier.
            Exposed separately (under "_inner_X" keys) so v1.1.0 polish
            features can use it: the Have-at-least check (item 7) and
            the "Potential 7 X" rows in the Stat Contributions popup
            (item 8). Per in-game verification, Partner% and Equipment
            don't contribute toward the in-game minimum stat thresholds,
            so this inner value is what those features compare against.
            """
            inner_mult = 1 + (mf_pct + pot_pct) / 100
            return (base + partner_flat) * inner_mult + gear_flat + affection_flat

        def _final(base, partner_flat, mf_pct, pot_pct, gear_flat, affection_flat,
                   partner_pct, equip_pct, equip_flat):
            outer_mult = 1 + (partner_pct + equip_pct) / 100
            inner = _inner(base, partner_flat, mf_pct, pot_pct, gear_flat, affection_flat)
            return inner * outer_mult + equip_flat

        # Shield_Heal_DEF: a Final-DEF variant where Partner_FLAT_DEF is
        # pulled OUT of the inner multiplier (treated as additive flat
        # instead). The only difference from regular Final DEF. See
        # docs/game_formulas.md §4.1 for the formula derivation. Computed
        # here because it shares all the same inputs as Final DEF; consumed
        # by _compute_optimizer_score via the _shield_heal_def return key.
        def _final_shield_heal_def(base, partner_flat, mf_pct, pot_pct, gear_flat,
                                    affection_flat, partner_pct, equip_pct, equip_flat):
            inner_mult = 1 + (mf_pct + pot_pct) / 100
            outer_mult = 1 + (partner_pct + equip_pct) / 100
            # Difference vs _final: partner_flat is NOT added to `base`
            # before applying inner_mult -- it's added as a separate flat
            # contribution. The rest of the layered structure is identical.
            inner = base * inner_mult + partner_flat + gear_flat + affection_flat
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
        # Items 7+8 (round 5): inner ATK/DEF/HP -- the build value without
        # Partner% multiplier and without Equipment (% or flat). Used by
        # _meets_have_at_least and surfaced in the breakdown popup as
        # "Potential 7 X".
        inner_atk = _inner(base_atk, partner_flat_atk, mf_atk_pct,
                            potential_atk_pct, gear_flat_atk, affection_atk)
        inner_def = _inner(base_def, partner_flat_def, mf_def_pct,
                            potential_def_pct, gear_flat_def, affection_def)
        inner_hp = _inner(base_hp, partner_flat_hp, mf_hp_pct,
                           potential_hp_pct, gear_flat_hp, affection_hp)
        shield_heal_def = _final_shield_heal_def(
            base_def, partner_flat_def, mf_def_pct, potential_def_pct,
            gear_flat_def, affection_def,
            partner_def_pct, self.EQUIPMENT_DEF_PCT, self.EQUIPMENT_FLAT_DEF,
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
            # v1.1.0 optimizer-scoring internals (underscore-prefixed).
            # UI display code can filter them out by ignoring keys
            # starting with "_". See _compute_optimizer_score.
            "_base_def_for_shield": base_def,
            "_shield_heal_def": shield_heal_def,
            # Items 7+8 (round 5): inner values (without outer multiplier
            # and without equipment). Used by _meets_have_at_least and
            # displayed in the popup as "Potential 7 X".
            "_inner_atk": inner_atk,
            "_inner_def": inner_def,
            "_inner_hp":  inner_hp,
        }

    def _count_locked_slots(self, combo, sets_selected: list) -> int:
        """Count how many slots are "locked" into a chosen set's satisfied bonus.

        A slot is locked if it belongs to a fully-satisfied bonus from one of
        the user's chosen sets. Total wildcard slots = 6 - locked; the build
        is valid if wildcard count <= max_flex_slots.

        This single rule implicitly enumerates the 6 combo-shape variants
        from docs/game_formulas.md:
          - locked=6 (0 wildcards): shape 4+2 (one 4pc + one 2pc) or 2+2+2
          - locked=4 (2 wildcards): shape 4+wild2 or 2+2+wild2
          - locked=2 (4 wildcards): shape 2+wild4
          - locked=0 (6 wildcards): shape wild6

        The max_flex_slots stepper cap maps directly to "how many wildcards
        are tolerated". Equivalent to enumerating per-shape but avoids
        partition combinatorics.

        Returns 0 when sets_selected is empty (every slot is a wildcard) --
        the caller's max_flex_slots check then determines whether that's
        acceptable.

        Args:
            combo: Tuple of 6 MemoryFragment objects (one per slot).
            sets_selected: List of set_id ints the user marked as desirable
                in the Optimizer tab's Set Configuration checklist.

        Returns:
            Integer 0-6: the number of slots locked into a satisfied chosen
            set's bonus.
        """
        if not sets_selected:
            return 0
        # Quick count: pieces per set in this build.
        set_counts: dict = {}
        for piece in combo:
            set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
        locked = 0
        for set_id in sets_selected:
            if set_id not in SETS:
                continue
            pieces_needed = SETS[set_id]["pieces"]
            if set_counts.get(set_id, 0) >= pieces_needed:
                # Bonus is satisfied; this set locks `pieces_needed` slots.
                # We don't count overflow (e.g. 6 of a 4pc set still only
                # locks 4 -- the extra 2 are wildcards).
                locked += pieces_needed
        return locked

    def _resolve_attribute(self, char_name: str, settings: dict) -> str:
        """Return the effective Element attribute for damage-formula purposes.

        For known characters, returns CHARACTERS[res_id].attribute. For
        characters with attribute == "Unknown" (not yet in characters.py),
        returns settings["element_override"] if set, otherwise empty
        string -- which the caller interprets as "no Element DMG% bonus
        applies" (Element DMG% main stats contribute 0 to damage).

        See docs/game_formulas.md §7.
        """
        if not char_name:
            return ""
        char_data = get_character_by_name(char_name)
        attribute = char_data.get("attribute", "Unknown")
        if attribute == "Unknown":
            override = settings.get("element_override")
            return override if override else ""
        return attribute

    def _meets_have_at_least(self, stats: dict, settings: dict) -> bool:
        """Check whether a build's stats meet every "Have at least" minimum.

        Returns True if all configured thresholds are satisfied (or no
        thresholds set). Empty / missing / zero thresholds are skipped
        (trivially met).

        For ATK / DEF / HP, the comparison value is the INNER stat (build
        value before the outer multiplier and without equipment) -- see
        _inner() in calculate_build_stats. Per in-game verification, the
        minimum-stat requirements in CZN don't take Partner% or Equipment
        into account -- only Base + Partner-flat + Memory-Fragment +
        Potential% nodes + Affection. So the HAL check uses the same
        "build contribution" view of ATK/DEF/HP that the in-game
        requirement checks against.

        For other stats (CRate, CDmg, Ego, Extra DMG%, DoT%), the regular
        final value is used since there's no inner/outer split for them.

        Item 7 (round 5): switched from "Final - Equipment_Flat" to the
        inner value, which additionally excludes Partner%.
        """
        hal = settings.get("have_at_least") or {}
        if not hal:
            return True
        # ATK/DEF/HP have inner-value alternatives; everything else uses
        # the regular key.
        inner_keys = {
            "ATK": "_inner_atk",
            "DEF": "_inner_def",
            "HP":  "_inner_hp",
        }
        for stat, min_val in hal.items():
            if min_val is None or min_val <= 0:
                continue
            lookup_key = inner_keys.get(stat, stat)
            # Fall back to the regular stat if the inner key is missing
            # (defensive -- calculate_build_stats always populates them).
            actual = stats.get(lookup_key, stats.get(stat, 0))
            if actual < min_val:
                return False
        return True

    def _compute_optimizer_score(self, gear: list, stats: dict,
                                  settings: dict, char_name: str) -> float:
        """v1.1.0 optimizer score: damage / shield-heal blend.

        See docs/game_formulas.md §3, §4, §5, §8 for the formula sources.
        Constants that don't affect relative ranking (0.35, Enemy_Defense_
        Multiplier, Element_Advantage, etc.) are dropped from the comparison.
        The shield/heal 0.3 constant IS preserved so the heal_share blend
        stays balanced against damage magnitudes.

        Args:
            gear: List of 6 MemoryFragment objects.
            stats: Result of calculate_build_stats. Must include
                _base_def_for_shield and _shield_heal_def keys.
            settings: Per-character optimizer settings dict.
            char_name: Character name (used for attribute lookup).

        Returns:
            Scalar score. Higher is better. Magnitudes are arbitrary --
            rankings are stable but absolute numbers aren't directly
            meaningful.
        """
        # All user-supplied percentages, normalized to fractions.
        extra_share = settings.get("extra_pct", 0) / 100.0
        dot_share = settings.get("dot_pct", 0) / 100.0
        def_split = settings.get("atk_def_split", 0) / 100.0
        heal_share = settings.get("shielding_healing_weight", 0) / 100.0
        set_effect_share = settings.get("set_effect_pct", 0) / 100.0
        # avg_card_dmg_pct is the average card's intrinsic multiplier as a
        # percentage (100 = card does normal damage, 150 = card does +50%, etc.)
        base_multiplier = settings.get("avg_card_dmg_pct", 100) / 100.0
        avg_mult_buff = settings.get("avg_mult_buff_pct", 0) / 100.0
        avg_add_buff = settings.get("avg_add_buff_pct", 0) / 100.0

        # ----- Conditional set DMG multi / DMG add accumulator -----
        # These flow through the damage card multiplier only (NOT
        # shield/heal -- see docs §5). Scaled by set_effect_share.
        # When set_effect_share == 0 we skip the whole walk -- common
        # case for users who haven't dialed the slider up.
        set_dmg_multi_total = 0.0
        set_dmg_add_total = 0.0
        if set_effect_share > 0:
            set_counts: dict = {}
            for piece in gear:
                set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
            for set_id, count in set_counts.items():
                if set_id not in SETS:
                    continue
                set_info = SETS[set_id]
                if set_info.get("type") != "conditional":
                    continue
                if count < set_info["pieces"]:
                    continue
                raw_stat = set_info.get("stat", "")
                value = set_info.get("value", 0)
                if raw_stat == "DMG multi":
                    set_dmg_multi_total += value * set_effect_share
                elif raw_stat == "DMG add":
                    set_dmg_add_total += value * set_effect_share

        # ----- Card multipliers (damage vs shield/heal) -----
        # Damage card multiplier includes DMG multi / DMG add.
        # Shield/heal card multiplier does NOT (see docs §5). Both share
        # the user's avg_card_dmg_pct base + avg buff inputs.
        mult_buffs_dmg = avg_mult_buff + set_dmg_multi_total / 100.0
        add_buffs_dmg = avg_add_buff + set_dmg_add_total / 100.0
        card_mult_dmg = base_multiplier * (1 + mult_buffs_dmg) + add_buffs_dmg
        card_mult_shield_heal = (
            base_multiplier * (1 + avg_mult_buff) + avg_add_buff
        )

        # ----- Crit modifier -----
        # Average damage per hit = (1 - p_crit) × base + p_crit × base × (1 + bonus)
        #                        = base × (1 + p_crit × bonus)
        # where bonus = (Final_CDmg - 100) / 100. CRate cap = 100%.
        final_crate = max(0.0, min(100.0, stats.get("CRate", 0)))
        final_cdmg = stats.get("CDmg", 125)
        crit_modifier = 1 + (final_crate / 100.0) * max(0.0, (final_cdmg - 100.0) / 100.0)

        # ----- Element DMG% -----
        # The optimizer treats all of a character's damage as their
        # element. We pick up the matching Element DMG% main stat from
        # slot 5 (if equipped). For Unknown-attribute characters, the
        # user's element_override drives the matching.
        attribute = self._resolve_attribute(char_name, settings)
        element_dmg_pct = 0
        if attribute:
            elem_main_name = f"{attribute} DMG%"
            for piece in gear:
                if piece.main_stat and piece.main_stat.name == elem_main_name:
                    element_dmg_pct += piece.main_stat.value
        element_multiplier = 1 + element_dmg_pct / 100.0

        # ----- ATK vs DEF scaling damage formulas -----
        # Constants (0.35, Enemy_Defense_Multiplier) dropped -- same
        # across all builds. See docs §3.1 / §3.2.
        final_atk = stats.get("ATK", 0)
        final_def = stats.get("DEF", 0)
        atk_scaling = card_mult_dmg * final_atk * element_multiplier * crit_modifier
        def_scaling = card_mult_dmg * (final_atk * 0.3 + final_def * 2.1) \
                      * element_multiplier * crit_modifier

        # Extra DMG and DoT always use ATK formula with the Mechanic_DMG%
        # multiplier (Extra DMG% or DoT% respectively). See docs §3 notes.
        extra_dmg_pct = stats.get("Extra DMG%", 0)
        dot_dmg_pct = stats.get("DoT%", 0)
        extra_dmg_per_hit = atk_scaling * (1 + extra_dmg_pct / 100.0)
        dot_dmg_per_hit = atk_scaling * (1 + dot_dmg_pct / 100.0)

        # ----- Blend damage by share -----
        # The character's damage is partitioned by type:
        #   extra_share  : Extra-typed damage (always ATK formula)
        #   dot_share    : DoT-typed damage   (always ATK formula)
        #   normal_share : everything else (split between ATK and DEF
        #                  formulas via def_split slider)
        # Shares sum to 1.0. If extra + dot > 1, normal_share clamps to 0.
        normal_share = max(0.0, 1.0 - extra_share - dot_share)
        damage_score = (
            normal_share * (1.0 - def_split) * atk_scaling
            + normal_share * def_split * def_scaling
            + extra_share * extra_dmg_per_hit
            + dot_share * dot_dmg_per_hit
        )

        # ----- Shield/heal score -----
        # See docs §4.1. Shield_Heal_DEF differs from Final DEF only in
        # having Partner_FLAT_DEF outside the inner multiplier.
        base_def_raw = stats.get("_base_def_for_shield", 0)
        shield_heal_def = stats.get("_shield_heal_def", 0)
        shield_heal_score = (
            (base_def_raw + shield_heal_def) / 2.0
            * 0.3
            * card_mult_shield_heal
        )

        # ----- Combined blend -----
        # heal_share = 0: pure damage. heal_share = 1: pure heal/shield.
        # In between: weighted blend. The user calibrates this slider by
        # feel since damage and heal magnitudes aren't naturally
        # commensurable.
        return damage_score * (1.0 - heal_share) + shield_heal_score * heal_share

    def compute_build_breakdown(self, gear: list, char_name: str,
                                settings: dict = None) -> dict:
        """Per-source breakdown of a build's final stats (Item 11).

        Recomputes the SAME layered formula as calculate_build_stats but
        keeps each contribution separate instead of collapsing it, so the
        Optimizer tab's "Show all stat contributions" popup can show where
        every number comes from. The ATK/DEF/HP `sum` values reconcile
        exactly with calculate_build_stats' Final ATK/DEF/HP (same inputs,
        same _final formula).

        Returns a dict keyed by stat name. For ATK/DEF/HP each value is a
        dict with: sum, base, partner_flat, mf_pct, pot_pct, mf_flat,
        affection, partner_pct, other_present (bool -- True if set% /
        equipment %/flat contribute, which they generally do via the
        equipment flat constant). For CRate/CDmg: base, mf_main, mf_sub,
        other (numeric). For Element%/Extra DMG%/DoT%/Ego: the relevant
        mf_main / mf_sub split plus a numeric `other`. Plus scalar
        "xDMG%" (multiplicative buffs) and "+DMG%" (additive buffs).
        """
        settings = settings or {}
        set_effect_share = settings.get("set_effect_pct", 0) / 100.0
        effective_level = settings.get("optimize_for_level")

        # ----- Base character stats at the effective level -----
        base_atk = base_def = base_hp = 0
        base_cr, base_cd = 0.0, 125.0
        if char_name:
            char_data = get_character_by_name(char_name)
            if effective_level is None:
                actual = (self.character_info[char_name].level
                          if char_name in self.character_info else 60)
                effective_level = max(60, min(62, actual))
            else:
                try:
                    effective_level = max(60, min(62, int(effective_level)))
                except (ValueError, TypeError):
                    effective_level = 60
            scaled = get_character_stats_at_level(char_data, effective_level)
            base_atk, base_def, base_hp = (
                scaled["base_atk"], scaled["base_def"], scaled["base_hp"]
            )
            base_cr = char_data.get("base_crit_rate", 0)
            base_cd = char_data.get("base_crit_dmg", 125.0)

        # ----- Affection + partner flat + partner passive + potential -----
        affection_atk = affection_def = affection_hp = 0
        partner_flat_atk = partner_flat_def = partner_flat_hp = 0
        partner_passive = {}
        potential = {}
        if char_name and char_name in self.character_info:
            ci = self.character_info[char_name]
            fb = ci.friendship_bonus
            affection_atk, affection_def, affection_hp = fb[0], fb[1], fb[2]
            if ci.partner_res_id:
                ps = get_partner_stats(ci.partner_res_id, ci.partner_level)
                partner_flat_atk, partner_flat_def, partner_flat_hp = (
                    ps["atk"], ps["def"], ps["hp"]
                )
                partner_passive = get_partner_passive_stats(
                    ci.partner_res_id, ci.partner_limit_break
                )
            for node, lvl in ((50, ci.potential_50_level),
                              (60, ci.potential_60_level)):
                if lvl > 0:
                    st, bonus = get_potential_stat_bonus(ci.res_id, node, lvl)
                    if st:
                        potential[st] = potential.get(st, 0) + bonus

        # ----- Separate MF main-stat vs substat contributions -----
        mf_main: dict = {}
        mf_sub: dict = {}
        for piece in gear:
            if piece.main_stat:
                mf_main[piece.main_stat.name] = (
                    mf_main.get(piece.main_stat.name, 0) + piece.main_stat.value
                )
            for sub in piece.substats:
                mf_sub[sub.name] = mf_sub.get(sub.name, 0) + sub.value

        def _m(name):
            return mf_main.get(name, 0)

        def _s(name):
            return mf_sub.get(name, 0)

        # Fragment % (main + sub), excluding set bonuses -- shown as "MF%".
        mf_atk_pct = _m("ATK%") + _s("ATK%")
        mf_def_pct = _m("DEF%") + _s("DEF%")
        mf_hp_pct  = _m("HP%")  + _s("HP%")
        # Fragment flat (main + sub) -- shown as "MF Flat".
        mf_flat_atk = _m("Flat ATK") + _s("Flat ATK")
        mf_flat_def = _m("Flat DEF") + _s("Flat DEF")
        mf_flat_hp  = _m("Flat HP")  + _s("Flat HP")

        # ----- Set bonuses (same routing as calculate_build_stats) -----
        set_atk_pct = set_def_pct = set_hp_pct = 0.0
        set_crate = set_cdmg = 0.0
        set_dmg_multi = set_dmg_add = 0.0
        set_counts: dict = {}
        for piece in gear:
            set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
        for set_id, count in set_counts.items():
            if set_id not in SETS:
                continue
            si = SETS[set_id]
            if count < si["pieces"]:
                continue
            stype = si["type"]
            raw = si.get("stat", "")
            val = si.get("value", 0)
            if stype == "unconditional":
                eff = val
            elif stype == "conditional" and raw in ("Crit DMG", "Crit Rate"):
                eff = val * set_effect_share
            elif stype == "conditional" and raw == "DMG multi":
                set_dmg_multi += val * set_effect_share
                continue
            elif stype == "conditional" and raw == "DMG add":
                set_dmg_add += val * set_effect_share
                continue
            else:
                continue
            ps_name = SET_STAT_NAME_MAP.get(raw)
            if ps_name == "ATK%":
                set_atk_pct += eff
            elif ps_name == "DEF%":
                set_def_pct += eff
            elif ps_name == "HP%":
                set_hp_pct += eff
            elif ps_name == "CDmg":
                set_cdmg += eff
            elif ps_name == "CRate":
                set_crate += eff

        # ----- Potential % + flat-crit, partner passive % -----
        pot_atk_pct = potential.get("ATK%", 0)
        pot_def_pct = potential.get("DEF%", 0)
        pot_hp_pct  = potential.get("HP%", 0)
        pot_crate = potential.get("CRate", 0)
        pot_cdmg  = potential.get("CDmg", 0)
        partner_atk_pct = partner_passive.get("ATK%", 0)
        partner_def_pct = partner_passive.get("DEF%", 0)
        partner_hp_pct  = partner_passive.get("HP%", 0)
        partner_cdmg  = partner_passive.get("CDmg", 0)
        partner_extra = partner_passive.get("Extra DMG%", 0)

        # ----- Final ATK/DEF/HP (reconciles with calculate_build_stats) -----
        def _final(base, partner_flat, mf_pct, set_pct, pot_pct, gear_flat,
                   affection_flat, partner_pct, equip_pct, equip_flat):
            inner_mult = 1 + (mf_pct + set_pct + pot_pct) / 100
            outer_mult = 1 + (partner_pct + equip_pct) / 100
            inner = (base + partner_flat) * inner_mult + gear_flat + affection_flat
            return inner * outer_mult + equip_flat

        def _inner(base, partner_flat, mf_pct, set_pct, pot_pct, gear_flat,
                   affection_flat):
            # Items 7+8 (round 5): inner value (before outer multiplier,
            # without equipment). Matches calculate_build_stats' _inner.
            inner_mult = 1 + (mf_pct + set_pct + pot_pct) / 100
            return (base + partner_flat) * inner_mult + gear_flat + affection_flat

        sum_atk = _final(base_atk, partner_flat_atk, mf_atk_pct, set_atk_pct,
                         pot_atk_pct, mf_flat_atk, affection_atk,
                         partner_atk_pct, self.EQUIPMENT_ATK_PCT, self.EQUIPMENT_FLAT_ATK)
        sum_def = _final(base_def, partner_flat_def, mf_def_pct, set_def_pct,
                         pot_def_pct, mf_flat_def, affection_def,
                         partner_def_pct, self.EQUIPMENT_DEF_PCT, self.EQUIPMENT_FLAT_DEF)
        sum_hp = _final(base_hp, partner_flat_hp, mf_hp_pct, set_hp_pct,
                        pot_hp_pct, mf_flat_hp, affection_hp,
                        partner_hp_pct, self.EQUIPMENT_HP_PCT, self.EQUIPMENT_FLAT_HP)
        inner_atk = _inner(base_atk, partner_flat_atk, mf_atk_pct, set_atk_pct,
                           pot_atk_pct, mf_flat_atk, affection_atk)
        inner_def = _inner(base_def, partner_flat_def, mf_def_pct, set_def_pct,
                           pot_def_pct, mf_flat_def, affection_def)
        inner_hp = _inner(base_hp, partner_flat_hp, mf_hp_pct, set_hp_pct,
                          pot_hp_pct, mf_flat_hp, affection_hp)

        def _other_present(equip_pct):
            # Item 1 (v1.1.0 polish round 2): Equipment is now its own column
            # in the popup ("Equip (apx.)"), so it's no longer rolled into
            # "Other". With sets ALSO broken out as "Set Effect Sum", every
            # contributor for ATK/DEF/HP is explicitly named. "Other" now
            # signals only Equipment ATK%/DEF%/HP% multipliers -- defaults to
            # 0 (so Other = False, displayed as cross), but if the user
            # customizes EQUIPMENT_*_PCT in optimizer.py, the cross flips to
            # check so the popup still reconciles.
            return bool(equip_pct)

        # ----- Crit / element / mechanic stats -----
        attribute = self._resolve_attribute(char_name, settings)
        elem_main = _m(f"{attribute} DMG%") if attribute else 0

        # Items 7 + 9: xDMG% / +DMG% in the popup show ONLY the set-effect
        # contributions (Avg Multi Buff% / Avg Add Buff% deliberately
        # excluded -- those are user-assumed external buffs, not actual
        # character contributions). Lines below that have an "Other" field
        # get a separate "Set Effect Sum" column; xDMG% / +DMG% don't have
        # Other, so the value here IS the set effect sum for those.

        return {
            "ATK": {
                "sum": sum_atk, "base": base_atk, "partner_flat": partner_flat_atk,
                "mf_pct": mf_atk_pct, "pot_pct": pot_atk_pct, "mf_flat": mf_flat_atk,
                "affection": affection_atk, "partner_pct": partner_atk_pct,
                "set_effect": set_atk_pct,
                "equip_flat": self.EQUIPMENT_FLAT_ATK,
                "inner": inner_atk,
                "other_present": _other_present(self.EQUIPMENT_ATK_PCT),
            },
            "DEF": {
                "sum": sum_def, "base": base_def, "partner_flat": partner_flat_def,
                "mf_pct": mf_def_pct, "pot_pct": pot_def_pct, "mf_flat": mf_flat_def,
                "affection": affection_def, "partner_pct": partner_def_pct,
                "set_effect": set_def_pct,
                "equip_flat": self.EQUIPMENT_FLAT_DEF,
                "inner": inner_def,
                "other_present": _other_present(self.EQUIPMENT_DEF_PCT),
            },
            "HP": {
                "sum": sum_hp, "base": base_hp, "partner_flat": partner_flat_hp,
                "mf_pct": mf_hp_pct, "pot_pct": pot_hp_pct, "mf_flat": mf_flat_hp,
                "affection": affection_hp, "partner_pct": partner_hp_pct,
                "set_effect": set_hp_pct,
                "equip_flat": self.EQUIPMENT_FLAT_HP,
                "inner": inner_hp,
                "other_present": _other_present(self.EQUIPMENT_HP_PCT),
            },
            "CRate": {
                "base": base_cr, "mf_main": _m("CRate"), "mf_sub": _s("CRate"),
                "set_effect": set_crate,
                "other": pot_crate,
            },
            "CDmg": {
                "base": base_cd, "mf_main": _m("CDmg"), "mf_sub": _s("CDmg"),
                "set_effect": set_cdmg,
                "other": pot_cdmg + partner_cdmg,
            },
            "Element%": {"mf_main": elem_main, "set_effect": 0.0, "other": 0.0},
            "Extra DMG%": {"mf_sub": _s("Extra DMG%"), "set_effect": 0.0,
                           "other": partner_extra},
            "DoT%": {"mf_sub": _s("DoT%"), "set_effect": 0.0, "other": 0.0},
            "Ego": {"mf_main": _m("Ego"), "mf_sub": _s("Ego"),
                    "set_effect": 0.0, "other": 0.0},
            "xDMG%": set_dmg_multi,
            "+DMG%": set_dmg_add,
        }

    def optimize(self, char_name: str, settings: dict, progress_callback: Callable = None,
                 cancel_flag: list = None) -> list[tuple[list[MemoryFragment], float, dict]]:
        """
        Find optimal gear combinations for a character.

        Uses brute-force enumeration with filtering. v1.1.0 rewrite:
        the build score is the damage/shield-heal blended formula from
        docs/game_formulas.md §8 (not the old gear_score sum). Per-
        character settings (Important Settings sliders, Have at Least
        minimums, set-effect %, avg buff fields, level stepper) drive
        the scoring; see _compute_optimizer_score for the formula.

        Side effect: writes `self.last_optimize_stats`, a small counters
        dict the caller can read after optimize() returns to drive UI
        messaging (e.g., distinguishing "no candidate sets found" from
        "every candidate failed Have at Least").

        Args:
            char_name: Character name to optimize for
            settings: Dictionary with optimization settings (see
                _compute_optimizer_score for the per-character fields,
                plus the legacy filter fields: four_piece_sets,
                two_piece_sets, main_stat_4/5/6, top_percent,
                include_equipped, excluded_heroes, max_results,
                optimize_for_level)
            progress_callback: Optional function(checked, total, results_count)
            cancel_flag: Optional list with single boolean element for cancellation

        Returns:
            List of tuples: (gear_list, score, final_stats).
            Sorted by score (highest first), limited to max_results.
        """
        required_4pc_list = settings.get("four_piece_sets", [])  # legacy (still read for back-compat)
        required_2pc = settings.get("two_piece_sets", [])         # legacy (still read for back-compat)
        main_stat_4 = settings.get("main_stat_4", [])
        main_stat_5 = settings.get("main_stat_5", [])
        main_stat_6 = settings.get("main_stat_6", [])
        top_percent = settings.get("top_percent", 100)
        include_equipped = settings.get("include_equipped", True)
        excluded_heroes = settings.get("excluded_heroes", [])
        max_results = settings.get("max_results", 100)

        # v1.1.0 settings used by calculate_build_stats + _compute_optimizer_score
        set_effect_share = settings.get("set_effect_pct", 0) / 100.0
        effective_level = settings.get("optimize_for_level")

        # Phase 5: per-character preset weights for the slot pre-filter
        # heuristic. When the user has assigned a custom preset to this
        # character, we sort each slot's candidates by their score under
        # THAT preset before the Top filter trims down; this keeps the
        # filter aligned with the character's actual build goals rather
        # than the global active preset (which might be a completely
        # different build archetype). Empty dict / missing key falls back
        # to fragment.gear_score (the active preset's value).
        slot_filter_weights = settings.get("slot_filter_weights") or None

        # Phase 4 set-combo configuration. `sets_selected` is the full list
        # of set IDs the user marked as usable for this character; the optimizer
        # works out which combo shapes are possible. `max_flex_slots` caps how
        # many slots in a build may NOT belong to a satisfied chosen-set bonus
        # ("wildcard slots"). See _count_locked_slots for the unified rule.
        # If sets_selected isn't supplied, fall back to the union of legacy
        # four/two_piece_sets so older callers keep working -- the locked-count
        # rule then still behaves correctly under the equivalent semantics.
        sets_selected = settings.get("sets_selected")
        if sets_selected is None:
            sets_selected = list({*required_4pc_list, *required_2pc})
        sets_selected = [s for s in sets_selected if s in SETS]
        max_flex_slots = int(settings.get("max_flex_slots", 6))

        # Counters for caller messaging. Reset on every optimize() call.
        # See check_queue in optimizer_tab for the "0 builds matched"
        # popup that uses passed_have_at_least vs passed_set_reqs to
        # distinguish "no candidates" from "all filtered". In Phase 4
        # `passed_set_reqs` counts combos that passed the locked-count
        # rule (which subsumes the legacy 4pc/2pc check).
        self.last_optimize_stats = {
            "total_combinations": 0,
            "passed_set_reqs": 0,
            "passed_have_at_least": 0,
        }

        # Phase 4 candidate pool sizing:
        # - When max_flex_slots == 0 AND sets_selected is non-empty, we know
        #   every slot must belong to a chosen set -- restrict candidates to
        #   chosen sets for efficiency (smaller search space).
        # - Otherwise (wildcards allowed, or no chosen sets) broaden the pool
        #   to all sets; the locked-count rule filters invalid combos during
        #   enumeration.
        if max_flex_slots == 0 and sets_selected:
            candidate_set_filter = list(sets_selected)
        else:
            candidate_set_filter = None

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
                required_sets=candidate_set_filter,
                required_main=main_filter,
                top_percent=top_percent,
                use_priority_score=False,  # v1.1.0: always sort by gear_score
                                            # (priority sliders are gone from UI)
                min_rarity=3,  # Only Rare+ for optimizer
                score_weights=slot_filter_weights,  # Phase 5: per-character preset
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
            self.last_optimize_stats["total_combinations"] += 1

            piece_ids = [p.id for p in combo]
            if len(piece_ids) != len(set(piece_ids)):
                continue

            # Phase 4 unified set-combo rule (replaces the legacy any-4pc +
            # all-2pc check). Count slots locked into chosen-set bonuses; the
            # build is valid if its wildcard count fits under max_flex_slots.
            # See _count_locked_slots docstring for the shape taxonomy.
            locked = self._count_locked_slots(combo, sets_selected)
            if (6 - locked) > max_flex_slots:
                continue

            self.last_optimize_stats["passed_set_reqs"] += 1

            # Compute build stats. set_effect_share lets conditional Crit
            # DMG / Crit Rate sets contribute to Final stats at the right
            # weighting; conditional DMG multi / DMG add sets affect the
            # damage card multiplier separately inside _compute_optimizer_score.
            stats = self.calculate_build_stats(
                list(combo), char_name,
                effective_level=effective_level,
                set_effect_share=set_effect_share,
            )

            # Hard constraint: "Have at least this much". Builds that fail
            # any minimum are excluded entirely (not just docked points).
            if not self._meets_have_at_least(stats, settings):
                continue

            self.last_optimize_stats["passed_have_at_least"] += 1

            # v1.1.0 scoring (see docs §8)
            total_score = self._compute_optimizer_score(
                list(combo), stats, settings, char_name
            )

            results.append((list(combo), total_score, stats))

            if progress_callback and checked % 5000 == 0:
                progress_callback(checked, total_perms, len(results))

            if len(results) > max_results * 10:
                results.sort(key=lambda x: -x[1])
                results = results[:max_results]

        results.sort(key=lambda x: -x[1])
        results = results[:max_results]

        # Round 9: rescale the SCORE COLUMN so the numbers are comparable both
        # within a list and across characters, WITHOUT disturbing the ranking.
        # Divide every score by the character's "buff baseline" -- the card
        # multiplier with set effects removed:
        #     baseline = avg_card_dmg/100 * (1 + avg_mult_buff/100)
        #                + avg_add_buff/100
        # This is a per-CHARACTER constant (identical for every build in the
        # list), so dividing by it preserves order AND ratios EXACTLY --
        # monotonic, and the visual gaps (e.g. "top is ~5% above 2nd") are
        # unchanged. It also divides out the user's external-buff assumptions,
        # so two characters with different Avg Card DMG% / buff settings can be
        # compared on build quality alone (a low-scoring roster member then
        # genuinely reflects weaker MFs/sets, not just lower assumed buffs).
        #
        # Exactness note: the baseline is the damage card multiplier WITHOUT
        # the conditional DMG-multi/DMG-add set terms (those add into the real
        # multiplier rather than scaling it). So when such set effects are
        # active the cross-character normalization is approximate -- but the
        # within-list order and ratios stay exact regardless, because the
        # divisor is a single constant for the whole list.
        base_mult = settings.get("avg_card_dmg_pct", 100) / 100.0
        mult_buff = settings.get("avg_mult_buff_pct", 0) / 100.0
        add_buff = settings.get("avg_add_buff_pct", 0) / 100.0
        buff_baseline = base_mult * (1.0 + mult_buff) + add_buff
        if buff_baseline <= 0:
            buff_baseline = 1.0
        return [(gear, score / buff_baseline, stats)
                for gear, score, stats in results]
