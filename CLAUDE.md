# Notes for Claude

Repo-specific conventions and hazards. Read the topic doc for the area
you're working in (index below) before touching it. Tasks and todos go
in `tasks.md` or a `plan.md`, never here.

Machine-wide rules — cp932, heredocs, editing, verifying, comment style,
the start-of-turn commit — are in `~/.claude/CLAUDE.md`, which loads
alongside this. Only the repo half is below. The topic docs are NOT
loaded; read them on demand.

## Hard rules

- **Doc-first.** When in-game behaviour disagrees with the code or with
  `docs/game_formulas.md`, fix the doc first, then the code. A formula
  doc records what the user is ASKED TO ENTER as well as what the
  program computes — the Important Settings shares are read off the
  deck, not off damage numbers. Establish what a setting's input MEANS
  before changing math because it "should" behave differently.
- **Load-bearing code that looks removable:** `make_checkbox`'s
  `winfo_id()`, the `realize_windows()` walk in `_reveal_window`,
  `_ScrolledText`'s copy of the wrapper's geometry methods, and
  `OptimizerSettingsManager.load()`'s unknown-key passthrough. All
  pinned with a check. See `docs/ui_runtime.md` for the first three.
- **"Never open a window unasked" means the GUI here** — `zRUN.bat` and
  the spacing audit both need the maintainer at the keyboard.
- End-of-turn commits go after `checks/run_all.py`; messages use the
  CHANGELOG's register.

## Commands

- Syntax-check everything touched, from the repo root:
  `python -m compileall -q Vribbels`
- Build: `zCreate exe.bat` (PyInstaller, onefile). It passes `--add-data`
  on the command line, so `Vribbels_CZN_Optimizer_Ikkoru.spec` is an
  artifact it overwrites — edit the bat, never the spec. It runs
  `default_settings/normalize/normalize_defaults.py` first and fails if
  `default_settings/` is missing its three JSONs. Workflow:
  `docs/how_to_maintain_default_settings.md`.
- Checks: `python checks/run_all.py`, or `zRUN Checks.bat` for a window
  that stays open. Both take the same flags.
- Spacing audit: `zRUN Spacing Audit.bat` prints every gap missing its
  target (`...Verbose.bat` for all rows, `...Freeze.bat` to rewrite the
  baseline). It photographs the screen, so it needs the window
  unobscured and frontmost, the pointer off it, and a snapshot loaded —
  **ask before running one.** A normal launch never imports it.

## Headless verification

**Run `python checks/run_all.py` before handing work over.** ~15s, no
GUI; `--list` names them. They cover the invariants that fail QUIETLY:
optimizer parity, scoring reconciliation, game data, settings
round-trips, DoT scoring, shipped defaults holding no user state, the
spacing markers and the spacing registry, the audit's ink test against
the eye that calibrated it, tab construction, the flash fix, keyboard
type-ahead, the Upgrade Log filters the Memory Fragments columns share,
the Optimizer opening with no combatant selected, and the capture ones —
the addon template, batched frames, gacha banners, one account per
session, both regions routed, one save per FRAME, and reporting only
the snapshot this session wrote. Checks needing captured data skip
themselves when `Vribbels/snapshots/` is empty. Parity runs bounded;
`--full` takes minutes.

**Add a check whenever you fix something that failed silently** — that
is what the directory is for. `checks/__init__.py` says how.

`Vribbels/` imports without Tk, so the optimizer, the managers, the
validator and the game-data tables can all be exercised from a snippet
run in that directory.

**The UI can be measured headlessly, but only halfway.** Building the
tabs against a Tk root (the `check_tabs_build.py` recipe) makes widget
OPTIONS and DATA readable — `cget`, `grid_info`, a Treeview's row
values. RENDERED GEOMETRY does not come with them: `winfo_width` /
`winfo_x` read 1 until the window is mapped.

Mapping a window puts it on the maintainer's screen — **ask first**.
`withdraw()` is not enough (`tk.Tk()` maps on construction, so
withdrawing on the next line still flashes a frame). The app's own
answer is `_hide_until_ready()`: alpha 0, which is mapped and therefore
measurable but invisible. Use that for any probe that needs real
geometry.

| To check                              | Do this                                                                                                                              |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Any file touched                      | `python -m compileall -q Vribbels`                                                                                                   |
| Anything, before handing over         | `python checks/run_all.py`                                                                                                           |
| A `game_data/` table                  | `game_data_validator.check_data_files()` and `find_data_problems()` — the launch-time checks, invoked directly                        |
| Scoring or per-combo math             | `optimizer/core.py` directly; it is pure                                                                                             |
| An end-to-end optimizer change        | `GearOptimizer().load_data(<newest snapshot>)`, then `optimize(...)`                                                                  |
| Parallel/sequential parity            | `checks/check_optimizer_parity.py` — don't re-roll it by hand                                                                        |
| A settings or defaults-sync change    | Point the managers at a COPY of `Vribbels/settings/` in the scratchpad, never the live folder                                        |
| Which widgets a change moved          | Build the tabs the `check_tabs_build.py` way, snapshot every row's values before and after, diff                                      |
| A rendered GAP, in pixels             | `zRUN Spacing Audit Verbose.bat` — every registered gap, read off a screenshot. Ask before running one                                |
| Something only the screen shows       | A side-by-side repro in `_tmp/`, for the maintainer to run                                                                            |

Snapshots are the maintainer's captured game data. Read them; never
write to `Vribbels/snapshots/` or `Vribbels/settings/`.

## Where the detail lives

| Area                                                                 | Doc                                        |
| -------------------------------------------------------------------- | ------------------------------------------ |
| Game math: damage, shield/heal, set effects, scoring                 | `docs/game_formulas.md` (canonical)        |
| `*_manager.py`, `defaults_sync.py`, Restore Defaults, settings files | `docs/settings_architecture.md`            |
| Shipping `default_settings/` — maintainer workflow                   | `docs/how_to_maintain_default_settings.md` |
| `capture/`, snapshot parsing, char-vs-partner classification         | `docs/capture_pipeline.md`                 |
| `game_data/*.py`, the launch-time validator, stat vocabularies       | `docs/game_data_files.md`                  |
| Tk threading, startup, display quirks                                | `docs/ui_runtime.md`                       |
| Panel layout, spacing rules, the ledger, ttk styles                  | `docs/ui_spacing.md`                       |
| `tasks.md` / `plan.md` / CHANGELOG conventions                       | `docs/repo_conventions.md`                 |
| The executable checks, and how to add one                            | `checks/__init__.py`                       |
| Optimizer / startup performance history                              | `past_plans/optimizer_performance.md`      |
| Why the game-data validator checks what it checks                    | `past_plans/game_data_validation.md`       |
| Why the spacing work took the shape it did, and what is left of it   | `past_plans/UI_unionization.md` and `_extra` |

`past_plans/` is an ARCHIVE and the one exception to the
no-dates/no-status-tags rule: its dated decisions and `[IMPLEMENTED]`
tags are the record. Read one before reopening a question it settled.

## Project identity

**Vribbels CZN Optimizer (Ikkoru fork)** — a Memory Fragment / gear
optimizer for **Chaos Zero Nightmare** (CZN), forked from
`Vorbroker/Vribbels-CZN-Optimizer` at upstream v1.7.0. This fork is
`Ikkoru/Vribbels-CZN-Optimizer`, branch `master`.

Version string: `Vribbels/version.py`, bumped ONLY at release — dev
builds keep the released string.

## Layout

- Python 3, Tkinter UI, mitmproxy for capture.
- Source root `Vribbels/`; main GUI `czn_optimizer_gui.py`; tabs in
  `ui/tabs/{about,capture,heroes,inventory,materials,optimizer,scoring,setup}_tab.py`.
- Optimizer engine: `optimizer/optimizer.py` (wrappers, run context,
  dispatch), pure per-combo math in `optimizer/core.py`, multiprocessing
  in `optimizer/parallel.py`.
- Game data tables in `game_data/`; dataclasses in `models/`.
- Shared widget helpers in `ui/utils/`. Every checkbox comes from
  `checkbox.py` and every scrolled text from `scrolled_text.py`; a check
  enforces both.

**Identifiers inherited from upstream do not use the game's words**, and
that mismatch is deliberate — renaming them cascades through saved
settings, presets and captured-data keys. User-visible TEXT uses the
game's term; identifiers keep upstream's.

| Code says                              | The game says     |
| -------------------------------------- | ----------------- |
| `heroes_tab.py`, `hero`                | Combatant         |
| `inventory_tab.py`, `piece`            | Memory Fragment   |
| `materials_tab.py`                     | growth stones     |
| `FRIENDSHIP_BONUSES`, `friendship_index` | Affinity        |
| `dot_pct`, `dot_share`                 | the Agony share   |

The last row is the sharp one: the `DoT%` STAT is called DoT% in game
and improves all three DoT types, while the damage TYPE the program
calls DoT is only Agony. `docs/game_formulas.md` §3.4 is canonical.

Rename toward the game when adding user-visible text; never the other
way, and don't "fix" an identifier to match.

## Engineering invariants

- **Parallel results must be byte-identical to sequential**, tie-break
  included (`core.result_sort_key`: -score, then fragment-id tuple).
  Re-verify parity after touching enumeration, scoring or result
  handling. Enumeration/trim ranks by the greedy-ref `trim_blend` scalar
  (a per-run constant, so every worker agrees); the display re-blend and
  top-row rescale run ONCE parent-side after the merge.
- **"Have at least" / Potential 7 comparison values mirror the in-game
  Potential 7 checks:** Partner flat class stats INCLUDED (inside the
  inner multiplier); Partner passives, Equipment and conditional set
  bonuses EXCLUDED. The optimizer SCORE still models every excluded
  source. Canonical: `docs/game_formulas.md` §8.
- **The Results Score column is a 0-100 display scale** (top row = 100)
  produced inside `optimize()`. Code re-deriving it elsewhere must go
  through `optimizer.reblend_results_for_display`, NOT
  `core.compute_score`, which is a raw scalar on a different scale.
  Canonical: `docs/game_formulas.md` §8.
- **The Combatants tab's live refresh is gated on
  `HeroesTab.display_signature()`.** A field that reaches the rows or
  the detail pane without being added to the signature goes stale
  silently — extend the signature in the same edit.

## Cross-cutting gotchas

- `optimizer.characters` holds only characters with at least one
  EQUIPPED MF. For ALL captured characters, union with
  `optimizer.character_info.keys()`. See `refresh_exclude_heroes`,
  `refresh_hero_list`.
- `_MEIPASS` is READ-ONLY in frozen builds. Anything that writes
  (settings, snapshots, `.defaults_sync.json`) must use
  `_user_data_dir()`, which returns `sys.executable.parent` when frozen,
  NOT `__file__`'s parent.

## Comments in this repo

- A `# spacing:` marker must be greppable as one string, so it stays on
  one line whatever its length. The wrap loses to the content.
- UI spacing values carry `# spacing: <rule>` rather than the distance
  they produce. See `docs/ui_spacing.md` "The rules".
