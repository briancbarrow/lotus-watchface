#include <pebble.h>

#include <ctype.h>

// White Lotus watchface for emery (Pebble Time 2, 200x228).
//
// The whole face is one layer with a single update proc, in two blocks: a
// header carrying the time, the day, the date, the weather and the status
// icons, and the tile's flower under it as a bitmap. Everything is drawn from
// cached strings so the update proc never formats anything itself.

// ---------------------------------------------------------------------------
// LAYOUT -- keep in sync with tools/build_assets.py and tools/mockup.py
// ---------------------------------------------------------------------------
// The tile artwork is traced by tools/build_assets.py, which owns its geometry.
// Only ART_H matters here: the bitmap is that tall and gets placed at ART_TOP.
#define ART_H 146

// Every readable thing is in a header above the flower.
//
// A timeline peek slides up from the bottom of the screen and holds a band of it
// for as long as it is up. Whatever sits down there is hidden for that whole
// time, so the question is what the face can afford to lose. Not the time, and
// not the date or the weather either -- they are the reason to look at a
// watchface at all. The flower can: it is the same flower it was a second ago,
// and half of it still reads as the tile.
//
// The time is off the flower rather than on it for a separate reason. The tile's
// centre is a seed pod of small dots -- the thing that identifies it as the
// White Lotus tile at all -- so the time there would cover the one part of the
// artwork worth keeping. Off it, the time gets the full screen width instead of
// a chord across a medallion, which is why it can be this large.
#define TIME_LEFT 0
#define TIME_WIDTH 200
#define TIME_TOP 0
#define TIME_HEIGHT 48

// A hairline parts the time from the row under it. There is no fill behind
// either: the window's black is already the black the artwork's own ground is
// drawn in, so there is no seam to hide, and a slab of colour under a
// black-and-white flower would be the only loud thing on the screen.
#define RULE_TOP 48
#define RULE_H 1
#define RULE_COLOR GColorWhite

// The day, date and weather, in one row under the rule. The icon rides 2px
// higher than the text so their optical centres line up.
#define ICON_TOP 50
#define INFO_TOP 52
#define INFO_HEIGHT 26
#define EDGE_PAD 6

// The flower gets whatever the header does not, and ART_H is fixed, so this is
// forced: 82 + 146 = 228, the whole screen, with nothing spare in either
// direction. Growing the header means regenerating the art shorter.
#define ART_TOP 82
// Frame size in resources/images/weather_icons.png. ICON_W must stay a
// multiple of 8 so the sub-bitmap lands on a byte boundary.
#define ICON_W 32
#define ICON_H 28
#define ICON_GAP 2
// Width reserved for the temperature, enough for "100°". What is left of the
// row after the icon and this goes to the date, which is why the info font is
// condensed. tools/mockup.py prints both.
#define INFO_TEMP_W 36

#define BATT_W 21
#define BATT_H 10
#define BATT_RIGHT_PAD 6
#define BATT_TOP 4
#define BT_W 12

// The tile is black and white, so the whole face is.
#define INFO_COLOR GColorWhite
#define TIME_COLOR GColorWhite
#define STATUS_COLOR GColorWhite

// Icon frames in resources/images/weather_icons.png, in sheet order.
typedef enum {
  WEATHER_CLEAR = 0,
  WEATHER_FEW_CLOUDS,
  WEATHER_CLOUDY,
  WEATHER_FOG,
  WEATHER_RAIN,
  WEATHER_SNOW,
  WEATHER_THUNDER,
  WEATHER_UNKNOWN,
  WEATHER_ICON_COUNT
} WeatherIcon;

// AppMessage keys, mirrored in src/pkjs/index.js.
#define KEY_TEMP MESSAGE_KEY_TEMP
#define KEY_ICON MESSAGE_KEY_ICON
#define KEY_FETCH MESSAGE_KEY_FETCH

// Persisted so the last reading is on screen immediately after a restart,
// before the phone has had a chance to answer.
#define PERSIST_TEMP 1
#define PERSIST_ICON 2

// Ask the phone for a fresh reading this often.
#define WEATHER_INTERVAL_MIN 30

static Window *s_window;
static Layer *s_canvas;

static GBitmap *s_tile;
static GBitmap *s_weather_sheet;
static GBitmap *s_weather_icon;  // sub-bitmap of s_weather_sheet, may be NULL
static GFont s_time_font;
static GFont s_info_font;

static char s_time_text[8] = "--:--";
// Wide enough for the longest "%a %b %d" the compiler can prove, not just the
// longest one a calendar can produce -- otherwise -Wformat-truncation fires.
static char s_date_text[32] = "";
static char s_temp_text[8] = "";

static int s_weather_icon_index = WEATHER_UNKNOWN;
static bool s_has_weather = false;
static uint8_t s_battery = 0;
static bool s_charging = false;
static bool s_connected = true;

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

static void prv_set_weather_icon(int index) {
  if (index < 0 || index >= WEATHER_ICON_COUNT) {
    index = WEATHER_UNKNOWN;
  }
  if (s_weather_icon && index == s_weather_icon_index) {
    return;
  }
  if (s_weather_icon) {
    gbitmap_destroy(s_weather_icon);
    s_weather_icon = NULL;
  }
  s_weather_icon_index = index;
  if (s_weather_sheet) {
    s_weather_icon = gbitmap_create_as_sub_bitmap(
        s_weather_sheet, GRect(index * ICON_W, 0, ICON_W, ICON_H));
  }
}

// The status icons take the two top corners, with the time centred between them.
// At its widest -- "23:58" -- the time is 103px of the 200, so there is room on
// both sides; tools/mockup.py checks both gaps.
static void prv_draw_battery(GContext *ctx, GRect bounds) {
  const int x = bounds.size.w - BATT_RIGHT_PAD - BATT_W - 3;  // 3px for the nub

  graphics_context_set_stroke_color(ctx, STATUS_COLOR);
  graphics_context_set_fill_color(ctx, STATUS_COLOR);
  graphics_draw_rect(ctx, GRect(x, BATT_TOP, BATT_W, BATT_H));
  graphics_fill_rect(ctx, GRect(x + BATT_W, BATT_TOP + 3, 3, BATT_H - 6), 0, GCornerNone);

  const int inner = BATT_W - 2;
  int fill = (inner * s_battery) / 100;
  if (fill > inner) {
    fill = inner;
  }
  if (fill > 0) {
    graphics_fill_rect(ctx, GRect(x + 1, BATT_TOP + 1, fill, BATT_H - 2), 0, GCornerNone);
  }
  if (s_charging) {
    // A bolt is fiddly at this size; a notch out of the middle reads well enough.
    graphics_context_set_fill_color(ctx, GColorBlack);
    graphics_fill_rect(ctx, GRect(x + BATT_W / 2 - 1, BATT_TOP + 2, 2, BATT_H - 4), 0, GCornerNone);
  }
}

static void prv_draw_bluetooth(GContext *ctx, GRect bounds) {
  // Only drawn while disconnected -- a permanent icon is noise.
  if (s_connected) {
    return;
  }
  // In the opposite corner from the battery rather than beside it. Beside it,
  // the pair reached far enough in from the right that a 24h "23:58" came
  // within a pixel of the icon; split across the two corners, the time has the
  // same room on either side and neither icon is anywhere near it.
  const int x = EDGE_PAD;
  const int y = BATT_TOP;
  graphics_context_set_stroke_color(ctx, STATUS_COLOR);
  graphics_context_set_stroke_width(ctx, 2);
  graphics_draw_line(ctx, GPoint(x, y + 2), GPoint(x + 7, y + 8));
  graphics_draw_line(ctx, GPoint(x, y + 8), GPoint(x + 7, y + 2));
  graphics_draw_line(ctx, GPoint(x + 4, y - 1), GPoint(x + 4, y + 11));
  graphics_context_set_stroke_width(ctx, 1);
}

static void prv_canvas_update(Layer *layer, GContext *ctx) {
  const GRect bounds = layer_get_bounds(layer);

  // The flower. The bitmap is only the ART_H band below the header; the window's
  // black background carries the header, which is the same black the artwork's
  // own ground is drawn in, so there is no seam to hide and the header needs no
  // fill of its own.
  if (s_tile) {
    graphics_context_set_compositing_mode(ctx, GCompOpAssign);
    graphics_draw_bitmap_in_rect(ctx, s_tile, GRect(0, ART_TOP, bounds.size.w, ART_H));
  }

  prv_draw_battery(ctx, bounds);
  prv_draw_bluetooth(ctx, bounds);

  graphics_context_set_fill_color(ctx, RULE_COLOR);
  graphics_fill_rect(ctx, GRect(0, RULE_TOP, bounds.size.w, RULE_H), 0, GCornerNone);

  graphics_context_set_text_color(ctx, TIME_COLOR);
  graphics_draw_text(ctx, s_time_text, s_time_font,
                     GRect(TIME_LEFT, TIME_TOP, TIME_WIDTH, TIME_HEIGHT),
                     GTextOverflowModeTrailingEllipsis, GTextAlignmentCenter, NULL);

  // The weather sits against the right edge; the date gets everything to the
  // left of it, so it never has to be truncated.
  const int icon_x = bounds.size.w - EDGE_PAD - INFO_TEMP_W - ICON_GAP - ICON_W;

  graphics_context_set_text_color(ctx, INFO_COLOR);
  graphics_draw_text(ctx, s_date_text, s_info_font,
                     GRect(EDGE_PAD, INFO_TOP, icon_x - EDGE_PAD - ICON_GAP, INFO_HEIGHT),
                     GTextOverflowModeTrailingEllipsis, GTextAlignmentLeft, NULL);

  if (s_has_weather) {
    graphics_draw_text(
        ctx, s_temp_text, s_info_font,
        GRect(bounds.size.w - EDGE_PAD - INFO_TEMP_W, INFO_TOP, INFO_TEMP_W, INFO_HEIGHT),
        GTextOverflowModeTrailingEllipsis, GTextAlignmentRight, NULL);
    if (s_weather_icon) {
      graphics_context_set_compositing_mode(ctx, GCompOpSet);
      graphics_draw_bitmap_in_rect(ctx, s_weather_icon,
                                   GRect(icon_x, ICON_TOP, ICON_W, ICON_H));
    }
  }
}

// ---------------------------------------------------------------------------
// Clock
// ---------------------------------------------------------------------------

static void prv_update_time(struct tm *tick) {
  const char *fmt = clock_is_24h_style() ? "%H:%M" : "%I:%M";
  strftime(s_time_text, sizeof(s_time_text), fmt, tick);
  if (!clock_is_24h_style() && s_time_text[0] == '0') {
    memmove(s_time_text, s_time_text + 1, strlen(s_time_text));
  }
  // Built piece by piece rather than with one strftime: Pebble's strftime does
  // not carry %e, and %d would pad the day with a zero.
  char day[8];
  char month[8];
  strftime(day, sizeof(day), "%a", tick);
  strftime(month, sizeof(month), "%b", tick);
  snprintf(s_date_text, sizeof(s_date_text), "%s %s %d", day, month, tick->tm_mday);
  // The info font is subset to uppercase only.
  for (char *c = s_date_text; *c; c++) {
    *c = toupper((unsigned char)*c);
  }
}

static void prv_request_weather(void);

static void prv_tick(struct tm *tick, TimeUnits units_changed) {
  prv_update_time(tick);
  layer_mark_dirty(s_canvas);
  if (tick->tm_min % WEATHER_INTERVAL_MIN == 0) {
    prv_request_weather();
  }
}

// ---------------------------------------------------------------------------
// Weather
// ---------------------------------------------------------------------------

static void prv_request_weather(void) {
  DictionaryIterator *out;
  if (app_message_outbox_begin(&out) != APP_MSG_OK) {
    return;
  }
  dict_write_uint8(out, KEY_FETCH, 1);
  app_message_outbox_send();
}

static void prv_apply_weather(int temp, int icon) {
  snprintf(s_temp_text, sizeof(s_temp_text), "%d°", temp);
  prv_set_weather_icon(icon);
  s_has_weather = true;
  persist_write_int(PERSIST_TEMP, temp);
  persist_write_int(PERSIST_ICON, icon);
  layer_mark_dirty(s_canvas);
}

static void prv_inbox_received(DictionaryIterator *iter, void *context) {
  Tuple *temp = dict_find(iter, KEY_TEMP);
  Tuple *icon = dict_find(iter, KEY_ICON);
  if (!temp) {
    return;
  }
  prv_apply_weather((int)temp->value->int32, icon ? (int)icon->value->int32 : WEATHER_UNKNOWN);
}

static void prv_inbox_dropped(AppMessageResult reason, void *context) {
  APP_LOG(APP_LOG_LEVEL_WARNING, "inbox dropped: %d", (int)reason);
}

static void prv_outbox_failed(DictionaryIterator *iter, AppMessageResult reason, void *context) {
  APP_LOG(APP_LOG_LEVEL_WARNING, "outbox failed: %d", (int)reason);
}

// ---------------------------------------------------------------------------
// Services
// ---------------------------------------------------------------------------

static void prv_battery_handler(BatteryChargeState state) {
  s_battery = state.charge_percent;
  s_charging = state.is_charging || state.is_plugged;
  layer_mark_dirty(s_canvas);
}

static void prv_connection_handler(bool connected) {
  const bool was_connected = s_connected;
  s_connected = connected;
  if (was_connected && !connected) {
    vibes_double_pulse();
  } else if (!was_connected && connected) {
    prv_request_weather();
  }
  layer_mark_dirty(s_canvas);
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

static void prv_window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  const GRect bounds = layer_get_bounds(root);

  s_tile = gbitmap_create_with_resource(RESOURCE_ID_IMAGE_TILE);
  s_weather_sheet = gbitmap_create_with_resource(RESOURCE_ID_IMAGE_WEATHER_ICONS);
  s_time_font = fonts_load_custom_font(resource_get_handle(RESOURCE_ID_FONT_TIME_38));
  s_info_font = fonts_load_custom_font(resource_get_handle(RESOURCE_ID_FONT_INFO_22));

  s_canvas = layer_create(bounds);
  layer_set_update_proc(s_canvas, prv_canvas_update);
  layer_add_child(root, s_canvas);

  // After the layer exists: restoring the reading marks it dirty.
  if (persist_exists(PERSIST_TEMP)) {
    prv_apply_weather(persist_read_int(PERSIST_TEMP), persist_read_int(PERSIST_ICON));
  } else {
    prv_set_weather_icon(WEATHER_UNKNOWN);
  }
}

static void prv_window_unload(Window *window) {
  layer_destroy(s_canvas);
  fonts_unload_custom_font(s_time_font);
  fonts_unload_custom_font(s_info_font);
  if (s_weather_icon) {
    gbitmap_destroy(s_weather_icon);
  }
  gbitmap_destroy(s_weather_sheet);
  gbitmap_destroy(s_tile);
}

static void prv_init(void) {
  s_window = window_create();
  window_set_background_color(s_window, GColorBlack);
  window_set_window_handlers(s_window, (WindowHandlers){
                                           .load = prv_window_load,
                                           .unload = prv_window_unload,
                                       });
  window_stack_push(s_window, true);

  const time_t now = time(NULL);
  prv_update_time(localtime(&now));

  const BatteryChargeState battery = battery_state_service_peek();
  s_battery = battery.charge_percent;
  s_charging = battery.is_charging || battery.is_plugged;
  s_connected = connection_service_peek_pebble_app_connection();

  tick_timer_service_subscribe(MINUTE_UNIT, prv_tick);
  battery_state_service_subscribe(prv_battery_handler);
  connection_service_subscribe((ConnectionHandlers){
      .pebble_app_connection_handler = prv_connection_handler,
  });

  app_message_register_inbox_received(prv_inbox_received);
  app_message_register_inbox_dropped(prv_inbox_dropped);
  app_message_register_outbox_failed(prv_outbox_failed);
  app_message_open(128, 64);
}

static void prv_deinit(void) {
  app_message_deregister_callbacks();
  connection_service_unsubscribe();
  battery_state_service_unsubscribe();
  tick_timer_service_unsubscribe();
  window_destroy(s_window);
}

int main(void) {
  prv_init();
  app_event_loop();
  prv_deinit();
}
