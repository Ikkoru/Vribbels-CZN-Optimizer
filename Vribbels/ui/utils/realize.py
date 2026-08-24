"""Force widget windows into existence before their tab is first shown.

**This is what stops the white flash**, and every line of it looks like
dead code: it calls one method for its side effect and throws the answer
away.

Tk defers creating a widget's underlying Win32 window until the widget is
first MAPPED. A window created at map time is erased to the system default
background -- near-white -- before Tk gets to paint it in the widget's own
colours, so the first time a tab is opened its classic Tk widgets appear
as blank light-grey blocks for a frame. `winfo_id()` calls
`Tk_MakeWindowExist`, which creates the window NOW, with the widget's `bg`
already on it. There is then nothing left to erase when the map happens.

Measured, in `_tmp/flash_repro.py` over two rounds:

* Classic `tk.*` widgets flash on their first map; `ttk` widgets never do.
  Both are walked here anyway -- the call is harmless on a ttk widget, and
  a list of "which classes flash" is a thing to get wrong later.
* It is not the parent (a `tk.Frame` with an explicit `bg` flashed too),
  and not the indicator (`indicatoron=0` flashed too).
* The blocks are BLANK, which is what says the area is erased rather than
  painted wrong.
* The Optimizer tab never flashed, because its page is mapped while the
  window itself is still hidden -- which is the same fix by accident, and
  the reason a tab-by-tab hunt kept coming back inconsistent.

So this must run while the window is still invisible, and it must reach
widgets that no tab has displayed yet.

There are two callers, and both are needed:

* `_reveal_window` walks the whole tree once, covering everything built
  during startup. This is the one that scales -- a widget added to any
  `setup_ui` later is covered without anybody remembering it exists.
* `make_checkbox` calls `winfo_id()` on each widget it builds, because
  three panels rebuild their checkboxes AFTER startup (Capture's log
  presets, and Memory Fragments' Sets and unknown main stats), and those
  widgets are created long after the walk below has run.
"""

import tkinter as tk


def realize_windows(widget) -> int:
    """Create the Win32 window for `widget` and every descendant.

    Returns how many were walked, for the startup log -- the count is
    the only evidence the walk reached anything, since the work itself
    is invisible.

    A widget destroyed mid-walk raises `TclError`; that is not worth
    failing a startup over, so it is skipped along with its children.
    """
    seen = 0
    queue = [widget]
    while queue:
        w = queue.pop()
        try:
            w.winfo_id()
            queue.extend(w.winfo_children())
        except tk.TclError:
            continue
        seen += 1
    return seen
