---
name: spacing-audit
description: Read or run the UI spacing audit — the screenshot-based measurement of every registered gap. Use when the maintainer pastes audit output, reports a gap as off, or mentions a baseline CHANGED or MISSING line; when a rendered distance needs confirming in pixels; when the baseline is being frozen; or when asked to run one. Covers how to read the table, what a miss resolves to, what registering a new gap obliges, and the preconditions and launchers for a run.
---

# Spacing audit

The procedure only. The mechanism — what each rule means, what the audit can and cannot see, the marker vocabulary — lives in `docs/ui_spacing.md`, and the entries themselves in `Vribbels/ui/spacing_registry.py`.

**The maintainer runs audits on their own judgement and hands over the output**, so reading a table is the common case and asking for a run is the rare one. Start at *Reading the table*.

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

**A reading can move without any distance moving.** The scan meets INK, so what is leftmost or lowest inside a panel can change when a widget is added, or when a frame that fills its parent paints its background where the panel's own showed. Before reaching for a padding constant, measure the structure: build the tab against a mapped window at alpha 0 (the `check_tabs_build.py` recipe, and `_hide_until_ready` is the app's own way to be mapped and invisible) and compare `winfo_rootx` against the panel's. A lever nudged to chase a reading that never moved is the mistake this catches. Glyphs do it too, and not by overshooting: a leading stem's first column is often dark enough for the ink threshold to pass over — invisible on the background, and rightly ignored — so most panels read a pixel further in than their content sits. A panel whose leading glyph does NOT have that dim column reads a pixel nearer its edge than its neighbours, for a lever nobody touched.

## Adding an entry

New rows carry obligations the audit itself will not remind you of, and `checks/check_spacing_registry.py` fails until they are met:

- **Prefer a rule to a `unique`.** Read the rules table in `docs/ui_spacing.md` before inventing one — `element and its label ↔ element and its label` already prices two label+value pairs side by side at 8px, and a unique for a distance a rule covers is a second vocabulary for one idea.
- **A `unique` needs both halves.** A `unique -- <what> --` marker in the widget code, spelled identically in the doc's uniques table, AND an entry measuring it — or a row in that table carrying **—** and a reason it is not tracked, with no entry at all.
- **A new entry is provisional.** Add its name to `AWAITING_FIRST_READING` so the row prints yellow: its target came from the rules table rather than from anything anyone has seen. It comes out the moment a run confirms it.
- **A distance that deliberately misses its rule is an `exception`**, registered at what the screen actually shows, with the reason at the site. Tracked at its real value, a later drift still reports; left out, it cannot be told apart from one.

## Freezing

Freeze only once the maintainer has confirmed the current readings are right. The freeze overwrites `docs/spacing_baseline.json` wholesale, so freezing over an unexplained `CHANGED` line buries it permanently.

It prints `baseline written: <n> gaps`, and before that a warning where two entries share a NAME:

- `baseline: N row(s) share a name with another and only one of each is watched -- <names>`

The baseline is keyed by name, so a shared one collapses to whichever was measured last and the other stops being compared — silently, because both still print in the table. A scenario row replacing its default-state twin is the usual cause. Rename one of the pair so both are watched; the registry's own naming (`<title> [element override]: title -> first element`) is what that looks like.

## Related

- `docs/ui_spacing.md` — the rules, the ledger, what the audit cannot reach, and the uniques table.
- `.claude/rules/ui.md` — the `px()` rule and the `# spacing:` marker conventions, loaded when a UI file is read.
- `Vribbels/ui/spacing_audit.py` — the measurement code; `run_audit` is the entry point.
- `Vribbels/ui/spacing_registry.py` — one entry per tracked gap.
- `past_plans/UI_unionization.md` — why the spacing work took this shape.
