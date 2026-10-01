# Deriving the default Gear Score presets

The shipped presets (`Vribbels/default_settings/presets.json`) weigh each substat for one combatant. They exist to rank fragments: which ones would make a combatant's top builds, and whether a fragment is worth levelling past +3, where the cost jumps. `docs/preset_weights.py` derives them from the Optimizer's own score, so a weight means the same thing for every combatant.

## A weight

**One MAX roll of a stat, as the relative gain it gives the score, divided by one max roll of the preset's scaling stat.** The score is the Optimizer's blend, `(1 - h) × D + h × S`, of `core.compute_score_components`' damage term D and shield/heal term S, with `h` the combatant's shield/heal weight. Its relative gain is `(1 - h) × dD/D + h × dS/S`. The roll is added as a pseudo-fragment carrying nothing else, so every layer of the stat formula (`game_formulas.md` §1) applies to it as to a real substat.

- **Max rolls, not average ones**, because the Gear Score divides every roll by its stat's max roll (`_raw_substat_score`). An average roll is a different share of the maximum for each stat, so an average-roll comparison misprices every stat whose minimum-to-maximum ratio differs from the scaling stat's: Extra% and DoT% up, Ego down.
- **The scaling stat reads 1**: DEF% for a DEF scaler or a healer (a shield/heal weight of 50 or more), else ATK% — or DEF% where the preset already reads DEF% 1 over a smaller ATK%. Only the ratios matter: the Gear Score rescales each preset to 0–100 by its own best and worst.
- **What the score cannot price keeps the preset's own weight.** Ego, HP, and any stat worth exactly nothing to the score are tie-breakers the maintainer sets, Ego and DEF ahead of HP, each small enough never to outrank a damage stat.

## The reference build: in a vacuum

A fragment is judged without knowing what the combatant wears now, so the build it is weighed against is a decently built one, the same for every account:

| Part | Assumed | Why |
| ---- | ------- | --- |
| Level | 61 | Level 62 gains are unknown; `LEVEL_BONUS_BY_CLASS` |
| Partner flat stats | Their class's 5★ partner (`PARTNER_CLASS_STATS`) | A weaker partner's smaller flat stat is a smaller base for a % roll to multiply, so it moves the flat-to-% ratio |
| Partner passives | The combatant's signature partner: 5★ and 4.5★ at limit break 0, 4★ at their highest | Most 5★ combatants wear it; `SIGNATURE_PARTNERS` lists the rest, and a 4.5★ one keeps its passive |
| Potential nodes 5 and 6 | Maxed | A built combatant has them |
| Potential node 7 | Taken, whatever the account's own combatant has | Its growth is part of what a stat buys: Rin's ATK buys CRate |
| Affection | The highest tier of `FRIENDSHIP_BONUSES` | Likewise |
| Fragment stats | Their ARCHETYPE's average | Below |
| Sets | Their own best build's, or the preset's named 4-piece | Below |

**The archetype's average fragment stats** are the mean of the fragment stats of every archetype member's best Optimizer build: substats and main stats, no sets. The build is run on their own settings at level 61, with nothing excluded and the global minimum-level and off-element filters. It uses the Optimizer tab's candidate cut too, the top of each slot by the combatant's assigned preset, so the archetypes lean slightly on the presets being derived: a re-derivation after new presets are written can move them a little. `archetype()` groups by what the settings say a combatant does: ATK DPS, ATK DPS with Extra damage, ATK DPS with DoT, DEF DPS, healers dealing ATK damage, healers. The averages and each member's set bonuses are kept in `preset_weights_archetypes.json`, so the weights are reproducible without running the Optimizer. It holds stats only, never a fragment's id, since it is tracked.

Why archetype averages rather than each combatant's own best build. Both were compared: they agree on every flat and % weight and within about 0.1 on CRate and CDMG for most combatants. Where they part, the best build's crit is lopsided by what the inventory happens to hold — the in-a-vacuum judgement the presets exist for is the archetype's.

**A preset named for a 4-piece set assumes it worn** (`VARIANTS`): Line of Justice's CRate or Conqueror's Aspect's CDMG, as `SETS` gives them, at the combatant's effect share. That is what moves CRate against CDMG for those combatants. Where the inventory has no such build, the set is added with Executioner's Tool ×2 (`PAIRED_TWO_PIECE`), and the report says so.

## Presets that are not the combatant's own settings

`VARIANTS` holds each: an override of the Optimizer settings (Beryl's Upgrade deck and the no-Extra builds, Orlea's two skews), the named set, or Maribell's lean. Her shield-scaling build deals damage that only CRate and CDMG move, which nothing in the Optimizer models. So her Shelter Strike preset blends that build's crit gains with the ordinary build's at `unique_lean`, the maintainer's hedge.

## Running it

From the repo root:

    python docs/preset_weights.py            # the derived weights against the current ones
    python docs/preset_weights.py --derive   # re-derive the archetypes (a few minutes), then the above
    python docs/preset_weights.py --check    # would today's archetypes move the weights? records the check
    python docs/preset_weights.py --write    # the derived weights into default_settings/presets.json

The report prints each preset's current and derived weights with the reference build's crit and ATK/DEF, and writes the whole proposal to `_tmp/preset_weights_proposal.json`. **Review it before `--write`**, and read the notes: a synthetic set, a combatant with no build. `--write` touches the shipped defaults only; the maintainer's own presets change through the app's Restore Defaults.

**When:** on demand, and once per Galactic Disaster from its part 2. `checks/check_preset_weights.py` fails until `--check` has been run in the season's part 2 or later, because the archetypes follow the game: new sets, new main stats, a change to a roll range all move them. `--check` re-derives, compares, and prints every weight that would move by more than 10%. If any does, re-derive with `--derive` and review.

## Keeping it in step

- **It runs on the program's own code**: `compute_build_stats`, `compute_score_components`, `optimize`, the partner, potential and level helpers. A change to the formulas, a new stat in `STATS`, new set values reach the weights with nothing to update here. `checks/check_preset_weights.py` derives every preset from the stored archetypes on each run, so a refactor that breaks the tool fails there.
- **A new combatant** needs Optimizer settings and an assigned preset. A signature partner other than the one equipped goes in `SIGNATURE_PARTNERS`, and a preset with its own assumption in `VARIANTS`.
- **A new kind of combatant** — one `archetype()` does not describe — gets its own group, or borrows a neighbour's averages until it has members.

## Outside the model

- **Potential 7 bonuses the score does not price**: a card's, an event's, Weakness Damage (`game_formulas.md` §1, *Potential 7*).
- **Card-level mechanics** the score does not see, like Maribell's shield-scaling card; those are hedges, set by hand in `VARIANTS`.
- **The Optimizer settings themselves**, which were set by eye; `tasks.md` T20 would derive them from a deck.
