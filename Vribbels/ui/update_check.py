"""The Update Status panel, the launch's update check, and the GitHub
request behind both.

The panel and the launch check are one feature: the widgets show what a
check found, and the launch check fills them as well as announcing a
newer release. The hosting tab builds the panel and packs `.panel`;
`OptimizerGUI` starts the launch check after the reveal, since the
Setup & Settings tab may not be built until later.

How the check works
===================
A background thread runs `fetch_latest`, which fetches
    https://api.github.com/repos/<repo>/releases/latest
with urllib -- no third-party dependency -- and parses the JSON. The
answer goes back through a queue, which the main thread drains on a
poll.

**Nothing touches a widget off the main thread.** Tk is single-threaded
and a config call from the worker is a crash with no traceback anyone
sees; the queue is what keeps the two apart.

The last result is persisted through the settings manager under
`update_latest_version` and `update_last_checked` (`record_result`), so
the labels populate on the next launch without a network round trip.

The launch check
================
`StartupCheck` runs one check per launch and, where the release is
newer than this build, shows `show_notice`: open the releases page,
ignore it this time, or ignore it until the program is updated. The last
stores this build's version under `IGNORE_KEY`, and a launch of that
same version makes no request at all (`startup_check_due`), so the
choice also stops the launch's request to GitHub. A different version,
newer or older, checks again. The panel's Check Now is unaffected.

Version comparison
==================
`packaging` is third-party, so the comparison here is a naive tuple of
the dot-separated numeric prefix. **The prefix has to be extracted
first**: this fork's own version string reads
`v1.0.0 (forked from v1.7.0)`, and splitting that on `.` attaches
` (forked from v1` to the third component -- which compares as newer
than itself and reports a phantom update.
"""

import json
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from tkinter import ttk

from ui.scaling import px
from ui.title_bar import apply_title_bar
from ui.utils.button_width import BUTTON_W_LARGE
from ui.utils.escape import close_on_escape

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
ROW_TOP_TRIM = -1    # spacing: border edge -> first non-button element -- panel, label ↕

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

# The readings the value column is held wide enough for, so the panel
# keeps one width whatever it shows. The widest of `format_age`'s
# answers, and this build's own version as an up-to-date check shows it
# (added in `UpdateStatus`). A reading wider than all of them widens the
# panel, and Client Status beside it gives the width up.
RESERVED_READINGS = ("999 days ago", "59 minutes ago", "59 seconds ago")


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


def fetch_latest() -> dict:
    """The latest release's tag, from GitHub: `{"ok": True, "latest":
    tag}`, or `{"ok": False, "error": why}`. Blocks for up to the
    request's timeout, so it runs on a worker."""
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
            return {"ok": False, "error": "No tag_name in response"}
        return {"ok": True, "latest": tag}
    except urllib.error.HTTPError as exc:
        # 404 is "this repo has published no releases", which is a
        # different answer from a server that failed.
        return {"ok": False, "error": (
            "No releases published yet on this repo" if exc.code == 404
            else f"HTTP {exc.code}")}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"Network: {exc.reason}"}
    except Exception as exc:                # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def record_result(settings_manager, result):
    """Persist a finished check and return what the panel renders from
    it: `(latest, checked_at, error)`.

    **The cached version is not cleared by a failure.** A check that
    could not reach GitHub says nothing about what the last one found,
    and blanking it would read as "no release exists".
    """
    now_iso = datetime.now().isoformat()
    if settings_manager is not None:
        settings_manager.set("update_last_checked", now_iso)
    if result.get("ok"):
        latest = (result.get("latest") or "").lstrip("vV")
        if settings_manager is not None:
            settings_manager.set("update_latest_version", latest)
        return latest, now_iso, None
    cached = (settings_manager.get("update_latest_version")
              if settings_manager is not None else None)
    return cached, now_iso, result.get("error") or "Unknown error"


# ------------------------------------------------------------ the launch

# The settings key "Ignore Until Updated" writes: the version that was
# running when it was chosen.
IGNORE_KEY = "update_ignored_in"

NOTICE_TITLE = "Update available"

# The notice's three choices, as the buttons read.
OPEN_TEXT = "Open Releases Page"
LATER_TEXT = "Ignore This Time"
IGNORE_TEXT = "Ignore Until Updated"


def startup_check_due(settings_manager, current) -> bool:
    """Whether this launch checks for an update: not where the user
    chose to ignore updates while running this same version."""
    if settings_manager is None:
        return True
    ignored = settings_manager.get(IGNORE_KEY) or ""
    return not (ignored and current
                and version_core(ignored) == version_core(current))


def notice_text(latest, current) -> str:
    """The notice's words for a release `latest` over this `current`."""
    return (f"Version {version_core(latest)} has been released.\n"
            f"You have version {version_core(current)}.")


def show_notice(root, colors, latest, current, *, on_open, on_ignore):
    """Show the update notice centred on `root`, and return the dialog.
    `on_open` and `on_ignore` (Ignore Until Updated) are called before
    it closes; Ignore This Time, Escape and the close box only close
    it."""
    dlg = tk.Toplevel(root)
    dlg.title(NOTICE_TITLE)
    dlg.transient(root)
    dlg.resizable(False, False)
    close_on_escape(dlg)
    try:
        dlg.configure(bg=colors["bg"])
    except tk.TclError:
        pass

    # spacing: content frame -> content frame -- frame, frame ↔↕
    outer = ttk.Frame(dlg, padding=px(4))
    outer.pack(fill=tk.BOTH, expand=True)
    ttk.Label(outer, text=notice_text(latest, current),
              justify=tk.LEFT).pack(anchor=tk.W)

    def choose(action):
        def run():
            dlg.destroy()
            if action is not None:
                action()
        return run

    # spacing: content frame -> content frame -- text, button ↕
    # A button row under the text and inside no panel of its own, as in
    # the settings notice.
    buttons = ttk.Frame(outer)
    buttons.pack(fill=tk.X, pady=px((4, 0)))
    ttk.Button(buttons, text=IGNORE_TEXT, width=BUTTON_W_LARGE,
               command=choose(on_ignore)).pack(side=tk.RIGHT)
    # spacing: button -> button -- button, button ↔
    ttk.Button(buttons, text=LATER_TEXT, width=BUTTON_W_LARGE,
               command=choose(None)).pack(side=tk.RIGHT, padx=px((0, 4)))
    # spacing: button -> button -- button, button ↔
    opener = ttk.Button(buttons, text=OPEN_TEXT, width=BUTTON_W_LARGE,
                        command=choose(on_open))
    opener.pack(side=tk.RIGHT, padx=px((0, 4)))
    opener.focus_set()

    dlg.update_idletasks()
    # Mapped by the line above, so its frame exists to colour.
    apply_title_bar(dlg, colors["fg"])
    try:
        width, height = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass
    return dlg


class StartupCheck:
    """One update check at launch, announced where it finds a newer
    release.

    `on_result(latest, checked_at, error)` is called on the main thread
    with every finished check, so a panel already built can show it.
    Does nothing where `startup_check_due` says the user ignored
    updates for this version. `.started` says whether it asked.
    """

    def __init__(self, root, colors, settings_manager, on_result=None,
                 fetch=fetch_latest):
        self.root = root
        self.colors = colors
        self.settings_manager = settings_manager
        self.on_result = on_result
        self.current = current_version()
        self.results = queue.Queue()
        self.notice = None
        self.thread = None
        self.started = bool(self.current) and startup_check_due(
            settings_manager, self.current)
        if not self.started:
            return
        self.thread = threading.Thread(
            target=lambda: self.results.put(fetch()), daemon=True)
        self.thread.start()
        self.root.after(POLL_MS, self._drain)

    def _drain(self):
        """Main thread: wait for the one answer, then act on it."""
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(POLL_MS, self._drain)
            return
        self.apply(result)

    def apply(self, result):
        """Persist `result`, pass it on, and announce a newer release."""
        latest, when_iso, error = record_result(self.settings_manager,
                                                result)
        if self.on_result is not None:
            try:
                self.on_result(latest, when_iso, error)
            except tk.TclError:
                pass
        if error or not latest or not is_newer(latest, self.current):
            return
        try:
            self.notice = show_notice(
                self.root, self.colors, latest, self.current,
                on_open=lambda: webbrowser.open(RELEASES_HTML_URL),
                on_ignore=self.ignore_until_updated)
        except tk.TclError:
            pass

    def ignore_until_updated(self):
        """No launch check again while this version runs."""
        if self.settings_manager is not None:
            self.settings_manager.set(IGNORE_KEY, self.current)


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
        # The value column's width: what the label asks for each reserved
        # reading -- its text and its own inset -- and the gap before it,
        # which sits inside the cell. MEASURED, so `check_ui_scales`
        # skips the column.
        reserved = RESERVED_READINGS + (
            f"{version_core(self.current)} (up to date)",)
        widest = 0
        for text in reserved:
            self.checked_label.configure(text=text)
            widest = max(widest, self.checked_label.winfo_reqwidth())
        self.checked_label.configure(text="")
        rows.grid_columnconfigure(1, minsize=widest + px(LABEL_TO_VALUE))
        rows.measured_columns = {1}

        # `tk.Label`, not ttk: the verdict is coloured per state and a
        # ttk style would need one style per colour.
        #
        # **`padx=0` is a LEVER, not tidiness.** A `tk.Label` insets its
        # own text by one pixel where a `ttk.Label` does not, so this row
        # sits a pixel right of the two above it on the same panel pad.
        # spacing: border edge -> first non-button element -- panel, label ↔
        self.verdict = tk.Label(self.panel, text="", bg=colors["bg"],
                                fg=colors["fg_dim"], font=("Segoe UI", 9),
                                padx=px(0))
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
        threading.Thread(target=lambda: self.results.put(fetch_latest()),
                         daemon=True).start()

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
        self.render(*record_result(self.settings_manager, result))

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
