# Notes for Claude

Repo-specific conventions and hazards. Read the topic doc for the area you're working in (index below) before touching it. Tasks and todos go in `tasks.md` or a `plan.md`, never here.

Machine-wide rules — cp932, heredocs, editing, verifying, comment style, the start-of-turn commit — are in `~/.claude/CLAUDE.md`, which loads alongside this. Only the repo half is below. The topic docs are NOT loaded; read them on demand.

**`.claude/rules/` holds the UI and optimizer rules**, which load when you read a file they cover — `px()` and the spacing markers under `Vribbels/ui/`, the parity and scoring invariants under `Vribbels/optimizer/`. Read the rule file yourself if you need it before touching such a file.

## Hard rules

- **A fact belongs in this file only if it is needed BEFORE you know which area you are working in.** This file loads in full every session; the topic docs are read on demand. A rule that only matters while editing one tab costs tokens in every session that does not touch it — put it in the topic doc.
- **`docs/ui_spacing.md` is parsed, not just read.** `check_spacing_markers.py` and `check_spacing_registry.py` navigate it by exact heading text and compare its rules, vocabulary and tables against the `RULE_*` constants and the `# spacing:` comments in the widget code. Renaming one of its headings fails a check. **`grep -rn "<heading text>" checks/` before editing a heading in any doc.**
- **Doc-first.** When in-game behaviour disagrees with the code or with `docs/game_formulas.md`, fix the doc first, then the code. A formula doc records what the user is ASKED TO ENTER as well as what the program computes — the Important Settings shares are read off the deck, not off damage numbers — so establish what an input MEANS before changing math because it "should" behave differently.
- **Load-bearing code that looks removable:** `make_checkbox`'s `winfo_id()`, the `realize_windows()` walk in `_reveal_window`, `_ScrolledText`'s copy of the wrapper's geometry methods, and `OptimizerSettingsManager.load()`'s unknown-key passthrough. All pinned with a check. The three UI ones are in `docs/ui_runtime.md`, the settings one in `docs/settings_architecture.md`.
- **"Never open a window unasked" means the GUI here** — `zRUN.bat` and the spacing audit both need the maintainer at the keyboard.
- End-of-turn commits go after `checks/run_all.py`; messages use the CHANGELOG's register.

## Commands

- **Build: `zCreate exe.bat`** (PyInstaller, onefile).
  - **Edit the bat, never the spec.** `--add-data` is passed on the command line, so `Vribbels_CZN_Optimizer_Ikkoru.spec` is an artifact the build overwrites.
  - Two scripts run first, and either failing stops the build. `default_settings/normalize/normalize_defaults.py` fails if `default_settings/` is missing its three JSONs — workflow in `docs/how_to_maintain_default_settings.md`. `build_tcl/prepare_tcl_data.py` unpacks Tcl/Tk's library only when PyInstaller cannot collect it.
  - **Tcl 9 keeps its library inside the DLL.** PyInstaller then finds no data files and its own runtime hook raises on the exe's first line: the build succeeds and the executable dies before any window.
- Spacing audit: `zRUN Spacing Audit.bat` prints every gap missing its target. It photographs the screen and needs the maintainer at the keyboard — **ask before running one.** A normal launch never imports it. The launchers, the preconditions and how to read the table: the `spacing-audit` skill.

## Headless verification

**Run `python checks/run_all.py` before handing work over** (`zRUN Checks.bat` for a window that stays open; same flags). No GUI, and quick enough to run every time. They cover the invariants that fail QUIETLY: optimizer scoring and parity, game data, settings round-trips, the capture pipeline, the spacing markers and registry, and the UI's own construction and geometry at both scales. `--list` names every one — read that rather than a copy of it here. A check with no captured data to work on skips, or notes what it could not cover. Parity runs bounded; `--full` takes minutes.

**Add a check whenever you fix something that failed silently** — that is what the directory is for. `checks/__init__.py` says how.

`Vribbels/` imports without Tk, so the optimizer, the managers, the validator and the game-data tables can all be exercised from a snippet run in that directory.

**Measuring the UI headlessly has its own rules** — `.claude/rules/ui.md`, which also carries the spacing audit's recipes.

| To check                              | Do this                                                                                                                              |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Any file touched                      | `python -m compileall -q Vribbels`                                                                                                   |
| Anything, before handing over         | `python checks/run_all.py`                                                                                                           |
| A `game_data/` table                  | `game_data_validator.check_data_files()` and `find_data_problems()` — the launch-time checks, invoked directly                        |
| A settings or defaults-sync change    | Point the managers at a COPY of `Vribbels/settings/` in the scratchpad, never the live folder                                        |

Snapshots are the maintainer's captured game data. Read them; never write to `Vribbels/snapshots/` or `Vribbels/settings/`.

## Where the detail lives

| Area                                                                 | Doc                                        |
| -------------------------------------------------------------------- | ------------------------------------------ |
| Game math: damage, shield/heal, set effects, scoring                 | `docs/game_formulas.md` (canonical)        |
| `*_manager.py`, `defaults_sync.py`, Restore Defaults, settings files | `docs/settings_architecture.md`            |
| Shipping `default_settings/` — maintainer workflow                   | `docs/how_to_maintain_default_settings.md` |
| `capture/`, snapshot parsing, char-vs-partner classification         | `docs/capture_pipeline.md`                 |
| Folding superseded captures into the archive                         | `Vribbels/capture/archive.py`, run by hand with `docs/snapshots_archive.py` |
| `game_data/*.py`, the launch-time validator, stat vocabularies       | `docs/game_data_files.md`                  |
| Which item res_ids are known, used, or still to identify              | `docs/items_id_dump.py` and the item TSVs it writes |
| What each shop sells, at what price and cap                           | `docs/items_shops.tsv` |
| The spacing audit's recorded readings                                 | `docs/spacing_baseline.json`, written by `zRUN Spacing Audit Freeze.bat` |
| Which mission res_ids are known, and which set each belongs to        | `docs/missions_id_dump.py` and `docs/missions_id.tsv` |
| Which wire field carries a Checklist row, and the suspects for the rest | `docs/wire_hunt.md` and `docs/wire_hunt.tsv` |
| What the wire has sent that nothing reads                             | `docs/wire_catalogue.py`, over `settings/wire_catalogue.json`; `docs/wire_catalogue_backfill.py` folds in older captures |
| Event categories, how to classify one, and what the Checklist does with each | `docs/events.md` |
| Tk threading, startup, display quirks                                | `docs/ui_runtime.md`                       |
| Panel layout, spacing rules, the ledger, ttk styles                  | `docs/ui_spacing.md`                       |
| Running a spacing audit and reading its table                        | `.claude/skills/spacing-audit/SKILL.md`    |
| `tasks.md` / `plan.md` / CHANGELOG conventions                       | `docs/repo_conventions.md`                 |
| The executable checks, and how to add one                            | `checks/__init__.py`                       |
| Optimizer / startup performance history                              | `past_plans/optimizer_performance.md`      |
| Why the game-data validator checks what it checks                    | `past_plans/game_data_validation.md`       |
| Why the spacing work took the shape it did, and what is left of it   | `past_plans/UI_unionization.md` and `_extra` |
| Why the capture archive is one rebuilt file, and what it cost to prove | `past_plans/capture_archiving.md` |

`past_plans/` is an ARCHIVE and the one exception to the no-dates/no-status-tags rule: its dated decisions and `[IMPLEMENTED]` tags are the record. Read one before reopening a question it settled.

## Project identity

**Vribbels CZN Optimizer (Ikkoru fork)** — a Memory Fragment / gear optimizer for **Chaos Zero Nightmare** (CZN). Python 3, Tkinter UI, mitmproxy for capture; source root `Vribbels/`. Forked from `Vorbroker/Vribbels-CZN-Optimizer` at upstream v1.7.0; this fork is `Ikkoru/Vribbels-CZN-Optimizer`, branch `master`.

Version string: `Vribbels/version.py`, bumped ONLY at release — dev builds keep the released string.

## Naming

**Identifiers inherited from upstream do not use the game's words**, and that mismatch is deliberate — renaming them cascades through saved settings, presets and captured-data keys. User-visible TEXT uses the game's term; identifiers keep upstream's.

| Code says                              | The game says     |
| -------------------------------------- | ----------------- |
| `heroes_tab.py`, `hero`                | Combatant         |
| `inventory_tab.py`, `piece`            | Memory Fragment   |
| `materials_tab.py`                     | growth stones     |
| `FRIENDSHIP_BONUSES`, `friendship_index` | Affinity        |
| `chaos_assault`, `assault_*`, `ASSAULT_SCHEDULE` | Sortie  |
| `dot_pct`, `dot_share`                 | the Agony share   |

The last row is the sharp one: the `DoT%` STAT is called DoT% in game and improves all three DoT types, while the damage TYPE the program calls DoT is only Agony. `docs/game_formulas.md` §3.4 is canonical.

Rename toward the game when adding user-visible text; never the other way, and don't "fix" an identifier to match.

## Frozen builds: `_MEIPASS` is read-only

- `_MEIPASS` is READ-ONLY in frozen builds. Anything that writes (settings, snapshots, `.defaults_sync.json`) must use `_user_data_dir()`, which returns `sys.executable.parent` when frozen, NOT `__file__`'s parent.
