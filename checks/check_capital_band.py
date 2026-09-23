"""A Text line's first capital is read where the Text drew it.

The spacing audit reads the gap between two rows of a Text between
their first CAPITALS, which puts both ends of the reading on the rules'
own references. Where that capital sits has to come from the widget:
measuring the string knows no tab stop and no tag's font, and on a row
that reaches its first capital through a tab -- `50/50s won<tab>Bottom`
-- the measured offset lands inside the words before the tab, on a
slash that hangs two below the baseline. The reading then comes out two
short, with nothing saying it was taken off the wrong glyph.

Maps one small window at alpha 0 -- a Text says where it drew a
character only once it is displayed -- and destroys it.
"""

from ._harness import Skip, add_source_to_path

NAME = "a Text line's capital is where it was drawn"

# Where the second column starts: the capital after the tab has to be
# read here, and nowhere a measured string would put it.
STOP = 120


def run():
    add_source_to_path()
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as e:                    # no display, headless CI
        raise Skip(f"Tk will not start here ({type(e).__name__})")

    failures = []
    try:
        root.attributes("-alpha", 0.0)
        from ui import spacing_registry as registry

        text = tk.Text(root, font=("Segoe UI", 9), tabs=(STOP,), padx=0,
                       pady=0, bd=0, highlightthickness=0, wrap=tk.NONE,
                       width=40, height=3)
        text.pack()
        text.insert(tk.END, "50/50s won\tBottom 13%\nLuck\tTop 12%\n")
        # An embedded window takes an index `get` does not return, so
        # a capital found by counting the string lands a character
        # early on this line.
        text.window_create(tk.END, window=tk.Frame(text, width=8,
                                                   height=8))
        text.insert(tk.END, "ab\tBottom")
        root.update()
        left = registry.sa.box_of(text).left
        for line, words, want in (
                (1, "50/50s won<tab>Bottom", left + STOP),
                (2, "Luck<tab>Top", left),
                (3, "<window>ab<tab>Bottom", left + STOP)):
            band = registry._capital_band(text, line)
            got = None if band is None else band.left
            if got != want:
                failures.append(
                    f"the first capital of {words!r} is read at x={got}, "
                    f"where the Text drew it at x={want}. Row pitches are "
                    f"read between capitals, so a reading taken off another "
                    f"glyph -- a slash two below the baseline -- comes out "
                    f"short and says nothing. `_capital_band` has to ask "
                    f"the widget, not measure the string.")
    finally:
        root.destroy()
    return failures
