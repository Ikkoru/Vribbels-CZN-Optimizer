"""A window above 100% answers Windows' DPI-change size query.

Per-monitor aware (V2), a window dragged across to a monitor of another
DPI is first asked `WM_GETDPISCALEDSIZE`. Tk does not answer it, and
unanswered, Windows scales the window by the DPIs' ratio -- the frame
doubles onto a 200% screen while the content, drawn at the user's scale
everywhere, does not. `ui/dpi_hold.py` answers with the size that keeps
the client area as it is.

A sent message cannot move a window to another monitor, so this asks
what it can: the query, at twice the window's DPI, to a window
`hold_size` has wrapped -- which must answer, with a size well short of
double -- and to one it has not, which must NOT answer, or Tk has taken
the message over and this guard needs a second look. Then
`WM_DPICHANGED` at the window's own DPI with a doubled rectangle: the
wrapped window keeps its size.

Run in a process of its own: DPI awareness belongs to the process and
its first window fixes it.
"""

import ast
import subprocess
import sys

from ._harness import SOURCE_ROOT, Skip

NAME = "a scaled window keeps its size across monitors"

PROBE = r"""
import ctypes, sys
from ctypes import wintypes
sys.path.insert(0, ".")
from ui import scaling
scaling.set_scale("150%")
scaling.declare_dpi_awareness()
import tkinter as tk
from ui import dpi_hold
user32 = ctypes.windll.user32
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, ctypes.c_void_p]
out = []
for wrap in (True, False):
    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    root.geometry("400x300+100+100")
    root.update()
    if wrap:
        dpi_hold.hold_size(root)
    hwnd = int(root.wm_frame(), 16)
    dpi = user32.GetDpiForWindow(hwnd)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    outer = (rect.right - rect.left, rect.bottom - rect.top)
    size = wintypes.SIZE(0, 0)
    answered = user32.SendMessageW(hwnd, 0x02E4, 2 * dpi, ctypes.byref(size))
    before = (root.winfo_width(), root.winfo_height())
    doubled = wintypes.RECT(rect.left, rect.top, rect.left + 2 * outer[0],
                            rect.top + 2 * outer[1])
    user32.SendMessageW(hwnd, 0x02E0, dpi | (dpi << 16),
                        ctypes.byref(doubled))
    root.update()
    after = (root.winfo_width(), root.winfo_height())
    out.append((wrap, answered, outer, (size.cx, size.cy), before, after))
    root.destroy()
print(out)
"""


def run():
    if sys.platform != "win32":
        raise Skip("Windows only")
    done = subprocess.run([sys.executable, "-c", PROBE],
                          cwd=str(SOURCE_ROOT), capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=120)
    if done.returncode:
        tail = (done.stderr.strip().splitlines() or ["?"])[-1]
        if "TclError" in tail and "display" in tail:
            raise Skip(f"Tk will not start here ({tail})")
        return [f"the probe raised: {tail}"]
    out = []
    rows = ast.literal_eval(done.stdout.strip().splitlines()[-1])
    for wrapped, answered, outer, size, before, after in rows:
        if wrapped:
            if not answered:
                out.append(
                    "a window held by `dpi_hold.hold_size` did not answer "
                    "WM_GETDPISCALEDSIZE, so Windows will scale it by the "
                    "DPIs' ratio on a drag between monitors.")
            elif not (outer[0] <= size[0] < 1.5 * outer[0]
                      and outer[1] <= size[1] < 1.5 * outer[1]):
                out.append(
                    f"asked for its size at twice its DPI, a held window "
                    f"answered {size} against its {outer}: it should be "
                    f"its client area plus a larger frame, not scaled.")
            if after != before:
                out.append(
                    f"a held window went from {before} to {after} on a "
                    f"WM_DPICHANGED offering it twice its size: its frame "
                    f"would grow around content that stays as it was.")
        elif answered:
            out.append(
                "an unwrapped window answered WM_GETDPISCALEDSIZE itself: "
                "Tk handles it now, and `ui/dpi_hold.py` may be fighting "
                "it. Look at what Tk does before trusting either.")
    return out
