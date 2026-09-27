"""A still of a widget's pixels, held over it while it repaints.

Tk draws a window's widgets one at a time, straight to the screen, and
the compositor shows whatever is there at each frame. A tab's worth of
widgets takes several frames to draw, so a tab switch shows the new
tab arriving over the old one, a few widgets a frame.

A `Still` copies what the screen shows of a widget -- on a worker
thread, so the copy costs the Tk thread nothing while it has other work
-- and `held()` puts that copy over the widget, in a window of its own,
for as long as its body runs. The widget repaints underneath, unseen,
and the whole of it appears when the copy goes: the compositor shows
both changes in the same frame.

The copy's window takes no focus and no clicks (`WS_EX_NOACTIVATE`,
`WS_EX_TRANSPARENT`), and is owned by the widget's toplevel, so it
sits over that and nothing else it was not already over.

Windows only; elsewhere, and wherever anything fails, the body simply
runs with nothing held over it.
"""

import ctypes
import sys
import threading
from contextlib import contextmanager

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x00080000, 0x00000020
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x00000080, 0x08000000
SW_SHOWNOACTIVATE = 4
ULW_OPAQUE = 0x00000004
SRCCOPY = 0x00CC0020
DWMWA_TRANSITIONS_OFF = 3           # DWMWA_TRANSITIONS_FORCEDISABLED

_api = None


def _win32():
    """user32, gdi32 and dwmapi with the signatures 64-bit handles
    need.

    Loaded here rather than taken from `ctypes.windll`, whose function
    objects every module shares: signatures set on those would change
    how the title bar's own calls are converted."""
    global _api
    if _api is None:
        from ctypes import wintypes as w
        user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
        dwmapi = ctypes.WinDLL("dwmapi")
        user32.GetDC.restype = w.HDC
        user32.GetDC.argtypes = [w.HWND]
        user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
        user32.IsIconic.argtypes = [w.HWND]
        user32.IsWindowVisible.argtypes = [w.HWND]
        user32.CreateWindowExW.restype = w.HWND
        user32.CreateWindowExW.argtypes = [
            w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU,
            w.HINSTANCE, w.LPVOID]
        user32.UpdateLayeredWindow.argtypes = [
            w.HWND, w.HDC, ctypes.POINTER(w.POINT), ctypes.POINTER(w.SIZE),
            w.HDC, ctypes.POINTER(w.POINT), w.COLORREF, w.LPVOID, w.DWORD]
        user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        user32.DestroyWindow.argtypes = [w.HWND]
        gdi32.CreateCompatibleDC.restype = w.HDC
        gdi32.CreateCompatibleDC.argtypes = [w.HDC]
        gdi32.CreateCompatibleBitmap.restype = w.HBITMAP
        gdi32.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int,
                                                 ctypes.c_int]
        gdi32.SelectObject.restype = w.HGDIOBJ
        gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
        gdi32.BitBlt.argtypes = [w.HDC] + [ctypes.c_int] * 4 + [
            w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD]
        gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
        gdi32.DeleteDC.argtypes = [w.HDC]
        dwmapi.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD,
                                                 w.LPVOID, w.DWORD]
        _api = (user32, gdi32, dwmapi, w)
    return _api


class Still:
    """What the screen shows of `widget` now, copied on a worker."""

    def __init__(self, widget):
        self._copy = None
        if sys.platform != "win32":
            return
        try:
            user32 = _win32()[0]
            top = widget.winfo_toplevel()
            self._rect = (widget.winfo_rootx(), widget.winfo_rooty(),
                          widget.winfo_width(), widget.winfo_height())
            self._owner = int(top.wm_frame(), 16)
            # Nothing to copy from a window the screen does not show --
            # one at alpha 0, as startup and the checks keep theirs, would
            # have its copy taken of whatever lies behind it.
            if (self._rect[2] < 2 or self._rect[3] < 2
                    or not user32.IsWindowVisible(self._owner)
                    or user32.IsIconic(self._owner)
                    or float(top.attributes("-alpha")) < 1):
                return
        except Exception:                                   # noqa: BLE001
            return
        self._mem = self._bitmap = self._previous = None
        self._copy = threading.Thread(target=self._take, daemon=True)
        self._copy.start()

    def _take(self):
        """The copy itself, off the Tk thread: ctypes lets go of the
        GIL for the whole of it."""
        user32, gdi32, _dwm, _w = _win32()
        x, y, width, height = self._rect
        screen = user32.GetDC(None)
        try:
            self._mem = gdi32.CreateCompatibleDC(screen)
            self._bitmap = gdi32.CreateCompatibleBitmap(screen, width,
                                                        height)
            self._previous = gdi32.SelectObject(self._mem, self._bitmap)
            gdi32.BitBlt(self._mem, 0, 0, width, height, screen, x, y,
                         SRCCOPY)
        finally:
            user32.ReleaseDC(None, screen)

    def _show(self):
        """Put the copy up, and wait until it is on screen. Its window,
        or None."""
        if self._copy is None:
            return None
        self._copy.join()
        if not self._bitmap:
            return None
        user32, _gdi, dwmapi, w = _win32()
        x, y, width, height = self._rect
        window = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE, "STATIC", None, WS_POPUP, x, y, width,
            height, self._owner, None, None, None)
        if not window:
            return None
        user32.UpdateLayeredWindow(
            window, None, ctypes.byref(w.POINT(x, y)),
            ctypes.byref(w.SIZE(width, height)), self._mem,
            ctypes.byref(w.POINT(0, 0)), 0, None, ULW_OPAQUE)
        # No fade in or out: faded, the copy lets the repaint through as
        # it arrives, and lingers over the finished tab as it goes.
        off = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(window, DWMWA_TRANSITIONS_OFF,
                                     ctypes.byref(off), ctypes.sizeof(off))
        user32.ShowWindow(window, SW_SHOWNOACTIVATE)
        # **Until the compositor has shown it**, and no longer. A repaint
        # started sooner can reach the screen a frame before the copy
        # does: the first widgets drawn flash over the old tab.
        dwmapi.DwmFlush()
        return window

    def discard(self):
        """Let the copy go without showing it."""
        self._free()

    def _free(self):
        if self._copy is None:
            return
        self._copy.join()
        _user, gdi32, _dwm, _w = _win32()
        if self._mem:
            gdi32.SelectObject(self._mem, self._previous)
            gdi32.DeleteDC(self._mem)
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)
        self._copy = None

    @contextmanager
    def held(self):
        """Hold the copy over the widget while the body runs."""
        try:
            window = self._show()
        except Exception:                                   # noqa: BLE001
            window = None
        try:
            yield
        finally:
            if window is not None:
                user32, gdi32, _dwm, _w = _win32()
                # Everything drawn underneath reaches the window before
                # the copy comes off it.
                gdi32.GdiFlush()
                user32.DestroyWindow(window)
            self._free()
