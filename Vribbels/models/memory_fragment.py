"""
Memory Fragment data model for CZN.

A Memory Fragment is an equippable piece of gear -- the game's analogue
of a relic / artifact in similar gacha games. Each character can equip
one Fragment per slot, slots 1-6. This module defines the in-memory
representation plus the Gear Score (GS) and Potential calculations that
drive the optimizer and the UI.

What lives on a Fragment
========================
- slot_num (1-6, see EQUIPMENT_SLOTS in constants.py)
- set_id  + set_name (e.g. "Spark of Passion" -- 4-piece set)
- rarity_num (1=Common ... 4=Legendary)
- level (current upgrade level, +0 to +15)
- main_stat  (Stat instance; type determined by slot, value by level)
- substats   (list of SubstatRoll; up to 4)
- equipped_to (character name, or None if unequipped)
- gear_score / potential_low / potential_high (cached; see below)

GS and Potential -- the conceptual story
========================================
We want one comparable number per Fragment that says "is this good?"
for a given build (preset of stat weights). Raw approach is straightforward
(weighted sum of substat rolls); the subtlety is making it COMPARABLE.

  Raw score:
      For each substat, take (value / max_value) * weight * 10. That's
      the substat's "fraction of its maximum potential" times the user's
      weighting times a scaling factor.
  Normalization (per-fragment, Philosophy B):
      Two presets with very different weights would produce raw scores
      with very different magnitudes (one preset's "great" could be
      another's "mediocre" numerically). To make scores comparable across
      presets, we map every raw score onto [0, 100]:

         normalize_gs(raw, bounds) = (raw - min_raw) / (max_raw - min_raw) * 100

      where (min_raw, max_raw) is the theoretical floor / ceiling of raw
      scores under THIS preset's weights AS THIS FRAGMENT CAN ACTUALLY
      ACHIEVE THEM. The fragment's main stat is excluded from the bounds
      calculation because a fragment cannot have its main stat appear
      as a substat -- so an MF whose main happens to be a top-4 weighted
      stat would otherwise cap below 100 even with perfectly-rolled
      substats. compute_gs_bounds() takes an `exclude_stat` parameter and
      bounds_for_fragment() is the convenience wrapper that passes the
      fragment's main stat name.

      Practical consequences:
        - Every fragment can in theory reach 100 with perfect substat
          rolls relative to its main-stat constraint.
        - Two fragments with the same substats but different main stats
          can score differently: the one whose main stat is more
          high-weighted under the preset gets a HIGHER score, because
          its bounds ceiling is lower (one fewer high-weight stat
          available in the substat pool), so the same raw value
          normalizes higher. This correctly reflects the build value of
          the main stat (which GS itself doesn't measure).
        - 3-star Rare fragments still cap below 100 because they have
          fewer upgrade rolls than the 4-star ceiling assumes -- the
          bounds use _MAX_UPGRADES_FOR_BOUNDS (= 4-star count).

Potential (low, high)
=====================
Tells the user "what's the range this Fragment can still reach with
remaining upgrades". Each level-up adds a single roll, value chosen
from the per-stat min/max range:

  - Best per upgrade: the upgrade lands on the highest-weighted substat,
    rolling at max_value. Contribution = 10 * best_weight.
  - Worst per upgrade: the upgrade lands on the lowest-(ratio_min*weight)
    substat, rolling at min_value. Contribution = 10 * ratio_min * weight.

remaining_upgrades = UPGRADES_PER_RARITY[rarity] - current_upgrades.
Both extremes are normalized through the same (main-stat-excluding)
bounds so they're on the 0-100 scale.

When low == high (no remaining upgrades), the Fragment is at max level
and Potential is undefined as a range -- callers display "-" in that case.

Why bounds matter for elementals
================================
STATS in constants.py includes both rollable substats (Flat ATK, ATK%,
CRate, ...) and main-stat-only entries (Passion DMG%, Order DMG%, ...).
The latter have min_roll/max_roll set to 0 as a sentinel -- they cannot
roll as substats. Every iteration over STATS that builds GS or Potential
data must skip max_roll <= 0 to avoid polluting the bounds calculation.
This is enforced in _raw_substat_score, compute_gs_bounds, and the
candidate-pool loop in compute_fragment_potential. (Same skip is what
lets fragments WITH elemental main stats reach 100: the elemental main
is already excluded from the substat pool by the max_roll filter, so the
per-fragment exclude_stat=main_name is a no-op for them.)

Module-level helpers vs methods
===============================
The numerical core (_raw_substat_score, compute_gs_bounds, normalize_gs,
compute_fragment_potential) is module-level and pure: same inputs always
produce the same outputs and no state on the Fragment is mutated. The
MemoryFragment methods calculate_base_score / calculate_potential just
delegate to the pure helpers and store the result for later display.

This split exists because per-fragment-per-preset loops (the Highest GS
and Highest Potential columns in the Inventory tab) need to score the
same Fragment under many presets back-to-back without clobbering its
display values, which reflect the globally-Apply'd preset's weights.
"""

from dataclasses import dataclass, field
from typing import Optional

from .stat import Stat, SubstatRoll
from game_data import (
    STATS,
    EQUIPMENT_SLOTS,
    RARITY,
    SETS,
    UPGRADES_PER_RARITY,
    get_character_name,
)


# =============================================================================
# Module-level scoring helpers
# =============================================================================
#
# Gear Score is a weighted sum over substats — but the magnitude of that sum
# depends entirely on the chosen weights, so two presets produce numbers that
# aren't directly comparable. To keep the displayed score on a stable 0-100
# scale per preset, we compute the theoretical (min, max) raw score reachable
# by ANY fragment under the active weights, then linearly rescale every raw
# score into that window.

# Largest #upgrades any rarity supports. Anchors the upper bound so that
# Legendary fragments (with full upgrade headroom) can in principle reach
# the full 100 ceiling -- specifically, those Legendaries whose substats
# match the preset's top-4 weighted stats and whose upgrades all land on
# the top-weighted one. Lower-rarity fragments cap below 100 because they
# have fewer upgrades to spend on the high-weight stat.
_MAX_UPGRADES_FOR_BOUNDS = (
    max(UPGRADES_PER_RARITY.values()) if UPGRADES_PER_RARITY else 0
)


def _raw_substat_score(fragment, weights: dict) -> float:
    """Sum over substats of (value/max_roll) × weight × 10 — the raw weighted
    GS before normalization. Same formula the previous direct GS used."""
    total = 0.0
    for sub in fragment.substats:
        stat_info = STATS.get(
            sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1.0, 0.5)
        )
        max_roll = stat_info[3]
        if max_roll <= 0:
            continue
        normalized = sub.value / (max_roll * sub.roll_count)
        weight = weights.get(sub.name, 1.0)
        total += normalized * sub.roll_count * weight
    return total * 10


def compute_gs_bounds(
    weights: dict, exclude_stat: str | None = None
) -> tuple[float, float]:
    """Theoretical (min_raw, max_raw) GS achievable by ANY fragment under
    these weights -- with optional exclusion of a single stat. Used as the
    calibration window for normalize_gs().

    The exclude_stat parameter exists so we can compute per-fragment bounds
    that respect the rule "a fragment's main stat cannot appear as a
    substat". When excluded, that stat is skipped in the top-4 / bottom-4
    sums AND in the best/worst-per-upgrade picks, so the theoretical max
    drops appropriately. This lets each fragment's GS be normalized against
    what THIS fragment can actually achieve rather than against an abstract
    "any fragment" max -- otherwise fragments whose main stat happens to
    be high-weighted under the preset would cap below 100 even with
    perfectly-rolled substats, which misleads users.

    Pass exclude_stat=None to get the old preset-wide bounds (useful when
    the caller genuinely wants "best any fragment could be" semantics, or
    in tests).

    Mechanics modelled (matches calculate_potential):
      - A fragment has up to 4 substats (one per stat, no duplicates)
      - All upgrade rolls beyond the initial 4 substats can land on a single
        substat -- so the "best" stat absorbs every upgrade in the best case,
        and the "worst" stat absorbs every upgrade in the worst case
      - Each individual roll's value lies in [min_roll, max_roll] for that stat

    For each stat the per-roll contribution is bracketed by:
      high_per_roll = weight x 1.0           (max roll)
      low_per_roll  = weight x min_roll/max_roll
    For positive weights, high > low; for negative weights it flips. Taking
    max/min handles both correctly.

    Bounds:
      max_raw = (sum of top-4 high_per_roll values
                 + max_upgrades x largest high_per_roll) x 10
      min_raw = (sum of bottom-4 low_per_roll values
                 + max_upgrades x smallest low_per_roll) x 10

    Returns (0.0, 0.0) when no usable stat data exists.
    """
    stat_bounds = []  # list[(high_per_roll, low_per_roll)]
    for _raw_name, info in STATS.items():
        if len(info) < 5:
            continue
        display_name = info[0]
        max_roll = info[3]
        min_roll = info[4]
        if max_roll <= 0:
            # Main-stat-only entries (elemental DMG%) -- never substats.
            continue
        if exclude_stat is not None and display_name == exclude_stat:
            # Per-fragment exclusion: this fragment's main stat can never
            # be a substat for this fragment, so it doesn't contribute to
            # the achievable max/min.
            continue
        weight = weights.get(display_name, 1.0)
        ratio_min = min_roll / max_roll
        c_high = weight * 1.0
        c_low = weight * ratio_min
        stat_bounds.append((max(c_high, c_low), min(c_high, c_low)))

    if not stat_bounds:
        return (0.0, 0.0)

    sorted_max = sorted(stat_bounds, key=lambda t: t[0], reverse=True)
    top_4_max = sum(t[0] for t in sorted_max[:4])
    best_per_upgrade = sorted_max[0][0]
    abs_max = (top_4_max + _MAX_UPGRADES_FOR_BOUNDS * best_per_upgrade) * 10

    sorted_min = sorted(stat_bounds, key=lambda t: t[1])
    bottom_4_min = sum(t[1] for t in sorted_min[:4])
    worst_per_upgrade = sorted_min[0][1]
    abs_min = (bottom_4_min + _MAX_UPGRADES_FOR_BOUNDS * worst_per_upgrade) * 10

    return (abs_min, abs_max)


def bounds_for_fragment(
    fragment, weights: dict
) -> tuple[float, float]:
    """Convenience wrapper around compute_gs_bounds that excludes the
    fragment's main stat from consideration. The right bounds to use when
    normalizing this fragment's GS or Potential under `weights`.

    Callers iterating many fragments under the same weights should cache
    by main_stat name -- there are only ~16 possible main stats, so the
    cache caps at that size regardless of fragment count.
    """
    main_name = fragment.main_stat.name if fragment.main_stat else None
    return compute_gs_bounds(weights, exclude_stat=main_name)


def normalize_gs(raw: float, bounds: tuple[float, float]) -> float:
    """Linearly rescale a raw GS into [0, 100] using the theoretical
    (min, max) from compute_gs_bounds(). Values outside that window are
    clamped. Returns 0 when bounds collapse (e.g., all-zero weights)."""
    abs_min, abs_max = bounds
    if abs_max <= abs_min:
        return 0.0
    val = (raw - abs_min) / (abs_max - abs_min) * 100
    return round(max(0.0, min(100.0, val)), 1)


def compute_fragment_potential(
    fragment, weights: dict, bounds: tuple[float, float] | None = None
) -> tuple[float, float]:
    """Pure function: (potential_low, potential_high) for one fragment under
    the given weights, normalized to the 0-100 scale.

    Same math as MemoryFragment.calculate_potential() but without mutating
    the fragment. Useful when scoring the same fragment under many presets in
    a row (e.g., the Highest Potential GS column) — each call needs to leave
    fragment.potential_low/high untouched so the active preset's values stay
    valid for elsewhere in the UI.

    Args:
        fragment: the MemoryFragment instance (only its substats / main_stat /
                  rarity_num are read — never written).
        weights:  stat_name -> weight. Missing keys default to 1.0.
        bounds:   pre-computed (min_raw, max_raw). Computed lazily otherwise.
                  When iterating many fragments under the same weights, pass
                  it in to skip the per-call recomputation.
    """
    if weights is None:
        weights = {}

    raw_base = _raw_substat_score(fragment, weights)

    if fragment.rarity_num < 3 or not fragment.substats:
        raw_low = raw_high = raw_base
    else:
        max_upgrades = UPGRADES_PER_RARITY.get(fragment.rarity_num, 3)
        current_upgrades = sum(s.roll_count - 1 for s in fragment.substats)
        remaining_upgrades = max(0, max_upgrades - current_upgrades)

        if remaining_upgrades == 0:
            raw_low = raw_high = raw_base
        else:
            # Candidate pool: existing substats; if fragment has <4 substats,
            # also any other STAT not already present and not the main stat.
            candidates = []
            existing_names = {s.name for s in fragment.substats}
            for sub in fragment.substats:
                stat_info = STATS.get(
                    sub.raw_name,
                    (sub.name, sub.name, sub.is_percentage, 1.0, 0.5),
                )
                max_roll = stat_info[3]
                min_roll = stat_info[4]
                weight = weights.get(sub.name, 1.0)
                candidates.append((sub.name, max_roll, min_roll, weight))

            if len(fragment.substats) < 4:
                main_name = fragment.main_stat.name if fragment.main_stat else None
                for _raw, info in STATS.items():
                    name, _short, _is_pct, max_roll, min_roll = info
                    if max_roll <= 0:
                        # Main-stat-only entries (elemental DMG%) are not
                        # rollable and must not be considered as potential
                        # 4th-substat candidates.
                        continue
                    if name in existing_names or name == main_name:
                        continue
                    weight = weights.get(name, 1.0)
                    candidates.append((name, max_roll, min_roll, weight))

            if not candidates:
                raw_low = raw_high = raw_base
            else:
                best_per_upgrade = max(w for _n, _mx, _mn, w in candidates)
                worst_per_upgrade = min(
                    ((mn / mx) if mx > 0 else 0.5) * w
                    for _n, mx, mn, w in candidates
                )
                raw_high = raw_base + remaining_upgrades * best_per_upgrade * 10
                raw_low = raw_base + remaining_upgrades * worst_per_upgrade * 10

    if bounds is None:
        # Lazy bounds match what the caller would compute via
        # bounds_for_fragment() -- main stat excluded so 100 is reachable
        # under perfect substat rolls regardless of which main this
        # fragment happens to have. Pass `bounds` explicitly when looping
        # many fragments to skip this per-call overhead (use a cache keyed
        # by main_stat name).
        main_name = fragment.main_stat.name if fragment.main_stat else None
        bounds = compute_gs_bounds(weights, exclude_stat=main_name)
    return (normalize_gs(raw_low, bounds), normalize_gs(raw_high, bounds))


@dataclass
class MemoryFragment:
    id: int
    slot_name: str
    slot_num: int
    rarity: str
    rarity_num: int
    set_name: str
    set_id: int
    level: int
    locked: bool
    equipped_to: Optional[str]
    equipped_char_id: int
    main_stat: Optional[Stat] = None
    substats: list[Stat] = field(default_factory=list)
    gear_score: float = 0.0
    priority_score: float = 0.0
    potential_low: float = 0.0
    potential_high: float = 0.0

    @classmethod
    def from_json(cls, data: dict) -> "MemoryFragment":
        res_id = data["res_id"]
        res_str = str(res_id)
        slot_num = int(res_str[2])
        rarity_num = int(res_str[3])
        set_id = int(res_str[4:])

        main_stat = None
        substat_map = {}
        substat_rolls = {}

        for stat_data in data.get("stat_list", []):
            raw_stat = stat_data["stat"]
            stat_info = STATS.get(raw_stat, (raw_stat, raw_stat, False, 1, 1))
            slot = stat_data["slot"]
            stat_type = stat_data["type"]
            value = stat_data["value"]

            if slot == 0 and stat_type == 0:
                main_stat = Stat(name=stat_info[0], raw_name=raw_stat, value=value,
                                is_percentage=stat_info[2], is_main=True)
            else:
                if slot not in substat_map:
                    substat_map[slot] = Stat(
                        name=stat_info[0], raw_name=raw_stat, value=value,
                        is_percentage=stat_info[2], roll_count=1,
                        base_value=value if stat_type in [1, 2] else 0.0
                    )
                    substat_rolls[slot] = [(value, stat_type)]
                else:
                    substat_map[slot].value += value
                    substat_map[slot].roll_count += 1
                    substat_rolls[slot].append((value, stat_type))
                    if stat_type == 3:
                        substat_map[slot].upgrade_values.append(value)
                    elif stat_type in [1, 2] and substat_map[slot].base_value == 0:
                        substat_map[slot].base_value = value

        for slot, stat in substat_map.items():
            stat_info = STATS.get(stat.raw_name, (stat.name, stat.name, stat.is_percentage, 1.0, 0.5))
            max_roll = stat_info[3]
            min_roll = stat_info[4]

            for value, stat_type in substat_rolls.get(slot, []):
                is_min = abs(value - min_roll) < 0.01
                is_max = abs(value - max_roll) < 0.01
                stat.rolls.append(SubstatRoll(value=value, stat_type=stat_type,
                                             is_min_roll=is_min, is_max_roll=is_max))

            if stat.base_value == 0 and stat.rolls:
                stat.base_value = stat.rolls[0].value

        substats = list(substat_map.values())
        char_id = data.get("char_res_id", 0)
        equipped_to = get_character_name(char_id)
        # Unknown sets are displayed by their bare numeric ID (no "Unknown(...)").
        set_info = SETS.get(set_id, {"name": str(set_id)})
        set_name = set_info["name"] if isinstance(set_info, dict) else set_info

        return cls(
            id=data["id"], slot_name=EQUIPMENT_SLOTS.get(slot_num, f"Unknown({slot_num})"),
            slot_num=slot_num, rarity=RARITY.get(rarity_num, f"Unknown({rarity_num})"),
            rarity_num=rarity_num, set_name=set_name, set_id=set_id,
            level=data.get("level", 0), locked=data.get("lock", False),
            equipped_to=equipped_to, equipped_char_id=char_id,
            main_stat=main_stat, substats=substats,
        )

    def calculate_base_score(
        self,
        weights: Optional[dict] = None,
        bounds: Optional[tuple[float, float]] = None,
    ) -> float:
        """Compute and store this fragment's gear score, normalized to a
        0-100 scale based on the theoretical bounds for the given weights.

        Args:
            weights: stat_name -> weight. Missing stats default to 1.0. Pass
                     None or {} for unweighted (= flat 1.0 across all stats).
            bounds:  pre-computed (min_raw, max_raw) for the same weights.
                     Pass it in when looping over many fragments to avoid
                     recomputing the bounds on every call. Computed lazily
                     if omitted.
        """
        if weights is None:
            weights = {}
        raw = _raw_substat_score(self, weights)
        if bounds is None:
            # Match the Philosophy B convention used elsewhere: exclude this
            # fragment's main stat from the bounds so 100 is reachable for
            # this fragment specifically (rather than the abstract "any
            # fragment" ceiling). Callers iterating many fragments under
            # the same weights should pass `bounds` explicitly from a
            # per-main-stat cache to skip this per-call work.
            main_name = self.main_stat.name if self.main_stat else None
            bounds = compute_gs_bounds(weights, exclude_stat=main_name)
        self.gear_score = normalize_gs(raw, bounds)
        return self.gear_score

    def calculate_priority_score(self, priorities: dict[str, int]) -> float:
        priority_score = 0.0
        for sub in self.substats:
            stat_info = STATS.get(sub.raw_name, (sub.name, sub.name, sub.is_percentage, 1, 1))
            max_roll = stat_info[3]
            normalized = sub.value / (max_roll * sub.roll_count) if max_roll > 0 else 0
            priority = priorities.get(sub.name, 0)
            priority_score += normalized * priority * sub.roll_count
        self.priority_score = round(priority_score * 10, 1)
        return self.priority_score

    def calculate_potential(
        self,
        weights: Optional[dict] = None,
        bounds: Optional[tuple[float, float]] = None,
    ) -> tuple[float, float]:
        """Compute and store the worst- and best-case GS reachable through
        remaining upgrades, normalized to the same 0-100 scale as gear_score.

        The math lives in module-level compute_fragment_potential(); this
        method just stores the result on self for later display. Callers that
        need to score this fragment under multiple presets back-to-back
        without clobbering self.potential_low/high should call the pure
        helper directly.

        Args:
            weights: stat_name -> weight. Missing stats default to 1.0.
            bounds:  pre-computed (min_raw, max_raw) for these weights —
                     pass when iterating many fragments to avoid recomputation.
        """
        low, high = compute_fragment_potential(self, weights or {}, bounds)
        self.potential_low = low
        self.potential_high = high
        return (low, high)

    def get_total_stats(self) -> dict[str, float]:
        stats = {}
        if self.main_stat:
            stats[self.main_stat.name] = stats.get(self.main_stat.name, 0) + self.main_stat.value
        for sub in self.substats:
            stats[sub.name] = stats.get(sub.name, 0) + sub.value
        return stats

    def get_set_pieces(self) -> int:
        set_info = SETS.get(self.set_id)
        if set_info:
            return set_info.get("pieces", 2)
        return 2
