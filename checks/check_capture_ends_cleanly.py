"""A capture that ends badly leaves nothing broken behind.

The program runs as Administrator and edits the system's hosts file, so
what it leaves when it ends matters past its own window. Four ways it
can leave a mess, each silent until the next capture or the next game:

1. **The proxy outlives the program.** A killed or crashed program
   leaves mitmdump bound to its port with nobody reading its pipe; the
   next capture cannot start. The proxy is put in a Job Object that ends
   it when this process's handle closes, however the process ends.
2. **The hosts file is rewritten in place.** Text mode turned every bare
   LF into CRLF on the way back out, changing lines the program never
   touched. Read and written with no newline translation, the redirect
   goes in and comes out leaving the file as it was, byte for byte; a
   copy is kept before the first write.
3. **A stale zstd dictionary wins.** A frozen build's copy beside the
   snapshots, made by an older release, would outlive every newer
   dictionary shipped after it.
4. **A Windows sign-out or shutdown during a capture** never reaches
   `on_close`, so the redirect stayed and the game could not connect.
   Tk hands `WM_QUERYENDSESSION` to the `WM_SAVE_YOURSELF` protocol,
   and the main window stops the capture there.
"""

import inspect
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

from ._harness import SOURCE_ROOT, add_source_to_path

NAME = "a capture that ends badly leaves nothing behind"

HOSTS = (b"# a hosts file\r\n127.0.0.1 localhost\n"
         b"10.0.0.1 caf\xe9.lan\r\n# last line\r\n")


def _alive(pid, wait_s):
    """Whether process `pid` is still running after up to `wait_s`."""
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p,
                                             ctypes.c_uint32)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    synchronize = 0x00100000
    handle = kernel32.OpenProcess(synchronize, False, int(pid))
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle,
                                            int(wait_s * 1000)) != 0
    finally:
        kernel32.CloseHandle(handle)


def _sleeper():
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _the_proxy_dies_with_the_program():
    from capture import job
    out = []
    # The job as this process makes it: closing its handle ends what
    # is in it.
    j = job.kill_on_close_job()
    child = _sleeper()
    try:
        if j is None or not job.assign(j, child.pid):
            return ["a Job Object could not be made or a child put in it, "
                    "so a proxy would outlive a crashed program."]
        job.close(j)
        if _alive(child.pid, 1.0):
            out.append(
                "a child in the proxy's Job Object outlived the job's last "
                "handle. Windows closes that handle when the program ends, "
                "however it ends; without the kill-on-close limit the proxy "
                "stays bound to its port and the next capture cannot start.")
    finally:
        child.kill()

    # And end to end: a program that starts a child through it and is
    # killed outright.
    helper = textwrap.dedent(f"""
        import os, subprocess, sys
        sys.path.insert(0, {str(SOURCE_ROOT)!r})
        from capture import job
        j = job.kill_on_close_job()
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(child.pid if job.assign(j, child.pid) else -1, flush=True)
        os._exit(0)
    """)
    run = subprocess.run([sys.executable, "-c", helper], capture_output=True,
                         text=True, timeout=60, check=False)
    try:
        pid = int(run.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return out + [f"the job helper printed nothing usable: "
                      f"{run.stdout!r} {run.stderr[-300:]!r}"]
    if pid < 0:
        out.append("the job helper could not put its child in the job.")
    elif _alive(pid, 1.0):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, check=False)
        out.append(
            "a program killed with os._exit left its job's child running "
            "a second later. That is a crashed capture's proxy.")
    return out


def _the_hosts_file_round_trips():
    from capture.manager import CaptureManager, HOSTS_BLOCK_START
    out = []
    root = Path(tempfile.mkdtemp(prefix="hosts_"))
    hosts = root / "hosts"
    hosts.write_bytes(HOSTS)
    said = []
    mgr = CaptureManager(root / "snapshots",
                         log_callback=lambda m, *a, **k: said.append(m))
    mgr.hosts_path = hosts
    mgr.hosts_backup_path = root / "backups" / "hosts_before_capture"
    mgr._flush_dns = lambda: None
    mgr.modify_hosts_file()
    added = hosts.read_bytes()
    if not added.startswith(HOSTS):
        out.append(
            "adding the redirect changed the lines before it. The hosts "
            "file is the system's, and its other entries are not ours to "
            "rewrite -- text mode turns every bare LF into CRLF.")
    block = added[len(HOSTS):]
    if HOSTS_BLOCK_START.encode() not in block:
        return out + ["the redirect block was not added."]
    if block.count(b"\r\n") != block.count(b"\n"):
        out.append(
            "the redirect block's lines do not end the way the file's last "
            "line does (CRLF).")
    mgr.remove_hosts_redirect()
    if hosts.read_bytes() != HOSTS:
        out.append(
            f"adding and removing the redirect did not give the hosts file "
            f"back byte for byte: {hosts.read_bytes()!r}, not {HOSTS!r}.")
    backup = mgr.hosts_backup_path
    if not backup.exists() or backup.read_bytes() != HOSTS:
        out.append(
            "no copy of the hosts file as it was was kept before the first "
            "write. The file is rewritten in place, and a crash mid-write "
            "leaves the machine's copy empty.")
    elif not any(str(backup) in str(line) for line in said):
        out.append("the Capture Log was not told where the hosts file's "
                   "copy is.")
    return out


def _a_stale_dictionary_is_replaced():
    from capture.manager import CaptureManager
    out = []
    root = Path(tempfile.mkdtemp(prefix="dict_"))
    bundle = root / "bundle"
    bundle.mkdir()
    (bundle / "zstd_dictionary.bin").write_bytes(b"new dictionary")
    snaps = root / "snapshots"
    snaps.mkdir()
    (snaps / "zstd_dictionary.bin").write_bytes(b"old dictionary")
    mgr = CaptureManager(snaps, log_callback=lambda *a, **k: None)
    sys.frozen, sys._MEIPASS = True, str(bundle)
    try:
        found = mgr._find_dictionary_path()
    finally:
        del sys.frozen, sys._MEIPASS
    if found is None or found.read_bytes() != b"new dictionary":
        out.append(
            "a frozen build kept the zstd dictionary an older release left "
            "beside the snapshots over the one it ships. Every install that "
            "has captured before would decompress with the old one.")
    return out


def _a_session_end_stops_the_capture():
    import ctypes
    import tkinter as tk
    import czn_optimizer_gui as gui
    out = []
    if "self._install_session_end()" not in inspect.getsource(
            gui.OptimizerGUI.__init__):
        out.append("OptimizerGUI.__init__ no longer installs the "
                   "session-end handler.")
    root = tk.Tk()
    try:
        root.attributes("-alpha", 0.0)
        root.update()
        stopped = []
        win = SimpleNamespace(root=root, capture_manager=SimpleNamespace(
            is_capturing=lambda: True,
            stop_capture=lambda: stopped.append(True)))
        for name in ("_install_session_end", "_on_session_end"):
            setattr(win, name, getattr(gui.OptimizerGUI, name).__get__(win))
        win._install_session_end()
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_size_t, ctypes.c_ssize_t)
        wm_queryendsession, endsession_logoff = 0x0011, 0x80000000
        user32.PostMessageW(int(root.wm_frame(), 16), wm_queryendsession,
                            0, endsession_logoff)
        deadline = time.monotonic() + 2.0
        while not stopped and time.monotonic() < deadline:
            root.update()
        if not stopped:
            out.append(
                "Windows asking to end the session did not stop the "
                "capture. A sign-out or shutdown then leaves the hosts "
                "redirect, and the game cannot connect until the program "
                "is next started as Administrator.")
    finally:
        root.destroy()
    return out


def run():
    add_source_to_path()
    if sys.platform != "win32":
        from ._harness import Skip
        raise Skip("Job Objects, the hosts file and session end are "
                   "Windows'")
    failures = _the_proxy_dies_with_the_program()
    failures.extend(_the_hosts_file_round_trips())
    failures.extend(_a_stale_dictionary_is_replaced())
    failures.extend(_a_session_end_stops_the_capture())
    return failures


FAULTS = [
    ("the kill-on-close limit dropped", "capture.job:kill_on_close_job",
     "info.BasicLimitInformation.LimitFlags = "
     "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE",
     "info.BasicLimitInformation.LimitFlags = 0",
     "outlived the job's last handle"),
    ("the hosts file read with newline translation",
     "capture.manager:CaptureManager._read_hosts",
     'errors="surrogateescape", newline="") as f:',
     'errors="surrogateescape") as f:',
     "changed the lines before it"),
    ("no copy before the first write",
     "capture.manager:CaptureManager._write_hosts",
     "if not self._hosts_backed_up:", "if False:",
     "no copy of the hosts file"),
    ("the old dictionary kept",
     "capture.manager:CaptureManager._find_dictionary_path",
     "            if (not dest.exists()\n"
     "                    or dest.read_bytes() != shipped.read_bytes()):",
     "            if not dest.exists():",
     "kept the zstd dictionary"),
    ("the session end on another protocol",
     "czn_optimizer_gui:OptimizerGUI._install_session_end",
     '"WM_SAVE_YOURSELF"', '"WM_TAKE_FOCUS"',
     "did not stop the capture"),
]
