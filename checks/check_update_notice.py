"""The launch's update check announces a newer release, and its three
choices do what they say.

`ui.update_check.StartupCheck` asks GitHub once per launch and shows a
notice where the release is newer than this build. Each way it can go
wrong is quiet: a notice for the version already running nags at every
launch; one that never shows leaves a user on an old build without a
word; an Ignore Until Updated that does not stick, or that sticks past
an update, is a choice the program forgot; and a failed request that
blanks the cached version reads in the panel as "no release exists".

Held with the request replaced by a made-up answer, so nothing reaches
the network, on a settings stand-in, with the notice built at alpha 0
under a withdrawn root so nothing shows. Also holds the main window to
starting the check, which nothing else would notice missing.
"""

import ast

from ._harness import SOURCE_ROOT, add_source_to_path, destroy_root, note

NAME = "the launch's update check and its notice"

# The file whose `OptimizerGUI.__init__` must start the launch check.
# A name here so a fault can point it at a copy that does not.
GUI_SOURCE = SOURCE_ROOT / "czn_optimizer_gui.py"


class _Settings:
    """The two calls the update check makes on a settings manager."""

    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def _gating(uc):
    """Which launches ask GitHub at all."""
    out = []
    current = "v2.7.0 (forked from v1.7.0)"
    cases = (
        ("nothing ignored", _Settings(), True),
        ("no settings manager", None, True),
        ("ignored in this very version", _Settings(
            **{uc.IGNORE_KEY: current}), False),
        ("ignored in this version, spelled as a tag",
         _Settings(**{uc.IGNORE_KEY: "2.7.0"}), False),
        ("ignored in an older version", _Settings(
            **{uc.IGNORE_KEY: "v2.6.0 (forked from v1.7.0)"}), True),
    )
    for what, settings, wanted in cases:
        if uc.startup_check_due(settings, current) != wanted:
            out.append(
                f"with {what}, the launch {'skips' if wanted else 'makes'} "
                f"its update check: Ignore Until Updated must hold while "
                f"the same version runs and lapse once it is updated "
                f"(`update_check.startup_check_due`).")
    return out


def _buttons(dlg):
    import tkinter as tk
    from tkinter import ttk
    found = {}

    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, (ttk.Button, tk.Button)):
                found[child.cget("text")] = child
            walk(child)
    walk(dlg)
    return found


def _launches(uc, root, colors):
    """A launch per answer, the notice's buttons pressed."""
    out = []
    current = uc.current_version()
    if not current:
        note("this build has no version string: the launch check was not "
             "exercised.")
        return out
    newer = f"v{int(uc.version_core(current).split('.')[0]) + 1}.0.0"
    same = f"v{uc.version_core(current)}"
    opened = []
    open_page = uc.webbrowser.open
    uc.webbrowser.open = lambda url, *a, **k: opened.append(url)
    try:
        def launch(settings, answer):
            asked, shown = [], []

            def fetch():
                asked.append(1)
                return answer
            check = uc.StartupCheck(root, colors, settings,
                                    on_result=lambda *r: shown.append(r),
                                    fetch=fetch)
            if check.started:
                # The worker's answer, taken on this thread rather than
                # through the poll, which needs the event loop.
                check.thread.join(5)
                check.apply(check.results.get_nowait())
            return check, asked, shown

        # A release newer than this build: the notice, three choices.
        settings = _Settings()
        check, asked, shown = launch(settings, {"ok": True, "latest": newer})
        if not asked:
            out.append("a launch with nothing ignored did not ask GitHub "
                       "for the latest release.")
        if settings.get("update_latest_version") != newer.lstrip("v") \
                or not settings.get("update_last_checked"):
            out.append("the launch check did not record what it found, so "
                       "the Update Status panel would show an older "
                       "check's answer (`update_check.record_result`).")
        if not shown:
            out.append("the launch check did not pass its answer on, so a "
                       "Setup & Settings tab built already keeps showing "
                       "the last launch's (`on_result`).")
        dlg = check.notice
        if dlg is None:
            out.append(f"a release newer than this build ({newer} over "
                       f"{current}) raised no notice, so nobody hears of "
                       f"it.")
            return out
        wanted = {uc.OPEN_TEXT, uc.LATER_TEXT, uc.IGNORE_TEXT}
        buttons = _buttons(dlg)
        if set(buttons) != wanted:
            out.append(f"the update notice has the buttons "
                       f"{sorted(buttons)}, not {sorted(wanted)}.")
            dlg.destroy()
            return out
        if uc.version_core(newer) not in uc.notice_text(newer, current):
            out.append("the update notice does not name the new version.")

        buttons[uc.OPEN_TEXT].invoke()
        if opened != [uc.RELEASES_HTML_URL] or dlg.winfo_exists():
            out.append(f"{uc.OPEN_TEXT} did not open the releases page and "
                       f"close the notice: opened {opened}.")
        if settings.get(uc.IGNORE_KEY):
            out.append(f"{uc.OPEN_TEXT} also ignored updates until the "
                       f"next one.")

        check, asked, _ = launch(settings, {"ok": True, "latest": newer})
        if not asked or check.notice is None:
            out.append(f"after {uc.OPEN_TEXT}, the next launch did not "
                       f"announce the release again.")
        else:
            _buttons(check.notice)[uc.LATER_TEXT].invoke()
            if check.notice.winfo_exists() or settings.get(uc.IGNORE_KEY):
                out.append(f"{uc.LATER_TEXT} did not just close the notice: "
                           f"it should neither stay up nor remember "
                           f"anything.")

        check, asked, _ = launch(settings, {"ok": True, "latest": newer})
        if check.notice is None:
            out.append(f"after {uc.LATER_TEXT}, the next launch did not "
                       f"announce the release again.")
        else:
            _buttons(check.notice)[uc.IGNORE_TEXT].invoke()
            if check.notice.winfo_exists():
                out.append(f"{uc.IGNORE_TEXT} left the notice up.")
            if settings.get(uc.IGNORE_KEY) != current:
                out.append(f"{uc.IGNORE_TEXT} did not record this version "
                           f"({settings.get(uc.IGNORE_KEY)!r} for "
                           f"{current!r}), so the notice comes back at the "
                           f"next launch.")

        check, asked, _ = launch(settings, {"ok": True, "latest": newer})
        if asked or check.notice is not None:
            out.append(f"after {uc.IGNORE_TEXT}, a launch of the same "
                       f"version still asked GitHub or announced the "
                       f"release.")

        # The version already running: nothing to announce.
        check, _, _ = launch(_Settings(), {"ok": True, "latest": same})
        if check.notice is not None:
            out.append(f"a launch of {current} announced {same} as an "
                       f"update: the notice would come up at every launch.")
            check.notice.destroy()

        # A failed request, with a newer version cached from before.
        settings = _Settings(update_latest_version=newer.lstrip("v"))
        check, _, shown = launch(settings, {"ok": False, "error": "Network"})
        if settings.get("update_latest_version") != newer.lstrip("v"):
            out.append("a failed launch check cleared the cached version, "
                       "which the panel then reads as no release at all.")
        if not shown or shown[0][2] != "Network":
            out.append("a failed launch check did not pass its error on to "
                       "the panel.")
        if check.notice is not None:
            out.append("a failed launch check announced the version cached "
                       "from an earlier one: the panel shows that, and a "
                       "notice per offline launch is a nag.")
            check.notice.destroy()
    finally:
        uc.webbrowser.open = open_page
    return out


def _gui_starts_it():
    """`OptimizerGUI.__init__` calls `_start_update_check`."""
    tree = ast.parse(GUI_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for call in ast.walk(node):
                if isinstance(call, ast.Attribute) \
                        and call.attr == "_start_update_check":
                    return []
    return ["the main window never starts the launch's update check "
            "(`OptimizerGUI._start_update_check`, from `__init__` after "
            "the reveal): nobody hears of a new release unless they press "
            "Check Now."]


def _state_key(uc):
    """The ignored version is the program's memory, not a preference."""
    from settings_manager import SettingsManager
    if uc.IGNORE_KEY not in SettingsManager.state_keys():
        return [f"{uc.IGNORE_KEY} is not under the settings' "
                f"{SettingsManager.STATE_SECTION}, so a release's defaults "
                f"would overwrite the user's Ignore Until Updated."]
    return []


def run():
    add_source_to_path()
    from ui import update_check as uc
    out = _gating(uc) + _gui_starts_it() + _state_key(uc)

    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        note(f"Tk will not start here ({exc}): the notice was not built.")
        return out
    import czn_optimizer_gui as gui
    from ui import spacing_audit as sa
    build = tk.Toplevel.__init__
    try:
        root.withdraw()
        root.attributes("-alpha", 0.0)
        sa.hide_new_windows()
        out += _launches(uc, root, dict(gui.COLORS))
    finally:
        tk.Toplevel.__init__ = build
        destroy_root(root)
    return out


def _gui_without_the_call():
    """Point the check at a copy of the main window's source that never
    starts the launch check."""
    global GUI_SOURCE
    import tempfile
    from pathlib import Path
    text = GUI_SOURCE.read_text(encoding="utf-8")
    copy = Path(tempfile.mkdtemp(prefix="gui_")) / GUI_SOURCE.name
    copy.write_text(text.replace("        self._start_update_check()\n", ""),
                    encoding="utf-8")
    GUI_SOURCE = copy


UC = "ui.update_check"

FAULTS = [
    ("Ignore Until Updated never lapses",
     f"{UC}:startup_check_due",
     "return not (ignored and current\n"
     "                and version_core(ignored) == version_core(current))",
     "return not ignored",
     "lapse once it is updated"),
    ("Ignore Until Updated never holds",
     f"{UC}:startup_check_due",
     "return not (ignored and current\n"
     "                and version_core(ignored) == version_core(current))",
     "return True",
     "Ignore Until Updated must hold"),
    ("the running version announced",
     f"{UC}:StartupCheck.apply",
     "if error or not latest or not is_newer(latest, self.current):",
     "if error or not latest:",
     "the notice would come up at every launch"),
    ("a failed check announces the cached version",
     f"{UC}:StartupCheck.apply",
     "if error or not latest or not is_newer(latest, self.current):",
     "if not latest or not is_newer(latest, self.current):",
     "a notice per offline launch is a nag"),
    ("a newer release never announced",
     f"{UC}:StartupCheck.apply",
     "self.notice = show_notice(",
     "self.notice = None and show_notice(",
     "raised no notice"),
    ("the answer not passed to the panel",
     f"{UC}:StartupCheck.apply",
     "self.on_result(latest, when_iso, error)",
     "None",
     "did not pass its answer on"),
    ("Ignore Until Updated forgets",
     f"{UC}:StartupCheck.ignore_until_updated",
     "self.settings_manager.set(IGNORE_KEY, self.current)",
     "pass",
     "did not record this version"),
    ("Open Releases Page ignores as well",
     f"{UC}:show_notice",
     "command=choose(on_open))",
     "command=lambda: (on_ignore(), choose(on_open)()))",
     "also ignored updates"),
    ("Ignore This Time remembers",
     f"{UC}:show_notice",
     "command=choose(None)).pack(",
     "command=choose(on_ignore)).pack(",
     "did not just close the notice"),
    ("a failure blanks the cached version",
     f"{UC}:record_result",
     "cached = (settings_manager.get(\"update_latest_version\")\n"
     "              if settings_manager is not None else None)",
     "cached = None\n"
     "    settings_manager.set(\"update_latest_version\", \"\")",
     "cleared the cached version"),
    ("nothing recorded",
     f"{UC}:record_result",
     "settings_manager.set(\"update_latest_version\", latest)",
     "pass",
     "did not record what it found"),
    ("the main window never starts it",
     _gui_without_the_call, None, None,
     "never starts the launch's update check"),
]
