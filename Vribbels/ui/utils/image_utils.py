"""Image utility functions for UI components.

The growth-stone assets are 144x144 RGBA, all fifteen of them, and are
drawn at that size: a resize to anything else costs a resample for no
gain, and it is what put the shown resolution a step off the stored
one.

**The white edge these icons used to show is not in the assets.** Every
one of them has a transparent outer ring -- no near-white pixel within
four of any border -- so what showed was the widget's own: `tk.Label`
defaults to `borderwidth=2` and `padx`/`pady` of 1, and an RGBA image
composites against whatever is behind it. Both are answered here and at
the call site: the icon is flattened onto the panel colour before Tk
sees it, and the label carries no border of its own.
"""

from PIL import Image, ImageDraw, ImageFont, ImageTk

# The assets' own resolution. Drawing at anything else resamples.
ICON_SIZE = (144, 144)

# The quantity badge, in the bottom-right corner.
BADGE_FONT_PX = 24
BADGE_MARGIN = 8
BADGE_PADDING = 4


def _flattened(img, background):
    """`img` composited onto an opaque `background`, or as-is without one.

    An RGBA photo image leaves Tk to composite it, and what it
    composites against is not always the widget's background -- which
    is where a pale rim around a dark icon comes from. Doing it here
    with a stated colour leaves nothing to interpret.
    """
    if background is None:
        return img
    flat = Image.new("RGBA", img.size, background)
    flat.alpha_composite(img)
    return flat.convert("RGB")


def create_icon_with_quantity(icon_path: str, quantity: int,
                              size=ICON_SIZE, background=None):
    """An icon with its owned quantity in the bottom-right corner.

    Args:
        icon_path: path to the icon image file.
        quantity: the number to draw over it.
        size: target size. Defaults to the assets' own, which is the
            only value that does not resample.
        background: a colour to flatten the icon onto, so nothing is
            left for Tk to composite. None keeps the alpha channel.

    Returns:
        A PhotoImage ready for a Label, or None if the file could not
        be read.
    """
    try:
        img = Image.open(icon_path).convert("RGBA")
        if img.size != tuple(size):
            img = img.resize(tuple(size), Image.Resampling.LANCZOS)

        draw = ImageDraw.Draw(img)
        qty_text = str(quantity)
        try:
            font = ImageFont.truetype("arial.ttf", BADGE_FONT_PX)
        except OSError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), qty_text, font=font)
        text_x = size[0] - (bbox[2] - bbox[0]) - BADGE_MARGIN
        text_y = size[1] - (bbox[3] - bbox[1]) - BADGE_MARGIN * 2

        # The box is measured AT the text's position rather than at the
        # origin: a glyph's bounding box is not the same shape wherever
        # it is drawn, and boxing the origin's measurements around the
        # drawn text leaves the badge off by the difference.
        placed = draw.textbbox((text_x, text_y), qty_text, font=font)
        draw.rectangle(
            [placed[0] - BADGE_PADDING, placed[1] - BADGE_PADDING,
             placed[2] + BADGE_PADDING, placed[3] + BADGE_PADDING],
            fill=(0, 0, 0, 200),
        )
        draw.text((text_x, text_y), qty_text, fill="white", font=font)
        return ImageTk.PhotoImage(_flattened(img, background))
    except Exception as e:
        print(f"Error creating icon: {e}")
        return None


def create_placeholder_icon(size=ICON_SIZE, background=None, outline=None):
    """A blank tile the size and shape of a real icon.

    For a column of the Materials tab that has nothing to show yet: it
    holds the layout at the size the real icons take, and reads as an
    empty slot rather than as an icon that failed to load.
    """
    try:
        img = Image.new("RGBA", tuple(size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [0, 0, size[0] - 1, size[1] - 1], radius=12,
            fill=background, outline=outline, width=1,
        )
        return ImageTk.PhotoImage(_flattened(img, background))
    except Exception as e:
        print(f"Error creating placeholder icon: {e}")
        return None
