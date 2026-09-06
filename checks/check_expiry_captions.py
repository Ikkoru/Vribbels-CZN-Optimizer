"""The words drawn over an icon's corner, and the box behind them.

Two things here fail without raising, and both of them only on a
screen somebody happens to be looking at.

The COUNTDOWN is the first. Weekly stock is spent against a reset no
snapshot dates, so its caption is derived from the clock alone -- and a
reset computed off by a day, or one that reports a week left at the
moment it rolls over, still draws a caption that reads like any other.
The tiers are checked with it: an item whose holding is under its floor
draws nothing at all, which is not a state the eye can tell apart from
a caption that failed to appear.

The BOX is the second. It is placed by solving for the origin its text
has to be drawn from, so an error in the arithmetic moves the words
inside their own box rather than raising anything, and a box measured
from a string's own ink grows a descender's worth taller on the lines
that have one. Both are read here as pixels off a rendered icon.

No Tk and no snapshot needed.
"""

from ._harness import add_source_to_path

NAME = "expiry captions"

# A Sunday 18:00:00 UTC. Every case below is an offset from it, and
# the first thing the run does is confirm it still is one.
SUNDAY_RESET = 1789927200


def run():
    add_source_to_path()
    import weekly_reset
    from PIL import Image, ImageFont
    from ui.utils import image_utils as iu
    from ui.tabs.materials_tab import (
        MODULE_BUCKETS, MODULE_URGENT, RESERVED_ITEMS, RESET_CAPTIONS,
        RESET_ITEMS, reset_caption,
    )
    from czn_optimizer_gui import COLORS

    failures = []

    # --- the reset the captions count down to -------------------------
    from datetime import datetime, timezone
    at = datetime.fromtimestamp(SUNDAY_RESET, timezone.utc)
    if (at.weekday(), at.hour, at.minute) != (weekly_reset.RESET_WEEKDAY,
                                              weekly_reset.RESET_HOUR, 0):
        failures.append(
            f"this check's own reference instant is {at}, which is not the "
            f"reset `weekly_reset` names. Every case below is measured "
            f"from it, so fix the constant before reading anything else.")

    for offset, want in ((-3600, SUNDAY_RESET),
                         (0, SUNDAY_RESET + 7 * 86400),
                         (60, SUNDAY_RESET + 7 * 86400),
                         (-6 * 86400, SUNDAY_RESET)):
        got = weekly_reset.next_reset(SUNDAY_RESET + offset)
        if got != want:
            failures.append(
                f"{offset}s from a reset, the next one came back "
                f"{got - SUNDAY_RESET:+.0f}s from the reference and not "
                f"{want - SUNDAY_RESET:+.0f}. Standing ON a reset the week "
                f"that just began is what is left, not nothing -- an "
                f"inclusive comparison there reports zero hours and paints "
                f"every weekly item red.")

    hours = weekly_reset.hours_left(SUNDAY_RESET + 3600)
    if abs(hours - (7 * 24 - 1)) > 1e-6:
        failures.append(
            f"an hour past a reset leaves {hours:.4f} hours, not "
            f"{7 * 24 - 1}. The captions are tiers over this number, so a "
            f"wrong scale moves every one of them.")

    # --- what those hours are drawn as --------------------------------
    for left, want in ((100, ""), (72, ""), (71.5, "<3 days"),
                       (48, "<3 days"), (47.9, "<2 days"),
                       (24, "<2 days"), (23.5, "<24h!"),
                       (6.01, "<7h!"), (0.2, "<1h!")):
        words, _colour = reset_caption(left)
        if words != want:
            failures.append(
                f"{left} hours out reads {words!r}, not {want!r}. The "
                f"windows are half-open downward -- a countdown standing "
                f"exactly on a limit is still in the window above it -- "
                f"and the hours round UP, `<7h!` meaning fewer than seven "
                f"remain rather than seven still to come.")

    for limit, _words, colour in RESET_CAPTIONS:
        if colour is not None and colour not in COLORS:
            failures.append(
                f"the {limit}-hour caption asks for colour {colour!r}, "
                f"which `COLORS` does not carry. The lookup is a direct "
                f"index at draw time and raises inside a redraw.")
    for caption, colour in MODULE_URGENT.items():
        if caption not in [words for _hours, words in MODULE_BUCKETS]:
            failures.append(
                f"{caption!r} is coloured as an urgent module window but "
                f"is not one of `MODULE_BUCKETS`' captions, so nothing "
                f"ever draws it -- the colour is dead.")
        if colour not in COLORS:
            failures.append(
                f"module window {caption!r} asks for colour {colour!r}, "
                f"which `COLORS` does not carry.")
    for res_id, floor in RESET_ITEMS:
        if res_id not in RESERVED_ITEMS:
            failures.append(
                f"item {res_id} counts down to the weekly reset but is not "
                f"in the reserved column, so no icon on the tab ever shows "
                f"that caption.")
        if floor < 0:
            failures.append(
                f"item {res_id} hides its caption at or below {floor}, "
                f"which no holding can reach -- the caption would never "
                f"be suppressed.")

    # --- the box behind the words -------------------------------------
    size = iu.icon_size()
    frame = iu._frame_rect(size, True)
    span = frame[2] - frame[0] + 1
    pad = max(1, round(span * iu.BADGE_PADDING_RATIO))
    margin = max(0, round(span * iu.BADGE_MARGIN_RATIO))
    try:
        font = ImageFont.truetype(
            "arial.ttf", max(8, round(span * iu.BADGE_FONT_RATIO)))
    except OSError:
        font = None

    if font is not None:
        for text in ("1", "12", "349", "9999"):
            box = iu._label_box(font, text, pad)
            origin = (frame[2] - margin - box[2], frame[3] - margin - box[3])
            ink = iu._ink(font, text)
            sides = (origin[0] + ink[0] - (origin[0] + box[0]),
                     origin[1] + ink[1] - (origin[1] + box[1]),
                     origin[0] + box[2] - (origin[0] + ink[2] - 1),
                     origin[1] + box[3] - (origin[1] + ink[3] - 1))
            if sides != (pad, pad, pad, pad):
                failures.append(
                    f"the quantity {text!r} sits {sides} from its box's "
                    f"four edges rather than {pad} on each. A box measured "
                    f"anywhere but the text's own ink puts the digits off "
                    f"centre inside it, and nothing raises.")
            corner = (frame[2] - (origin[0] + box[2]),
                      frame[3] - (origin[1] + box[3]))
            if corner != (margin, margin):
                failures.append(
                    f"the quantity {text!r} boxes to {corner} from the "
                    f"plate's bottom-right rather than {margin} on both. "
                    f"Every overlay is placed against the PLATE and not "
                    f"the canvas, the canvas being the taller of the two "
                    f"-- a margin taken from the wrong rect lands at a "
                    f"different distance on each axis. (The 1px border "
                    f"rides outside the box, so at a margin of 0 it is "
                    f"the plate's own edge pixel.)")

    caption_font = None
    try:
        caption_font = ImageFont.truetype(iu.CORNER_FONT_FILE, 16)
    except OSError:
        pass
    if caption_font is not None:
        band = iu._ink(caption_font, iu.CAPTION_BAND)[1::2]
        heights = set()
        for words in ("<24h!", "<2 days", "3+ days", "<7h!"):
            box = iu._label_box(caption_font, words, pad, band)
            heights.add(box[3] - box[1])
        if len(heights) != 1:
            failures.append(
                f"the corner captions box to {sorted(heights)} different "
                f"heights. They are read as a column down the reserved "
                f"items, and a `y` in one of them is what makes its box "
                f"the odd one -- which is why the band comes from "
                f"`CAPTION_BAND` and not from the words themselves.")

    # And the whole of it, rendered: an icon that raises here draws
    # nothing at all on the tab.
    blank = Image.new("RGBA", size, (0, 0, 0, 0))
    scratch = blank.copy()
    if font is not None:
        try:
            iu._badged(scratch, "349", (10, 10), font, pad)
        except Exception as exc:
            failures.append(
                f"drawing a quantity badge raised {exc!r}. The overlay is "
                f"composited rather than drawn straight onto the icon, so "
                f"a mismatch in image mode fails here and the caller "
                f"reports only `Error creating icon`.")
        if scratch.getchannel("A").getbbox() is None:
            failures.append(
                "a drawn badge left the icon untouched. `ImageDraw` on an "
                "overlay that is never composited paints nothing, which "
                "looks exactly like an item with no quantity.")

    return failures
