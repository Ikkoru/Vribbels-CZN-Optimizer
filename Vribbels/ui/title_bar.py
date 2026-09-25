"""The title bar Windows draws over each of the app's windows.

Tk has no say in it: the caption is Windows' own, painted by the desktop
window manager (DWM). What DWM lets an app choose is a window ATTRIBUTE:

* **Windows 11** (build 22000 on) takes the caption's colours outright --
  `CAPTION` behind the title, the app's text colour on it -- and dark
  mode for the menus and buttons beside them.
* **Windows 10** (build 17763 on) takes only dark or light, which here
  follows the system's own app theme as its settings last set it.

Anything older, and every other platform, keeps its default. The native
message and file dialogs are Windows' own windows and keep theirs.

An attribute set before a window is first shown is simply there; one
set on a window already showing waits for its next frame repaint, which
`style_title_bar` asks for.
"""

import sys

CAPTION = "#191926"

# From dwmapi.h. The dark-mode attribute was 19 before Windows 10 20H1.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
WINDOWS_11 = 22000
DARK_MODE_BUILD = 18985
FIRST_DARK_BUILD = 17763

# SetWindowPos: repaint the frame, and nothing else.
_FRAME_ONLY = 0x0020 | 0x0001 | 0x0002 | 0x0004     # FRAMECHANGED, NO SIZE/MOVE/ZORDER


def _colorref(colour):
    """`#rrggbb` as the 0x00bbggrr Windows wants."""
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return r | (g << 8) | (b << 16)


def system_uses_dark():
    """Whether Windows' app theme is dark. Light where it cannot say."""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes"
                r"\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def style_title_bar(window, text_colour):
    """Colour `window`'s title bar as this build of Windows allows.

    Returns the HRESULT of every attribute set, 0 each where it took --
    empty where nothing applies. The window must exist on screen, mapped
    or at alpha 0: Tk makes its frame window when it first maps it.
    """
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    build = sys.getwindowsversion().build
    if build < FIRST_DARK_BUILD:
        return []
    hwnd = wintypes.HWND(int(window.wm_frame(), 16))
    dwm = ctypes.windll.dwmapi

    def put(attribute, value):
        data = ctypes.c_uint(value)
        return dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data),
                                         ctypes.sizeof(data))

    if build >= WINDOWS_11:
        results = [put(DWMWA_USE_IMMERSIVE_DARK_MODE, 1),
                   put(DWMWA_CAPTION_COLOR, _colorref(CAPTION)),
                   put(DWMWA_TEXT_COLOR, _colorref(text_colour))]
    else:
        results = [put(DWMWA_USE_IMMERSIVE_DARK_MODE
                       if build >= DARK_MODE_BUILD
                       else DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                       1 if system_uses_dark() else 0)]
    ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, _FRAME_ONLY)
    return results


def apply_title_bar(window, text_colour):
    """`style_title_bar` for a window being shown: a caption that cannot
    be coloured is a cosmetic, never a reason for the window to fail."""
    import tkinter as tk
    try:
        style_title_bar(window, text_colour)
    except (tk.TclError, OSError, ValueError):
        pass
