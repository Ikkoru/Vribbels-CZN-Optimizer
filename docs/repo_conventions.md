# Repo conventions

How `tasks.md`, `plan.md`, `CHANGELOG.md` and `RELEASE_NOTES.md` are kept. Nothing here affects the program.

## `tasks.md` — the triaged backlog

Taxonomy: **1a/1b** (bugs — fixable without / needing maintainer input), **2a/2b** (improvements, likewise), **3** (big changes), **TBD** (parked, with bug / improvement / change subsections).

Completed items are REMOVED, not struck through, and answered questions go with them. Parked ideas move to TBD. An empty section keeps its heading and reads `*N/A*`.

## `plan.md` — created when a task needs planning

Lives at the repo root while the work is live. The test of a plan is whether someone else can pick it up and follow it. The usual shape serves that: constraints → options with pros/cons → recommendation → phases. Acceptance criteria, a decisions log and per-phase status tags are available structure, not requirements.

- **Reference data does not belong in a plan.** A table the CODE points at outlives the plan that produced it, and archiving the plan takes the table out of reach. Put it in the matching `docs/` file and link.
- **Finished phases collapse.** Leave the ruling and the reasoning; drop the status tables and per-file bookkeeping.

When the work finishes the file moves to `past_plans/<topic>.md`, keeping the measurements and the reasoning behind rejected options. `past_plans/` is an archive: its dated entries and `[IMPLEMENTED]` tags are the record, not staleness to clean up.

## `CHANGELOG.md` — Keep a Changelog format

Active work goes under the top `## [X.Y.Z] - unreleased` section as it lands: new features → `### Added`, polish → `### Changed`, bug fixes → `### Fixed`.

**Summarize at USER-FACING level**, not implementation detail. "Memory Fragments tab: the Highest Potential column names the preset it scored under" — not "refactored `_presets_for_highest_gs` to return tuples".

**Write the entry in that register when it LANDS.** An entry written from the implementation and rewritten at release costs the rewrite and loses detail nobody can recover months later. Three habits carry most of it: no figure that only argues the change was worth making, no internal mechanism a user cannot act on, and the game's word for anything the UI names.

At release, `unreleased` is replaced by a short release name (`- Multi-core`), which is also when `version.py` is bumped. Released entries record what shipped and are never retro-edited, even where their numbers no longer describe the current build.

**The CHANGELOG is the complete record.** Nothing is omitted for being small, internal or invisible — that filtering happens once, in the release notes.

## `RELEASE_NOTES.md` — what a player is told

Gitignored, rewritten per release, and pasted into the GitHub release. It is **not** a shorter CHANGELOG: it is the subset a player needs, in their words.

- **Cut anything self-evident from the UI.** Opening the tab teaches it faster than a sentence can. The exception: keep a line where the absence of something reads as a bug — "the Seasonal Shop shows no rates" stays for that reason alone.
- **Cut what a player cannot act on.** Internal mechanism, exact figures, timing, control names, the reason a thing works the way it does.
- **What and where, in that order.** "Archive info and settings are in Setup & Settings → Settings", not a tour of the panel.
- **No reason-giving at all**, including the factual kind. The CHANGELOG carries the why.
- **A fix to something never really released does not get an entry.** Where a release shipped a feature marked unfinished, that feature's fixes belong to the CHANGELOG alone. Judge it against what the earlier release SAID, not against the commit history.
- **Group by tab**, and give a new tab one line saying what it is for.
- The header names one or two themes, not every area touched.

The register is a player's, not a maintainer's: second person, contractions, and a light touch are all correct here and wrong in the CHANGELOG.

## Keeping the settings docs in step

Any change to `defaults_sync.py` or the manager APIs lands in `docs/settings_architecture.md` (mechanism) and, if it changes what the maintainer DOES, `docs/how_to_maintain_default_settings.md` (workflow). Don't restate either in the other.
