#!/usr/bin/env python3
"""Render the whole face to preview.png, and check the fits that can break.

The emulator is the truth, but it is slow to reach for while nudging a layout.
This draws the same thing from the same constants and, more usefully, measures
the places where the layout can silently overflow:

  * the time against its band. It has the full screen width now that it sits
    off the flower rather than inside the tile's seed pod, so the binding
    constraint is the band's height, not its width.
  * the time against the status icons, which share the top row with it.
  * the date against what the info row leaves it once the weather has taken the
    right-hand end.
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
TIME_SIZE = 38
TIME_TOP = 0
TIME_HEIGHT = 48
RULE_TOP = 48
RULE_H = 1
INFO_SIZE = 22
INFO_TOP = 52
INFO_HEIGHT = 26
ART_TOP = 82
EDGE_PAD = 6
ICON_W, ICON_H, ICON_GAP, ICON_TOP = 32, 28, 2, 50
INFO_TEMP_W = 36
BATT_W, BATT_H, BATT_RIGHT_PAD, BATT_TOP, BT_W = 21, 10, 6, 4, 12

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

    # The battery, because it is the thing the time is now closest to.
    bx = SCREEN_W - BATT_RIGHT_PAD - BATT_W - 3
    d.rectangle([bx, BATT_TOP, bx + BATT_W - 1, BATT_TOP + BATT_H - 1], outline=WHITE)
    d.rectangle([bx + BATT_W, BATT_TOP + 3, bx + BATT_W + 2, BATT_TOP + BATT_H - 4], fill=WHITE)
    d.rectangle([bx + 1, BATT_TOP + 1, bx + 1 + (BATT_W - 2) * 3 // 4, BATT_TOP + BATT_H - 2],
                fill=WHITE)

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

    # The time is centred in the top band, with bluetooth in the left corner and
    # the battery in the right. Both gaps have to stay open.
    bt_right = EDGE_PAD + BT_W
    batt_left = SCREEN_W - BATT_RIGHT_PAD - BATT_W - 3
    for s in WIDEST_TIME:
        w, _ = text_size(time_font, s)
        left, right = SCREEN_W / 2 - w / 2, SCREEN_W / 2 + w / 2
        slack = min(left - bt_right, batt_left - right)
        print("stat  %-6s %3d..%-3d between icons %d and %d  slack %+3d"
              % (s, left, right, bt_right, batt_left, slack))
        if slack < 0:
            ok = False

    # The header and the flower fill the screen exactly: the info row has to end
    # before the art starts, and the art has to end before the screen does.
    info_bottom = max(INFO_TOP + INFO_HEIGHT, ICON_TOP + ICON_H)
    print("head  time %d..%d  rule %d  info %d..%d  art at %d  slack %+3d"
          % (TIME_TOP, TIME_TOP + TIME_HEIGHT, RULE_TOP, INFO_TOP, info_bottom, ART_TOP,
             ART_TOP - info_bottom))
    if TIME_TOP + TIME_HEIGHT > RULE_TOP or info_bottom > ART_TOP:
        ok = False

    print("art   %d..%d  screen %d  slack %+3d"
          % (ART_TOP, ART_TOP + ba.ART_H, SCREEN_H, SCREEN_H - ART_TOP - ba.ART_H))
    if ART_TOP + ba.ART_H > SCREEN_H:
        ok = False

    icon_x = SCREEN_W - EDGE_PAD - INFO_TEMP_W - ICON_GAP - ICON_W
    room = icon_x - EDGE_PAD - ICON_GAP
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
