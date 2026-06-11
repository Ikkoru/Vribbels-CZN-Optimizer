"""
Memory Fragment set definitions for CZN.
Contains set bonus information and derived lists.

`type` field semantics (see docs/game_formulas.md §5 for full treatment):
  - "unconditional": the bonus is always active when the set is
    complete. The `stat` and `value` fields tell the optimizer where
    to add the bonus -- typically into a Final stat (ATK%, DEF%, HP%,
    Crit DMG, Crit Rate).
  - "conditional": the bonus only triggers under specific in-game
    conditions described by `bonus`. The optimizer can't directly
    evaluate the condition, so it applies the bonus weighted by the
    user's "% of damage with set effect" slider.

  The `stat` field for conditional sets uses the extended vocabulary
  `DMG multi` and `DMG add` for the two damage-multiplier shapes that
  can't be expressed as a single Final-stat addition.
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
}

TWO_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 2]
FOUR_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 4]
