"""One scrolled text widget for the whole UI.

`scrolledtext.ScrolledText` is a `tk.Text` that builds its own wrapping
`tk.Frame` and `tk.Scrollbar` and then borrows the frame's geometry
methods. Those two are NOT reachable through the constructor: every
keyword goes to the Text. So the frame keeps Tk's default background --
system near-white -- and it paints before the Text paints over it, which
shows as the whole panel flashing white on first display.

**That is a different fault from the first-map erase** in
`ui/utils/realize.py`, and the two need separate fixes. Realizing the
window early cannot help here, because the frame's background genuinely
IS white; there is nothing to create earlier. Equally, colouring the
frame does not remove the erase. A ScrolledText needs both, which is why
neither fix alone made the Capture Log clean.

The other options are the same corrections every text panel in this app
makes: `bd` and `highlightthickness` default to 1 each on a Text, adding
stray inset and drawing a sunken border and focus ring in colours the
dark theme never set.

`docs/ui_spacing.md` covers where the inset lives on these panels and why
`padx`/`pady` are not symmetric between them.
"""

import tkinter as tk
from tkinter import scrolledtext


def make_scrolled_text(parent, colors, *, padx=6, pady=6, **kwargs):
    """A dark-themed `ScrolledText`, wrapper and scrollbar included.

    Args:
        parent: the containing widget.
        colors: the palette dict every tab carries as `self.colors`.
        padx / pady: the text's own inset. `pady` differs between panels
            because the font's line box already contributes space above
            the first glyph -- see `docs/ui_spacing.md`.
        **kwargs: passed to the Text (`height`, `wrap`, `font`, ...).
    """
    opts = dict(
        bg=colors["bg_light"], fg=colors["fg"],
        insertbackground=colors["fg"],
        bd=0, highlightthickness=0,
        padx=padx, pady=pady,
    )
    opts.update(kwargs)
    widget = scrolledtext.ScrolledText(parent, **opts)

    # NOT optional, and not reachable through the constructor above.
    # Guarded because both attributes are tkinter implementation detail
    # rather than public API.
    try:
        widget.frame.configure(bg=colors["bg_light"])
    except (AttributeError, tk.TclError):
        pass
    try:
        widget.vbar.configure(
            bg=colors["bg_light"],
            troughcolor=colors["bg"],
            activebackground=colors["bg_lighter"],
        )
    except (AttributeError, tk.TclError):
        pass
    return widget
