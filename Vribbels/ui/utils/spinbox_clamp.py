"""Hold a Spinbox's variable inside the range the Spinbox declares.

**A `tk.Spinbox`'s `from_`/`to` bound its BUTTONS and its wheel, not its
text.** Typed input reaches the variable unchecked in both directions --
500 and -7 both arrive intact through a `from_=0, to=100` spinbox -- so
the floor needs this as much as the ceiling does. Nothing about it is
visible until the bad number reaches whatever reads the variable.

    clamp_on_commit(spin, var, colors, root)

The bounds are READ OFF THE WIDGET rather than passed in, so each
spinbox declares its own range once and this enforces what it declared.
A field meant to accept negatives says so with its own `from_`.
"""

import tkinter as tk


# A clamp that snapped silently would read as the number being accepted.
# Three quick flashes behind the value say it moved.
#
# Its own red, not the palette's: `red` is a foreground, chosen to read
# as text against the dark background, and a field filled with it puts
# the value it is about invisibly on top. This one is dark enough to
# keep the digits legible while it flashes.
CLAMP_ALERT = "#9b0f1b"
CLAMP_BLINK_MS = 110
CLAMP_BLINKS = 3


def blink(widget, root, normal):
    """Flash a widget's background between the alert colour and its own,
    ending on its own."""
    last = CLAMP_BLINKS * 2 - 1

    def step(n):
        try:
            widget.config(bg=CLAMP_ALERT if n % 2 == 0 else normal)
        except tk.TclError:
            return                       # the tab went away mid-blink
        if n < last:
            root.after(CLAMP_BLINK_MS, step, n + 1)

    step(0)


def commit_clamp(spin, var, colors, root, state=None):
    """Hold `var` inside `spin`'s range, blinking it if it moved.

    Callable rather than only bound, and that matters: Tk will not
    deliver a key event to an unmapped widget, so nothing headless can
    press Return into a spinbox. A clamp reachable only through its
    binding is a clamp only the maintainer can test.

    `state` carries the last value that WAS a number. Text that is not
    one cannot be clamped toward anything, so the field goes back to
    what it last held rather than to a bound -- which for a field the
    user has not otherwise touched is the saved value.

    Returns whether it changed anything.
    """
    lo, hi = float(spin.cget("from")), float(spin.cget("to"))
    try:
        value = var.get()
    except tk.TclError:
        if state is None:
            return False
        var.set(state["good"])
        blink(spin, root, colors["bg_light"])
        return True
    held = type(value)(min(max(value, lo), hi))
    if state is not None:
        state["good"] = held
    if held == value:
        return False
    var.set(held)
    blink(spin, root, colors["bg_light"])
    return True


def clamp_on_commit(spin, var, colors, root):
    """Bind the clamp to `spin`, on commit rather than per keystroke.

    Mid-edit the field passes through states that are not numbers at all
    -- empty after a select-all, a lone minus sign -- and a per-stroke
    clamp would spend most of its life fighting them.

    The VARIABLE is what gets held, not the saved value. Clamping only
    on the way out would leave the field reading 500 while whatever
    reads the variable used 100.
    """
    state = {}
    try:
        state["good"] = var.get()
    except tk.TclError:
        state["good"] = spin.cget("from")

    def commit(_event=None):
        commit_clamp(spin, var, colors, root, state)

    spin.bind("<FocusOut>", commit, add="+")
    spin.bind("<Return>", commit, add="+")
