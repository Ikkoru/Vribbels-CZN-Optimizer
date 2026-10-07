"""A window's client area as Windows renders it, not as the screen shows it.

    image = render(widget)        # PIL RGB, widget.winfo_width() wide

Asks the window to draw itself (`PrintWindow`, with the flag that takes
the compositor's copy of its content), so what comes back does not
depend on the screen at all:

  * the window can be at alpha 0 -- the spacing audit's app is never
    made visible;
  * it can be larger than every monitor, or off them -- the app at 200%
    is 3100 x 2000;
  * nothing over it, the pointer, a tooltip or the taskbar, is in the
    picture.

Measured against reading the screen: the 100% audit read every gap the
same, and its baseline did not move.

Windows only, through ctypes. This is a Windows application.
"""

import ctypes
from ctypes import wintypes

from PIL import Image

# PrintWindow's flags: the client area only, and the content the
# compositor holds -- what the screen would show -- rather than a
# repaint into the bitmap. A Tk window renders the same either way;
# the compositor's copy is the one the audit was proven against.
PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def render(widget):
    """`widget`'s toplevel client area, rendered, as an RGB image the
    size of `widget` -- which is meant to be a toplevel, so the two are
    one area. Raises RuntimeError where Windows declines."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    inner = widget.winfo_id()
    # A Tk toplevel's own id is the client window inside the frame
    # Windows draws; PrintWindow wants the frame.
    frame = user32.GetParent(inner) or inner
    width, height = widget.winfo_width(), widget.winfo_height()
    source = user32.GetDC(inner)
    dc = gdi32.CreateCompatibleDC(source)
    bitmap = gdi32.CreateCompatibleBitmap(source, width, height)
    try:
        gdi32.SelectObject(dc, bitmap)
        if not user32.PrintWindow(frame, dc,
                                  PW_CLIENTONLY | PW_RENDERFULLCONTENT):
            raise RuntimeError("PrintWindow declined to render the window")
        # A negative height asks for the rows top-down, as PIL wants.
        info = _BitmapInfoHeader(ctypes.sizeof(_BitmapInfoHeader), width,
                                 -height, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = ctypes.create_string_buffer(width * height * 4)
        if gdi32.GetDIBits(dc, bitmap, 0, height, pixels,
                           ctypes.byref(info), 0) != height:
            raise RuntimeError("the rendered rows could not be read back")
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(inner, source)
    # Copied out: `frombuffer` shares the ctypes buffer's memory, which
    # is this function's to free.
    return Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX",
                            0, 1).copy()
