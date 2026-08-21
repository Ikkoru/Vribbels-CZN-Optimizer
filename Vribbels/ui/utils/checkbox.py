"""One checkbox widget for the whole UI.

Every checkbox is a `tk.Checkbutton`, never a `ttk.Checkbutton`. The two
draw DIFFERENT indicators at different sizes with different internal
padding, so mixing them makes distances between checkbox rows disagree
between panels for reasons no padding value explains.

`tk.Checkbutton` is the one that survives, for three reasons: it honours
`font` directly where ttk's font handling varies by theme and silently
drops `overstrike`; it takes a per-widget `fg`, which a ttk style cannot
do without a style per colour; and its padding is a plain widget option
rather than a theme layer. The cost is that nothing inherits the dark
palette any more, which is what this module exists to supply.

Asymmetric padding is the one thing `tk.Checkbutton` cannot express --
its `padx` applies to both sides. Where a lever needs one side only, use
the geometry manager: `cb.pack(padx=(left, right))`.
"""

import tkinter as tk


def make_checkbox(parent, colors, *, text="", variable=None, command=None,
                  font=("Segoe UI", 9), fg=None, compact=False,
                  wraplength=None, **kwargs):
    """A dark-themed `tk.Checkbutton`.

    Args:
        parent: the containing widget.
        colors: the palette dict every tab carries as `self.colors`.
        text: label text. Empty for the text-less checkboxes that sit
            beside a separate label.
        variable: the `tk.BooleanVar` / `tk.IntVar` to bind.
        command: called on toggle.
        font: defaults to the UI body font.
        fg: overrides the foreground, for the rows that colour their
            label by element. Falls back to the palette's `fg`.
        compact: drop the widget's own padding to zero, for rows whose
            height is constrained by something else (the Optimizer
            toolbar's status cluster).
        wraplength: wrap the label at this pixel width.
    """
    colour = fg or colors["fg"]
    opts = dict(
        text=text, variable=variable,
        bg=colors["bg"], fg=colour,
        selectcolor=colors["bg_light"],
        activebackground=colors["bg"], activeforeground=colour,
        font=font, anchor=tk.W,
        # highlightthickness kills the ring Tk paints OUTSIDE the widget;
        # takefocus stops it ever being the focused widget, which is what
        # paints the dotted rectangle around the label. These filters are
        # clicked, never tabbed to, so nothing is lost -- but note that
        # this does remove them from the keyboard tab order.
        highlightthickness=0, bd=0, takefocus=0,
    )
    if command is not None:
        opts["command"] = command
    if compact:
        opts.update(padx=0, pady=0)
    if wraplength is not None:
        opts["wraplength"] = wraplength
    opts.update(kwargs)
    return tk.Checkbutton(parent, **opts)
