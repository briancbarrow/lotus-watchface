#!/usr/bin/env python3
"""Render the whole face to preview.png, and check the fits that can break.

The emulator is the truth, but it is slow to reach for while nudging a layout.
This draws the same thing from the same constants and, more usefully, measures
the places where the layout can silently overflow:

  * the time against its band. It has the full screen width now that it sits
    below the flower rather than inside the tile's seed pod, so the binding
    constraint is the band's height, not its width.
  * the date against what the strip leaves it once the weather has taken the
    right-hand end.

Each is reported with its slack, and the script exits non-zero if any has run
out -- so this is worth running after any change to a font size, to ART_H, or to
INFO_TEMP_W.

Usage: python3 tools/mockup.py [out.png]
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

import build_assets as ba

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONTS = os.path.join(ROOT, "resources", "fonts")

# Mirrors the LAYOUT block in src/c/lotus.c.
SCREEN_W, SCREEN_H = 200, 228
TIME_SIZE = 38
TIME_TOP = ba.ART_H
TIME_HEIGHT = 48
INFO_SIZE = 22
PANEL_TOP = 196
PANEL_RULE = 1
INFO_TOP = 200
EDGE_PAD = 6
ICON_W, ICON_H, ICON_GAP, ICON_TOP = 32, 28, 2, 198
INFO_TEMP_W = 36

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# What the clock can actually produce, at its widest in each format.
WIDEST_TIME = ("23:58", "12:48")
# %a %b %-d, uppercased. September is the long month name; 30 is two digits.
WIDEST_DATE = "WED SEPT 30"


def text_size(font, s):
    x0, y0, x1, y1 = font.getbbox(s)
    return x1 - x0, y1 - y0


def draw_face(time_text, date_text, temp_text, icon_index):
    time_font = ImageFont.truetype(os.path.join(FONTS, "time.ttf"), TIME_SIZE)
    info_font = ImageFont.truetype(os.path.join(FONTS, "info.ttf"), INFO_SIZE)

    face = Image.new("RGB", (SCREEN_W, SCREEN_H), BLACK)
    face.paste(ba.tile(), (0, 0))
    d = ImageDraw.Draw(face)

    d.rectangle([0, PANEL_TOP, SCREEN_W, PANEL_TOP + PANEL_RULE - 1], fill=WHITE)

    d.text((SCREEN_W / 2, TIME_TOP + TIME_HEIGHT / 2), time_text, font=time_font,
           fill=WHITE, anchor="mm")

    icon_x = SCREEN_W - EDGE_PAD - INFO_TEMP_W - ICON_GAP - ICON_W
    d.text((EDGE_PAD, INFO_TOP + 2), date_text, font=info_font, fill=WHITE)
    d.text((SCREEN_W - EDGE_PAD, INFO_TOP + 2), temp_text, font=info_font, fill=WHITE, anchor="ra")

    sheet = ba.weather_sheet()
    frame = sheet.crop((icon_index * ICON_W, 0, (icon_index + 1) * ICON_W, ICON_H))
    face.paste(frame, (icon_x, ICON_TOP), frame)

    return face


def check():
    """Measure the two fits. Returns True if both still have room."""
    ok = True

    time_font = ImageFont.truetype(os.path.join(FONTS, "time.ttf"), TIME_SIZE)
    info_font = ImageFont.truetype(os.path.join(FONTS, "info.ttf"), INFO_SIZE)

    for s in WIDEST_TIME:
        w, h = text_size(time_font, s)
        print(
            "time  %-6s %3dx%-3d in band %dx%d  slack %+3d wide %+3d tall"
            % (s, w, h, SCREEN_W, TIME_HEIGHT, SCREEN_W - w, TIME_HEIGHT - h)
        )
        if w > SCREEN_W or h > TIME_HEIGHT:
            ok = False

    # The band has to end before the strip does, or the time overlaps the date.
    print("band  %d..%d  strip at %d  slack %+3d" % (TIME_TOP, TIME_TOP + TIME_HEIGHT,
                                                     PANEL_TOP, PANEL_TOP - TIME_TOP - TIME_HEIGHT))
    if TIME_TOP + TIME_HEIGHT > PANEL_TOP:
        ok = False

    icon_x = SCREEN_W - EDGE_PAD - INFO_TEMP_W - ICON_GAP - ICON_W
    room = icon_x - EDGE_PAD - ICON_GAP
    w, _ = text_size(info_font, WIDEST_DATE)
    print("date  %-11s %3d  in strip %3d  slack %+3d" % (WIDEST_DATE, w, room, room - w))
    if w > room:
        ok = False

    w, _ = text_size(info_font, "100°")
    print("temp  %-11s %3d  in %3d       slack %+3d" % ("100°", w, INFO_TEMP_W, INFO_TEMP_W - w))
    if w > INFO_TEMP_W:
        ok = False

    return ok


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "preview.png")
    ok = check()

    face = draw_face("10:35", "SAT AUG 16", "72°", ba.__dict__.get("PREVIEW_ICON", 1))
    face.save(out)
    face.resize((SCREEN_W * 2, SCREEN_H * 2), Image.NEAREST).save(
        out.replace(".png", "_2x.png")
    )
    print("wrote", out)

    if not ok:
        print("LAYOUT DOES NOT FIT -- see the negative slack above")
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main())
