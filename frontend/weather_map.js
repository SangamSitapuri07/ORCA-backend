/* ORCA live weather map — zoom.earth-style animated layer.
 *
 * Data: GET /api/v1/weather/grid (DWD ICON via Open-Meteo) — one call,
 * all frames. Falls back to the bundled REAL snapshot (?demo=1, clearly
 * badged) when the live API is unreachable.
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
  return [0, Math.round(a[1] + f * (b[1] - a[1])),
          Math.round(a[2] + f * (b[2] - a[2])),
          Math.round(a[3] + f * (b[3] - a[3]))];
}
const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
const IST_MIN = 330;                       // UTC + 5:30
const SIM_RATE = 20000;                    // sim-seconds per real-second
const HOURS_PER_SEC = 0.9;                 // time-slider playback speed
const CITIES = [['Bhuj', 23.24, 69.67], ['Dwarka', 22.24, 68.97],
                ['Jamnagar', 22.47, 70.06], ['Rajkot', 22.30, 70.80],
                ['Porbandar', 21.64, 69.61], ['Kandla', 23.03, 70.22]];

/* ── state ── */
let DATA = null, DEMO = false, loading = false;
let t = 0, playing = true, lastTs = 0, needsField = true, lastDrawnT = -1;
let cursorLL = null, tinies = [];
let particles = [], origin = {x: 0, y: 0}, scale = 1;

const map = L.map('map', {zoomControl: true, attributionControl: true,
                          minZoom: 4, maxZoom: 12, worldCopyJump: false})
  .setView([22.2, 69.4], 7);
L.tileLayer('/api/v1/tiles/{z}/{x}/{y}.png', {maxZoom: 12}).addTo(map);

const fC = document.getElementById('field'), pC = document.getElementById('particles');
const fx = fC.getContext('2d'), px = pC.getContext('2d');
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
  try {
    const r = await fetch(`${base}?lat=${c.lat.toFixed(3)}&lon=${c.lng.toFixed(3)}` +
                          `&span=${span.toFixed(2)}&frames=8&grid=12`);
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

function onData(fitIt) {
  loading = false; hideStatus();
  const n = DATA.grid_n, F = DATA.times.length;
  t = Math.min(t, F - 1);
  $('tslider').max = String((F - 1) * 100);
  /* tiny per-frame colour rasters */
  tinies = [];
  for (let f = 0; f < F; f++) {
    const cv = document.createElement('canvas');
    cv.width = n; cv.height = n;
    const cx = cv.getContext('2d');
    const img = cx.createImageData(n, n);
    for (let p = 0; p < n * n; p++) {
      const col = colorFor(DATA.rh[f][p]);
      img.data[p * 4] = col[1]; img.data[p * 4 + 1] = col[2];
      img.data[p * 4 + 2] = col[3]; img.data[p * 4 + 3] = col[0] ? 235 : 0;
    }
    cx.putImageData(img, 0, 0);
    tinies.push(cv);
  }
  buildLegend();
  const badge = $('modeBadge');
  if (DEMO) {
    badge.className = 'badge demo';
    badge.innerHTML = '<span class="dot"></span>DEMO — REAL ICON SNAPSHOT · 13 SEP 07:00 UTC';
  } else {
    badge.className = 'badge live';
    badge.innerHTML = '<span class="dot"></span>LIVE · DWD ICON · ' + DATA.fetched_at.slice(11, 16) + ' UTC';
  }
  if (fitIt) {
    map.fitBounds([[DATA.lats[n - 1], DATA.lons[0]], [DATA.lats[0], DATA.lons[n - 1]]],
                  {padding: [24, 24]});
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

  if ($('tgHum').checked) {
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
  const count = Math.max(350, Math.min(2400,
      Math.round((bx1 - bx0) * (by1 - by0) / 420 / Math.max(1, scale / 32768))));
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
  px.fillStyle = 'rgba(0,0,0,0.07)';
  px.fillRect(0, 0, W, H);
  px.globalCompositeOperation = 'source-over';
  if (!DATA || !$('tgWind').checked) return;

  const n = DATA.grid_n;
  const bx0 = mX(DATA.lons[0]), bx1 = mX(DATA.lons[n - 1]);
  const by0 = mY(DATA.lats[0]), by1 = mY(DATA.lats[n - 1]);
  const pxPerM = scale / 40075016.686;
  px.strokeStyle = 'rgba(255,255,255,0.5)';
  px.lineWidth = 1.15;
  px.beginPath();
  for (const p of particles) {
    const lat = wLat(p.wy);
    const w = sampleWind(lat, wLon(p.wx), tt);
    p.age++;
    if (!w || p.age > 100 + (p.age % 200) || p.wx < bx0 || p.wx > bx1 ||
        p.wy < by1 || p.wy > by0) {
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

/* ── HUD ── */
function updateHud() {
  if (!DATA) return;
  if (!cursorLL) {
    $('hPos').textContent = $('hRh').textContent = $('hWind').textContent =
      $('hTemp').textContent = '—';
    $('hHint').textContent = 'move the cursor over the map';
    return;
  }
  const {lat, lng} = cursorLL;
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
  $('hHint').textContent = 'values at cursor · ' + timeLabel(t) + ' (IST)';
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
  const stops = (DATA.legend && DATA.legend.length) ?
      DATA.legend.map((s) => [s.value, s.color]) : PALETTE.map((p) => [p[0],
        'rgb(' + p[1] + ',' + p[2] + ',' + p[3] + ')']);
  $('legendgrad').style.background =
      'linear-gradient(90deg,' + stops.map((s) => s[1] + ' ' + s[0] + '%').join(',') + ')';
  $('legendticks').innerHTML = stops.map((s) => '<span>' + s[0] + '</span>').join('');
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
    if (needsField || Math.abs(t - lastDrawnT) > 0.008) {
      drawField(t); lastDrawnT = t; needsField = false;
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
$('tslider').oninput = (e) => { t = parseInt(e.target.value, 10) / 100; };
map.on('mousemove', (e) => { cursorLL = e.latlng; });
map.on('mouseout', () => { cursorLL = null; });
map.on('move zoom', () => { reproj(); needsField = true; });
map.on('zoomstart', () => { px.clearRect(0, 0, pC.clientWidth, pC.clientHeight); });
map.on('moveend', () => {
  reproj(); respawn(); needsField = true;
  if (!DEMO && !loading) {
    clearTimeout(loadGrid._deb);
    loadGrid._deb = setTimeout(() => loadGrid(true), 900);
  }
});
for (const id of ['tgHum', 'tgRef']) $(id).onchange = () => { needsField = true; };

function resize() {
  const dpr = window.devicePixelRatio || 1;
  for (const cv of [fC, pC]) {
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
