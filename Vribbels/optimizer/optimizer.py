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
picture. The damage and shield/heal scoring formulas are layered on
top of this baseline.

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
  potential_node% Percentage bonuses from the character's level-50 and
                  level-60 potential nodes -- the only two the program
                  models. Flat bonuses from nodes 10/20/30 don't go
                  here; they're inside the gear_flat layer below.
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
others sit outside it. Treating everything as a single big sum would
over-credit percentage bonuses on top of percentage bonuses; the
layered form matches the in-game math closely enough to compare builds
reliably.

Heuristic stats
===============
Derived stats like EHP, Avg DMG, Max CD, and a Bruiser score are
deliberately NOT computed: they varied unpredictably between game
versions and weren't actionable. The Final ATK/DEF/HP plus GS columns
carry the comparison work; build-quality judgment lives in the user's
preset weights, which is where it belongs.
"""

import json
import time
import itertools
from typing import Callable
from pathlib import Path

from models import MemoryFragment, CharacterInfo, UserInfo
from game_data import (
    get_character, get_character_by_name, get_partner,
    get_level_from_exp, get_partner_level_from_exp,
    get_friendship_bonus, parse_potential_node_ids,
    get_partner_stats, get_partner_passive_stats, get_potential_stat_bonus,
    SETS, SLOT_ORDER, SLOT_MAIN_STATS, ALL_STAT_NAMES
)
# Direct module-path import to avoid relying on game_data/__init__.py
# re-exporting it.
from game_data.characters import get_character_stats_at_level
# Pure GS helper for per-character slot pre-filter sorting. optimize()
# resolves the character's assigned preset weights into the settings
# dict, then this scores candidate fragments inside get_gear_by_slot
# without mutating their cached fragment.gear_score (which still
# reflects the globally-active preset). compute_gs_bounds is imported
# alongside since the per-slot bounds cache reuses it.
from models.memory_fragment import compute_fragment_gs, compute_gs_bounds
# Pure per-combo evaluation core. The formula bodies live there; the
# methods on GearOptimizer below are thin wrappers that build the
# char-static inputs and delegate, so there is exactly one
# implementation of each formula. SET_STAT_NAME_MAP is re-exported here
# for back-compat with existing importers.
from optimizer import core
from optimizer.core import SET_STAT_NAME_MAP  # noqa: F401  (re-export)
# Parallel enumeration path. Imported at module level (cheap -- no pool
# or Manager is created until the first parallel run); optimize()
# dispatches to it for large runs when optimizer_workers allows, with
# the sequential path kept as the fallback.
from optimizer import parallel


# Slot V main stats that are element DMG% -- i.e. everything a Slot V
# main can be except ATK%/HP%. Consumed by the off-element candidacy
# filter in get_gear_by_slot.
SLOT5_ELEMENT_MAINS = frozenset(
    s for s in SLOT_MAIN_STATS[5] if s.endswith(" DMG%")
)


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
        # Optional reference to SettingsManager, injected by
        # czn_optimizer_gui.py at startup. Read by _resolve_worker_count
        # for `optimizer_workers`; the Optimizer tab's per-character
        # "Optimize for LVL" value reaches the formulas through the
        # settings dict / effective_level argument instead.
        self.settings_manager = None

    def load_data(self, filepath: str):
        """
        Load capture data from JSON file.

        Parses inventory (piece_items) and character data, creating MemoryFragment
        objects and CharacterInfo objects.

        Args:
            filepath: Path to capture JSON file
        """
        with open(filepath, "r", encoding="utf-8") as f:
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

        # Lookup keyed by *instance id*, covering every PARTNER entry —
        # used as a fallback when a character's partner_id points at a partner
        # whose res_id isn't in PARTNERS. Without this, we'd lose the partner's
        # res_id entirely (and couldn't tell the user what to add to partners.py).
        # Character entries carry no instance id, so they're skipped.
        all_items_by_id = {char["id"]: char for char in char_items if "id" in char}

        # The snapshot lumps characters AND partner cards into this one
        # list with no explicit type field -- but the game gives the two
        # DIFFERENT SCHEMAS, which is the reliable discriminator:
        #
        #   character entries carry the progression fields
        #     (potential_node_ids, friendship_exp, psychosis_*,
        #      card_animations, ...) and have NO instance id;
        #   partner entries are a short record whose distinguishing
        #     fields are `id` (instance id) and `lock`, with none of the
        #     character progression fields.
        #
        # So an `id` key means partner and a potential_node_ids /
        # friendship_exp key means character. The CHARACTERS / PARTNERS
        # tables are consulted only as a fallback, for entries that carry
        # neither marker.
        #
        # Do NOT test whether potential_node_ids is non-EMPTY. A
        # brand-new character has "[]" until its first node is unlocked,
        # and an emptiness test classified it as a partner -- it then
        # vanished from every tab until an MF was equipped to it, which
        # reintroduced it through the equipped-gear path only.
        #
        # Res_id ranges are NOT usable: characters and partners both
        # appear in the 1xxx and 3xxxx ranges in real snapshots.
        #
        # NB: `partner_id` means different things on the two schemas. On
        # a character it's the equipped partner's INSTANCE id (what
        # partner_lookup is keyed by). On a partner it's a back-reference
        # to the owning character's RES id. Only the character -> partner
        # direction is used here.
        for char in char_items:
            res_id = char.get("res_id", 0)
            inst_id = char.get("id", 0)
            if "potential_node_ids" in char or "friendship_exp" in char:
                hero_items.append(char)
            elif "id" in char or "lock" in char:
                partner_lookup[inst_id] = char
            elif res_id and get_character(res_id).get("name") != "Unknown":
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

            # Captured-but-unknown characters (a res_id not yet in
            # characters.py) must NOT be skipped here: skipping them means
            # they only appear in the Combatants / Optimizer tabs via the
            # `characters` dict (equipped gear) -- so they'd VANISH when
            # their last MF was unequipped. Instead, give them a
            # CharacterInfo keyed by the numeric res_id string (matching
            # get_character_name's behavior, so this character_info key
            # lines up with the `equipped_to` value used in the
            # `characters` dict). They show up on capture and persist
            # regardless of equipped gear. Only a falsy/zero res_id is a
            # genuinely empty entry to skip.
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
                         min_level: int = 0,
                         offelement_attribute: str = None,
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
            min_level: Minimum fragment level (0 = no filter). Applied
                during candidate collection -- before the sort and the
                top-N / 10-fragment-floor selection -- so the floor's
                "keep at least 10 per slot" guarantee applies to the
                fragments that passed this filter.
            offelement_attribute: When set (a non-empty element name,
                e.g. "Passion") and slot_num == 5, drops candidates
                whose main stat is an element DMG% OTHER than
                "<attribute> DMG%". ATK%/HP% Slot V mains always pass.
                Like min_level, applied before the sort/floor selection.
                None disables the filter (also the right value when the
                character's element can't be resolved).
            score_weights: When provided, rank candidates by their normalized
                GS computed under THESE weights (pure, doesn't mutate
                fragment.gear_score). When None, use the cached
                fragment.gear_score which reflects the globally-active
                Scoring tab preset. This is wired to the CURRENT
                CHARACTER's assigned preset weights so the pre-filter
                heuristic matches the character's actual build goals
                rather than the global default.

        Returns:
            List of MemoryFragment objects matching filters, sorted by score
        """
        candidates = [f for f in self.fragments
                      if f.slot_num == slot_num and f.rarity_num >= min_rarity
                      and f.level >= min_level]

        if excluded_heroes:
            candidates = [f for f in candidates if f.equipped_to not in excluded_heroes]

        if not include_equipped:
            candidates = [f for f in candidates if not f.equipped_to or f.equipped_to == exclude_char]

        if required_sets:
            candidates = [f for f in candidates if f.set_id in required_sets]

        if required_main and slot_num in [4, 5, 6]:
            candidates = [f for f in candidates if f.main_stat and f.main_stat.name in required_main]

        if offelement_attribute and slot_num == 5:
            on_element = f"{offelement_attribute} DMG%"
            candidates = [
                f for f in candidates
                if not (f.main_stat
                        and f.main_stat.name in SLOT5_ELEMENT_MAINS
                        and f.main_stat.name != on_element)
            ]

        if use_priority_score:
            candidates.sort(key=lambda f: -f.priority_score)
        elif score_weights is not None:
            # Per-character pre-filter sort. We score every candidate
            # under the character's weights using the pure helper so
            # fragment.gear_score (set by the active preset) stays intact
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
        # builds; the percentage handles large inventories. The cap stays at
        # len(candidates) so we never return more than we have.
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

    def _resolve_effective_level(self, char_name: str, effective_level) -> int:
        """Resolve the level at which to read base stats.

        Priority:
          1. effective_level argument from the caller (the Optimizer
             tab's per-character "Optimize for LVL" stepper flows
             through here; the Combatants-tab "Calculate GS for lvl:"
             setting is GS-scoped and intentionally does NOT).
          2. max(60, actual character level), clamped to 62.
          3. 60 fallback.

        Optimizer's contract: stats are computed at level >= 60. For
        characters below 60 we still use the level-60 baseline (their
        in-game stats would be lower, but the optimizer exists to
        compare endgame builds, not model mid-level progression).
        """
        if not char_name:
            return 60
        if effective_level is None:
            actual_level = (self.character_info[char_name].level
                            if char_name in self.character_info else 60)
            return max(60, min(62, actual_level))
        try:
            return max(60, min(62, int(effective_level)))
        except (ValueError, TypeError):
            return 60

    def _build_char_static(self, char_name: str, effective_level: int) -> dict:
        """Build the char-static input dict consumed by core.compute_build_stats.

        Everything here is constant across all combos of an optimize()
        run (base stats at the effective level, affection, partner
        flats + passives, potential-node bonuses, equipment constants),
        so optimize() computes it ONCE per run via build_run_context
        instead of once per combo -- a meaningful hot-loop saving on
        its own. calculate_build_stats builds it per call for all other
        callers.

        get_character_stats_at_level applies the character's optional
        level_61_bonus / level_62_bonus (per-character keys in the
        CHARACTERS dict) when the level is 61/62. Characters without
        those keys fall back to their level-60 base stats, so for them
        this is a no-op.
        """
        cs = core.empty_char_static()
        # Equipment constants apply to every build (even char_name=None
        # calls -- historical behavior).
        cs["equip_flat_atk"] = self.EQUIPMENT_FLAT_ATK
        cs["equip_flat_def"] = self.EQUIPMENT_FLAT_DEF
        cs["equip_flat_hp"] = self.EQUIPMENT_FLAT_HP
        cs["equip_atk_pct"] = self.EQUIPMENT_ATK_PCT
        cs["equip_def_pct"] = self.EQUIPMENT_DEF_PCT
        cs["equip_hp_pct"] = self.EQUIPMENT_HP_PCT
        if not char_name:
            return cs

        char_data = get_character_by_name(char_name)
        scaled = get_character_stats_at_level(char_data, effective_level)
        cs["base_atk"] = scaled["base_atk"]
        cs["base_def"] = scaled["base_def"]
        cs["base_hp"] = scaled["base_hp"]
        cs["base_cr"] = char_data.get("base_crit_rate", 0)
        cs["base_cd"] = char_data.get("base_crit_dmg", 125.0)

        if char_name in self.character_info:
            char_info = self.character_info[char_name]
            fb = char_info.friendship_bonus
            cs["affection_atk"], cs["affection_def"], cs["affection_hp"] = (
                fb[0], fb[1], fb[2]
            )

            if char_info.partner_res_id:
                partner_stats = get_partner_stats(
                    char_info.partner_res_id, char_info.partner_level
                )
                cs["partner_flat_atk"] = partner_stats["atk"]
                cs["partner_flat_def"] = partner_stats["def"]
                cs["partner_flat_hp"] = partner_stats["hp"]

                partner_passive = get_partner_passive_stats(
                    char_info.partner_res_id, char_info.partner_limit_break
                )
                cs["partner_atk_pct"] = partner_passive.get("ATK%", 0)
                cs["partner_def_pct"] = partner_passive.get("DEF%", 0)
                cs["partner_hp_pct"] = partner_passive.get("HP%", 0)
                cs["partner_cdmg"] = partner_passive.get("CDmg", 0)
                cs["partner_extra_dmg"] = partner_passive.get("Extra DMG%", 0)
                cs["partner_crate"] = partner_passive.get("CRate", 0)
                cs["partner_dot"] = partner_passive.get("DoT%", 0)
                cs["partner_ego"] = partner_passive.get("Ego", 0)

                # Conditional partner effects ("stats_conditional"):
                # scored at full encoded value, excluded from the
                # Have-at-least comparison values (see core).
                partner_cond = get_partner_passive_stats(
                    char_info.partner_res_id, char_info.partner_limit_break,
                    conditional=True,
                )
                cs["partner_atk_pct_cond"] = partner_cond.get("ATK%", 0)
                cs["partner_def_pct_cond"] = partner_cond.get("DEF%", 0)
                cs["partner_hp_pct_cond"] = partner_cond.get("HP%", 0)
                cs["partner_crate_cond"] = partner_cond.get("CRate", 0)
                cs["partner_cdmg_cond"] = partner_cond.get("CDmg", 0)
                cs["partner_extra_dmg_cond"] = partner_cond.get("Extra DMG%", 0)
                cs["partner_dot_cond"] = partner_cond.get("DoT%", 0)
                cs["partner_ego_cond"] = partner_cond.get("Ego", 0)

            potential_stats = {}  # Potential-node bonuses
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
            cs["pot_atk_pct"] = potential_stats.get("ATK%", 0)
            cs["pot_def_pct"] = potential_stats.get("DEF%", 0)
            cs["pot_hp_pct"] = potential_stats.get("HP%", 0)
            cs["pot_crate"] = potential_stats.get("CRate", 0)
            cs["pot_cdmg"] = potential_stats.get("CDmg", 0)

        return cs

    def build_run_context(self, char_name: str, settings: dict,
                          sets_selected: list, max_flex_slots: int) -> dict:
        """Assemble the per-run context dict consumed by core.evaluate_combo.

        Built ONCE per optimize() run (and, in the parallel path, once
        in the parent then shipped to every worker). All values are
        plain picklable data.
        """
        effective_level = self._resolve_effective_level(
            char_name, settings.get("optimize_for_level")
        )
        score_pre = core.build_score_precompute(settings)
        return {
            "char_static": self._build_char_static(char_name, effective_level),
            "attribute": self._resolve_attribute(char_name, settings),
            # Per-conditional-set effect shares (same parse the score
            # precompute carries -- one source of truth).
            "set_effect_shares": score_pre["set_effect_shares"],
            "sets_selected": list(sets_selected),
            "max_flex_slots": int(max_flex_slots),
            "hal": settings.get("have_at_least") or {},
            "score_pre": score_pre,
            # Greedy trim references. Placeholder here (slot candidates
            # aren't built until optimize()); optimize() overwrites this
            # with core.build_greedy_refs(...) once the per-slot
            # candidate lists exist, BEFORE any enumeration.
            # {"D": 1.0, "S": 1.0} keeps trim_blend well-defined for any
            # caller that evaluates combos without setting refs.
            "gref": {"D": 1.0, "S": 1.0},
        }

    def _calibration_reference_build(self, char_name: str,
                                     slot_candidates: dict) -> list:
        """The build the Agony calibration is measured against.

        Chosen per SLOT rather than per build: the combatant's own
        equipped fragment wherever they have one, the slot's top
        candidate wherever they do not. The percentage the user typed
        describes the damage they were looking at, so their real gear is
        the honest reference -- but a half-geared combatant read
        literally would be calibrated against empty slots, which is less
        crit than they will actually be running, and the mixed shares
        would tilt accordingly.

        A slot with neither is simply left out; a run in that state
        returns no results anyway.
        """
        equipped = {}
        for piece in self.characters.get(char_name, []):
            equipped.setdefault(piece.slot_num, piece)

        reference = []
        for slot_num in SLOT_ORDER:
            piece = equipped.get(slot_num)
            if piece is None:
                candidates = slot_candidates.get(slot_num) or []
                if not candidates:
                    continue
                piece = candidates[0]
            reference.append(piece)
        return reference

    def calculate_build_stats(self, gear: list[MemoryFragment],
                               char_name: str = None, *,
                               effective_level: int = None,
                               set_effect_shares: dict = None) -> dict[str, float]:
        """
        Calculate final stats for a gear build.

        Implements the Final ATK / DEF / HP formula:

          inner_X = (Base X + Partner X) * (1 + Memory_Fragment_X% + Potential_X%)
                    + Gear_Flat_X + Affinity_Flat_X
          Final X = inner_X * (1 + Partner_X% + Equipment_X%) + Equipment_Flat_X

        Also computes the optimizer-scoring helper Shield_Heal_DEF
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
            set_effect_shares: Per-conditional-set effect share dict
                ({set_id: 0.0–1.0}, see core.parse_set_effect_shares) —
                each conditional set's Crit DMG / Crit Rate contribution
                is weighted by its own share. None/empty (default): no
                conditional set effect is applied to Final stats —
                unconditional sets still apply at full value. Callers
                outside the optimizer (Heroes tab, etc.) leave this
                unset since the conditional bonuses aren't actually
                always active in-game.

        Returns:
            Dictionary with Final ATK/DEF/HP, CRate, CDmg, the summed substat
            % buckets (informational), Ego / Extra DMG% / DoT%, and the
            underscore-prefixed `_base_def_for_shield` and `_shield_heal_def`
            used by _compute_optimizer_score.
        """
        # Formula body lives in optimizer/core.py; this wrapper resolves
        # the level, builds the char-static inputs, and delegates.
        effective_level = self._resolve_effective_level(char_name, effective_level)
        cs = self._build_char_static(char_name, effective_level)
        return core.compute_build_stats(gear, cs,
                                        set_effect_shares=set_effect_shares)

    def _count_locked_slots(self, combo, sets_selected: list) -> int:
        """Count how many slots are "locked" into a chosen set's satisfied
        bonus. Delegates to core.count_locked_slots -- see its docstring
        for the wildcard rule and the combo-shape taxonomy."""
        return core.count_locked_slots(combo, sets_selected)

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
        Delegates to core.meets_have_at_least -- see its docstring. These
        minimums exist primarily (but not exclusively) for the in-game
        Potential 7 stat requirements; per in-game verification, those
        checks ignore all Partner PASSIVE bonuses, all Equipment
        contributions, and conditional set procs (Partner flat class
        stats DO count), and the comparison values match."""
        return core.meets_have_at_least(stats, settings.get("have_at_least") or {})

    def _compute_optimizer_score(self, gear: list, stats: dict,
                                  settings: dict, char_name: str) -> float:
        """Scalar optimizer score: damage / shield-heal blend.

        Delegates to core.compute_score (see docs/game_formulas.md §3,
        §4, §5, §8 and optimizer/core.py for the formula body). Kept as
        a method because callers outside optimize() -- e.g. the Optimizer
        tab's refresh_after_load score recompute -- hold a GearOptimizer
        and a raw settings dict; optimize() itself goes through the
        per-run context + core.evaluate_combo instead.

        Returns a scalar score; higher is better. Magnitudes are
        arbitrary -- rankings are stable but absolute numbers aren't
        directly meaningful.
        """
        return core.compute_score(
            gear, stats,
            core.build_score_precompute(settings),
            self._resolve_attribute(char_name, settings),
        )

    def compute_build_breakdown(self, gear: list, char_name: str, *,
                                settings: dict = None) -> dict:
        """Per-source breakdown of a build's final stats.

        `settings` is keyword-only, as is `calculate_build_stats`'
        `effective_level`. The two take the same first two arguments and
        a different THIRD -- a settings dict here, an int level there --
        so a positional call that picks the wrong one is accepted
        silently and returns plausible, wrong numbers.

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
        set_effect (all set contributions), pot7_excluded (everything the
        Potential 7 rows subtract: conditional set contributions plus ALL
        partner passive crit contributions), other (numeric). For Element%/Extra DMG%/DoT%/Ego:
        the relevant mf_main / mf_sub split plus a numeric `other`;
        Extra DMG% / DoT% / Ego also carry `pot7_excluded` (their partner
        passive contributions -- no conditional-set path feeds these
        stats). Plus
        scalar "xDMG%" (multiplicative buffs) and "+DMG%" (additive
        buffs).
        """
        settings = settings or {}
        set_effect_shares = core.parse_set_effect_shares(settings)
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

        # ----- Affinity + partner flat + partner passive + potential -----
        affection_atk = affection_def = affection_hp = 0
        partner_flat_atk = partner_flat_def = partner_flat_hp = 0
        partner_passive = {}
        partner_cond = {}
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
                partner_cond = get_partner_passive_stats(
                    ci.partner_res_id, ci.partner_limit_break,
                    conditional=True,
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
        # Conditional-only portions of the crit set bonuses. Together
        # with ALL partner crit contributions these form the
        # pot7_excluded buckets the popup's "Potential 7 CRate/CDMG"
        # rows subtract (matching the HAL gate's view; the in-game
        # Potential 7 checks see neither conditional procs nor any
        # partner contribution).
        set_crate_cond = set_cdmg_cond = 0.0
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
            share = set_effect_shares.get(set_id, 0.0)
            if stype == "unconditional":
                eff = val
            elif stype == "conditional" and raw in ("Crit DMG", "Crit Rate"):
                eff = val * share
            elif stype == "conditional" and raw == "DMG multi":
                set_dmg_multi += val * share
                continue
            elif stype == "conditional" and raw == "DMG add":
                set_dmg_add += val * share
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
                if stype == "conditional":
                    set_cdmg_cond += eff
            elif ps_name == "CRate":
                set_crate += eff
                if stype == "conditional":
                    set_crate_cond += eff

        # ----- Potential % + flat-crit, partner passive % -----
        pot_atk_pct = potential.get("ATK%", 0)
        pot_def_pct = potential.get("DEF%", 0)
        pot_hp_pct  = potential.get("HP%", 0)
        pot_crate = potential.get("CRate", 0)
        pot_cdmg  = potential.get("CDmg", 0)
        partner_atk_pct = (partner_passive.get("ATK%", 0)
                           + partner_cond.get("ATK%", 0))
        partner_def_pct = (partner_passive.get("DEF%", 0)
                           + partner_cond.get("DEF%", 0))
        partner_hp_pct  = (partner_passive.get("HP%", 0)
                           + partner_cond.get("HP%", 0))
        partner_cdmg  = partner_passive.get("CDmg", 0)
        partner_extra = partner_passive.get("Extra DMG%", 0)
        partner_crate = partner_passive.get("CRate", 0)
        partner_dot   = partner_passive.get("DoT%", 0)
        partner_ego   = partner_passive.get("Ego", 0)
        # Partner PASSIVE contributions: included in the row totals
        # (they DO affect Final stats and the score) but excluded from
        # every Potential 7 value -- for CRate/CDmg, the unconditional
        # AND conditional partner crit are folded into the
        # pot7_excluded subtraction buckets, mirroring the HAL gate.
        # (The Partner's flat CLASS stats, by contrast, DO count toward
        # Pot7 ATK/DEF/HP -- they sit inside _inner.)
        partner_crate_cond = partner_cond.get("CRate", 0)
        partner_cdmg_cond  = partner_cond.get("CDmg", 0)
        partner_extra_cond = partner_cond.get("Extra DMG%", 0)
        partner_dot_cond   = partner_cond.get("DoT%", 0)
        partner_ego_cond   = partner_cond.get("Ego", 0)

        # ----- Final ATK/DEF/HP (reconciles with calculate_build_stats) -----
        def _final(base, partner_flat, mf_pct, set_pct, pot_pct, gear_flat,
                   affection_flat, partner_pct, equip_pct, equip_flat):
            inner_mult = 1 + (mf_pct + set_pct + pot_pct) / 100
            outer_mult = 1 + (partner_pct + equip_pct) / 100
            inner = (base + partner_flat) * inner_mult + gear_flat + affection_flat
            return inner * outer_mult + equip_flat

        def _inner(base, partner_flat, mf_pct, set_pct, pot_pct, gear_flat,
                   affection_flat):
            # Inner / Potential-7 view: Partner flat class stats
            # included, no Partner passive % and no Equipment. Matches
            # core.compute_build_stats' _inner (plus the set% term this
            # breakdown keeps separate -- unconditional set bonuses are
            # sheet-visible and stay in).
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
            # Equipment has its own column in the popup ("Equip (apx.)"),
            # and sets are broken out as "Set Effect Sum", so every
            # contributor for ATK/DEF/HP is explicitly named. "Other"
            # signals only Equipment ATK%/DEF%/HP% multipliers -- defaults
            # to 0 (so Other = False, displayed as cross), but if the user
            # customizes EQUIPMENT_*_PCT in optimizer.py, the cross flips
            # to check so the popup still reconciles.
            return bool(equip_pct)

        # ----- Crit / element / mechanic stats -----
        attribute = self._resolve_attribute(char_name, settings)
        elem_main = _m(f"{attribute} DMG%") if attribute else 0

        # xDMG% / +DMG% in the popup show ONLY the set-effect
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
                "pot7_excluded": (set_crate_cond + partner_crate
                                  + partner_crate_cond),
                "other": pot_crate + partner_crate + partner_crate_cond,
            },
            "CDmg": {
                "base": base_cd, "mf_main": _m("CDmg"), "mf_sub": _s("CDmg"),
                "set_effect": set_cdmg,
                "pot7_excluded": (set_cdmg_cond + partner_cdmg
                                  + partner_cdmg_cond),
                "other": pot_cdmg + partner_cdmg + partner_cdmg_cond,
            },
            "Element%": {"mf_main": elem_main, "set_effect": 0.0, "other": 0.0},
            "Extra DMG%": {"mf_sub": _s("Extra DMG%"), "set_effect": 0.0,
                           "other": partner_extra + partner_extra_cond,
                           "pot7_excluded": partner_extra + partner_extra_cond},
            "DoT%": {"mf_sub": _s("DoT%"), "set_effect": 0.0,
                     "other": partner_dot + partner_dot_cond,
                     "pot7_excluded": partner_dot + partner_dot_cond},
            "Ego": {"mf_main": _m("Ego"), "mf_sub": _s("Ego"),
                    "set_effect": 0.0, "other": partner_ego + partner_ego_cond,
                    "pot7_excluded": partner_ego + partner_ego_cond},
            "xDMG%": set_dmg_multi,
            "+DMG%": set_dmg_add,
        }

    def _resolve_worker_count(self) -> int:
        """Effective optimizer worker count from settings.json's
        `optimizer_workers` field (0 = auto = cpu_count - 1, 1 =
        single-thread legacy path, N = capped to cpu_count), read
        through the injected SettingsManager. No manager (standalone
        use) or a bad value degrades to auto."""
        configured = 0
        if self.settings_manager is not None:
            try:
                configured = int(
                    self.settings_manager.get("optimizer_workers", 0)
                )
            except (TypeError, ValueError):
                configured = 0
        return parallel.resolve_worker_count(configured)

    def _optimize_sequential(self, slot_candidates: dict, ctx: dict,
                             max_results: int, total_perms: int,
                             progress_callback=None, cancel_flag=None):
        """Single-process enumeration: the small-run path and the
        fallback whenever the parallel path is disabled, under the size
        threshold, or errored. Increments self.last_optimize_stats
        counters in place. Returns (results, checked).

        The per-combo work lives in core.evaluate_combo, shared with
        parallel.evaluate_partition -- the status codes map onto the
        counters identically in both:
        duplicates and set failures skip both passed counters; HAL
        failures count as passed_set_reqs only.
        """
        results = []
        checked = 0
        for combo in itertools.product(*[slot_candidates[s] for s in SLOT_ORDER]):
            if cancel_flag and cancel_flag[0]:
                break

            checked += 1
            self.last_optimize_stats["total_combinations"] += 1

            status, total_score, stats = core.evaluate_combo(combo, ctx)
            if status == core.COMBO_DUPLICATE or status == core.COMBO_SET_FAIL:
                continue
            self.last_optimize_stats["passed_set_reqs"] += 1
            if status == core.COMBO_HAL_FAIL:
                continue
            self.last_optimize_stats["passed_have_at_least"] += 1

            results.append((list(combo), total_score, stats))

            if progress_callback and checked % 5000 == 0:
                progress_callback(checked, total_perms, len(results))

            if len(results) > max_results * 10:
                results.sort(key=core.result_sort_key)
                results = results[:max_results]

        results.sort(key=core.result_sort_key)
        return results[:max_results], checked

    def reblend_results_for_display(self, results: list, char_name: str,
                                   settings: dict) -> list:
        """Re-apply the display blend to an existing results list.

        optimize() ranks/rescales results against the run's true max-D /
        max-S so the top row reads 100. When the Optimizer tab re-maps a
        cached results list after a live equip/upgrade event
        (refresh_after_load), the per-build (D, S) components can change
        (an upgrade alters substats), so the display must be recomputed
        on the SAME basis or the Score column falls back to a different
        scale.

        For each (gear, _oldscore, stats) this recomputes stats +
        components for the remapped gear, then re-blends against the
        max-D / max-S of THIS list and rescales so the top row = 100 --
        identical math to optimize()'s post-merge step, just over the
        already-trimmed list (no re-enumeration, no re-sort: equip/
        upgrade events don't change which builds exist, only their
        numbers, and the tab preserves row identity by index).

        Returns a new list of (gear, display_score, stats) with the
        refreshed stats dicts (including updated _D / _S). Falls back to
        the input entry on any per-build error.
        """
        if not results:
            return results
        sp = core.build_score_precompute(settings)
        # The Agony calibration is a per-run constant measured against a
        # reference build this path cannot reconstruct -- it needs the
        # per-slot candidate lists, which only optimize() has. Recover
        # the run's own value from the results instead; every row of a
        # run carries the same one. Without it the Agony share would be
        # weighted differently here from the run that produced these
        # rows, and the column would shift under an equip with no gear
        # having changed for most of them.
        for _g, _s, st in results:
            if "_agony_cal" in st:
                sp["agony_calibration"] = st["_agony_cal"]
                break
        attribute = self._resolve_attribute(char_name, settings)
        set_effect_shares = sp["set_effect_shares"]
        # Re-score at the SAME level the run used (the "Optimize for LVL"
        # stepper), not the character's actual level. Omitting this let
        # _resolve_effective_level fall back to max(60, actual), so an equip
        # event silently re-based the Results list and the Stats Comparison
        # "New" column onto a different level from the one the run -- and
        # the "Now" column, and both breakdown popups -- were computed at.
        effective_level = settings.get("optimize_for_level")
        rebuilt = []
        for gear, old_score, old_stats in results:
            try:
                stats = self.calculate_build_stats(
                    gear, char_name, effective_level=effective_level,
                    set_effect_shares=set_effect_shares,
                )
                d, s = core.compute_score_components(gear, stats, sp, attribute)
                stats["_D"], stats["_S"] = d, s
                # Re-stamp it: calculate_build_stats returns a fresh
                # dict, so without this a second re-blend would find no
                # calibration to recover and fall back to the default.
                stats["_agony_cal"] = sp["agony_calibration"]
                rebuilt.append((gear, None, stats))
            except Exception:
                rebuilt.append((gear, old_score, old_stats))
        EPS = 1e-9
        d_ref = max((st.get("_D", 0.0) for _g, _s, st in rebuilt), default=0.0)
        s_ref = max((st.get("_S", 0.0) for _g, _s, st in rebuilt), default=0.0)
        d_ref = max(d_ref, EPS)
        s_ref = max(s_ref, EPS)
        scored = []
        for gear, placeholder, stats in rebuilt:
            if placeholder is not None:
                # Per-build recompute failed above -- keep its old score.
                scored.append((gear, placeholder, stats))
                continue
            scored.append((gear, core.display_blend(
                stats.get("_D", 0.0), stats.get("_S", 0.0), sp, d_ref, s_ref,
            ), stats))
        # Rescale so the current top row reads 100, preserving the tab's
        # existing row order (index identity matters for selection
        # restore -- see refresh_after_load).
        top = max((sc for _g, sc, _st in scored if sc is not None),
                  default=0.0)
        if top > 0:
            scale = 100.0 / top
            scored = [(g, (sc * scale if sc is not None else sc), st)
                      for g, sc, st in scored]
        return scored

    def optimize(self, char_name: str, settings: dict, progress_callback: Callable = None,
                 cancel_flag: list = None) -> list[tuple[list[MemoryFragment], float, dict]]:
        """
        Find optimal gear combinations for a character.

        Uses brute-force enumeration with filtering. The build score is
        the damage/shield-heal blended formula from
        docs/game_formulas.md §8. Per-character settings (Important
        Settings sliders, Have at Least minimums, per-set effect
        shares, avg buff fields, level stepper) drive the scoring; see
        _compute_optimizer_score for the formula.

        Side effect: writes `self.last_optimize_stats`, a small counters
        dict the caller can read after optimize() returns to drive UI
        messaging (e.g., distinguishing "no candidate sets found" from
        "every candidate failed Have at Least"). Also carries
        `duration_seconds` and `combos_per_sec` for performance
        baselining.

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
        # Global minimum-MF-level candidacy filter (0 = off).
        try:
            min_gear_level = max(0, int(settings.get("min_gear_level", 0) or 0))
        except (TypeError, ValueError):
            min_gear_level = 0

        # Global off-element Slot V candidacy filter: drop Slot V
        # fragments whose main stat is an element DMG% that doesn't
        # match the character's element (ATK%/HP% mains always pass).
        # Skipped when the character's element can't be resolved
        # (unknown character without an Element override) -- with no
        # element, every element main is equally credit-less, so none is
        # more "off-element" than another.
        offelement_attr = None
        if settings.get("ignore_offelement_slot5"):
            offelement_attr = self._resolve_attribute(char_name, settings) or None

        # Per-character preset weights for the slot pre-filter
        # heuristic. When the user has assigned a custom preset to this
        # character, we sort each slot's candidates by their score under
        # THAT preset before the Top filter trims down; this keeps the
        # filter aligned with the character's actual build goals rather
        # than the global active preset (which might be a completely
        # different build archetype). Empty dict / missing key falls back
        # to fragment.gear_score (the active preset's value).
        slot_filter_weights = settings.get("slot_filter_weights") or None

        # Set-combo configuration. `sets_selected` is the full list
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
        # distinguish "no candidates" from "all filtered".
        # `passed_set_reqs` counts combos that passed the locked-count
        # rule (which subsumes the legacy 4pc/2pc check).
        start_time = time.perf_counter()
        self.last_optimize_stats = {
            "total_combinations": 0,
            "passed_set_reqs": 0,
            "passed_have_at_least": 0,
            # Filled in when the run ends (finished OR cancelled).
            "duration_seconds": 0.0,
            "combos_per_sec": 0.0,
        }

        # Candidate pool sizing:
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
                use_priority_score=False,  # always sort by gear_score
                                            # (no priority sliders in the UI)
                min_rarity=3,  # Only Rare+ for optimizer
                min_level=min_gear_level,  # global "Ignore MFs below level"
                offelement_attribute=offelement_attr,  # global "Ignore off-Element MFs"
                score_weights=slot_filter_weights,  # per-character preset
            )
            slot_candidates[slot_num] = candidates if candidates else []

        # Per-slot candidate counts. The search space is the PRODUCT of
        # these, so they're what any scaling estimate has to be built from --
        # the fragment total on its own says nothing about run time.
        # Recorded BEFORE the empty-slot return below, so a run that
        # dies there still reports which slot came up empty.
        self.last_optimize_stats["slot_candidates"] = {
            slot: len(cands) for slot, cands in sorted(slot_candidates.items())
        }

        for slot_num in SLOT_ORDER:
            if not slot_candidates[slot_num]:
                self.last_optimize_stats["duration_seconds"] = (
                    time.perf_counter() - start_time
                )
                return []

        total_perms = 1
        for slot_num in SLOT_ORDER:
            total_perms *= len(slot_candidates[slot_num])

        # Per-run evaluation context (char-static inputs, resolved
        # attribute, HAL minimums, score precompute): built ONCE here,
        # then every combo is evaluated against it by core.evaluate_combo.
        # Besides enabling the parallel workers (the ctx is plain
        # picklable data), this keeps the per-combo character lookups
        # (partner tables, potential nodes, base stats) out of the hot
        # loop.
        ctx = self.build_run_context(
            char_name, settings, sets_selected, max_flex_slots
        )

        # Put the Agony term on the card-damage scale, BEFORE the greedy
        # refs below -- those score through compute_score_components, so
        # they have to see the finished calibration or the trim would be
        # gated against a different formula from the one that produced
        # the results. Both are per-run constants, which is what keeps
        # the parallel path byte-identical to the sequential one.
        ctx["score_pre"]["agony_calibration"] = core.build_agony_calibration(
            self._calibration_reference_build(char_name, slot_candidates),
            ctx["char_static"], ctx["set_effect_shares"], ctx["score_pre"],
        )

        # Build the per-run GREEDY trim references from the top
        # candidate in each slot, now that slot_candidates exists. These
        # gate the in-flight trim (a per-run constant divisor pair, so
        # parallel/sequential parity and the deterministic tie-break are
        # preserved). The DISPLAYED score is re-blended after the merge
        # against the run's true max-D / max-S (see below).
        ctx["gref"] = core.build_greedy_refs(
            slot_candidates, ctx["char_static"], ctx["set_effect_shares"],
            ctx["score_pre"], ctx["attribute"],
        )

        # ---- Parallel dispatch ----
        # Above the size threshold and with more than one configured
        # worker, the enumeration is farmed out to worker processes
        # (strided partitioning of slot 1 -- see optimizer/parallel.py).
        # The sequential method is both the small-run path and the
        # fallback if the parallel path fails for any reason.
        results = None
        checked = 0
        workers = self._resolve_worker_count()
        if workers > 1 and total_perms >= parallel.PARALLEL_MIN_COMBOS:
            try:
                par_results, counters, checked = parallel.optimize_parallel(
                    slot_candidates, ctx, max_results, workers, total_perms,
                    progress_callback, cancel_flag,
                )
            except Exception:
                # Spawn trouble (frozen-build quirks, AV interference),
                # pickling errors, a broken pool -- fall back to the
                # sequential path below. Correctness over speed.
                par_results = None
                checked = 0
            else:
                for k in ("total_combinations", "passed_set_reqs",
                          "passed_have_at_least"):
                    self.last_optimize_stats[k] = counters[k]
                # Gear returned from workers consists of pickled COPIES
                # of the fragments (they crossed a process boundary);
                # remap onto THIS process's fragment objects by id so
                # identity-adjacent behavior downstream (live-update
                # remapping, owner display) matches the single-thread
                # path exactly.
                by_id = {getattr(f, "id", None): f for f in self.fragments}
                by_id.pop(None, None)
                results = [
                    ([by_id.get(getattr(p, "id", None), p) for p in gear],
                     score, stats)
                    for gear, score, stats in par_results
                ]

        if results is None:
            results, checked = self._optimize_sequential(
                slot_candidates, ctx, max_results, total_perms,
                progress_callback, cancel_flag,
            )

        # Wall time + throughput, recorded whether the run finished or
        # was cancelled.
        duration = time.perf_counter() - start_time
        self.last_optimize_stats["duration_seconds"] = duration
        self.last_optimize_stats["combos_per_sec"] = (
            checked / duration if duration > 0 else 0.0
        )

        # ---- Display re-blend ----
        # Enumeration/trim ranked by the greedy-ref trim blend. Now
        # re-score the survivors against the run's TRUE max-D / max-S
        # (the exact percent-normalized semantics), re-sort, and rescale
        # so the top row reads 100 at any slider position. The (D, S)
        # components rode along in each stats dict under "_D" / "_S".
        #
        # Re-sorting can reorder survivors slightly vs the trim order
        # (greedy refs != run-max refs): the display uses the true
        # references, while the trim only had to keep the right builds
        # IN the survivor pool (it keeps max_results * 10), not rank
        # them for display.
        if results:
            EPS = 1e-9
            d_ref = max((st.get("_D", 0.0) for _g, _s, st in results),
                        default=0.0)
            s_ref = max((st.get("_S", 0.0) for _g, _s, st in results),
                        default=0.0)
            d_ref = max(d_ref, EPS)
            s_ref = max(s_ref, EPS)
            rescored = []
            for gear, _trim, stats in results:
                disp = core.display_blend(
                    stats.get("_D", 0.0), stats.get("_S", 0.0),
                    ctx["score_pre"], d_ref, s_ref,
                )
                rescored.append((gear, disp, stats))
            # Sort by the display score (same deterministic tie-break),
            # then rescale the whole column so the top row = 100.
            rescored.sort(key=core.result_sort_key)
            top = rescored[0][1] if rescored else 0.0
            if top > 0:
                scale = 100.0 / top
                results = [(gear, score * scale, stats)
                           for gear, score, stats in rescored]
            else:
                # Degenerate (all-zero) column -- leave scores as-is
                # rather than divide by zero; ordering already applied.
                results = rescored

        return results
