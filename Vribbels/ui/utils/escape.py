"""Escape closes a popup window.

Every window the app opens over the main one answers to Escape: the
contributions popup, the Restore Defaults dialog, and the hover tooltip.
The `messagebox` dialogs already do -- those are drawn by Windows.

One helper rather than three bindings, so a window added later is one
call away from behaving like the rest, and a check can say when one
was not.
"""

import tkinter as tk


def close_on_escape(window, on_close=None):
    """Bind Escape on `window` so the key closes it.

    `on_close` replaces the default of destroying the window, for a
    dialog that has something to tear down first.

    Returns nothing useful. Binds with `add="+"`, so a window that also
    binds Escape for its own reasons keeps both.

    **Not for a window with `wm_overrideredirect` set.** Such a window
    takes no keyboard focus, so the key never arrives -- the binding
    has to sit on whatever does have focus instead. `Tooltip` does that
    for the one popup in this app that is built that way.
    """
    close = on_close or window.destroy

    def dismiss(_event=None):
        try:
            if not window.winfo_exists():
                return None
        except tk.TclError:
            return None
        close()
        return "break"

    window.bind("<Escape>", dismiss, add="+")
    # A dialog that has never been clicked has no focus inside it, and
    # a key event goes to whatever does -- so the window is given focus
    # rather than waiting to be clicked for Escape to work.
    try:
        window.focus_set()
    except tk.TclError:
        pass
