"""Image utility functions for UI components.

The growth-stone assets are 144x144 RGBA, all fifteen of them, and are
drawn smaller than that. The difference costs one resample as each icon
is built, which is the price of the Materials tab fitting three columns
of three inside a window the other tabs already size.

**The white edge these icons used to show is not in the assets.** Every
one of them has a transparent outer ring -- no near-white pixel within
four of any border -- so what showed was the widget's own: `tk.Label`
defaults to `borderwidth=2` and `padx`/`pady` of 1, and an RGBA image
composites against whatever is behind it. Both are answered here and at
the call site: the icon is flattened onto the panel colour before Tk
sees it, and the label carries no border of its own.
"""

from PIL import Image, ImageDraw, ImageFont, ImageTk

# What the files hold, and what is drawn. They differ, so every icon
# is resampled once -- LANCZOS, at build time, not per repaint.
ICON_NATIVE_SIZE = (114, 114)
ICON_SIZE = (114, 114)

# The quantity badge, in the bottom-right corner. Sized against the
# icon rather than stated, so the badge keeps its proportions when the
# icon does not: at the native size these are 24, 8 and 4.
BADGE_FONT_RATIO = 24 / ICON_NATIVE_SIZE[0]
BADGE_MARGIN_RATIO = 8 / ICON_NATIVE_SIZE[0]
BADGE_PADDING_RATIO = 4 / ICON_NATIVE_SIZE[0]

# How round the placeholder tile's corners are, as a share of its side.
# The stone art is drawn to about this.
PLACEHOLDER_RADIUS_RATIO = 12 / ICON_NATIVE_SIZE[0]

# The rarity plate an icon sits on, as a share of the icon's side. The
# assets are 101 against the icons' 114, and the two are drawn together
# -- so the plate is sized from the icon rather than stated, and the
# pair keeps its proportions at whatever `ICON_SIZE` becomes.
#
# 13 pixels apart at the native size, which is ODD: centring leaves one
# more pixel on one side than the other, and nothing can divide it
# evenly. The icons carry a transparent border of their own for exactly
# this reason -- their art is centred inside it the way the game centres
# it -- so the plate is what gets the uneven split, not the artwork.
RARITY_PLATE_RATIO = 101 / 114

# Where the rarity plates live, under the images folder.
RARITY_DIR = "bg"


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


def _plated(icon, plate_path, size):
    """`icon` over its rarity plate, on a canvas of `size`.

    The plate goes down first and the icon over it, so the icon's
    transparent border shows the plate through rather than covering it
    -- which is the whole point of drawing the two together.

    Returns the icon unchanged where there is no plate to draw.
    """
    if not plate_path:
        return icon
    plate = Image.open(plate_path).convert("RGBA")
    side = max(1, round(size[0] * RARITY_PLATE_RATIO))
    plate = plate.resize((side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", tuple(size), (0, 0, 0, 0))
    canvas.alpha_composite(plate, dest=((size[0] - side) // 2,
                                        (size[1] - side) // 2))
    canvas.alpha_composite(icon)
    return canvas


def create_icon_with_quantity(icon_path: str, quantity: int,
                              size=ICON_SIZE, background=None,
                              plate_path=None):
    """An icon with its owned quantity in the bottom-right corner.

    Args:
        icon_path: path to the icon image file.
        quantity: the number to draw over it.
        size: target size. `ICON_NATIVE_SIZE` is the only value that
            does not resample.
        background: a colour to flatten the icon onto, so nothing is
            left for Tk to composite. None keeps the alpha channel.
        plate_path: the rarity plate to draw the icon on, or None.

    Returns:
        A PhotoImage ready for a Label, or None if the file could not
        be read.
    """
    try:
        img = Image.open(icon_path).convert("RGBA")
        if img.size != tuple(size):
            img = img.resize(tuple(size), Image.Resampling.LANCZOS)
        img = _plated(img, plate_path, tuple(size))

        draw = ImageDraw.Draw(img)
        qty_text = str(quantity)
        margin = max(1, round(size[0] * BADGE_MARGIN_RATIO))
        try:
            font = ImageFont.truetype(
                "arial.ttf", max(8, round(size[0] * BADGE_FONT_RATIO)))
        except OSError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), qty_text, font=font)
        text_x = size[0] - (bbox[2] - bbox[0]) - margin
        text_y = size[1] - (bbox[3] - bbox[1]) - margin * 2

        # The box is measured AT the text's position rather than at the
        # origin: a glyph's bounding box is not the same shape wherever
        # it is drawn, and boxing the origin's measurements around the
        # drawn text leaves the badge off by the difference.
        placed = draw.textbbox((text_x, text_y), qty_text, font=font)
        pad = max(1, round(size[0] * BADGE_PADDING_RATIO))
        draw.rectangle(
            [placed[0] - pad, placed[1] - pad,
             placed[2] + pad, placed[3] + pad],
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
            [0, 0, size[0] - 1, size[1] - 1],
            radius=max(1, round(size[0] * PLACEHOLDER_RADIUS_RATIO)),
            fill=background, outline=outline, width=1,
        )
        return ImageTk.PhotoImage(_flattened(img, background))
    except Exception as e:
        print(f"Error creating placeholder icon: {e}")
        return None
