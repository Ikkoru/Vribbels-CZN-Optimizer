"""
Partner card data and related functions for CZN.

Partners are the secondary equippable units that pair with characters --
analogous to relic-set or weapon-companion mechanics in similar games.
Each character can equip one partner card. Partners contribute three
things to a build:

  1. Flat ATK/DEF/HP added before the inner-layer multipliers in the
     optimizer's damage formula. Scales LINEARLY with partner level.
  2. Unconditional passive stat bonuses (% scaling) that vary with the
     partner's limit-break (E0 through E4) level. Some partners give
     CRate, others Extra DMG%, etc. See get_partner_passive_stats.
  3. A named passive ability whose effect text scales with limit-break.
     This is descriptive only -- not factored into stat math directly.

Module structure
================

PARTNERS
--------
Maps res_id (int) to a partner data dict:
    {
      "name":         "Alyssa",
      "grade":        4,                  # rarity / star count
      "class":        "Controller",       # determines base stat scaling
      "passive_name": "Alchemical Fruits",
      "passive_desc": "...{DEF%}% ...",   # templated effect text
      "values":       {...},              # template-substitution values
      "stats":        {"DEF%": (12, 15, 18, 21, 24)},  # E0..E4 tiers
    }

PARTNER_CLASS_STATS
-------------------
Maps (grade, class) tuples to base ATK/DEF/HP at level 60:
    PARTNER_CLASS_STATS[(4, "Controller")] = {"atk": 92, "def": 9, "hp": 96}

Partners share base-stat profiles by grade+class because the game
ensures balance at that granularity -- two 4-star Controllers have the
same level-60 stats regardless of which character they are. This is
verified empirically against snapshot data.

Level scaling
-------------
get_partner_stats(res_id, level) returns the partner's effective ATK/
DEF/HP at the given level. Scaling is LINEAR from level 0 (zero) to
level 60 (base). This matches the in-game progression closely enough
for build comparison; the game may use a slightly different curve
internally but the linear approximation is well within rounding error
at the levels that matter (50+).

Passive scaling with limit-break
--------------------------------
get_partner_passive_stats reads the partner's "stats" dict (a tuple of
five values, one per E0/E1/E2/E3/E4) and returns the appropriate value
for the given limit_break index. Passives often grant CRate%, Extra
DMG%, or attribute-DMG% -- these feed into the inner-layer MF% bucket
of the optimizer's damage formula.

Unknown partner handling
========================
get_partner returns a generic placeholder for unknown res_ids. The UI
fall-back path in heroes_tab shows "Unknown partner (res_id X, instance
Y)" when this fires; the user is expected to add the partner to the
PARTNERS dict (and rerun) once they have its name.
"""

# Default partner data for unknown partners
DEFAULT_PARTNER = {
    "name": "Unknown",
    "grade": 3,
    "class": "Controller",
    "passive_name": "Unknown Passive",
    "passive_desc": "Unknown passive effect.",
    "values": {},
    "stats": {},
    "ego_name": "Unknown Skill",
    "ego_cost": 2,
    "ego_desc": "Unknown effect.",
}

# Unified partner card data: res_id -> all partner information
# Contains: name, grade, class, passive_name, passive_desc, values, stats, ego_name, ego_cost, ego_desc
# Note: Values marked with # EST are estimated (linear interpolation) - update when real data is available
PARTNERS = {
    20015: {
        "name": "Douglas",
        "grade": 3,
        "class": "Striker",
        "passive_name": "Guard",
        "passive_desc": "The assigned combatant's Attack is increased by {ATK%}%.\nAt the start of battle, Damage dealt by the assigned combatant increases by {DMG%}% for 1 turn.",
        "values": {
            "ATK%": (8,10,12,14,16),
            "DMG%": (8,10,12,14,16),
        },
        "stats": {"ATK%": (8,10,12,14,16)
        },
        "ego_name": "Giant Bazooka",
        "ego_cost": 2,
        "ego_desc": "120% Damage to all enemies",
    },
    20010: {
        "name": "Nakia",
        "grade": 3,
        "class": "Ranger",
        "passive_name": "Hot-Blooded Soldier",
        "passive_desc": "The assigned combatant's Attack is increased by {ATK%}%.\nWhen an ally defeats an enemy, gain 1 [Backline Support].\n[Backline Support]: {DMG%}% Damage of 1 attack card. Upon activation, Backline Support is reduced by 1 (up to 3 stacks).",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "DMG%": (10, 13, 15, 18, 20),
        },
        "stats": {
            "ATK%": (8, 10, 12, 14, 16),
        },
        "ego_name": "Powerful Shot",
        "ego_cost": 2,
        "ego_desc": "Deal 200% Damage.",
    },
    20013: {
        "name": "Raidel",
        "grade": 3,
        "class": "Vanguard",
        "passive_name": "Strategic Analysis",
        "passive_desc": "The combatant's max Health increases by {HP%}%.\nIf the combatant is in Counterattack state, their Defense-Based Damage increases by {DEFDAM%}%.",
        "values": {
            "HP%": (8, 10, 12, 14, 16),
            "DEFDAM%": (8, 10, 12, 14, 16),
        },
        "stats": {"HP%": (8, 10, 12, 14, 16)},
        "ego_name": "Analyze Weakness",
        "ego_cost": 2,
        "ego_desc": "Gain 100% Shield. Gain 1 Counterattack.",
    },
    20016: {
        "name": "Yuri",
        "grade": 3,
        "class": "Hunter",
        "passive_name": "Cantrip",
        "passive_desc": "The assigned combatant's Attack is increased by {ATK%}%.\nUpon the first shuffle, the assigned Combatant's damage dealt is increased by {DMG%}%.",
        "values": {
            "ATK%": (8,10,12,14,16),
            "DMG%": (8,10,12,14,16)
        },
        "stats": {"ATK%": (8,10,12,14,16)},
        "ego_name": "Drone Deployment",
        "ego_cost": 3,
        "ego_desc": "Draw 2",
    },
    20026: {
        "name": "Yvonne",
        "grade": 3,
        "class": "Controller",
        "passive_name": "Bless",
        "passive_desc": "The assigned combatant's Defense is increased by {DEF%}%.\nIf the combatant ends the turn without using an attack card, Heal {heal%}% at the start of the next turn.",
        "values": {
            "DEF%": (8, 10, 12, 14, 16),
            "heal%": (30, 38, 45, 53, 60),
        },
        "stats": {"DEF%": (8, 10, 12, 14, 16)},
        "ego_name": "Consecration",
        "ego_cost": 2,
        "ego_desc": "Heal 100%. For 1 turn, gain 1 Fortitude.",
    },
    20012: {
        "name": "Zatera",
        "grade": 3,
        "class": "Psionic",
        "passive_name": "Fortune Telling",
        "passive_desc": "The assigned combatant's Attack is increased by {ATK%}%.\nWhen Injured, at the end of battle, recover {skill}% Health.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "skill": (4, 5, 6, 7, 8),
        },
        "stats": {"ATK%": (8, 10, 12, 14, 16)},
        "ego_name": "Flower of Memory",
        "ego_cost": 2,
        "ego_desc": "Gain 200% Shield.",
    },
    20007: {
        "name": "Akad",
        "grade": 4,
        "class": "Hunter",
        "passive_name": "Self Defense",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe damage of the combatant's Bullet cards increases by {BulletDMG%}%.\nWhen the combatant lands their first critical hit, Bullet card damage increases by {BulletDMG2%}% for 1 turn.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "BulletDMG%": (10, 13, 15, 18, 20),
            "BulletDMG2%": (12, 15, 18, 21, 24),
        },
        "stats": {"ATK%": (8, 10, 12, 14, 16)},
        "ego_name": "What I Wished to Protect",
        "ego_cost": 2,
        "ego_desc": "For 1 turn, +25% Critical Chance of Designated Combatant's Attack cards.",
    },
    20003: {
        "name": "Alyssa",
        "grade": 4,
        "class": "Controller",
        "passive_name": "Alchemical Fruits",
        "passive_desc": "The assigned combatant's Defense is increased by {DEF%}%.\nAt the end of battle, recover {heal}% Health.",
        "values": {
            "DEF%": (12, 15, 18, 21, 24),
            "heal": (3, 3.8, 4.5, 5.3, 6),
        },
        "stats": {"DEF%": (12, 15, 18, 21, 24)},
        "ego_name": "Vitality Boosting Potion",
        "ego_cost": 2,
        "ego_desc": "Heal 100%. When in an Injured state, increase Healing Amount by 50%. 1 Morale for 1 turn.",
    },
    20001: {
        "name": "Arwen",
        "grade": 4,
        "class": "Controller",
        "passive_name": "Starshine Intellect",
        "passive_desc": "The assigned combatant's HP and healing are increased by {HP%}%.\nAt the start of the turn, gain [Ponopoko's Cheer] equal to the number of enemies with attack intentions.\n[Ponopoko's Cheer]: Incoming Damage is reduced by {DR%}%. Upon activation, remove Ponopoko's Cheer (stacks up to 3 times).",
        "values": {
            "HP%": (8, 9, 10, 11, 12),
            "DR%": (10, 13, 15, 18, 20),
        },
        "stats": {"HP%": (8, 9, 10, 11, 12)},
        "ego_name": "Pokopo Ponpon!",
        "ego_cost": 3,
        "ego_desc": "Heal 200%. Apply 1 Damage Reduction.",
    },
    20036: {
        "name": "Carroty",
        "grade": 4,
        "class": "Hunter",
        "passive_name": "Super Carrot Power!",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nAt the start of the turn, the damage of 1 attack card increases by {cardATK%}% for the combatant.\nWhen the combatant generates a card for the first time, their attack card damage increases by {cardATK%2}% for 1 turn.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "cardATK%": (10, 13, 15, 18, 20),
            "cardATK%2": (10, 13, 15, 18, 20),
        },
        "stats": {"ATK%": (8, 10, 12, 14, 16),},
        "ego_name": "Eating Soft Carrots",
        "ego_cost": 2,
        "ego_desc": "Increase Damage Amount of cards created by Designated Combatant's ability by 20% for 1 turn.",
    },
    20011: {
        "name": "Daisy",
        "grade": 4,
        "class": "Ranger",
        "passive_name": "Dowsing",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nIncrease Damage Amount of the assigned Combatant's Extra Attacks by {Extra DMG%}%.\nWhen the assigned combatant Draws for the first time each turn using an ability, there is a {MChance%}% chance to gain 1 Morale for 1 turn.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "Extra DMG%": (10, 13, 15, 18, 20),
            "MChance%": (20, 25, 30, 35, 40),
        },
        "stats": {
            "ATK%": (8, 10, 12, 14, 16),
            "Extra DMG%": (10, 13, 15, 18, 20),
        },
        "ego_name": "Commencing Detection!",
        "ego_cost": 2,
        "ego_desc": "Gain 180% Shield. Gain 1 Morale for 1 turn.",
    },
    20027: {
        "name": "Eloise",
        "grade": 4,
        "class": "Psionic",
        "passive_name": "Technical Support",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe combatant's attack card damage increases by {atkcard%}%.\nWhen the combatant first Exhausts a card or first gains a Status Ailment card, their attack card damage increases by {atkcard%2}% for 1 turn.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "atkcard%": (10, 13, 15, 18, 20),
            "atkcard%2": (12, 15, 18, 21, 24),
        },
        "stats": {"ATK%": (8, 10, 12, 14, 16),},
        "ego_name": "Activate Defense Module",
        "ego_cost": 3,
        "ego_desc": "For 1 turn, when a card is Exhausted, apply 1 Weaken to a random enemy.",
    },
    20033: {
        "name": "Lillian",
        "grade": 4,
        "class": "Striker",
        "passive_name": "Poltergeist",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe assigned combatant's attack cards with a cost of 1 or less deal {atkDAM%}% damage.\nWhen the assigned combatant uses a Skill card, {atkDAM%2}% attack card damage for 1 turn. Stacks up to 3 times.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "atkDAM%": (10, 13, 15, 18, 20),
            "atkDAM%2": (10, 13, 15, 18, 20),
        },
        "stats": {"ATK%": (8, 10, 12, 14, 16),},
        "ego_name": "Light of Judgment",
        "ego_cost": 3,
        "ego_desc": "Deal 100% Damage to all enemies. Draw 1 Attack card(s) from the assigned combatant with cost of less than or equal to 1.",
    },
    20032: {
        "name": "Rachel",
        "grade": 4,
        "class": "Vanguard",
        "passive_name": "Replenish Energy",
        "passive_desc": "The assigned combatant's skill card shield gain is increased by {shieldgain%}%.\nWhen the assigned combatant gains Shield, {counterchance%}% chance to gain 1 Counterattack.",
        "values": {
            "shieldgain%": (10, 13, 15, 18, 20),
            "counterchance%": (20, 25, 30, 35, 40),
        },
        "stats": {},
        "ego_name": "Colonel Hamburger!",
        "ego_cost": 2,
        "ego_desc": "Gain 100% Shield. Draw 1 Card.",
    },
    20035: {
        "name": "Ritochka",
        "grade": 4,
        "class": "Striker",
        "passive_name": "Construction Support",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe assigned Combatant's attack cards with a cost of 2 or more deal +{Cost2DMG%}% damage.\nAt the start of the turn, 1 of the assigned Combatant's attack cards gains +{CostScaleDMG%}% damage for every point of the total cost of attack cards.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "Cost2DMG%": (10, 13, 15, 18, 20),
            "CostScaleDMG%": (5, 7, 8, 9, 10),
        },
        "stats": {"ATK%": (8, 10, 12, 14, 16),},
        "ego_name": "Workplace hazards ahead!",
        "ego_cost": 2,
        "ego_desc": "For 1 turn, 3 Morale.",
    },
    20025: {
        "name": "Rosaria",
        "grade": 4,
        "class": "Ranger",
        "passive_name": "Financial Support",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe assigned combatant's Extra Attack Damage is increased by {Extra DMG}%.\nWhen the assigned combatant uses an Upgrade or Skill card, {MChance%}% chance to gain 1 Morale for 1 turn.",
        "values": {
            "ATK%": (8, 10, 12, 14, 16),
            "Extra DMG": (10, 13, 15, 18, 20),
            "MChance%": (25, 32, 38, 44, 50),
        },
        "stats": {
            "ATK%": (8, 10, 12, 14, 16),
            "Extra DMG%": (10, 13, 15, 18, 20)
        },
        "ego_name": "Security Team, Requesting Support!",
        "ego_cost": 2,
        "ego_desc": "Draw 1 Enhanced Card(s).\nIf there are no Enhance Cards in the Draw Pile, Draw 1 Card.",
    },
    20024: {
        "name": "Wilhelmina",
        "grade": 4,
        "class": "Vanguard",
        "passive_name": "Battle Command",
        "passive_desc": "The assigned combatant's Defense is increased by {DEF%}%.\nWhen the assigned combatant targets a Vulnerable enemy, {DEFDAM%}% Defense-based Damage of Attack cards.",
        "values": {
            "DEF%": (12, 15, 18, 21, 24),
            "DEFDAM%": (10, 13, 15, 18, 20),
        },
        "stats": {"DEF%": (12, 15, 18, 21, 24)},
        "ego_name": "Tactical Command",
        "ego_cost": 2,
        "ego_desc": "For 1 turn, gain 2 Morale.\nFor 1 turn, gain 1 Fortitude.",
    },
    20008: {
        "name": "Anteia",
        "grade": 4.5,
        "class": "Psionic",
        "passive_name": "Clairvoyance",
        "passive_desc": "Increase the assigned Combatant's Attack, Health, and Damage Amount by {ATKHPDMG%}%.\nWhen a card is created for the first time by the assigned Combatant each turn, +{CardDMG%}% Damage Amount to Attack Cards for 1 turn.",
        "values": {
            "ATKHPDMG%": (12, 14, 16, 18, 20),
            "CardDMG%": (8, 10, 12, 14, 16),
        },
        "stats": {
            "ATK%": (12, 14, 16, 18, 20),
            "HP%": (12, 14, 16, 18, 20),
        },
        "ego_name": "Scholarly Measures",
        "ego_cost": 2,
        "ego_desc": "180% Damage to all enemies. 1 Vulnerable.",
    },
    20005: {
        "name": "Eishlen",
        "grade": 4.5,
        "class": "Vanguard",
        "passive_name": "Arcane Wave",
        "passive_desc": "Increase the assigned Combatant's Defense, Health, and Shield Gain Amount by {DEFHPSHLD%}%.\nWhen the assigned Combatant gains Counterattack for the first time, +{Counter%}%.",
        "values": {
            "DEFHPSHLD%": (12, 14, 16, 18, 20),
            "Counter%": (15, 19, 23, 27, 30),
        },
        "stats": {
            "DEF%": (12, 14, 16, 18, 20),
            "HP%": (12, 14, 16, 18, 20),
        },
        "ego_name": "Innos's Guardian",
        "ego_cost": 4,
        "ego_desc": "100% shield. At the end of the turn, retain 50% of Shield.",
    },
    20006: {
        "name": "Nyx",
        "grade": 4.5,
        "class": "Controller",
        "passive_name": "Resonance",
        "passive_desc": "Increase the assigned Combatant's Defense, Health, and Heal Amount by {DEFHPHEAL%}%.\nWhen the assigned combatant Draws for the first time each turn using an ability, {DMG%}% Damage dealt by allies for 1 turn.",
        "values": {
            "DEFHPHEAL%": (12, 14, 16, 18, 20),
            "DMG%": (8, 10, 12, 14, 16),
        },
        "stats": {
            "DEF%": (12, 14, 16, 18, 20),
            "HP%": (12, 14, 16, 18, 20),
        },
        "ego_name": "Errante Hurricane",
        "ego_cost": 4,
        "ego_desc": "Discard up to 3 cards, then Draw +1 cards equal to the number discarded.",
    },
    20019: {
        "name": "Priscilla",
        "grade": 4.5,
        "class": "Striker",
        "passive_name": "Arachnid Domain",
        "passive_desc": "Increase the assigned Combatant's Attack, Health, and Damage Amount by {ATKHPDMG%}%.\n+{RavagedDMG%}% Damage dealt by the assigned Combatant to targets in a Ravaged state.",
        "values": {
            "ATKHPDMG%": (12, 14, 16, 18, 20),
            "RavagedDMG%": (25, 32, 38, 44, 50),
        },
        "stats": {
            "ATK%": (12, 14, 16, 18, 20),
            "HP%": (12, 14, 16, 18, 20),
        },
        "ego_name": "Arachnid Web",
        "ego_cost": 2,
        "ego_desc": "Deal 250% Damage. Apply Weakness Attack to 1 assigned combatant's random Attack cards in hand.",
    },
    20014: {
        "name": "Serithea",
        "grade": 4.5,
        "class": "Hunter",
        "passive_name": "Ensemble",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe Critical Chance of the combatant's attack cards increases by {CRate%}%.\nWhen the assigned combatant's attack results in a Critical Hit, +{CDmg%}% Critical Damage. Stacks up to 5 times.",
        "values": {
            "ATK%": (12, 14, 16, 18, 20),
            "CRate%": (8, 10, 12, 14, 16),
            "CDmg%": (3, 3.5, 4, 4.5, 5),
        },
        "stats": {"ATK%": (12, 14, 16, 18, 20)},
        "ego_name": "Crimson Romance",
        "ego_cost": 3,
        "ego_desc": "250% Damage. 2 Vulnerable.",
    },
    1058: {
        "name": "Solia",
        "grade": 4.5,
        "class": "Ranger",
        "passive_name": "Spacetime Warp",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK}%.\n+{ExtraDMG%}% Extra Attack damage of the assigned combatant.\nWhen the assigned combatant Draws for the first time each turn using an ability, +{CardDMG%}% Attack Card Damage for 1 turn.",
        "values": {
            "ATK%": (12, 14, 16, 18, 20),
            "ExtraDMG%": (20, 25, 30, 35, 40),
            "CardDMG%": (10, 13, 15, 18, 20),
        },
        "stats": {
            "ATK%": (12, 14, 16, 18, 20),
            "ExtraDMG%": (20, 25, 30, 35, 40),
        },
        "ego_name": "Spacetime Rift",
        "ego_cost": 3,
        "ego_desc": "250% Damage\nMark 1",
    },
    30045: {
        "name": "Asteria",
        "grade": 5,
        "class": "Striker",
        "passive_name": "Starshine-piercing Lighthouse",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe assigned combatant's attack cards with a cost of 2 or more deal +{Cost2DMG%}% damage.\nIncrease Damage Amount of Pulverize cards of the assigned Combatant by {PulverizeDMG%}%.",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "Cost2DMG%": (25, 32, 38, 44, 50),
            "PulverizeDMG%": (10, 13, 15, 18, 20),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Light of Ark",
        "ego_cost": 2,
        "ego_desc": "+40% Damage of the next Attack card used by the assigned Combatant for the total cost of all cards in the hand (Max 10).",
    },
    30054: {
        "name": "Erica",
        "grade": 5,
        "class": "Vanguard",
        "passive_name": "No Speeding!",
        "passive_desc": "Increase the assigned Combatant's Defense by {DEF%}%.\nThe assigned combatant's Counterattack damage increases by {CounterDMG%}%.\nWhen the assigned Combatant uses a Skill or Upgrade Card, there is a {CounterChance%}% chance to gain Counterattack.",
        "values": {
            "DEF%": (16, 18, 20, 22, 24),
            "CounterDMG%": (15, 19, 23, 27, 30),
            "CounterChance%": (50, 63, 75, 88, 100),
        },
        "stats": {"DEF%": (16, 18, 20, 22, 24)},
        "ego_name": "Crackdown Beam Bombardment",
        "ego_cost": 2,
        "ego_desc": "200% Defense-based Damage to all enemies.\n1 Counterattack.\nIf any enemy's Anticipated Action is attack, 1 Counterattack.",
    },
    20030: {
        "name": "Kiara",
        "grade": 5,
        "class": "Hunter",
        "passive_name": "Analyze Weakness",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nIf there are 10 or more cards in the Graveyard, the assigned combatant's attack card damage is increased by {GraveDMG%}%.\nWhen a card is discarded for the first time by the assigned Combatant each turn, +{DiscardDMG%}% Damage Amount to Attack Cards for 1 turn.",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "GraveDMG%": (15, 19, 23, 27, 30),
            "DiscardDMG%": (25, 32, 38, 44, 50),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Lumina Explosion",
        "ego_cost": 3,
        "ego_desc": "200% Damage. +20% Damage by the number of cards in Graveyard.",
    },
    30051: {
        "name": "Marin",
        "grade": 5,
        "class": "Ranger",
        "passive_name": "Raging Wave",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nThe Extra Attack damage of cards generated by the assigned combatant's abilities increases by {ExtraDMG%}%.\nWhen a Skill Card is used for the first time by the assigned Combatant each turn, +{SkillExtra%}% Damage Amount to Extra Attacks for 1 turn.",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "ExtraDMG%": (15, 19, 23, 27, 30),
            "SkillExtra%": (25, 32, 38, 44, 50),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Azure Fury",
        "ego_cost": 3,
        "ego_desc": "200% Damage to all enemies. Draw 1 skill card.",
    },
    30052: {
        "name": "Noel",
        "grade": 5,
        "class": "Controller",
        "passive_name": "Hymn of Blessing",
        "passive_desc": "Increase the assigned Combatant's Defense by {DEF%}%.\nIncrease Damage, Shield Gain, and Heal Amounts of the assigned Combatant's Retain Cards by {RetainBonus%}%.\nAt the end of the turn, deal Fixed Damage to all enemies equal to {FixedDMG%}% for each retained card of the assigned combatant. +5% Damage for enemies with the Instinct attribute.",
        "values": {
            "DEF%": (16, 18, 20, 22, 24),
            "RetainBonus%": (15, 19, 23, 27, 30),
            "FixedDMG%": (15, 19, 23, 27, 30),
        },
        "stats": {"DEF%": (16, 18, 20, 22, 24)},
        "ego_name": "Legato of Faith",
        "ego_cost": 3,
        "ego_desc": "Heal 100%. Activate the Retain effect of all cards held by the assigned combatant.",
    },
    20034: {
        "name": "Scarlet",
        "grade": 5,
        "class": "Striker",
        "passive_name": "The Path to Mastery",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nIf the assigned Combatant's card was used just before, +{ChainDMG%}% Damage Amount to Attack Cards. Can stack up to 2 times and is removed when a different Combatant's card is used.\nGain Focus each time 2 of the assigned Combatant's cards are used.\nFocus: Increase Damage Amount of the assigned Combatant's Attack Cards by {FocusDMG%}%.\nWhen the effect is activated, decrease Focus by 1, and when another Combatant's card is used, remove Focus.",
        "values": {
            "ATK%":      (16, 18, 20, 22, 24),
            "ChainDMG%": (15, 19, 23, 26, 30),  # EST
            "FocusDMG%": (20, 25, 30, 35, 40),
        },
        "stats": {
            "ATK%": (16, 18, 20, 22, 24),
        },
        "ego_name": "Binding Knot",
        "ego_cost": 3,
        "ego_desc": "Deal 250% Damage. +10% assigned Combatant's Attack Card Damage Amount for each owned buff for 1 turn.",
    },
    20039: {
        "name": "Tina",
        "grade": 5,
        "class": "Ranger",
        "passive_name": "Communication Support",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nOrder attribute's Extra Attack damage increase by {OrderExtra%}%.\n+{TargetExtra%}% Extra Attack damage from Targeting Attack Cards.",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "OrderExtra%": (15, 19, 23, 27, 31),
            "TargetExtra%": (25, 32, 38, 44, 50),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Target confirmed, initiating support!",
        "ego_cost": 2,
        "ego_desc": "Draw 1. Increase the combatant's Extra Attack damage by 30% for 1 turn.",
    },
    20009: {
        "name": "Zeta",
        "grade": 5,
        "class": "Vanguard",
        "passive_name": "Deadly Poison",
        "passive_desc": "Increase the assigned Combatant's Defense by {DEF%}%.\nThe Defense-Based Damage of the assigned combatant's Instinct cards is increased by {InstDMG%}%.\nThe assigned Combatant's Defense-Based Damage and Shield Amount for the Celestial card becomes +{CelestialBonus%}%.",
        "values": {
            "DEF%": (16, 18, 20, 22, 24),
            "InstDMG%": (15, 19, 23, 27, 31),
            "CelestialBonus%": (25, 32, 38, 44, 50),
        },
        "stats": {"DEF%": (16, 18, 20, 22, 24)},
        "ego_name": "Undertaking the Mission",
        "ego_cost": 2,
        "ego_desc": "200% Defense-Based Damage. Draws 1 highest-cost card.",
    },
    30044: {
        "name": "Westmacott",
        "grade": 5,
        "class": "Striker",
        "passive_name": "Gleaming Deduction",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nWhen an Attack Card of the assigned Combatant is Drawn through that Combatant's ability, +{DrawnDMG%}% Damage Amount for 1 turn.\nIncreases Damage Amount of the assigned Combatant's cards that have Inspiration by {InspireDMG%}%.",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "DrawnDMG%": (25, 32, 38, 44, 50),
            "InspireDMG%": (10, 13, 15, 18, 20),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Clue Spotted",
        "ego_cost": 3,
        "ego_desc": "Move 1 card from hand to Draw Pile. Draw 2 assigned Combatant cards.",
    },
    30046: {
        "name": "Itsuku",
        "grade": 5,
        "class": "Psionic",
        "passive_name": "Tranquil Marker",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nEvery time the assigned Combatant's cards stack, increases Damage Amount of Attack Cards by {StackDMG%}%. Can stack up to 3 times.\nEvery time 1 Attack Card used by the assigned Combatant deals 3 Hits, inflicts {FixedDMG%}% Fixed Damage to the target.",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "StackDMG%": (5, 7, 8, 9, 10),
            "FixedDMG%": (30, 38, 45, 53, 60),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Moonlit Leisure",
        "ego_cost": 3,
        "ego_desc": "200% Damage to all enemies.\n 1 Fierce Winds.",
    },
    30076: {
        "name": "Peko",
        "grade": 5,
        "class": "Hunter",
        "passive_name": "Peko's Multi-Purpose Kit",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nWhen the assigned Combatant's card Moves from the Graveyard to hand, gain 1 Repairs Complete.\nRepairs Complete: +{RepairsDMG%}% Damage Amount to the assigned Combatant's Attack Cards (Max-3) \nIncrease Damage Amount of the assigned Combatant's Attack Cards that are used against Ravaged targets by {RavagedDMG%}%.",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "RepairsDMG%": (10, 13, 15, 18, 20),
            "RavagedDMG%": (15, 19, 23, 27, 30),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Overclock Beacon",
        "ego_cost": 3,
        "ego_desc": "When an ally inflicts Ravage, 1 Overclock to the assigned Combatant (1 per turn).",
    },
    20002: {
        "name": "Gaya",
        "grade": 5,
        "class": "Controller",
        "passive_name": "Snow Upon the Heart",
        "passive_desc": "Increase the assigned Combatant's Defense by {DEF%}%.\n+{DEFDAM%}% Defense-Based Damage Amount to the assigned Combatant's Instinct cards.\nWhen using a Unique Attack Card of the assigned Combatant with an original Cost of 6, +{DMG%}% to Damage Amount of all allies (max 1).",
        "values": {
            "DEF%": (16, 18, 20, 22, 24),
            "DEFDAM%": (20, 25, 30, 35, 40),
            "DMG%": (20, 25, 30, 35, 40),
        },
        "stats": {"DEF%": (16, 18, 20, 22, 24)},
        "ego_name": "Ice Wyrm's Roar",
        "ego_cost": 3,
        "ego_desc": "60% Defense-Based Damage x 4.\nDraw 1 Attack Card(s).",
    },
    30091: {
        "name": "Alcea",
        "grade": 5,
        "class": "Vanguard",
        "passive_name": "You're Quite High Maintenance",
        "passive_desc": "Increase the assigned Combatant's Defense by {DEF%}%.\nWhen an Exhaust card of the assigned Combatant is Exhausted or activated, increase Defense-Based Damage Amount of the next Attack Card used by {DEFDAM%}% (max 1-stack).\nWhen a 2-Cost or higher card of the assigned Combatant is Exhausted, gain {FixedShield%}% Fixed Shield (1 time per turn).",
        "values": {
            "DEF%": (16, 18, 20, 22, 24),
            "DEFDAM%": (20, 25, 30, 35, 40),
            "FixedShield%": (100, 125, 150, 175, 200),
        },
        "stats": {"DEF%": (16, 18, 20, 22, 24)},
        "ego_name": "If You Require Assistance",
        "ego_cost": 3,
        "ego_desc": "250% Defense-Based Damage.\n5 Caustic Remarks.",
    },
    30085: {
        "name": "Tiana",
        "grade": 5,
        "class": "Controller",
        "passive_name": "Star in the Darkness",
        "passive_desc": "Increase the assigned Combatant's Defense by {DEF%}%.\nWhen the assigned Combatant creates 3 Exhaust cards, increase allies’ next Attack Card Damage Amount by {DMG%}% (max 2 stacks)\nWhen the assigned Combatant has activated Shield gain and Heal through Order Cards, +{CRITRATE%}% Critical Chance of allies for 1 turn. (max 1 stack)",
        "values": {
            "DEF%": (16, 18, 20, 22, 24),
            "DMG%": (15, 19, 23, 27, 30),
            "CRITRATE%": (6, 8, 9, 11, 12),
        },
        "stats": {"DEF%": (16, 18, 20, 22, 24)},
        "ego_name": "Phase Alignment",
        "ego_cost": 3,
        "ego_desc": "Draw 1 Exhaust Card\nDraw 1 Exhaust card the next 2 times Ego Skill is used\nDecrease the Cost of the next Ego Skill used by 1",
    },
    1025: {
        "name": "Ivy",
        "grade": 5,
        "class": "Psionic",
        "passive_name": "All of Me",
        "passive_desc": "Increase the assigned Combatant’s Attack by {ATK%}%.\nWhen a 2-Cost or higher Justice Attribute Attack Card of the assigned Combatant is used, increase Damage Amount of the assigned Combatant’s next Attack Card used by {2COSTDMG%}%.\nIf a 2-, 3-, or 4-Cost Attack Card of the assigned Combatant is used, gain 1 [Imply]. (max 1 time each)\n[Imply]: Increase Damage Amount of the assigned Combatant by {IMPLY%}% (max 3 stacks).",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "2COSTDMG%": (25, 32, 38, 44, 50),
            "IMPLY%": (5, 7, 8, 9, 10),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "A New Visitor",
        "ego_cost": 3,
        "ego_desc": "2 Illusory Erosion\nIncrease Damage Amount taken from 2-Cost or higher Attack Cards of the assigned Combatant by 20%\nAt the end of the turn, Decrease 1 Illusory Erosion",
    },
    30053: {
        "name": "Sophia",
        "grade": 5,
        "class": "Hunter",
        "passive_name": "Milky Way Chorus",
        "passive_desc": "Increase the assigned Combatant’s Attack by {ATK%}%.\nWhen a Passion Quietus card of the assigned Combatant is Discarded, +{CDMG%}% Critical Damage (max 4 stacks).\nWhen 3 Bullet cards are Discarded, {EXTRADMG%}% Extra Attack by the assigned Combatant to a random enemy (2 times per turn)",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "CDMG%": (5, 7, 8, 9, 10),
            "EXTRADMG%": (200, 250, 300, 350, 400),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Always Cheer For You",
        "ego_cost": 3,
        "ego_desc": "3 Die-hard Fan\nDraw 1\nDiscard up to 2 cards\n\nDie-hard Fan\n+40% Damage Amount to Extra Attacks of the assigned Combatant\nAt the end of the turn, decrease Die-hard Fan by 1",
    },
    30094: {
        "name": "Sylvia",
        "grade": 5,
        "class": "Ranger",
        "passive_name": "Auroric Wingbeats",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nEach time the assigned Combatant's Linked cards are used manually or Discarded, gain  1 [Zephyr].\nWhen [Zephyr] reaches 3, +{CDMG%}% Critical Damage to assigned Combatant.\n[Zephyr]: +{ZEPHYRDMG%}% Damage Amount to assigned Combatant's Passion Attack Cards (max 3 stacks)",
        "values": {
            "ATK%": (16, 18, 20, 22, 24),
            "CDMG%": (20, 25, 30, 35, 40),
            "ZEPHYRDMG%": (15, 19, 23, 27, 30),
        },
        "stats": {"ATK%": (16, 18, 20, 22, 24)},
        "ego_name": "Field Overview",
        "ego_cost": 2,
        "ego_desc": "Select up to 2 cards in hand, apply Linked\nIf a selected card is the assigned Combatant's Linked card, +10% Critical Damage to assigned Combatant for each",
    },
    30095: {
        "name": "Clara",
        "grade": 5,
        "class": "Vanguard",
        "passive_name": "Dreamwoven Prism",
        "passive_desc": "Increase the assigned Combatant's Defense by {DEF%}%.\nWhen a card with the Blessing effect applied by the assigned Combatant is used, Fixed Heal {HEAL%}% (5 times per turn).\nWhen the assigned Combatant's Blessing card is used, allies gain 1 Prism.\nPrism: Increase Damage Amount of Attack Cards and Shield Gain Amount of Skill Cards by {PRISMDMG%}% (max 4 stacks)",
        "values": {
            "DEF%": (16, 18, 20, 22, 24),
            "HEAL%": (40, 45, 50, 55, 60),
            "PRISMDMG%": (5, 7, 8, 9, 10),
        },
        "stats": {"DEF%": (16, 18, 20, 22, 24)},
        "ego_name": "Genius Stage Director",
        "ego_cost": 3,
        "ego_desc": "200% Shield\nSelect and Draw 2 Blessing card(s) from Draw Pile",
    },
    -2: {  # TODO: replace key with real res_id when known (Bria)
        "name": "Bria",
        "grade": 5,
        "class": "Psionic",
        "passive_name": "Check the instructions",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nWhen the assigned Combatant creates a card, gain Risk Factor Report.\nRisk Factor Report: Increase Damage Amount of the assigned Combatant's Attack Cards by {RiskReportDMG%}% for 1 turn (max 3 stacks).\nWhen the assigned Combatant creates a Status Ailment card for the first time (includes cards that have been changed from Status Ailment cards), +{StatusDMG%}% Damage Amount to Attack Cards for 1 turn.",
        "values": {
            "ATK%":           (16, 18, 20, 22, 24),
            "RiskReportDMG%": (10, 13, 15, 18, 20),  # EST
            "StatusDMG%":     (25, 31, 38, 44, 50),  # EST
        },
        "stats": {
            "ATK%": (16, 18, 20, 22, 24),
        },
        "ego_name": "Capable Secretary",
        "ego_cost": 3,
        "ego_desc": "Exhaust all Status Ailment Cards (including those that were originally Status Ailment) and Curse Cards from Discard Pile.\nIncrease Damage Amount of the assigned Combatant's Attack Cards by 10% for each card Exhausted for 1 turn.",
    },
    -3: {  # TODO: replace key with real res_id when known (Janet)
        "name": "Janet",
        "grade": 5,
        "class": "Hunter",
        "passive_name": "Understanding and Ideas",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\n+{CritCost1%}% Critical Chance of the assigned combatant's attack cards costing 1 or less.\nWhen the assigned combatant uses 5 Bullet cards, generate a random Handgun Bullet card. Increase Damage Amount of the created card by {HandgunDMG%}%.",
        "values": {
            "ATK%":         (16, 18, 20, 22, 24),
            "CritCost1%":   (9, 11, 13, 16, 18),     # EST
            "HandgunDMG%":  (50, 88, 125, 163, 200), # EST
        },
        "stats": {
            "ATK%": (16, 18, 20, 22, 24),
        },
        "ego_name": "Ultimate Missile Turret!",
        "ego_cost": 3,
        "ego_desc": "150% Damage to all enemies.\nIncrease Damage Amount of Designated Combatant's Bullets by 20% for 1 turn.",
    },
    -4: {  # TODO: replace key with real res_id when known (Marianne)
        "name": "Marianne",
        "grade": 5,
        "class": "Striker",
        "passive_name": "Eyes on the Target",
        "passive_desc": "Increase the assigned Combatant's Attack by {ATK%}%.\nIncrease Damage Amount of the assigned Combatant when attacking Ravaged enemies by {RavagedDMG%}%.\nThe assigned combatant's Basic Cards always apply as Weak Point Damage, and +{WeakDMG%}% Weakness Damage.",
        "values": {
            "ATK%":       (16, 18, 20, 22, 24),
            "RavagedDMG%": (15, 19, 23, 26, 30),  # EST
            "WeakDMG%":   (5, 10, 15, 20, 25),
        },
        "stats": {
            "ATK%": (16, 18, 20, 22, 24),
        },
        "ego_name": "Blood Stalker",
        "ego_cost": 3,
        "ego_desc": "Deal 350% Damage.",
    },
}

# Base stats by grade and class at level 60
# Offensive classes (Hunter, Psionic, Ranger, Striker): High ATK, low DEF
# Defensive classes (Controller, Vanguard): Low ATK, high DEF
PARTNER_CLASS_STATS = {
    # 3-star classes
    (3, "Hunter"):     {"atk": 89, "def": 5, "hp": 85},
    (3, "Psionic"):    {"atk": 89, "def": 5, "hp": 85},
    (3, "Ranger"):     {"atk": 89, "def": 5, "hp": 85},
    (3, "Striker"):    {"atk": 89, "def": 5, "hp": 85},
    (3, "Controller"): {"atk": 5, "def": 36, "hp": 85},
    (3, "Vanguard"):   {"atk": 5, "def": 36, "hp": 85},
    # 4-star classes
    (4, "Hunter"):     {"atk": 101, "def": 5, "hp": 95},
    (4, "Psionic"):    {"atk": 101, "def": 5, "hp": 95},
    (4, "Ranger"):     {"atk": 101, "def": 5, "hp": 95},
    (4, "Striker"):    {"atk": 101, "def": 5, "hp": 95},
    (4, "Controller"): {"atk": 5, "def": 40, "hp": 95},
    (4, "Vanguard"):   {"atk": 5, "def": 40, "hp": 95},
    # 5-star Arkhianon Supply classes (Seasonal Pass)
    (4.5, "Hunter"):     {"atk": 113, "def": 5, "hp": 105},
    (4.5, "Psionic"):    {"atk": 113, "def": 5, "hp": 105},
    (4.5, "Ranger"):     {"atk": 113, "def": 5, "hp": 105},
    (4.5, "Striker"):    {"atk": 113, "def": 5, "hp": 105},
    (4.5, "Controller"): {"atk": 5, "def": 44, "hp": 105},
    (4.5, "Vanguard"):   {"atk": 5, "def": 44, "hp": 105},
    # 5-star classes
    (5, "Hunter"):     {"atk": 155, "def": 5, "hp": 144},
    (5, "Psionic"):    {"atk": 155, "def": 5, "hp": 144},
    (5, "Ranger"):     {"atk": 155, "def": 5, "hp": 144},
    (5, "Striker"):    {"atk": 155, "def": 5, "hp": 144},
    (5, "Controller"): {"atk": 5, "def": 61, "hp": 144},
    (5, "Vanguard"):   {"atk": 5, "def": 61, "hp": 144},
}


def get_partner(res_id: int) -> dict:
    """Get partner data by res_id, returning DEFAULT_PARTNER if not found."""
    return PARTNERS.get(res_id, DEFAULT_PARTNER)


def get_value_for_ego_level(values_tuple: tuple, limit_break: int) -> float:
    """Get the value from a 5-element tuple based on limit_break (0-4)."""
    if not values_tuple or len(values_tuple) < 5:
        return 0
    index = max(0, min(4, limit_break))  # Clamp to 0-4
    return values_tuple[index]


def get_partner_base_stats(res_id: int) -> dict:
    """Get base stats for a partner card based on its grade and class."""
    partner = get_partner(res_id)
    grade = partner.get("grade", 3)
    partner_class = partner.get("class", "Controller")
    base = PARTNER_CLASS_STATS.get((grade, partner_class), {"atk": 85, "def": 5, "hp": 90})
    return base


def get_partner_stats(res_id: int, level: int) -> dict:
    """Return effective ATK / DEF / HP for a partner at the given level.

    Scales LINEARLY from 0 at level 0 to base at level 60:
        scaled = floor(base * (level / 60))

    Linear is an approximation -- the game may use a slightly different
    curve internally -- but the discrepancy is well within the rounding
    error that matters for build comparison, especially at endgame
    levels (50+). For the optimizer's purposes, this is correct.

    Note: a level > 60 partner will return MORE than base stats here
    (scale > 1.0). PARTNER_EXP_TABLE caps at level 60, so in practice
    this shouldn't happen, but callers that pass arbitrary levels
    should clamp upstream if they need to be safe.
    """
    base = get_partner_base_stats(res_id)
    scale = level / 60.0
    return {
        "atk": int(base["atk"] * scale),
        "def": int(base["def"] * scale),
        "hp": int(base["hp"] * scale),
    }


def get_partner_passive_stats(res_id: int, limit_break: int) -> dict:
    """Get unconditional passive stat bonuses for a partner card.
    Returns stat bonuses based on limit_break (0=E0 through 4=E4)."""
    partner = get_partner(res_id)
    stats = {}
    for stat_name, values_tuple in partner.get("stats", {}).items():
        stats[stat_name] = get_value_for_ego_level(values_tuple, limit_break)
    return stats


def format_passive_description(res_id: int, limit_break: int) -> str:
    """Format the passive description with values based on limit_break."""
    partner = get_partner(res_id)

    desc = partner.get("passive_desc", "Unknown passive effect.")
    values = partner.get("values", {})

    # Replace each placeholder with the value for this ego level
    for placeholder, values_tuple in values.items():
        current_val = get_value_for_ego_level(values_tuple, limit_break)
        # Format as integer if whole number, otherwise one decimal
        if current_val == int(current_val):
            val_str = str(int(current_val))
        else:
            val_str = f"{current_val:.1f}"
        desc = desc.replace("{" + placeholder + "}", val_str)

    return desc


def get_partner_passive_info(res_id: int, limit_break: int) -> dict:
    """Get full passive information for display.
    Returns dict with passive_name, formatted description, ego_name, ego_cost, ego_desc."""
    partner = get_partner(res_id)

    return {
        "passive_name": partner.get("passive_name", "Unknown"),
        "passive_desc": format_passive_description(res_id, limit_break),
        "ego_name": partner.get("ego_name", "Unknown"),
        "ego_cost": partner.get("ego_cost", 0),
        "ego_desc": partner.get("ego_desc", "Unknown effect."),
    }
