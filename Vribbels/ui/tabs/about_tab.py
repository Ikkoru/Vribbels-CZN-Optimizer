"""About tab: where the rest of it went.

Everything this tab used to hold -- the version, the description, the
links and the update check -- is on **Setup & Settings** now, which is
where a user goes for the things they read once rather than every
session. The tab stays so the notebook keeps its shape and nothing
that reaches for `AboutTab` breaks.
"""

import tkinter as tk
from tkinter import ttk

from ui.base_tab import BaseTab
from ui.context import AppContext
from ui.scaling import px


class AboutTab(BaseTab):
    """A pointer at Setup & Settings."""

    def __init__(self, parent: tk.Widget, context: AppContext):
        super().__init__(parent, context)
        self.setup_ui()

    def setup_ui(self):
        """Build the About tab UI."""
        main_container = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        main_container.pack(fill=tk.BOTH, expand=True, padx=px(2),
                            pady=px((0, 2)))
        ttk.Label(
            main_container,
            text=("Version, links and the update check are on the "
                  "Setup & Settings tab."),
            foreground=self.colors["fg_dim"],
        ).pack(anchor=tk.W, padx=px(2), pady=px(2))
