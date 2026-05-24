"""
About tab displaying application version and update information.

Provides:
- Current application version
- Latest available version from GitHub (this fork: Ikkoru/Vribbels-CZN-Optimizer)
- Manual "Check Now" button
- Links to GitHub, documentation, support


How the update check works
==========================
Check Now starts a background thread that fetches
    https://api.github.com/repos/Ikkoru/Vribbels-CZN-Optimizer/releases/latest
using urllib (no third-party deps), parses the JSON, and posts the result
back to the main thread via self.check_queue. The main thread renders
the new "Latest version" / "Last checked" / status indicator on the next
poll cycle.

The last-known result is persisted via SettingsManager under
    update_latest_version : str   (e.g. "1.7.1")
    update_last_checked   : str   (ISO-8601 timestamp)
so the labels populate on next launch without needing another network
round-trip. The cached result is restored shortly after the tab loads.

No messageboxes pop on result -- update info is shown in-tab only. The
user can click the "View Releases on GitHub" link to see release notes
themselves.

Version comparison
==================
We don't import 'packaging' (third-party) for version comparison. The
local _is_newer helper does naive tuple-of-ints comparison on the
dot-separated numeric prefix, ignoring "-rc1" / "-beta" suffixes. Good
enough for any sane release tag; prerelease handling can be tightened
later if needed.
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import json
import webbrowser
import urllib.request
import urllib.error
from datetime import datetime

from ui.base_tab import BaseTab
from ui.context import AppContext


# GitHub releases endpoint for this fork. Replace the slug if the fork
# ever migrates -- everything else in the file flows from this constant.
GITHUB_REPO = "Ikkoru/Vribbels-CZN-Optimizer"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_HTML_URL = f"https://github.com/{GITHUB_REPO}/releases"


def _version_core(v: str) -> str:
    """Extract the numeric "x.y.z" core of a version string, ignoring a
    leading 'v' and any trailing suffix like " (forked from v1.7.0)" or
    "-rc1". Required because version.py stores a richer display string
    while GitHub release tag_names are bare numerics, and the parser
    needs the two to compare equal when they should.

    Examples:
        "v1.0.0 (forked from v1.7.0)" -> "1.0.0"
        "v1.0.0-rc1"                  -> "1.0.0"
        "1.7.0"                       -> "1.7.0"
        ""                            -> ""
    """
    if not v:
        return ""
    s = v.lstrip("vV").strip()
    out = []
    for ch in s:
        if ch.isdigit() or ch == ".":
            out.append(ch)
        else:
            break
    return "".join(out).rstrip(".")


def _is_newer(latest: str, current: str) -> bool:
    """Return True if latest > current. Both sides go through
    _version_core to strip leading 'v' / trailing suffixes, then are
    compared as tuples of ints. Any parsing failure returns False
    (caller treats that as 'not newer').

    Note: _version_core does the heavy lifting -- the previous
    implementation split on '.' first and would mis-parse strings like
    'v1.0.0 (forked from v1.7.0)' into (1, 0) by attaching ' (forked
    from v1' to the third numeric component, making _is_newer report
    a phantom update for an actually-current version."""
    def parts(v: str):
        core = _version_core(v)
        out = []
        for p in core.split("."):
            if not p.isdigit():
                break
            out.append(int(p))
        return tuple(out)
    try:
        return parts(latest) > parts(current)
    except Exception:
        return False


def _format_age(iso_ts: str) -> str:
    """Render an ISO timestamp as a relative age ('Just now', '5 minutes
    ago', '2 hours ago', '3 days ago', etc.). Returns 'Never' on parse
    failure / empty input."""
    if not iso_ts:
        return "Never"
    try:
        when = datetime.fromisoformat(iso_ts)
    except (ValueError, TypeError):
        return "Never"
    delta = datetime.now() - when
    seconds = int(delta.total_seconds())
    if seconds < 30:
        return "Just now"
    if seconds < 60:
        return f"{seconds} seconds ago"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


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

        self.checking_updates = False
        self.check_queue = queue.Queue()

        # Widget references
        self.latest_version_label = None
        self.last_check_label = None
        self.status_label = None
        self.check_btn = None

        # Cached for status rendering -- read from version.py once at setup.
        self._current_version = self._load_current_version()

        self.setup_ui()

        # Background poll: main-thread handler for any pending check result.
        self.root.after(100, self._check_queue)
        # Restore the last-known (cached) check result so the labels aren't
        # blank on first display.
        self.root.after(50, self._restore_cached_status)

    # ----- helpers -----

    @staticmethod
    def _load_current_version() -> str:
        try:
            from version import __version__
            return str(__version__)
        except ImportError:
            return ""

    def _get_settings(self):
        """Return the SettingsManager instance or None."""
        return getattr(self.context, "settings_manager", None)

    # ----- UI -----

    def setup_ui(self):
        """Build the About tab UI."""
        main_container = ttk.Frame(self.frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # ===== APPLICATION INFO SECTION =====
        info_section = ttk.LabelFrame(main_container, text="Application Information", padding=15)
        info_section.pack(fill=tk.X, pady=(0, 15))

        app_name = ttk.Label(
            info_section,
            text="Vribbels CZN Optimizer (Ikkoru)",
            font=("Segoe UI", 12, "bold")
        )
        app_name.pack(pady=(0, 5))

        version_text = (f"Version {self._current_version}"
                        if self._current_version else "Version Unknown")
        version_label = ttk.Label(
            info_section, text=version_text, font=("Segoe UI", 14, "bold")
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

        latest_frame = ttk.Frame(update_section)
        latest_frame.pack(fill=tk.X, pady=2)
        ttk.Label(latest_frame, text="Latest version:").pack(side=tk.LEFT)
        self.latest_version_label = ttk.Label(latest_frame, text="")
        self.latest_version_label.pack(side=tk.LEFT, padx=(5, 0))

        check_frame = ttk.Frame(update_section)
        check_frame.pack(fill=tk.X, pady=2)
        ttk.Label(check_frame, text="Last checked:").pack(side=tk.LEFT)
        self.last_check_label = ttk.Label(check_frame, text="")
        self.last_check_label.pack(side=tk.LEFT, padx=(5, 0))

        status_frame = ttk.Frame(update_section)
        status_frame.pack(fill=tk.X, pady=(10, 5))
        self.status_label = tk.Label(
            status_frame, text="", font=("Segoe UI", 10),
            bg=self.colors["bg"], fg=self.colors["fg_dim"],
        )
        self.status_label.pack(side=tk.LEFT)

        btn_frame = ttk.Frame(update_section)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        self.check_btn = ttk.Button(
            btn_frame, text="Check Now", command=self.check_now
        )
        self.check_btn.pack(side=tk.LEFT)

        # ===== LINKS SECTION =====
        links_section = ttk.LabelFrame(main_container, text="Links", padding=15)
        links_section.pack(fill=tk.X)

        links = [
            ("View Releases on GitHub", RELEASES_HTML_URL),
            ("Report an Issue", f"https://github.com/{GITHUB_REPO}/issues"),
            ("Documentation", f"https://github.com/{GITHUB_REPO}#readme"),
        ]
        for text, url in links:
            link_btn = tk.Button(
                links_section, text=text,
                command=lambda u=url: webbrowser.open(u),
                bg=self.colors["bg_lighter"], fg=self.colors["accent"],
                font=("Segoe UI", 9), relief=tk.FLAT,
                padx=10, pady=5, cursor="hand2", anchor="w",
            )
            link_btn.pack(fill=tk.X, pady=2)

        def show_donation_message():
            from tkinter import messagebox
            messagebox.showinfo(
                "Support Development",
                "Currently not accepting donations.\n\n"
                "If you wish to instead donate to the original creator of this project, "
                "feel free to do so at:\nhttps://ko-fi.com/H2H21PHYKW"
            )

        support_btn = tk.Button(
            links_section, text="Support Development",
            command=show_donation_message,
            bg=self.colors["bg_lighter"], fg=self.colors["accent"],
            font=("Segoe UI", 9), relief=tk.FLAT,
            padx=10, pady=5, cursor="hand2", anchor="w",
        )
        support_btn.pack(fill=tk.X, pady=2)

    # ----- check flow -----

    def check_now(self):
        """Trigger a background GitHub-API check for the latest release."""
        if self.checking_updates:
            return
        self.checking_updates = True
        self.check_btn.config(state="disabled", text="Checking...")
        # status_label gets a transient hint while the request is in flight
        self.status_label.config(text="Checking GitHub...",
                                 fg=self.colors["fg_dim"])
        threading.Thread(target=self._do_check, daemon=True).start()

    def _do_check(self):
        """Background thread: fetch latest release from the GitHub API.
        Network errors and bad responses are caught and reported back via
        the queue so the main-thread handler can render an error state."""
        try:
            req = urllib.request.Request(
                RELEASES_API_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    # API requires a UA; bare urllib doesn't set one.
                    "User-Agent": "Vribbels-CZN-Optimizer",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            tag = (data.get("tag_name") or "").strip()
            if not tag:
                self.check_queue.put({"ok": False, "error": "No tag_name in response"})
                return
            self.check_queue.put({"ok": True, "latest": tag})
        except urllib.error.HTTPError as e:
            # 404 most commonly means "this repo has no published releases
            # yet" -- distinguishable from a server error.
            if e.code == 404:
                self.check_queue.put({
                    "ok": False,
                    "error": "No releases published yet on this repo"
                })
            else:
                self.check_queue.put({"ok": False, "error": f"HTTP {e.code}"})
        except urllib.error.URLError as e:
            self.check_queue.put({"ok": False, "error": f"Network: {e.reason}"})
        except Exception as e:
            self.check_queue.put({"ok": False, "error": str(e)})

    def _check_queue(self):
        """Drain the result queue on the main thread. Always re-arms itself."""
        try:
            while True:
                result = self.check_queue.get_nowait()
                self._handle_check_result(result)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._check_queue)

    def _handle_check_result(self, result):
        """Apply a finished check result to the UI and persist it."""
        self.checking_updates = False
        if self.check_btn:
            self.check_btn.config(state="normal", text="Check Now")

        now_iso = datetime.now().isoformat()
        sm = self._get_settings()
        if sm is not None:
            sm.set("update_last_checked", now_iso)

        if result.get("ok"):
            latest = (result.get("latest") or "").lstrip("vV")
            if sm is not None:
                sm.set("update_latest_version", latest)
            self._render_status(latest=latest, when_iso=now_iso, error=None)
        else:
            error = result.get("error") or "Unknown error"
            # Don't clobber the cached "latest" -- if a previous check
            # succeeded, the version stays visible; the error is reflected
            # in the status indicator only.
            cached_latest = sm.get("update_latest_version") if sm else None
            self._render_status(
                latest=cached_latest, when_iso=now_iso, error=error
            )

    def _restore_cached_status(self):
        """On tab load, populate the labels from the last persisted check
        so the user doesn't see blanks until they click Check Now."""
        sm = self._get_settings()
        if sm is None:
            return
        latest = sm.get("update_latest_version")
        when_iso = sm.get("update_last_checked")
        if not latest and not when_iso:
            return
        self._render_status(latest=latest, when_iso=when_iso, error=None)

    def _render_status(self, latest, when_iso, error):
        """Update the three status widgets from a (latest, when, error) triple."""
        # Latest version label. Compare numeric cores so a current version
        # like "v1.0.0 (forked from v1.7.0)" still registers as "up to
        # date" against a GitHub tag_name of "1.0.0".
        if latest:
            if (self._current_version and
                    _version_core(latest) == _version_core(self._current_version)):
                self.latest_version_label.config(text=f"{latest} (up to date)")
            else:
                self.latest_version_label.config(text=latest)
        else:
            self.latest_version_label.config(text="")

        # Last checked label.
        self.last_check_label.config(text=_format_age(when_iso))

        # Status indicator -- error takes precedence over comparison.
        if error:
            self.status_label.config(
                text=f"Check failed: {error}", fg=self.colors["red"]
            )
            return
        if not latest or not self._current_version:
            self.status_label.config(text="", fg=self.colors["fg_dim"])
            return
        if _is_newer(latest, self._current_version):
            self.status_label.config(
                text="Update available", fg=self.colors["accent"]
            )
        else:
            self.status_label.config(
                text="Up to date", fg=self.colors["green"]
            )
