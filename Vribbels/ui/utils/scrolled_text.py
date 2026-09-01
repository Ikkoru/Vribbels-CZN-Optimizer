"""One scrolled text widget for the whole UI.

A text panel is a `tk.Text` and a `ttk.Scrollbar` side by side in a
`ttk.Frame`, with the frame's geometry methods copied onto the Text so
a caller packs the pair by packing the widget it was handed.

**`scrolledtext.ScrolledText` is deliberately not used.** It is the same
shape, but the frame and scrollbar it builds are `tk` and no constructor
keyword reaches them: every keyword goes to the Text. So the frame keeps
Tk's near-white default and paints before the Text covers it, which
shows as the whole panel flashing white on first display, and the
scrollbar keeps classic Tk's grey however `TScrollbar` is styled. Both
were corrected here by hand afterwards. Building the pair from ttk
answers both at the source: the theme reaches a `ttk.Frame` and a
`ttk.Scrollbar` directly, and one `TScrollbar` style now paints every
scrollbar in the app.

**The map-time erase is a different fault** and still needs
`ui/utils/realize.py`; the walk there covers these three widgets the way
it covers every other. What went away is the second, colour half.

The other options below are the same corrections every text panel in
this app makes: `bd` and `highlightthickness` default to 1 each on a
Text, adding stray inset and drawing a sunken border and focus ring in
colours the dark theme never set.

`docs/ui_spacing.md` covers where the inset lives on these panels and
why `padx`/`pady` are not symmetric between them.
"""

import tkinter as tk
from tkinter import ttk


class _ScrolledText(tk.Text):
    """A Text and its scrollbar in one frame, addressed as the Text."""

    def __init__(self, master=None, **kw):
        self.frame = ttk.Frame(master)
        self.vbar = ttk.Scrollbar(self.frame, orient=tk.VERTICAL)
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)

        kw["yscrollcommand"] = self.vbar.set
        tk.Text.__init__(self, self.frame, **kw)
        # Still the Text's own `pack` at this point, which is what puts
        # it in the frame. The copy below is what makes the NEXT call
        # reach the frame instead.
        self.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vbar["command"] = self.yview

        # NOT dead code: without this, a caller's `.pack()` packs the
        # bare Text into the panel and the scrollbar is never placed, so
        # the frame collapses and nothing shows. Text's own names are
        # excluded so text methods keep working -- `config` and
        # `configure` above all, which callers use to set `state`.
        geometry = (vars(tk.Pack).keys() | vars(tk.Grid).keys()
                    | vars(tk.Place).keys()) - vars(tk.Text).keys()
        for name in geometry:
            if not name.startswith("_") and name not in ("config", "configure"):
                setattr(self, name, getattr(self.frame, name))

    def __str__(self):
        """The frame's path, so passing this to Tk addresses the pair."""
        return str(self.frame)


def make_scrolled_text(parent, colors, *, padx=4, pady=3, **kwargs):
    """A dark-themed scrolled text, wrapper and scrollbar included.

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
    return _ScrolledText(parent, **opts)
