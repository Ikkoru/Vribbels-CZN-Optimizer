"""
About tab displaying application version and update information.

Provides:
- Current application version
- Latest available version from GitHub
- Manual "Check Now" button
- Links to GitHub, documentation, support
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import webbrowser
from datetime import datetime
from packaging import version as pkg_version

from ui.base_tab import BaseTab
from ui.context import AppContext


class AboutTab(BaseTab):
    """
    About tab with version info and update checking.

    Features:
    - Application version display
    - Update status with visual indicators
    - Manual update check button
    - Links to GitHub, issues, documentation, Ko-fi
    """

    def __init__(self, parent: tk.Widget, context: AppContext):
        """Initialize AboutTab with parent and app context."""
        super().__init__(parent, context)

        # State
        self.update_checker = None  # Set when added to context
        self.checking_updates = False
        self.check_queue = queue.Queue()

        # Widget references
        self.latest_version_label = None
        self.last_check_label = None
        self.status_label = None
        self.check_btn = None

        self.setup_ui()

        # Start queue checking loop
        self.root.after(100, self._check_queue)

    def setup_ui(self):
        """Build the About tab UI."""
        main_container = ttk.Frame(self.frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # ===== APPLICATION INFO SECTION =====
        info_section = ttk.LabelFrame(main_container, text="Application Information", padding=15)
        info_section.pack(fill=tk.X, pady=(0, 15))

        app_name = ttk.Label(
            info_section,
            text="Vribbels - CZN Memory Fragment Optimizer",
            font=("Segoe UI", 12, "bold")
        )
        app_name.pack(pady=(0, 5))

        # Import version dynamically
        try:
            from version import __version__
            version_text = f"Version {__version__}"
        except ImportError:
            version_text = "Version Unknown"

        version_label = ttk.Label(
            info_section,
            text=version_text,
            font=("Segoe UI", 14, "bold")
        )
        version_label.pack(pady=(5, 5))

        desc_label = ttk.Label(
            info_section,
            text="A Fribbels-inspired gear management and optimization tool",
            font=("Segoe UI", 9)
        )
        desc_label.pack()

        # ===== UPDATE STATUS SECTION =====
        update_section = ttk.LabelFrame(main_container, text="Update Status", padding=15)
        update_section.pack(fill=tk.X, pady=(0, 15))

        # Latest version
        latest_frame = ttk.Frame(update_section)
        latest_frame.pack(fill=tk.X, pady=2)

        ttk.Label(latest_frame, text="Latest version:").pack(side=tk.LEFT)
        self.latest_version_label = ttk.Label(latest_frame, text="Please check manually")
        self.latest_version_label.pack(side=tk.LEFT, padx=(5, 0))

        # Last check time
        check_frame = ttk.Frame(update_section)
        check_frame.pack(fill=tk.X, pady=2)

        ttk.Label(check_frame, text="Last checked:").pack(side=tk.LEFT)
        self.last_check_label = ttk.Label(check_frame, text="At some point in the past millennium")
        self.last_check_label.pack(side=tk.LEFT, padx=(5, 0))

        # Status indicator
        status_frame = ttk.Frame(update_section)
        status_frame.pack(fill=tk.X, pady=(10, 5))

        self.status_label = tk.Label(
            status_frame,
            text="● N/A",
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg=self.colors["fg_dim"]
        )
        self.status_label.pack(side=tk.LEFT)

        # Check Now button
        btn_frame = ttk.Frame(update_section)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.check_btn = ttk.Button(
            btn_frame,
            text="Check Now",
            command=self.check_now
        )
        self.check_btn.pack(side=tk.LEFT)

        # ===== LINKS SECTION =====
        links_section = ttk.LabelFrame(main_container, text="Links", padding=15)
        links_section.pack(fill=tk.X)

        links = [
            ("View Releases on GitHub", "https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases"),
            ("Report an Issue", "https://github.com/Ikkoru/Vribbels-CZN-Optimizer/issues"),
            ("Documentation", "https://github.com/Ikkoru/Vribbels-CZN-Optimizer#readme"),
        ]

        for text, url in links:
            link_btn = tk.Button(
                links_section,
                text=text,
                command=lambda u=url: webbrowser.open(u),
                bg=self.colors["bg_lighter"],
                fg=self.colors["accent"],
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10,
                pady=5,
                cursor="hand2",
                anchor="w"
            )
            link_btn.pack(fill=tk.X, pady=2)

        def show_donation_message():
            messagebox.showinfo(
                "Support Development",
                "Currently not accepting donations.\n\n"
                "If you wish to instead donate to the original creator of this project, "
                "feel free to do so at:\nhttps://ko-fi.com/H2H21PHYKW"
            )

        support_btn = tk.Button(
            links_section,
            text="Support Development",
            command=show_donation_message,
            bg=self.colors["bg_lighter"],
            fg=self.colors["accent"],
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=10,
            pady=5,
            cursor="hand2",
            anchor="w"
        )
        support_btn.pack(fill=tk.X, pady=2)

        # Initial status refresh disabled — automatic update checking not in use
        # self.root.after(500, self.refresh_update_status)

    def _check_queue(self):
        """Check for update check results from background thread."""
        try:
            while True:
                result = self.check_queue.get_nowait()
                self._handle_check_result(result)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._check_queue)

    def _handle_check_result(self, result):
        """Handle update check result from background thread."""
        self.checking_updates = False
        self.check_btn.config(state='normal', text="Check Now")

        if result:
            # Refresh display with new info
            self.refresh_update_status()

            # Show message if update available
            if result.update_available and not result.error:
                response = messagebox.askyesno(
                    "Update Available",
                    f"A new version ({result.latest_version}) is available!\n\n"
                    f"Current version: {result.current_version}\n"
                    f"Latest version: {result.latest_version}\n\n"
                    "Would you like to view the release page?"
                )
                if response:
                    self.update_checker.open_releases_page()
        else:
            self.status_label.config(
                text="✗ Check failed: Unknown error",
                fg=self.colors["red"]
            )

    def refresh_update_status(self):
        """Refresh displayed update information from cache."""
        # Automatic update checking not in use — labels are set to static text in setup_ui
        # if not self.update_checker:
        #     self.status_label.config(
        #         text="● Configuration error",
        #         fg=self.colors["red"]
        #     )
        #     return
        #
        # cached = self.update_checker.get_cached_info()
        #
        # # Update latest version
        # latest = cached.get('latest_version', 'Unknown')
        # current = cached.get('current_version', '0.0.0')
        #
        # if latest == current:
        #     self.latest_version_label.config(text=f"{latest} (up to date)")
        # else:
        #     self.latest_version_label.config(text=latest)
        #
        # # Update last check time
        # last_check = cached.get('last_check_timestamp')
        # if last_check:
        #     try:
        #         check_dt = datetime.fromisoformat(last_check)
        #         time_diff = datetime.now() - check_dt
        #
        #         if time_diff.days > 0:
        #             time_str = f"{time_diff.days} day{'s' if time_diff.days > 1 else ''} ago"
        #         elif time_diff.seconds > 3600:
        #             hours = time_diff.seconds // 3600
        #             time_str = f"{hours} hour{'s' if hours > 1 else ''} ago"
        #         elif time_diff.seconds > 60:
        #             minutes = time_diff.seconds // 60
        #             time_str = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        #         else:
        #             time_str = "Just now"
        #
        #         self.last_check_label.config(text=time_str)
        #     except (ValueError, TypeError):
        #         self.last_check_label.config(text="Never")
        # else:
        #     self.last_check_label.config(text="Never")
        #
        # # Update status indicator
        # error = cached.get('last_error')
        #
        # if error:
        #     self.status_label.config(
        #         text=f"✗ Check failed: {error}",
        #         fg=self.colors["red"]
        #     )
        # elif latest == current:
        #     self.status_label.config(
        #         text="✓ Up to date",
        #         fg=self.colors["green"]
        #     )
        # else:
        #     try:
        #         if pkg_version.parse(latest) > pkg_version.parse(current):
        #             self.status_label.config(
        #                 text="↑ Update available",
        #                 fg=self.colors["accent"]
        #             )
        #         else:
        #             self.status_label.config(
        #                 text="✓ Up to date",
        #                 fg=self.colors["green"]
        #             )
        #     except Exception as e:
        #         self.status_label.config(
        #             text="● Unknown",
        #             fg=self.colors["fg_dim"]
        #         )
        pass

    def check_now(self):
        """Show message explaining manual update process."""
        messagebox.showinfo(
            "Automatic Update Unavailable",
            "Automatic update currently doesn't work.\n"
            "Please follow the GitHub link and build manually."
        )

    def _do_check(self):
        """Background thread: perform update check."""
        # Automatic update checking not in use
        # try:
        #     result = self.update_checker.check_for_updates()
        #     self.check_queue.put(result)
        # except Exception as e:
        #     print(f"Error checking for updates: {e}")
        #     self.check_queue.put(None)
        pass
