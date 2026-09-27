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

1. Whatever is pending runs first, painting on: a paint still owed to
   the tab on screen, spent with painting off, would leave it showing
   its old pixels.
2. Painting on the notebook is switched off (`WM_SETREDRAW`). Windows
   keeps showing the pixels it had, and the notebook's windows drop
   out of hit-testing, so nothing below changes what is on screen.
3. The tab is selected and its pending work run: its window events --
   the `<Configure>` cascade that is the whole point -- and its idle
   work. NOT timers: see `_drain`.
4. The tab that was showing is selected again, its work run the same
   way, and painting switched back on. What it redrew was drawn with
   painting off, and it redrew what was already on screen.

A step still takes the UI thread for as long as the tab takes to lay
out; Tk has no other. So steps run while the user is not using the
program, and yield to the event loop between tabs. The first open of a
settled tab is then a paint and nothing more.

**Using the program means input that reaches it**: the pointer moving
over its window's content, a click, a key, the wheel -- noted by a
binding on every widget (`track_input`). The title bar, other windows,
and typing into another program are none of these, and hold nothing
back. A held mouse button does while one of this program's windows is
in front: a drag of the title bar or a border is a held button and
nothing else Tk sees.

**A click on the notebook during a settle step lands behind it**: its
windows are out of hit-testing, so the click reaches the window below.
One on a tab is replayed once painting is back
(`replay_lost_tab_click`); one on a tab's contents is lost. A build
step holds no painting, and only delays a click.

**Two windows let the pointer move**, while the user cannot yet be
about to click: just after the window appears, and just after each
tab switch -- `LAUNCH_MS` and `SWITCH_MS`. A click, a key or the wheel
closes either, and steps inside one follow each other closely. After
a switch, the next click is likely on the new tab's contents, so that
window runs build steps only; after the reveal it is likely on a tab,
which a settle step gives back.

**The Capture tab is never settled here, and nothing is settled while
it is the tab showing.** Its switch handlers act on what the user saw:
selecting it clears its failure mark and starts its log title's pulse,
and leaving it stops the pulse. A tab switched to and from behind the
user's back would do both for nobody.

Windows only: `WM_SETREDRAW` is what makes a step invisible, and without
it a step would flash the tab being settled.
"""

import ctypes
import os
import sys
import time
import tkinter as tk

from _tkinter import DONT_WAIT, IDLE_EVENTS, WINDOW_EVENTS

import perf_log

# When the first step is tried, after the reveal: soon, since the user
# cannot act on a window they have not seen yet, but after the work
# startup queued behind the reveal.
FIRST_MS = 50
# How long the user must have left the program alone before a step,
# outside the two windows.
IDLE_MS = 400
# Until this long after the reveal, the pointer moving does not hold a
# step back. The quickest first click in the perf log's
# `presettle:switch` lines (`first_act_ms`), less the longest step: a
# step started by then is over before the user can click.
LAUNCH_MS = 650
# After a tab switch, how long before a step may start -- the new tab
# paints first -- and until when the pointer moving does not hold one
# back.
SWITCH_WAIT_MS = 100
SWITCH_MS = 250
# The pause between one step and the next, so the ordinary event loop
# -- the capture's poll, the user's input -- gets its turn. Shorter
# inside a window, which is short itself.
GAP_MS = 150
WINDOW_GAP_MS = 20
# How soon to look again while a held button holds a step back.
RETRY_MS = 300
# A step that has not drained by now gives up draining and switches
# painting back on; whatever is left runs in the ordinary loop, in view.
STEP_LIMIT_S = 3.0

WM_SETREDRAW = 0x000B
RDW_INVALIDATE, RDW_ALLCHILDREN, RDW_UPDATENOW = 0x0001, 0x0080, 0x0100
MOUSE_BUTTONS = (0x01, 0x02, 0x04)      # VK_LBUTTON, VK_RBUTTON, VK_MBUTTON

# In Tcl, so that the bindings cost no trip into Python: a procedure
# call per event, well under a microsecond. `since` is when the
# tracking began -- the reveal, where the app starts it -- and
# `first_act` the first click, key or wheel since it was last cleared.
_TRACKING = r"""
namespace eval ::vribbels_input {
    variable since [clock milliseconds]
    variable move 0
    variable act 0
    variable press {}
}
proc ::vribbels_input::moved {} {
    variable move [clock milliseconds]
    variable first_move
    if {![info exists first_move]} {set first_move $move}
}
proc ::vribbels_input::acted {} {
    variable act [clock milliseconds]
    variable first_act
    if {![info exists first_act]} {set first_act $act}
}
proc ::vribbels_input::pressed {W X Y} {
    acted
    variable act
    variable press [list $act $W $X $Y]
}
bind all <Motion> {+::vribbels_input::moved}
bind all <KeyPress> {+::vribbels_input::acted}
bind all <ButtonPress> {+::vribbels_input::acted}
bind all <ButtonPress-1> {+::vribbels_input::pressed %W %X %Y}
bind all <MouseWheel> {+::vribbels_input::acted}
"""


def track_input(root):
    """Note the time of every input that reaches this program, from
    now on. Once per interpreter; the first call's time is `since`."""
    if root.tk.eval("namespace exists ::vribbels_input") == "1":
        return
    root.tk.eval(_TRACKING)


def _clock_ms(root):
    return int(root.tk.call("clock", "milliseconds"))


def _noted(root, name):
    """What `track_input` holds under `name`, as text.

    **As text, never through `tk.call`**, which hands over the Tcl
    object's type along with its value. A time not noted yet is the
    literal 0 -- one object Tcl shares with every script holding a 0 --
    and any of those reading it as a list makes it one: ttk's own
    `-padding 0` does. `tk.call` then returns `('0',)`, and the settler
    raised on it and stopped for the session."""
    return root.tk.eval("set ::vribbels_input::" + name)


def _input(root, name):
    """A time `track_input` noted, in `clock milliseconds`; 0 where it
    has noted none."""
    try:
        return int(_noted(root, name))
    except (tk.TclError, ValueError):
        return 0


def _held_in_front():
    """Whether a mouse button is down while one of this program's
    windows is the one in front."""
    user32 = ctypes.windll.user32
    if not any(user32.GetAsyncKeyState(key) & 0x8000
               for key in MOUSE_BUTTONS):
        return False
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(),
                                    ctypes.byref(pid))
    return pid.value == os.getpid()


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint32)]


def _last_input_tick():
    """The tick of the last keyboard or mouse input anywhere, or None.

    Anywhere, not just here: a drag of the window's border reaches Tk
    as nothing, yet resizes the notebook under a step."""
    info = _LastInput()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return info.dwTime


def replay_lost_tab_click(root, notebook, since_ms):
    """Select the tab a click went for, if the click came after
    `since_ms` while the notebook was out of hit-testing and so landed
    behind it. True if it did.

    Only a click on a tab: selecting it is all the notebook would have
    done. One on a tab's contents had a widget to reach and a state to
    find it in, and cannot be given back.
    """
    try:
        when, widget, x_root, y_root = root.tk.splitlist(
            _noted(root, "press"))
        if int(when) < since_ms:
            return False
        # Lost means it landed on what holds the notebook. One that
        # reached the notebook was handled; one on another window -- a
        # popup over the tab row -- was that window's.
        behind, holder = set(), notebook.master
        while holder is not None:
            behind.add(str(holder))
            holder = holder.master
        if widget not in behind:
            return False
        x = int(x_root) - notebook.winfo_rootx()
        y = int(y_root) - notebook.winfo_rooty()
        index = notebook.tk.call(str(notebook), "identify", "tab", x, y)
        if str(index) == "":
            return False
        notebook.select(int(index))
    except (tk.TclError, ValueError):
        return False
    if perf_log.is_enabled():
        perf_log.log("presettle:replayed_click",
                     tab=_tab_text(notebook, notebook.select()))
    return True


def _tab_text(notebook, page):
    try:
        return notebook.tab(page, "text")
    except tk.TclError:
        return "?"


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

    def __init__(self, root, notebook, skip=(), first=(), lazy=None):
        self.root = root
        self.notebook = notebook
        # The app's `LazyTabs`, or None: a queued page may be a
        # placeholder, built in its own step. See `lazy_tabs.py`.
        self._lazy = lazy
        self._skip = {str(w) for w in skip}
        # Shared with `LazyTabs`, whose first shows settle a tab as much
        # as a step does -- and which must know of a step's tab before
        # the step selects it.
        self._settled = lazy.shown if lazy is not None else set()
        self._settled.add(notebook.select())
        ahead = [str(w) for w in first]
        order = ahead + [t for t in notebook.tabs() if t not in ahead]
        self._queue = [t for t in order
                       if t not in self._skip and t not in self._settled]
        track_input(root)
        self._revealed_at = _input(root, "since")
        self._switched_at = None
        self._last_page = notebook.select()
        self._stepping = False
        self._pending = None
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed,
                      add="+")

    def start(self):
        if sys.platform != "win32" or not self._queue:
            return
        self._after(FIRST_MS)

    def _on_tab_changed(self, _event=None):
        """A switch the user made opens a switch window."""
        if self._stepping:
            return
        try:
            page = self.notebook.select()
        except tk.TclError:
            return
        if self._lazy is None:
            self._settled.add(page)
        # A placeholder's build selects the tab that replaces it: the
        # same switch, arriving twice.
        same = self._current(self._last_page) == page
        self._last_page = page
        if same:
            return
        now = _clock_ms(self.root)
        if perf_log.is_enabled():
            self._log_switch(page, now)
        self._switched_at = now
        self.root.tk.call("unset", "-nocomplain",
                          "::vribbels_input::first_act")
        if self._queue:
            self._after(SWITCH_WAIT_MS)

    def _log_switch(self, page, now):
        """How soon the user acted, and switched, after the reveal or the
        last switch: what `LAUNCH_MS` and `SWITCH_MS` are chosen from."""
        opened = self._switched_at or self._revealed_at
        acted = _input(self.root, "first_act")
        fields = {"tab": _tab_text(self.notebook, page),
                  "at_ms": now - self._revealed_at,
                  "after_ms": now - opened,
                  "first_act_ms": acted - opened if acted else "none"}
        if self._switched_at is None:
            moved = _input(self.root, "first_move")
            fields["first_move_ms"] = moved - opened if moved else "none"
        perf_log.log("presettle:switch", **fields)

    def _after(self, ms):
        """Try the next step in `ms`: the one try pending, never two."""
        if self._pending is not None:
            try:
                self.root.after_cancel(self._pending)
            except tk.TclError:
                pass
        try:
            self._pending = self.root.after(max(1, int(ms)), self._next)
        except tk.TclError:
            self._pending = None        # the window is closing

    def _current(self, tab):
        """What stands at `tab` now: a placeholder's built page, once it
        has been built -- by a step, a click, or a reload."""
        return self._lazy.current(tab) if self._lazy is not None else tab

    def _wait(self, settle):
        """(how long until a step may start, what lets it start then):
        0 for now, and "launch", "switch" or "idle". `settle` for a
        settle step, which a switch window does not take."""
        if _held_in_front():
            return RETRY_MS, None
        root = self.root
        now = _clock_ms(root)
        act, move = _input(root, "act"), _input(root, "move")
        if self._switched_at is not None:
            opened, lead, span, why = (self._switched_at, SWITCH_WAIT_MS,
                                       SWITCH_MS, "switch")
        else:
            opened, lead, span, why = self._revealed_at, 0, LAUNCH_MS, \
                "launch"
        # The click or key that made a switch comes just before it, and
        # does not close the window it opens.
        if (opened and act <= opened and now < opened + span
                and not (settle and why == "switch")):
            return max(0, opened + lead - now), why
        return max(0, max(act, move) + IDLE_MS - now), "idle"

    def _next(self):
        self._pending = None
        try:
            # Whatever is pending first, painting on -- see step 1 of the
            # module docstring. It can include the user's own switch.
            _drain(self.root, time.monotonic() + STEP_LIMIT_S)
            showing = self.notebook.select()
        except tk.TclError:
            return
        self._queue = [t for t in self._queue
                       if self._current(t) not in self._settled]
        if not self._queue:
            return
        if showing in self._skip:
            self._after(RETRY_MS)
            return
        tab = self._queue[0]
        # A tab not built yet is built in a step of its own and settled
        # in the next: each half is a pause of its own, and the two in
        # one step would be the longest pause the user could meet.
        # Nothing is mapped by a build, so it needs painting off no more
        # than the ordinary loop does.
        build = self._lazy is not None and not self._lazy.is_built(tab)
        wait, why = self._wait(settle=not build)
        if wait > 0:
            self._after(wait)
            return
        # By what stands there now: a built tab's placeholder is gone.
        text = _tab_text(self.notebook, self._current(tab))
        started, began = _clock_ms(self.root), time.perf_counter()
        try:
            if build:
                kind = "build"
                self._lazy.build_page(tab)
            else:
                kind = "settle"
                self._queue.pop(0)
                self._settle(self._current(tab), showing)
        except tk.TclError:
            return      # closed during the step: the drain ran its close
        if perf_log.is_enabled():
            perf_log.log("presettle:step", kind=kind, tab=text,
                         ms=round((time.perf_counter() - began) * 1000),
                         at_ms=started - self._revealed_at, why=why)
        self._after(GAP_MS if why == "idle" else WINDOW_GAP_MS)

    def _settle(self, tab, showing):
        """One step: `tab` laid out behind the pixels of `showing`."""
        notebook = self.notebook
        hwnd = int(notebook.winfo_id())
        user32 = ctypes.windll.user32
        before = _last_input_tick()
        since = _clock_ms(self.root)
        deadline = time.monotonic() + STEP_LIMIT_S
        # Counted here, not by the tab-changed handler, which ignores a
        # step's own selections: uncounted, the tab is settled again and
        # again for the rest of the session. (`LazyTabs` holds no switch
        # while painting is off, which is what keeps it out of a step.)
        self._settled.add(tab)
        self._stepping = True
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
            self._stepping = False
            # NOT optional, whatever went wrong above: a notebook left
            # with painting off never repaints again.
            user32.SendMessageW(hwnd, WM_SETREDRAW, 1, 0)
            # Input that arrived during the step drew nothing, so its
            # effect is on no pixel yet. Repaint what it could have
            # touched.
            if _last_input_tick() != before:
                user32.RedrawWindow(hwnd, None, None,
                                    RDW_INVALIDATE | RDW_ALLCHILDREN)
        replay_lost_tab_click(self.root, notebook, since)


def settle_hidden_tabs(root, notebook, skip=(), first=(), lazy=None):
    """Start settling every tab but the one showing and `skip`, in
    idle moments, `first` before the rest; a placeholder of `lazy` is
    built in its step. Returns the settler, which the caller keeps."""
    settler = HiddenTabSettler(root, notebook, skip, first, lazy)
    settler.start()
    return settler
