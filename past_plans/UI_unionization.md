# plan.md — Spacing: make it verifiable instead of remembered

## Why

A rendered gap is `ancestor padding + pack/grid pad + the child's own internal inset + the font's line box`, and the last two are not derivable from the source. So the source cannot be read to find out what is on screen, and a comment recording what WAS on screen goes stale the moment an ancestor moves.

Two problems fall out of that:

1. **Verification is manual.** Only the maintainer can measure, one gap at a time, by eye.
2. **Couplings are invisible.** A padding value is often shared — by an ancestor, a container, or a ttk style — so a correct change to one panel silently moves another.

This plan fixes (1) with a tool and (2) with a written coupling ledger, then uses both to finish the outstanding nudges.

## Rejected alternatives

- **A `spacing.py` of named constants.** The constants would be TARGETS but the numbers at the call sites are LEVERS, and they differ — a 3px title gap is written as `padding=(5, 6, 5, 5)`. A constant named for the target sitting in a slot that holds a lever invites exactly the wrong inference. Targets belong in the audit's expectations, not in widget code.
- **Per-site comments recording the measured value.** Records an output; goes stale silently when an ancestor moves, and a stale comment is worse than none because the next pass trusts it.
- **Golden-image regression tests.** A whole-image diff fails on font hinting, DPI, theme and any unrelated content change, so it reports noise instead of spacing. Phase 1 screenshots in order to MEASURE named gaps, which is not the same thing.
- **Font-metric estimation of glyph extents.** Tk's `ascent`/`descent` bound the LINE BOX, not the glyphs, and the difference is a per-font constant needing hand calibration for every face and size. Measuring pixels makes it unnecessary.

## Phases 1 and 2 — complete

The audit (`ui/spacing_audit.py`), the registry (`ui/spacing_registry.py`), the scenario mechanism, the ledger, the marker pass across all six tab files plus the style block, and the prose sweep across every `.md` and docstring. Reference material moved to `docs/ui_spacing.md`, which is now canonical for all of it.

Two conventions that came out of it and are worth not relitigating:

- **The target lives on the ENTRY, not the rule** — but it is the same number for every entry obeying one rule. It was not always: the reference point is the painted glyph, so a title with a descender read tighter than one without, and the two carried different targets. Correcting the READING to the baseline instead is what collapsed them, and it is the better place for it: the difference is a fact about the font, not about the panel.
- **Panels are located by their visible title**, not by attribute — most are locals, and storing each on `self` purely to measure it would touch six files for no functional reason. Renaming a title drops it from the audit; the baseline reports that as a missing entry.

## Phase 3 — Remove the couplings that caused the trouble

**3.0 Re-measure by hand. Non-critical.** A baseline frozen from the tool cannot catch the tool becoming confidently wrong; only a human reading can. That does not need a file of tables, it needs a habit:

> **After any change to `spacing_audit.py`'s measuring code, re-read two or three gaps by hand before trusting a run.** Include one text panel, since those are measured inside the fill and break differently.

`Element override (Unknown character)` no longer needs a fresh reading. A parenthesis sits exactly 1px above a descender at Segoe UI 9, and the reading is corrected to the baseline before it is compared, so its target is the same plain 5 as every other title's. Nothing in the registry is `inferred`, and the only `exception` target is Setup Status' left edge at 7.

**3.1 A shared tab-header helper. Done.** `ui/utils/tab_header.py`. Gear Score, Capture and Setup hand-rolled `heading + subtitle on one line` across five values, and no two agreed on three of them; Gear Score was the outlier on heading top and subtitle bottom, Setup on the heading's leading edge. One set of numbers now, with `x_trim` the only per-tab argument — Capture nests one container deeper, which genuinely starts its heading further right. The three heading-to-subtitle gaps are registered at the rule's 14px, so the helper's numbers are measured rather than trusted.

The Combatants detail pane's `Select a combatant` is a fourth 14pt heading with its own negative padding but is NOT in scope — it has a control group beside it, not a subtitle.

**3.2 A shared All/None button row helper. Done.** `ui/utils/all_none_row.py`, across Slots, Sets, Main Stats and Exclude. No two of the four agreed on all three of the row's numbers, and the row gap split two against two — not even a majority to be wrong about. Both of the row's gaps are registered per panel, because the panels' own paddings differ and one lever renders a different inset in each.

**3.3 The Combatants `Character` panel. Done.** It was a stack of Labels and a Frame grid; it is now one `tk.Text` built like `Partner` — `padding=0` on the LabelFrame, the inset on the widget's own `padx`/`pady`. No scrollbar, unlike `Partner`: this card's content is a fixed number of lines and the frame is sized to hold them, where `Partner`'s prose has no bound.

The stat columns were the one thing that did not carry over. They were right-aligned by a fixed `width=` per value Label, which a Text has no equivalent for, so they sit on right-aligned TAB STOPS computed from font metrics in `_compute_and_apply_fixed_sizes`. `HERO_STAT_VALUE_MAXIMA` sizes them, stating the widest value each stat can hold as the STRING rather than a character count.

The panel also had to join `TEXT_PANELS` in `ui/spacing_registry.py`: its entries were measured by scanning inward from the border for a background pixel, and a text panel deliberately leaves none.

## Phase 4 — The outstanding nudges, converted to measurements

The list read: *preset dropdown down 1; `Character` and `Partner` title and top edge up 3, bottom edge up 1; `Character` text up 3 and right 3; Equipped Memory Fragments content top −3.* It was written before anything could measure, and it is not safe to apply now.

**Three of the gaps it names are tracked and ON target.** `Character` and `Partner`'s title gaps, and Equipped Memory Fragments' — all at the rule, all frozen in the baseline. "Title up 3" and "content top −3" would take four confirmed gaps off their rule to satisfy a reading nothing can reproduce.

**Two more left the list earlier** for the same reason: the gear cells' left, once they were read at the content-frame rule's 4px, and the `minlvl_row` / `offelem_row` pair, which became `unique` markers at 6px and 4px because three rows seating their content at different insets cannot share one row-pitch number.

**What was left is registered and measured.** Seven entries — `Character` and `Partner`'s TOP insets, `Character`'s RIGHT, the same top inset on the three other text panels, and the gap from the `Assign preset to` caption to its dropdown — all on target now.

Of the original readings, one survived and two did not. `Character`'s text wanted moving up by **1**, not 3. Its right was **already correct**; the 7px the tool reported was the tool measuring past a text widget that does not fill its frame. The five top insets each took a different pad, because the line box above a first glyph differs per font — 0 for the Segoe UI 11 panel, whose line box supplies the whole inset by itself.

BOTTOM is deliberately absent. A text panel's prose stops where it stops, so the space under it is slack, not an inset — the standing exception already says so for `Character`.

**Two rule targets changed, propagated, and the panels have followed them.** `explanation text -> the controls it explains` went 10 → 8px and `border edge -> first non-button element` 6 → 5px. The second reaches furthest: 43 entries carry that rule and every one is on target.

**Four more moved later, once every rule had instances to judge it by:** `label ↔ its element` 4 → 5, `border edge -> first non-button element` 5 → 4, `checkbox/slider ↕ checkbox/slider rows` 7 → 6, and `explanation text -> the controls it explains` 8 → 7. Two entries came onto target without being touched, the checkbox indicator's 5 stopped being an exception, and four panels needed a negative Label inset because their frame padding was already 0 where the rule now asks for one pixel less.

Both are a single number in the table now. They read as a pair — 5px, or 8px without a descender — until the reading was corrected to the baseline instead, which is what let the conditional go.

The `minlvl_row` / `offelem_row` pair left this list rather than moving: the two gaps are `unique` markers now, at 6px (label → spinbox) and 4px (spinbox → checkbox), because the three rows seat their content at different insets and one row-pitch number cannot serve both.

## Ordering

All four phases are done, and so is the registration work they led to: about 68 gaps the maintainer had read by hand, taken in batches by resolver shape and nudged onto their rules. One reading was never registered (Equipped MF's substat columns, which are tab stops inside a Text widget rather than widgets) and one number is parked. `paused_task.md` holds what is left, which is no longer registration.

**The thing worth carrying forward is the shape of the failures.** Roughly one resolver in six measured the wrong thing, and not one of those was visible from its number — a scan reading panel TITLES reported a constant 3, another stopping inside a spinbox's fill reported 0, and a pitch reported as the most COMMON gap certified three panels clean while a whole group of their rows sat 4px tight. Each looked like an ordinary UI defect, and nudging to satisfy any of them would have made the app worse. What caught them was recording what the eye read beside what the tool read, and treating a disagreement as the tool's fault until shown otherwise.
