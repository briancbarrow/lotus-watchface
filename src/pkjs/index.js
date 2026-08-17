// Phone-side half of the watchface: it turns the watch's FETCH request into a
// weather lookup and sends the temperature and an icon index back.
//
// Open-Meteo is used because it needs no API key and no account, so the
// watchface works as soon as it is installed.

// Flip to 'celsius' if you want metric. The watch only ever sees a number.
var UNITS = 'fahrenheit';

var API = 'https://api.open-meteo.com/v1/forecast';

// Icon frame indices, matching WeatherIcon in src/c/aang.c.
var ICON = {
  CLEAR: 0,
  FEW_CLOUDS: 1,
  CLOUDY: 2,
  FOG: 3,
  RAIN: 4,
  SNOW: 5,
  THUNDER: 6,
  UNKNOWN: 7
};

// WMO weather codes, as documented by Open-Meteo, collapsed onto our icons.
function iconForCode(code) {
  if (code === 0) return ICON.CLEAR;
  if (code === 1 || code === 2) return ICON.FEW_CLOUDS;
  if (code === 3) return ICON.CLOUDY;
  if (code === 45 || code === 48) return ICON.FOG;
  if (code >= 51 && code <= 67) return ICON.RAIN;   // drizzle and freezing rain
  if (code >= 71 && code <= 77) return ICON.SNOW;
  if (code >= 80 && code <= 82) return ICON.RAIN;   // showers
  if (code === 85 || code === 86) return ICON.SNOW; // snow showers
  if (code >= 95) return ICON.THUNDER;
  return ICON.UNKNOWN;
}

function send(temp, icon) {
  Pebble.sendAppMessage(
    { TEMP: temp, ICON: icon },
    function () {},
    function (e) {
      console.log('send failed: ' + JSON.stringify(e));
    }
  );
}

function fetchWeather(lat, lon) {
  var url =
    API +
    '?latitude=' + lat.toFixed(3) +
    '&longitude=' + lon.toFixed(3) +
    '&current=temperature_2m,weather_code' +
    '&temperature_unit=' + UNITS;

  var req = new XMLHttpRequest();
  req.open('GET', url, true);
  req.timeout = 20000;
  req.onload = function () {
    if (req.status !== 200) {
      console.log('weather http ' + req.status);
      return;
    }
    try {
      var current = JSON.parse(req.responseText).current;
      send(Math.round(current.temperature_2m), iconForCode(current.weather_code));
    } catch (e) {
      console.log('weather parse failed: ' + e);
    }
  };
  req.onerror = function () {
    console.log('weather request failed');
  };
  req.ontimeout = function () {
    console.log('weather request timed out');
  };
  req.send();
}

function locateAndFetch() {
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      fetchWeather(pos.coords.latitude, pos.coords.longitude);
    },
    function (err) {
      console.log('location failed: ' + err.message);
    },
    { timeout: 15000, maximumAge: 15 * 60 * 1000 }
  );
}

Pebble.addEventListener('ready', function () {
  locateAndFetch();
});

// The watch drives the refresh interval; this side just answers.
Pebble.addEventListener('appmessage', function (e) {
  if (e.payload && e.payload.FETCH) {
    locateAndFetch();
  }
});
