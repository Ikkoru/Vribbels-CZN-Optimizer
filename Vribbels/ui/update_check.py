"""The Update Status panel, and the GitHub check behind it.

A panel plus its own background thread, in one place because the two
are one feature: the widgets exist to show what the check found, and
the check exists to fill them. The hosting tab builds it and packs
`.panel`; everything else is armed here.

How the check works
===================
`check_now` starts a background thread that fetches
    https://api.github.com/repos/<repo>/releases/latest
with urllib -- no third-party dependency -- parses the JSON and posts
the result back through a queue. The main thread drains that queue on a
poll and renders the answer.

**Nothing touches a widget off the main thread.** Tk is single-threaded
and a config call from the worker is a crash with no traceback anyone
sees; the queue is what keeps the two apart.

The last result is persisted through the settings manager under
`update_latest_version` and `update_last_checked`, so the labels
populate on the next launch without a network round trip. No message
box ever pops: the answer is in the panel, and the release notes are a
link away.

Version comparison
==================
`packaging` is third-party, so the comparison here is a naive tuple of
the dot-separated numeric prefix. **The prefix has to be extracted
first**: this fork's own version string reads
`v1.0.0 (forked from v1.7.0)`, and splitting that on `.` attaches
` (forked from v1` to the third component -- which compared as newer
than itself and reported a phantom update.
"""

import json
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime
from tkinter import ttk

from ui.scaling import px

# GitHub releases endpoint for this fork. Replace the slug if the fork
# ever migrates -- everything else here flows from this constant.
GITHUB_REPO = "Ikkoru/Vribbels-CZN-Optimizer"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_HTML_URL = f"https://github.com/{GITHUB_REPO}/releases"

# How often the main thread looks for a finished check, in ms. Cheap:
# it drains an empty queue and re-arms.
POLL_MS = 100

# The panel's own inset, as (left, top, right, bottom). Levers a
# rendered distance short of the rule -- a ttk.Label's glyphs start
# inside its own box, which is 3 on the left.
#
# **NEVER NEGATIVE.** A `ttk.LabelFrame` shrunk past 0 on a side eats
# its own BORDER on that side, not the space inside it -- the panel
# loses the edge every rule here is measured to, and the audit's border
# scan then reports nonsense for every gap in the panel rather than
# failing. The vertical correction goes on the first row's labels, as
# `ROW_TOP_TRIM` below.
PANEL_PAD = (1, 0, 1, 1)    # spacing: border edge -> first non-button element -- panel, label ↔↕

# What the FIRST ROW gives back to the gap above it. A `ttk.Label`
# carries about two pixels of inset above its glyphs, and a negative
# `padding` hands them back by shrinking the box rather than by moving
# the text. Both of the row's labels carry it: the row is as tall as
# the taller of them, so trimming one alone changes nothing.
ROW_TOP_TRIM = -2    # spacing: border edge -> first non-button element -- panel, label ↕

# The Check Now button against the panel's LEFT and BOTTOM edges.
# A different rule from the labels' -- 3 rather than 4 -- and a
# different reading of the same padding: a ttk.Button's box edge IS
# its border, where a Label's box starts outside its glyphs, so the
# inset that renders 4 for a label renders 1 for the button. This
# is what makes up the difference.
BUTTON_INSET = 2     # spacing: border edge -> button -- panel, button ↔↕

# A label against the value beside it. Three short of the rule, which
# is the two labels' insets meeting.
LABEL_TO_VALUE = 2   # spacing: label ↔ its element -- label, label ↔

# The three gaps down the panel: the two readings, the verdict under
# them, and the button under that. **One rule, three levers.** The four
# widgets are boxed differently -- two `ttk.Label`s in a grid, then a
# `tk.Label` at a face of its own, then a `ttk.Button` -- and each box
# carries a different amount of its own slack into the gap below it, so
# one number renders as three distances.
PITCH_READINGS = 2   # spacing: config panel row ↕ row -- label, label ↕
PITCH_VERDICT = 1    # spacing: config panel row ↕ row -- label, label ↕
PITCH_BUTTON = 6     # spacing: config panel row ↕ row -- label, button ↕


def version_core(version: str) -> str:
    """The numeric `x.y.z` core of a version string.

    Drops a leading `v` and stops at the first character that is
    neither a digit nor a dot, which is what makes
    `v1.0.0 (forked from v1.7.0)` compare equal to a tag of `1.0.0`.
    """
    if not version:
        return ""
    out = []
    for char in version.lstrip("vV").strip():
        if char.isdigit() or char == ".":
            out.append(char)
        else:
            break
    return "".join(out).rstrip(".")


def is_newer(latest: str, current: str) -> bool:
    """True where `latest` is a higher version than `current`.

    Anything unparseable is not newer: an update the program cannot be
    sure of is one it should not announce.
    """
    def parts(version):
        out = []
        for piece in version_core(version).split("."):
            if not piece.isdigit():
                break
            out.append(int(piece))
        return tuple(out)

    try:
        return parts(latest) > parts(current)
    except Exception:                       # noqa: BLE001
        return False


def format_age(iso_ts: str) -> str:
    """An ISO timestamp as a relative age, or `Never`."""
    if not iso_ts:
        return "Never"
    try:
        when = datetime.fromisoformat(iso_ts)
    except (ValueError, TypeError):
        return "Never"
    seconds = int((datetime.now() - when).total_seconds())
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


def current_version() -> str:
    """This build's version string, or "" where there is none."""
    try:
        from version import __version__
        return str(__version__)
    except ImportError:
        return ""


class UpdateStatus:
    """The Update Status panel: what was found, when, and a button.

    Built into `parent` and reachable as `.panel`, which the host tab
    packs or grids. The poll and the cached-result restore are armed
    here, so a host has nothing to remember beyond building it.
    """

    def __init__(self, parent, colors, root, settings_manager):
        self.colors = colors
        self.root = root
        self.settings_manager = settings_manager
        self.checking = False
        self.results = queue.Queue()
        self.current = current_version()

        self.panel = ttk.LabelFrame(parent, text="Update Status",
                                    padding=px(PANEL_PAD))

        rows = ttk.Frame(self.panel)
        rows.pack(fill=tk.X, anchor=tk.W)
        # A grid, so the two values line up under each other however
        # long their labels are.
        rows.grid_columnconfigure(1, weight=1)
        # spacing: border edge -> first non-button element -- panel, label ↕
        trim = px((0, ROW_TOP_TRIM, 0, 0))
        ttk.Label(rows, text="Latest version:", padding=trim).grid(
            row=0, column=0, sticky="w")
        self.latest_label = ttk.Label(rows, text="", padding=trim)
        # spacing: label ↔ its element -- label, label ↔
        self.latest_label.grid(row=0, column=1, sticky="w",
                               padx=px((LABEL_TO_VALUE, 0)))
        # spacing: config panel row ↕ row -- label, label ↕
        # On the whole row, both cells: a grid pad set on one column
        # only would leave the other's baseline where it was.
        ttk.Label(rows, text="Last checked:").grid(
            row=1, column=0, sticky="w", pady=px((PITCH_READINGS, 0)))
        self.checked_label = ttk.Label(rows, text="")
        # spacing: label ↔ its element -- label, label ↔
        self.checked_label.grid(row=1, column=1, sticky="w",
                                padx=px((LABEL_TO_VALUE, 0)),
                                pady=px((PITCH_READINGS, 0)))

        # `tk.Label`, not ttk: the verdict is coloured per state and a
        # ttk style would need one style per colour.
        self.verdict = tk.Label(self.panel, text="", bg=colors["bg"],
                                fg=colors["fg_dim"], font=("Segoe UI", 9))
        # spacing: config panel row ↕ row -- label, label ↕
        self.verdict.pack(anchor=tk.W, pady=px((PITCH_VERDICT, 0)))

        self.button = ttk.Button(self.panel, text="Check Now",
                                 command=self.check_now)
        # spacing: config panel row ↕ row -- label, button ↕
        # spacing: border edge -> button -- panel, button ↔↕
        self.button.pack(anchor=tk.W, padx=px((BUTTON_INSET, 0)),
                         pady=px((PITCH_BUTTON, BUTTON_INSET)))

        self.root.after(POLL_MS, self._drain)
        # Shortly after, so the tab is built before its labels move.
        self.root.after(50, self.restore_cached)

    # ------------------------------------------------------------ check

    def check_now(self):
        """Start a background check, unless one is already running."""
        if self.checking:
            return
        self.checking = True
        self.button.config(state="disabled", text="Checking...")
        self.verdict.config(text="Checking GitHub...",
                            fg=self.colors["fg_dim"])
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        """The worker. Every outcome goes back through the queue."""
        try:
            request = urllib.request.Request(
                RELEASES_API_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    # The API requires a UA and urllib sets none.
                    "User-Agent": "Vribbels-CZN-Optimizer",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            tag = (data.get("tag_name") or "").strip()
            if not tag:
                self.results.put({"ok": False, "error": "No tag_name in response"})
                return
            self.results.put({"ok": True, "latest": tag})
        except urllib.error.HTTPError as exc:
            # 404 is "this repo has published no releases", which is a
            # different answer from a server that failed.
            self.results.put({"ok": False, "error": (
                "No releases published yet on this repo" if exc.code == 404
                else f"HTTP {exc.code}")})
        except urllib.error.URLError as exc:
            self.results.put({"ok": False, "error": f"Network: {exc.reason}"})
        except Exception as exc:            # noqa: BLE001
            self.results.put({"ok": False, "error": str(exc)})

    def _drain(self):
        """Main thread: apply whatever finished. Always re-arms."""
        try:
            while True:
                self._apply(self.results.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.root.after(POLL_MS, self._drain)

    def _apply(self, result):
        """Render a finished check and persist it."""
        self.checking = False
        self.button.config(state="normal", text="Check Now")
        now_iso = datetime.now().isoformat()
        if self.settings_manager is not None:
            self.settings_manager.set("update_last_checked", now_iso)

        if result.get("ok"):
            latest = (result.get("latest") or "").lstrip("vV")
            if self.settings_manager is not None:
                self.settings_manager.set("update_latest_version", latest)
            self.render(latest, now_iso, None)
            return
        # **The cached version is not cleared by a failure.** A check
        # that could not reach GitHub says nothing about what the last
        # one found, and blanking it would read as "no release exists".
        cached = (self.settings_manager.get("update_latest_version")
                  if self.settings_manager is not None else None)
        self.render(cached, now_iso, result.get("error") or "Unknown error")

    def restore_cached(self):
        """Fill the labels from the last persisted check."""
        if self.settings_manager is None:
            return
        latest = self.settings_manager.get("update_latest_version")
        when_iso = self.settings_manager.get("update_last_checked")
        if latest or when_iso:
            self.render(latest, when_iso, None)

    def render(self, latest, when_iso, error):
        """The three widgets, from one (latest, when, error) triple."""
        if latest and self.current and version_core(latest) == version_core(
                self.current):
            self.latest_label.config(text=f"{latest} (up to date)")
        else:
            self.latest_label.config(text=latest or "")
        self.checked_label.config(text=format_age(when_iso))

        if error:
            self.verdict.config(text=f"Check failed: {error}",
                                fg=self.colors["red"])
        elif not latest or not self.current:
            self.verdict.config(text="", fg=self.colors["fg_dim"])
        elif is_newer(latest, self.current):
            self.verdict.config(text="Update available",
                                fg=self.colors["accent"])
        else:
            self.verdict.config(text="Up to date", fg=self.colors["green"])
