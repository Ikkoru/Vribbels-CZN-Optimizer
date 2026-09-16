---
paths:
  - "Vribbels/optimizer/**"
  - "Vribbels/ui/tabs/optimizer_tab.py"
  - "Vribbels/ui/tabs/scoring_tab.py"
---

# Optimizer rules

Loads when an optimizer file is read. Canonical math: `docs/game_formulas.md`.

## Invariants

- **Parallel results must be byte-identical to sequential**, tie-break included (`core.result_sort_key`: -score, then fragment-id tuple). Re-verify parity after touching enumeration, scoring or result handling. Enumeration/trim ranks by the greedy-ref `trim_blend` scalar (a per-run constant, so every worker agrees); the display re-blend and top-row rescale run ONCE parent-side after the merge.
- **"Have at least" / Potential 7 comparison values mirror the in-game Potential 7 checks:** Partner flat class stats INCLUDED (inside the inner multiplier); Partner passives, Equipment and conditional set bonuses EXCLUDED. The optimizer SCORE still models every excluded source. Canonical: `docs/game_formulas.md` §8.
- **The Results Score column is a 0-100 display scale** (top row = 100) produced inside `optimize()`. Code re-deriving it elsewhere must go through `optimizer.reblend_results_for_display`, NOT `core.compute_score`, which is a raw scalar on a different scale. Canonical: `docs/game_formulas.md` §8.

## Gotcha

- `optimizer.characters` holds only characters with at least one EQUIPPED MF. For ALL captured characters, union with `optimizer.character_info.keys()`. See `refresh_exclude_heroes`, `refresh_hero_list`.

## Verifying a change

| To check                     | Do this                                                                       |
| ---------------------------- | ------------------------------------------------------------------------------- |
| Scoring or per-combo math    | `optimizer/core.py` directly; it is pure                                      |
| An end-to-end change         | `GearOptimizer().load_data(<newest snapshot>)`, then `optimize(...)`           |
| Parallel/sequential parity   | `checks/check_optimizer_parity.py` — don't re-roll it by hand                 |
