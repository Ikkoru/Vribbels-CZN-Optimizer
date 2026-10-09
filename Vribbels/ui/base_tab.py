"""
Base tab class for all UI tabs in the CZN Optimizer.

Provides common infrastructure and enforces consistent tab interface.
"""

from abc import ABC, abstractmethod
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import AppContext


class BaseTab(ABC):
    """
    Abstract base class for all UI tabs.

    Provides common infrastructure and enforces consistent tab interface.
    Each tab receives an AppContext for accessing shared state and services.
    """

    def __init__(self, parent: tk.Widget, context: 'AppContext'):
        """
        Initialize the tab.

        Args:
            parent: Parent widget (typically a ttk.Notebook)
            context: Application context with shared state
        """
        self.parent = parent
        self.context = context
        self.frame = ttk.Frame(parent)

    @abstractmethod
    def setup_ui(self):
        """
        Setup the tab's UI components.

        Called once during initialization to build the tab's interface.
        Must be implemented by subclasses.
        """
        pass

    def get_frame(self) -> ttk.Frame:
        """Return the tab's root frame for adding to notebook."""
        return self.frame

    def is_hidden(self) -> bool:
        """Whether another tab is the one showing. A notebook with none
        selected -- the tab built on its own, as the checks build it,
        or before the tabs are added -- counts as showing this one."""
        notebook = getattr(self.context, "notebook", None)
        try:
            shown = notebook.select() if notebook is not None else ""
            return bool(shown) and notebook.nametowidget(shown) \
                is not self.frame
        except (tk.TclError, KeyError):
            return False

    def when_shown(self, on_shown, on_left=None):
        """Call `on_shown()` each time this tab becomes the one showing,
        and `on_left()`, if given, each time another tab is chosen.

        For work a tab skips while hidden and catches up on when looked
        at. Bound once, with `add`, beside every other tab's. Unlike
        `is_hidden`, it wants this tab selected: a switch that leaves
        none selected shows nothing.
        """
        notebook = getattr(self.context, "notebook", None)
        if notebook is None:
            return

        def changed(_event=None):
            try:
                shown = notebook.select()
                mine = bool(shown) and notebook.nametowidget(shown) \
                    is self.frame
            except (tk.TclError, KeyError):
                return
            if mine:
                on_shown()
            elif on_left is not None:
                on_left()

        notebook.bind("<<NotebookTabChanged>>", changed, add="+")

    # Convenience properties for accessing shared resources
    @property
    def colors(self) -> dict:
        """Access color palette from context."""
        return self.context.colors

    @property
    def optimizer(self):
        """Access optimizer instance from context."""
        return self.context.optimizer

    @property
    def notebook(self) -> ttk.Notebook:
        """Access main notebook from context."""
        return self.context.notebook

    @property
    def root(self) -> tk.Tk:
        """Access root window from context."""
        return self.context.root
