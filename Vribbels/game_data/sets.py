"""
Memory Fragment set definitions for CZN.
Contains set bonus information and derived lists.
"""

# Set definitions
SETS = {
    6: {"name": "Conqueror's Aspect", "pieces": 4, "bonus": "+35% Crit DMG to 1-cost Cards", "type": "conditional"},
    7: {"name": "Tetra's Authority", "pieces": 2, "bonus": "+12% Defense", "type": "stat", "stat": "DEF%", "value": 12},
    8: {"name": "Healer's Journey", "pieces": 2, "bonus": "+12% Max HP", "type": "stat", "stat": "HP%", "value": 12},
    9: {"name": "Black Wing", "pieces": 2, "bonus": "+12% Attack", "type": "stat", "stat": "ATK%", "value": 12},
    10: {"name": "Seth's Scarab", "pieces": 2, "bonus": "Increase Basic Card DMG, Shield & Healing by 20%", "type": "conditional"},
    11: {"name": "Executioner's Tool", "pieces": 2, "bonus": "+25% Crit Damage", "type": "stat", "stat": "Crit DMG", "value": 25},
    12: {"name": "Instinctual Growth", "pieces": 4, "bonus": "Increase Instinct Card DMG by 20% when 3+ Cards in hand", "type": "conditional"},
    15: {"name": "Bullet of Order", "pieces": 4, "bonus": "Increase Order Card DMG by 10% after Attack Card used for 1 turn (max 2 per turn)", "type": "conditional"},
    16: {"name": "Offering of the Void", "pieces": 4, "bonus": "Increase Void Card DMG by 20% after Exhaust for 1 turn (max 1 per turn)", "type": "conditional"},
    18: {"name": "Spark of Passion", "pieces": 4, "bonus": "Increase Passion Card DMG by 20% after Upgrade used (max 1)", "type": "conditional"},
    19: {"name": "Cursed Corpse", "pieces": 2, "bonus": "Increase DMG by 10% to targets afflicted by Agony", "type": "conditional"},
    20: {"name": "Line of Justice", "pieces": 4, "bonus": "+20% Crit Rate for 2+ cost Cards", "type": "conditional"},
    22: {"name": "Orb of Inhibition", "pieces": 4, "bonus": "+30% Void Card DMG for Cards with 2 or more Hits", "type": "conditional"},
    23: {"name": "Judgment's Flames", "pieces": 4, "bonus": "+50% Instinct Card DMG to Ravaged targets", "type": "conditional"},
    24: {"name": "Beast's Yearning", "pieces": 4, "bonus": "Increase Justice and Order Exhaust Attack Card DMG by 30% (max 5 per turn)", "type": "conditional"},
    25: {"name": "Glory's Reign", "pieces": 4, "bonus": "Increase ally DMG by 5% on Exhaust Skill Card create/use (max 15%)", "type": "conditional"},
    26: {"name": "Prelude to a Hero", "pieces": 4, "bonus": "+15% Crit Rate when a Passion or Void Attack Card of this unit is Discarded for 1 turn (max 15%; max 2 stacks)", "type": "conditional"},
    27: {"name": "Starlight and Dreams", "pieces": 4, "bonus": "Increase ally Counterattack and Extra Attack DMG by 5% when Shield is gained through an ability (max 25%)", "type": "conditional"},
}

TWO_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 2]
FOUR_PIECE_SETS = [sid for sid, s in SETS.items() if s["pieces"] == 4]
