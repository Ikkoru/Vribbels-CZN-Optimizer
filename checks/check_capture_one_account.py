"""One capture session must hold ONE account's data.

Two games running at once both reach the proxy, and their payloads are
indistinguishable after the fact: only the `user` record names an
account, and `piece_items` -- the bulk of a snapshot -- do not. Merging
them yields one snapshot holding one account's fragments against
another's roster, with nothing downstream able to detect it. The
Combatants tab, the exclude list and every score would simply be wrong.

So the addon keeps the first account it sees and drops the rest of the
session. This drives the REAL generated addon, the same way
check_capture_batching does, so a guard lost from the template fails
here rather than in someone's snapshot.
"""

import tempfile
from pathlib import Path

from ._harness import add_source_to_path

NAME = "capture keeps one account per session"


def _addon(tmp):
    """Build and import the addon exactly as a capture would."""
    add_source_to_path()
    from capture.manager import CaptureManager

    mgr = CaptureManager(tmp, log_callback=lambda *a, **k: None)
    script = mgr._generate_addon_script(debug_mode=False)

    import importlib.util
    spec = importlib.util.spec_from_file_location("_probe_addon", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and hasattr(obj, "_handle_server_payload"):
            return obj(Path(tmp))
    raise LookupError("no addon class with _handle_server_payload")


def _payload(account, pieces=1):
    return {
        "res": "ok",
        "user": {"id": account, "auth_id": f"auth-{account}"},
        "characters": [{"res_id": 1001}],
        "piece_items": [{"id": n} for n in range(pieces)],
    }


def run():
    failures = []
    tmp = tempfile.mkdtemp()
    try:
        addon = _addon(tmp)
    except Exception as e:
        return [f"could not build the addon: {type(e).__name__}: {e}"]

    logged = []
    addon.log_callback = lambda msg, *a, **k: logged.append(str(msg))

    # First account is adopted.
    addon._handle_server_payload(_payload("acct-A", pieces=3), 100)
    if addon.session_account != "acct-A":
        failures.append(
            f"the first account seen was not adopted "
            f"(session_account={addon.session_account!r}). Without it there "
            f"is nothing to compare a second account against."
        )
    first = addon.inventory_data

    # Same account again: still accepted.
    addon._handle_server_payload(_payload("acct-A", pieces=4), 100)
    if addon.mixed_accounts:
        failures.append(
            "the same account arriving twice was treated as two accounts. "
            "A session sends many payloads; only a DIFFERENT id counts."
        )

    # A second account: dropped, and said so.
    before = addon.inventory_data
    addon._handle_server_payload(_payload("acct-B", pieces=99), 100)
    if not addon.mixed_accounts:
        failures.append(
            "a second account's payload was accepted. Two games running at "
            "once would merge into one snapshot, and piece_items carry no "
            "account id, so nothing downstream could tell."
        )
    if addon.inventory_data is not before:
        failures.append(
            "a second account's payload reached inventory_data. The guard "
            "has to run BEFORE anything mutates cached state."
        )
    if not any("second game account" in m.lower() or "second account" in m.lower()
               for m in logged):
        failures.append(
            f"nothing was logged when two accounts were detected. Silent is "
            f"the one thing this must not be; logged: {logged!r}"
        )

    # And it stays shut for the rest of the session, even for account A.
    addon._handle_server_payload(_payload("acct-A", pieces=7), 100)
    if addon.inventory_data is not before:
        failures.append(
            "capture resumed after two accounts were seen. Once mixed, the "
            "session cannot be trusted: the payloads already merged cannot "
            "be told apart."
        )
    _ = first
    return failures
