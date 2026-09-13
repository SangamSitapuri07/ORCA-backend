/* ORCA live weather map — zoom.earth-style animated layer.
 *
 * Data: GET /api/v1/weather/grid (DWD ICON via Open-Meteo) — one call,
 * all frames — plus GET /api/v1/ocean/grid (NOAA satellite currents +
 * CoralTemp SST + Open-Meteo Marine waves). Each falls back to its
 * bundled REAL snapshot (?demo=1, clearly badged) when live is
 * unreachable.
 *
 * Rendering: two stacked canvases over a Leaflet map —
 *   #field     humidity colours (crossfaded between hourly frames,
 *              half-cell-correct raster stretch) + graticule + cities
 *   #particles wind particles advected through the (time-interpolated)
 *              10 m wind field, fading trails, mercator-correct speeds
 *
 * Coordinates: particles live in WORLD mercator px (geo-glued during
 * pan/zoom); sampling is bilinear in geographic space over the grid.
 */
'use strict';

/* ── palette (kept in sync with pipeline/humidity.py PALETTE) ── */
const PALETTE = [
  [0, 0xB3, 0x54, 0x1E], [20, 0xE6, 0x7E, 0x22], [40, 0xF4, 0xD0, 0x3F],
  [60, 0xA9, 0xDF, 0x72], [75, 0x58, 0xD6, 0x8D], [85, 0x2E, 0x9E, 0x8F],
  [100, 0x1A, 0x52, 0x76],
];
function colorFor(rh) {
  if (rh === null || rh === undefined || isNaN(rh)) return [0, 0, 0, 0];
  const v = Math.max(0, Math.min(100, rh));
  let i = 0;
  while (i < PALETTE.length - 2 && v > PALETTE[i + 1][0]) i++;
  const a = PALETTE[i], b = PALETTE[i + 1];
  const f = (v - a[0]) / (b[0] - a[0] || 1);
  /* [1, r, g, b] — slot 0 is the "valid" flag the tiny-raster builders
   * gate their pixel alpha on (null data → [0,…] → transparent) */
  return [1, Math.round(a[1] + f * (b[1] - a[1])),
          Math.round(a[2] + f * (b[2] - a[2])),
          Math.round(a[3] + f * (b[3] - a[3]))];
}
/* sea-surface temperature palette (°C → colour) */
const SST_PALETTE = [
  [25.0, 0x21, 0x66, 0xAC], [26.5, 0x43, 0x93, 0xC3], [27.5, 0x92, 0xC5, 0xDE],
  [28.0, 0xFD, 0xB8, 0x63], [28.5, 0xE0, 0x82, 0x14], [29.0, 0xB2, 0x18, 0x2B],
];
function colorForSst(t) {
  if (t === null || t === undefined || isNaN(t)) return [0, 0, 0, 0];
  const v = Math.max(SST_PALETTE[0][0], Math.min(SST_PALETTE[SST_PALETTE.length - 1][0], t));
  let i = 0;
  while (i < SST_PALETTE.length - 2 && v > SST_PALETTE[i + 1][0]) i++;
  const a = SST_PALETTE[i], b = SST_PALETTE[i + 1];
  const f = (v - a[0]) / (b[0] - a[0] || 1);
  return [1, Math.round(a[1] + f * (b[1] - a[1])),
          Math.round(a[2] + f * (b[2] - a[2])),
          Math.round(a[3] + f * (b[3] - a[3]))];   /* [1,r,g,b]: 1 = valid */
}
/* wave-height palette (m → colour), mirrors ocean_grid.wave_legend */
const WAVE_PALETTE = [
  [0.0, 0x1B, 0x4F, 0x72], [0.5, 0x2E, 0x86, 0xC1], [1.0, 0x48, 0xC9, 0xB0],
  [1.5, 0xF4, 0xD0, 0x3F], [2.0, 0xE6, 0x7E, 0x22], [3.0, 0xB0, 0x3A, 0x2E],
  [4.0, 0x64, 0x1E, 0x16],
];
function colorForWave(h) {
  if (h === null || h === undefined || isNaN(h)) return [0, 0, 0, 0];
  const v = Math.max(0, Math.min(4, h));
  let i = 0;
  while (i < WAVE_PALETTE.length - 2 && v > WAVE_PALETTE[i + 1][0]) i++;
  const a = WAVE_PALETTE[i], b = WAVE_PALETTE[i + 1];
  const f = (v - a[0]) / (b[0] - a[0] || 1);
  return [Math.round(a[1] + f * (b[1] - a[1])),
          Math.round(a[2] + f * (b[2] - a[2])),
          Math.round(a[3] + f * (b[3] - a[3]))];
}
/* ── selectable field layers (zoom.earth-style picker) ── */
const TEMP_PALETTE = [
  [20, 0x21, 0x66, 0xAC], [24, 0x43, 0x93, 0xC3], [27, 0x92, 0xC5, 0xDE],
  [29, 0xFD, 0xB8, 0x63], [32, 0xE0, 0x82, 0x14], [36, 0xB2, 0x18, 0x2B],
];
const WIND_KMH = [
  [0, 0x1B, 0x4F, 0x72], [10, 0x2E, 0x86, 0xC1], [20, 0x48, 0xC9, 0xB0],
  [30, 0xF4, 0xD0, 0x3F], [40, 0xE6, 0x7E, 0x22], [55, 0xB0, 0x3A, 0x2E], [75, 0x64, 0x1E, 0x16],
];
const GUST_KMH = [
  [10, 0x1B, 0x4F, 0x72], [20, 0x2E, 0x86, 0xC1], [30, 0x48, 0xC9, 0xB0],
  [40, 0xF4, 0xD0, 0x3F], [55, 0xE6, 0x7E, 0x22], [70, 0xB0, 0x3A, 0x2E], [90, 0x64, 0x1E, 0x16],
];
const RAIN_PALETTE = [
  [0.05, 0xA3, 0xD9, 0x77], [0.5, 0xF4, 0xD0, 0x3F], [1.5, 0xE6, 0x7E, 0x22],
  [3, 0xB0, 0x3A, 0x2E], [6, 0x7B, 0x1F, 0xA2], [12, 0x4A, 0x14, 0x8C],
];
const CLOUD_PALETTE = [
  [20, 0x5D, 0x6D, 0x7E], [40, 0x85, 0x92, 0x9E], [60, 0xAA, 0xB7, 0xB8],
  [80, 0xD5, 0xDB, 0xDB], [100, 0xF8, 0xF9, 0xF9],
];
const CURR_PALETTE = [
  [0, 0x1B, 0x4F, 0x72], [0.2, 0x2E, 0x86, 0xC1], [0.4, 0x48, 0xC9, 0xB0],
  [0.6, 0xF4, 0xD0, 0x3F], [0.8, 0xE6, 0x7E, 0x22], [1.2, 0xB0, 0x3A, 0x2E],
];
/* generic palette sampler — [1,r,g,b] (1 = valid), [0,…] for null */
function palColor(pal, v) {
  if (v === null || v === undefined || isNaN(v)) return [0, 0, 0, 0];
  const vv = Math.max(pal[0][0], Math.min(pal[pal.length - 1][0], v));
  let i = 0;
  while (i < pal.length - 2 && vv > pal[i + 1][0]) i++;
  const a = pal[i], b = pal[i + 1];
  const f = (vv - a[0]) / (b[0] - a[0] || 1);
  return [1, Math.round(a[1] + f * (b[1] - a[1])),
          Math.round(a[2] + f * (b[2] - a[2])),
          Math.round(a[3] + f * (b[3] - a[3]))];
}
/* weather frame index → nearest ODATA wave frame (both hourly UTC) */
function waveFrameFor(f) {
  if (!ODATA || !ODATA.times.length) return 0;
  const span = Math.max(1, (DATA ? DATA.times.length : 8) - 1);
  return Math.max(0, Math.min(ODATA.times.length - 1,
      Math.round(f * (ODATA.times.length - 1) / span)));
}
const LAYERS = [
  {id: 'rh',    label: 'humidity %',  src: 'w', title: 'humidity %',  pal: PALETTE,
   get: (d, f, p) => d.rh[f][p]},
  {id: 'temp',  label: 'temperature', src: 'w', title: 'temp °C',     pal: TEMP_PALETTE,
   get: (d, f, p) => d.temp[f][p]},
  {id: 'wind',  label: 'wind speed',  src: 'w', title: 'wind km/h',   pal: WIND_KMH,
   get: (d, f, p) => (d.u[f][p] === null || d.v[f][p] === null) ?
       null : Math.hypot(d.u[f][p], d.v[f][p]) * 3.6},
  {id: 'gust',  label: 'wind gusts',  src: 'w', title: 'gusts km/h',  pal: GUST_KMH,
   get: (d, f, p) => d.gust ? d.gust[f][p] : null},
  {id: 'rain',  label: 'rain',        src: 'w', title: 'rain mm/h',   pal: RAIN_PALETTE,
   get: (d, f, p) => d.pr ? d.pr[f][p] : null, cut: 0.05},
  {id: 'cloud', label: 'clouds',      src: 'w', title: 'cloud %',     pal: CLOUD_PALETTE,
   get: (d, f, p) => d.cloud ? d.cloud[f][p] : null, cut: 10},
  {id: 'sst',   label: 'sea temp',    src: 'o', title: 'sea temp °C', pal: SST_PALETTE,
   get: (d, f, p) => d.sst ? d.sst[p] : null},
  {id: 'wave',  label: 'waves',       src: 'o', title: 'wave m',      pal: WAVE_PALETTE,
   get: (d, f, p) => d.wh ? d.wh[waveFrameFor(f)][p] : null},
  {id: 'cur',   label: 'currents',    src: 'o', title: 'current m/s', pal: CURR_PALETTE,
   get: (d, f, p) => (d.cu === null || d.cv === null || d.cu[p] === null ||
                      d.cv[p] === null) ? null : Math.hypot(d.cu[p], d.cv[p])},
];
/* build the per-frame tiny rasters for the ACTIVE layer */
function buildTinies() {
  tinies = [];
  if (!DATA) return;
  const L = LAYERS.find((l) => l.id === activeLayer);
  if (!L) return;
  if (L.src === 'o' && !ODATA) return;      /* sea layer before ocean feed lands */
  const d = L.src === 'o' ? ODATA : DATA;
  const n = d.grid_n, F = DATA.times.length;
  for (let f = 0; f < F; f++) {
    const cv = document.createElement('canvas');
    cv.width = n; cv.height = n;
    const c2 = cv.getContext('2d');
    const img = c2.createImageData(n, n);
    for (let p = 0; p < n * n; p++) {
      const v = L.get(d, f, p);
      const col = (v === null || v === undefined) ? [0, 0, 0, 0] :
          ((L.cut !== undefined && v < L.cut) ? [0, 0, 0, 0] : palColor(L.pal, v));
      img.data[p * 4] = col[1]; img.data[p * 4 + 1] = col[2];
      img.data[p * 4 + 2] = col[3]; img.data[p * 4 + 3] = col[0] ? 235 : 0;
    }
    c2.putImageData(img, 0, 0);
    tinies.push(cv);
  }
}
function selectLayer(id) {
  activeLayer = id;
  document.querySelectorAll('#layers .lyr').forEach(
      (b) => b.classList.toggle('on', b.dataset.lyr === id));
  buildTinies(); buildLegend(); needsField = true;
}

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
const IST_MIN = 330;                       // UTC + 5:30
const SIM_RATE = 20000;                    // sim-seconds per real-second
const CUR_SIM_RATE = SIM_RATE * 8;         // currents displayed 8× true speed
const HOURS_PER_SEC = 0.9;                 // time-slider playback speed
const CITIES = [['Bhuj', 23.24, 69.67], ['Dwarka', 22.24, 68.97],
                ['Jamnagar', 22.47, 70.06], ['Rajkot', 22.30, 70.80],
                ['Porbandar', 21.64, 69.61], ['Kandla', 23.03, 70.22]];

/* ── state ── */
let DATA = null, DEMO = false, loading = false;
let ODATA = null, ODEMO = false, activeLayer = 'rh';
let t = 0, playing = true, lastTs = 0, needsField = true, lastDrawnT = -1;
let cursorLL = null, tinies = [];
let dataBounds = null, coverBox = null;   // data coverage box + jump target
let particles = [], curParticles = [], origin = {x: 0, y: 0}, scale = 1;

const map = L.map('map', {zoomControl: true, attributionControl: true,
                          minZoom: 4, maxZoom: 17, worldCopyJump: false})
  .setView([22.2, 69.4], 7);

/* Real basemaps — fetched DIRECTLY by the browser from Esri/CARTO/OSM
 * (the backend proxy can't reach tile servers from every network; the
 * user's browser almost always can). If a provider is unreachable the
 * layer auto-falls-forward, ending at the first-party proxy. */
const BASEMAPS = [
  {id: 'satellite', label: 'Satellite',
   url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
   attr: 'Imagery © Esri, Maxar, Earthstar Geographics', maxZoom: 18},
  {id: 'dark', label: 'Dark',
   url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
   attr: '© OpenStreetMap contributors © CARTO', subdomains: 'abcd', maxZoom: 19},
  {id: 'streets', label: 'Streets',
   url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
   attr: '© OpenStreetMap contributors', maxZoom: 19},
  {id: 'proxy', label: 'Proxy',
   url: '/api/v1/tiles/{z}/{x}/{y}.png',
   attr: 'ORCA tile proxy', maxZoom: 12},
];
let baseLayer = null, tileOk = false;
function mountBasemap(i) {
  const cfg = BASEMAPS[Math.max(0, Math.min(i, BASEMAPS.length - 1))];
  if (baseLayer) map.removeLayer(baseLayer);
  tileOk = false;
  baseLayer = L.tileLayer(cfg.url, {
      maxZoom: cfg.maxZoom, attribution: cfg.attr,
      subdomains: cfg.subdomains || 'abc'})
    .on('tileload', () => { tileOk = true; })
    .on('tileerror', () => {
      /* zero tiles loaded → provider unreachable → fall forward */
      if (!tileOk && i + 1 < BASEMAPS.length) mountBasemap(i + 1);
    })
    .addTo(map);
  document.querySelectorAll('.bm').forEach(b =>
    b.classList.toggle('on', b.dataset.bm === cfg.id));
}
mountBasemap(0);                    /* satellite — the zoom.earth look */
document.querySelectorAll('.bm').forEach(b => b.addEventListener('click', () => {
  const i = BASEMAPS.findIndex(c => c.id === b.dataset.bm);
  if (i >= 0) mountBasemap(i);
}));

const fC = document.getElementById('field'), pC = document.getElementById('particles');
const wC = document.getElementById('wavemark'), cC = document.getElementById('currents');
const fx = fC.getContext('2d'), px = pC.getContext('2d');
const wx = wC.getContext('2d'), cx = cC.getContext('2d');
const $ = (id) => document.getElementById(id);

/* ── mercator helpers (world px) ── */
function reproj() {
  scale = 256 * Math.pow(2, map.getZoom());
  origin = map.getPixelOrigin();
}
const mX = (lon) => (lon + 180) / 360 * scale;
const mY = (lat) => (1 - Math.log(Math.tan(lat * Math.PI / 180) +
           1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * scale;
const wLon = (wx) => wx / scale * 360 - 180;
const wLat = (wy) => Math.atan(Math.sinh(Math.PI * (1 - 2 * wy / scale))) * 180 / Math.PI;
const toC = (wx, wy) => ({x: wx - origin.x, y: wy - origin.y});

/* ── data ── */
async function loadGrid(followView) {
  loading = true; showStatus('Loading DWD ICON grid…');
  const c = map.getCenter();
  let span = 3.0;
  if (followView) {
    const b = map.getBounds();
    span = Math.max(b.getNorth() - b.getSouth(),
                    (b.getEast() - b.getWest()) * Math.cos(c.lat * Math.PI / 180));
    span = Math.max(0.6, Math.min(30, span));
  }
  const base = '/api/v1/weather/grid';
  const q = `?lat=${c.lat.toFixed(3)}&lon=${c.lng.toFixed(3)}` +
            `&span=${span.toFixed(2)}&frames=8&grid=12`;
  loadOcean(q);                       // parallel; independent fallback
  try {
    const r = await fetch(base + q);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    DATA = await r.json();
    if (DATA.error) throw new Error(DATA.error);
    DEMO = false;
  } catch (e) {
    if (DEMO) { showStatus('live fetch failed (' + e.message + ') — staying on demo', true); loading = false; return; }
    const r2 = await fetch(base + '?demo=1');
    if (!r2.ok) { showStatus('no data available (' + e.message + ')', true); loading = false; return; }
    DATA = await r2.json();
    DEMO = true;
  }
  onData(followView);
}

async function loadOcean(q) {
  const base = '/api/v1/ocean/grid';
  try {
    const r = await fetch(base + q);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    ODATA = await r.json();
    if (ODATA.error) throw new Error(ODATA.error);
    ODEMO = false;
  } catch (e) {
    if (!ODEMO) {
      try {
        const r2 = await fetch(base + '?demo=1');
        if (r2.ok) { ODATA = await r2.json(); ODEMO = true; }
      } catch (e2) { /* sea layers simply stay off */ }
    }
  }
  onOceanData();
}

function onOceanData() {
  if (!ODATA) return;
  curRespawn(); needsField = true;
  const L = LAYERS.find((l) => l.id === activeLayer);
  if (L && L.src === 'o') buildTinies();   /* selected sea layer can paint now */
  updateBadge(); buildLegend();
}

function updateBadge() {
  const badge = $('modeBadge');
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const when = (s) => {          /* "2026-09-13T16:10:00+00:00" -> "13 Sep 16:10 UTC" */
    if (!s) return '';
    const d = new Date(s);
    return d.getUTCDate() + ' ' + MON[d.getUTCMonth()] + ' ' +
        String(d.getUTCHours()).padStart(2, '0') + ':' +
        String(d.getUTCMinutes()).padStart(2, '0') + ' UTC';
  };
  const w = DATA ? when(DATA.fetched_at) : '';
  if (DEMO && ODEMO) {
    badge.className = 'badge demo';
    badge.innerHTML = '<span class="dot"></span>DEMO — REAL DATA · DWD ICON ' + w +
        ' · NOAA CURRENTS/SST/WAVES 10–13 SEP';
  } else if (DEMO) {
    badge.className = 'badge demo';
    badge.innerHTML = '<span class="dot"></span>LIVE OCEAN · WEATHER DEMO (DWD ICON ' + w + ')';
  } else if (ODEMO) {
    badge.className = 'badge demo';
    badge.innerHTML = '<span class="dot"></span>LIVE ICON · OCEAN DEMO (NOAA SNAPSHOTS 10–13 SEP)';
  } else if (DATA) {
    badge.className = 'badge live';
    badge.innerHTML = '<span class="dot"></span>LIVE · DWD ICON + NOAA SATELLITE · ' +
        DATA.fetched_at.slice(11, 16) + ' UTC';
  }
}

function onData(fitIt) {
  loading = false; hideStatus();
  const n = DATA.grid_n, F = DATA.times.length;
  t = Math.min(t, F - 1);
  $('tslider').max = String((F - 1) * 100);
  buildTinies();          /* tiny per-frame rasters for the active layer */
  buildLegend();
  updateBadge();
  if (fitIt) {
    map.fitBounds([[DATA.lats[n - 1], DATA.lons[0]], [DATA.lats[0], DATA.lons[n - 1]]],
                  {padding: [24, 24]});
  }
  /* dashed coverage box — always shows where the data lives; in demo
   * mode, snap back if the current view doesn't touch it at all */
  dataBounds = L.latLngBounds([DATA.lats[n - 1], DATA.lons[0]],
                               [DATA.lats[0], DATA.lons[n - 1]]);
  if (coverBox) map.removeLayer(coverBox);
  coverBox = L.rectangle(dataBounds, {color: '#fff', weight: 1, opacity: 0.55,
                                      dashArray: '4 6', fill: false,
                                      interactive: false});
  coverBox.addTo(map);
  if (DEMO && !map.getBounds().intersects(dataBounds) && !fitIt) {
    map.fitBounds(dataBounds, {padding: [24, 24]});
  }
  reproj(); respawn(); needsField = true;
}

/* ── sampling (bilinear in geo space, frames lerped) ── */
function sampleField(lat, lon, tt, key) {
  const n = DATA.grid_n, lats = DATA.lats, lons = DATA.lons;
  if (lat > lats[0] || lat < lats[n - 1] || lon < lons[0] || lon > lons[n - 1]) return null;
  let r = 0, c = 0;
  while (r < n - 2 && lat < lats[r + 1]) r++;
  while (c < n - 2 && lon > lons[c + 1]) c++;
  const fr = (lats[r] - lat) / (lats[r] - lats[r + 1]);
  const fc = (lon - lons[c]) / (lons[c + 1] - lons[c]);
  const fA = Math.floor(tt), fB = Math.min(fA + 1, DATA.times.length - 1);
  const g = (f) => {
    const arr = DATA[key][f];
    const i00 = arr[r * n + c], i10 = arr[r * n + c + 1];
    const i01 = arr[(r + 1) * n + c], i11 = arr[(r + 1) * n + c + 1];
    if (i00 === null || i10 === null || i01 === null || i11 === null) return null;
    return (i00 * (1 - fc) + i10 * fc) * (1 - fr) + (i01 * (1 - fc) + i11 * fc) * fr;
  };
  const a = g(fA), b = g(fB);
  if (a === null || b === null) return null;
  return a + (b - a) * (tt - fA);
}
function sampleWind(lat, lon, tt) {
  const u = sampleField(lat, lon, tt, 'u');
  const v = sampleField(lat, lon, tt, 'v');
  if (u === null || v === null) return null;
  return {u, v};
}

/* ── sea sampling (lattice of ODATA; daily fields constant, waves hourly) ── */
function sampleSea(lat, lon, frame, key) {
  if (!ODATA) return null;
  const n = ODATA.grid_n, lats = ODATA.lats, lons = ODATA.lons;
  if (lat > lats[0] || lat < lats[n - 1] || lon < lons[0] || lon > lons[n - 1]) return null;
  let r = 0, c = 0;
  while (r < n - 2 && lat < lats[r + 1]) r++;
  while (c < n - 2 && lon > lons[c + 1]) c++;
  const fr = (lats[r] - lat) / (lats[r] - lats[r + 1]);
  const fc = (lon - lons[c]) / (lons[c + 1] - lons[c]);
  const arr = (key === 'cu' || key === 'cv' || key === 'sst') ? ODATA[key] : ODATA[key][frame];
  if (!arr) return null;
  const i00 = arr[r * n + c], i10 = arr[r * n + c + 1];
  const i01 = arr[(r + 1) * n + c], i11 = arr[(r + 1) * n + c + 1];
  if (i00 === null || i10 === null || i01 === null || i11 === null) return null;
  return (i00 * (1 - fc) + i10 * fc) * (1 - fr) + (i01 * (1 - fc) + i11 * fc) * fr;
}
/* map the weather clock onto the nearest wave frame (times are UTC) */
function waveFrameAt(tt) {
  if (!ODATA || !ODATA.times.length || !DATA || !DATA.times.length) return 0;
  const fA = Math.max(0, Math.min(DATA.times.length - 1, Math.floor(tt)));
  const target = parseT(DATA.times[fA])[1] + (tt - fA) * 60;   // minutes UTC
  let best = 0, bd = Infinity;
  for (let i = 0; i < ODATA.times.length; i++) {
    const d = Math.abs(parseT(ODATA.times[i])[1] - target);
    if (d < bd) { bd = d; best = i; }
  }
  return best;
}

/* ── field layer ── */
function drawField(tt) {
  const W = fC.clientWidth, H = fC.clientHeight;
  fx.clearRect(0, 0, W, H);
  if (!DATA) return;
  const n = DATA.grid_n, F = DATA.times.length;
  const p0 = toC(mX(DATA.lons[0]), mY(DATA.lats[0]));
  const p1 = toC(mX(DATA.lons[n - 1]), mY(DATA.lats[n - 1]));
  const wpx = p1.x - p0.x, hpx = p1.y - p0.y;
  const cellX = wpx / (n - 1), cellY = hpx / (n - 1);
  const rect = [p0.x - cellX / 2, p0.y - cellY / 2, wpx + cellX, hpx + cellY];

  if (tinies.length) {                     /* active-layer wash (picker) */
    const fA = Math.max(0, Math.min(F - 1, Math.floor(tt)));
    const fB = Math.min(fA + 1, F - 1);
    const frac = tt - fA;
    fx.imageSmoothingEnabled = true; fx.imageSmoothingQuality = 'high';
    fx.drawImage(tinies[fA], ...rect);
    if (frac > 0.004 && fB !== fA) {
      fx.globalAlpha = Math.min(1, frac);
      fx.drawImage(tinies[fB], ...rect);
      fx.globalAlpha = 1;
    }
  }
  if ($('tgRef').checked) drawRef(p0, p1);
  fx.strokeStyle = 'rgba(150,180,205,0.5)'; fx.lineWidth = 1.5;
  fx.strokeRect(p0.x, p0.y, wpx, hpx);
}

function drawRef(p0, p1) {
  const x0 = p0.x, y0 = p0.y, x1 = p1.x, y1 = p1.y;
  fx.lineWidth = 1; fx.strokeStyle = 'rgba(255,255,255,0.18)';
  fx.fillStyle = 'rgba(255,255,255,0.85)';
  fx.font = '11px "Segoe UI", system-ui, sans-serif';
  const lonL = wLon(x0 + origin.x), lonR = wLon(x1 + origin.x);
  const latT = wLat(y0 + origin.y), latB = wLat(y1 + origin.y);
  for (let lon = Math.ceil(lonL); lon <= Math.floor(lonR); lon++) {
    const x = mX(lon) - origin.x;
    fx.beginPath(); fx.moveTo(x, y0); fx.lineTo(x, y1); fx.stroke();
    fx.fillText(lon + '°E', x + 4, y1 - 6);
  }
  for (let lat = Math.ceil(latB); lat <= Math.floor(latT); lat++) {
    const y = mY(lat) - origin.y;
    fx.beginPath(); fx.moveTo(x0, y); fx.lineTo(x1, y); fx.stroke();
    fx.fillText(lat + '°N', x0 + 4, y + 13);
  }
  for (const [name, la, lo] of CITIES) {
    if (la > latT || la < latB || lo < lonL || lo > lonR) continue;
    const x = mX(lo) - origin.x, y = mY(la) - origin.y;
    fx.fillStyle = '#fff';
    fx.beginPath(); fx.arc(x, y, 2.6, 0, 7); fx.fill();
    fx.strokeStyle = 'rgba(10,20,30,0.9)'; fx.lineWidth = 1;
    fx.beginPath(); fx.arc(x, y, 2.6, 0, 7); fx.stroke();
    fx.fillStyle = 'rgba(255,255,255,0.92)';
    fx.fillText(name, x + 6, y - 5);
  }
}

/* ── wind particles ── */
function respawn() {
  if (!DATA) { particles = []; return; }
  const n = DATA.grid_n;
  const bx0 = mX(DATA.lons[0]), bx1 = mX(DATA.lons[n - 1]);
  const by0 = mY(DATA.lats[0]), by1 = mY(DATA.lats[n - 1]);
  /* density: ~1 particle per 170 px² of grid box (scaled by zoom),
   * bounded so tiny boxes never get overcrowded */
  let count = Math.round((bx1 - bx0) * (by1 - by0) / 170 /
                         Math.max(1, scale / 32768));
  count = Math.max(500, Math.min(2600, count));
  count = Math.min(count, Math.round((bx1 - bx0) * (by1 - by0) / 6));
  particles = [];
  for (let i = 0; i < count; i++) {
    particles.push({
      wx: bx0 + Math.random() * (bx1 - bx0),
      wy: by0 + Math.random() * (by1 - by0),
      age: Math.random() * 240,
    });
  }
}

function drawParticles(dt, tt) {
  const W = pC.clientWidth, H = pC.clientHeight;
  px.globalCompositeOperation = 'destination-out';
  px.fillStyle = 'rgba(0,0,0,0.045)';
  px.fillRect(0, 0, W, H);
  px.globalCompositeOperation = 'source-over';
  if (!DATA || !$('tgWind').checked) return;

  const n = DATA.grid_n;
  const bx0 = mX(DATA.lons[0]), bx1 = mX(DATA.lons[n - 1]);
  const by0 = mY(DATA.lats[0]), by1 = mY(DATA.lats[n - 1]);
  const pxPerM = scale / 40075016.686;
  px.strokeStyle = 'rgba(255,255,255,0.62)';
  px.lineWidth = 1.35;
  px.beginPath();
  for (const p of particles) {
    const lat = wLat(p.wy);
    const w = sampleWind(lat, wLon(p.wx), tt);
    p.age++;
    if (!w || p.age > 100 + (p.age % 200) || p.wx < bx0 || p.wx > bx1 ||
        p.wy < by0 || p.wy > by1) {
      p.wx = bx0 + Math.random() * (bx1 - bx0);
      p.wy = by0 + Math.random() * (by1 - by0);
      p.age = 0;
      continue;
    }
    const spd = Math.hypot(w.u, w.v);
    let dx = w.u * SIM_RATE * dt * pxPerM;
    let dy = -w.v * SIM_RATE * dt * pxPerM / Math.cos(lat * Math.PI / 180);
    const d = Math.hypot(dx, dy);
    if (d > 6) { dx *= 6 / d; dy *= 6 / d; }      // cap per-frame jump
    const a = toC(p.wx, p.wy), b = {x: a.x + dx, y: a.y + dy};
    if (spd > 0.4) { px.moveTo(a.x, a.y); px.lineTo(b.x, b.y); }
    p.wx += dx; p.wy += dy;
  }
  px.stroke();
}

/* ── current particles (satellite geostrophic flow, cyan, slower) ── */
function curRespawn() {
  curParticles = [];
  if (!ODATA) return;
  const n = ODATA.grid_n;
  const bx0 = mX(ODATA.lons[0]), bx1 = mX(ODATA.lons[n - 1]);
  const by0 = mY(ODATA.lats[0]), by1 = mY(ODATA.lats[n - 1]);
  const count = Math.max(200, Math.min(1200,
      Math.round((bx1 - bx0) * (by1 - by0) / 700)));
  for (let i = 0; i < count; i++) {
    curParticles.push({wx: bx0 + Math.random() * (bx1 - bx0),
                       wy: by0 + Math.random() * (by1 - by0),
                       age: Math.random() * 300});
  }
}
function drawCurParticles(dt) {
  const W = cC.clientWidth, H = cC.clientHeight;
  cx.globalCompositeOperation = 'destination-out';
  cx.fillStyle = 'rgba(0,0,0,0.06)';
  cx.fillRect(0, 0, W, H);
  cx.globalCompositeOperation = 'source-over';
  if (!ODATA || !$('tgCur').checked) return;
  const n = ODATA.grid_n;
  const bx0 = mX(ODATA.lons[0]), bx1 = mX(ODATA.lons[n - 1]);
  const by0 = mY(ODATA.lats[0]), by1 = mY(ODATA.lats[n - 1]);
  const pxPerM = scale / 40075016.686;
  cx.strokeStyle = 'rgba(0,229,255,0.65)';
  cx.lineWidth = 1.45;
  cx.beginPath();
  for (const p of curParticles) {
    const lat = wLat(p.wy), lon = wLon(p.wx);
    const u = sampleSea(lat, lon, 0, 'cu'), v = sampleSea(lat, lon, 0, 'cv');
    p.age++;
    if (u === null || v === null || p.age > 260 ||
        p.wx < bx0 || p.wx > bx1 || p.wy < by0 || p.wy > by1) {
      p.wx = bx0 + Math.random() * (bx1 - bx0);
      p.wy = by0 + Math.random() * (by1 - by0);
      p.age = 0;
      continue;
    }
    let dx = u * CUR_SIM_RATE * dt * pxPerM;
    let dy = -v * CUR_SIM_RATE * dt * pxPerM / Math.cos(lat * Math.PI / 180);
    const d = Math.hypot(dx, dy);
    if (d > 5) { dx *= 5 / d; dy *= 5 / d; }
    const a = toC(p.wx, p.wy);
    if (Math.hypot(u, v) > 0.02) { cx.moveTo(a.x, a.y); cx.lineTo(a.x + dx, a.y + dy); }
    p.wx += dx; p.wy += dy;
  }
  cx.stroke();
}

/* ── wave arrows (chevrons toward travel direction, coloured by height) ── */
function drawWaves(tt) {
  const W = wC.clientWidth, H = wC.clientHeight;
  wx.clearRect(0, 0, W, H);
  if (!ODATA || !$('tgWaves').checked) return;
  const n = ODATA.grid_n, f = waveFrameAt(tt);
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      const p = r * n + c;
      const h = ODATA.wh[f] ? ODATA.wh[f][p] : null;
      if (h === null || h === undefined) continue;
      const dirFrom = ODATA.wd[f][p];
      const per = ODATA.wp[f][p];
      const x = mX(ODATA.lons[c]) - origin.x, y = mY(ODATA.lats[r]) - origin.y;
      if (x < -20 || x > W + 20 || y < -20 || y > H + 20) continue;
      const ang = (dirFrom + 180) * Math.PI / 180;   // toward-direction, screen
      const L = 11 + Math.min(9, h * 3);
      const [rr, gg, bb] = colorForWave(h);
      wx.strokeStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',0.92)';
      wx.lineWidth = 1.6;
      wx.beginPath();
      wx.moveTo(x - Math.sin(ang) * L / 2, y + Math.cos(ang) * L / 2);
      wx.lineTo(x + Math.sin(ang) * L / 2, y - Math.cos(ang) * L / 2);
      wx.stroke();
      /* head chevron */
      const hx = x + Math.sin(ang) * L / 2, hy = y - Math.cos(ang) * L / 2;
      wx.beginPath();
      wx.moveTo(hx - Math.sin(ang + 2.5) * 4, hy + Math.cos(ang + 2.5) * 4);
      wx.lineTo(hx, hy);
      wx.lineTo(hx - Math.sin(ang - 2.5) * 4, hy + Math.cos(ang - 2.5) * 4);
      wx.stroke();
      if (per !== null && n <= 9) {
        wx.fillStyle = 'rgba(255,255,255,0.75)';
        wx.font = '9px system-ui, sans-serif';
        wx.fillText(h.toFixed(1) + 'm', hx + 4, hy - 3);
      }
    }
  }
}

/* ── HUD ── */
let pinLL = null, pinMarker = null;   // click-to-pin readout
function updateHud() {
  if (!DATA) return;
  const focus = pinLL || cursorLL;
  if (!focus) {
    $('hPos').textContent = $('hRh').textContent = $('hWind').textContent =
      $('hTemp').textContent = $('hGust').textContent =
      $('hRain').textContent = '—';
    $('hHint').textContent = 'move the cursor over the map — or click to pin a point';
    return;
  }
  const {lat, lng} = focus;
  $('hPos').textContent = lat.toFixed(2) + '°N ' + lng.toFixed(2) + '°E';
  const rh = sampleField(lat, lng, t, 'rh');
  $('hRh').textContent = rh === null ? 'outside grid' : rh.toFixed(0) + ' %';
  const w = sampleWind(lat, lng, t);
  if (w) {
    const spd = Math.hypot(w.u, w.v);
    const dir = (270 - Math.atan2(w.v, w.u) * 180 / Math.PI + 360) % 360;
    $('hWind').textContent = spd.toFixed(1) + ' m/s · ' + (spd * 3.6).toFixed(0) +
      ' km/h · from ' + COMPASS[Math.round(dir / 22.5) % 16] + ' (' + dir.toFixed(0) + '°)';
  } else $('hWind').textContent = 'outside grid';
  const tp = sampleField(lat, lng, t, 'temp');
  $('hTemp').textContent = tp === null ? 'outside grid' : tp.toFixed(1) + ' °C';
  const gu = sampleField(lat, lng, t, 'gust');
  $('hGust').textContent = gu === null ? '—' : gu.toFixed(0) + ' km/h';
  const rn = sampleField(lat, lng, t, 'pr');
  $('hRain').textContent = rn === null ? '—' :
      (rn < 0.05 ? 'dry' : rn.toFixed(1) + ' mm/h');
  /* sea readout: SST, current (toward), waves (from) */
  if (ODATA) {
    const sstv = sampleSea(lat, lng, 0, 'sst');
    const cu = sampleSea(lat, lng, 0, 'cu'), cv = sampleSea(lat, lng, 0, 'cv');
    const wf = waveFrameAt(t);
    const wh = sampleSea(lat, lng, wf, 'wh'), wd = sampleSea(lat, lng, wf, 'wd');
    const wp = sampleSea(lat, lng, wf, 'wp');
    let parts = [];
    if (sstv !== null) parts.push(sstv.toFixed(1) + ' °C');
    if (cu !== null && cv !== null) {
      const sp = Math.hypot(cu, cv);
      const toward = (Math.atan2(cu, cv) * 180 / Math.PI + 360) % 360;
      parts.push('cur ' + sp.toFixed(2) + ' m/s ' + COMPASS[Math.round(toward / 22.5) % 16]);
    }
    if (wh !== null) {
      parts.push('waves ' + wh.toFixed(1) + ' m from ' +
        COMPASS[Math.round(wd / 22.5) % 16] + (wp !== null ? ' · ' + wp.toFixed(0) + ' s' : ''));
    }
    $('hSea').textContent = parts.length ? parts.join(' · ') : 'land';
  } else $('hSea').textContent = '—';
  $('hHint').textContent = (pinLL ? '📌 pinned at ' + pinLL.lat.toFixed(2) + '°N ' +
      pinLL.lng.toFixed(2) + '°E · click the pin again to unpin · ' :
      'values at cursor · ') + timeLabel(t) + ' IST · currents shown 8× speed';
}

/* ── time ── */
function parseT(s) {   // "2026-09-13T07:00" (UTC) -> [dayLabel, minutes]
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return [parseInt(m[3], 10) + ' ' + MONTHS[parseInt(m[2], 10) - 1] +
          (parseInt(m[3], 10) < 15 ? '' : ''), parseInt(m[4], 10) * 60 + parseInt(m[5], 10)];
}
function timeLabel(tt) {
  if (!DATA || !DATA.times.length) return '—';
  const fA = Math.max(0, Math.min(DATA.times.length - 1, Math.floor(tt)));
  const [day, min] = parseT(DATA.times[fA]);
  let tot = Math.round(min + (tt - fA) * 60 + IST_MIN);
  let d = day;
  if (tot >= 1440) { tot -= 1440; d = nextDay(day); }
  const hh = String(Math.floor(tot / 60)).padStart(2, '0');
  const mm = String(tot % 60).padStart(2, '0');
  return d + ' · ' + hh + ':' + mm;
}
function nextDay(day) {
  const [d, m] = day.split(' ');
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const L = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const i = MONTHS.indexOf(m);
  const nd = parseInt(d, 10) + 1;
  return nd > L[i] ? '1 ' + MONTHS[(i + 1) % 12] : nd + ' ' + m;
}
function refreshTimeLabel() {
  const rel = t < 0.05 ? 'now' : '+' + t.toFixed(1) + ' h';
  $('tlabel').textContent = timeLabel(t) + ' IST · ' + rel;
}

/* ── legend ── */
function buildLegend() {
  const L = LAYERS.find((l) => l.id === activeLayer) || LAYERS[0];
  const stops = (L.id === 'rh' && DATA && DATA.legend && DATA.legend.length) ?
      DATA.legend.map((s) => [s.value, s.color]) :
      L.pal.map((p) => [p[0], 'rgb(' + p[1] + ',' + p[2] + ',' + p[3] + ')']);
  const lo = stops[0][0], hi = stops[stops.length - 1][0];
  $('legendgrad').style.background = 'linear-gradient(90deg,' +
      stops.map((s) => s[1] + ' ' + (((s[0] - lo) / (hi - lo || 1)) * 100).toFixed(1) + '%')
          .join(',') + ')';
  $('legendticks').innerHTML = stops.map((s) => '<span>' + s[0] + '</span>').join('');
  $('legendtitle').textContent = L.title;
}

/* ── status ── */
function showStatus(msg, isErr) {
  const el = $('status');
  el.style.display = 'block';
  el.className = 'panel' + (isErr ? ' err' : '');
  el.textContent = msg;
}
function hideStatus() { $('status').style.display = 'none'; }

/* ── main loop ── */
function loop(ts) {
  const dt = Math.min((ts - lastTs) / 1000 || 0.016, 0.05);
  lastTs = ts;
  if (DATA) {
    if (playing) {
      t += dt * HOURS_PER_SEC;
      if (t > DATA.times.length - 1) t = 0;
      $('tslider').value = String(Math.round(t * 100));
    }
    drawParticles(dt, t);
    drawCurParticles(dt);
    if (needsField || Math.abs(t - lastDrawnT) > 0.008) {
      drawField(t); lastDrawnT = t; needsField = false;
      drawWaves(t);
      refreshTimeLabel();
    }
    updateHud();
  }
  requestAnimationFrame(loop);
}

/* ── events ── */
$('play').onclick = () => {
  playing = !playing;
  $('play').textContent = playing ? '▶' : '❚❚';
};
$('fitbox').onclick = () => {
  if (dataBounds) map.fitBounds(dataBounds, {padding: [24, 24]});
};
$('tslider').oninput = (e) => { t = parseInt(e.target.value, 10) / 100; };
map.on('mousemove', (e) => { cursorLL = e.latlng; });
map.on('mouseout', () => { cursorLL = null; });
/* click-to-pin: first click drops a pin and freezes the HUD readout on
   that point (so you can scrub the time slider and watch the point's
   values evolve); clicking the pin again removes it. */
map.on('click', (e) => {
  if (pinLL && Math.abs(e.latlng.lat - pinLL.lat) < 0.02 &&
      Math.abs(e.latlng.lng - pinLL.lng) < 0.02) {
    pinLL = null;
    if (pinMarker) { map.removeLayer(pinMarker); pinMarker = null; }
    return;
  }
  pinLL = e.latlng;
  if (!pinMarker) {
    pinMarker = L.circleMarker(pinLL, {radius: 7, color: '#fff', weight: 2.5,
                                       fillColor: '#0af', fillOpacity: 0.9});
    pinMarker.addTo(map);
  } else { pinMarker.setLatLng(pinLL); }
});
map.on('move zoom', () => { reproj(); needsField = true; });
map.on('zoomstart', () => {
  px.clearRect(0, 0, pC.clientWidth, pC.clientHeight);
  cx.clearRect(0, 0, cC.clientWidth, cC.clientHeight);
});
map.on('moveend', () => {
  reproj(); respawn(); needsField = true;
  if (!DEMO && !loading) {
    clearTimeout(loadGrid._deb);
    loadGrid._deb = setTimeout(() => loadGrid(true), 900);
  }
  /* demo mode: if the user panned away from the covered box, say so
   * instead of silently showing an empty map */
  if (DEMO && dataBounds) {
    if (!map.getBounds().intersects(dataBounds)) {
      showStatus('no live fetch in this sandbox — demo data covers the dashed Kutch box · tap ⌖ to jump back', true);
    } else { hideStatus(); }
  }
});
$('tgRef').onchange = () => { needsField = true; };
document.querySelectorAll('#layers .lyr').forEach((b) => {
  b.onclick = () => selectLayer(b.dataset.lyr);
});
$('tgCur').onchange = () => {
  cx.clearRect(0, 0, cC.clientWidth, cC.clientHeight); curRespawn();
};
$('tgWaves').onchange = () => {
  wx.clearRect(0, 0, wC.clientWidth, wC.clientHeight); needsField = true;
};

function resize() {
  const dpr = window.devicePixelRatio || 1;
  for (const cv of [fC, wC, cC, pC]) {
    cv.width = Math.round(cv.clientWidth * dpr);
    cv.height = Math.round(cv.clientHeight * dpr);
    cv.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  needsField = true;
}
window.addEventListener('resize', resize);

/* ── boot ── */
resize();
loadGrid(true);
requestAnimationFrame(loop);
