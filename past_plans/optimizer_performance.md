# plan.md — Parallelism / multi-threading plan (v1.2.0+)

Planning document for speeding up the app's long-running work. Written
against the v1.2.0-dev codebase; update this file as phases land or
decisions change.

## Scope and goals

- **Primary target: `optimizer.optimize()` build enumeration.** The only
  genuinely long-running compute in the app (seconds to minutes depending
  on candidate pool sizes and flex settings).
- **Secondary targets:** Combatants-tab `refresh_heroes` cost (see
  CLAUDE.md task list — needs profiling first), snapshot load/parse.
- **Out of scope:** capture — mitmproxy already runs as a separate
  process; nothing to parallelize on our side.

## Hard constraints

1. **Tkinter is single-threaded.** All widget/StringVar access stays on
   the main thread. The established pattern — worker posts to a
   `queue.Queue`, the UI polls via `after()` (`check_queue` in the
   Optimizer tab, timer polling in the About tab) — is kept as-is. The
   run-id tagging + per-run cancel object scheme added in v1.2.0 carries
   over 1:1.
2. **Result parity.** The parallel path must produce the same top-100
   builds (and the same `last_optimize_stats` counters) as the
   single-thread path on identical inputs. Parallelism is a pure
   performance change, never a behavior change.
3. **Frozen builds keep working.** PyInstaller on Windows +
   `multiprocessing` means spawn semantics — see the checklist below.
4. **Rollback stays cheap.** The legacy in-process path remains intact
   and selectable; the parallel path ships behind a setting.

## Why processes, not threads (for the enumeration)

The enumeration is pure-Python arithmetic in tight loops — GIL-bound, so
`threading` yields ~zero speedup for it. Realistic options:

- **A) `multiprocessing` (ProcessPoolExecutor).** True parallelism,
  ceiling ≈ core count. Costs: pickling the inputs per run, Windows
  spawn startup latency, frozen-build caveats, a new module boundary.
- **B) NumPy vectorization.** Batch the scoring math over many combos at
  once; commonly ≥10x single-core for this shape of problem, no process
  machinery. Costs: substantial rewrite of `_compute_optimizer_score` /
  `calculate_build_stats` hot path, float-parity care, and ~15–30 MB of
  exe size. Dependency approved by the maintainer (2026-07-10), so this
  is a real option — held as the follow-up if processes alone aren't
  enough (the two also stack).
- **C) Algorithmic pruning (branch & bound).** Skip inner loops when even
  an optimistic upper bound can't beat the current worst kept result.
  Complication: the score is not monotone-decomposable (the crit modifier
  is nonlinear across CRate/CDmg, HAL is a hard filter), so any bound must
  be provably conservative. Worth investigating regardless of A/B — the
  wins multiply.

**Recommendation:** A (processes) as the main line — it preserves the
exact per-combo math, so parity is trivial — with C investigated
alongside. B is the approved next lever if measurements say more is
needed after Phase C.

## Current `optimize()` shape (facts the design builds on)

- Per-slot candidate lists (`get_gear_by_slot`: top-N by weights,
  10-fragment floor), then `itertools.product` across the 6 lists.
- Per combo: locked-slot set check → build stats → inline Have-at-least
  filter → score → append.
- `cancel_flag` (1-element list) polled every iteration; fresh object per
  run since v1.2.0.
- Progress callback every 5000 combos with `(checked, total, found)`.
- In-flight trim: when `len(results) > max_results*10`, sort + keep top
  `max_results`.
- End of run: final sort desc → trim to `max_results` (100) →
  buff-baseline rescale of the score column → `last_optimize_stats`
  counters (`total_combinations`, `passed_set_reqs`,
  `passed_have_at_least`).

## Parallel decomposition design (Phase C)

- **Partition dimension:** slot 1's candidate list, strided — worker *i*
  of *N* takes candidates `[i::N]` and enumerates
  `product(its_share, slots 2..6)`. Striding balances load when the
  best candidates cluster at the top of the sorted list.
- **Per-worker accumulation:** bounded top-K min-heap (K =
  `max_results`) keyed by score, plus local counters and a checked
  count. No in-flight global list, no cross-worker coordination during
  the loop.
- **Merge in parent:** concatenate the workers' top-K sets → final sort →
  trim to K → buff-baseline rescale → counters summed into
  `last_optimize_stats`. A union of per-partition top-Ks provably
  contains the global top-K, so parity holds.
- **Determinism note:** the current sort keys on score alone; equal-score
  builds could order differently across worker counts. Add an explicit
  deterministic tie-break (e.g. tuple of fragment ids) to the sort key in
  BOTH paths in Phase B — behavior-neutral, makes parity testable.
- **Progress:** workers post `(worker_id, checked_delta)` on a
  `multiprocessing.Queue` every 5000 combos. A small coordinator
  *thread* in the GUI process drains it, aggregates, and re-posts the
  existing `("progress", run_id, checked, total, found)` message shape
  onto the tab's `queue.Queue` — the UI code doesn't change.
- **Cancel:** one `multiprocessing.Event` per run (mirrors the per-run
  flag object); workers poll it each chunk; Stop sets it; partial
  results still merge and "done" is always posted (parity with the
  crash-safe done handling from v1.2.0).
- **Data marshaling:** parent precomputes plain picklable inputs —
  fragments as tuples/dicts (id, slot, set_id, main stat, substats,
  level, rarity, owner), the settings dict, and the character's static
  inputs (base stats, partner contributions, attribute) — so workers
  never touch managers or Tk. Workers import `game_data` normally on
  spawn.
- **Worker entry point:** module-level function in a new
  `optimizer/parallel.py` (spawn cannot pickle closures/nested
  functions). No Tk imports anywhere on that module's import path.

## Frozen-build checklist (Windows spawn + PyInstaller)

- `multiprocessing.freeze_support()` as the first statement in the
  `__main__` guard of `czn_optimizer_gui.py`. **[DONE]**
- AUDIT: confirm all side effects (single-instance socket bind, Tk root,
  manager construction, defaults sync) run inside the `__main__` guard /
  a `main()` function — spawn re-imports the entry module in every
  worker, and import-time side effects would run N extra times (or worse,
  trip the single-instance lock). **[DONE — audited clean: module level
  is imports/classes/constants only; every side effect is inside
  `main()`.]**
- Verify worker spawn latency from the packaged exe. The release stays
  **onefile** (maintainer decision — simpler for users to download);
  modern PyInstaller children reuse the parent's extracted `_MEIPASS`
  dir, so spawn is process + interpreter startup, not a re-extraction.
  Mitigate by creating the pool lazily ONCE per app session and reusing
  it across runs. If real-machine testing shows pathological spawn cost
  anyway (known culprit: antivirus re-scanning the exe per child),
  revisit onedir then — not before. **[VERIFIED 2026-07-11: frozen
  build works.]**
- Fallback setting: `optimizer_workers` (0 = auto = `cpu_count()-1`,
  1 = legacy single-thread path), stored in `settings/config.json`
  (maintainer decision). Ship file-only first; see UI note below.

## Phases

- **Phase A — Measure. [IMPLEMENTED]** Wall-time + combos/sec land in
  `last_optimize_stats`, the Results status line shows the run duration,
  and `perf_log.py` appends every run to `settings/perf_log.txt`
  (including the per-slot candidate counts the search space is built
  from).

  **Measurements (maintainer, i9-12900K, 607 MFs, Chizuru):**

  | Run | Max Flex | Ignore below | Combos | Time | µs/combo |
  | --- | -------: | -----------: | -----: | ---: | -------: |
  | auto workers | 2 | 0 | 10,647,000 (2.6% scored) | 3.34s | — |
  | auto workers | 6 | 0 | 10,647,000 (all scored)  | 21.27s | 2.00 |
  | auto workers | 6 | 3 | 3,963,960  | 11.15s | 2.81 |
  | auto workers | 6 | 4 | 1,000,000  | 2.36s  | 2.36 |
  | auto workers | 6 | 5 | 900,000    | 2.14s  | 2.38 |
  | 1 worker     | 6 | 0 | 10,647,000 | 201.11s | 18.89 |

  Per-slot candidates at 607 MFs: `{1:13, 2:15, 3:15, 4:14, 5:26, 6:10}`
  (slot 6 sits on the 10-fragment floor).

  **Derived cost model.** Solving the two Max-Flex runs against
  `time = N_enum x c_enum + N_scored x c_score` gives, on auto workers:
  **c_enum ≈ 0.27 µs** per enumerated-then-rejected combo and
  **c_score ≈ 1.73 µs** per fully scored one — scoring costs ~6.4x what
  rejection does. Single-thread is 18.89 µs/combo, so the parallel
  speedup is **9.45x** (24 threads; sub-linear as expected from E-cores
  plus merge overhead). Note `combos_per_sec` on its own is NOT a
  constant — it tracks the scored fraction, which is why the Max Flex 2
  run appears 6x "faster" per combo.

  **Second measurement set (616 MFs, Chizuru, Max Flex 6, auto workers)**
  — this one varies the exclude list, which turns out to matter more than
  anything else:

  | Excluded | Ignore below | Slot candidates | Combos | Time |
  | -------- | -----------: | --------------- | -----: | ---: |
  | None | 0 | {18,19,20,19,31,14} | 56,402,640 | 105.9s |
  | All  | 0 | {13,15,15,14,26,10} | 10,647,000 | 26.2s |
  | All  | 4 | {10,10,10,10,10,10} | 1,000,000 | 2.3s |
  | All  | 4 (Flex 2) | {10,...} | 1,000,000 (7% scored) | 0.6s |

  Excluding every combatant removes all EQUIPPED fragments from the pool,
  which shrinks each slot list by roughly a third and the product by
  **5.3x**. Any projection has to be anchored on the Excluded=None row.

  **1000-MF projection (revised).** From the Excluded=None row: all six
  slots are above the 10-fragment floor, so all six scale, and
  1000/616 = 1.62 gives 1.62^6 = **18.3x** -> ~1.0 x 10^9 combos,
  **~32 minutes on auto workers**, ~5 hours single-threaded. That is far
  worse than the earlier estimate, which was anchored on the
  Excluded=All pool.

  Caveat: this assumes fragments spread evenly across slots, and they
  don't. Slot 5 runs consistently largest (26-31 vs 13-20) because it has
  the most distinct worthwhile main stats -- the five elemental DMG%
  mains all live there, so players keep more slot-5 fragments to cover
  different elements. That's a property of the game, not of one
  inventory, so expect other users' slot 5 to be disproportionate too,
  and expect real growth to be lumpier than a flat 1.62^6.

  **Conclusion: still no new engine work, but the level filter is now
  load-bearing rather than a convenience.** "Ignore MFs below level 4"
  collapses every slot to the floor (1,000,000 combos, 2.3s) and holds
  that until level-4+ fragments per slot exceed the floor, so it absorbs
  inventory growth almost entirely -- which is why it now defaults to 4.
  Max Flex 2 adds a further 4x by rejecting 93% of combos cheaply. Both
  shrink the per-slot lists BEFORE the product is formed, which is
  leverage neither branch-and-bound nor NumPy can match: at 1000 MFs
  they would turn ~32 minutes into ~3-15 minutes, where the filter turns
  it into seconds. Revisit only if a future cap lands far beyond 1000 AND
  users are routinely running unfiltered with no exclusions.

  **`refresh_heroes` profiling: DONE, and it is not a bottleneck** —
  67-72 ms per call, with the whole re-score + both tab rebuilds at
  180-186 ms. The old suspects (per-row widget creation,
  `get_potential_stat_bonus`, per-substat dict lookups) are all
  irrelevant at this scale.
- **Phase B — Extract the pure core. [IMPLEMENTED 2026-07-10, verified
  behavior-neutral by the maintainer.]** Per-combo evaluation lives in
  `optimizer/core.py` (pure module-level functions, plain data, no
  `self`); GearOptimizer's formula methods are delegating wrappers; the
  deterministic tie-break (`core.result_sort_key`) is in both sort
  sites; the run context (`build_run_context`) precomputes all
  char-static inputs once per run.
- **Phase C — Parallel path** behind `optimizer_workers`, per the design
  above. **[IMPLEMENTED 2026-07-10, VERIFIED 2026-07-11.]**
  `optimizer/parallel.py`: strided slot-1 partitioning, per-worker
  top-K with the shared trim/sort semantics, Manager Event/Queue for
  cancel + progress, persistent session pool, sequential fallback on
  any parallel-path exception, worker-returned fragments remapped onto
  the parent's objects by id. Acceptance verified by the maintainer:
  identical results vs `optimizer_workers = 1` on the same inputs,
  Stop mid-run works, frozen build spawns workers correctly.
- **Phase D — Startup time.** The Combatants half of this phase is
  **dropped**: Phase A measured the whole re-score + both tab rebuilds at
  ~0.19s, so neither threading the parse nor reusing Combatants row
  widgets would be felt. (`load_data` also no longer calls
  `refresh_inventory()` / `refresh_heroes()` directly — the
  `apply_active_weights()` call right after already does both, so each
  tab had been rebuilt twice per load.)

  What remains is the rest of startup, now measured (616 MFs, i9-12900K):

  | Phase | Time |
  | ----- | ---: |
  | module imports (`-X importtime`) | <0.1s |
  | managers | 0.06s |
  | build_tabs (all eight) | 0.42s |
  | auto_load (read + parse + refresh) | 0.50s |
  | reveal settle, pass 1 | **2.17s** |
  | reveal settle, passes 2-3 | 0.00s |
  | **TOTAL** | **~3.1s** |

  **Startup is at its floor without restructuring the Optimizer tab.**
  Everything except the first layout pass is already sub-second combined,
  and that pass is Tk laying out and drawing the Optimizer tab's several
  hundred widgets for the first time -- work that has to happen before
  the window can be shown, wherever it's triggered from. The settle
  loop's 3-pass floor costs nothing (passes 2-3 measure 0.000s), so it
  stays as cheap insurance against a layout that needs a second pass.

  Two earlier suspicions were measured and dropped: cycling every tab to
  pre-settle it cost 2.6-3.8s and was replaced with pre-settling only the
  Optimizer tab; and the Combatants tab does NOT re-run `refresh_heroes`
  on tab switches (the only caller is `scoring_tab.apply_active_weights`
  at load). Its slowness on each open is Tk re-mapping ~400 individual
  labels -- it uses labels rather than a Treeview because it needs
  per-CELL colour, which ttk.Treeview can't do. Accepted as-is.

  If startup ever needs to go lower, the only real lever left is reducing
  what the Optimizer tab builds up front -- deferring the exclude
  checklist or the sets grid until first use.
- **Phase E — capture:** none (separate process already).

## Invariants to preserve

- Tk single-thread rule: workers and the coordinator thread never touch
  widgets or Tk variables.
- Parity: top-100 builds, their order (after the tie-break lands), and
  all `last_optimize_stats` counters match the legacy path.
- Cancel always yields partial results + a "done" message; Start can
  never be left disabled.
- Parent-side precompute only: workers get read-only plain data;
  `recalculate_scores` and other mutations stay on the GUI process.
- Dependency policy: no third-party additions without an explicit
  decision (NumPy route only).

## Maintainer decisions (2026-07-10)

1. **Run times:** worst case observed ≈ 6 minutes on a powerful PC with
   500 of the 1000-MF cap — Phase C is justified; expect super-linear
   growth toward the cap.
2. **`optimizer_workers` lives in `settings/config.json`.** Default
   auto (`cpu_count()-1`). Ship file-only initially; add a UI control
   only if a real reason to deviate from auto emerges (plausible ones:
   keeping cores free for the game client running alongside capture,
   thermal/battery limits, spawn troubleshooting). If the UI control is
   added: the spot originally earmarked for it — directly under the
   `Loaded <num> fragments` status — is now occupied by the "Ignore MFs
   below level" spinbox, so it needs a new home (the status cluster has
   room for a third row).
3. **Build stays onefile** — easier for users to download. Persistent
   pool per session amortizes spawn; onedir only reconsidered if
   testing shows pathological child-spawn cost (e.g. AV re-scans).
4. **NumPy is approved** as a dependency if measurements favor
   vectorization (Phase C follow-up, not the first move).
5. **Version bump happens at release time** (`version.py` stays at the
   released version during development).
