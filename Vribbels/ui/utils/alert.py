"""Say that something failed while the user was looking elsewhere.

A background task reports into the Capture Log, which is on a tab the
user is usually not on. The line is there, and nobody reads it. This
puts a mark on the TAB until the tab is opened.

**ttk has no per-tab colour.** `TNotebook.Tab` styles every tab of a
notebook at once, and a tab's state is only `normal` / `disabled` /
`hidden`, so no custom style state can be mapped either. What IS
per-tab is `text`, `image`, `compound` and `underline` -- so the mark
is an image, drawn here rather than loaded: a `PhotoImage` filled with
`put`, sized through `px()` like every other distance.

Use it for a failure the user must act on. Anything that retries and
carries on stays in the log, or the mark becomes wallpaper.
"""

import tkinter as tk

from ..scaling import px

# The mark, and the pause between its two states. Slow enough to read
# as a pulse rather than a flicker -- a fast blink reads as a fault in
# the program rather than a message from it.
DOT_PX = 8
BLINK_MS = 700


class TabAlert:
    """A blinking mark on one notebook tab, cleared when it is opened.

    One instance per tab. `raise_alert()` is idempotent: a second
    failure while the first is still showing does not start a second
    blink.
    """

    def __init__(self, notebook, frame, colour):
        self.notebook = notebook
        self.frame = frame
        self._after = None
        self._lit = False
        size = px(DOT_PX)
        # **Both images are held on the instance.** A `PhotoImage` with
        # no Python reference is garbage-collected and the tab goes
        # blank -- the widget keeps the name, Tk drops the pixels.
        self._dot = tk.PhotoImage(master=notebook, width=size, height=size)
        self._dot.put(colour, to=(0, 0, size, size))
        # Same size, nothing drawn: swapping to a transparent image
        # blinks the mark without the label shifting under it.
        self._blank = tk.PhotoImage(master=notebook, width=size, height=size)
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

    def is_current(self) -> bool:
        """Is this tab the one being looked at?"""
        try:
            return self.notebook.nametowidget(
                self.notebook.select()) is self.frame
        except (tk.TclError, KeyError):
            return False

    def raise_alert(self) -> bool:
        """Mark the tab. True if the mark went up.

        It does NOT go up on the tab already on screen. A mark exists to
        bring someone TO a tab; raised on the one they are reading it
        has nothing to say and no way to be dismissed, because
        `<<NotebookTabChanged>>` does not fire for the tab that is
        already selected -- so it would blink until they left and came
        back.

        The answer is the caller's cue: a mark that went up means the
        user is elsewhere, and whatever else the failure wants to say
        should wait for them.
        """
        if self._after is not None:
            return True
        if self.is_current():
            return False
        self._show(True)
        self._tick()
        return True

    def clear(self):
        """Take the mark off and stop the blink. Safe to call twice."""
        if self._after is not None:
            try:
                self.notebook.after_cancel(self._after)
            except (ValueError, tk.TclError):
                pass
            self._after = None
        self._unmark()

    @property
    def showing(self) -> bool:
        return self._after is not None

    def _tick(self):
        self._show(not self._lit)
        try:
            self._after = self.notebook.after(BLINK_MS, self._tick)
        except tk.TclError:
            # The window went away between one blink and the next.
            self._after = None

    def _show(self, lit):
        """One blink. The dark half keeps the dot's WIDTH.

        A tab carrying an image is wider than one without it, so
        blinking by adding and removing the image would shuffle the
        whole tab strip twice a second. The blank twin holds the space
        instead, and only `_unmark` gives it back.
        """
        self._lit = bool(lit)
        try:
            self.notebook.tab(self.frame,
                              image=self._dot if lit else self._blank,
                              compound=tk.LEFT)
        except tk.TclError:
            pass

    def _unmark(self):
        """Take the image off entirely, so the tab is its own width again.

        Setting the blank here is what left a dot-shaped hole in the
        tab strip for the rest of the session.
        """
        self._lit = False
        try:
            self.notebook.tab(self.frame, image="", compound=tk.NONE)
        except tk.TclError:
            pass

    def _on_tab_changed(self, event):
        """Opening the tab is reading the message, so the mark comes off."""
        try:
            if event.widget.nametowidget(event.widget.select()) is self.frame:
                self.clear()
        except Exception:
            pass
