# UI runtime: threading and startup

Read before adding to the startup path or doing work off the UI thread. Layout and pixels are in `ui_spacing.md`.

## Nothing on the Tk main thread may block — `after()` callbacks included

A blocked callback stops Tk processing events entirely: the window stays painted but dead, Windows serves a cached taskbar thumbnail, Aero Peek shows bare desktop, and the thumbnail's close button does nothing.

Both startup prerequisite checks are split for this reason — the Setup & Settings tab's `check_status` and the Capture tab's `check_capture_prerequisites` hand the work to a worker (`_probe_prerequisites` / `_probe_capture_prerequisites`) and collect the answer through a main-thread poll (`_poll_probe` / `_poll_capture_prerequisites`).

External calls carry `timeout=`, `stdin=DEVNULL` and `CREATE_NO_WINDOW`; without the last a console window flashes over the UI. **A timeout alone is not enough**: a killed child's grandchildren can hold the inherited pipe open past it. That is what makes `python --version` hang forever on a machine without Python, where bare `python` hits the Microsoft Store's app-execution alias, opens the Store and never closes the pipe.

Any new external-program or network call belongs on a worker thread.

## A worker thread must not call `root.after()`

It only works while the main thread is inside `mainloop()`. Before it (startup, including the reveal's `update()` passes) or after it (shutdown), Tk raises `RuntimeError: main thread is not in main loop` and kills the worker. Anything scheduled during startup can land there.

**Inside mainloop it is still a wait.** tkinter hands a Tk call made on another thread to the main thread and blocks until the main thread has run it, so the worker stalls for as long as the main thread is busy -- a second behind a snapshot reload.

The pattern that works, used by both prerequisite probes, by `_report_data_problems` and by the capture: the worker assigns a plain attribute or puts on a queue, and a main-thread `after` chain polls for it. The capture's is `OptimizerGUI._poll_capture` over the Capture tab's inbox -- see "Logging from the proxy reader thread" in `capture_pipeline.md`.

## Diagnosing an unresponsive window

`debug_perf_log` in `settings/settings.json` also arms a hang watchdog: `_start_hang_watchdog` dumps every thread's stack to `settings/hang_traceback.txt` every 30s. **First thing to reach for on any "window is up but unresponsive" report**: it names the blocking call outright.

## The main window is hidden for the whole of startup

`tk.Tk()` maps a window the moment it is created, so `OptimizerGUI.__init__` calls `_hide_until_ready()` as its first act and `_reveal_window()` as its last. Everything between is built, loaded and drawn off-screen.

`_hide_until_ready` prefers alpha 0 to `withdraw()`: a transparent window is still MAPPED, so children realize their true sizes and `winfo_width` / `bbox` return real numbers. That also makes it the way to measure rendered geometry in a probe without putting a window on the maintainer's screen.

`_reveal_window()` settles with full `update()` passes, NOT `update_idletasks()`: geometry runs in idle handlers, but the `<Configure>` events geometry generates and the redraws that follow are ordinary events, so draining only idle work reveals a window one layout pass short and partly unpainted.

Two consequences: startup code MAY pump the event loop to realize geometry (the exclude flow layout depends on this to measure its true width), and anything added to the startup path must not reveal the root early or pop its own window.

## Most tabs are built after the reveal

Startup builds three tabs:

- the Optimizer, which a launch opens on;
- Gear Score, whose weights score every fragment on every load;
- Capture, where the capture's and the startup jobs' log lines land.

Setup & Settings joins them on a first launch, which opens on it. Every other tab is a slot of `ui/utils/lazy_tabs.py`: an empty placeholder page under the tab's title, replaced by the tab when it is built. That happens on the first of:

- the idle settler's step for it (below), the ordinary case;
- the user selecting it first, which builds it with painting off and paints it once, whole;
- anything that needs the tab itself: a reload the Checklist has to record from first, or the spacing audit.

**Any tab's first show is held until the tab is whole**, built or not: a placeholder, a tab a step built but has not laid out, or Gear Score and Capture before their step. `LazyTabs` switches painting off in the first tab-changed handler and ends the hold with a queued `<<LazyTabShown>>`, so every tab's own handler runs inside it. A tab built already is never built again. Being built saves only the build's share of its first open: most of it is the layout and first draw, which only a settle step takes away.

Until then the app's handle on the tab is None. Four rules follow, and `checks/check_lazy_tabs.py` holds them:

- **Nothing calls through a handle that may be None.** A load tells only the tabs built so far (`_refresh_built_tabs`). A tab built later reads the data current then, in its `after_build`.
- **Both load paths build the Checklist before replacing a snapshot it has not read** (`_let_the_checklist_record`). It records from every snapshot, and the game purges what it records.
- **A first show comes back with painting on and painted**, in a `finally`.
- **`LazyTabs` is created before any tab.** Its handler has to be the first bound; a tab's own handler ahead of it draws in view, before painting goes off.

One more, held by `checks/check_style_once.py`: **no tab's build may change a ttk style.** Any style change re-measures every themed widget, and after the reveal that lays out again the tabs already laid out. A stretching Treeview column then asks for the space it had filled, and the Combatants list keeps 6px of its detail pane for the session. So each style a tab uses is defined once per interpreter (`ui/utils/style_once.py`), at startup, from `OptimizerGUI.configure_styles`.

## Unopened tabs are laid out after the reveal, unseen

A notebook sizes only the page it shows, so every other page is 1px square until it is first opened, and that open lays the whole page out again after its first paint: the user watches it assemble. `_reveal_window` settles the Optimizer tab while the window is still hidden, and pays for it in startup time. Every other tab is settled by `ui/utils/presettle.py` after the reveal, one tab per idle moment:

1. Whatever is pending runs, painting on.
2. Painting on the notebook is switched off with `WM_SETREDRAW`. The screen keeps the pixels it had.
3. The tab is selected, and its window events and idle work run: the `<Configure>` cascade, and its `<Map>` and `<<NotebookTabChanged>>` first-show work.
4. The tab that was showing is selected again, drained the same way, and painting switched back on.

A tab not built yet is built in an idle step of its own, and settled in the next. Nothing is mapped by a build, so it needs no painting off; and each half is a pause of its own, shorter than the two together.

Six rules keep it unseen, and breaking any of them fails silently. `checks/check_presettle.py` holds all six:

- **Painting comes back on in a `finally`.** Otherwise the notebook stays frozen on its last picture.
- **The drain runs window and idle events only, never `update()`.** Timers would run with painting off, and a capture reload's redraw would never reach the screen.
- **The way back is drained with painting still off.** Left to the ordinary loop, the notebook repaints the page area's background, and the page's widgets never paint over it.
- **The Capture tab is skipped.** Its switch handlers clear its failure mark and start and stop its log title's pulse.
- **A step's tab counts as laid out before it is selected.** The settler shares `LazyTabs.shown`; the selection's event arrives mid-step, and a first show there would switch painting back on with the settled tab on screen.
- **What is pending runs before painting goes off.** A paint still owed to the tab on screen, spent with painting off, leaves its old pixels showing.

A step still holds the UI thread while its tab lays out, and while painting is off the notebook is out of hit-testing. So when a step may start has rules of its own:

- **Input that reaches the window holds it back** for `IDLE_MS`: the pointer over the window's content, a click, a key, the wheel, noted from the reveal by `track_input`. The title bar and other programs hold nothing back.
- **A held mouse button holds it back** while the program is in front: a drag of the title bar or a border is nothing else Tk sees.
- **The pointer moving does not, in two windows**: `LAUNCH_MS` after the reveal, and `SWITCH_MS` after a tab switch, from `SWITCH_WAIT_MS` in. A click, a key or the wheel closes either.
- **A click during a settle step lands behind the notebook.** One on a tab is given back once painting is (`replay_lost_tab_click`); one on a tab's contents is lost. A build step holds no painting and only delays a click, so the switch window, after which the next click is likely on the new tab's contents, runs builds only.

Nothing is settled under the spacing audit, which switches tabs itself.

With `debug_perf_log` on, the log records what the windows' lengths are chosen from: `presettle:switch` lines, how soon the user acted and switched after the reveal and after each switch; `presettle:step`, each step and what let it start; `lazy_tabs:first_show`, what each first show cost.

The Checklist and Memory Fragments are settled first. Both leave their drawing to their first show (see *A hidden tab draws when shown, but records now*), so they are the costliest to open before their step.

## Every widget's window is created before its tab is first shown

Tk defers creating a widget's Win32 window until first MAP, and a window created at map time is erased to the system default — near-white — before Tk paints it in the widget's own colours. So the first time a tab opens, its classic Tk widgets appear as blank light-grey blocks for a frame.

`_reveal_window` walks the tree and calls `winfo_id()` on every widget (`ui/utils/realize.py`), creating the windows while the app is still invisible, so there is nothing left to erase. `TabSlot.build` walks each tab built after the reveal the same way, before anything maps it.

**`make_checkbox` makes the same call per widget, and that is not redundant.** Three panels rebuild their checkboxes after startup — Capture's log presets, Memory Fragments' Sets and its unknown main stats — long after either walk has run. All three callers are needed.

What the flash is and is not:

- Classic `tk.*` widgets flash on first map; `ttk` widgets never do. The walk covers both anyway — a list of "which classes flash" is a thing to get wrong later.
- Not the parent (a `tk.Frame` with an explicit `bg` flashed too) and not the indicator (`indicatoron=0` flashed too).
- The blocks are BLANK, which is what says the area is ERASED rather than painted wrong.
- The Optimizer tab never flashes: `_reveal_window` already gives its page a mapped layout pass while the window is hidden. A tab-by-tab hunt therefore reads as inconsistent.

### A ScrolledText flashes for a SECOND reason, which is why the app builds its own

`scrolledtext.ScrolledText` builds its own wrapping `tk.Frame` and `tk.Scrollbar`, and neither is reachable through the constructor — every keyword goes to the Text. So the frame keeps Tk's near-white default and paints before the Text covers it.

**Realizing the window early cannot fix that**, because the frame's background genuinely IS white; there is nothing to create earlier. Equally, colouring the frame does not remove the map-time erase.

`ui/utils/scrolled_text.py` answers the colour half at the source: it builds the same shape — a Text and a vertical scrollbar in a wrapper, with the wrapper's geometry methods copied onto the Text so a caller packs the pair by packing what it was handed — out of a `ttk.Frame` and a `ttk.Scrollbar`, which the theme reaches directly. All three scrolled texts go through it, and the map-time erase is still the walk's job.

**A wrapper recoloured by hand instead reads as a walk failure when one is missed**: only the skipped panel flashes.

A `ttk.Scrollbar` asks for less width than a `tk` one, so the three texts are that much wider than the same shape built by hand, and their wrap points differ accordingly.

### The guard

`checks/check_no_flash.py` guards the SOURCE, since losing any of this is invisible from a headless run: the walk must be called from `_reveal_window`, `make_checkbox` must keep its own call, and no file may build a `Checkbutton` or a `ScrolledText` outside the module that owns it.

## Pre-startup dialogs use native Win32, not tkinter

The admin prompt uses `MessageBoxW` via `_win_message`. It runs before `OptimizerGUI` builds the Tk root, and a throwaway root there — built, destroyed, then the real one built after — leaves the real window unable to pump events. tkinter's messagebox wraps this same dialog on Windows, so there is no visual difference. The "Already Running" branch does build a Tk root, safe only because the process exits immediately after.

## The Optimizer tab builds into an unmapped `content` frame

`setup_ui` packs it as its very last statement. Redundant with the hidden window, and it keeps the tab atomic if it is ever rebuilt after startup. Don't parent new top-level tab sections to `self.frame`; use `content`.

## A rebuild on the load path is gated on what it would draw

A panel that destroys its children and builds them again blinks: between the destroy and the next paint there is a hole where the widgets were, and a login burst saves the snapshot several times in a few seconds — so a refresh wired to the data load runs two or three times while the user watches.

Four panels rebuild real widgets after startup, and each is gated on a SIGNATURE computed before anything is destroyed, holding everything the rebuild would read:

| Panel | Method | What the gate holds |
| ----- | ------ | ------------------- |
| Capture's Log Presets | `refresh_log_presets` | the presets and their assignments |
| Memory Fragments' Sets | `populate_set_filters` | each set name with the number owned, in layout order |
| Memory Fragments' unknown mains | `populate_unknown_main_stats` | the unknown main-stat names |
| Optimizer's Exclude Combatant's MFs | `refresh_exclude_heroes` | the roster, the excluded set, the selected combatant |
| The Checklist's columns | `_rebuild_columns` | per column, the row keys and what `_fill` cannot patch |

**Width belongs in the signature wherever the layout is solved from the built widgets' own `winfo_reqwidth()`** — the exclude list's flow is, so it re-flows on `<Configure>`; the Sets grid is five columns whatever the window does, and its column widths are measured off the counts already in the signature.

`checks/check_tabs_build.py` holds each of these to widget IDENTITY: same inputs in, the same objects still on screen. Comparing the labels would pass while every widget behind them was replaced.

Treeview and Listbox rebuilds are not this: their rows are not widgets, and clearing one repaints inside a single widget with no hole to see.

## A hidden tab draws when shown, but records now

A snapshot load while another tab is showing skips three tabs' drawing, and each catches up in its `<<NotebookTabChanged>>` handler when shown:

- Materials: `refresh_materials`, with a `_stale` flag.
- Memory Fragments: `refresh_inventory`, the same way.
- The Checklist: `refresh_checklist`, which redraws on every show anyway.

A capture reloads after every save while the user is usually on another tab, and startup loads with the Optimizer tab showing.

**Only drawing may wait.** The Checklist's refresh records as it reads: event totals, final rewards, the floor clock, the currency ledger. A record has to come from every snapshot, because the game purges what it is read from. So that refresh runs all of its recording and returns just before its columns are built.

`_hidden()` counts a notebook with nothing selected as showing. That is how the checks build a tab, and how every tab is built before the notebook gets its pages.

## The exclude checklist's flow layout must not create widgets per re-flow

Checkbuttons are created once per combatant (`_exclude_checkbutton`) and positioned by `place()`; a re-flow moves them. Destroying and recreating ~40 classic Tk widgets on every `<Configure>` is the cost that rules it out, and pooled row *frames* can't help (a Tk widget can't change parent).

**Its row pitch and column flow are derived from `winfo_reqheight()` and `winfo_reqwidth()`**, so anything that changes a checkbutton's size moves the gap between rows with it — as `make_checkbox`'s zeroed border and focus ring did, by 6px. See `ROW_PITCH_OFFSET`, and keep it positive: a negative offset makes rows overlap and clip each other.

The panel's own width is an explicit layout preference, never derived from its children — content-driven width closes a content → width → `<Configure>` → content loop. Only the height follows the content.

## A mapped Treeview asks for a new size only on `configure`

Once a Treeview is mapped, a column's new width changes what it draws but not what it asks its container for, and reassigning `columns` asks for 200px a column whatever widths follow. Before the first map it tracks its columns, so a list built once and never rewritten is never caught out; one rewritten while shown keeps its old size, and the only symptom is a list too wide or clipped for its content.

The Stats & Gacha History tab's standings lists rebuild their columns on every load, so `_write_standings` ends each list with a `configure(height=...)` that looks redundant: it is what makes the list ask again. `check_tabs_build` writes them twice while mapped and holds every list's requested width to its columns'.

The same tab's Banners list takes the window's spare width in its last column, again on every resize, and `_fit_banners` follows it with the same `configure`. There the symptom hides itself: a stretching last column fills the list's OLD width back out, so the columns always add up and the list simply never changes size. `check_tabs_build` resizes and holds the change the list's width makes.

## The frozen build re-launches itself for every worker

Windows spawn relaunches the executable per multiprocessing worker. `multiprocessing.freeze_support()` must stay the FIRST statement in the `__main__` guard: it detects those launches and runs the multiprocessing bootstrap instead of the GUI. Every other side effect (single-instance lock, admin prompt, Tk roots) must stay inside `main()`, so a spawned worker importing the module never triggers them and never trips the single-instance lock. The parallel path keeps a persistent session pool, so the onefile spawn cost is paid once.

## The title bar is Windows' own, coloured through DWM

Tk cannot draw the caption; `ui/title_bar.py` sets it as window attributes, the colours on Windows 11 and dark or light by the system's app theme on Windows 10, and says which builds take which. It is set on the main window at the end of `_reveal_window`, still at alpha 0, so the caption never paints in the default first; the two Toplevel dialogs set it where they first map. The native message and file dialogs keep Windows' default. Its height is Windows' too and has no attribute: changing it means drawing a title bar of our own. `check_tabs_build` holds every attribute to Windows accepting it, since a refusal is an error code the caption simply ignores.

## Display rules that look like bugs

- **Memory Fragments, Highest Potential column:** for fully-levelled MFs (low == high under every preset) the display is `-`, not `low-high`. The Highest GS column already shows the value.
- **`refresh_inventory` must NOT clear the tree.** `_display_inventory_sorted` clears it immediately after reading the current selection, which is what restores the highlight onto the same fragments across a live update. Clearing earlier drops the selection before it can be read.
