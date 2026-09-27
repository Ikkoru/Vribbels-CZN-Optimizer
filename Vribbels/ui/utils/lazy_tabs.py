"""Tabs built the first time they are needed, rather than at startup.

Creating every tab's widgets before the window appears is most of what
startup costs, and most tabs are not what the user looks at first. So
a tab can be a SLOT: an empty placeholder page under the tab's title,
standing in the notebook where the tab goes, and the tab itself built
on the first of these:

* **The idle settler's step for it** (`ui/utils/presettle.py`), which
  builds it in one idle moment and lays it out, unseen, in the next.
  This is the ordinary case.
* **The user selecting it** before that step came. Painting on the
  notebook is switched off, the tab built and laid out, and the whole
  of it painted at once -- so the click shows the finished tab late
  rather than an empty page or a tab assembling. A tab built but not
  yet laid out is shown the same way, and is never built twice.
* **Anything that needs the tab itself**: a reload the Checklist must
  record from first, or the spacing audit, which measures every tab.

A built tab takes its placeholder's place in the notebook, and from
then on it is the tab as if it had been built at startup. Until then,
`TabSlot.instance` is None, and **every caller that reaches a slot's
tab has to allow for that**: a refresh for a tab not built yet is one
there is nothing to apply to, since building it reads the data then
current.
"""

import sys
import time
import tkinter as tk
from tkinter import ttk

from .realize import realize_windows


class TabSlot:
    """One tab of the notebook, built on first need.

    `factory` builds the tab and returns it; `after_build` brings the
    new tab up to date with whatever loaded before it existed.
    """

    def __init__(self, notebook, text, factory, after_build=None):
        self.notebook = notebook
        self.text = text
        self.factory = factory
        self.after_build = after_build
        self.instance = None
        self.placeholder = ttk.Frame(notebook)
        notebook.add(self.placeholder, text=text)
        # Kept after the build: a caller holding the placeholder's path
        # -- the idle settler's queue does -- asks with it what stands
        # there now.
        self.placeholder_path = str(self.placeholder)

    @property
    def page(self):
        """The page standing in the notebook for this tab now."""
        if self.instance is not None:
            return self.instance.get_frame()
        return self.placeholder

    def build(self):
        """The tab, built now if it was not already."""
        if self.instance is not None:
            return self.instance
        instance = self.factory()
        frame = instance.get_frame()
        notebook, placeholder = self.notebook, self.placeholder
        # In the placeholder's place, and selected where it was, BEFORE
        # the placeholder goes: forgetting the selected page first
        # would have the notebook select some other tab in between.
        notebook.insert(placeholder, frame, text=self.text)
        selected = notebook.select() == str(placeholder)
        self.instance = instance
        self.placeholder = None
        if selected:
            notebook.select(frame)
        notebook.forget(placeholder)
        placeholder.destroy()
        # NOT optional, and not covered by the walk in `_reveal_window`,
        # which ran before this tab existed: a widget whose window is
        # created at its first map is erased near-white for a frame.
        # See `realize.py`.
        realize_windows(frame)
        if self.after_build is not None:
            self.after_build(instance)
        return instance


class LazyTabs:
    """The app's slots, and every tab's first show.

    **A tab is shown whole the first time, whatever state it is in**:
    a placeholder, a tab built but not yet laid out, or one built at
    startup that the idle settler has not reached. Painting on the
    notebook goes off when it is selected, and comes back on once it
    is built, laid out, and every tab-changed handler has run for it;
    then all of it is painted at once. Until then the old tab stays on
    screen. Off Windows, where painting cannot be held, a tab is built
    and shown as it comes.

    `shown` holds every page already laid out at its real size, by
    being displayed or settled. The idle settler adds a page to it
    BEFORE selecting it, so that its own selections are never first
    shows.

    **Created before any tab**, so that its tab-changed handler is the
    first one bound: painting must be off before any tab's own handler
    draws.
    """

    # Queued behind a first show's tab-changed event: see
    # `_on_tab_changed`.
    SHOWN = "<<LazyTabShown>>"

    def __init__(self, root, notebook):
        self.root = root
        self.notebook = notebook
        self.slots = {}
        self.shown = set()
        # Until the reveal, a page selected is laid out by the reveal's
        # own passes, unseen.
        self._watching = False
        self._holds = 0
        self._held_since = 0
        self._showing = []
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed,
                      add="+")
        notebook.bind(self.SHOWN, self._finish_show, add="+")

    def watch(self):
        """Show every first show whole from now on. The reveal calls it,
        once the page it shows is laid out."""
        self._watching = True
        try:
            self.shown.add(self.notebook.select())
        except tk.TclError:
            pass

    def add(self, name, text, factory, after_build=None):
        slot = TabSlot(self.notebook, text, factory, after_build)
        self.slots[name] = slot
        return slot

    def instance(self, name):
        """The tab named `name`, or None where it is not built yet."""
        slot = self.slots.get(name)
        return slot.instance if slot is not None else None

    def build(self, name):
        return self.slots[name].build()

    def build_all(self):
        for slot in self.slots.values():
            slot.build()

    def _slot_at(self, path):
        return next((s for s in self.slots.values()
                     if s.placeholder_path == path), None)

    def current(self, path):
        """The path of the page standing where `path` stood: the built
        tab's, where `path` is a placeholder that has been replaced."""
        slot = self._slot_at(path)
        return str(slot.page) if slot is not None else path

    def build_page(self, path):
        """Build the slot whose placeholder `path` is, if it is one, and
        return the path of its page. What an idle settler step calls."""
        slot = self._slot_at(path)
        return str(slot.build().get_frame()) if slot is not None else path

    def is_built(self, path):
        """Whether what stands at `path` is a tab rather than a
        placeholder still waiting for one."""
        slot = self._slot_at(path)
        return slot is None or slot.instance is not None

    def _on_tab_changed(self, _event=None):
        try:
            page = self.notebook.select()
        except tk.TclError:
            return
        if not page or page in self.shown:
            return
        self.shown.add(page)
        slot = self._slot_at(page)
        unbuilt = slot is not None and slot.instance is None
        if not self._watching or sys.platform != "win32":
            if unbuilt:
                self.shown.add(str(slot.build().get_frame()))
            return
        text = slot.text if slot is not None else self._text(page)
        began = time.perf_counter()
        self._hold_painting()
        try:
            if unbuilt:
                # Known as shown before the event its build queued, by
                # selecting it, arrives: that one is no first show.
                self.shown.add(str(slot.build().get_frame()))
        finally:
            # Queued rather than run here, and in a `finally`: every
            # tab-changed handler bound after this one -- each tab built
            # after startup binds its own -- has still to run for this
            # event, and a build's own selection has still to arrive.
            # What they draw has to be drawn with painting off too.
            self._showing.append((text, began, unbuilt))
            self.notebook.event_generate(self.SHOWN, when="tail")

    def _finish_show(self, _event=None):
        """Lay out what a first show held back, then paint all of it."""
        from .presettle import STEP_LIMIT_S, _drain
        try:
            _drain(self.root, time.monotonic() + STEP_LIMIT_S)
        finally:
            self._release_painting()
        if self._showing:
            text, began, unbuilt = self._showing.pop(0)
            import perf_log
            perf_log.log("lazy_tabs:first_show", tab=text,
                         built_now="yes" if unbuilt else "no",
                         ms=round((time.perf_counter() - began) * 1000))

    def _text(self, page):
        try:
            return self.notebook.tab(page, "text")
        except tk.TclError:
            return "?"

    def _hold_painting(self):
        import ctypes
        from .presettle import WM_SETREDRAW, _clock_ms
        if self._holds == 0:
            self._held_since = _clock_ms(self.root)
            ctypes.windll.user32.SendMessageW(
                int(self.notebook.winfo_id()), WM_SETREDRAW, 0, 0)
        self._holds += 1

    def _release_painting(self):
        import ctypes
        from .presettle import (RDW_ALLCHILDREN, RDW_INVALIDATE,
                                WM_SETREDRAW, replay_lost_tab_click)
        self._holds = max(0, self._holds - 1)
        if self._holds:
            return
        try:
            hwnd = int(self.notebook.winfo_id())
        except tk.TclError:
            return                      # the window is closing
        user32 = ctypes.windll.user32
        # NOT optional: a notebook left with painting off never repaints
        # again. And the repaint is the whole point here: nothing of the
        # new tab has been drawn yet.
        user32.SendMessageW(hwnd, WM_SETREDRAW, 1, 0)
        user32.RedrawWindow(hwnd, None, None,
                            RDW_INVALIDATE | RDW_ALLCHILDREN)
        replay_lost_tab_click(self.root, self.notebook, self._held_since)
