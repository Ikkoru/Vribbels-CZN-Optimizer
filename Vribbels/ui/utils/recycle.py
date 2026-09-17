"""Delete a file to the Recycle Bin, where the drive has one.

Used for the ONE deletion in the app that no verified copy stands
behind: the capture archive, removed by hand from the Setup tab.
Everything else the archiver deletes was matched against its archived
member a moment earlier, and sending those to the bin would guard a
failure that verification has already ruled out while filling a user's
bin with hundreds of files they would not recognise.

`SHFileOperationW` with `FOF_ALLOWUNDO` rather than `send2trash`: the
build already has one fragile third-party step and the call is twenty
lines of `ctypes`. Where there is no bin -- a network share, a
removable drive, a policy that turns it off -- Windows deletes outright
and reports success, which is the same answer the caller wants.
"""

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004
FOF_NOERRORUI = 0x0400


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def recycle(path) -> bool:
    """Send one file to the bin. True if it is gone afterwards.

    Falls back to `os.remove` off Windows and when the shell call is
    unavailable, so the caller has one answer to handle rather than
    two.
    """
    path = Path(path)
    if not path.exists():
        return True
    if sys.platform != "win32":
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    try:
        # **Double-NUL terminated**: the field is a LIST of paths, and
        # a single terminator leaves the shell reading past the string.
        op = _SHFILEOPSTRUCTW(
            hwnd=None, wFunc=FO_DELETE,
            pFrom=str(path.resolve()) + "\0\0", pTo=None,
            fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
            | FOF_NOERRORUI,
            fAnyOperationsAborted=False, hNameMappings=None,
            lpszProgressTitle=None)
        ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    except (AttributeError, OSError, ValueError):
        pass
    if not path.exists():
        return True
    try:
        os.remove(path)
        return True
    except OSError:
        return False
