# UI styles, fonts and scaling

Read before changing a font, a colour, a ttk style or a Treeview's look, or a distance `px()` scales. What a gap between two elements should measure, the markers that say so and the audit that checks it are `ui_spacing.md`; threading and startup are `ui_runtime.md`.

Sections, in order: *The UI scale, and what the audit can see of it*; *Fonts in use*; *Colours that come in sets*; *Spacing inside a Treeview*; *Shared styles for tab framing*.

## The UI scale, and what the audit can see of it

Every hardcoded distance in the UI passes through `px()` from `ui/scaling.py`, which multiplies it by the active scale -- 1 at 100%, 1.25 to 1.75 between, 2 at 200% -- and rounds it to a whole pixel, halves up. Fonts scale separately, through Tk's own point-to-pixel ratio, and everything the app COMPUTES from a font metric follows from that for free.

Two rules, and the second is the one that bites:

- **`px` on the geometry call, never on the constant.** A distance built from parts is scaled once at the end; scaling each addend rounds each one and the sum lands elsewhere. At 200% nothing rounds; at 125% a 5 becomes 6 and a 2 becomes 3, so two parts scaled apart can land a pixel off their sum scaled once. A row of widths laid end to end -- a list's columns -- goes through `px_spans`, which scales the running edges so the parts add up to the whole.
- **A MEASURED distance never goes through `px`.** `font.measure(...)`, `winfo_reqheight()`, a Text's `dlineinfo` — all already grew with the font. A pad mixing the two wraps its hardcoded half alone: `px(INSET) + indent`.

**The audit runs at every scale, and holds each gap to its target as `px` scales it** -- exactly twice it at 200%. A scaled screen should show what a 100% one does, so a target is a 100% distance and a run at a scale scales it (`spacing_audit.scaled`). The resolvers' own distances -- a glyph's overshoot, a scan's reach -- are 100% numbers too, and go through `px` where they are used. A miss above 100% that reads its frozen value is accepted (`as frozen`); what was frozen is font rounding and fixed theme pixels, studied first. The headless half is `checks/check_ui_scales.py`. It builds every tab at 100% and 200% only: 200% is the one whole multiple, where a pad that missed its `px` shows as EQUAL and nothing rounds to hide it. It compares each pad, failing one that did not grow (a missed `px`) and one that grew twice (a `px` on a measurement). It also hands every label that rewraps on `<Configure>` an event of a known width, and fails a wraplength that lands wider than that width. The event's width is measured, and a `px` on it wraps the text past its space.

**Tk scales only what is given in points**: the fonts, and the theme metrics clam states in points. Everything else in pixels stays its 100% size unless the app restates it: a classic widget's default `bd` and `padx`, a ttk label's built-in border (clam's element default, 2, with no padding), a button's focus ring. `ui/scaling.py` restates them at startup (`CLASSIC_PIXELS`, `THEME_PIXELS`), and only above 100%. `checks/check_theme_scaling.py` reads every pixel option of every style at both scales, the app's own styles included. **A clam border is the exception that does not double**: clam draws a panel's, a button's and a combobox field's border 2px at any `borderwidth`, which only reserves room inside the line. So those keep their 100% value, and the line stays 2px at 200%. Every distance measured from a border's inner edge still doubles; the line's own thickness is the theme's limit.

**Some of Tk's pixels are inside its C code**, where no option reaches them. A Windows checkbutton adds a 1px focus inset on every side and trims 4px off the height its dialog-unit rule gives (`tkWinButton.c`). `make_checkbox` carries both through its padding, except that Tk clamps a negative pad to 0, so a `compact` checkbox stays 1px taller on each side at 200%. A Spinbox or Entry keeps a 1px inset round its text, and a Spinbox 4px more in its arrow column. A Text's narrowest TAB is one space of the Text's own font (`AdjustForTab` in tkTextDisp.c) -- a measurement, so a stop worked out from it takes no `px`.

**Between 100% and 200% a gap is scaled whole, not part by part.** `px` rounds a half up, and most gaps are two parts meeting: two frames' 2s, or a pad and a checkbox's inset. Two halves then make a pixel -- two 2s are 3 + 3 at 125%, where 5 is wanted. A pad that ends a gap another began takes `px_after(before, distance)`, the rest of the whole scaled once. An inset inside a widget takes `px_inset`, rounding its half down where the pad beside it rounds up. A default checkbox's inset is one (`make_checkbox`), and `pad_between` and `pad_beside_label` give the pads around it. `px_after` and `px_inset` are exact at 100% and 200%, the same as `px`. `checks/check_scale_runs.py` holds the arithmetic. What is left at 125%, 150% and 175% is font rounding and parts no option reaches.

**A font does not double to the pixel either**, and that rounding is accepted above 100%: a point size lands on whole pixels separately at each scale, and its line spacing and glyph widths are hinted per size. No size matches the 100% one scaled in every metric -- 12px Segoe UI is hinted narrow and short. So each scale above 100% sets `tk scaling` under the scale (`scaling.TEXT_SCALING`), at the size whose line height is nearest the 100% one scaled, of those the font gauge passes. The gauge (`docs/font_gauge.py`) measures the places a taller or a wider font clips first. What the theme states in points is then restated as its 100% pixels through `px` (`scale_theme`), since that ratio no longer scales it exactly. A width measured off text at 100% and written down takes `text_px`, which grows it by what the face grew by rather than by the scale. `docs/scale_survey.py --scale=<n>%` compares every widget at a scale with its 100% size scaled, writing what differs and an image of each tab at both.

Icons double by NEAREST NEIGHBOUR at 200%, which is exact at a whole multiple -- every source pixel becomes a square of copies. Between 100% and 200% they are resampled with Lanczos3 and a light sharpen (`image_utils._resized`): there is no art larger than 112x113 in the repo, so anything between invents what it draws.

## Fonts in use

Body text is **Segoe UI 9**. The panels of running prose are **Segoe UI Variable Small**, the optical size Windows draws small text at. The Checklist's rows are **Segoe UI 10**, a point up, that tab being read rather than scanned, and so are the Galactic Disaster tab's and the Epione tab's. `TkDefaultFont` is Segoe UI 9 and no ttk style overrides it, so an explicit `("Segoe UI", 9)` is the same face the default already gives.

| Face                    | Tk pt   | Ascent | Descent | Linespace | Where                            |
| ----------------------- | ------- | ------ | ------- | --------- | -------------------------------- |
| Segoe UI                | 9       | 12     | 3       | 15        | body text everywhere, bold included |
| Segoe UI                | 11      | 16     | 4       | 20        | Setup Status; Capture's `Ready`; the Epione tab's scenario counts, opening lines, cures and follow-up names |
| Segoe UI                | 14 bold | 20     | 5       | 25        | the tab headings, the Materials tab's three column headings, Application Information's first two lines |
| Segoe UI Variable Small | 11      | 16     | 4       | 20        | Capture Log; Setup Instructions; How Gear Score Works; the settings notice (`defaults_notice.FONT`) |
| Segoe UI                | 12 bold | 17     | 4       | 21        | the Materials tab's Element names |
| Consolas                | 10      | 12     | 3       | 15        | the contributions popup, which is ASCII so every character is one 7px cell |

Variable Small stands a pixel taller than Segoe UI below 11 — one more of ascent, the same descent — and that pixel lands above the first glyph, so a panel changing size owes its `pady` the difference. At 11 the two share a line box, and Variable Small **8** is the exact metric twin of Segoe UI 9 (12/3/15).

Its ascenders clear its capitals, where Segoe UI's do not. That is why the panels set in it read their top inset off the first CAPITAL rather than off the line's topmost ink.

A 14 bold heading's ascenders reach above its capitals. Judge it by the capitals anyway.

### Digits share an advance width but not an ink width

`measure()` returns the ADVANCE; in Segoe UI 9 every digit advances 6px. What each PAINTS inside that differs, so a gap measured painted-edge to painted-edge changes with the last digit of the number:

| Digit           | Ink width | Left of the norm | Right of the norm |
| --------------- | --------- | ---------------- | ----------------- |
| `1`             | 4px       | **-1**           | **-1**            |
| `5`             | 5px       | **-1**           | 0                 |
| `7`             | 7px       | 0                | **+1**            |
| `0 2 3 4 6 8 9` | 6px       | 0                | 0                 |

A minus means the ink falls SHORT of the advance on that side, a plus that it runs past. So a gap ending at a `1` reads 1px WIDER than the same gap ending at a `0`, and one ending at a `7` reads 1px tighter, with no padding having changed. **`1` is the one to watch**: it is inset on both sides, so it widens the gap before it as well as the gap after.

Where that digit is the data's -- a date ending a column -- the reading takes that end at the advance instead, so it follows the layout rather than the date: `_text_field_gap`'s `advance`, and `_materials_value_column` for the same reason.

Measured through GDI, the rasteriser Tk draws with on Windows, into a memory DC with no window on screen. A 9pt Segoe UI logfont (`lfHeight` -12 at 96 DPI) reports the same 6px advance for every digit that Tk's own `measure` does, and the ink columns are read back under `FRINGE_LIGHTNESS`, the audit's own test. ClearType, which is what Windows renders text with by default -- the greyscale-antialiased raster gives narrower ink for every digit and does not match what the audit reads off the screen.

Segoe UI 9 only; re-measure for another face, and re-MEASURE rather than reason. Neither `1` flush left nor `4` overhanging by a pixel on each side is what the screen does. A table that assumes either shows up as a `label -> count` gap reading a pixel wider than its target wherever the count begins with a 1.

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

Every scrollbar in the app is a `ttk.Scrollbar`, so this one style paints all of them: the colours above, `SCROLLBAR_WIDTH` thick (`czn_optimizer_gui.py`). `scrolledtext.ScrolledText` would not be: it builds its own `tk.Frame` and `tk.Scrollbar` that no constructor keyword reaches, which is why `ui/utils/scrolled_text.py` builds the pair itself instead. See `ui_runtime.md`, *A ScrolledText flashes for a SECOND reason*.

### Element colouring

A combatant's Element colours:

- Set Configuration's indicators;
- Capture's Log Presets, only where every combatant assigned to the preset shares one Element: a preset spanning two, or covering an unknown combatant, stays on the default foreground;
- Memory Fragments' five elemental Main Stat filters;
- Memory Fragments' Sets, where a two-Element set colours its NAME with the first and its COUNT with the second.

The audit's palette holds the Element and rarity tables; a widget painted from any other table needs that table added there (`ui_spacing.md`, *The audit's definition of ink*).

## Spacing inside a Treeview

**A list's internals are ruled by this section, not by `ui_spacing.md`'s rules table.** Row height, the inset from a column edge to its text and the header's own padding are style options on a widget that draws itself, not gaps between two things a geometry manager can reach. So no row-pitch or frame-edge rule reaches inside a Treeview, and a marker there names the lever rather than a rule. The rules table covers the gap from the list's outer edge to whatever sits beside it.

Every Treeview but the Stats & Gacha History tab's takes the base `Treeview` style — none passes a `style=` — so they move together. `configure_styles` sets: `Treeview` padding (3, 0, 3, 0), `rowheight` **21**, heading padding **3**, heading borderwidth **0**, and a layout with no `Treeview.field`, so the widget has no outline.

The Stats & Gacha History tab's lists take `GachaHistory.Treeview`, set up in that tab: 3 at each side of a column's text, in cells and headings alike, and an empty spacer column between every two columns. **Padding cannot be set per column** — one left and one right value serve every column of a list — so the spacer is what keeps the outermost columns 3 from the list's edges while the rest sit further apart. Its layout has no `Treeview.padding` element, so its `padding` insets the text alone rather than the tree area too. Colours and row height fall through to `Treeview`, except the selected row's text colour: `Treeview` maps it, a style map outranks a row's tag, and this style's own empty map is what keeps a selected row in its rarity or warning colour.

Its Overall Gacha Stats sheet is a Text, not a list, because its rows are label rows and one kind sits further apart: `label row -> label row` between rows, four more above a section's heading (`HEADING_PAD`, marked as the exception). A Treeview's rows are one height, with nothing reaching between them. Each line carries one pitch tag, which is what the registry's entries read the two gaps by. The columns are tab stops worked out from the rows on every fill, each only from the rows with something after it. A record's ties follow it as (units, date) pairs: units to their date is `label ↔ its element`, one pair to the next `element and its label ↔ element and its label`. As many pairs as fit the Banners list's width are shown, oldest first, since a wider sheet would widen that column and take the difference from the pulls list. **A line can set two sections side by side** (a `Beside`): every banner's section sits beside the first section's opening lines, `BESIDE_GAP` past the furthest of them. Such a line carries stops of its own on a tag of its own, since the sheet's stops are the first section's columns.

The standings stand under it as lists. The Great Rift's has the Banners list's width for its room. Under it, the Full-Scale Offensive's and the Sortie's share that width, half each less the pads between them, a title wider than its half taking the difference from its neighbour's list. Each is two Treeviews in the tab's list style: the rows' names, held still, and the seasons, one column each, in a holder that scrolls sideways past its room. Each list grows a column a season up to its room rather than taking it: held at it, two seasons would be mostly empty heading over a scrollbar with nothing to scroll. Each title is a labelwidget, so a grey note on how to fill the list sits on its line (`header subtext`, as the Optimizer's Results title does). **A labelwidget `ttk.Label` sits 2px in from a `text=` title** on every side: `TLabel` draws its text inside a 1px border and a 1px padding, where a LabelFrame's own title has neither. So the titles take `panel_title_style()` (`ui/utils/panel_title.py`), the title's own layout, and the gap to the note is the note's whole pad. Their columns sit `STANDINGS_COLUMN_GAP` apart, narrower than the Banners and Pulls lists' `COLUMN_GAP`.

The Banners list takes all of the window's spare width, in its last column, from `_fit_banners` on every resize of the tab's body. Every column before it keeps its measured width, the Pulls list keeps its own, and the standings have the Banners list's width to grow into, whatever it has become.

What makes the column fit the default window: every list on the tab at `LIST_ROW_HEIGHT`, shorter than the app's other lists; the Banners list showing at most `BANNER_ROWS` rows and scrolling past them; and the tab's scrollbars at `SCROLLBAR_WIDTH`. `check_tabs_build` measures the worst of it -- a Banners row for every banner type, every list scrolling, the warning lines showing, the gacha sheet at its widest -- in a default-sized window, under the app's own styles.

The titles' leading pads differ by what stands above them, all three set for `panel ↕ unrelated label`:

- `UNDER_SHEET_PAD` under the gacha sheet, whose last line box already reaches below its baseline;
- `UNDER_LIST_PAD` under the Great Rift's list;
- the button group's bottom pad for the Banners and Pulls titles under the toolbar, which holds only while the help text beside the buttons is no taller than they are.

The audit reads those columns between where the Text drew each field (`_text_field_gap`), not from the ink alone. A 5px boundary between fields is no wider than the comma-space inside `Nine, Narja`, and inferring columns from the gaps split the units instead. A date's end is read at its advance, since its last digit is the data's.

| Lever                   | What it insets                                                                                                                                                                                                                                                                        | Set to          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `Treeview.padding`      | the whole tree area — **and every cell's text inset**, see below                                                                                                                                                                                                                      | **(3, 0, 3, 0)** |
| `Treeview.Cell` padding | the inset from a column's edge to its text, in principle. **Inert here**; not set, deliberately                                                                                                                                                                                       | unset, shadowed |
| `Treeitem.padding`      | nothing — it draws the TREE column (#0), which `show="headings"` hides                                                                                                                                                                                                                | unset, inert    |
| `Treeheading.padding`   | one heading cell's content                                                                                                                                                                                                                                                            | **3**           |
| `Treeview.field` border | the widget's outline. Its WIDTH is not a style option (clam exposes only colours), so removing it means replacing the LAYOUT, the way `Flush.TNotebook` does. `fieldbackground` belongs to that element and goes with it; the area below the last row then falls back to `background` | absent          |
| `Treeview` `rowheight`  | the height of a row                                                                                                                                                                                                                                                                   | **21**          |

Heading borderwidth pairs with `relief`, which the theme sets to `raised`: at borderwidth 0 the relief has nothing to draw with, so the headings are deliberately flat.

Rows are contiguous — a row is `rowheight` tall and the next begins immediately, so any "row -> row" rule has nothing to attach to. Vertical breathing room comes from `rowheight` alone.

`bbox()` returns a row's rendered geometry but only once the window is mapped. `_hide_until_ready`'s alpha-0 trick makes that measurable without putting anything on screen.

### `Treeview` padding shadows `Treeview.Cell` padding

**Setting `padding` on the `Treeview` style at all — any value, `0` included — makes `Treeview.Cell` padding do nothing.** Once the widget's own style defines `padding`, the lookup for the cell's `Treedata.padding` element stops there and the derived style is never consulted. The value on `Treeview` is then what insets the cell text, on top of the tree area.

Measured by sweeping cell padding -4…12 and reading where the cell's text element starts (`identify_element` across the cell — no pixels needed): with `Treeview` padding unset the text moves at every value; with it set, `0` included, the text never moves, and sits at the `Treeview` value.

- **To tune the cell inset, change `Treeview`'s `padding`.** A `Treeview.Cell` line would look like the lever and do nothing.
- **For an independent cell lever, drop `padding` from the `Treeview` configure.** The tree area does not move when you do: the borderless layout has already removed the field element the theme's padding was insetting from (measured, `bbox` unchanged either way).

## Shared styles for tab framing

`Flush.TNotebook` borrows the default theme's client element: clam's own insets tab content by 2px on every side, shared by every tab and not tunable per tab. Tabs that shouldn't shift add the 2px back in their own outer margin. `Flush.TNotebook.Tab` inherits the `TNotebook.Tab` colours, and draws its tab with an image element of its own so that each tab's group bar can reach the tab's edges: its padding carries clam's tab inset, which stays 3px at every scale while the rest doubles. `ui/utils/tab_bars.py` says how, and what the image element costs.

`Borderless.TLabelframe` keeps a panel's title and drops its border, for panels whose content already draws one: the Optimizer's Stats Comparison / Results / Selected Build trees and the Combatants gear grid. `Tight.Borderless.TLabelframe` pulls the title 5px tighter (Optimizer Results). `Gear.Borderless.TLabelframe` exists for its bottom component, which is 0 where the base style's is 3. That is not an oversight: the gear cells carry a `pady` of their own where a bordered panel's content does not, so the panel reads on target. Measured.

**`labelmargins` REPLACES the theme's margins rather than adding to them**, so `"0 0 0 -1"` is 5px tighter than leaving it unset, not 1px — and setting three components to 0 sits tighter than the default rather than preserving it. A LabelFrame's title starts at x=0 by default, and its x offset is the FIRST component, so nudging a title sideways means a dedicated style variant.

**A title is aligned with its own panel automatically, and must never be aligned by hand.** The x offset is the first `labelmargins` component and it is `0` in every style block. A title that looks out of line with the content beneath it is reporting that the PANEL is misplaced — moving the title instead hides the evidence and leaves the panel where it was.

None of the three variants is in the audit, so their values rest on the base style's measurement rather than one of their own.
