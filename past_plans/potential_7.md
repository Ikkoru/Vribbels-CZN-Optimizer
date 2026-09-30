# Potential 7 in the program's stats and scoring — [IMPLEMENTED] 2026-09-30

Node 7 per combatant is `Vribbels/game_data/potential_7.py`, and the rules it follows are `docs/game_formulas.md` §1, *Potential 7*. Kept for what the wire showed, the decisions the maintainer made and why, and where the build departed from the design.

Sources: the e7bot wiki, prydwen and game8, collected side by side into `_tmp/potential7_sources.tsv` (gitignored), and the server's own sheets. **e7bot's text is the data** wherever the sources disagree; the maintainer checked every number against the game.

## What the game does

- **One node, one level.** Node 7 is wire node 70 in `potential_node_ids`, level 1 once unlocked. Every level-60 combatant captured by 2026-09-29 had it.
- **An effect is a base part and a conditional part.** Either may be absent: "+X", "if STAT is T or higher, +X", "+Y for every S of STAT above T, up to +Z more". Khalipe and Owen stack two conditions. Every threshold is "or higher".
- **The check reads the stat's Potential 7 value**, the one the Have-at-least gate already models (`game_formulas.md` §8): inner ATK/DEF/HP; CRate and CDMG without partner passives and conditional sets; Extra, DoT and Ego without partner passives. The wire sends it per combatant as `potential_base_status`.
- **A sheet-stat bonus is on the sheet once its check passes**, verified against the server before the implementation:
  - Owen's +4% ATK and DEF land in the inner %; his +4% more at 700 HP is absent at 366 HP;
  - Diana's +12% Extra DMG% is 4 + her capped 8 at 55.5% CRate;
  - Heidemarie, Arabella, Fei and Adelheid carry +15 attribute damage (5 + the capped 10) in `S_<COLOUR>_DMG_RATE`, where RED is Passion, BLUE Justice, ORANGE Instinct and PURPLE Void;
  - Olga and Hilde carry 7 + 8.
- **A Sortie grants every Potential 7 in full**, met or not: Olga, Hilde and Magna show their maximum there with check values of 0 DoT, 0 Extra and 246 DEF.
- **"Allies" includes the combatant** (the maintainer): Orlea's +6% CRate and Tiphera's +10% CDmg are their own stats as well as the team's.
- **Weakness** (the maintainer): an attack on an enemy of the same Element deals ×1.25, which is `S_WEAK_EGO_DMG_RATE` (125 on every sheet). Mei Lin's Weakness Damage raises it, probably additively.
- **A check value can carry more stats than the check reads**: Olga's names ATK beside the DoT her check reads, and Sereniel's ATK only in the season-4 Chaos. The check stat comes from the data, never from the keys present.
- **A node 7 can come with a card**: Amir's `potential_cs` reads `{"1017_7_0_1": ["cs00_0231"]}`, likely the Metallization her bonus names. Metallization is her unique passive effect; her Potential 7 involves cards only through Metallization being granted by them.
- **Rita's out-of-battle screen** (ATK 700 (+263), DEF 187 (+36), HP 539 (+50), CRate 13.0% (+22.8%), CDMG 137.0% (+93.7%), Extra 13.0%) could not say whether her +10% ATK at 800 is on the sheet: the white figure is the base, and the check value lies somewhere between it and the total. A plain-battle capture settled it (below).

## What the captures of 2026-09-29 settled

Tower floors 31-60, every sheet held by `formula_gaps` with node 70 taken:

- **Growth is continuous, not stepped**: Magna 9.8 at 324 DEF, Rin +6.275 CRate at 651 ATK, Diana +7.7 Extra at 28.5% CRate, Fei 8.1 and Heidemarie 8.3 at 631 and 633 ATK.
- **The check reads the value before the bonus**: Rita +10% ATK at 902, none at 755, where the bonus would have carried her past 800. Rin nothing at 589.
- **A start-of-battle bonus is not on the sheet**: Orlea (ATK 713, DEF 323) and Tiphera (DEF 467), in one team, carry neither +6% CRate nor +10% CDmg.
- **GREEN is Order**: Nine +15 in `S_GREEN_DMG_RATE`.
- Selena +8 at 37.9% Extra; Tressa +4 only, at 0 DoT.
- Along the way: Tressa's and Yuki's base stats were wrong, and Tiphera's node 6 is DEF%, not CDmg.

## The combatants, by where the bonus lands

| Kind                                  | Who (check stat)                                                                                                   | How the score takes it                                                                            |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| **Attribute damage**                  | Adelheid, Magna, Nine (DEF); Arabella, Fei, Heidemarie, Tenebria (ATK); Olga, Tressa (DoT); Hilde, Selena (Extra)  | into the element multiplier, `× (1 + Element DMG%)` (§7), beside the fragments' element main stat |
| **CRate / CDMG / Extra DMG%**         | Rin CRate (ATK), Kayron CDMG (ATK), Diana Extra (CRate), Hugo Extra (ATK); Orlea CRate (ATK or DEF), Tiphera CDMG (DEF) | added like a fragment's, into the final stat                                                      |
| **ATK% / DEF%**                       | Owen (HP), Rita (ATK)                                                                                              | into the inner %                                                                                  |
| **One card's damage, shield or heal** | Amir, Beryl, Chizuru, Haru, Khalipe, Lucas, Luke, Maribell, Mika, Narja, Nia, Renoa, Rei, Sereniel, Veronica, Yuki | not priced (decision 2)                                                                           |
| **Battle events**                     | Cassius (HP)                                                                                                       | not priced                                                                                        |
| **Weakness damage**                   | Mei Lin (ATK)                                                                                                      | not priced: the score has no weakness term                                                        |

## Decisions

1. **e7bot is right in all.** Where the other two disagreed: Haru's threshold is 600 ATK (not 1000), Chizuru's step 1% per 10 ATK (not per 40), Yuki's per 20 ATK (not per 80), Tenebria's +1% per 20 ATK (not +2%), Maribell's bonus goes to Basic and Signature cards, Orlea's CRate to allies, Rita's has no timing, and every threshold is "or higher" (not "greater than").
2. **Card bonuses are ignored**, for the reason Equipment is a standard: which deck a player takes into their next battle cannot be known. Two alternatives were offered and not taken: pricing them through a per-combatant share of the combatant's damage those cards deal, or offering only the threshold.
3. **The optimizer prices every bonus it can, conditions included**, so it decides for itself whether meeting a threshold is worth the stats. Have-at-least minimums stay manual. A button fills them with a combatant's thresholds, raising and never lowering one: for a growing effect, where the growth stops; for Orlea's ATK-or-DEF check, DEF 300 (the maintainer's pick, the effect's `fill`).
4. **Mei Lin's Weakness Damage** is left out with the rest of weakness.
5. **The preset-weight reference builds include Potential 7**, like nodes 5 and 6. Rewriting the shipped weights moved nine presets through node 7, and Tressa's and Yuki's through their corrected bases.

## As built, against the design

- **The data is a table of its own**, `POTENTIAL_7` in `game_data/potential_7.py`, rather than a key in each `CHARACTERS` entry, like `POTENTIAL_NODE_OVERRIDES`. The launch-time validator checks it: every combatant has an entry, every grant and check stat is known, growth is whole.
- **The evaluation reads the check by position.** `core.potential_7_effects` flattens each combatant's priced effects once per run, and `potential_7_bonus` rounds only the values an effect reads: the first version, building and rounding all eight per build, cost 20% of `compute_build_stats`, this one 9%.
- **The Combatants tab names what node 7 raises** (`Void%`, `Team Crit%`, `Card`) rather than showing a check value against its threshold: the character card's lines are fixed-width, and the value depends on the equipped build.
- **The contributions popup folds the bonus into `Pot` and `Other`** and adds a `Potential 7:` line saying how much, with the Pot7 rows taking it out again, instead of a row of its own per stat.
- **`formula_gaps` holds every plain sheet to the program's node 7**, attribute damage added to what it compares; start-of-battle effects are left out of the sheet side only.
