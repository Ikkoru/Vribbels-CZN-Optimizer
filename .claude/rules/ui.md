---
paths:
  - "Vribbels/ui/**"
---

# UI rules

Loads when a file under `Vribbels/ui/` is read. Panel layout, the spacing ledger and ttk styles: `docs/ui_spacing.md`. Tk threading, startup and display quirks: `docs/ui_runtime.md`. Running and reading the spacing audit: the `spacing-audit` skill.

## Hard rules

- **The default window size is the design target.** Resizing is a convenience, not a supported layout: nothing may BREAK at another size, but nothing has to look good at one either. A change that makes a tab taller or wider is judged against the default and against the minimum, not against whatever size the window happens to be — and "someone's window might need widening" is not a defect.
- **Every hardcoded distance goes through `px()`**, on the geometry call and never on the constant — `ui/scaling.py` says why. A MEASURED distance (a font metric, a `winfo_reqheight`) must NOT: the font scaling already carried it. The spacing audit is 100%-only; `checks/check_ui_scales.py` is what watches 200%.
- **Every checkbox comes from `ui/utils/checkbox.py` and every scrolled text from `ui/utils/scrolled_text.py`** — a check enforces both.
- **The Combatants tab's live refresh is gated on `HeroesTab.display_signature()`.** A field that reaches the rows or the detail pane without being added to the signature goes stale silently — extend the signature in the same edit.

## Comments

- A `# spacing:` marker must be greppable as one string, so it stays on one line whatever its length. The wrap loses to the content.
- UI spacing values carry `# spacing: <rule>` rather than the distance they produce. See `docs/ui_spacing.md` "The rules".

## Measuring the UI without a window

**The UI can be measured headlessly, but only halfway.** Building the tabs against a Tk root (the `check_tabs_build.py` recipe) makes widget OPTIONS and DATA readable — `cget`, `grid_info`, a Treeview's row values. RENDERED GEOMETRY does not come with them: `winfo_width` / `winfo_x` read 1 until the window is mapped.

Mapping a window puts it on the maintainer's screen — **ask first**. `withdraw()` is not enough (`tk.Tk()` maps on construction, so withdrawing on the next line still flashes a frame). The app's own answer is `_hide_until_ready()`: alpha 0, which is mapped and therefore measurable but invisible. Use that for any probe that needs real geometry.

| To check                        | Do this                                                                                             |
| ------------------------------- | --------------------------------------------------------------------------------------------------- |
| Which widgets a change moved    | Build the tabs the `check_tabs_build.py` way, snapshot every row's values before and after, diff     |
| A rendered GAP, in pixels       | `zRUN Spacing Audit Verbose.bat` — every registered gap, read off a screenshot. Ask before running one |
| Something only the screen shows | A side-by-side repro in `_tmp/` — the maintainer runs it, so it goes in the repo, not the scratchpad |
