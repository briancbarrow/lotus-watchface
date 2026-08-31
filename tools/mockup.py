#!/usr/bin/env python3
"""Render the whole face to preview.png, and check the fits that can break.

The emulator is the truth, but it is slow to reach for while nudging a layout.
This draws the same thing from the same constants and, more usefully, measures
the places where the layout can silently overflow:

  * the time against its band. It has the full screen width now that it sits
    off the flower rather than inside the tile's seed pod, so the binding
    constraint is the band's height, not its width.
  * the date against what the info row leaves it once the weather and the
    battery have taken the right-hand end. This is the tight one, and the
    reason the info font is 18 rather than 22.
  * the time against the bluetooth icon, which shares the time row with it.
  * the header against the flower, which has to fit in what is left of the 228.

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
INFO_SIZE = 18
INFO_TOP = 4
INFO_HEIGHT = 24
EDGE_PAD = 6
INFO_GAP = 6
ICON_W, ICON_H, ICON_GAP, ICON_TOP = 32, 28, 2, 2
INFO_TEMP_W = 30
RULE_TOP = 32
RULE_H = 1
TIME_SIZE = 38
TIME_TOP = 34
TIME_HEIGHT = 48
ART_TOP = 82
BATT_W, BATT_H, BATT_RIGHT_PAD, BATT_TOP, BT_W = 21, 10, 6, 11, 12
BT_LEFT = EDGE_PAD
BT_TOP = TIME_TOP + (TIME_HEIGHT - 12) // 2 + 1

# The right-hand end of the info row, laid out from the battery inwards -- the
# same order src/c/lotus.c derives it in.
BATT_X = SCREEN_W - BATT_RIGHT_PAD - BATT_W - 3
TEMP_X = BATT_X - INFO_GAP - INFO_TEMP_W
ICON_X = TEMP_X - ICON_GAP - ICON_W

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
    face.paste(ba.tile(), (0, ART_TOP))
    d = ImageDraw.Draw(face)

    d.rectangle([0, RULE_TOP, SCREEN_W, RULE_TOP + RULE_H - 1], fill=WHITE)

    # The battery, because it shares the info row and sets its right-hand end.
    bx = BATT_X
    d.rectangle([bx, BATT_TOP, bx + BATT_W - 1, BATT_TOP + BATT_H - 1], outline=WHITE)
    d.rectangle([bx + BATT_W, BATT_TOP + 3, bx + BATT_W + 2, BATT_TOP + BATT_H - 4], fill=WHITE)
    d.rectangle([bx + 1, BATT_TOP + 1, bx + 1 + (BATT_W - 2) * 3 // 4, BATT_TOP + BATT_H - 2],
                fill=WHITE)

    d.text((SCREEN_W / 2, TIME_TOP + TIME_HEIGHT / 2), time_text, font=time_font,
           fill=WHITE, anchor="mm")

    d.text((EDGE_PAD, INFO_TOP + 2), date_text, font=info_font, fill=WHITE)
    d.text((TEMP_X + INFO_TEMP_W, INFO_TOP + 2), temp_text, font=info_font, fill=WHITE,
           anchor="ra")

    sheet = ba.weather_sheet()
    frame = sheet.crop((icon_index * ICON_W, 0, (icon_index + 1) * ICON_W, ICON_H))
    face.paste(frame, (ICON_X, ICON_TOP), frame)

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

    # The time is centred in its row; the bluetooth icon sits at the left end of
    # the same row while the link is down.
    bt_right = BT_LEFT + BT_W
    for s in WIDEST_TIME:
        w, _ = text_size(time_font, s)
        left = SCREEN_W / 2 - w / 2
        print("bt    %-6s starts %3d  icon ends %3d      slack %+3d"
              % (s, left, bt_right, left - bt_right))
        if left < bt_right:
            ok = False

    # The header and the flower fill the screen exactly: the info row has to end
    # before the art starts, and the art has to end before the screen does.
    info_bottom = max(INFO_TOP + INFO_HEIGHT, ICON_TOP + ICON_H)
    print("head  info %d..%d  rule %d  time %d..%d  art at %d  slack %+3d"
          % (INFO_TOP, info_bottom, RULE_TOP, TIME_TOP, TIME_TOP + TIME_HEIGHT, ART_TOP,
             ART_TOP - TIME_TOP - TIME_HEIGHT))
    if info_bottom > RULE_TOP or TIME_TOP + TIME_HEIGHT > ART_TOP:
        ok = False

    print("art   %d..%d  screen %d  slack %+3d"
          % (ART_TOP, ART_TOP + ba.ART_H, SCREEN_H, SCREEN_H - ART_TOP - ba.ART_H))
    if ART_TOP + ba.ART_H > SCREEN_H:
        ok = False

    room = ICON_X - EDGE_PAD - INFO_GAP
    w, _ = text_size(info_font, WIDEST_DATE)
    print("date  %-11s %3d  in row   %3d  slack %+3d" % (WIDEST_DATE, w, room, room - w))
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
