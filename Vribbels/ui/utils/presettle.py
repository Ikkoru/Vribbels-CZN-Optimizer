"""Lay out the tabs nobody has opened yet, while nobody is looking.

**A tab that has never been shown has never been given its size.** The
notebook sizes only the page it shows, so every other page is 1px
square and everything in it is laid out for that. The first open gives
it its real size, and the whole page lays itself out again -- AFTER its
first paint, so the user watches it assemble: panels arriving, text
re-wrapping, contents resizing into their frames.

Settling a tab while the window is still hidden fixes that, but costs
startup time for a tab the user may never open, which is why
`_reveal_window` does it for the Optimizer tab alone. Every other tab
is settled here, after the window is up, one at a time and only while
the user leaves the program alone:

1. Painting on the notebook is switched off (`WM_SETREDRAW`). Windows
   keeps showing the pixels it had, and the notebook's windows drop
   out of hit-testing, so nothing below changes what is on screen.
2. The tab is selected and its pending work run: its window events --
   the `<Configure>` cascade that is the whole point -- and its idle
   work. NOT timers: see `_drain`.
3. The tab that was showing is selected again, its work run the same
   way, and painting switched back on. What it redrew was drawn with
   painting off, and it redrew what was already on screen.

A step still takes the UI thread for as long as the tab takes to lay
out; Tk has no other. So a step runs only when the user has not touched
the program for `IDLE_MS`, and yields to the event loop between tabs.
The first open of a settled tab is then a paint and nothing more.

**The Capture tab is never settled here, and nothing is settled while
it is the tab showing.** Its switch handlers act on what the user saw:
selecting it clears its failure mark and starts its log title's pulse,
and leaving it stops the pulse. A tab switched to and from behind the
user's back would do both for nobody.

Windows only: `WM_SETREDRAW` is what makes a step invisible, and without
it a step would flash the tab being settled.
"""

import ctypes
import sys
import time
import tkinter as tk

from _tkinter import DONT_WAIT, IDLE_EVENTS, WINDOW_EVENTS

# When the first step is tried, after the reveal. Long enough for the
# startup's own after-callbacks to have run; short, because a tab
# opened before its step pays for its whole layout in view.
START_MS = 500
# How long the user must have left the program alone before a step.
IDLE_MS = 400
# The pause between one step and the next, so the ordinary event loop
# -- the capture's poll, the user's input -- gets its turn.
GAP_MS = 150
# How soon to look again when the user is busy.
RETRY_MS = 300
# A step that has not drained by now gives up draining and switches
# painting back on; whatever is left runs in the ordinary loop, in view.
STEP_LIMIT_S = 3.0

WM_SETREDRAW = 0x000B
RDW_INVALIDATE, RDW_ALLCHILDREN = 0x0001, 0x0080
MOUSE_BUTTONS = (0x01, 0x02, 0x04)      # VK_LBUTTON, VK_RBUTTON, VK_MBUTTON


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint32)]


def _last_input_tick():
    """The tick of the last keyboard or mouse input anywhere, or None."""
    info = _LastInput()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return info.dwTime


def _user_is_busy(root):
    """Whether a step now could get in the user's way.

    Not while a mouse button is held -- a drag in progress -- and not
    within `IDLE_MS` of the last input while the window is the one in
    front. Behind another window, the user is not using this one.
    """
    user32 = ctypes.windll.user32
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in MOUSE_BUTTONS):
        return True
    try:
        front = user32.GetForegroundWindow() == int(root.wm_frame(), 16)
    except (tk.TclError, ValueError):
        front = True
    if not front:
        return False
    tick = _last_input_tick()
    if tick is None:
        return False
    since = (ctypes.windll.kernel32.GetTickCount() - tick) & 0xFFFFFFFF
    return since < IDLE_MS


def _drain(root, deadline):
    """Run the pending window events and idle work, and nothing else.

    **Never `update()`.** That runs every due timer as well, and a
    timer in here would run with painting off: the capture's poll can
    reload a snapshot and redraw the tab on screen, and none of that
    redraw would reach the screen. Window events and idle work are
    what laying a page out consists of.

    True when everything pending ran, False when the deadline cut it
    short.
    """
    flags = WINDOW_EVENTS | IDLE_EVENTS | DONT_WAIT
    while root.tk.dooneevent(flags):
        if time.monotonic() > deadline:
            return False
    return True


class HiddenTabSettler:
    """Settles every tab but the one showing and `skip`, one per idle
    moment, `first` before the rest. See the module docstring."""

    def __init__(self, root, notebook, skip=(), first=()):
        self.root = root
        self.notebook = notebook
        self._skip = {str(w) for w in skip}
        self._settled = {notebook.select()}
        ahead = [str(w) for w in first]
        order = ahead + [t for t in notebook.tabs() if t not in ahead]
        self._queue = [t for t in order
                       if t not in self._skip and t not in self._settled]
        # A tab the user opens is settled by being opened.
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed,
                      add="+")

    def start(self):
        if sys.platform != "win32" or not self._queue:
            return
        self._after(START_MS)

    def _on_tab_changed(self, _event=None):
        try:
            self._settled.add(self.notebook.select())
        except tk.TclError:
            pass

    def _after(self, ms):
        try:
            self.root.after(ms, self._next)
        except tk.TclError:
            pass                        # the window is closing

    def _next(self):
        self._queue = [t for t in self._queue if t not in self._settled]
        if not self._queue:
            return
        try:
            showing = self.notebook.select()
        except tk.TclError:
            return
        if showing in self._skip or _user_is_busy(self.root):
            self._after(RETRY_MS)
            return
        self._settle(self._queue.pop(0), showing)
        self._after(GAP_MS)

    def _settle(self, tab, showing):
        """One step: `tab` laid out behind the pixels of `showing`."""
        notebook = self.notebook
        hwnd = int(notebook.winfo_id())
        user32 = ctypes.windll.user32
        before = _last_input_tick()
        deadline = time.monotonic() + STEP_LIMIT_S
        user32.SendMessageW(hwnd, WM_SETREDRAW, 0, 0)
        try:
            notebook.select(tab)
            _drain(self.root, deadline)
            # Unless the user changed tabs meanwhile, which is theirs.
            if notebook.select() == tab:
                notebook.select(showing)
            # **Drained with painting still off**, the way back as much
            # as the way there. Left to the ordinary loop, the notebook's
            # own relayout repaints the page area's background, and the
            # page's widgets -- which Tk believes are already drawn --
            # never paint over it: the tab on screen goes blank in
            # patches until something redraws each one.
            _drain(self.root, deadline)
        finally:
            # NOT optional, whatever went wrong above: a notebook left
            # with painting off never repaints again.
            user32.SendMessageW(hwnd, WM_SETREDRAW, 1, 0)
            # Input that arrived during the step drew nothing, so its
            # effect is on no pixel yet. Repaint what it could have
            # touched.
            if _last_input_tick() != before:
                user32.RedrawWindow(hwnd, None, None,
                                    RDW_INVALIDATE | RDW_ALLCHILDREN)
        self._settled.add(tab)


def settle_hidden_tabs(root, notebook, skip=(), first=()):
    """Start settling every tab but the one showing and `skip`, in
    idle moments, `first` before the rest. Returns the settler, which
    the caller keeps."""
    settler = HiddenTabSettler(root, notebook, skip, first)
    settler.start()
    return settler
