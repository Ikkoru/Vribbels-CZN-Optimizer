"""`capture.setup.remove_certificate`, with certutil stood in for.

Delete Certificate is the one button whose half-success looks exactly
like success. Out of the stores but with its key left in
`~/.mitmproxy`, the next Generate & Install Cert puts the same CA back:
the one the user was withdrawing because a copy of its key got out. One
store emptied and the other forgotten leaves the CA trusted with the
dialog saying it was removed. Neither raises.

So certutil is replaced by a fake holding a count of certificates per
store, and the files live in a temporary folder. Nothing here touches
a real certificate store or the user's `.mitmproxy`.

No Tk and no snapshot needed.
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from ._harness import add_source_to_path

NAME = "certificate removal"

# A file of mitmproxy's that is not the CA, and must survive.
KEPT = "mitmproxy-dhparam.pem"


def _fake_certutil(held, refuse=()):
    """A certutil over `held`, {store flag: certificates named
    mitmproxy}, that deletes one per `-delstore` -- the least any real
    certutil does -- and fails `-delstore` on the flags in `refuse`.
    Records every call."""
    calls = []

    def run(args, timeout=15):
        calls.append(list(args))
        flag = "-user" if "-user" in args else ""
        if "-store" in args:
            return SimpleNamespace(returncode=0 if held.get(flag) else 17,
                                   stdout="", stderr="")
        if flag in refuse:
            return SimpleNamespace(returncode=5, stdout="",
                                   stderr="Access is denied.")
        held[flag] = max(0, held.get(flag, 0) - 1)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run, calls


def _folder(setup):
    folder = Path(tempfile.mkdtemp())
    for name in setup.CA_FILES + (KEPT,):
        (folder / name).write_text("x", encoding="utf-8")
    return folder


def run():
    add_source_to_path()
    from capture import setup

    out = []
    saved = setup._certutil
    try:
        # Two CAs in Local Machine's store, from two Generates, and one
        # in Current User's.
        held = {"": 2, "-user": 1}
        setup._certutil, calls = _fake_certutil(held)
        folder = _folder(setup)
        done = setup.remove_certificate(folder)
        if held != {"": 0, "-user": 0}:
            out.append(f"after Delete Certificate the stores still hold "
                       f"{held}: a CA left in either is still trusted, "
                       f"and the dialog says it was removed.")
        if sorted(done.stores) != ["Current User", "Local Machine"]:
            out.append(f"the removal reports stores {done.stores}, not "
                       f"both it emptied.")
        left = sorted(p.name for p in folder.iterdir())
        if left != [KEPT]:
            out.append(f"~/.mitmproxy keeps {left} after the removal, not "
                       f"only {KEPT}: a CA file left behind -- above all "
                       f"mitmproxy-ca.pem, the key -- is what the next "
                       f"Generate & Install Cert installs again, and "
                       f"anything else deleted was never the CA's.")
        if done.failures:
            out.append(f"a clean removal reports failures: "
                       f"{done.failures}.")

        # Nothing in either store: asked, and never told to delete.
        held = {}
        setup._certutil, calls = _fake_certutil(held)
        done = setup.remove_certificate(_folder(setup))
        if any("-delstore" in c for c in calls):
            out.append("with no certificate in a store, the removal still "
                       "ran -delstore on it -- Current User's store puts "
                       "Windows' prompt up for that.")
        if done.stores:
            out.append(f"with nothing installed the removal reports "
                       f"stores {done.stores}.")

        # Local Machine refusing, as it does without Administrator.
        held = {"": 1, "-user": 1}
        setup._certutil, calls = _fake_certutil(held, refuse={""})
        done = setup.remove_certificate(_folder(setup))
        where = [store for store, _why in done.failures]
        if where != ["Local Machine"] or done.stores != ["Current User"]:
            out.append(f"with Local Machine refusing, the removal reports "
                       f"failures in {where} and removals from "
                       f"{done.stores}, not a failure in Local Machine and "
                       f"a removal from Current User: a refusal must "
                       f"reach the dialog.")
    finally:
        setup._certutil = saved
    return out
