#!/usr/bin/env python3
"""Regenerate the watchface bitmaps from the show's White Lotus tile.

The source (tools/source/white_lotus_tile.png) is the tile icon from the Avatar
Wiki, which is the tile as the series draws it: eight heart-shaped petals with a
deep notch at the outer tip, sitting on a scalloped pale backing, around a seed
pod of small dots. It is flat vector-style art in exactly three colours plus a
transparent surround.

That art is traced rather than approximated. An earlier version of this file
generated the flower parametrically -- rings of petals from a width profile --
and it could be made to look like *a* lotus but never like *the* tile: the real
one has eight lobed petals and a dotted seed pod, and no amount of tuning
exponents converges on that. Three flat colours downscale cleanly, so tracing
costs nothing in quality and is exact.

The recolour happens at full resolution, before the downscale, so the Lanczos
filter blends between the final tones rather than between the source's browns.
Every channel is then snapped to Pebble's 64-colour palette (channels in
{0, 85, 170, 255}); four levels per channel is enough for the downsampled edge
pixels to read as antialiasing rather than as jaggies, so the resource compiler
is left with nothing to dither.

Geometry here is mirrored by the LAYOUT block in src/c/lotus.c. The one that has
to agree is ART_H, where the tile bitmap stops and the time band begins.

Usage: python3 tools/build_assets.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source", "white_lotus_tile.png")
OUT = os.path.join(ROOT, "resources", "images")

# Pebble 64-colour palette entries, by their SDK names.
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)  # GColorWhite
GRAY = (170, 170, 170)  # GColorLightGray

# The source's three flat colours, and what each becomes. The show's tile is
# wood: dark brown ground, cream backing, terracotta petals. Black and white
# keeps that three-tone structure -- the petals stay a step darker than the
# backing they sit on, which is what separates them from each other.
SRC_GROUND = (110, 71, 29)
SRC_BACKING = (242, 209, 98)
SRC_PETAL = (213, 146, 83)
RECOLOUR = {
    SRC_GROUND: BLACK,
    SRC_BACKING: WHITE,
    SRC_PETAL: GRAY,
}

# Emery is 200x228. The tile bitmap covers the top of the screen; src/c/lotus.c
# draws the time band and the info strip below it.
ART_W, ART_H = 200, 146

# The art is scaled to the *flower*, not to the tile's disc. On the wooden tile
# the flower sits inside a wide brown ground, which would cost about 30px of an
# already short screen -- and once that ground is recoloured black it is the same
# black as the window behind it, so it is 30px that cannot be seen. Scaling to
# the flower and letting the disc run off the top and bottom of the bitmap spends
# those pixels on the part of the tile there is any point drawing.
#
# What this gives up is the tile's edge: there is no rim to see, so the face
# reads as the emblem on black rather than as a tile held up to the camera.
FLOWER_D = 142
FLOWER_CX, FLOWER_CY = 100, 73

# The weather icons are drawn straight in the strip's accent colour, so the
# watchface can blit them without a tinting pass. FRAME_W must stay a multiple
# of 8; see weather_sheet().
ICON_FG = WHITE
FRAME_W, FRAME_H = 32, 28


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


# A pixel whose channels span less than this is grey rather than any of the
# three wood tones. The source is drawn with a soft near-white halo just outside
# the disc, and those pixels are much closer to the cream backing than to the
# brown ground in plain RGB distance -- so without this test the halo classifies
# as flower, and the measured flower bounding box comes back as the whole canvas.
# The three real tones span 81, 130 and 144; the halo spans 9 to 60.
MIN_CHROMA = 70


def classify(colour):
    """Which of the source's three flat tones this pixel is, or None.

    None means it belongs to neither the flower nor the tile: the halo around the
    disc, and anything else too grey to be wood. Everything else goes to the
    nearest tone in plain RGB distance -- the art is flat, but it is stored as a
    PNG whose edges carry a few hundred in-between pixels, and folding those back
    onto the three tones before the downscale means the only antialiasing in the
    result is the one this script introduces.
    """
    r, g, b = colour
    if max(colour) - min(colour) < MIN_CHROMA:
        return None
    return min(RECOLOUR, key=lambda c: (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2)


def source_tones():
    """The source's pixels as (classified tone or None), and its size."""
    src = Image.open(SRC).convert("RGBA")
    px = src.load()
    cache = {}
    tones = []
    for y in range(src.size[1]):
        row = []
        for x in range(src.size[0]):
            r, g, b, a = px[x, y]
            if a < 128:
                row.append(None)  # outside the disc
                continue
            key = (r, g, b)
            if key not in cache:
                cache[key] = classify(key)
            row.append(cache[key])
        tones.append(row)
    return tones, src.size


def recoloured_source():
    """The source art, flattened onto black and mapped to the final tones."""
    tones, (w, h) = source_tones()
    out = Image.new("RGB", (w, h), BLACK)
    out_px = out.load()
    for y in range(h):
        row = tones[y]
        for x in range(w):
            tone = row[x]
            if tone is not None:
                out_px[x, y] = RECOLOUR[tone]
    return out


def flower_bbox():
    """The flower's bounding box in the source, in source pixels.

    Everything inside the disc that is not the brown ground: the pale backing
    plus the petals. FLOWER_D is measured against this rather than against the
    disc, so it has to be measured rather than assumed -- the flower is not
    centred in the source canvas and does not fill a predictable fraction of it.
    """
    tones, (w, h) = source_tones()
    mask = Image.new("L", (w, h), 0)
    mask_px = mask.load()
    for y in range(h):
        row = tones[y]
        for x in range(w):
            if row[x] is not None and row[x] != SRC_GROUND:
                mask_px[x, y] = 255
    return mask.getbbox()


def snap(img):
    """Round every channel to the nearest of {0, 85, 170, 255}."""
    table = bytes(round(v / 85.0) * 85 for v in range(256)) * len(img.getbands())
    return img.point(table)


def tile():
    """The traced flower, scaled to FLOWER_D and placed on black."""
    x0, y0, x1, y1 = flower_bbox()
    scale = FLOWER_D / float(max(x1 - x0, y1 - y0))

    src = recoloured_source()
    w, h = int(round(src.width * scale)), int(round(src.height * scale))
    scaled = src.resize((w, h), Image.LANCZOS)

    # Where the flower's centre landed in the scaled image, so the paste can put
    # it on (FLOWER_CX, FLOWER_CY). The disc around it runs off the top and
    # bottom of the bitmap, which is black either way.
    fcx, fcy = (x0 + x1) / 2.0 * scale, (y0 + y1) / 2.0 * scale

    art = Image.new("RGB", (ART_W, ART_H), BLACK)
    art.paste(scaled, (FLOWER_CX - int(round(fcx)), FLOWER_CY - int(round(fcy))))
    return snap(art)


# ---------------------------------------------------------------------------
# Other assets
# ---------------------------------------------------------------------------


def weather_sheet():
    """Draw the weather icon strip on a transparent ground.

    Frame order matches WeatherIcon in src/c/lotus.c.

    The frames are FRAME_W wide, not the 26px the drawings need. Two colours
    plus transparency compile to a 1-bit palettised bitmap, and
    gbitmap_create_as_sub_bitmap() rounds a sub-rect's x down to a byte
    boundary on sub-8-bit formats -- so a frame width that is not a multiple of
    8 would slice the wrong pixels out of the strip.
    """
    n = 8
    art = 26  # what the drawings below are sized for
    pad = (FRAME_W - art) // 2
    sheet = Image.new("RGBA", (n * FRAME_W, FRAME_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(sheet)
    W = ICON_FG + (255,)

    def sun(ox, cx, cy, r, rays=True):
        d.ellipse([ox + cx - r, cy - r, ox + cx + r, cy + r], fill=W)
        if not rays:
            return
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            x0, y0 = cx + dx * (r + 2), cy + dy * (r + 2)
            x1, y1 = cx + dx * (r + 5), cy + dy * (r + 5)
            d.line([ox + x0, y0, ox + x1, y1], fill=W, width=2)

    def cloud(ox, y=15, scale=1.0):
        # Three overlapping discs on a slab, the usual cloud silhouette.
        r = 6 * scale
        d.ellipse([ox + 4, y - r, ox + 4 + 2 * r, y + r], fill=W)
        d.ellipse([ox + 9, y - r - 4, ox + 9 + 2 * r + 2, y + r - 2], fill=W)
        d.ellipse([ox + 13, y - r + 1, ox + 13 + 2 * r, y + r + 1], fill=W)
        d.rectangle([ox + 5, y, ox + 21, y + r], fill=W)

    def drops(ox, glyphs="rain"):
        for i in range(3):
            x = ox + 7 + i * 5
            if glyphs == "rain":
                d.line([x, 21, x - 2, 25], fill=W, width=2)
            else:  # snow
                d.ellipse([x - 1, 21, x + 1, 23], fill=W)

    for i in range(n):
        ox = i * FRAME_W + pad
        if i == 0:  # clear day
            sun(ox, 13, 13, 6)
        elif i == 1:  # few clouds
            sun(ox, 9, 9, 5)
            cloud(ox, y=17, scale=0.85)
        elif i == 2:  # cloudy
            cloud(ox, y=14)
        elif i == 3:  # fog
            cloud(ox, y=11)
            for j, y in enumerate((19, 23)):
                d.line([ox + 4 + j * 2, y, ox + 22 - j * 2, y], fill=W, width=2)
        elif i == 4:  # rain
            cloud(ox, y=11)
            drops(ox, "rain")
        elif i == 5:  # snow
            cloud(ox, y=11)
            drops(ox, "snow")
        elif i == 6:  # thunderstorm
            cloud(ox, y=11)
            d.polygon(
                [ox + 14, 18, ox + 9, 26, ox + 12, 26, ox + 9, 26, ox + 16, 19, ox + 13, 19],
                fill=W,
            )
            d.line([ox + 14, 18, ox + 10, 25], fill=W, width=3)
        else:  # 7: unknown / no data
            d.ellipse([ox + 5, 5, ox + 21, 21], outline=W, width=2)
            d.line([ox + 9, 9, ox + 17, 17], fill=W, width=2)
    return sheet


def menu_icon(size=25):
    """The flower's silhouette, white on transparent.

    The petals and the pod's dots are lost at menu size, so the icon is
    everything that is not ground -- the backing and the petals flattened into
    one shape, which keeps the eight-lobed outline that identifies the tile.
    """
    tones, (w, h) = source_tones()
    mask = Image.new("L", (w, h), 0)
    mask_px = mask.load()
    for y in range(h):
        row = tones[y]
        for x in range(w):
            if row[x] is not None and row[x] != SRC_GROUND:
                mask_px[x, y] = 255

    mask = mask.crop(flower_bbox())
    mask = mask.resize((size, size), Image.LANCZOS).point(lambda v: 255 if v > 110 else 0)
    icon = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    icon.putalpha(mask)
    return icon


def main():
    os.makedirs(OUT, exist_ok=True)
    print("source flower bbox", flower_bbox())

    art = tile()
    art.save(os.path.join(OUT, "lotus_emery.png"))
    print("wrote lotus_emery.png", art.size, len(art.getcolors(4096) or []), "colours")

    sheet = weather_sheet()
    sheet.save(os.path.join(OUT, "weather_icons.png"))
    print("wrote weather_icons.png", sheet.size)

    icon = menu_icon()
    icon.save(os.path.join(OUT, "menu_icon.png"))
    print("wrote menu_icon.png", icon.size)


if __name__ == "__main__":
    main()
