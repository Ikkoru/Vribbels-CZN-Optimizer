# UI spacing

Read before changing any padding, margin or layout value in the tabs. Threading and startup are in `ui_runtime.md`.

A rendered gap is `ancestor padding + pack/grid pad + the child's own internal inset + the font's line box`, and only the first two appear in the source. **So the source cannot be read to find out what is on screen, and rendered pixels must never be predicted from padding values.** Hence the four parts below: the rules say what a gap should measure, the markers say which value is a lever for which rule, the ledger says what else that lever moves, and the audit measures the result from a screenshot.

## The rules

Target: **4px** between any two content frames, and between a content frame and the window edge. Achieved by giving each container 2 and each content frame inside it 2.

Every other target is measured on screen: from the first background-coloured pixel after one element's painted edge to the last one before the next element's, counting both ends, with no hover effect showing.

Where text is one end of the gap, the reference is the BASELINE below and the CAPITALS above — fixed points, not whatever the string happens to contain:

- **Text above, element below**: from the BASELINE. Ignore descenders; a `g` hanging below it does not move where the text sits.
- **Element above, text below**: to the top of the CAPITALS. Where an ascender reaches higher than a cap, ignore it — the capitals are the line's top for measuring purposes, whatever paints highest.

**This holds for every vertical distance involving text, with no exceptions.** Where a string has no capital at all, the reference below it is the baseline of an ordinary non-ascender.

**Two ways to obey it, and the second is better where it is available.** The correction tables below restate a reading taken from the ink as one taken from the reference — which needs a number per glyph class, per face. Narrowing the SCAN to a single capital needs none: both ends of the reading land on the reference by construction. `_capital_row_pitch` and the text panels' top inset do that, and they do it because their strings defeat the tables — `[OK] Python 3.13` opens on a bracket that clears the cap AND drops below the baseline, and Segoe UI Variable Small's ascenders clear its capitals where Segoe UI's do not.

Prefer narrowing the scan wherever the string can be indexed to a capital. Prefer the tables where it cannot — a title found by its own words, where the audit has the string but not a font to measure it in.

**The audit sees INK, so it corrects what it sees.** A descender hangs below the baseline and a tall ascender clears the capitals, so a raw reading is tighter than the rule asks by however far the string's glyphs overshoot. `ui/spacing_registry.py` adds that back at the point of measurement.

**The correction always ADDS, whichever end of the gap the text is on.** Ink overshoots INTO the gap in both directions — a descender hangs down into a gap below the text, an ascender rises up into a gap above it — so the raw reading is short either way. Treating the two as opposites is the one mistake this is easy to make, and it costs 2px: one for the correction going backwards and one for the target having moved to meet it.

| Overshoot | By | Where |
| --------- | -- | ----- |
| a true descender below the baseline (`g j p q y`) | 3px | any body size |
| a parenthesis below the baseline | 2px | any body size |
| an ascender or tittle above the caps (`b d f h i j k l`) | 1px | **Segoe UI 14 bold only** |

`i` and `l` are measured; the rest of that class is assumed to match, and `t` is NOT in it. At Segoe UI 9 and 11 the whole class tops out level with the capitals, so only the tab headings need the correction.

**Correcting the reading rather than the target is what keeps a target one number.** A target per glyph class says the same fact twice — that the tool reads a different reference point than the rules name — and puts a conditional in every rule's target column.

One case has no correction and cannot get one: a string with **no cap and no ascender** (`someone`, all lowercase) tops out at the x-height, 2-3px lower, which looks exactly like a gap that is too wide. No title in the app is one, and a title that became one would more likely be a typo than a decision — so the registry refuses to guess rather than deriving something, and the refusal names the reason.

| Gap                                                   | Target                                      | Marker                                          |
| ----------------------------------------------------- | ------------------------------------------- | ----------------------------------------------- |
| Content frame → content frame, and → the window edge  | 4px                                         | `content frame -> content frame`                |
| Tab list above → topmost element of the tab           | 6px                                         | `tab list -> first element`                     |
| Header subtext                                        | on the header's own line, not stacked below | `header subtext`                                |
| Border edge → first non-button element inside it      | 4px, all edges                              | `border edge -> first non-button element`       |
| Between two adjacent buttons                          | 4px                                         | `button -> button`                              |
| Border edge → internal button                         | 3px, on every edge a button meets           | `border edge -> button`                         |
| Checkbox block above → its All/None button row below  | 5px                                         | `checkbox block -> All/None row`                |
| Between spinbox rows                                  | 3px                                         | `spinbox row -> spinbox row`                    |
| Between non-tall rows (checkboxes, sliders)           | 6px                                         | `checkbox/slider ↕ checkbox/slider rows`        |
| Between text-only label rows                          | 10px                                        | `label row -> label row`                        |
| Small division between specific checkbox rows         | 12px                                        | `checkbox row -> checkbox row (small division)` |
| Title above, frame below                              | 5px                                         | `title above, element below`                    |
| Explanation text above/below the controls it explains | 7px                                         | `explanation text -> the controls it explains`  |
| A label left/right of the element it labels           | 5px                                         | `label ↔ its element`                           |
| A heading and the element beside it                   | 14px                                        | `heading ↔ element`                             |
| Between two label+value pairs, side by side           | 8px                                         | `element and its label ↔ element and its label` |
| Checkboxes above, UNRELATED checkboxes below          | 20px                                        | `checkboxes -> unrelated checkboxes`            |
| Panel above, an unrelated label beneath it            | 10px                                        | `panel ↕ unrelated label`                       |
| Between rows of a config panel                        | 12px                                        | `config panel row ↕ row`                        |
| Between groups of tab-wide controls                   | 16px                                        | `control group ↔ control group`                 |

These are exact targets, not floors: a value above target needs bringing down as much as one below it needs raising.

**A panel whose content runs to its border cannot be measured across its middle.** The border scan walks inward from the frame's box looking for the first background pixel, and a panel filled edge to edge along that line has none — so the scan hits its cap and every reading on that panel comes out short by however far it walked. The Gear Score preset list running flush to three borders cost the whole panel 3px that way. The scan tries the middle first and falls back to other lines, any one of which reports the same border where there is background behind it.

Where a side has background on NO line — the list spans that panel's full width, so every column at the bottom is filled — there is no transition to find at all, and the scan cannot answer however many lines it tries. A frame's border is one width, so that side takes it from a side that did answer, and the reading says it was inferred rather than passing for a measurement.

**A glyph's ADVANCE and its INK are not the same width, and the difference is per string.** `font.measure` returns the advance — what Tk reserves to lay the next character out — while the audit reads painted pixels, and a glyph's antialiased edge fades rather than stopping. So two strings measured identically can render a pixel apart, and the same column formula lands on 4 for one and 5 for another.

It shows up as a single pixel, in whichever column a formula sizes from a measured string: the ATK/DEF row's name column wanting one more than the damage rows', or `4pc` sitting a different distance from its indicator than `2pc`.

**`FRINGE_LIGHTNESS` is what closed most of it.** Counting a column as ink only past a lightness threshold puts the ink edge where the eye puts it, which is usually where the advance is — see "What the audit counts as ink". A pixel that survives that is a real difference between two strings, and a per-site constant for it would tie a number to today's text.

**A grid `minsize` is a FLOOR, not a width, and a fixed-width label's slack lands on the side its anchor points away from.** Two ways a column that looks pinned is not:

- The column still grows to its widest cell, and a `ttk.Label` asks for its ink PLUS the style's inset — 4px here. A floor set to the widest INK is outgrown by the longest label, which then sets its own column while the shorter rows keep the floor. The rows stop lining up and only the longest one's gap looks wrong.
- The same floor on a column whose text CHANGES is outgrown whenever the text reaches its widest, and the pixels come out of whatever shares the row: a readout column pinned to `100%`'s ink made every slider beside it visibly shorten going from 99% to 100%. A floor has to clear the widest REQUEST, not the widest ink.
- `anchor=tk.E` on a `width=` label puts its slack on the LEFT. Where that is the side a rule measures, the slack is in the gap. It has cost a `DEF` label 4px against its slider, a percent readout 2 against its own, and a set count 4 against its set name — three panels, one cause. `ui/utils/label_width.py` is the fix and states the conditions; a label pinned by a column must drop its own `width=` or it brings the slack straight back.

**A gap to a right-aligned readout is only a distance at its widest value.** The Optimizer's percent readouts are fixed-width labels with `anchor=tk.E`, so a short value leaves its slack on the LEFT — the side the gap to the slider is measured on. `0%` is 16px of ink and `100%` is 28, and the gap moves by exactly that 12 as the slider travels. The audit's `max_readouts` scenario fills them before measuring, which is the same convention as measuring a column from its LONGEST label.

That scenario writes to the app's own variables, and is only safe because no combatant is selected at startup — every per-combatant save no-ops while `_current_res_id` is None. `checks/check_optimizer_starts_unselected.py` holds that invariant.

**Moving a label's ink down does not close the gap below it.** Anything spent above a packed widget — a leading `pady`, or internal TOP padding, which grows its box downward — drops the ink and drops everything packed after it by the same amount. The gap above changes; the gap below is untouched. Reaching a gap BELOW text takes the label's trailing pad, the next widget's leading pad, or a negative BOTTOM padding.

This bites where one label carries an entry on each side of it, because the two gaps look like they trade against each other and they do not. Assuming they did cost a run.

### Which rule wins — PROXIMITY, and this is untested

**Where two rules could govern one gap, the nearer element decides.** Report every case that turns up, so the ruling gets tested against more than the one that prompted it.

Two stacked panels are the case that prompted it. Side by side, both ends of the gap are borders and `content frame -> content frame` governs. Stacked, the lower panel's topmost ink is its TITLE, drawn above its own border — so what sits across the gap is text, the text rule is nearer, and `panel ↕ unrelated label` governs at 10px. That title belongs to the panel BELOW, so relative to the panel above it is unrelated text, exactly what the rule describes.

The consequence is real: those pairs were built on the content-frame rule's 2+2 pads and read 7, so meeting 10 means a stacked pair's pads stop matching a side-by-side one.

**The 10 serves two shapes.** A panel with the next panel's title beneath it, and text — a tab heading, a header control — with a panel beneath that: the rule names text beneath a panel, and a heading above the first panel on its tab is the same distance seen from the other side. Fourteen sites are registered under it and all fourteen are on 10.

### Markers

The **Marker** column is the canonical spelling, in both directions: the widget code carries `# spacing: <marker>` on the lever's line, and `ui/spacing_registry.py` holds the same strings as `RULE_*` constants. A comment cannot import a constant, so this table is what both copy from. `checks/check_spacing_markers.py` compares all three.

| Marker                                       | Means                                                          |
| -------------------------------------------- | -------------------------------------------------------------- |
| `# spacing: <rule> -- <suffix>`              | this value is a lever for that rule                            |
| `# spacing: exception -- <rule> -- <suffix>` | that rule applies here and is deliberately not followed        |
| `# spacing: unique -- <what> -- <suffix>`    | deliberate, and no rule will ever cover it                     |
| `# spacing: TBD -- <description>`            | deliberate, no rule yet, awaiting a ruling                     |
| `# spacing: out of scope -- <why>`           | outside what the rules cover, marked so it reads as a decision |

`<suffix>` is `<elements> <orientation>`, below, and always ends the line.

`exception` names the rule it breaks, in the Marker column's spelling, with the reason on the lines below — grepping a rule has to surface its own exceptions. `unique` has no rule to break; both must name their subject precisely enough that grep finds one site and not its neighbour. Padding doing genuinely unrelated work stays unmarked.

**A `unique`'s `<what>` is also its key in the registry**, so it is spelled in three places rather than two — the marker, "The uniques, as a table" below, and the entry that measures it. Precision in naming one stopped being a style preference when that happened.

A `TBD` gets a row in "The unruled rows" below, description copied verbatim so the two match with grep. They are judged as a set, not one at a time.

**Markers are matched a LINE at a time**, so one must fit on a single line whatever its length. A marker wrapped onto a second comment line is truncated, and greps for the full text find nothing.

### The marker suffix

Every marker carries a suffix naming the two elements and the orientation of the particular gap:

```
# spacing: <rule> -- <elements, comma separated> <↔, ↕ or ↔↕>
# spacing: exception -- <rule> -- <elements> <↔, ↕ or ↔↕>
# spacing: unique -- <what> -- <elements> <↔, ↕ or ↔↕>
```

**Why:** it makes a rule SPLIT cheap — if `label ↔ its element` ever needs separating by orientation, the instances are already tagged — and it makes the set of sites obeying a rule greppable instead of listed by hand, which is the duplication that kept going stale.

The elements are written in layout order — top-to-bottom for `↕`, left-to-right for `↔`. Three conventions make it work rather than decay:

- **The orientation is always written**, even where the rule's own name already carries an arrow. Optional means `grep "↕"` returns a partial answer that looks complete, which is the failure the whole marker convention exists to prevent.
- **A lever that acts in both directions is written `↔↕`.** A frame's `padding`, a `ttk` style inset and a symmetric `padx`+`pady` all reach every edge at once; one arrow would drop the site out of the other arrow's grep.
- **The element words come from a fixed vocabulary**, below, and the check rejects anything outside it. Free text splits `checkbox` from `checkbutton` from `cb` and the searchability is gone.

Line length grows to about 95 characters at worst. The one-line rule wins over the margin, as always.

**Anchor an orientation grep to the end of the line.** Five rule NAMES carry an arrow of their own, so an unanchored `grep "↔"` returns those sites too whatever their actual orientation — 59 of the markers have an arrow on both sides of the ` -- `.

| Want                                 | Grep     |
| ------------------------------------ | -------- |
| horizontal only                      | `↔$`     |
| vertical only                        | `[^↔]↕$` |
| both directions                      | `↔↕$`    |
| anything with a horizontal component | `↔↕\?$`  |
| anything with a vertical component   | `↕$`     |

Every marker ends with its arrow, `unique` included — which is why that form puts its free-prose subject BEFORE the suffix and the check splits it from the right.

### The element vocabulary

Two names differ only when the elements have a **different lever or a different reference edge**. How we talk about them does not matter; how they are moved and measured does.

| Term       | Is                                     | Why it is its own type                                                                                                                            |
| ---------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `title`    | a LabelFrame's own title               | Drawn by the frame, on its border. Cannot be packed; the lever is `labelmargins`, not padding; sits ~0 from its box top where a 9pt Label sits ~2 |
| `heading`  | a 14pt bold Label                      | ~5px internal offset against ~2 — the only text needing negative padding to cancel it                                                             |
| `label`    | any 9pt Label                          | absorbs what might be called a caption or a status readout: same widget, same lever, same edges                                                   |
| `panel`    | a `ttk.LabelFrame`                     | has a visible border, so there is an edge to measure to                                                                                           |
| `frame`    | a plain `ttk.Frame`                    | has a different colored background, so there is an edge to measure to                                                                             |
| `tab`      | the Notebook's tab strip               | the edge every tab's first element measures from; no geometry manager reaches it                                                                  |
| `checkbox` | `tk.Checkbutton`                       |                                                                                                                                                   |
| `spinbox`  | `tk.Spinbox`                           | taller than a checkbox row; has a row rule of its own                                                                                             |
| `slider`   | `ttk.Scale`                            |                                                                                                                                                   |
| `button`   | `ttk.Button`                           | its box edge IS its border, unlike a Label's                                                                                                      |
| `dropdown` | `ttk.Combobox`                         | carries a ~2px text inset a Label does not                                                                                                        |
| `entry`    | `tk.Entry`                             |                                                                                                                                                   |
| `tree`     | `ttk.Treeview`                         | internals are style options; no geometry manager reaches inside                                                                                   |
| `text`     | `tk.Text`, scrolled or not             | fill reaches the border, and it is measured inside the fill                                                                                       |
| `run`      | a stretch of text INSIDE a Text widget | glyph edges like a `label`, but no geometry manager reaches it: the lever is a pixel tab stop, or `spacing1`/`2`/`3` between lines                |

**The vocabulary governs the SUFFIX only. Rule names stay prose.** Three rule names use a vocabulary word in a wider sense, all of them older than the vocabulary:

- `content frame -> content frame` covers panels as well as frames, and buttons that sit outside a panel.
- `explanation text` means prose in a Label, not a `text` widget.
- `panel ↕ unrelated label` means any TEXT beneath a panel, a `title` as much as a `label`. The distinction between the two did not exist when the rule was written.

### Rule renames

The names that changed when the suffixes went on, since every marker was being rewritten anyway:

| Was                                                         | Is                                        | Why                                                                                                                   |
| ----------------------------------------------------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `frame edge -> first non-button element`                    | `border edge -> first non-button element` | The rule needs a visible border to measure to, and `frame` is the vocabulary's word for the container that has none   |
| `frame edge -> button`                                      | `border edge -> button`                   | same                                                                                                                  |
| `text label row -> text label row`                          | `label row -> label row`                  | `text` means a Text widget in the vocabulary; this rule means a row holding only a label                              |
| `overarching tab control element group ↔ OTC element group` | `control group ↔ control group`           | It applies inside a panel too, not only tab-wide. Also 54 characters to 29, which is what keeps the suffix affordable |

`panel edge` was considered for the first two and dropped. The border measured to belongs to a LabelFrame at 36 of the 39 sites, so the name would have been right most of the time — but the three it is wrong about (the Optimizer toolbar's preset label, status label and off-Element checkbox) measure to a plain frame's content edge, where there is no panel and no painted border at all. `border edge` names what is measured to rather than what owns it, and covers both.

### Scope and standing exceptions

**Materials and About are out of scope**, and are the whole of it. No `# spacing: out of scope` marker is left in the source; the three that were — the Stat Contributions popup, the Restore Defaults dialog and the hover tooltip — are marked and nudged like anything else. Where a new boundary is drawn, one `# spacing: out of scope -- <why>` marks it.

**A Text sizes in CHARACTERS and LINES, and neither can say what a window needs to the pixel.** `width` reserves whole cells, so what is left after the last glyph lands on the RIGHT inset and nothing inside the widget reaches it; `height` multiplies the font's linespace, so a per-line `spacing3` changes what is drawn and not what the widget asks for. The contributions popup rounds both up and takes the difference off the WINDOW, which its text field absorbs because it is the only child packed to expand.

**A gap inside a window the app opens over the main one names that window.** A screenshot covers one window, so `track(window=...)` takes a callable returning the widget to photograph, and a scenario opens that window first and destroys it after. Eighteen such gaps are registered, across the Stat Contributions popup and the Restore Defaults dialog.

**A window sized to its content is sized to the WIDEST of its children, and the one that expands stretches to whatever wins.** The contributions popup's text field lost that race three ways at once: to the Close button, to the minimum width a window manager grants a titled window, and — in the other direction — to its own character grid rounding up. Each puts pixels between the last glyph and the field's border that no padding at the site can reach, and the reading then describes the winner rather than the inset. A gap measured inside an expanding child is only a reading of that child while the child is the one setting the size.

**Locate a control in one of those by CLASS as well as by words.** `Restore ` found the panel titled `Restore Missing` before it found the Restore button, and reported the 4px between the buttons as 307 — far enough out to be obvious, which was luck rather than design.

**The tooltip has no measured gap and no scenario.** Its inset is the one thing left that wants a scan inside a filled widget with no second widget to measure against: the tip window IS the label, so there is no pair to read. `_text_inset` reaches the popup's Text because a Text's own box edge is the border its prose is inset from; a Label's is not.

- **"Title above, element below" measures to the first painted pixel below the title, INCLUDING a border.** A LabelFrame's title sits above its own top border, so that border is usually what the rule measures to. The border-to-content gap is a separate measurement; adding the two gives a number two or three times the target.
- **Slack is left alone.** Where a frame is stretched larger than its content, the far edges have space nothing put there (`Character`'s bottom, `Requirements`' right).
- **A button row in a plain `ttk.Frame` is not the button rule's business.** That rule is `border edge -> internal button` — a panel's border against a button inside it. Capture and Setup's button rows and the Optimizer's Start/Stop sit in no panel, so their offset answers to `content frame -> content frame` and only the distance between the buttons is `button -> button`.
- **Set Configuration rows carry a spinbox beside each checkbox**, so row-pitch rules are measured between the CHECKBOXES. Measured as spinboxes the panel reports `0 x5, 9 x1, 42 x1` — they sit flush, and only conditional sets carry one at all, so consecutive spinboxes can be rows apart and the column has no pitch to read.
- **Capture's Status panel is exempt on its LEFT edge** and is excluded from the audit for that reason.
- **Setup Status misses the border-edge rule on BOTH axes**, and is tracked at what it actually is rather than left out: 7px on the left because the panel is placed to read before anything else on the tab, 7px on top because a Segoe UI 11 label's ink starts that far down its own box and a padding of 0 cannot claw it back.
- A **spinbox row** is the only single-row element tall enough to want its own target. A **slider row** takes the checkbox row's target deliberately, so the two can be split later without unpicking anything. Buttons are not single-row and answer to `button -> button`.

## Fonts in use

Body text is **Segoe UI 9**; the three panels of running prose are **Segoe UI Variable Small**, the optical size Windows draws small text at. `TkDefaultFont` is Segoe UI 9 and no ttk style overrides it, so an explicit `("Segoe UI", 9)` is the same face the default already gives.

| Face                    | Tk pt   | Ascent | Descent | Linespace | Where                            |
| ----------------------- | ------- | ------ | ------- | --------- | -------------------------------- |
| Segoe UI                | 9       | 12     | 3       | 15        | body text everywhere, bold included |
| Segoe UI                | 11      | 16     | 4       | 20        | Setup Status; Capture's `Ready`  |
| Segoe UI                | 14 bold | 20     | 5       | 25        | the tab headings                 |
| Segoe UI Variable Small | 11      | 16     | 4       | 20        | Capture Log; Setup Instructions; How Gear Score Works |
| Segoe UI                | 10      | 13     | 3       | 16        | About only — out of scope |
| Segoe UI                | 12 bold | 17     | 4       | 21        | About and Materials only — out of scope |
| Consolas                | 10      | 12     | 3       | 15        | the contributions popup — out of scope |

**Variable Small stands a pixel taller than Segoe UI below 11** — one more of ascent, the same descent — and that pixel lands above the first glyph, so a panel changing size owes its `pady` the difference. At 11 the two share a line box, and Variable Small **8** is the exact metric twin of Segoe UI 9 (12/3/15).

**Its ascenders clear its capitals, where Segoe UI's do not.** That is why the three panels set in it read their top inset off the first CAPITAL rather than off the line's topmost ink.

A 14 bold heading's ascenders reach above its capitals. Judge it by the capitals anyway.

### Digits share an advance width but not an ink width

`measure()` returns the ADVANCE; in Segoe UI 9 every digit advances 6px. What each PAINTS inside that differs, so a gap measured painted-edge to painted-edge changes with the last digit of the number:

| Digit           | Ink width | Left of the norm | Right of the norm |
| --------------- | --------- | ---------------- | ----------------- |
| `1`             | 5px       | 0                | **-1**            |
| `4`             | 8px       | **+1**           | **+1**            |
| `7`             | 7px       | 0                | **+1**            |
| `0 2 3 5 6 8 9` | 6px       | 0                | 0                 |

So a value ending in `4` reads 1px tighter than the same gap ending in `0`, with no padding having changed. Segoe UI 9 only — re-measure for another face.

## Where the spacing work stands

### Behaviour worth knowing before editing

- **Every checkbox is a `tk.Checkbutton` from `make_checkbox`**, and `checks/check_no_flash.py` enforces it. A panel building its own drifts from the rest in ways no padding value explains.
- **The helper's `bd` / `highlightthickness` are a LAYOUT lever**, not just a look: they set every checkbox's requested size, and the exclude checklist derives its row pitch and column flow from that. See the ledger.
- **`tk.Checkbutton` applies `padx` to both sides at once.** Where a lever needs one side only it lives on the geometry manager — which is why the Set Configuration left inset is a `pack(padx=(1, 1))` call and not a style.
- **A Checkbutton's tick is drawn in `fg`**, the same option that colours its text, so an indicator cannot differ in colour from its own label. Where the two must differ (Set Configuration), the widget is split into a text-less Checkbutton plus separate Labels.
- **Element colouring** reaches: Set Configuration indicators; Capture's Log Presets (only where every combatant assigned to the preset shares one Element — a preset spanning two, or covering an unknown combatant, stays on the default foreground); Memory Fragments' five elemental Main Stat filters; and Memory Fragments' Sets, where a two-Element set colours its NAME with the first and its COUNT with the second.
- **Gear cells put the slot name on the main stat's row**, right-aligned against the main stat's left, so a cell reserves one bold line rather than two.

### Measured, or not

**A marker says which rule a value answers to, not that the value is on target.**

**Counting markers against entries does NOT give a coverage figure**, and reading it as one is misleading in both directions. One entry can cover several markers — `tab list -> first element` measures every tab, and its extra sites are pads on outer frames feeding those same gaps. And a rule can have more entries than sites, because entries are generated in loops from tables while a marker is written once per lever.

**The one real limit is that some values cannot be measured at all.** Most of `content frame -> content frame` is pads on a plain `ttk.Frame`, which paints nothing, and a screenshot cannot measure a distance between two things that leave no pixels. The rest are on a `ttk.LabelFrame`, which draws a border and can be measured, except where the neighbour on the marked side is borderless or absent.

Derive that split rather than trusting a count, since a container can
change class: group the sites by what each pad's target was built as.

Two kinds of gap that look unmeasurable are not, and have their own resolvers. The columns of a Text widget are tab stops with no widget on either side: `_text_column_gap` turns each line into a band of rows with `dlineinfo`, merges painted bands closer together than a column gap into words, and reports the SMALLEST gap across the rows -- these value stops are right-aligned, so a short value leaves a wider gap after its label and only the widest row shows the distance that was set. Its rows are not widgets either, and `_text_line_pitch` reads the painted lines.

Both inset the box by what the widget paints around its own content: a cell with a relief border has painted pixels on every row, so a run scan over the whole box finds one run and never sees the lines inside it.

**Two entries measure to the Capture Log title, one per column above it,** and that pair is worth knowing about because it is the only place the ledger watches an ALIGNMENT. `left_col` is the taller of the two columns, so its height is the grid row's, and whatever pad sits below its last panel pushes the row down — carrying the right column's border with it and leaving the left one where it was. The two entries then read different numbers, and the difference is exactly that pad. Keeping it at 0 is what keeps the columns ending level.

### What the audit does not reach

Every registered gap is on its target and confirmed against a hand reading. An entry named in `AWAITING_FIRST_READING` is the exception and prints yellow, in the short run as well as the verbose one, until a run agrees with it. What follows is the parts of the app no entry measures, so a drift there shows up on screen and nowhere else.

- **The Optimizer's status label ends 6px from the tab's right edge**, where the border rule asks 4 and a Label's own inset has 2 left to give. The off-Element checkbox below it sits at 13, deliberately: it stays under the spinbox and is easier to click there.
- **`checkboxes -> unrelated checkboxes` has no entry at all.** Its one site pins its block to a panel's floor, so what sits above it is leftover height rather than a distance. The rule's 20 is a floor there, and the audit compares against a number.
- **A Treeview's internals**, and a button's own padding: both are `unique`, and the uniques table says why neither is a gap between two elements.

### Still to decide

**Nothing is unruled.** Every deliberate spacing value names a rule, an exception or a `unique`; `grep -rho "# spacing: TBD" Vribbels --include="*.py"` returns nothing, and the check fails if it stops being true.

**The `Character` panel is a COLLECTION OF LABELS**, settled. It is one Text widget holding a details block, a Sets line and two columns of build stats, but the Text is a drawing-speed choice rather than what the content is: every stat name and value is a `label ↔ its element` pair, and the two columns sit at `element and its label ↔ element and its label` from each other. Its tab stops are STATED for that reason, like the gear cell's.

`How Gear Score Works` goes the other way — it is meant to read as ordinary prose, so no distance rule reaches inside it.

## Spacing inside a Treeview

**A list's internals are ruled by this section, not the rules table.** Row height, the inset from a column edge to its text and the header's own padding are style options on a widget that draws itself, not gaps between two things a geometry manager can reach. So no row-pitch or frame-edge rule reaches inside a Treeview, and a marker there names the lever rather than a rule. The rules table covers the gap from the list's outer edge to whatever sits beside it.

All six Treeviews take the base `Treeview` style — none passes a `style=` — so they move together. `configure_styles` sets: `Treeview` padding **(2, 0, 2, 0)**, `rowheight` **21**, heading padding **3**, heading borderwidth **0**, and a layout with no `Treeview.field`, so the widget has no outline.

| Lever                   | What it insets                                                                                                                                                                                                                                                                        | Set to          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `Treeview.padding`      | the whole tree area — **and every cell's text inset**, see below                                                                                                                                                                                                                      | **(2, 0, 2, 0)** |
| `Treeview.Cell` padding | the inset from a column's edge to its text, in principle. **Inert here**; not set, deliberately                                                                                                                                                                                       | unset, shadowed |
| `Treeitem.padding`      | nothing — it draws the TREE column (#0), which `show="headings"` hides                                                                                                                                                                                                                | unset, inert    |
| `Treeheading.padding`   | one heading cell's content                                                                                                                                                                                                                                                            | **3**           |
| `Treeview.field` border | the widget's outline. Its WIDTH is not a style option (clam exposes only colours), so removing it means replacing the LAYOUT, the way `Flush.TNotebook` does. `fieldbackground` belongs to that element and goes with it; the area below the last row then falls back to `background` | absent          |
| `Treeview` `rowheight`  | the height of a row                                                                                                                                                                                                                                                                   | **21**          |

Heading borderwidth pairs with `relief`, which the theme sets to `raised`: at borderwidth 0 the relief has nothing to draw with, so the headings are deliberately flat.

**Rows are contiguous** — a row is `rowheight` tall and the next begins immediately, so any "row -> row" rule has nothing to attach to. Vertical breathing room comes from `rowheight` alone.

`bbox()` returns a row's rendered geometry but only once the window is mapped. `_hide_until_ready`'s alpha-0 trick makes that measurable without putting anything on screen.

### `Treeview` padding shadows `Treeview.Cell` padding

**Setting `padding` on the `Treeview` style at all — any value, `0` included — makes `Treeview.Cell` padding do nothing.** Once the widget's own style defines `padding`, the lookup for the cell's `Treedata.padding` element stops there and the derived style is never consulted. The value on `Treeview` is then what insets the cell text, on top of the tree area.

Measured by sweeping cell padding -4…12 and reading where the cell's text element starts (`identify_element` across the cell — no pixels needed):

| `Treeview` padding | `Treeview.Cell` padding -4 … 12 |
| ------------------ | ------------------------------- |
| unset              | text moves at every value       |
| 0                  | text never moves                |
| 3                  | text never moves; sits at 3     |
| 8                  | text never moves; sits at 8     |

- **To tune the cell inset, change `Treeview`'s `padding`.** A `Treeview.Cell` line would look like the lever and do nothing.
- **For an independent cell lever, drop `padding` from the `Treeview` configure.** The tree area does not move when you do: the borderless layout has already removed the field element the theme's padding was insetting from (measured, `bbox` unchanged either way).

## Colours that come in sets

### A border is three colours

| Option        | Draws                          |
| ------------- | ------------------------------ |
| `bordercolor` | the outline itself             |
| `lightcolor`  | the highlight side of a relief |
| `darkcolor`   | the shadow side of a relief    |

Setting only `bordercolor` leaves a pale highlight and shadow behind, which on a dark theme reads as the border not having changed at all. All three move together.

They are set once on the ROOT style (`.`), so every ttk widget that draws a border inherits them — including **Buttons, Scrollbars and Scales**, whose troughs and thumbs come from the same three. That reach is the point, but it is not only frame outlines that move.

A `tk` widget is not covered: its `relief` shading derives from its own `bg` and cannot be given a colour. A flat coloured outline there means `highlightbackground` with `highlightthickness=1`, not `relief`.

### A scrollbar is five

The three border colours reach only a scrollbar's edges; the two that fill it are separate, and clam ships them as light greys.

| Option                                     | Paints                             | Set to                        |
| ------------------------------------------ | ---------------------------------- | ----------------------------- |
| `troughcolor`                              | the groove the thumb slides in     | `bg`                          |
| `background`                               | the THUMB, and the arrow buttons   | `bg_lighter`                  |
| `arrowcolor`                               | the glyph inside the arrow buttons | `fg_dim`                      |
| `bordercolor` / `lightcolor` / `darkcolor` | its outline and relief             | inherited from the root style |

`TScale` splits the same way — trough is `troughcolor`, slider is `background`. Both are configured on `TScrollbar` / `TScale` rather than per-orientation; the horizontal and vertical variants inherit from one style.

**Every scrollbar in the app is a `ttk.Scrollbar`**, so this one style paints all of them. `scrolledtext.ScrolledText` would not be: it builds its own `tk.Frame` and `tk.Scrollbar` that no constructor keyword reaches, which is why `ui/utils/scrolled_text.py` builds the pair itself instead. See `ui_runtime.md`.

### What the audit counts as ink

The audit's question is not "is this pixel painted" but **"would the eye put the edge here"** — a gap measured to a pixel nobody can see reads as misaligned when it looks fine. Antialiasing puts such a pixel at both ends of every string.

So `is_background` runs three tests in order. A pixel matching a background shade exactly is empty space. A blend of two background shades is too — that is the tab-strip seam, and it needs no tolerance in RGB because testing whether the pixel lies BETWEEN two known shades is exact at any width. Then, for a pixel matching no palette colour at all, a **lightness** test: below `FRINGE_LIGHTNESS` in CIE L\* from the background, it is a fringe the eye cannot find, and it is empty space.

Three things about that last test are load-bearing.

**It is lightness, not colour difference.** These fringes are strongly tinted — Windows renders text with subpixel antialiasing, so a glyph's left edge goes blue and its right edge red rather than both going grey. A ΔE that includes chroma does not separate the visible from the invisible; L\* alone does, cleanly. The eye is not finding these specks by their colour.

**It only ever judges blends.** A control's fill and a border are palette colours and stay ink by identity. That matters because `bg_light` is a SMALLER lightness step from `bg` than the faintest glyph edge is — it is legible in the app because it covers an area, not because any one of its pixels stands out. A per-pixel test that judged it would look straight through every control.

**The palette therefore has to be complete.** `Capture.of_window` adds the rarity and element tables to it, because three of the four rarity row fills sit within L\* 6 of the window background and nothing about their own lightness would save them. **A widget painted in a shade from some new table must have that table added there too.**

`FRINGE_LIGHTNESS` was fitted against graded judgements of real glyph edges at life size, and `checks/check_fringe_lightness.py` holds that grading — it is the only record of it. Set the constant to 0 for the old exact-match behaviour.

## Column alignment, and what it cannot have both of

`label ↔ its element` is 5px, but in a COLUMN of label/value pairs the 5px is measured from the LONGEST label in the group, and every value starts from there — otherwise the values stagger and it stops being a column.

The `Character` panel is the reference implementation. Its stat block is a grid of labels and values that lives in a Text widget for drawing speed, so it is ruled as labels, not as prose, and its stops are STATED (`CHAR_TAB_VAL1` / `CHAR_TAB_NAME2` / `CHAR_TAB_VAL2` in `heroes_tab.py`) rather than measured at build time.

The arithmetic those numbers come from, per column:

```
col_width  = max(measure(label) + 5 + measure(widest_value))   # row by row
stop_val1  = col_width(left)                    # right-aligned stop
stop_name2 = stop_val1 + 8                      # the pair -> pair gap
stop_val2  = stop_name2 + col_width(right)      # right-aligned stop
```

**Taken row by row, not label-max against value-max separately**, so a row pairing a wide label with a narrow value costs nothing. `Element` is the widest label in the block and would drag the column right if the two maxima were combined.

The widest value each stat can hold, as the STRING rather than a character count — Segoe UI's digits are tabular, so a count is exact for digits alone, but `.` and `%` are not digit-width and the right column carries both:

| Stat       | Widest   |
| ---------- | -------- |
| ATK        | `9999`   |
| DEF        | `9999`   |
| HP         | `9999`   |
| Ego        | `999`    |
| CRate      | `99.9%`  |
| CDmg       | `999.9%` |
| Extra DMG% | `99.9%`  |
| DoT%       | `99.9%`  |
| Element    | `99.9%`  |

A value that outgrows its entry clips rather than pushing the column, so widen it here if one ever does. **Recompute the three stops from this table after changing the rows, the body font, or either rule's target.** At Segoe UI 9 they come to 51 / 59 / 138.

Tab stops are **pixel** offsets, not character counts, so a group can be tuned to the pixel. `name_px` is measured in the actual font, which is what survives a font change.

**A value column is anchored at one edge, and which one decides what stays constant:**

- **Right-aligned** (what `Character` does): last digits line up, so magnitudes are scannable down the column. The gap from label to the value's first glyph then VARIES with the value's length — which is why that panel reads 30px on the left column and 5px on the right. The 5px is the gap to where a FULL-WIDTH value would start.
- **Left-aligned**: every value starts 5px after the longest label, so the gap is constant and digits no longer line up.

Worth choosing per group: same-width percentages lose nothing by going left-aligned; a column mixing `9` and `600` wants its digits lined up.

| Group                     | Where                                   | Gap now              | Notes                                                    |
| ------------------------- | --------------------------------------- | -------------------- | -------------------------------------------------------- |
| Extra, Agony and Fracture | Optimizer, `Important Settings`         | 11px                 | the gap predates the third row and wants remeasuring     |
| HAL columns 1 and 2       | Optimizer, `Have at Least`              | 5px                  | on target                                                |
| Set spinboxes             | Optimizer, `Set Configuration`          | 5px                  | takes the 5px, NOT the alignment — see below             |
| Set MF counts             | Memory Fragments, `Sets`                | 8px                  | aligned per column                                       |
| Stat roll ranges          | Gear Score, `How Gear Score Works`      | 8px                  | the `STAT MIN - MAX ROLLS` block                         |
| Weights, left column      | Gear Score, `Stat Weight Configuration` | 12px                 |                                                          |
| Weights, right column     | Gear Score, `Stat Weight Configuration` | 10px                 | the 2px difference is the rightmost glyph, not a setting |
| `Stats:` values           | Combatants, `Character`                 | 30px left, 5px right | the right-alignment effect above                         |

`Set Configuration` is the standing exception to the ALIGNMENT half: its spinboxes keep the 5px but are not pulled into a shared column. The panel is tightly packed, so aligning would put a spinbox nearer a set it does not belong to; and only conditional sets have one at all, so the column would have holes. Ownership becomes ambiguous, which is worse than a ragged edge.

## Setup Status reads at one pitch

Every gap inside the panel — top edge to first row, between rows, last row to bottom edge — reads **11px to the ink**. The four rows carry no padding of their own: a Segoe UI 11 label's line box already contributes 7px above its ink and 4 below, which is the whole pitch, so anything added lands on top of it. The frame's top and bottom padding are chosen to make the first and last gaps match the ones between.

**Between the rows the tracked number is 13, not 11**, and the two are the same rendering. Those rows read `[OK] Python 3.13` once they have checked, and a bracket rises above the cap and drops below the baseline — so the ink is not where the rule's references are. The registry reads the pitch on each row's first CAPITAL instead, which puts both ends on a cap top and a baseline with no glyph correction to model, and which does not move when the panel leaves its `Checking ...` state. The gaps to the panel's own border are still read from the ink.

**The top gap is an exception to `border edge -> first non-button element`**, and unavoidably so: that rule's target is below the 7px the label's own line box contributes, so even a top padding of 0 renders 7. The exception is marked at the call site.

## The status cluster, and why its rows resist one rule

The Optimizer toolbar's right-hand stack is three things packed `side=TOP` in one frame: a bare status Label, then `Ignore MFs below level:` + spinbox, then `Ignore off-Element MFs` + checkbox. Rows 2 and 3 are frames; row 1 is not.

**Row-level padding is the correct lever and already the only one set.** The widgets inside carry no vertical padding.

**What zeroing the children cannot fix is that the rows are different heights.** A spinbox and a checkbox have intrinsic height — border, indicator, theme insets — that no padding removes, so each row's painted content sits at a different inset inside its box, and equal row padding measures equal box-to-box while looking unequal glyph-to-glyph. Hence two separate `unique` markers rather than one rule. Padding the tallest child does not help: a child's padding moves it INSIDE the row.

**The cluster's height is constrained.** It must fit the toolbar, whose height is set by the taller left-hand cluster. `small_font` is what these three rows are set in, so it is a lever on the toolbar's height rather than a cosmetic choice.

## The uniques, as a table

A `unique` names no rule, so nothing derives its number — and the registry's rule field is what an entry is checked through.

**An entry for a unique carries the marker's own `<what>` there.** `check_spacing_registry` accepts a rule string outside the rules table only when a `unique -- <what> -- ...` marker in the widget code spells it exactly AND the row below gives it the same number. That is the same two-copies-must-agree guarantee a rule name gets, so a typo on either side still fails; what it gives up is the rules table being the only vocabulary the registry may use.

**Every unique in the code needs a row here.** A row carrying a number must have an entry measuring it, and a row carrying **—** must have no entry at all — so a unique that ought to be tracked and quietly never was fails the check rather than sitting unwatched.

| What                                                | Where                                      | Distance | Why not tracked |
| --------------------------------------------------- | ------------------------------------------ | -------- | --------------- |
| `between mixed element rows (label -> spinbox)`     | Optimizer toolbar, status cluster           | 6px      | |
| `between mixed element rows (spinbox -> checkbox)`  | Optimizer toolbar, status cluster           | 2px      | |
| `Setup Status stands apart on purpose`              | Setup, the four status rows                 | 13px     | |
| `a button's own internal inset`                     | `TButton` padding, every button in the app  | —        | a widget's own inset, and it sets that widget's SIZE — the widths in `ui/utils/button_width.py` are only true against it. Every `button -> button` and `border edge -> button` reading rides it |
| `Treeview internals, which are style options`       | every list                                  | —        | style options on a widget that draws its own insides, and no geometry manager reaches between them. See "Spacing inside a Treeview" |
| `monospace columns inside the contributions text`   | Optimizer, the Stat Contributions popup     | —        | the columns are the `f"{value:>5.1f}"` that built the string, in a face where every character advances the same. No padding reaches between them, and changing one means changing a format |

**The first pair is read from the status text's BASELINE**, taken off its first capital rather than off its ink -- `No data loaded` has no descender and the strings that replace it do, which would move the reading by three without anything on screen moving at all. Text to text the same gap is 11, the spinbox seating its own digits inside its border. The second pair has a border at both ends and no such split.

**The Setup Status pitch is read on the first CAPITAL of each row**, not on the row's whole painted extent. Those rows read `[OK] Python 3.13` once they have checked, and a bracket rises above the cap and drops below the baseline — so a whole-row scan reports a pitch two overshoots short, and one that changes the moment the panel leaves its `Checking ...` state. Narrowing the scan to one letter puts both ends of the reading on the rule's own reference with no glyph correction to model. The same panel's gaps to its own border are still read from the ink, so they are not this number.

## The unruled rows, as a table

**Empty.** Every deliberate spacing value now names a rule, an exception, or a `unique`. `checks/check_spacing_markers.py` compares this section against the `# spacing: TBD -- ...` markers in the code, so a row here with no site — or a site with no row — fails.

The form, for when the next one appears:

| Description | Location | Rule/Question |
| ----------- | -------- | ------------- |

## Checking spacing

`ui/spacing_audit.py` measures registered gaps from a screenshot of the live window, counting background pixels by the convention above, so glyph reference points come out right without a font table. It cycles the tabs itself; the operator keeps the window unobscured and frontmost, the pointer off it (hover repaints and is measured), and a snapshot loaded so the data-driven panels exist.

**It locates panels by their visible title**, not by attribute — most of these frames are locals, and storing each on `self` purely to measure it would touch six tab files for no functional reason. So renaming a panel's title removes it from the audit; the baseline comparison reports that as a missing entry rather than a pass.

Some panels exist only in one app state (the Optimizer's Element override frame, for Unknown-attribute characters) and their presence moves everything beneath them, so the audit runs scenarios: it sets each state up, captures, tears it down, and moves on, all in one run.

**A borderless panel still has an edge to measure to.** `Borderless` drops the frame's own border, but everything these panels hold — a Treeview's `bg_light` field, a gear cell's `RIDGE` — paints a boundary in a colour the tab background never uses. So the reference edge is found by the colour transition, not by scanning for a border run. Pure text is the only thing in the app with no boundary of its own, and the glyph rules cover that case instead.

**The content-frame rule is measured BOX to box, alone among the rules.** It is the one target defined by the pads that produce it rather than by pixels on screen, and a painted reading gets the vertical case wrong: a LabelFrame's title is drawn above its border and inside its box, so a scan for the lower panel's first painted pixel finds the title's glyphs and adds that title's leading to the gap. It read 7 where the pads give 4. Horizontally the two agree, since a border starts at the box edge.

**A row that is registered but not yet confirmed by a hand reading prints in dark yellow.** The flag is `provisional=True` on the entry; it comes off once a reading agrees, and the next batch takes it. So a table of sixty rows says at a glance which ones nobody has checked yet.

**The `axis` column is `<>` or `^v`, not the arrows the markers use.** The audit prints to a cp932 console, where a single non-ASCII character raises `UnicodeEncodeError` before the table reaches the screen.

**The note column names a row that is not simply following its rule.** An ordinary row says nothing there; the two words that appear are:

- **`exception`** — the site deliberately misses the rule, and its call site carries an `exception` marker saying so. `Setup Status`' left edge is one. Every miss is one of these, by ruling: a distance that does not answer to its rule is an `exception` or a `unique`, never an unexplained number.
- **`inferred`** — the rule applies and is followed, but its number cannot be COMPUTED for this case, so it was carried across from elsewhere. Nothing needs this today. The parenthesis class was the last one and it derives now.

A target following a DIFFERENT rule is neither: `Restore Defaults` answers `border edge -> button` at that rule's own 3, so it says nothing. `checks/check_spacing_registry.py` enforces all of this against the targets in the table above, including that a miss has a marker somewhere naming the rule it breaks.

**A resolver's pixel path only runs under the audit.** The checks build tabs but never take a screenshot, and a locator probe stops at finding the widget — so an error in the scanning half survives `compileall`, `run_all.py` and a probe, and surfaces as one dead row in a run the maintainer had to set up. Writing a copy of the loop to try it out proves nothing: a copy is not the code.

**A resolver that matches nothing reports a SKIP, not a failure** — and a green run and a skipped row look alike. A class name that no longer matches any widget is the way in: an entry looking for `"TCheckbutton"` measures nothing at all, quietly, for as long as nobody reads the run closely.

## The ledger: which lever moves what

The registry says what each gap SHOULD be and measures it. What it cannot say is what else moves when you change something. **Read this before editing any spacing value.**

| Lever                                                               | Also moves                                                                                                                                                                                                      |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TLabelframe` `labelmargins`                                        | The title → border gap on EVERY LabelFrame. The `Borderless`, `Tight.Borderless` and `Gear.Borderless` variants set their own and do NOT inherit it.                                                            |
| A Set Configuration checkbox's `pack(padx=(left, right))`           | Every checkbutton in the set grid — one pack call serves every row. LEADING component is the panel's frame-edge lever; the TRAILING one is 0 and has to stay there, since the widget reserves 7px after its indicator that no padding reaches. |
| A Set Configuration name label's `pack(padx)`                       | The gap from the piece count, which is the checkbox's own TEXT — so this is the only lever on it. A leading space in the name string cannot serve: a space is whatever the font makes it.                       |
| A LabelFrame's `padding` left                                       | Every element in that panel, not just the first. Four panels track a second element in its own right (`ELEMENT_ENTRIES`), so a frame-level change there breaks as much as it fixes.                             |
| Capture's `left_col` grid `padx`                                    | The tab header, Status, Server Region, Requirements and the button row together.                                                                                                                                |
| A Set Configuration row's `container` `pady`                        | The checkbox AND its spinbox — they share one container.                                                                                                                                                        |
| The Optimizer's `content` pack `pady`                               | The entire tab, toolbar included.                                                                                                                                                                               |
| A text panel's LabelFrame `padding`                                 | Nothing useful — the inset lives on the `tk.Text`'s own `padx`/`pady`, inside the fill. Frame padding just exposes dark background.                                                                             |
| `make_checkbox`'s `bd` / `highlightthickness`                       | The requested HEIGHT and WIDTH of every checkbox, by 6px each way — and through that the exclude checklist's row pitch and column flow, computed from `winfo_reqheight()` / `winfo_reqwidth()` rather than set. |
| A Gear Score stat cell's trailing `padx`                             | Both the gap BETWEEN the two weight columns and the gap out to the button column: the cell's pad sits inside `stats_frame`'s width, so `stat grid -> button column` carries it too. |
| Memory Fragments' `opt_frame` `pack(padx)` LEADING                   | All four options checkboxes at once — they carry no padding of their own, so this is the only lever on their distance from the Main Stats border. `main_frame`'s trailing pad is 0 to keep it that way; a value there would move the same gap from the other side. |

**"Correct it on the frame or on the first label?" has an answer per panel, not a general one.** The four `ELEMENT_ENTRIES` panels split two ways:

- **Upgrade Log Settings** takes the FRAME for both, its label and its checkbox column reading the same inset. Its TOP is the exception: the frame's padding cannot go below 0 and the rule asks for less than a label's line box gives, so that one pixel comes off the label.
- **Important Settings** corrects on the FRAME, because an ordinary 9pt Label is what most of its content is. Correcting on the first label instead puts that one line on target and leaves every other label a pixel out. The one element needing its own pixel is the Shielding & Healing slider: it is the only one starting at the frame's edge rather than after a row label, and a Scale's trough begins at its box edge where a Label's glyphs start inside theirs.
- **Set Configuration** takes the frame lever for both elements, its checkboxes riding it with the leading component of their own `pack(padx=...)` as the differential.
- **Stat Weight Configuration** has no frame lever at all. Its preset list runs to three of the panel's borders, and a frame padding insets every child alike — so the inset lives on each of the OTHER children's `padx` as `PANEL_INSET`, and the list carries nothing. Its grid, its `Applied ...` label and its caption all take that one constant.

## Reading a bad measurement

**When a gap looks wrong, measure from the glyphs and the border, not from the numbers in the source.** Equal padding across two tabs is not evidence they look the same.

If a reading looks wrong in one of these shapes, suspect the tool:

| Symptom                                                | Cause                                                                                                                                       |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Unrelated panels all reporting the same number         | `ImageGrab` reads the COMPOSITED desktop, which lags `update()`. Needs a pause before the grab.                                             |
| Gaps inflated wherever the first element was a control | `bg_light`/`bg_lighter` treated as background, but they are the FILL of buttons, spinboxes and Treeviews — the scan looked through to text. |
| Every left inset exactly +1                            | Measured from the frame's box edge, where the border STARTS. The reference is the border's inner edge.                                      |
| Text panels reporting 0, then a huge negative          | Their fill reaches the border by design, so a scan looking for background to stop at never stops.                                           |
| Descender found in some titles, not others             | The probe strip sampled only the first two or three characters.                                                                             |
| Title gaps 2-3x too large                              | Measured title → first CHILD, through the border. The rule measures to the first painted pixel below the title, which IS the border.        |

## Padding is not what you see

**Nesting depth varies per tab.** The 2+2 rule assumes exactly two levels between the tab frame and anything with a visible border. Capture has three on its left (`main_frame` → `top_columns` → `left_col`), so `top_columns` carries 0 on top; Memory Fragments has one on the list side, so `tree_frame` carries the full 4. **Count the levels for the specific widget before assigning a value.**

**Text sits at different offsets inside different widgets**, measured from the widget's own top edge:

| Widget           | Offset                       |
| ---------------- | ---------------------------- |
| LabelFrame title | ~0 (drawn on the top border) |
| 9pt `ttk.Label`  | ~2                           |
| 14pt `ttk.Label` | ~5                           |

So identical frame padding puts a 14pt heading several pixels lower than a LabelFrame title. Every in-scope 14pt heading carries a negative vertical `padding` to cancel it — Capture, Gear Score, Setup, and the Combatants detail pane's `Select a combatant`, which `make_tab_header` does NOT build: it has a control group beside it, not a subtitle. **Their values have DRIFTED apart, so do not read one as canonical.** A tab leading with a plain Label instead (Optimizer) drops its container's top pad for the same reason.

### Negative padding

A caption packed `anchor=W` above a `ttk.Combobox` or `tk.Spinbox` sits ~2px RIGHT of the field's text and needs `padding=(-2, 0, 0, 0)` on the Label. Note the direction — the opposite reading has been "corrected" with positive `padx` twice, making it worse both times. `style.lookup("TCombobox", "padding")` is a false lead: it reports one element's contribution, not the widget's total text offset.

The correction goes on the widget because pack's `padx` **cannot be negative** (`bad pad value "-2": must be positive screen distance`). Negative `padding` shrinks the Label's requested width and shifts the glyphs within it.

Limits:

- A Label has about **2px of internal inset to give back**; at -3 the text is drawn outside its box and the leading glyph clips. When more is needed, take the rest from the widget on the other side — the Set Configuration checkbox's `pack(padx=(1, 1))` trims its trailing side.
- Negative `padding` works on `ttk.Label` and other ttk widgets but is **ignored on `ttk.Frame`** — the child does not move.
- `tk.Label`'s `pady` clamps at 0, so it gives back at most the 1px it adds by default. For more, use a `ttk.Label`; the theme's default background already matches `colors["bg"]`, so only `foreground` needs carrying over.

### Text-backed panels

`Character`, `Partner`, `Capture Log`, `Setup Instructions` and `How Gear Score Works` carry `padding=0` on the LabelFrame and put the whole inset on the text widget: `bd=0, highlightthickness=0, padx=5` (the border-edge target), plus a `pady` that lands the first line on it.

Frame padding would push the lighter background away from the border and expose a dark strip; the Text's own `padx`/`pady` are drawn INSIDE that background, so the panel fills and the text is still inset.

`pady` is not the same on every panel because the line box already contributes space above the first glyph — about 3px at Segoe UI 9, about 1px at the default fixed font, so fixed-font panels carry a larger `pady`. `padx` is needed in full everywhere. `bd` and `highlightthickness` matter because Tk's defaults for a `Text` are 1 each, which adds stray inset and draws a sunken border and focus ring in colours the dark theme never set.

**A panel that becomes text-backed must be added to `TEXT_PANELS`** in `ui/spacing_registry.py`, which is what makes the audit measure it INSIDE the fill. Left out, its rows report a negative inset and a saturated border scan.

## Shared styles for tab framing

`Flush.TNotebook` borrows the default theme's client element: clam's own insets tab content by 2px on every side, shared by every tab and not tunable per tab. Tabs that shouldn't shift add the 2px back in their own outer margin. `Flush.TNotebook.Tab` inherits every `TNotebook.Tab` setting, dynamic state maps included.

`Borderless.TLabelframe` keeps a panel's title and drops its border, for panels whose content already draws one: the Optimizer's Stats Comparison / Results / Selected Build trees and the Combatants gear grid. `Tight.Borderless.TLabelframe` pulls the title 5px tighter (Optimizer Results). `Gear.Borderless.TLabelframe` exists for its bottom component, which is 0 where the base style's is 3 — not an oversight: the gear cells carry a `pady` of their own where a bordered panel's content does not, so the panel reads on target. Measured.

**`labelmargins` REPLACES the theme's margins rather than adding to them**, so `"0 0 0 -1"` is 5px tighter than leaving it unset, not 1px — and setting three components to 0 sits tighter than the default rather than preserving it. A LabelFrame's title starts at x=0 by default, and its x offset is the FIRST component, so nudging a title sideways means a dedicated style variant.

**A title is aligned with its own panel automatically, and must never be aligned by hand.** The x offset is the first `labelmargins` component and it is `0` in every style block but one. A title that looks out of line with the content beneath it is reporting that the PANEL is misplaced — moving the title instead hides the evidence and leaves the panel where it was.

`Gear.Borderless` carried the one violation, a 1px nudge read as the title needing to meet the gear grid. The grid was already right — it sits at the content-frame rule's 4px from the character list — and the nudge is what put the TITLE at 5. Removed; the offset is 0 everywhere now.

None of the three variants is in the audit, so their values rest on the base style's measurement rather than one of their own.
