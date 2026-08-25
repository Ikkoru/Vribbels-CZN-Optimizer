"""The widths every button in the app is sized from.

**`width` on a ttk.Button is CHARACTERS, not pixels.** Tk multiplies it
by the font's average character width and the style adds its padding, so
a pixel target only lands exactly on some values. At Segoe UI 9 the
relation is:

    inside = 6 * width + 12          edge-to-edge = inside + 4

measured from two buttons twelve characters apart, which is what
separates the per-character step from the fixed padding. A target that
falls between steps rounds DOWN, so a button never grows past what was
asked for.

Sharing a constant is what makes a size a decision rather than an
accident: seven different widths were in the code, none of them agreeing
with another for any stated reason. Splitting one back out later is a
one-line change at the call site -- which is the point of naming them by
SIZE rather than by the panel that happens to use them.
"""

# 60px asked, 60 given.
BUTTON_W_TINY = 8

# 80px asked, 78 given. The Optimizer's Start/Stop were already this
# size with no width set at all; stating it is what lets anything else
# match them.
BUTTON_W_SMALL = 11

# 100px asked, 96 given.
BUTTON_W_MEDIUM = 14

# 140px asked, 138 given.
BUTTON_W_LARGE = 21


def inside_px(width: int) -> int:
    """The rendered inside width, in pixels, of a button `width` chars
    wide at Segoe UI 9. For choosing a constant, not for laying out --
    nothing should predict a rendered distance from a lever."""
    return 6 * width + 12
