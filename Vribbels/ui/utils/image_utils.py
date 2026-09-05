"""Image utility functions for UI components.

The growth-stone assets are 144x144 RGBA, all fifteen of them, and are
drawn smaller than that. The difference costs one resample as each icon
is built, which is the price of the Materials tab fitting three columns
of three inside a window the other tabs already size.

**A pale edge around one of these icons is the WIDGET's, not the
asset's.** Every one of them has a transparent outer ring -- no
near-white pixel within four of any border. What draws such an edge is
`tk.Label`, which defaults to `borderwidth=2` and `padx`/`pady` of 1,
and an RGBA image composited against whatever is behind it. Both are
answered here and at the call site: the icon is flattened onto the
panel colour before Tk sees it, and the label carries no border.
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

# The face a corner caption is drawn in. Segoe UI Bold, so a caption
# over an icon reads as the same voice as the row names beside it --
# which Tk names by family and PIL by file. The caller states the pixel
# size, Tk's point size not being one this module can convert.
CORNER_FONT_FILE = "segoeuib.ttf"


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


def _badged(draw, text, at, font, size, corner):
    """Draw `text` in a dark box, anchored at one corner of the icon.

    `at` is (x, y) for a top-left anchor; `corner` says which corner
    the pair is pushed into, which is what turns the same measurement
    into a bottom-right badge or a top-left caption.

    The box is measured AT the text's position rather than at the
    origin: a glyph's bounding box is not the same shape wherever it is
    drawn, and boxing the origin's measurements around the drawn text
    leaves the badge off by the difference.
    """
    placed = draw.textbbox(at, text, font=font)
    pad = max(1, round(size[0] * BADGE_PADDING_RATIO))
    draw.rectangle([placed[0] - pad, placed[1] - pad,
                    placed[2] + pad, placed[3] + pad], fill=(0, 0, 0, 200))
    draw.text(at, text, fill="white", font=font)


def create_icon_with_quantity(icon_path: str, quantity: int,
                              size=ICON_SIZE, background=None,
                              plate_path=None, corner_text="",
                              corner_font_px=0):
    """An icon with its owned quantity in the bottom-right corner.

    Args:
        icon_path: path to the icon image file, or "" for an item whose
            art is not in the repo yet -- its plate is drawn alone, and
            the quantity still lands on it.
        quantity: the number to draw over it.
        size: target size. `ICON_NATIVE_SIZE` is the only value that
            does not resample.
        background: a colour to flatten the icon onto, so nothing is
            left for Tk to composite. None keeps the alpha channel.
        plate_path: the rarity plate to draw the icon on, or None.
        corner_text: words for the TOP-LEFT corner, where the quantity
            takes the bottom-right. "" draws none.
        corner_font_px: pixel size for those words. Passed in rather
            than derived, so the caller can match a Tk font this module
            cannot see.

    Returns:
        A PhotoImage ready for a Label, or None if the file could not
        be read.
    """
    try:
        if icon_path:
            img = Image.open(icon_path).convert("RGBA")
            if img.size != tuple(size):
                img = img.resize(tuple(size), Image.Resampling.LANCZOS)
        else:
            img = Image.new("RGBA", tuple(size), (0, 0, 0, 0))
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
        _badged(draw, qty_text,
                (size[0] - (bbox[2] - bbox[0]) - margin,
                 size[1] - (bbox[3] - bbox[1]) - margin * 2),
                font, size, "se")

        if corner_text:
            try:
                caption = ImageFont.truetype(CORNER_FONT_FILE,
                                             max(8, corner_font_px))
            except OSError:
                caption = font
            _badged(draw, corner_text, (margin, margin), caption, size, "nw")
        return ImageTk.PhotoImage(_flattened(img, background))
    except Exception as e:
        print(f"Error creating icon: {e}")
        return None


def create_plate_icon(plate_path, size=ICON_SIZE, background=None):
    """A rarity plate with nothing on it, at an icon's size.

    For a RESERVED tile: it holds the space and the shape a real item
    would take, drawn from the same plate asset the real icons sit on
    rather than from a rectangle of this module's own -- so a tile and
    an icon are one thing in two states rather than two drawings that
    have to be kept looking alike.

    That also puts its outer pixels where an icon's are. Both are
    transparent out to the same margin, so a gap either side of a tile
    measures the same as a gap either side of an icon.
    """
    try:
        blank = Image.new("RGBA", tuple(size), (0, 0, 0, 0))
        return ImageTk.PhotoImage(
            _flattened(_plated(blank, plate_path, tuple(size)), background))
    except Exception as e:
        print(f"Error creating plate icon: {e}")
        return None
