"""Cards whose play differs from what their data says, kept by the
maintainer (plan D45, D50).

{card id: what to count instead, and why}. An entry holds for the
card's Potential and Ego Manifestation upgrades too. The keys a card
can carry:

    "ignore"   it adds nothing to any sum and needs no draw
    "hidden"   left out of the sums by default; a deck can show it
    "cost"     the AP it costs in practice
    "cycles"   it returns to the deck after a shuffle, though its
               keywords say it leaves after use
    "why"      the reason, shown beside the card

A user can still set any card's figures and list per deck.
"""

EXCEPTIONS = {
    # Homing Arrow (Hilde): it draws a card when drawn and uses no AP.
    "c_30113_cre1": {"ignore": True, "why": "draws a card when drawn, and uses no AP"},
    "c_30113_cre2": {"ignore": True, "why": "draws a card when drawn, and uses no AP"},
    "c_30113_cre3": {"ignore": True, "why": "draws a card when drawn, and uses no AP"},
    # Hew (Flash) (Nine): Ignition brings it to 0 in practice.
    "c_30047_srt4_rsp3_mut": {"cost": 0, "why": "costs 0 in practice (Ignition)"},
    "c_30047_srt4_rsp3_mut2": {"cost": 0, "why": "costs 0 in practice (Ignition)"},
    "c_30047_srt4_rsp3_mut3": {"cost": 0, "why": "costs 0 in practice (Ignition)"},
    # Dirge Bullet (Renoa): used by discarding it, which does not Exhaust
    # it, so it cycles back through the deck. Hearsay, to be confirmed.
    "c_1041_cre1": {"cost": 0, "cycles": True,
                    "why": "used by discarding it, so it cycles back (to be confirmed)"},
    # Homing Laser L (Sereniel): both uses happen before a shuffle, in the
    # maintainer's play.
    "c_30075_srt4_mut": {"hidden": True,
                         "why": "both uses usually happen before a shuffle"},
    # Mealtime (Narja): 6 AP, 1 less each time Voracity drops, and played
    # for 0 as a rule. Its Ego Manifestation version takes this too.
    "c_1052_uni4": {"cost": 0, "why": "played for 0 as a rule: Voracity drops cut its 6"},
}
