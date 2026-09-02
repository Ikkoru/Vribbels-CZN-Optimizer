# UI runtime: threading and startup

Read before adding to the startup path or doing work off the UI thread. Layout and pixels are in `ui_spacing.md`.

## Nothing on the Tk main thread may block — `after()` callbacks included

A blocked callback stops Tk processing events entirely: the window stays painted but dead, Windows serves a cached taskbar thumbnail, Aero Peek shows bare desktop, and the thumbnail's close button does nothing.

Both startup prerequisite checks are split for this reason — the Setup tab's `check_status` and the Capture tab's `check_capture_prerequisites` hand the work to a worker (`_probe_prerequisites` / `_probe_capture_prerequisites`) and collect the answer through a main-thread poll (`_poll_probe` / `_poll_capture_prerequisites`).

External calls carry `timeout=`, `stdin=DEVNULL` and `CREATE_NO_WINDOW`; without the last a console window flashes over the UI. **A timeout alone is not enough**: a killed child's grandchildren can hold the inherited pipe open past it. That is what makes `python --version` hang forever on a machine without Python, where bare `python` hits the Microsoft Store's app-execution alias, opens the Store and never closes the pipe.

Any new external-program or network call belongs on a worker thread.

## A worker thread must not call `root.after()`

It only works while the main thread is inside `mainloop()`. Before it (startup, including the reveal's `update()` passes) or after it (shutdown), Tk raises `RuntimeError: main thread is not in main loop` and kills the worker. Anything scheduled during startup can land there.

The pattern that works, used by both prerequisite probes and by `_report_data_problems`: the worker assigns a plain attribute, and a main-thread `after` chain polls for it. Where a poll would be overkill — `capture_log_msg`, reached from the proxy-reader thread — the cross-thread `after` is wrapped in `try/except (RuntimeError, TclError)` and the message dropped, since outside mainloop there is no live log to write to.

## Diagnosing an unresponsive window

`debug_perf_log` in `settings/settings.json` also arms a hang watchdog: `_start_hang_watchdog` dumps every thread's stack to `settings/hang_traceback.txt` every 30s. **First thing to reach for on any "window is up but unresponsive" report** — it names the blocking call outright, which reasoning from symptoms reliably fails to do.

## The main window is hidden for the whole of startup

`tk.Tk()` maps a window the moment it is created, so `OptimizerGUI.__init__` calls `_hide_until_ready()` as its first act and `_reveal_window()` as its last. Everything between is built, loaded and drawn off-screen.

`_hide_until_ready` prefers **alpha 0** to `withdraw()`: a transparent window is still MAPPED, so children realize their true sizes and `winfo_width` / `bbox` return real numbers. That also makes it the way to measure rendered geometry in a probe without putting a window on the maintainer's screen.

`_reveal_window()` settles with full `update()` passes, NOT `update_idletasks()`: geometry runs in idle handlers, but the `<Configure>` events geometry generates and the redraws that follow are ordinary events, so draining only idle work reveals a window one layout pass short and partly unpainted.

Two consequences: startup code MAY pump the event loop to realize geometry (the exclude flow layout depends on this to measure its true width), and anything added to the startup path must not reveal the root early or pop its own window.

## Every widget's window is created before its tab is first shown

Tk defers creating a widget's Win32 window until first MAP, and a window created at map time is erased to the system default — near-white — before Tk paints it in the widget's own colours. So the first time a tab opens, its classic Tk widgets appear as blank light-grey blocks for a frame.

`_reveal_window` walks the tree and calls `winfo_id()` on every widget (`ui/utils/realize.py`), creating the windows while the app is still invisible, so there is nothing left to erase. ~55ms over ~500 widgets.

**`make_checkbox` makes the same call per widget, and that is not redundant.** Three panels rebuild their checkboxes after startup — Capture's log presets, Memory Fragments' Sets and its unknown main stats — long after the walk has run. Both callers are needed.

Measured, over three rounds of side-by-side repros:

- Classic `tk.*` widgets flash on first map; `ttk` widgets never do. The walk covers both anyway — a list of "which classes flash" is a thing to get wrong later.
- Not the parent (a `tk.Frame` with an explicit `bg` flashed too) and not the indicator (`indicatoron=0` flashed too).
- The blocks are BLANK, which is what says the area is ERASED rather than painted wrong.
- The Optimizer tab never flashed, because `_reveal_window` already gives its page a mapped layout pass while the window is hidden — the same fix by accident, and why a tab-by-tab hunt kept coming back inconsistent.

### A ScrolledText flashes for a SECOND reason, which is why the app builds its own

`scrolledtext.ScrolledText` builds its own wrapping `tk.Frame` and `tk.Scrollbar`, and neither is reachable through the constructor — every keyword goes to the Text. So the frame keeps Tk's near-white default and paints before the Text covers it.

**Realizing the window early cannot fix that**, because the frame's background genuinely IS white; there is nothing to create earlier. Equally, colouring the frame does not remove the map-time erase.

`ui/utils/scrolled_text.py` answers the colour half at the source: it builds the same shape — a Text and a vertical scrollbar in a wrapper, with the wrapper's geometry methods copied onto the Text so a caller packs the pair by packing what it was handed — out of a `ttk.Frame` and a `ttk.Scrollbar`, which the theme reaches directly. All three scrolled texts go through it, and the map-time erase is still the walk's job.

Recolouring each wrapper by hand does the same job and fails the same way every time one is missed: the panel that was skipped is the only one that flashes, which reads as the walk having failed rather than as a colour nobody set.

A `ttk.Scrollbar` asks for less width than a `tk` one, so the three texts are that much wider than the same shape built by hand, and their wrap points differ accordingly.

### The guard

`checks/check_no_flash.py` guards the SOURCE, since losing any of this is invisible from a headless run: the walk must be called from `_reveal_window`, `make_checkbox` must keep its own call, and no file may build a `Checkbutton` or a `ScrolledText` outside the module that owns it.

## Pre-startup dialogs use native Win32, not tkinter

The admin prompt uses `MessageBoxW` via `_win_message`. It runs before `OptimizerGUI` builds the Tk root, and a throwaway root there — built, destroyed, then the real one built after — leaves the real window unable to pump events. tkinter's messagebox wraps this same dialog on Windows, so there is no visual difference. The "Already Running" branch does build a Tk root, safe only because the process exits immediately after.

## The Optimizer tab builds into an unmapped `content` frame

`setup_ui` packs it as its very last statement. Belt-and-braces with the hidden window, and it keeps the tab atomic if it is ever rebuilt after startup. Don't parent new top-level tab sections to `self.frame`; use `content`.

## The exclude checklist's flow layout must not create widgets per re-flow

Checkbuttons are created once per combatant (`_exclude_checkbutton`) and positioned by `place()`; a re-flow moves them. Destroying and recreating ~40 classic Tk widgets on every `<Configure>` is the cost that rules it out, and pooled row *frames* can't help (a Tk widget can't change parent).

**Its row pitch and column flow are derived from `winfo_reqheight()` and `winfo_reqwidth()`**, so anything that changes a checkbutton's size moves the gap between rows with it — as `make_checkbox`'s zeroed border and focus ring did, by 6px. See `ROW_PITCH_OFFSET`, and keep it positive: a negative offset makes rows overlap and clip each other.

The panel's own width is an explicit layout preference, never derived from its children — content-driven width closes a content → width → `<Configure>` → content loop. Only the height follows the content.

## The frozen build re-launches itself for every worker

Windows spawn relaunches the executable per multiprocessing worker. `multiprocessing.freeze_support()` must stay the FIRST statement in the `__main__` guard: it detects those launches and runs the multiprocessing bootstrap instead of the GUI. Every other side effect (single-instance lock, admin prompt, Tk roots) must stay inside `main()`, so a spawned worker importing the module never triggers them and never trips the single-instance lock. The parallel path keeps a persistent session pool, so the onefile spawn cost is paid once.

## Display rules that look like bugs

- **Memory Fragments, Highest Potential column:** for fully-levelled MFs (low == high under every preset) the display is `-`, not `low-high`. The Highest GS column already shows the value.
- **`refresh_inventory` must NOT clear the tree.** `_display_inventory_sorted` clears it immediately after reading the current selection, which is what restores the highlight onto the same fragments across a live update. Clearing earlier drops the selection before it can be read.
