"""One WebSocket frame writes the snapshot once, and says so once.

**A FRAME is the unit, not a payload.** The client batches its commands
whenever it has several to send and the server answers in kind, so one
frame carries a LIST of replies -- and loading into the game sends the
roster, the inventory and the banner schedule that way. Every branch
that reads one of those must flag the addon rather than write the file,
with the single save at the end of the frame handler.

Getting this wrong is invisible from the code: each branch is correct on
its own, and the duplication only exists for a frame that trips more
than one. It is also awkward to see by hand, needing the proxy, the game
and a fresh login. So the frame is synthesised here instead.

The file content is identical however many times it is written --
`_save_data` writes the whole cache whenever it runs -- which is exactly
why nothing else would catch it.

**Logging in still takes two frames**, and always will: the inventory
arrives in one and the lobby's banner schedule seconds later in the
next. Both are real saves and the second carries something the first
did not, but the report counts fragments and combatants and neither of
those moved -- so the line repeats itself word for word. The second one
is dropped, and ONLY where it would repeat the last line logged: a save
that follows an upgrade or a delete still confirms itself.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture saves once per frame"


class _Message:
    """The three attributes `websocket_message` reads off a message."""

    def __init__(self, payload):
        self.from_client = False
        self.is_text = True
        self.text = json.dumps(payload)
        self.content = self.text.encode()


class _Flow:
    """A mitmproxy flow, as far as `websocket_message` looks into one."""

    def __init__(self, payload):
        self.websocket = type("W", (), {"messages": [_Message(payload)]})()


def run():
    add_source_to_path()
    from capture.manager import ADDON_TEMPLATE

    # The addon is a program inside a string literal -- mitmdump writes
    # it out and runs it -- so there is no class to import. Executing the
    # template is what `check_addon_template` already proves is safe: it
    # imports nothing beyond the standard library.
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    # The tables the generated script appends below the template. Empty
    # is enough here -- every lookup falls back to a res_id -- but they
    # have to EXIST, or a line that names a fragment raises instead.
    namespace.update(CHAR_NAMES={}, SET_NAMES={}, SLOT_NAMES={},
                     KNOWN_UNIT_IDS=set(), REGION_ROUTES={})
    Addon = namespace["Addon"]

    failures = []
    work = Path(tempfile.mkdtemp())
    lines = []
    addon = Addon(work, log_callback=lambda msg, *a, **k: lines.append(msg))

    # A login reply as the server sends it: one frame, several replies.
    # The handler drops anything not answered "ok" before it reads a key.
    batch = [
        {"res": "ok", "piece_items": [
            {"id": 1, "res_id": 1010001, "level": 0, "char_res_id": 0}]},
        {"res": "ok",
         "characters": [{"id": 11, "res_id": 101, "level": 60}],
         "user": {"nickname": "probe"}},
        {"res": "ok", "event_schedules": {"GACHA": {}}},
    ]
    addon.websocket_message(_Flow(batch))

    saves = [l for l in lines if str(l).startswith("Saved:")]
    if len(saves) != 1:
        failures.append(
            f"one frame of {len(batch)} replies produced {len(saves)} "
            f"`Saved:` lines, not 1. A branch that reads part of a batched "
            f"reply must set `_save_pending` rather than write the file; "
            f"the save belongs after the payload loop. Lines: {saves}"
        )

    written = list(work.glob("memory_fragments_*.json"))
    if len(written) != 1:
        failures.append(
            f"one frame wrote {len(written)} snapshot files, not 1: "
            f"{[p.name for p in written]}"
        )

    # The login as it actually arrives: the roster and inventory in one
    # frame, the lobby's banner schedule in the next.
    lines = []
    addon = Addon(Path(tempfile.mkdtemp()),
                  log_callback=lambda msg, *a, **k: lines.append(msg))
    addon.websocket_message(_Flow(batch))
    addon.websocket_message(_Flow(
        [{"res": "ok", "event_schedules": {"GACHA": {"a": {}}}}]))
    saves = [l for l in lines if str(l).startswith("Saved:")]
    if len(saves) != 1:
        failures.append(
            f"logging in reported {len(saves)} saves, not 1. The lobby "
            f"frame's save is real -- it carries the banner schedule -- "
            f"but its report repeats the previous line word for word, and "
            f"a repeat of the last line says nothing. Lines: {saves}"
        )

    # ...and a save that follows anything else still confirms itself,
    # identical counts or not. An upgrade changes a level, so the
    # fragment and combatant counts in the line do not move.
    upgraded = dict(batch[0]["piece_items"][0])
    upgraded["level"] = 3
    addon.websocket_message(_Flow([{"res": "ok", "piece": upgraded}]))
    if not str(lines[-1]).startswith("Saved:"):
        failures.append(
            f"the save after an upgrade did not report itself; the log "
            f"ends {lines[-1]!r}. Only a repeat of the LAST line is "
            f"dropped -- with an upgrade logged in between there is "
            f"nothing to repeat."
        )

    return failures
