# doc-audit overlay: Vribbels CZN Optimizer

What the kit's `craft:doc-audit` needs to know about this repository; the skill itself is in the kit. This file holds only what differs here.

## Scope

- **Prose**: `docs/`, `.claude/**/*.md` and `CLAUDE.md`; in `CHANGELOG.md`, only the unreleased section, since narrating change is what the file is for and released sections are edited only to fix them.
- **Docstrings and comments**: `Vribbels/` and `checks/`. The false positives below were all found in code.
- **Archive, exempt from every sweep**: `past_plans/`. Its dates and `[IMPLEMENTED]` tags are the record.
- **Published**: this repository (`origin` is public on GitHub), so the privacy sweep runs first.

## The repository's own checks

- `checks/check_instruction_files.py` resolves every backticked path in `CLAUDE.md`, `.claude/rules/`, `.claude/skills/` and `docs/`, but not identifiers, and not paths in code comments: a constant or a function a doc names has no guard.
- Invocation modes are in `.claude/settings.local.json` (`skillOverrides`): the `release` skill is manual only.

## Hard gate

`docs/ui_spacing.md` is parsed: `check_spacing_markers.py` and `check_spacing_registry.py` navigate it by exact heading text and compare its rules, vocabulary and tables with the code, so a renamed heading fails a check. Before editing a heading in any doc, `grep -rn "<heading text>" checks/`; the same grep covers a table's text. **Two of its headings are exactly the shape the heading sweep says to rewrite: leave them.** A coordinated rename is a code change, not a doc edit.

## Last pass, queue

- The last audit is the commit whose subject starts `Doc audit`: `git log --grep '^Doc audit' -1`.
- The rule-misfire queue is `_tmp/skill_notes.md`.

## False positives here

Each has been mistaken for a breach at least once.

- **"Used to exchange for Chaos run rewards"**: *in order to*, not history.
- **Dates that are evidence**: the wire's day-zero epoch, an observed reset time, a sample JSON timestamp.
- **A number a check pins**: `POTENTIAL_MAX_TOTAL`'s 45 is held in three places on purpose, one of them a check whose comment says so. `grep -rn "<the number>" checks/` before touching any figure.
- **The `# spacing:` markers and `ui_spacing.md`'s contract tables**: a check parses them (*Hard gate*).
- **A digit inside a name**: `Potential 7`, `Slot 5`, `Level 61`, `Season 8`. A capitalised word before the digit is the tell.
- **A `past_plans/` entry that reads stale**: the record of a decision, not a description of today.

## Found this way

The generic failure modes, as they happened here:

- A correction in one place: `ui_spacing.md` priced a tooltip underline's horizontal overshoot at 1px for as long as the correction to 0 had been live in `spacing_audit.py`.
- A constant cited against its importer: `SET_STAT_NAME_MAP` was cited against `optimizer/core.py` by two docs and by `sets.py`'s own docstring, sixty-nine lines above the definition.
- Measuring part of the corpus: `event_bartender_entities` is absent from every archived snapshot and present in most loose ones, because the archive predates the capture change.
- A target against a reading: `ui_spacing.md`'s rules table is targets and every row stays verbatim; its `Gap now` column is readings and belongs to `docs/spacing_baseline.json`. Where the doc names the constant beside a target without restating its value, leave it.
- Comments that assure: "DEF% only appears on slot 6 (game data confirmed)", in `constants.py`.

## Related

- `docs/repo_conventions.md`: the CHANGELOG and release-notes register.
- The `release` skill runs this audit as one of its steps.
