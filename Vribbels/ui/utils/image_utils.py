"""Image utility functions for UI components.

Every icon asset is `ICON_NATIVE_SIZE` RGBA and is drawn at
`ICON_SIZE`. Keep the two equal: they differ only while the assets are
being resized, and any difference costs one LANCZOS resample per icon
as the Materials tab builds.

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
ICON_NATIVE_SIZE = (112, 113)
ICON_SIZE = (112, 113)

# The rarity plate an icon sits on, as a share of the icon's WIDTH.
# `_plate_side` reads `size[0]` and the plate assets are square, so the
# denominator is the icon's width and not its height -- against the
# height the plate would come out a pixel small.
#
# Sized from the icon rather than stated, so the pair keeps its
# proportions at whatever `ICON_SIZE` becomes.
#
# **Centring divides what is left over, and an ODD remainder cannot be
# split evenly** -- one side gets the extra pixel. Which axis that
# falls on moves with the icon's shape, so it is not a thing to write
# down. What absorbs it is the icons' own transparent border: their art
# is centred inside that the way the game centres it, so the plate
# takes the uneven split and the artwork does not.
RARITY_PLATE_RATIO = 101 / 112

# Where the rarity plates live, under the images folder.
RARITY_DIR = "bg"

# The plate's side at the native icon size. **Every overlay below is a
# share of the PLATE, not of the canvas.** The canvas is taller than it
# is wide and the plate is square, so one margin taken from the canvas
# lands at two different distances from the frame the eye reads.
PLATE_NATIVE_SIZE = round(ICON_NATIVE_SIZE[0] * RARITY_PLATE_RATIO)

# The two things drawn OVER an icon: its owned quantity in the
# bottom-right corner of the plate, and a caption in the top-left. Each
# has the same three levers, and they are separate so one can be moved
# without the other.
#
# * FONT   -- how big the words are.
# * MARGIN -- how far the BOX sits from the plate's own edges. The box
#             is the outermost paint, so this is the distance the eye
#             reads and what a gap measured to the icon stops at.
# * PAD    -- how much dark box there is around the words, the same on
#             all four sides.
#
# All of them are shares of the plate's side rather than pixel counts,
# so the pair keeps its proportions at whatever `ICON_SIZE` becomes.
# The two margins are equal, which puts the two corners symmetrically
# inside the frame; they stay separate levers so one can be moved
# alone.
BADGE_FONT_RATIO = 24 / PLATE_NATIVE_SIZE
BADGE_MARGIN_RATIO = 0 / PLATE_NATIVE_SIZE
BADGE_PADDING_RATIO = 3 / PLATE_NATIVE_SIZE

# The caption's, which the CALLER sizes the font of -- it matches a Tk
# font this module cannot see.
CORNER_MARGIN_RATIO = 0 / PLATE_NATIVE_SIZE
CORNER_PADDING_RATIO = 2 / PLATE_NATIVE_SIZE

# What a caption's box is measured against VERTICALLY, in place of the
# caption's own ink. These words are read as a row down the column, and
# a descender in one of them would give that one a taller box than the
# rest -- so the box is sized to characters that have none and a `y`
# hangs past its bottom edge.
CAPTION_BAND = "24h"

# The box behind either label, and the one-pixel border around it. The
# border is translucent, so it reads as an edge over both a dark icon
# and a bright one without being a line in its own right.
BADGE_FILL = (0, 0, 0, 200)
BADGE_BORDER = (0, 0, 0, 180)
BADGE_TEXT = (255, 255, 255, 255)

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


def _plate_side(size):
    """The side of the rarity plate drawn on a canvas of `size`."""
    return max(1, round(size[0] * RARITY_PLATE_RATIO))


def _frame_rect(size, plated):
    """The rect an overlay is placed and scaled against.

    The PLATE where one is drawn, and the whole canvas where none is:
    an item with no plate has no frame to sit inside, so its labels
    take the only edges there are.

    Returns (left, top, right, bottom) as the outermost pixels, so a
    margin of zero puts a box's edge exactly on the frame's.
    """
    if not plated:
        return 0, 0, size[0] - 1, size[1] - 1
    side = _plate_side(size)
    left = (size[0] - side) // 2
    top = (size[1] - side) // 2
    return left, top, left + side - 1, top + side - 1


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
    side = _plate_side(size)
    plate = plate.resize((side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", tuple(size), (0, 0, 0, 0))
    canvas.alpha_composite(plate, dest=((size[0] - side) // 2,
                                        (size[1] - side) // 2))
    canvas.alpha_composite(icon)
    return canvas


def _ink(font, text):
    """The tight ink rect of `text`, relative to its draw origin.

    Not `textbbox`, which starts at the layout origin and so reports a
    left edge the glyph does not reach. The mask is what gets painted,
    and its own bounding box is where the paint actually is -- which is
    what a box drawn `pad` from the words has to be measured from.

    Returns (left, top, right, bottom) with the right and bottom one
    PAST the last painted pixel, the way every PIL box reads.
    """
    mask, offset = font.getmask2(text)
    box = mask.getbbox()
    if box is None:      # nothing painted -- a space, or an empty string
        return offset[0], offset[1], offset[0], offset[1]
    return (offset[0] + box[0], offset[1] + box[1],
            offset[0] + box[2], offset[1] + box[3])


def _label_box(font, text, pad, band=None):
    """The box around `text`, relative to the text's draw origin.

    Exactly `pad` painted pixels of box on every side. Its corners are
    INCLUSIVE, which is what `ImageDraw.rectangle` takes -- so the
    right and bottom come off the ink's far edges, those being one past
    the last painted pixel.

    `band` replaces the text's own top and bottom, for a row of
    captions that has to keep one height whatever glyphs it holds.
    """
    ink = _ink(font, text)
    top, bottom = band if band else (ink[1], ink[3])
    return (ink[0] - pad, top - pad, ink[2] - 1 + pad, bottom - 1 + pad)


def _badged(img, text, origin, font, pad, band=None, fill=BADGE_TEXT):
    """Draw `text` in a bordered box, its ORIGIN at `origin`.

    On an overlay of its own and composited, not drawn straight onto
    the icon: `ImageDraw` replaces a pixel with the colour it is given
    rather than blending it, so a translucent box drawn directly would
    erase the artwork under it and a translucent border would not be
    translucent at all.

    **The border is what reaches furthest**, one pixel outside the box
    on every side -- so it, and not the artwork, is where a gap
    measured to this icon's painted edge stops.
    """
    box = _label_box(font, text, pad, band)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    placed = [origin[0] + box[0], origin[1] + box[1],
              origin[0] + box[2], origin[1] + box[3]]
    draw.rectangle([placed[0] - 1, placed[1] - 1,
                    placed[2] + 1, placed[3] + 1], fill=BADGE_BORDER)
    draw.rectangle(placed, fill=BADGE_FILL)
    draw.text(origin, text, fill=fill, font=font)
    img.alpha_composite(overlay)


def create_icon_with_quantity(icon_path: str, quantity: int,
                              size=ICON_SIZE, background=None,
                              plate_path=None, corner_text="",
                              corner_font_px=0, corner_fill=None):
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
        corner_fill: what colour to draw those words. None is white,
            which is a caption saying no more than what it says.

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

        frame = _frame_rect(tuple(size), bool(plate_path))
        span = frame[2] - frame[0] + 1
        qty_text = str(quantity)
        margin = max(0, round(span * BADGE_MARGIN_RATIO))
        pad = max(1, round(span * BADGE_PADDING_RATIO))
        try:
            font = ImageFont.truetype(
                "arial.ttf", max(8, round(span * BADGE_FONT_RATIO)))
        except OSError:
            font = ImageFont.load_default()

        # Solving for the origin the box has to be drawn from, its far
        # corner one margin inside the frame's.
        box = _label_box(font, qty_text, pad)
        _badged(img, qty_text,
                (frame[2] - margin - box[2], frame[3] - margin - box[3]),
                font, pad)

        if corner_text:
            try:
                caption = ImageFont.truetype(CORNER_FONT_FILE,
                                             max(8, corner_font_px))
            except OSError:
                caption = font
            edge = max(0, round(span * CORNER_MARGIN_RATIO))
            cpad = max(1, round(span * CORNER_PADDING_RATIO))
            band = _ink(caption, CAPTION_BAND)[1::2]
            box = _label_box(caption, corner_text, cpad, band)
            _badged(img, corner_text,
                    (frame[0] + edge - box[0], frame[1] + edge - box[1]),
                    caption, cpad, band, corner_fill or BADGE_TEXT)
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
