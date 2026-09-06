"""About tab: what this build is, and where to find the project.

The version, a description, and the links. **The update check is not
here** -- it lives with the Update Status panel in `ui/update_check.py`
and is built by the Setup tab, beside the other things a user goes
looking for once rather than every session. This tab keeps the links
because they point at the same repository the check reads.
"""

import tkinter as tk
import webbrowser
from tkinter import ttk

from ui.base_tab import BaseTab
from ui.context import AppContext
from ui.scaling import px
from ui.update_check import GITHUB_REPO, RELEASES_HTML_URL, current_version


class AboutTab(BaseTab):
    """Version, description and outward links."""

    def __init__(self, parent: tk.Widget, context: AppContext):
        super().__init__(parent, context)
        self._current_version = current_version()
        self.setup_ui()

    def setup_ui(self):
        """Build the About tab UI."""
        main_container = ttk.Frame(self.frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=px(20),
                            pady=px((22, 20)))

        info_section = ttk.LabelFrame(
            main_container, text="Application Information", padding=px(15))
        info_section.pack(fill=tk.X, pady=px((0, 15)))

        ttk.Label(
            info_section, text="Vribbels CZN Optimizer (Ikkoru)",
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=px((0, 5)))

        ttk.Label(
            info_section,
            text=(f"Version {self._current_version}"
                  if self._current_version else "Version Unknown"),
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=px((5, 5)))

        ttk.Label(
            info_section,
            text="A Fribbels-inspired gear management and optimization tool",
            font=("Segoe UI", 9),
        ).pack()

        links_section = ttk.LabelFrame(main_container, text="Links",
                                       padding=px(15))
        links_section.pack(fill=tk.X)

        links = [
            ("View Releases on GitHub", RELEASES_HTML_URL),
            ("Report an Issue", f"https://github.com/{GITHUB_REPO}/issues"),
            ("Documentation", f"https://github.com/{GITHUB_REPO}#readme"),
        ]
        for text, url in links:
            tk.Button(
                links_section, text=text,
                command=lambda u=url: webbrowser.open(u),
                bg=self.colors["bg_lighter"], fg=self.colors["accent"],
                font=("Segoe UI", 9), relief=tk.FLAT,
                padx=px(10), pady=px(5), cursor="hand2", anchor="w",
            ).pack(fill=tk.X, pady=px(2))

        def show_donation_message():
            from tkinter import messagebox
            messagebox.showinfo(
                "Support Development",
                "Currently not accepting donations.\n\n"
                "If you wish to instead donate to the original creator of "
                "this project, feel free to do so at:\n"
                "https://ko-fi.com/H2H21PHYKW"
            )

        tk.Button(
            links_section, text="Support Development",
            command=show_donation_message,
            bg=self.colors["bg_lighter"], fg=self.colors["accent"],
            font=("Segoe UI", 9), relief=tk.FLAT,
            padx=px(10), pady=px(5), cursor="hand2", anchor="w",
        ).pack(fill=tk.X, pady=px(2))
