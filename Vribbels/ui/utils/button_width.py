"""The widths every button in the app is sized from.

**`width` on a ttk.Button is CHARACTERS, not pixels.** Tk multiplies it
by the font's average character width and the style adds its padding, so
a pixel target only lands exactly on some values. At Segoe UI 9 the
relation is:

    inside = 6 * width + 2 * padx    edge-to-edge = inside + 4

measured from two buttons twelve characters apart, which is what
separates the per-character step from the constant. A target that falls
between steps rounds DOWN, so a button never grows past what was asked
for.

**The constant term IS the style's padding**, both sides of it, and
`BUTTON_PAD_X` below is where that padding is set -- `configure_styles`
imports it rather than holding its own copy, so a button's size and the
number this module predicts cannot disagree.

The padding renders ONE MORE than it says, which is why the constant is
`2 * (BUTTON_PAD_X + 1)` rather than twice the setting.

Sharing a constant is what makes a size a decision rather than an
accident: seven different widths were in the code, none of them agreeing
with another for any stated reason. Splitting one back out later is a
one-line change at the call site -- which is the point of naming them by
SIZE rather than by the panel that happens to use them.
"""

# 58px inside, 62 edge-to-edge
BUTTON_W_TINY = 9

# 76px inside, 80 edge-to-edge
BUTTON_W_SMALL = 12

# 94px inside, 98 edge-to-edge
BUTTON_W_MEDIUM = 15

# 130px inside, 134 edge-to-edge
BUTTON_W_LARGE = 21


# spacing: unique -- a button's own internal inset -- button, text ↔
# TButton's horizontal padding. Here rather than in `configure_styles`
# because it sets a button's SIZE, not just where its text sits, so the
# widths above are only true against this number.
BUTTON_PAD_X = 1


def inside_px(width: int) -> int:
    """The rendered inside width, in pixels, of a button `width` chars
    wide at Segoe UI 9. For choosing a constant, not for laying out --
    nothing should predict a rendered distance from a lever."""
    return 6 * width + 2 * (BUTTON_PAD_X + 1)
