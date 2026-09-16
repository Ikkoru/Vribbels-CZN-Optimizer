---
name: spacing-audit
description: Run and read the UI spacing audit — the screenshot-based measurement of every registered gap. Use when asked to run a spacing audit, to check a rendered gap in pixels, to freeze the spacing baseline, or when a UI change needs its distances confirmed on screen. Covers the preconditions, the launchers, how to read the table and what to do with a miss.
---

# Spacing audit

The procedure only. The mechanism — what each rule means, what the audit can and cannot see, the marker vocabulary — lives in `docs/ui_spacing.md`, and the entries themselves in `Vribbels/ui/spacing_registry.py`.

## Before asking for a run

A run costs the maintainer's attention: it puts the app on their screen and they have to hold the window still. Spend the headless checks first, because two of them catch registry faults without a run:

```bash
python checks/run_all.py
```

`checks/check_spacing_registry.py` enforces every entry against the targets in the doc's table, including that a miss carries a marker naming the rule it breaks. `checks/check_spacing_markers.py` checks the `# spacing:` markers themselves. A fault either of those can see is not worth a screenshot.

**Never launch it unasked.** It needs the maintainer at the keyboard — ask, and wait for them to say they are ready.

## Preconditions the maintainer holds

State these when asking:

- the app window unobscured and frontmost;
- the pointer off the window — hover repaints, and the repaint gets measured;
- a snapshot loaded, so the data-driven panels exist to be measured.

## The three launchers

| Want | Run |
| ---- | --- |
| Only the rows that miss their target | `zRUN Spacing Audit.bat` |
| Every row, including the ones on target | `zRUN Spacing Audit Verbose.bat` |
| Rewrite `docs/spacing_baseline.json` | `zRUN Spacing Audit Freeze.bat` |

Each sets `VRIBBELS_DEV=1` and passes `--spacing-audit`, `--spacing-audit-verbose` or `--spacing-audit-freeze` to `Vribbels/czn_optimizer_gui.py`. A normal launch never imports the audit.

## Reading the table

- **A short run is a good run.** The default prints only misses, so a clean pass is a handful of lines.
- **`axis` is `<>` or `^v`**, never arrows: the console is cp932 and one non-ASCII character raises before the table reaches the screen.
- **Dark yellow means provisional** — registered but never confirmed by a hand reading. It clears once a reading agrees.
- **The note column** says `exception` where the site deliberately misses its rule and carries a marker saying so, or `inferred` where the rule applies but its number is carried across from elsewhere. An ordinary row says nothing there.
- **A `SKIP` row measured nothing.** It looks like a pass at a glance. A resolver whose class name no longer matches any widget is the usual cause, and only reading the run closely finds it.

After the table come the baseline lines, from `compare_baseline`:

- `baseline: no change` — nothing moved since the freeze.
- `baseline CHANGED <name>: <was> -> <is>` — the distance moved. Either the change was intended, or something re-plumbed it.
- `baseline MISSING <name>` — the entry stopped being measured. A renamed panel title is the usual cause: the audit finds panels by their visible title, so renaming one removes it from the run silently, and this line is what catches that.

An entry the baseline has never seen is not reported; it prints yellow in the table instead.

## What to do with a miss

Doc-first, as everywhere in this repo. **A distance that does not answer to its rule is an `exception` or a `unique`, never an unexplained number.** So a miss resolves one of three ways:

1. the code is wrong — fix the geometry call, keeping every hardcoded distance inside `px()`;
2. the rule's target is wrong — fix `docs/ui_spacing.md` first, then the registry entry;
3. the site is a deliberate departure — add the `exception` marker at the call site naming the rule it breaks, and register it as one.

Take the maintainer's own measurements over the audit's when the two disagree and they have measured by hand: several of the audit's reference conventions were corrected that way. Readings are capital-to-capital, and gaps are counted background pixels.

## Freezing

Freeze only once the maintainer has confirmed the current readings are right. The freeze overwrites `docs/spacing_baseline.json` wholesale, so freezing over an unexplained `CHANGED` line buries it permanently.

## Related

- `docs/ui_spacing.md` — the rules, the ledger, what the audit cannot reach, and the uniques table.
- `.claude/rules/ui.md` — the `px()` rule and the `# spacing:` marker conventions, loaded when a UI file is read.
- `Vribbels/ui/spacing_audit.py` — the measurement code; `run_audit` is the entry point.
- `Vribbels/ui/spacing_registry.py` — one entry per tracked gap.
- `past_plans/UI_unionization.md` — why the spacing work took this shape.
