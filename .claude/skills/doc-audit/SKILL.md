---
name: doc-audit
description: Audit the repo's prose — docs/, CLAUDE.md, .claude/rules/, skills, docstrings and comments — for staleness, contradictions, unfollowable references and guideline breaches. Use when the maintainer asks whether the docs are up to date, asks for a doc or comment pass, reports a doc disagreeing with the code, before a release, or when a convention has just been corrected and its old value may survive elsewhere. Covers what to grep for, which findings are false positives here, and what must never be deleted.
---

# Doc audit

The written guidelines are elsewhere and are not repeated here: `~/.claude/CLAUDE.md` (comment style, mechanism-not-output, no change narration), `CLAUDE.md` (what belongs in which file), `docs/repo_conventions.md` (`tasks.md`, `plan.md`, CHANGELOG, release notes). This skill is the **detection and judgement** half — how to find breaches, which apparent ones are not, and what a pass must leave alone.

## Order

1. **Contradictions first.** Every other improvement to a passage is wasted if two passages disagree.
2. **Then anything that moves a fact between files.** Editing prose that is about to be deleted is the one wholly wasted edit.
3. **Then staleness**, then references, then shape.

## The three failure modes that actually happen here

**A correction lands in one place only.** The most common real defect. A convention gets fixed in the code and the doc keeps the old value, or the reverse. When any convention, constant or target changes, grep the OLD value across `docs/`, `.claude/`, `CLAUDE.md` and the source before closing the task — not just the file you edited.

*Found this way:* `ui_spacing.md` priced a tooltip underline's horizontal overshoot at 1px for as long as the correction to 0 had been live in `spacing_audit.py`.

**A doc restates a value the code owns.** It then drifts silently. The fix is to name the constant, not to copy it better. A doc may hold a table's schema — what the columns mean, what a row must satisfy — never its rows.

**A reference points at the wrong file, or at nothing.** Ordinals into lists (`the second`, `the first three`) break when a row is inserted, with nothing failing. `` see `file.md` `` with no section is unfollowable. Worst and least visible: a constant cited against the file that IMPORTS it rather than the one that defines it.

*Found this way:* `SET_STAT_NAME_MAP` was cited against `optimizer/core.py` by two docs and by `sets.py`'s own docstring, sixty-nine lines above the definition.

## Sweeps

Cheap, and each has caught something. Run them over `docs/`, `.claude/**/*.md` and `CLAUDE.md`. **`past_plans/` is exempt from all of them** — it is an archive and its dates and `[IMPLEMENTED]` tags are the record.

| Looking for | Signal |
| ----------- | ------ |
| Change narration | `used to`, `previously`, `formerly`, `we now`, `renamed from`, `the old `, `an earlier attempt`, `for months`, `went unread` |
| Bug-history prose | past tense about the program's own behaviour; `which is why` right after a past-tense clause |
| Stale outputs | a digit next to `captured`, `snapshots`, `rows`, `readings`, `so far`, `ever`, `of the`; any `N/M` in prose |
| Unfollowable refs | `the second`/`the third`/`the first N` with no noun; `` see `*.md` `` with no `§`; `above`/`below` across a section break |
| Mirrored tables | a table next to `Stored as X in Y`, `single source of truth`, `this table is for documentation` |
| Dense sentences | over ~40 words; two or more of `—` `;` in one sentence |
| Headings that name nothing | `^#+ (What|Why|Where|How|Which|When)\b`; headings with ` and ` or a comma; pronouns |
| Emphasis inflation | count `^\*\*` per file against the heading count; above ~1:1 the bold marks nothing |

Two mechanical traps, both of which have produced wrong numbers:

- **A heading detector must skip fenced blocks.** `grep '^#'` counts shell and Python comments at column 0 inside code fences. Validate any detector against a file you have counted by hand before quoting what it returns.
- **Resolve backticked paths and identifiers against the tree.** `checks/check_instruction_files.py` does this for `CLAUDE.md`, `.claude/rules/` and `.claude/skills/`, but NOT for `docs/` — so a `docs/` path that names nothing has no guard and must be checked by hand.

## False positives in this repo

Do not "fix" these. Each has been mistaken for a breach at least once.

- **"Used to exchange for Chaos run rewards"** — that is *in order to*, not history. Read the sentence before matching on the word.
- **Dates that are evidence.** The wire's day-zero epoch, an observed reset time, a sample JSON timestamp. The rule bars narrating change, not recording a fact that happens to be a date.
- **A number a check pins.** `POTENTIAL_MAX_TOTAL`'s 45 is held in three places on purpose, one of them a check whose comment says so. Deleting it throws away a deliberate cross-copy. `grep -rn "<the number>" checks/` before touching any figure.
- **The `# spacing:` markers and `ui_spacing.md`'s contract tables.** A check parses them; density edits break the build. See the hard gate below.
- **A `past_plans/` entry that reads stale.** It is the record of a decision, not a description of today.

## Verify against the artifact, not the mechanism

The most expensive error available here, and it has been made: reading the code, seeing that it *would* keep a field, and concluding a snapshot *contains* it. Code that sweeps `event_*` tables into the snapshot does not mean any capture ever ran while such a table was being sent — zero of 113 archived snapshots carry one.

The same discipline in the other direction: **a passage that describes itself is a hypothesis.** A sentence saying "the code owns this table" is not evidence that it does. Open the constant and diff the columns; a doc table that adds a column the code has no field for is not a mirror.

When a claim cannot be settled without data, say so and leave both sites marked, rather than smoothing one into agreement with the other.

**Split a contradiction into clauses before resolving it.** A passage is rarely wrong end to end. One catalogued case was wrong in two clauses of three, and replacing the whole passage would have lost the true one.

## What must survive the pass

A density pass run without this gate removes the most valuable lines in the corpus.

1. **Negative imperatives naming a silent failure** — "Never test whether `potential_node_ids` is non-EMPTY", with the symptom that follows. This is the target register, not a violation of it.
2. **Load-bearing-code markers** — "that is not redundant", "Pinned by a check. Don't undo it." They exist because the next reader's instinct is to tidy the thing away.
3. **Failure-mode sentences** — "the only symptom is…", "looks exactly like…". These are how a reader recognises the bug. Trim the anecdote around them; keep the symptom.
4. **Precedence and ordering lists.** Directly executable, cheapest content per token.
5. **Naming contracts where three places must agree**, and every pointer to a source file or a check. Add anchors; remove none.
6. **A stated method for re-measuring something.** The method stays even when the resulting table goes.

## Hard gate

**`docs/ui_spacing.md` is parsed by two checks**, which navigate it by exact heading text and compare its tables against `RULE_*` constants and the `# spacing:` comments. Two of its headings are exactly the shape the heading rule says to rewrite. Do not.

**`grep -rn "<the literal heading or table text>" checks/` before rewriting any heading or table in any doc.** This is the one place a prose edit can fail the build. A coordinated rename is possible — the check names the constant to update — but it is a code change, not a doc edit.

## Reporting

Findings with a `file:line` anchor and the proposed rewrite. Separate what was fixed from what needs the maintainer: a contradiction that needs a capture to settle, a decision about who owns an unowned file. Say plainly when a sweep found nothing — a clean sweep is a result, and the next audit should know which ones are worth keeping.

## Related

- `docs/repo_conventions.md` — CHANGELOG and release-notes register.
- `.claude/skills/release/SKILL.md` — runs this pass as one of its steps.
- `checks/check_instruction_files.py` — the path guard, and what it does not cover.
