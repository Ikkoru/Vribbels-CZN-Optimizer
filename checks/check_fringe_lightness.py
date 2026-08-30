"""The audit's ink test, against what the eye actually reported.

`is_background` decides where a measured gap ends. Antialiasing puts a
blended pixel at both ends of every string, and a gap measured to a pixel
nobody can see reads as misaligned when it looks fine -- so the test is
not "is this painted" but "would the eye put the edge here".

That is a perceptual claim, and it was settled perceptually: a survey
rendered every character the app can display, each in its own checkbox
against a fixed reference edge, and the maintainer graded glyph edges at
life size by whether REMOVING them was noticeable. The pixels below are
that grading. The columns whose removal was invisible topped out at
L* 6.5; the faintest whose removal was visible sat at 18.9. Nothing fell
in between, which is why the threshold is not delicate.

**This is the only record of that calibration.** The survey lived in
`_tmp/` and the screenshots it read are gone, so nothing else can
re-derive these numbers without running the whole exercise again.

Three things it holds:

1. Every pixel the eye could not find is treated as empty space.
2. Every pixel it could find is treated as ink.
3. The shades a widget is PAINTED in stay ink whatever their lightness.
   `bg_light` is a smaller lightness step from `bg` than the faintest
   glyph edge is -- it is legible in the app because it covers an area,
   not because any one pixel stands out. A per-pixel test alone would
   look straight through every control, which is the failure
   `ui/spacing_audit.py` warns about; what prevents it is that the
   lightness test is reached only by a pixel matching no palette colour.
"""

from ._harness import add_source_to_path

NAME = "fringe lightness matches the eye"

# (r, g, b) -> was removing this column noticeable?
# Segoe UI 9, palette `fg` on `bg`. Both edges of each glyph.
GRADED = [
    # Removal not noticeable, or barely.
    ((31, 31, 120), False, "'%' and 'H' left edge"),
    ((31, 31, 85), False, "'#' left edge"),
    ((65, 31, 46), False, "'%' and '#' right edge"),
    # Removal noticeable.
    ((31, 67, 153), True, "'d' 'e' '$' 'c' 'o' left edge"),
    ((125, 67, 46), True, "'H' and 'd' right edge"),
    ((152, 99, 46), True, "'c' '$' 'o' right edge"),
    ((31, 99, 184), True, "'6' left edge"),
    ((65, 130, 214), True, "'0' '9' '8' left edge"),
    ((179, 130, 85), True, "'9' right edge"),
    ((205, 159, 120), True, "'0' '6' '8' 'e' right edge"),
]


def run():
    failures = []
    add_source_to_path()

    from ui import spacing_audit as sa
    from czn_optimizer_gui import COLORS
    from game_data.characters import ATTRIBUTE_COLORS
    from game_data.constants import RARITY_BG_COLORS, RARITY_COLORS

    def hexes(value):
        return tuple(int(value.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    # Assembled the way Capture.of_window assembles it. Widening that is
    # what keeps the rarity row fills out of the lightness test, so a
    # narrower stand-in here would pass while the real thing broke.
    palette = {k: hexes(v) for k, v in COLORS.items()
               if isinstance(v, str) and v.startswith("#")}
    for source, prefix in ((RARITY_COLORS, "rarity fg"),
                           (RARITY_BG_COLORS, "rarity bg"),
                           (ATTRIBUTE_COLORS, "element")):
        for key, value in source.items():
            palette[f"{prefix} {key}"] = hexes(value)
    bg = palette["bg"]

    class OnePixel:
        """The smallest thing Capture can be built over."""

        def __init__(self, rgb):
            self.rgb = rgb

        def load(self):
            return {(0, 0): self.rgb}

    def verdict(rgb):
        cap = sa.Capture(OnePixel(rgb), (0, 0), [bg, palette["bg_strip"]],
                         palette)
        return cap.is_background(0, 0)

    for rgb, visible, where in GRADED:
        got_background = verdict(rgb)
        if visible and got_background:
            failures.append(
                f"{rgb} ({where}) is treated as empty space, but removing "
                f"it from the glyph was visible at life size. The audit "
                f"would measure past ink the eye can see, reporting a "
                f"misalignment as aligned. FRINGE_LIGHTNESS is too high "
                f"(L* {sa.lightness(rgb) - sa.lightness(bg):+.2f} from bg)."
            )
        if not visible and not got_background:
            failures.append(
                f"{rgb} ({where}) is treated as ink, but removing it from "
                f"the glyph was not noticeable at life size. The audit "
                f"would measure to a pixel nobody can see, reporting a "
                f"gap that looks right as wrong. FRINGE_LIGHTNESS is too "
                f"low (L* {sa.lightness(rgb) - sa.lightness(bg):+.2f} "
                f"from bg)."
            )

    # 3. The painted shades, whatever their lightness.
    for name in ("bg_light", "bg_lighter", "select", "fg_dim"):
        if verdict(palette[name]):
            failures.append(
                f"a solid {name} pixel {palette[name]} is treated as empty "
                f"space. That shade FILLS controls and draws borders, so "
                f"every scan would run straight through them and measure "
                f"to their contents instead of their edges. Solid palette "
                f"shades must stay ink by identity -- the lightness test "
                f"is for blends only."
            )

    # The same, for the shades COLORS does not carry. The three TINTED
    # rarity row fills sit within L* 6 of the window background, so they
    # depend entirely on being in the palette -- nothing about their own
    # lightness would save them. Rarity 1 is skipped because it IS the
    # window background: a Normal row carries no tint, so reading it as
    # empty space is right.
    for rarity, value in sorted(RARITY_BG_COLORS.items()):
        rgb = hexes(value)
        if rgb == bg:
            continue
        if verdict(rgb):
            delta = sa.lightness(rgb) - sa.lightness(bg)
            failures.append(
                f"the rarity {rarity} row fill {rgb} is treated as empty "
                f"space (L* {delta:+.2f} from bg). It fills rows in the "
                f"Memory Fragments tree, so every scan there would read "
                f"through the row to whatever is behind it. Capture."
                f"of_window has to put these tables in the palette; "
                f"COLORS does not carry them."
            )

    # The seam the exact-match rule exists for: a blend of two background
    # shades is still empty space.
    seam = tuple((a + b) // 2 for a, b in zip(bg, palette["bg_strip"]))
    if not verdict(seam):
        failures.append(
            f"the tab-strip seam colour {seam} is treated as ink. It is a "
            f"blend of bg and bg_strip, and counting it made every tab's "
            f"first element measure 0 from the tab list."
        )

    return failures
