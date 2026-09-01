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
        wraplength: wrap the label at this pixel width. Wrapped labels
            are left-justified, so a caller does not have to ask.
    """
    # spacing: label ↔ its element -- checkbox, label ↔
    # A checkbox's indicator sits 5px from its own label, which is the
    # rule's number -- but nothing here reaches it either way: the two
    # are inside ONE widget and Tk spaces them itself. Measured the same
    # 5 on every checkbox the audit has looked at, which is what says it
    # is Tk's and not a value someone chose. The marker is here so a
    # grep for the rule finds the app's commonest instance of it, not
    # because there is a lever on this line.
    #
    # Gaining control means splitting every checkbox into a text-less
    # one plus a Label -- the way the Optimizer's Set Configuration rows
    # do -- and that also changes what `fg` colours, since Tk draws the
    # tick in the same option as the text.
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
        # Themed even though the ring above is off: it defaults to
        # SystemButtonFace, and that is the one near-white value left on
        # a widget whose every other colour comes from the palette.
        highlightbackground=colors["bg"],
    )
    if command is not None:
        opts["command"] = command
    if compact:
        opts.update(padx=0, pady=0)
    if wraplength is not None:
        # justify with it, always. A wrapped label is the only way this
        # widget gets a second line, and tk.Checkbutton centres its lines
        # by default -- which reads as ragged beside the `anchor=tk.W`
        # above, and against every other label in the app. Two of the
        # three call sites passed it by hand and the third did not.
        opts["wraplength"] = wraplength
        opts["justify"] = tk.LEFT
    opts.update(kwargs)
    widget = tk.Checkbutton(parent, **opts)
    # NOT dead code: the return value is discarded and the call still has
    # to happen, or a gridful of these appears as blank light-grey blocks
    # for a frame the first time its tab is shown. `ui/utils/realize.py`
    # holds the mechanism and what was measured to establish it.
    #
    # The startup walk there covers everything built during `setup_ui`.
    # This call is for the three panels that rebuild their checkboxes
    # AFTER startup -- Capture's log presets, and Memory Fragments' Sets
    # and unknown main stats -- whose widgets are created long after that
    # walk has run. Both callers are needed; neither subsumes the other.
    widget.winfo_id()
    return widget
