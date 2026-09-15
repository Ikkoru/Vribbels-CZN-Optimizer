"""A capture meant to be left running for weeks.

Three things that only matter once a capture outlives one sitting, and
each of which fails quietly:

1. **The debug log is compressed, and readable after every write.** Its
   content is almost all repetition -- a bare login is 1.8MB of which
   99.3% is byte-for-byte what the last login said -- so an always-on
   capture without compression is gigabytes. What makes it safe is one
   gzip MEMBER per line rather than one stream: a stream is readable
   only once its end marker is written, and an always-on capture ends
   by being killed.

2. **A snapshot per game RELAUNCH.** `saved_path` is chosen once and
   rewritten on every save, so without a rotation a month of capture
   leaves exactly one snapshot -- the newest state, with no history
   behind it, and that history is what every derived reading in this
   program is built from. The trap is the rotation firing too often
   instead: this game drops its connection regularly, and a reconnect
   looks like a launch from every angle but one.

3. **The wire catalogue accumulates rather than doubling.** It is the
   record of which request carries which field, kept so that a field
   nobody reads is visible -- `entity` and `issued_limit_entities` were
   both on the wire for months. It merges with what is already on disk,
   and a merge that also folded in its own starting point would read
   one sighting as three.

Drives the REAL generated addon, so a guard lost from the template
fails here rather than in someone's capture.
"""

import gzip
import json
import tempfile
import time
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture survives being left on"

HELO = [{"cmd": "helo", "qid": 1, "params": {"device_id": "d"}}]
ASK = [{"cmd": "mission", "qid": 100,
        "params": {"cmd": "reward_event_limit",
                   "event_mission_id": "event_bartender_1"}}]
REPLY = {"res": "ok", "qid": 100,
         "entity": {"res_id": "event_bartender_1", "event_achieve_state": 1}}
# **`last_login_tm` is what says a launch is a launch.** A reconnect
# keeps it; only a real login moves it.
LOGIN = {"res": "ok", "qid": 4,
         "user": {"id": "acct", "auth_id": "a", "last_login_tm": 1000},
         "characters": [{"res_id": 1001}], "piece_items": [{"id": 1}]}
RELAUNCH = {"res": "ok", "qid": 4,
            "user": {"id": "acct", "auth_id": "a", "last_login_tm": 2000},
            "characters": [{"res_id": 1001}],
            "piece_items": [{"id": 1}, {"id": 2}]}

CATALOGUED = "mission/reward_event_limit|entity"


class _Message:
    def __init__(self, payload, from_client=False):
        self.from_client = from_client
        self.is_text = True
        self.text = json.dumps(payload)
        self.content = self.text.encode()


class _Flow:
    def __init__(self, payload, from_client=False):
        self.websocket = type(
            "W", (), {"messages": [_Message(payload, from_client)]})()


def _addon(root, debug, maintainer=True):
    """Build and import the addon exactly as a capture would."""
    import os
    from capture.manager import CaptureManager, MAINTAINER_ENV

    was = os.environ.get(MAINTAINER_ENV)
    if maintainer:
        os.environ[MAINTAINER_ENV] = "1"
    else:
        os.environ.pop(MAINTAINER_ENV, None)

    snaps = Path(root) / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    mgr = CaptureManager(snaps, log_callback=lambda *a, **k: None)
    # **Generated without debug**, and the debug one built below. The
    # script constructs an addon of its own at import, and that one
    # would open a second log and announce it on stdout -- a check has
    # no business writing to the run's output.
    script = mgr._generate_addon_script(debug_mode=False)

    import importlib.util
    spec = importlib.util.spec_from_file_location("_always_on_addon", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if was is None:
        os.environ.pop(MAINTAINER_ENV, None)
    else:
        os.environ[MAINTAINER_ENV] = was

    # Everything about it -- the class, the paths -- is the generated
    # script's own, so this is still the real addon.
    said = []
    addon = type(mod.addons[0])(
        mod.OUTPUT_DIR, dict_path=mod.DICT_PATH,
        log_callback=lambda msg, *a, **k: said.append(str(msg)),
        debug_mode=debug, catalogue_path=mod.CATALOGUE_PATH)
    return addon, snaps, said


def _debug_log_is_readable_while_open(addon, snaps):
    """Complaints about the compressed log, or []."""
    logs = list(snaps.glob("websocket_debug_*"))
    if len(logs) != 1 or logs[0].suffix != ".gz":
        return [
            f"debug logging produced {[p.name for p in logs]!r}. It has to "
            f"be compressed: uncompressed, a capture left on for a month "
            f"is gigabytes of near-identical login bursts."]

    addon.websocket_message(_Flow(HELO, from_client=True))
    addon.websocket_message(_Flow(ASK, from_client=True))
    addon.websocket_message(_Flow(REPLY))

    # **Read while the capture still holds it open**, which is the
    # whole point of a member per line.
    try:
        with gzip.open(logs[0], "rt", encoding="utf-8") as fh:
            frames = [json.loads(line) for line in fh if line.strip()]
    except (OSError, EOFError) as e:
        return [
            f"the debug log could not be read while the capture still held "
            f"it open ({type(e).__name__}: {e}). One gzip stream over the "
            f"whole file is readable only once its end marker is written, "
            f"and an always-on capture ends by being killed -- so every "
            f"frame has to be its own member."]
    if len(frames) != 3:
        return [
            f"the debug log held {len(frames)} frames mid-write, not the 3 "
            f"written. A frame that is not on disk when the capture dies is "
            f"a frame nobody will ever see."]
    return []


def _a_snapshot_per_launch(addon, snaps, said):
    """Complaints about snapshot rotation, or []."""
    out = []
    addon.websocket_message(_Flow(LOGIN))
    first = sorted(snaps.glob("memory_fragments_*.json"))
    if len(first) != 1:
        return [f"the first launch left {len(first)} snapshots."]

    # **A reconnect must NOT rotate.** This game drops its connection
    # often, and a reconnect closes the socket, redoes the handshake
    # and re-sends the lobby -- all of which look like a launch. What
    # it does not do is log in again.
    #
    # Read off `saved_path` rather than off the folder: a snapshot's
    # name carries a timestamp to the SECOND, so a wrongful rotation
    # inside one second would write to the same name and leave the
    # file count alone.
    was = addon.saved_path
    addon.websocket_end(None)
    if addon.saved_path != was:
        out.append(
            "a dropped connection released the snapshot. `websocket_end` "
            "fires on a blip exactly as it does on a close, and this game "
            "blips often -- one evening of it made three files out of one "
            "sitting.")
    addon.websocket_message(_Flow(HELO, from_client=True))
    if addon.saved_path != was:
        out.append(
            "the handshake after a reconnect released the snapshot. A "
            "reconnect redoes it, so `helo` does not mean a new game.")
    # **Counted off the LOG, not off the path.** A rotation is
    # immediately followed by a save, which picks a name from the clock
    # at second resolution -- so a wrongful rotation inside one second
    # puts the path back exactly as it was and leaves no trace on disk.
    before = len([line for line in said if "relaunch" in line.lower()])
    addon.websocket_message(_Flow(LOGIN))
    if len([line for line in said if "relaunch" in line.lower()]) != before:
        out.append(
            "re-sending the SAME login was taken for a relaunch. Only a "
            "`last_login_tm` the account has not been seen at is a new "
            "game; a reconnect keeps the one it had.")

    # The filename carries a timestamp to the second, so two launches
    # inside one second would share a name however the code behaves.
    time.sleep(1.1)
    addon.websocket_message(_Flow(HELO, from_client=True))
    addon.websocket_message(_Flow(RELAUNCH))
    after = sorted(snaps.glob("memory_fragments_*.json"))
    if len(after) != 2:
        out.append(
            f"two game launches left {len(after)} snapshot(s), not 2. A "
            f"capture left running rewrites one file for its whole life "
            f"otherwise, and the history every derived reading is built "
            f"from never exists.")
    else:
        held = json.loads(first[0].read_text(encoding="utf-8"))
        if len(held["inventory"]["piece_items"]) != 1:
            out.append(
                "the first launch's snapshot was rewritten by the second. "
                "A finished session's file has to be left as it was.")

    return out


def _the_catalogue_accumulates(addon, root):
    """Complaints about the wire catalogue, or []."""
    out = []
    addon.done()
    book = Path(root) / "settings" / "wire_catalogue.json"
    if not book.exists():
        return [
            f"no wire catalogue at {book}. It belongs beside the settings: "
            f"the snapshots folder is the one a user empties, and this is a "
            f"record built up over months."]
    rows = json.loads(book.read_text(encoding="utf-8"))["keys"]
    row = rows.get(CATALOGUED)
    if not row:
        return [
            f"the catalogue holds {sorted(rows)!r}, without {CATALOGUED!r}. "
            f"A key is filed under the command that answered with it, which "
            f"is what makes it findable at all."]
    if row["count"] != 1:
        out.append(f"one sighting was catalogued as {row['count']}.")

    second, _snaps, _said = _addon(root, debug=False)
    second.websocket_message(_Flow(ASK, from_client=True))
    second.websocket_message(_Flow(REPLY))
    second.done()
    again = json.loads(book.read_text(encoding="utf-8"))["keys"][CATALOGUED]
    if again["count"] != 2:
        out.append(
            f"a second capture took one sighting to {again['count']}, not "
            f"2. The catalogue merges with the file, so an addon that also "
            f"STARTS from the file adds the whole history to itself.")
    if again["first"] != row["first"]:
        out.append(
            f"the first sighting moved from {row['first']!r} to "
            f"{again['first']!r}. It is the earlier of the two, or the "
            f"record cannot say how long a field has been there.")
    return out


def _a_released_build_catalogues_nothing(root):
    """The catalogue is the maintainer's, and nobody else's.

    It is of no use to anyone not reading the wire, and it would put a
    file in a user's `settings/` that nothing explains. The switch is
    an environment variable the `zRUN*.bat` launchers set; a frozen exe
    has no way to, which is what makes this safe by construction
    rather than by a setting somebody has to find.

    Returns a list of complaints.
    """
    import shutil
    out = []
    plain = Path(root) / "released"
    plain.mkdir(parents=True, exist_ok=True)
    addon, _snaps, _said = _addon(plain, debug=False, maintainer=False)
    if addon.catalogue_path is not None:
        out.append(
            f"a released build was given a catalogue at "
            f"{addon.catalogue_path}. Without the environment variable the "
            f"whole thing has to be off -- nothing recorded and nothing "
            f"written.")
    addon.websocket_message(_Flow(ASK, from_client=True))
    addon.websocket_message(_Flow(REPLY))
    addon.done()
    if addon.catalogue:
        out.append(
            f"a released build recorded {len(addon.catalogue)} sightings. "
            f"The recording costs nothing much, but a switch that only "
            f"stops the WRITING is one edit away from shipping the file.")
    left = list((plain / "settings").glob("*")) if (
        plain / "settings").exists() else []
    if left:
        out.append(
            f"a released build wrote {[p.name for p in left]!r} into "
            f"settings/.")
    shutil.rmtree(plain, ignore_errors=True)
    return out


def _the_marker_survives_elevation():
    """The working copy's marker reaches the process that captures.

    Capture needs Administrator, so the program relaunches itself
    elevated -- and `ShellExecuteW`'s "runas" starts the new process
    with a FRESH environment. The `zRUN*.bat` launchers set
    `VRIBBELS_DEV`; the elevated copy, which is the one that captures,
    never saw it, so the catalogue was off in every session that
    accepted the UAC prompt.

    The flag rides the relaunch instead, and is read back only where
    the program runs from source: a frozen build ignores it, so the
    switch is still closed by construction.

    Returns a list of complaints.
    """
    import ctypes
    import os
    import sys
    import czn_optimizer_gui as gui

    if sys.platform != "win32":
        return []
    out = []
    was = os.environ.get(gui.MAINTAINER_ENV)
    seen = []
    real = ctypes.windll.shell32.ShellExecuteW
    try:
        os.environ[gui.MAINTAINER_ENV] = "1"
        # **The real relaunch, with only the Win32 call stubbed.** The
        # stub answers 33 -- what ShellExecuteW returns when the
        # elevated copy started -- so nothing is elevated and nothing
        # is opened.
        ctypes.windll.shell32.ShellExecuteW = (
            lambda *a: seen.append(a) or 33)
        gui.run_as_admin()
    finally:
        ctypes.windll.shell32.ShellExecuteW = real
        if was is None:
            os.environ.pop(gui.MAINTAINER_ENV, None)
        else:
            os.environ[gui.MAINTAINER_ENV] = was

    params = str(seen[0][3]) if seen else ""
    if gui.DEV_FLAG not in params:
        out.append(
            f"the elevated relaunch was asked for as {params!r}, without "
            f"{gui.DEV_FLAG!r}. The environment does not survive a UAC "
            f"prompt, so the marker has to ride the command line -- "
            f"otherwise the process that captures is never the one that "
            f"knows it is a working copy.")

    # And the far end reads it back, but only from source.
    os.environ.pop(gui.MAINTAINER_ENV, None)
    try:
        gui._adopt_dev_flag(["czn_optimizer_gui.py", gui.DEV_FLAG])
        # **Read off the ENVIRONMENT, not off the return value.** What
        # the addon generator consults is the variable; a function that
        # answers yes without setting it leaves the catalogue off.
        if not os.environ.get(gui.MAINTAINER_ENV):
            out.append(
                f"{gui.DEV_FLAG!r} on the command line did not set "
                f"{gui.MAINTAINER_ENV}. The relaunch passes it and "
                f"nothing reads it back, which is the same as not "
                f"passing it.")
        os.environ.pop(gui.MAINTAINER_ENV, None)
        sys.frozen = True
        if gui._adopt_dev_flag(["app.exe", gui.DEV_FLAG]):
            out.append(
                f"a FROZEN build adopted {gui.DEV_FLAG!r}. The catalogue "
                f"is the maintainer's; a released build has to ignore the "
                f"flag whoever types it.")
    finally:
        if hasattr(sys, "frozen"):
            del sys.frozen
        os.environ.pop(gui.MAINTAINER_ENV, None)
        if was is not None:
            os.environ[gui.MAINTAINER_ENV] = was
    return out


def run():
    add_source_to_path()
    root = Path(tempfile.mkdtemp())
    addon, snaps, said = _addon(root, debug=True)

    failures = _debug_log_is_readable_while_open(addon, snaps)
    if failures:
        return failures
    failures.extend(_a_snapshot_per_launch(addon, snaps, said))
    failures.extend(_the_catalogue_accumulates(addon, root))
    failures.extend(_a_released_build_catalogues_nothing(root))
    failures.extend(_the_marker_survives_elevation())
    return failures
