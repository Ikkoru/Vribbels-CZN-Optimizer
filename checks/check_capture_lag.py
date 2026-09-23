"""Debug WS says how long each Capture Log line was held, and by whom.

A line that reaches the log late was held either by the game, which had
not sent its request yet, or by the program -- the addon, the pipe or
the UI thread. Under Debug WS the addon stamps each line with when its
request went out, when the reply came in and when it printed the line;
the reader takes the stamp off and the log shows the delays after the
line.

What fails quietly: a stamp that stops arriving leaves the log
unchanged and the question unanswerable, and one that is not taken off
reaches every test the reader makes of a line -- `in` checks survive
it, anything that matches a line's END does not. So this drives the
real generated addon, with and without debug mode, through the real
reader's `split_lag`.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "Debug WS times each Capture Log line"

ITEM_ID = 3300013


class _Message:
    def __init__(self, data, from_client, timestamp):
        self.from_client = from_client
        self.is_text = True
        self.text = json.dumps(data)
        self.content = self.text.encode("utf-8")
        self.timestamp = timestamp


class _Flow:
    def __init__(self, message):
        self.websocket = type("_WS", (), {"messages": [message]})()


def _addon(root, debug_mode, lines):
    """The real generated addon class, printing into `lines`.

    Built here rather than taken from the script's own `addons`: the
    wrapper that stamps a line closes over the sink it was built with,
    so the sink has to be there at construction. The script is
    generated without debug mode, so its own instance opens no debug
    file this one would not close.
    """
    from capture.manager import CaptureManager

    output = root / "snapshots"
    output.mkdir(parents=True, exist_ok=True)
    manager = CaptureManager(output, log_callback=lambda *_a, **_k: None)
    script = manager._generate_addon_script(debug_mode=False)
    namespace = {"__name__": "_generated_addon_under_check"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"),
         namespace)
    return namespace["Addon"](output, debug_mode=debug_mode,
                              log_callback=lambda msg, *_a, **_k:
                              lines.append(msg))


def _pair(addon, sent_at, got_at):
    """A request, then its reply paying one item."""
    addon.websocket_message(_Flow(_Message(
        [{"cmd": "item", "qid": 7, "params": {"cmd": "use"}}], True,
        sent_at)))
    addon.inventory_data = {"items": [{"res_id": ITEM_ID, "amount": 1}]}
    addon.websocket_message(_Flow(_Message(
        {"res": "ok", "qid": 7, "add_result": {"items": {str(ITEM_ID): {
            "doc": {"res_id": ITEM_ID, "amount": 5}, "diff": 4}}}},
        False, got_at)))


def run():
    add_source_to_path()
    from capture.manager import (ADDON_TEMPLATE, LAG_MARKER, split_lag)
    from ui.tabs.capture_tab import lag_text

    failures = []
    if f'LAG_MARKER = "{LAG_MARKER}"' not in ADDON_TEMPLATE:
        failures.append(
            f"the reader takes lines apart at {LAG_MARKER!r} and the addon "
            f"template does not define the same marker. The stamp would "
            f"reach the log as text, and every test of a line's end with "
            f"it.")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plain, stamped = [], []
        _pair(_addon(root / "plain", False, plain), 100.0, 100.25)
        debug = _addon(root / "debug", True, stamped)
        _pair(debug, 100.0, 100.25)
        if debug.debug_file is not None:
            debug.debug_file.close()

    received = [line for line in plain if "Received" in line]
    if not received:
        return failures + ["the addon wrote no receipt for a reward, so "
                           "there was no line to time"]
    if any(LAG_MARKER in line for line in plain):
        failures.append(
            f"a capture without Debug WS stamped its lines: {plain!r}. "
            f"Only a debug capture is timed.")
    line = next((l for l in stamped if "Received" in l), "")
    text, stamp = split_lag(line)
    if stamp is None:
        failures.append(
            f"under Debug WS the receipt reads {line!r}, with no timing "
            f"the reader can take off. The log would show the line as "
            f"ever, and nothing about how long it was held.")
    else:
        if text != received[0]:
            failures.append(
                f"with its timing taken off, the receipt reads {text!r}; "
                f"without Debug WS it reads {received[0]!r}. The reader's "
                f"tests of a line have to see the same text either way.")
        if (stamp["sent"], stamp["got"]) != (100.0, 100.25) or \
                stamp["said"] < 100.25:
            failures.append(
                f"the receipt's timing reads {stamp}: its request went out "
                f"at 100.0 and its reply came in at 100.25, and it cannot "
                f"have been printed before the reply.")
        shown = lag_text(stamp, stamp["read"] + 0.04)
        if "server 250" not in shown or "UI 40" not in shown:
            failures.append(
                f"the timing shown for a reply 250 ms after its request, "
                f"shown 40 ms after it was read, reads {shown!r}.")
    return failures
