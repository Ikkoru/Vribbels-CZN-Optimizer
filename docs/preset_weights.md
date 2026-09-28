# Deriving the default Gear Score presets

The shipped presets (`Vribbels/default_settings/presets.json`) weigh each substat for one combatant. They exist to rank fragments: which ones would make a combatant's top builds, and whether a fragment is worth levelling past +3, where the cost jumps. `docs/preset_weights.py` derives them from the Optimizer's own score, so a weight means the same thing for every combatant.

## What a weight is

**One MAX roll of a stat, as the relative gain it gives the score, divided by one max roll of the preset's scaling stat.** The score is the Optimizer's blend, `(1 - h) × D + h × S` over `core.compute_score_components`' damage term D and shield/heal term S, with `h` the combatant's shield/heal weight; its relative gain is `(1 - h) × dD/D + h × dS/S`. The roll is added as a pseudo-fragment carrying nothing else, so every layer of the stat formula (`game_formulas.md` §1) applies to it as to a real substat.

- **Max rolls, not average ones**, because the Gear Score divides every roll by its stat's max roll (`_raw_substat_score`). An average-roll comparison overstates Extra% and DoT% by about 11% and understates Ego, their minimum rolls being a different share of their maximum.
- **The scaling stat reads 1**: DEF% for a DEF scaler or a healer (a shield/heal weight of 50 or more), else ATK% — or DEF% where the preset already reads DEF% 1 over a smaller ATK%. Only the ratios matter: the Gear Score rescales each preset to 0–100 by its own best and worst.
- **What the score cannot price keeps the preset's own weight.** Ego, HP, and any stat worth exactly nothing to the score are tie-breakers the maintainer sets, Ego and DEF ahead of HP, each small enough never to outrank a damage stat.

## The reference build: in a vacuum

A fragment is judged without knowing what the combatant wears now, so the build it is weighed against is a decently built one, the same for every account:

| Part | Assumed | Why |
| ---- | ------- | --- |
| Level | 61 | Level 62 gains are unknown; `LEVEL_BONUS_BY_CLASS` |
| Partner flat stats | Their class's 5★ partner (`PARTNER_CLASS_STATS`) | A 4★ or 4.5★ partner shifts the flat-to-% ratio by up to 10% |
| Partner passives | The combatant's signature partner at limit break 0 | Most 5★ combatants wear it; `SIGNATURE_PARTNERS` lists the rest, and a 4.5★ one keeps its passive |
| Potential nodes 5 and 6 | Maxed | A built combatant has them |
| Affection | The highest tier of `FRIENDSHIP_BONUSES` | Likewise |
| Fragment stats | Their ARCHETYPE's average | Below |
| Sets | Their own best build's, or the preset's named 4-piece | Below |

**The archetype's average fragment stats** are the mean of the fragment stats — substats and main stats, no sets — of every archetype member's best Optimizer build: their own settings, level 61, nothing excluded, the global minimum-level and off-element filters. `archetype()` groups by what the settings say a combatant does: ATK DPS, ATK DPS with Extra damage, ATK DPS with DoT, DEF DPS, healers dealing ATK damage, healers. The averages and each member's set bonuses are kept in `preset_weights_archetypes.json`, so the weights are reproducible without running the Optimizer. It holds stats only, never a fragment's id, since it is tracked.

**Why archetype averages rather than each combatant's own best build.** Both were compared: they agree on every flat and % weight and within about 0.1 on CRate and CDMG for most combatants. Where they part, the best build's crit is lopsided by what the inventory happens to hold — the in-a-vacuum judgement the presets exist for is the archetype's.

**A preset named for a 4-piece set assumes it worn** (`VARIANTS`): Line of Justice's +20 CRate or Conqueror's Aspect's +35 CDMG at the combatant's effect share, which is what moves CRate against CDMG for those combatants. Where the inventory has no such build, the set is added with Executioner's Tool ×2 (`PAIRED_TWO_PIECE`), and the report says so.

## Presets that are not the combatant's own settings

`VARIANTS` holds each: an override of the Optimizer settings (Beryl's Upgrade deck and the no-Extra builds, Orlea's two skews), the named set, or Maribell's lean. Her shield-scaling build deals damage only CRate and CDMG move — nothing the Optimizer models — so her Shelter Strike preset blends that build's crit gains with the ordinary build's at `unique_lean`; 0.5 is the maintainer's hedge.

## Running it

From the repo root:

    python docs/preset_weights.py            # the derived weights against the current ones
    python docs/preset_weights.py --derive   # re-derive the archetypes (a few minutes), then the above
    python docs/preset_weights.py --check    # would today's archetypes move the weights? records the check
    python docs/preset_weights.py --write    # the derived weights into default_settings/presets.json

The report prints each preset's current and derived weights with the reference build's crit and ATK/DEF, and writes the whole proposal to `_tmp/preset_weights_proposal.json`. **Review it before `--write`**, and read the notes: a synthetic set, a combatant with no build. `--write` touches the shipped defaults only; the maintainer's own presets change through the app's Restore Defaults.

**When:** on demand, and once per Galactic Disaster, from its part 2 — `checks/check_preset_weights.py` fails until `--check` has been run in the season's part 2 or later, because the archetypes follow the game: new sets, new main stats, a change to a roll range all move them. `--check` re-derives, compares, and prints every weight that would move by more than 10%; if any does, re-derive with `--derive` and review.

## What keeps it working

- **It runs on the program's own code**: `compute_build_stats`, `compute_score_components`, `optimize`, the partner, potential and level helpers. A change to the formulas, a new stat in `STATS`, new set values reach the weights with nothing to update here. `checks/check_preset_weights.py` derives every preset from the stored archetypes on each run, so a refactor that breaks the tool fails there.
- **A new combatant** needs Optimizer settings and an assigned preset; a signature partner other than the one equipped goes in `SIGNATURE_PARTNERS`; a preset with its own assumption in `VARIANTS`.
- **A new kind of combatant** — one `archetype()` does not describe — gets its own group, or borrows a neighbour's averages until it has members.

## What it does not model

- **Potential node 7**, a conditional stat per combatant; to be redone once the program models it.
- **Card-level mechanics** the score does not see, like Maribell's shield-scaling card; those are hedges, set by hand in `VARIANTS`.
- **The Optimizer settings themselves**, which were set by eye; `tasks.md` T20 would derive them from a deck.
