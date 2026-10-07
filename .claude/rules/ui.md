---
paths:
  - "Vribbels/ui/**"
---

# UI rules

Loads when a file under `Vribbels/ui/` is read. Panel layout, the spacing ledger and ttk styles: `docs/ui_spacing.md`. Tk threading, startup and display quirks: `docs/ui_runtime.md`. Running and reading the spacing audit: the `spacing-audit` skill.

## Hard rules

- **The default window size is the design target.** Resizing is a convenience, not a supported layout: nothing may BREAK at another size, but nothing has to look good at one either. A change that makes a tab taller or wider is judged against the default and against the minimum, not against whatever size the window happens to be — and "someone's window might need widening" is not a defect.
- **Every hardcoded distance goes through `px()`**, on the geometry call and never on the constant — `ui/scaling.py` says why. A MEASURED distance (a font metric, a `winfo_reqheight`) must NOT: the font scaling already carried it. The spacing audit reads both scales, each gap held to exactly its 100% target times the scale; `checks/check_ui_scales.py` is the headless half, comparing every pad at the two.
- **Every checkbox comes from `ui/utils/checkbox.py` and every scrolled text from `ui/utils/scrolled_text.py`** — a check enforces both.
- **The Combatants tab's live refresh is gated on `HeroesTab.display_signature()`.** A field that reaches the rows or the detail pane without being added to the signature goes stale silently — extend the signature in the same edit.

## Comments

- A `# spacing:` marker must be greppable as one string, so it stays on one line whatever its length. The wrap loses to the content.
- UI spacing values carry `# spacing: <rule>` rather than the distance they produce. See `docs/ui_spacing.md` "The rules".

## Measuring the UI without a window

**The UI can be measured headlessly, but only halfway.** Building the tabs against a Tk root (the `check_tabs_build.py` recipe) makes widget OPTIONS and DATA readable — `cget`, `grid_info`, a Treeview's row values. RENDERED GEOMETRY does not come with them: `winfo_width` / `winfo_x` read 1 until the window is mapped.

Mapping a window puts it on the maintainer's screen. A probe maps at alpha 0 instead: `_hide_until_ready()` is measurable, invisible, and nothing a stray click can disturb. `withdraw()` is not enough (`tk.Tk()` maps on construction, so withdrawing on the next line still flashes a frame).

**In a check, never `root.update()`.** It runs every tab's pending `after()` callbacks as well, and the Capture tab's prerequisite check then writes into its log, so a check reading that log fails on lines it never wrote. Map with `deiconify()` and `update_idletasks()`, as `check_tabs_build` does, and call a `<Map>`- or `<Configure>`-bound handler directly: no event loop runs to call it.

**A width of 1 after that is a notebook page that never mapped**, not a measurement. In a fresh root the notebook maps its page on the root's `<Map>`, a window event `update_idletasks()` does not deliver. Follow it with `ui.utils.presettle._drain(root, deadline)`, which runs window events and idle work and no timers (`check_important_settings._build_tab`).

**One UI scale per process when reading rendered text.** Tk caches a font given as a tuple per display, not per interpreter, so a second root in the same process lays some text out at the first root's size and every width read off it is wrong. `check_important_settings.run` measures each scale in a subprocess; `check_ui_scales` builds both in one and is sound only because it reads pads and named-font measures, never rendered widths.

| To check                        | Do this                                                                                             |
| ------------------------------- | --------------------------------------------------------------------------------------------------- |
| Which widgets a change moved    | Build the tabs the `check_tabs_build.py` way, snapshot every row's values before and after, diff     |
| A rendered GAP, in pixels       | `zRUN Spacing Audit Verbose.bat` — every registered gap at both scales, read off the rendered window. Invisible; needs no asking |
| Something only the screen shows | A side-by-side repro in `_tmp/` — the maintainer runs it, so it goes in the repo, not the scratchpad |
