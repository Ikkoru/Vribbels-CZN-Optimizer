"""
Memory Fragment set definitions for CZN.
Contains set bonus information and derived lists.

Entry shape
===========
    SETS[set_id] = {
      "name":     "Black Wing",
      "pieces":   2,               # 2 or 4 -- pieces needed to complete
      "bonus":    "+12% Attack",   # description text, shown in the UI
      "type":     "unconditional", # or "conditional"
      "stat":     "ATK%",          # see the vocabulary table below
      "value":    12,              # magnitude, in that stat's own units
      "elements": ["Void"],        # optional; the card elements the
                                   # bonus text names. Cosmetic -- the
                                   # Set Configuration rows colour
                                   # themselves by it; no formula reads it.
    }

`type` field semantics (see docs/game_formulas.md §5 for full treatment):
  - "unconditional": the bonus is always active when the set is
    complete. The `stat` and `value` fields tell the optimizer where
    to add the bonus -- typically into a Final stat (ATK%, DEF%, HP%,
    Crit DMG, Crit Rate).
  - "conditional": the bonus only triggers under specific in-game
    conditions described by `bonus`. The optimizer can't evaluate the
    condition, so it applies the bonus weighted by that set's own
    effect share (the per-set Effect % spinbox in Set Configuration,
    stored per combatant; absent = 0 = the bonus contributes nothing,
    though the set still counts for set-locking).

Stat-name vocabulary for the "stat" field
=========================================
The optimizer consumes ONLY the exact strings below (mapping table:
`SET_STAT_NAME_MAP` in optimizer/core.py). Any other value is silently
ignored -- no error, no effect -- so a typo costs the set its bonus
while leaving it working for set-locking, which is easy to miss.

Note these names match neither the program's internal vocabulary nor
partners.py: the two crit stats are spelled "Crit DMG" / "Crit Rate"
here and "CDmg" / "CRate" everywhere else.

    In-game stat        "stat" value   Internal   Where it lands
    -----------------   ------------   --------   --------------------
    Attack %            "ATK%"         ATK%       inner ATK multiplier,
                                                  same bucket as a
                                                  fragment's ATK%
    Defense %           "DEF%"         DEF%       inner DEF multiplier
    Health %            "HP%"          HP%        inner HP multiplier
    Crit DMG (CDMG)     "Crit DMG"     CDmg       flat addition to
                                                  Final CDmg
    Crit Chance (Crit%) "Crit Rate"    CRate      flat addition to
                                                  Final CRate
    Damage, multiplied  "DMG multi"    --         Multiplicative_Buffs
                                                  in the DAMAGE card
                                                  multiplier
    Damage, added       "DMG add"      --         Additive_Buffs in the
                                                  DAMAGE card multiplier

Two things to know about "DMG multi" / "DMG add": they have no
Final-stat equivalent, so they're absent from SET_STAT_NAME_MAP and
never reach the stat sheet; and they only work on CONDITIONAL sets --
the score's card-multiplier walk skips unconditional ones, so an
unconditional set carrying either name contributes nothing at all.
Neither touches the shield/heal side (buffs don't apply to shields or
heals).

There is deliberately NO spelling for Extra DMG%, DoT%, Ego, or a flat
ATK/DEF/HP bonus: no set grants one today, and the routing in
`core.compute_build_stats` has no bucket for them. A set needing one
means adding that bucket, not inventing a string here.
"""

# Set definitions
SETS = {
 6: {"name": "Conqueror's Aspect", "pieces": 4, "bonus": "+35% Crit DMG to 1-cost Cards", "type": "conditional", "stat": "Crit DMG", "value": 35},
 7: {"name": "Tetra's Authority", "pieces": 2, "bonus": "+12% Defense", "type": "unconditional", "stat": "DEF%", "value": 12},
 8: {"name": "Healer's Journey", "pieces": 2, "bonus": "+12% Max HP", "type": "unconditional", "stat": "HP%", "value": 12},
 9: {"name": "Black Wing", "pieces": 2, "bonus": "+12% Attack", "type": "unconditional", "stat": "ATK%", "value": 12},
 10: {"name": "Seth's Scarab", "pieces": 2, "bonus": "Increase Basic Card DMG, Shield & Healing by 20%", "type": "conditional", "stat": "DMG multi", "value": 20},
 11: {"name": "Executioner's Tool", "pieces": 2, "bonus": "+25% Crit Damage", "type": "unconditional", "stat": "Crit DMG", "value": 25},
 12: {"name": "Instinctual Growth", "pieces": 4, "bonus": "Increase Instinct Card DMG by 20% when 3+ Cards in hand", "type": "conditional", "stat": "DMG multi", "value": 20, "elements": ["Instinct"]},
 15: {"name": "Bullet of Order", "pieces": 4, "bonus": "Increase Order Card DMG by 10% after Attack Card used for 1 turn (max 2 per turn)", "type": "conditional", "stat": "DMG multi", "value": 20, "elements": ["Order"]},
 16: {"name": "Offering of the Void", "pieces": 4, "bonus": "Increase Void Card DMG by 20% after Exhaust for 1 turn (max 1 per turn)", "type": "conditional", "stat": "DMG multi", "value": 20, "elements": ["Void"]},
 18: {"name": "Spark of Passion", "pieces": 4, "bonus": "Increase Passion Card DMG by 20% after Upgrade used (max 1)", "type": "conditional", "stat": "DMG multi", "value": 20, "elements": ["Passion"]},
 19: {"name": "Cursed Corpse", "pieces": 2, "bonus": "Increase DMG by 10% to targets afflicted by Agony", "type": "conditional", "stat": "DMG multi", "value": 10},
 20: {"name": "Line of Justice", "pieces": 4, "bonus": "+20% Crit Rate for 2+ cost Cards", "type": "conditional", "stat": "Crit Rate", "value": 20},
 22: {"name": "Orb of Inhibition", "pieces": 4, "bonus": "+30% Void Card DMG for Cards with 2 or more Hits", "type": "conditional", "stat": "DMG add", "value": 30, "elements": ["Void"]},
 23: {"name": "Judgment's Flames", "pieces": 4, "bonus": "+50% Instinct Card DMG to Ravaged targets", "type": "conditional", "stat": "DMG add", "value": 50, "elements": ["Instinct"]},
 24: {"name": "Beast's Yearning", "pieces": 4, "bonus": "Increase Justice and Order Exhaust Attack Card DMG by 30% (max 5 per turn)", "type": "conditional", "stat": "DMG multi", "value": 30, "elements": ["Justice", "Order"]},
 25: {"name": "Glory's Reign", "pieces": 4, "bonus": "Increase ally DMG by 5% on Exhaust Skill Card create/use (max 15%)", "type": "conditional", "stat": "DMG multi", "value": 15},
 26: {"name": "Prelude to a Hero", "pieces": 4, "bonus": "+15% Crit Rate when a Passion or Void Attack Card of this unit is Discarded for 1 turn (max 15%; max 2 stacks)", "type": "conditional", "stat": "Crit Rate", "value": 15, "elements": ["Passion", "Void"]},
 27: {"name": "Starlight and Dreams", "pieces": 4, "bonus": "Increase ally Counterattack and Extra Attack DMG by 5% when Shield is gained through an ability (max 25%)", "type": "conditional", "stat": "DMG multi", "value": 25},
 28: {"name": "Battlefield Evolution", "pieces": 4, "bonus": "On Extra Attack / Attack Card created in Draw Pile / Draw via Attack Card: +10% Critical Damage (each source max 1 time). When 3 stacks are reached add an additional +5% Critical Damage", "type": "conditional", "stat": "Crit DMG", "value": 35},
 29: {"name": "Sanguine Thorn", "pieces": 4, "bonus": "When Fracture via card, +25% Critical Damage for 1 turn (max 25%, max 2 stacks). When 10+ Fractures via cards, +15% Critical Damage to DoTs (max 15%)", "type": "conditional", "stat": "Crit DMG", "value": 40},
}

TWO_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 2]
FOUR_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 4]
