"""Keep a window its own size when it is dragged between monitors.

Above 100% the process is per-monitor DPI aware (`scaling`), and a
window crossing to a monitor of another DPI is sent `WM_DPICHANGED`
with a rectangle scaled by the ratio of the two DPIs -- which Tk then
applies, so a window dragged from a 100% screen onto a 200% one doubles
its frame. The program draws at the scale the user chose on EVERY
monitor (Tk follows no per-monitor DPI), so the content stays as it was
and the extra frame is empty space.

So the window's procedure is wrapped: `WM_GETDPISCALEDSIZE`, which
Windows asks while the window is being dragged across, and
`WM_DPICHANGED`, sent once it is across, both answer with the size that
keeps the CLIENT area unchanged at the new DPI. Only the frame -- the
title bar and borders Windows draws for that monitor -- changes size.
Everything else goes to the window's own procedure as before.
"""

import ctypes
import sys
from ctypes import wintypes

WM_DPICHANGED = 0x02E0
WM_GETDPISCALEDSIZE = 0x02E4
GWLP_WNDPROC = -4
GWL_STYLE = -16
GWL_EXSTYLE = -20
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

# The wrappers handed to Windows, and the procedures they replaced. Held
# for the life of the process: Windows calls a wrapper by address, and
# one the collector freed would be a crash on the next message.
_held = {}


def _api():
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                              wintypes.UINT, wintypes.WPARAM,
                              wintypes.LPARAM)
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int,
                                         ctypes.c_void_p]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND,
                                       wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM]
    user32.AdjustWindowRectExForDpi.argtypes = [
        ctypes.POINTER(wintypes.RECT), wintypes.DWORD, wintypes.BOOL,
        wintypes.DWORD, wintypes.UINT]
    return user32, proc


def outer_size(hwnd, dpi):
    """The window size that holds `hwnd`'s current client area at
    `dpi`: the client plus the frame Windows draws at that DPI."""
    user32, _proc = _api()
    client = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client))
    rect = wintypes.RECT(0, 0, client.right, client.bottom)
    user32.AdjustWindowRectExForDpi(
        ctypes.byref(rect),
        user32.GetWindowLongPtrW(hwnd, GWL_STYLE) & 0xFFFFFFFF, False,
        user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF, dpi)
    return rect.right - rect.left, rect.bottom - rect.top


def hold_size(window):
    """Wrap `window`'s frame procedure as the module docstring says.

    The window must have been mapped (at alpha 0 counts): Tk makes its
    frame window then. Returns False where nothing was wrapped -- not
    Windows, or wrapped already.
    """
    if sys.platform != "win32":
        return False
    user32, proc = _api()
    hwnd = int(window.wm_frame(), 16)
    if hwnd in _held:
        return False
    previous = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

    def handle(h, message, wparam, lparam):
        if message == WM_GETDPISCALEDSIZE:
            size = ctypes.cast(lparam, ctypes.POINTER(wintypes.SIZE))
            size[0].cx, size[0].cy = outer_size(h, wparam & 0xFFFF)
            return 1
        if message == WM_DPICHANGED:
            suggested = ctypes.cast(lparam,
                                    ctypes.POINTER(wintypes.RECT))[0]
            width, height = outer_size(h, wparam & 0xFFFF)
            user32.SetWindowPos(h, None, suggested.left, suggested.top,
                                width, height,
                                SWP_NOZORDER | SWP_NOACTIVATE)
            return 0
        return user32.CallWindowProcW(previous, h, message, wparam, lparam)

    wrapper = proc(handle)
    _held[hwnd] = (wrapper, previous)
    user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC,
                             ctypes.cast(wrapper, ctypes.c_void_p))
    return True
