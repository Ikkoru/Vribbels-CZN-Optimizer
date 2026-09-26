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
  rather than an empty page or a tab assembling.
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
    """The app's slots, and the build that follows selecting one."""

    def __init__(self, root, notebook):
        self.root = root
        self.notebook = notebook
        self.slots = {}
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed,
                      add="+")

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
            shown = self.notebook.select()
        except tk.TclError:
            return
        slot = self._slot_at(shown)
        if slot is not None and slot.instance is None:
            self._build_in_view(slot)

    def _build_in_view(self, slot):
        """Build the slot the user just selected, and show it whole.

        With painting off while it is built and laid out, then all of
        it painted at once: the old tab stays on screen until the new
        one is finished. Off Windows, where painting cannot be held, it
        is built and shown as it comes.
        """
        if sys.platform != "win32":
            slot.build()
            return
        import ctypes
        from .presettle import (RDW_ALLCHILDREN, RDW_INVALIDATE,
                                STEP_LIMIT_S, WM_SETREDRAW, _drain)
        user32 = ctypes.windll.user32
        hwnd = int(self.notebook.winfo_id())
        user32.SendMessageW(hwnd, WM_SETREDRAW, 0, 0)
        try:
            slot.build()
            _drain(self.root, time.monotonic() + STEP_LIMIT_S)
        finally:
            # NOT optional: a notebook left with painting off never
            # repaints again. And the repaint is the whole point here:
            # nothing of the new tab has been drawn yet.
            user32.SendMessageW(hwnd, WM_SETREDRAW, 1, 0)
            user32.RedrawWindow(hwnd, None, None,
                                RDW_INVALIDATE | RDW_ALLCHILDREN)
