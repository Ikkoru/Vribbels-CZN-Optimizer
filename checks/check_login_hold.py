"""A login reloads the window once, after its saves stop.

A login saves the snapshot a dozen times in a few seconds, each save
holding more of the account than the last: the addon starts empty and
saves as soon as the inventory lands. A window reloading on every one
shows its tabs going backwards and then forwards -- the Checklist's
Other column went from 27 rows to 12 and back in one login. Nothing
raises; the tabs just resettle while the player watches.

So the reload is held, not the save. Three parts must agree:

1. the addon prints `LOGIN_MARKER` when the server's `last_login_tm`
   moves -- the capture's first login too -- and not on a reconnect,
   which re-sends the same stamp;
2. the reader consumes the marker and calls `login_callback`;
3. `_poll_capture` asks `login_hold.decide` and runs a wanted reload
   only once the saves have gone quiet, or the login has run long
   enough that waiting more would leave the last session on screen.

Drives the real generated addon, the real reader and the real
`OptimizerGUI` methods on a stand-in window, with the clock scripted.
"""

from types import SimpleNamespace

from ._harness import add_source_to_path

NAME = "a login reloads once, after its saves"

POLL_S = 0.04


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


def _window(gui, clock):
    """The real capture-polling methods on a stand-in window, and the
    times of the reloads they run."""
    reloads = []
    win = SimpleNamespace(
        _live_update_wanted=False, _last_save_at=None, _login_began=None,
        _gacha_written=False, _stats_written=False, _event_moved=False,
        gacha_tab_instance=None, disaster_tab_instance=None,
        capture_tab_instance=SimpleNamespace(drain_inbox=lambda: None),
        root=SimpleNamespace(after=lambda *a: None),
        _handle_live_update=lambda: reloads.append(clock.now))
    for name in ("_poll_capture", "_want_live_update", "_on_login"):
        setattr(win, name, getattr(gui.OptimizerGUI, name).__get__(win))
    return win, reloads


def _play(gui, script, until):
    """Poll every `POLL_S` to `until`, firing `script`'s ("login" or
    "save", at) events as their time comes. Returns the reload times,
    relative to the start."""
    clock = _Clock()
    start = clock.now
    real_time = gui.time
    gui.time = clock
    try:
        win, reloads = _window(gui, clock)
        events = sorted(script, key=lambda e: e[1])
        t = 0.0
        while t <= until:
            clock.now = start + t
            while events and events[0][1] <= t:
                kind, _at = events.pop(0)
                (win._on_login if kind == "login"
                 else win._want_live_update)()
            win._poll_capture()
            t = round(t + POLL_S, 6)
    finally:
        gui.time = real_time
    return [round(r - start, 3) for r in reloads]


def _the_decision(gui, quiet, cap):
    out = []
    # The 2026-11-13 login's shape: the marker, then saves under a
    # second apart for 3.4 s, then nothing for half a minute.
    burst = [("login", 0.0)] + [("save", 3.24 + 0.3 * i) for i in range(12)]
    last = burst[-1][1]
    got = _play(gui, burst, 20.0)
    if len(got) != 1:
        out.append(
            f"a login burst of 12 saves under a second apart reloaded "
            f"{len(got)} times, at {got}. It has to reload once, after the "
            f"saves stop: each reload in between shows a snapshot that is "
            f"not whole yet, and the tabs go backwards and then forwards.")
    elif not (last + quiet - 0.01 <= got[0] <= last + quiet + 2 * POLL_S):
        out.append(
            f"a login burst whose last save came at {last:.2f}s reloaded "
            f"at {got[0]:.2f}s, not {quiet}s after it. Earlier is a "
            f"snapshot not whole yet; later keeps the last session's rows "
            f"up for no reason.")

    # A login that never goes quiet: the cap.
    endless = [("login", 0.0)] + [("save", 0.5 * i) for i in range(1, 60)]
    got = _play(gui, endless, 30.0)
    if not got or not (cap - 0.01 <= got[0] <= cap + 2 * POLL_S):
        out.append(
            f"a login whose saves never stopped first reloaded at "
            f"{got[0] if got else None}s, not at the {cap}s cap. Without "
            f"one, a game that keeps saving leaves the last session's data "
            f"on screen for as long as it does.")
    elif len(got) < 2 or got[1] - got[0] > 0.5 + 2 * POLL_S:
        out.append(
            f"after the cap released a login, the next save reloaded at "
            f"{got[1:2]}, not at once. The hold is for one login; once it "
            f"ends a save reloads on the next poll.")

    # No login pending: at once, as before the hold existed.
    got = _play(gui, [("save", 1.0)], 3.0)
    if len(got) != 1 or not 1.0 <= got[0] <= 1.0 + POLL_S + 1e-6:
        out.append(
            f"a save with no login pending reloaded at {got}, not on the "
            f"next poll after 1.0s. An `Upgraded` line waits for that "
            f"reload, so a hold here delays every upgrade's Highest Pot.")
    return out


def _the_addon_says_it(said_list, addon, flow):
    """Complaints about the addon's marker, or []."""
    from capture.manager import LOGIN_MARKER, SAVE_MARKER
    from .check_capture_always_on import LOGIN, RELAUNCH

    def count():
        return sum(1 for line in said_list if line == LOGIN_MARKER)

    out = []
    addon.websocket_message(flow(LOGIN))
    if count() != 1:
        return [
            f"the capture's first login printed {LOGIN_MARKER!r} "
            f"{count()} times, not once. The first login is as partial as "
            f"any relaunch's, and without the marker the window reloads on "
            f"every save of it."]
    first_save = next((i for i, line in enumerate(said_list)
                       if line == SAVE_MARKER), None)
    if first_save is not None and said_list.index(LOGIN_MARKER) > first_save:
        out.append(
            f"the addon printed {LOGIN_MARKER!r} after the login's first "
            f"save. That save reloads before the hold begins.")
    addon.websocket_message(flow(LOGIN))
    if count() != 1:
        out.append(
            f"a second `load/user` carrying the same `last_login_tm` "
            f"printed {LOGIN_MARKER!r} again. That is a reconnect, which "
            f"this game does often; holding the reload for one delays an "
            f"`Upgraded` line's Highest Pot. for no login.")
    addon.websocket_message(flow(RELAUNCH))
    if count() != 2:
        out.append(
            f"a relaunch (a new `last_login_tm`) printed {LOGIN_MARKER!r} "
            f"{count() - 1} times, not once.")
    return out


def _the_reader_hears_it():
    """Complaints about the reader, or []."""
    from capture.manager import (ADDON_TEMPLATE, CaptureManager,
                                 LOGIN_MARKER)
    import tempfile
    out = []
    if f'LOGIN_MARKER = "{LOGIN_MARKER}"' not in ADDON_TEMPLATE:
        out.append(
            f"the reader watches for {LOGIN_MARKER!r} and the addon "
            f"template prints something else. No login would be held, and "
            f"no error would say so.")
    shown = []
    mgr = CaptureManager(tempfile.mkdtemp(),
                         log_callback=lambda msg, *a, **k: shown.append(msg))
    heard = []
    mgr.login_callback = lambda: heard.append(True)
    mgr.proxy_process = SimpleNamespace(
        stdout=iter([LOGIN_MARKER + "\n"]), poll=lambda: 0)
    mgr._read_proxy_output()
    if heard != [True]:
        out.append(
            f"the reader called `login_callback` {len(heard)} times for "
            f"one {LOGIN_MARKER!r} line, not once.")
    if any(LOGIN_MARKER in str(line) for line in shown):
        out.append(
            f"the reader showed {LOGIN_MARKER!r} in the Capture Log. It is "
            f"a signal to the window, like the save marker, not a line.")
    return out


def run():
    add_source_to_path()
    import tempfile
    from pathlib import Path
    import czn_optimizer_gui as gui
    import login_hold
    from .check_capture_always_on import _addon, _Flow

    failures = _the_decision(gui, login_hold.LOGIN_QUIET_S,
                             login_hold.LOGIN_MAX_S)
    addon, _snaps, said = _addon(Path(tempfile.mkdtemp()), debug=False)
    failures.extend(_the_addon_says_it(said, addon, _Flow))
    failures.extend(_the_reader_hears_it())
    return failures


FAULTS = [
    ("the quiet test removed",
     "login_hold:decide",
     "    if last_save_at is not None and now - last_save_at >= LOGIN_QUIET_S:\n"
     "        return RELOAD\n",
     "",
     "reloaded at"),
    ("the cap removed",
     "login_hold:decide",
     "    if now - login_began >= LOGIN_MAX_S:\n        return RELOAD\n",
     "",
     "not at the 10.0s cap"),
    ("the marker not printed on a first login",
     "capture.manager:ADDON_TEMPLATE",
     "        self.log_callback(LOGIN_MARKER)\n"
     "        if was is None or self.saved_path is None:\n"
     "            return                       # the capture's first login\n",
     "        if was is None or self.saved_path is None:\n"
     "            return                       # the capture's first login\n"
     "        self.log_callback(LOGIN_MARKER)\n",
     "the capture's first login printed"),
    ("the window not asking",
     "czn_optimizer_gui:OptimizerGUI._poll_capture",
     "== login_hold.RELOAD", "!= None",
     "reloaded 12 times"),
]
