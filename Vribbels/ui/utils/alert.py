"""Say that something failed while the user was looking elsewhere.

A background task reports into the Capture Log, which is on a tab the
user is usually not on. The line is there, and nobody reads it. This
blinks the TAB's group bar (`tab_bars.py`) in the alert colour until
the tab is opened.

The bar in either colour is one width, so the blink moves nothing in
the tab strip.

Use it for a failure the user must act on. Anything that retries and
carries on stays in the log, or the mark becomes wallpaper.
"""

import tkinter as tk

from .tab_bars import TabBars

# The pause between the mark's two states. Slow enough to read as a
# pulse rather than a flicker -- a fast blink reads as a fault in the
# program rather than a message from it.
BLINK_MS = 700


class TabAlert:
    """A blinking mark on one notebook tab, cleared when it is opened.

    One instance per tab. `raise_alert()` is idempotent: a second
    failure while the first is still showing does not start a second
    blink. Raises LookupError on a notebook with no `TabBars`, which
    has no bar to blink.
    """

    def __init__(self, notebook, frame, colour):
        self.notebook = notebook
        self.frame = frame
        self.colour = colour
        self._after = None
        self._lit = False
        self.bars = TabBars.of(notebook)
        if self.bars is None:
            raise LookupError("the notebook has no tab bars to blink")
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
        # Lit at once, and the first blink a pause later.
        self._show(True)
        self._schedule()
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
        self._schedule()

    def _schedule(self):
        try:
            self._after = self.notebook.after(BLINK_MS, self._tick)
        except tk.TclError:
            # The window went away between one blink and the next.
            self._after = None

    def _show(self, lit):
        """One blink: the bar in the alert colour, or its group's."""
        self._lit = bool(lit)
        try:
            self.bars.mark(self.frame, self.colour if lit else None)
        except tk.TclError:
            pass

    def _unmark(self):
        """The bar back in its group's colour."""
        self._show(False)

    def _on_tab_changed(self, event):
        """Opening the tab is reading the message, so the mark comes off."""
        try:
            if event.widget.nametowidget(event.widget.select()) is self.frame:
                self.clear()
        except Exception:
            pass
