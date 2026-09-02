# Chaos Zero Nightmare — Game Formula Reference

Canonical reference for the in-game formulas the optimizer scores with. Whenever code refers to "the damage formula" or "the shield/heal formula", it means the formulas here.

**If in-game math is observed to disagree with this file, FIX THIS FILE FIRST**, then propagate into `optimizer.py` / `memory_fragment.py` / `characters.py`.

## 1. Final stat layered formulas

In `optimizer.calculate_build_stats`.

```
Final ATK = ((Base_ATK + Partner_ATK)
             × (1 + Fragment_ATK% + Potential_ATK%)
             + Fragment_FLAT_ATK + Affinity_FLAT_ATK)
            × (1 + Partner_ATK% + Equipment_ATK%)
            + Equipment_FLAT_ATK

Final DEF = ((Base_DEF + Partner_DEF)
             × (1 + Fragment_DEF% + Potential_DEF%)
             + Fragment_FLAT_DEF + Affinity_FLAT_DEF)
            × (1 + Partner_DEF% + Equipment_DEF%)
            + Equipment_FLAT_DEF

Final HP  = ((Base_HP + Partner_HP)
             × (1 + Fragment_HP% + Potential_HP%)
             + Fragment_FLAT_HP + Affinity_FLAT_HP)
            × (1 + Partner_HP% + Equipment_HP%)
            + Equipment_FLAT_HP

Final_CRate = Base_CRate + Sum(CRate_contributions)  # base default = 3
Final_CDmg  = Base_CDmg + Sum(CDmg_contributions)    # base default = 125
```

| Source              | Contributes                                                                        |
| ------------------- | ---------------------------------------------------------------------------------- |
| **Base**            | Character's base stat at the chosen level (`CHARACTERS[res_id]`)                    |
| **Partner_X**       | Partner card's class/rarity flat stat at the partner's level                        |
| **Partner_X%**      | Partner card's passive % bonus (by limit break level)                               |
| **Fragment_X%**     | Sum of substat + main-stat % across all 6 equipped fragments                        |
| **Fragment_FLAT_X** | Sum of substat + main-stat flat across all 6 equipped fragments                     |
| **Potential_X%**    | Nodes 50 / 60 — the `node_50`/`node_60` fields in characters.py                     |
| **Affinity_FLAT_X** | Affinity reward bonuses (`FRIENDSHIP_BONUSES`)                                      |
| **Equipment_X**     | Constant; separate gear system not captured (`EQUIPMENT_*` in `optimizer.py`)       |
| **Set bonuses**     | See §5 — three different landing places depending on `type` and `stat`              |

### The potential tree

Ten nodes; the program stores levels for **two**, because only two feed the stat formulas. A snapshot carries all ten, and **the numbering on the wire does not match the numbering in the game.**

| In game  | On the wire | Max level | What it does                                                  | Reaches Final stats? |
| -------- | ----------- | --------- | ------------------------------------------------------------- | -------------------- |
| Node 1   | `10`        | 1         | A random Rare Signature Card on entering Chaos                | no                   |
| Node 2   | `20`        | 10        | Basic Card base effect, +2%/level                             | no                   |
| Node 3   | `30`        | 10        | Neutral Card base effect, +2%/level                           | no                   |
| Node 3.1 | `31`        | 1         | Improves some Basic Cards, uniquely per character             | no                   |
| Node 4   | `40`        | 10        | Signature Card base effect, +2%/level                         | no                   |
| Node 5   | `50`        | 5         | One stat, per `POTENTIAL_STAT_VALUES`                         | **yes**              |
| Node 5.1 | `51`        | 1         | Improves some Basic Cards (Tiphera: her Archetype cards)      | no                   |
| Node 5.2 | `52`        | 1         | +25% chance of a Divine Epiphany appearing                    | no                   |
| Node 6   | `60`        | 5         | One stat, per `POTENTIAL_STAT_VALUES`                         | **yes**              |
| Node 7   | `70`        | 1         | A conditional stat bonus, gated on a per-character stat check | only when modelled   |

Max levels total **45**, which is what a "node levels out of max" display counts against.

`characters.py` stores `node_50` and `node_60` only. `game_data.parse_potential_node_ids` returns every node it finds and `CharacterInfo` keeps `potential_50_level` / `potential_60_level`; the other eight are parsed and dropped. **Deliberate, not an oversight** — the card-effect nodes change card magnitudes, which the build score does not model.

- **Node 4 is not a stat node**, despite sitting between two that are. Its levels run to 10 while `POTENTIAL_STAT_VALUES` holds five tiers and `get_potential_stat_bonus` rejects `level > 5`, so treating it as one silently returns zero.
- **Node 7 is the only other node that can move a stat.** Its bonus and unlock condition are unique per character and not yet in `characters.py`.

Per-level magnitudes are `POTENTIAL_STAT_VALUES`: 1.6/level for ATK%/DEF%/HP%, 2.0 for CRate, 2.4 for CDmg.

## 2. Main stat magnitudes (max-level Legendary)

The optimizer reads `fragment.main_stat.value` from captured data, so this table is for documentation and UI forcing constraints. Stored as `MAIN_STAT_VALUES` in `game_data/constants.py`.

| Main stat     | Max value | Slot 1 | Slot 2 | Slot 3 | Slot 4 | Slot 5 | Slot 6 |
| ------------- | ---------:|:------:|:------:|:------:|:------:|:------:|:------:|
| Flat ATK      | 22        | ✓      |        |        |        |        |        |
| Flat DEF      | 22        |        | ✓      |        |        |        |        |
| Flat HP       | 37        |        |        | ✓      |        |        |        |
| ATK%          | 25        |        |        |        | ✓      | ✓      | ✓      |
| HP%           | 25        |        |        |        | ✓      | ✓      | ✓      |
| CRate         | 27        |        |        |        | ✓      |        |        |
| CDmg          | 40.8      |        |        |        | ✓      |        |        |
| Passion DMG%  | 16        |        |        |        |        | ✓      |        |
| Order DMG%    | 16        |        |        |        |        | ✓      |        |
| Justice DMG%  | 16        |        |        |        |        | ✓      |        |
| Void DMG%     | 16        |        |        |        |        | ✓      |        |
| Instinct DMG% | 16        |        |        |        |        | ✓      |        |
| DEF%          | 25        |        |        |        |        |        | ✓      |
| Ego           | 40        |        |        |        |        |        | ✓      |

### Rarity, levels and substats

Memory Fragments come in three of the game's five rarity tiers — Mythic and Normal exist but not for MFs.

| Rarity    | Colour | Program tier | Substats at level 0 | Max level |
| --------- | ------ | -----------: | ------------------: | --------: |
| Legendary | Gold   | 4            | 3                   | 5         |
| Rare      | Blue   | 3            | 2                   | 4         |
| Uncommon  | Green  | 2            | 1                   | 3         |

**A level-up ADDS a new substat while the fragment has fewer than four**; once it has four, each further level-up rolls into an existing one. Every rarity therefore lands on exactly 4 substats at max level. There is **no per-substat cap** — one substat can absorb every remaining roll.

Visible in captured data: a piece's `stat_list` holds `1 + starting_substats + level` entries.

## 3. Damage formulas

A character is ATK-scaling or DEF-scaling. The **ATK/DEF Split** slider exists for hybrid kits where part of the damage uses each.

### 3.1 ATK scaling

```
Final ATK Damage =
    Final_Card_Multiplier
    × Final_ATK
    × 0.35
    × (1 + Element_DMG%)
    × (1 + Mechanic_DMG%)
    × Enemy_Defense_Multiplier
    × (1 + Crit_DMG_bonus)   [only on crit hits]
```

### 3.2 DEF scaling

```
Final DEF Damage =
    Final_Card_Multiplier
    × ((Final_ATK × 0.3) + (Final_DEF × 2.1))
    × 0.35
    × (1 + Element_DMG%)
    × (1 + Mechanic_DMG%)
    × Enemy_Defense_Multiplier
    × (1 + Crit_DMG_bonus)   [only on crit hits]
```

- `Mechanic_DMG%` is **Extra DMG%** for Extra DMG and **DoT%** for every damage-over-time type. Extra DMG and all DoT types always use the ATK-scaling formula regardless of the character's split. The DoT types do NOT share the rest of the formula — see §3.4.
- `Crit_DMG_bonus = (Final_CDmg - 100) / 100`, so CDmg=125 is a 1.25 crit multiplier. Max CRate is 100%.
- `Enemy_Defense_Multiplier`, `0.35` and similar are the same for every build → safe to drop from optimizer comparison.

### 3.3 Final Card Multiplier (damage)

```
Final_Card_Multiplier_DMG =
    ((Base_Multiplier + Base_Additive_Potential) × (1 + Multiplicative_Potential))
    × (1 + Multiplicative_Buffs)
    + Additive_Buffs)
    × (1 + Element_Advantage_Multiplier)
    × (1 + Vulnerable_Multiplier)
    × (1 - Enemy_Damage_Reductions)
    × (1 - Weakness_Multiplier)
```

- `Base_Multiplier` ≈ the user's **Average Card DMG%** setting (100% = the card does normal damage).
- `Base_Additive_Potential`, `Multiplicative_Potential` — character potential/talent values not tied to gear; **treated as 0**, the user is expected to fold them into Average Card DMG%.
- `Multiplicative_Buffs` — **Average Multiplicative Buff%** plus conditional-set `DMG multi`, each weighted by its own set's share.
- `Additive_Buffs` — **Average Additive Buff%** plus conditional-set `DMG add`, likewise weighted.
- The terms after `+ Additive_Buffs` (Element Advantage, Vulnerable, Enemy Damage Reductions, Weakness) are constant across builds → safe to drop.

**Convention:** "Multiplicative Buffs" is the raw bonus fraction (0.2 for +20%), so the multiplier uses `× (1 + Multiplicative Buffs)`. Buffs do NOT apply to shields/heals at all — see §4.2.

### 3.4 Damage-over-time types

Three, and they do NOT share a formula. All scale off ATK and are improved by DoT% and Element DMG%; they differ on crit and buffs.

|                          | Agony  | Fracture     | Scorched     |
| ------------------------ | ------ | ------------ | ------------ |
| Scales off               | ATK    | ATK          | ATK          |
| Improved by DoT%         | yes    | yes          | yes          |
| Improved by Element DMG% | yes    | yes          | yes          |
| Can crit                 | **no** | yes          | yes          |
| Affected by buffs        | **no** | general only | general only |

Agony is what the settings key `dot_pct` names. Fracture and Scorched are mechanically identical, so the optimizer gives them ONE share between them; the slider is labelled `Fracture` and its caption names both.

"Buffs" here means everything in the damage card multiplier beyond `Base_Multiplier`. Agony takes none of them, so a conditional set dialled up for its `DMG multi` does not lift the Agony portion of a build's score — the one build-dependent consequence, and why it changes ranking rather than just scale.

**Agony keeps `Base_Multiplier`.** Only the buff terms are removed. Scaling Agony by anything further — the reference build's crit and card multiplier, say — inflates it against the other types by exactly that factor.

**Where the shares come from, and why it matters.** The Important Settings shares are read off the combatant's **DECK**, not off damage numbers: add up the DMG% of each source over a turn — cards, Extra Attacks, DoT procs — and take each type's fraction. Only a deck change moves them, where a reading taken from damage numbers moves on every gear change.

That makes each share a fraction of **base coefficients**, before ATK, crit, buffs and the mechanic multipliers. So each type's term must carry its own full multiplier stack, `(1 + DoT%)` and `(1 + Extra%)` included — not double-counted, because the share never contained them. A combatant declaring 50% Agony is saying half their raw coefficient output is Agony, **not** half their damage.

**The program does not distinguish general buffs from card-only buffs.** In game, Fracture and Scorched take general buffs but not card-only ones. The Average Buff% settings are read as GENERAL throughout, which overstates the Fracture share for a combatant whose buffs are card-only. Splitting the two is parked in `tasks.md` TBD.

## 4. Shield and Heal formulas

### 4.1 Final shield/heal value

```
Shield_Heal =
    (Base_DEF + (Shield_Heal_DEF - Base_DEF) × 0.5)
    × 0.3
    × Final_Card_Multiplier_Shield_Heal
```

Equivalently `(Base_DEF + Shield_Heal_DEF) / 2 × 0.3 × card_mult`.

`Shield_Heal_DEF` is Final DEF with **Partner's flat DEF pulled out of the inner multiplier** — that is the only difference. Potential DEF% is still included.

```
Shield_Heal_DEF_inner =
    Base_DEF × (1 + Fragment_DEF% + Potential_DEF%)
    + Partner_FLAT_DEF          ← additive, NOT inside the multiplier
    + Fragment_FLAT_DEF
    + Affinity_FLAT_DEF

Shield_Heal_DEF = Shield_Heal_DEF_inner
             × (1 + Partner_DEF% + Equipment_DEF%)
             + Equipment_FLAT_DEF
```

### 4.2 Final Card Multiplier (shield/heal)

```
Final_Card_Multiplier_Shield_Heal =
    ((Base_Multiplier + Base_Additive_Potential) × (1 + Multiplicative_Potential))
    × (1 - Impair_Penalty)
```

**Multiplicative_Buffs and Additive_Buffs do NOT apply to shields or heals** (verified in game) — the key difference from the damage card multiplier. `Impair_Penalty` applies only to shielding and depends on enemy state; **treated as 0**.

**Optimizer note:** with buffs excluded, no remaining term depends on gear, so the whole shield/heal card multiplier is constant across builds and the optimizer drops it — the score's shield/heal term is the §4.1 stat expression with no card multiplier attached.

## 5. Set effects in optimizer math

`sets.py` marks each set with `type` and a numeric `value`.

| `type`          | Where the value lands                                                                                                                                                                                        |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `unconditional` | Adds into Final ATK/DEF/HP/CRate/CDmg via the Fragment buckets — exactly like a sub/main stat. Always applies, no share gating.                                                                               |
| `conditional`   | Gated by that set's **effect-share spinbox** in Set Configuration (0–100 per character: what percent of this combatant's damage the effect affects). At 0 (the default) it contributes nothing, but the set still counts for set-locking. |

Within `conditional`, the `stat` field decides where the value goes:

| Set `stat`  | Where it lands                                                                                        |
| ----------- | ----------------------------------------------------------------------------------------------------- |
| `DMG multi` | `Multiplicative_Buffs` in the **damage** card multiplier (× share). NOT the shield/heal multiplier.    |
| `DMG add`   | `Additive_Buffs` in the **damage** card multiplier (× share). NOT the shield/heal multiplier.          |
| `Crit DMG`  | Final_CDmg (× share)                                                                                  |
| `Crit Rate` | Final_CRate (× share, capped so total CRate ≤ 100%)                                                   |

Why DMG multi / DMG add are damage-only: Seth's Scarab would technically buff Basic Shield and Heal cards too, but those aren't used in practice, so the only observable effect is on damage.

Each conditional set's share is the spinbox beside its checkbox, persisted per character (`set_effect_pcts` in optimizer_settings.json; absent id = 0). The Set Configuration checkboxes control which sets are considered at all.

### Set stat name → program name mapping

`sets.py` spells some stats differently from the rest of the program. Mapping is `SET_STAT_NAME_MAP` in `optimizer/core.py`.

| sets.py `stat` | Internal name                         |
| -------------- | ------------------------------------- |
| `ATK%`         | `ATK%`                                |
| `DEF%`         | `DEF%`                                |
| `HP%`          | `HP%`                                 |
| `Crit DMG`     | `CDmg`                                |
| `Crit Rate`    | `CRate`                               |
| `DMG multi`    | (internal accumulator — sets.py only) |
| `DMG add`      | (internal accumulator — sets.py only) |

## 6. Endgame stat benchmarks

"High but not max", for sanity-checking optimizer output.

| Stat        | ATK-based | DEF-based | Support |
| ----------- | --------- | --------- | ------- |
| Final ATK   | 1020      | 530       | –       |
| Final DEF   | 200       | 450       | –       |
| Final HP    | 600       | 600       | –       |
| Final CRate | 60%       | 60%       | –       |
| Final CDmg  | 210%      | 210%      | –       |
| Final Ego   | 5         | 5         | 60      |

## 7. Element handling

Element DMG% applies as `× (1 + Element_DMG%)` in both damage formulas. The element is `CHARACTERS[res_id]["attribute"]` — Passion / Order / Justice / Void / Instinct.

For `attribute == "Unknown"` the optimizer shows an **Element override dropdown** in Important Settings; the pick is treated as that character's attribute. Once the character is added to `CHARACTERS` with a real attribute the override is silently ignored.

The optimizer treats **all of a character's damage as their element** — there is no per-card element split.

## 8. Optimizer scoring

```
damage_score = (
    normal_share   × atk_formula_damage   ← (1 - extra_share - agony_share - fracture_share)
                   × (1 - def_split_share) ← × (1 - atk_def_split / 100)
  + normal_share   × def_formula_damage   ← × (atk_def_split / 100)
  + extra_share    × atk_formula_damage × (1 + extra_dmg_pct/100)
  + fracture_share × atk_formula_damage × (1 + dot_dmg_pct/100)
  + agony_share    × agony_formula      × (1 + dot_dmg_pct/100)
)

# Both formulas share many constants. With constants dropped:
atk_formula = card_mult × Final_ATK × (1 + element_dmg_pct/100) × crit_modifier
def_formula = card_mult × (Final_ATK × 0.3 + Final_DEF × 2.1) × (1 + element_dmg_pct/100) × crit_modifier

# Agony neither crits nor takes buffs, so it drops crit_modifier and
# uses base_multiplier where the others use the full card multiplier.
agony_formula = base_multiplier × Final_ATK × (1 + element_dmg_pct/100)

crit_modifier = 1 + min(1.0, Final_CRate/100) × max(0, (Final_CDmg - 100)/100)

shield_heal_score = (Base_DEF + (Shield_Heal_DEF - Base_DEF) × 0.5) × 0.3 × card_mult_shield_heal

heal_share = shielding_healing_weight / 100   ← from "How much value..." slider
```

### Score blend (percent-normalized)

The damage and shield/heal terms are not commensurable, so the score blends each as a fraction of a reference rather than adding raw magnitudes:

```
D = damage_score / buff_baseline     ← normalized damage term
S = shield_heal_score                ← shield/heal term (no card mult)

buff_baseline = base_multiplier × (1 + avg_mult_buff) + avg_add_buff

score = (1 - heal_share) × (D / D_ref) + heal_share × (S / S_ref)
```

`buff_baseline` divides out the user's external-buff assumptions so D reflects build quality. It is a per-run constant, so it never changes ranking.

**Two reference regimes, by design:**

- **Enumeration / trimming** uses GREEDY references: `D_ref`/`S_ref` read off a single greedy build (the top candidate in each slot). Being a per-run constant divisor pair, the in-flight top-K trim and the deterministic tie-break stay valid and the parallel path stays byte-identical to sequential. These refs only decide which builds survive trimming, never the displayed number.
- **Display** uses RUN-MAX references: after enumeration, `D_ref`/`S_ref` are the true max D and max S across survivors. Every survivor is re-blended, re-sorted, then the column is rescaled (÷ top, × 100) so **the top row reads 100** at any slider position (order-preserving). The trim's 10× headroom makes it effectively impossible for a build the run-max blend would rank in the display top-K to have been trimmed.

Implementation: `core.compute_score_components` (D, S), `core.trim_blend` (greedy-ref), `core.build_greedy_refs`, `core.display_blend` plus the post-merge rescale in `optimizer.optimize`. `core.compute_score` keeps a legacy scalar `(1-h)·D + h·S` for callers outside the optimizer; `optimizer.reblend_results_for_display` re-applies the display blend when a cached results list is re-mapped after an equip/upgrade.

### Hard constraint: "Have at least this much"

Eight per-character minimums (ATK, DEF, HP, Ego, CRate, CDmg, Extra%, DoT%), all HARD: builds missing ANY are excluded. If no combination satisfies them the optimizer returns an empty list and the UI must surface that.

They exist mainly to help meet the in-game **Potential 7** stat requirements, so **the comparison values mirror what those in-game checks can see**: Potential 7 ignores ALL Partner passive bonuses (unconditional and conditional alike), all Equipment contributions, and conditional set procs — but DOES see the Partner's flat class stats. The optimizer SCORE still models every excluded source; only the Have-at-least gate and the Potential 7 display rows ignore them.

- **ATK / DEF / HP** compare against the build's INNER value: `(Base + Partner flat) × (1 + Fragment% + Potential%) + Fragment flat + Affinity flat` — no outer `(1 + Partner% + Equipment%)`, no Equipment flat.
- **CRate / CDmg** compare against the final value minus conditional set contributions and minus all partner passives (both `stats` and `stats_conditional` in `partners.py`).
- **Ego, Extra%, DoT%** compare against the final value minus all partner passives.

None compares raw substat sums.

### Per-character settings persistence

`settings/optimizer_settings.json`, keyed by `res_id` (string form). Each entry holds that character's slider/spinbox/checkbox state. New characters get a default entry on first appearance, and renames don't lose data because the key is the res_id.
