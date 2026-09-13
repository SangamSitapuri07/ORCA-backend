/* ORCA GPU wind-particle engine — WebGL 1, ZERO extensions required.
 * ==========================================================================
 * Implements the ORCA spec §7/§10/§11: thousands of particles advected on
 * the GPU through the REAL spatial wind field (u/v from the validated
 * weather grid), with trails, speed-based colour ramp, configurable
 * settings and adaptive quality. Falls back to the Canvas-2D engine
 * (drawParticles) automatically when WebGL is unavailable or errors.
 *
 * DATA FLOW (spec §10):
 *   backend grid (u/v per frame, m/s, real model data)
 *     → per-frame RGBA8 "wind textures" (n×n, 16-bit u + 16-bit v)
 *     → GPU vertex/fragment shaders sample them with HARDWARE BILINEAR
 *       filtering (same interpolation as the CPU sampler)
 *     → particle positions in a ping-pong RGBA8 texture (16-bit x/y in
 *       grid-normalised [0,1]² coordinates — zoom-invariant)
 *
 * TEXTURE ENCODINGS (documented per spec §10 — no silent precision loss):
 *   wind texture texel = [u_hi, u_lo, v_hi, v_lo] bytes
 *     u = (r·256 + g) / 65535 · 160 − 80  m/s   (range ±80 m/s)
 *     v = (b·256 + a) / 65535 · 160 − 80  m/s
 *     resolution: 160/65535 ≈ 0.0024 m/s — finer than the source model
 *   position texture texel = [x_hi, x_lo, y_hi, y_lo] bytes
 *     x = (r·256 + g)/65535, y = (b·256 + a)/65535  in [0,1] grid units
 *     resolution: 1/65535 of the grid box (~0.02 px on a 1400 px box)
 *
 * SCIENTIFIC CONVENTIONS (spec §9):
 *   u/v are m/s components of the meteorological wind vector (blowing
 *   FROM direction θ): u = −spd·sin θ, v = −spd·cos θ — identical to the
 *   backend derivation (pipeline/weather_grid.py). The GPU moves
 *   particles with the SAME advection formula as the CPU engine
 *   (dx = u·SIM_RATE·dt·pxPerM, dy = −v·…/cos φ), so both engines are
 *   visually equivalent. Particle colour = |(u,v)|·3.6 in km/h on the
 *   map's WIND_KMH palette (single source of truth, passed in by the
 *   page) — the unit is stated in the legend, never switched silently.
 *
 * This file is a rendering accelerator only: it never invents data. If
 * the field contains missing cells (nulls) the engine refuses the field
 * (setField → false) and the page keeps the CPU path, which handles
 * nulls correctly.
 * ========================================================================== */
'use strict';

(function () {

const VERT_QUAD = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() { v_uv = a_pos; gl_Position = vec4(a_pos * 2.0 - 1.0, 0.0, 1.0); }
`;

/* ── update pass: advect every particle, handle respawn ── */
const FRAG_UPDATE = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform sampler2D u_pos, u_windA, u_windB;
uniform float u_mix, u_dt, u_time, u_dropRate, u_simRate, u_speedScale;
uniform vec4  u_gridWorld;          /* gx0, gy0(north), gx1, gy1(south) world px */
uniform vec2  u_geoScale;           /* pxPerM, N = 256*2^zoom                  */
uniform vec3  u_debug;              /* on, u, v  (verification override)      */
varying vec2 v_uv;

vec2 decodePos(vec4 t) {
  return vec2(t.r * 65280.0 + t.g * 255.0, t.b * 65280.0 + t.a * 255.0) / 65535.0;
}
vec4 encodePos(vec2 p) {
  vec2 v = clamp(floor(p * 65535.0), 0.0, 65535.0);
  return vec4(floor(v.x / 256.0), mod(v.x, 256.0),
              floor(v.y / 256.0), mod(v.y, 256.0)) / 255.0;
}
vec2 decodeWind(vec4 t) {
  return vec2((t.r * 65280.0 + t.g * 255.0) / 65535.0 * 160.0 - 80.0,
              (t.b * 65280.0 + t.a * 255.0) / 65535.0 * 160.0 - 80.0);
}
float hash(vec2 x) {
  return fract(sin(dot(x, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
  vec2 p = decodePos(texture2D(u_pos, v_uv));
  /* p.y = 0 is the NORTH edge (matches gy0 = mY(lats[0])); texture row 0
   * (v = 0) is also the north row — sample with NO flip */
  vec2 wuv = vec2(p.x, p.y);
  vec2 wind;
  if (u_debug.x > 0.5) {
    wind = u_debug.yz;
  } else {
    vec2 a = decodeWind(texture2D(u_windA, wuv));
    vec2 b = decodeWind(texture2D(u_windB, wuv));
    wind = mix(a, b, u_mix) * u_speedScale;
  }

  /* advection: identical formula to the CPU engine, in world px */
  vec2 size = u_gridWorld.zw - u_gridWorld.xy;
  vec2 world = u_gridWorld.xy + p * size;
  /* inverse Web-Mercator: φ = atan(sinh(π(1−2y/N))); sinh is not in
   * GLSL ES 1.0, so use its exponential form */
  float mt = 3.14159265 * (1.0 - 2.0 * world.y / u_geoScale.y);
  float lat = atan(0.5 * (exp(mt) - 1.0 / exp(mt)));
  vec2 dpx = vec2(wind.x, -wind.y / max(cos(lat), 0.05))
             * u_simRate * u_dt * u_geoScale.x;
  float d = length(dpx);
  if (d > 6.0) dpx *= 6.0 / d;                 /* CPU-parity per-frame jump cap */
  vec2 np = p + dpx / size;

  /* respawn: left the box, random drop, or lifetime elapsed (stateless:
   * lifetime derived from a per-texel seed + wall-clock generation) */
  float seed = hash(v_uv);
  float life = 2.0 + 6.0 * seed;               /* seconds, staggered per particle */
  float gen = floor(u_time / life);
  bool drop = hash(v_uv * 1.7 + u_time) < u_dropRate * u_dt * 60.0;
  if (np.x < 0.0 || np.x > 1.0 || np.y < 0.0 || np.y > 1.0 || drop) {
    np = vec2(hash(v_uv + gen * 0.37), hash(v_uv.yx + gen * 1.13));
  }
  gl_FragColor = encodePos(np);
}
`;

/* ── draw pass: particles as points, coloured by wind speed ── */
const VERT_DRAW = `
precision highp float;
attribute vec2 a_pos;               /* per-particle uv (texel centre) */
uniform sampler2D u_pos, u_windA, u_windB;
uniform float u_mix, u_size, u_count, u_texSize, u_dpr, u_speedScale;
uniform vec4  u_screenGrid;         /* grid box on screen, CSS px: x0, y0, w, h */
uniform vec2  u_canvas;             /* canvas size, device px */
uniform vec3  u_debug;
varying float v_kmh;

vec2 decodePos(vec4 t) {
  return vec2(t.r * 65280.0 + t.g * 255.0, t.b * 65280.0 + t.a * 255.0) / 65535.0;
}
vec2 decodeWind(vec4 t) {
  return vec2((t.r * 65280.0 + t.g * 255.0) / 65535.0 * 160.0 - 80.0,
              (t.b * 65280.0 + t.a * 255.0) / 65535.0 * 160.0 - 80.0);
}

void main() {
  float idx = floor(a_pos.y * u_texSize) * u_texSize + floor(a_pos.x * u_texSize);
  if (idx >= u_count) { gl_Position = vec4(2.0, 2.0, 0.0, 1.0); gl_PointSize = 0.0; return; }
  vec2 p = decodePos(texture2D(u_pos, a_pos));
  vec2 wind;
  if (u_debug.x > 0.5) {
    wind = u_debug.yz;
  } else {
    vec2 wuv = vec2(p.x, p.y);
    vec2 a = decodeWind(texture2D(u_windA, wuv));
    vec2 b = decodeWind(texture2D(u_windB, wuv));
    wind = mix(a, b, u_mix) * u_speedScale;
  }
  v_kmh = length(wind) * 3.6;
  vec2 dev = (u_screenGrid.xy + p * u_screenGrid.zw) * u_dpr;
  gl_Position = vec4(dev / u_canvas * 2.0 - 1.0, 0.0, 1.0);
  gl_PointSize = max(u_size * u_dpr, 1.0);
}
`;

const FRAG_DRAW = `
precision mediump float;
varying float v_kmh;
uniform vec4 u_stops[7];            /* [kmh, r, g, b] — page palette */
uniform float u_alpha;
void main() {
  vec3 col = u_stops[0].yzw;
  for (int i = 1; i < 7; i++) {
    float v1 = u_stops[i].x;
    if (v_kmh <= v1) {
      float f = clamp((v_kmh - u_stops[i - 1].x) / max(v1 - u_stops[i - 1].x, 0.001), 0.0, 1.0);
      col = mix(u_stops[i - 1].yzw, u_stops[i].yzw, f);
      break;
    }
    col = u_stops[i].yzw;
  }
  gl_FragColor = vec4(col * u_alpha, u_alpha);
}
`;

/* ── trail fade + composite passes ── */
const FRAG_FADE = `
precision mediump float;
uniform sampler2D u_trail;
uniform float u_fade;
varying vec2 v_uv;
void main() { gl_FragColor = texture2D(u_trail, v_uv) * u_fade; }
`;

const FRAG_COMPOSITE = `
precision mediump float;
uniform sampler2D u_trail;
varying vec2 v_uv;
void main() { gl_FragColor = texture2D(u_trail, v_uv); }
`;

const WIND_ENC_RANGE = 160.0;   /* ±80 m/s, documented above */
const TEX = 256;                /* position texture 256×256 = 65,536 slots   */

class WindGPU {
  static _seq = 0;
  constructor(canvas) {
    this.canvas = canvas;
    this.ok = false;
    this.failed = false;
    this.hasField = false;
    this.debugWind = null;       /* {u, v} m/s — verification override */
    this.debugGL = false;        /* per-pass gl.getError capture */
    this._dbg = [];
    this.time = 0;
    this.frameTimes = [];
    this._slowFrames = 0;

    /* configurable rendering settings (spec §11 — NOT scientific values) */
    this.config = {
      count: (('ontouchstart' in window) || innerWidth < 900) ? 9000 : 30000,
      size: 1.5,                 /* point size, CSS px */
      fade: 0.94,                /* trail decay per frame */
      alpha: 0.42,               /* particle opacity */
      dropRate: 0.006,           /* random respawn probability/frame */
      speedScale: 1.0,           /* animation speed multiplier (§68) */
    };

    const gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: true,
                                            antialias: false, depth: false });
    if (!gl) return;
    if (gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS) < 1) return;
    gl.disable(gl.DITHER);   /* keep byte-exact RGBA8 round-trips */
    this.gl = gl;

    this._progQuad   = this._program(VERT_QUAD, FRAG_UPDATE);
    this._progDraw   = this._program(VERT_DRAW, FRAG_DRAW);
    this._progFade   = this._program(VERT_QUAD, FRAG_FADE);
    this._progComp   = this._program(VERT_QUAD, FRAG_COMPOSITE);
    this._u = {};
    for (const [prog, names] of [
      [this._progQuad, ['u_pos', 'u_windA', 'u_windB', 'u_mix', 'u_dt', 'u_time',
                        'u_dropRate', 'u_simRate', 'u_speedScale', 'u_gridWorld',
                        'u_geoScale', 'u_debug']],
      [this._progDraw, ['u_pos', 'u_windA', 'u_windB', 'u_mix', 'u_size', 'u_count',
                        'u_texSize', 'u_dpr', 'u_speedScale', 'u_screenGrid',
                        'u_canvas', 'u_debug', 'u_stops', 'u_alpha']],
      [this._progFade, ['u_trail', 'u_fade']],
      [this._progComp, ['u_trail']],
    ]) {
      this._u[prog.__id] = {};
      for (const n of names) this._u[prog.__id][n] = gl.getUniformLocation(prog, n);
    }

    /* quad buffer + full per-particle vertex buffer */
    this._quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this._quadBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]),
                  gl.STATIC_DRAW);
    const pts = new Float32Array(TEX * TEX * 2);
    for (let ty = 0; ty < TEX; ty++)
      for (let tx = 0; tx < TEX; tx++) {
        const i = (ty * TEX + tx) * 2;
        pts[i] = (tx + 0.5) / TEX; pts[i + 1] = (ty + 0.5) / TEX;
      }
    this._ptBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this._ptBuf);
    gl.bufferData(gl.ARRAY_BUFFER, pts, gl.STATIC_DRAW);

    /* position ping-pong textures — random initial positions */
    this._pos = [];
    const rand = new Uint8Array(TEX * TEX * 4);
    for (let i = 0; i < 2; i++) {
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      for (let k = 0; k < rand.length; k++) rand[k] = (Math.random() * 256) | 0;
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, TEX, TEX, 0, gl.RGBA,
                    gl.UNSIGNED_BYTE, rand);
      this._texParams(t);
      this._pos.push({ tex: t, fbo: this._fbo(t) });
    }
    this._posIdx = 0;

    this._trail = [null, null];
    this._trailIdx = 0;
    this._windTex = [];          /* one per data frame */
    this._palette = null;
    this.ok = true;
  }

  /* ── helpers ── */
  _texParams(t) {
    const gl = this.gl;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }
  _fbo(tex) {
    const gl = this.gl;
    const fb = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return fb;
  }
  _program(vs, fs) {
    const gl = this.gl;
    const compile = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
        throw new Error('shader: ' + gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS))
      throw new Error('link: ' + gl.getProgramInfoLog(p));
    /* unique id per program — two programs whose shader sources share a
     * prefix (fade/composite) MUST NOT share a uniform-location table:
     * they collided once and the fade pass set the composite's uniform
     * (GL INVALID_OPERATION) while u_fade stayed 0 → trails wiped every
     * frame and particles looked frozen */
    p.__id = 'prog' + (++WindGPU._seq);
    return p;
  }
  _quad(prog) {                  /* bind quad buffer to a program's a_pos */
    const gl = this.gl, loc = gl.getAttribLocation(prog, 'a_pos');
    gl.bindBuffer(gl.ARRAY_BUFFER, this._quadBuf);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  }

  setPalette(stops) {            /* [[kmh, r, g, b], ...] — page's palette */
    this._palette = stops.map(s => [s[0], s[1] / 255, s[2] / 255, s[3] / 255]);
  }

  /* Build one RGBA8 wind texture per frame. Returns false (and keeps the
   * engine field-less → CPU fallback) if any u/v cell is missing: the GPU
   * path has no null representation and must never turn missing into 0. */
  setField(DATA) {
    try {
      const gl = this.gl, n = DATA.grid_n, F = DATA.times.length;
      const check = (arr) => { for (let i = 0; i < arr.length; i++) if (arr[i] === null || arr[i] === undefined || !isFinite(arr[i])) return false; return true; };
      for (let f = 0; f < F; f++)
        if (!check(DATA.u[f]) || !check(DATA.v[f])) return false;

      for (const w of this._windTex) { gl.deleteTexture(w); }
      this._windTex = [];
      const buf = new Uint8Array(n * n * 4);
      for (let f = 0; f < F; f++) {
        for (let r = 0; r < n; r++)          /* r: 0 = NORTH row (lats[0]) */
          for (let c = 0; c < n; c++) {
            const i = (r * n + c) * 4, g = r * n + c;
            const eu = Math.max(0, Math.min(65535,
                          Math.round((DATA.u[f][g] + 80) / WIND_ENC_RANGE * 65535)));
            const ev = Math.max(0, Math.min(65535,
                          Math.round((DATA.v[f][g] + 80) / WIND_ENC_RANGE * 65535)));
            buf[i] = eu >> 8; buf[i + 1] = eu & 255;
            buf[i + 2] = ev >> 8; buf[i + 3] = ev & 255;
          }
        const t = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, t);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, n, n, 0, gl.RGBA,
                      gl.UNSIGNED_BYTE, buf);
        this._texParams(t);
        this._windTex.push(t);
      }
      this._gridN = n;
      this.hasField = true;
      return true;
    } catch (e) {
      this.hasField = false;
      return false;
    }
  }

  resize(wCss, hCss, dpr) {
    if (!this.ok) return;
    const gl = this.gl;
    const w = Math.max(2, Math.round(wCss * dpr)), h = Math.max(2, Math.round(hCss * dpr));
    if (this.canvas.width !== w) this.canvas.width = w;
    if (this.canvas.height !== h) this.canvas.height = h;
    if (this._trail[0] && this._trail[0].w === w && this._trail[0].h === h) return;
    for (const t of this._trail) {
      if (t) { gl.deleteTexture(t.tex); gl.deleteFramebuffer(t.fbo); }
    }
    this._trail = [0, 1].map(() => {
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA,
                    gl.UNSIGNED_BYTE, null);
      this._texParams(tex);
      return { tex, fbo: this._fbo(tex), w, h };
    });
    this._trailIdx = 0;
  }

  clearTrails() {
    if (!this.ok || !this._trail[0]) return;
    const gl = this.gl;
    for (const t of this._trail) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, t.fbo);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  /* debug: decoded positions of the first k texels of the CURRENT
   * position texture (for automated advection verification) */
  readPos(k) {
    const gl = this.gl, out = [];
    gl.bindFramebuffer(gl.FRAMEBUFFER, this._pos[this._posIdx].fbo);
    const buf = new Uint8Array(k * 4);
    gl.readPixels(0, 0, 1, k, gl.RGBA, gl.UNSIGNED_BYTE, buf);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    for (let i = 0; i < k; i++)
      out.push([+(((buf[i * 4] * 256 + buf[i * 4 + 1]) / 65535).toFixed(4)),
                +(((buf[i * 4 + 2] * 256 + buf[i * 4 + 3]) / 65535).toFixed(4))]);
    return out;
  }

  /* view = {gx0, gy0, gx1, gy1, originX, originY, pxPerM, N, simRate}
   * (world-px grid box, viewport world origin, mercator constants) */
  step(dt, tt, view) {
    if (!this.ok || !this.hasField || this.failed) return;
    const gl = this.gl, cfg = this.config;
    try {
      /* adaptive quality (§11): if frames run slow, shed particles */
      this.frameTimes.push(dt);
      if (this.frameTimes.length >= 90) {
        const avg = this.frameTimes.reduce((a, b) => a + b, 0) / this.frameTimes.length;
        this.frameTimes = [];
        if (avg > 0.045 && cfg.count > 4000) {
          cfg.count = Math.max(4000, Math.round(cfg.count * 0.6));
          this._slowFrames++;
        }
      }
      this.time += dt;

      const F = this._windTex.length;
      const fA = Math.max(0, Math.min(F - 1, Math.floor(tt)));
      const fB = Math.min(fA + 1, F - 1);
      const mixv = Math.max(0, Math.min(1, tt - fA));
      const dbg = this.debugWind
        ? [1, this.debugWind.u, this.debugWind.v] : [0, 0, 0];
      const posR = this._pos[this._posIdx], posW = this._pos[1 - this._posIdx];

      /* 1 — update positions */
      gl.bindFramebuffer(gl.FRAMEBUFFER, posW.fbo);
      gl.viewport(0, 0, TEX, TEX);
      gl.disable(gl.BLEND);
      gl.useProgram(this._progQuad);
      this._quad(this._progQuad);
      const U = this._u[this._progQuad.__id];
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, posR.tex);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this._windTex[fA]);
      gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, this._windTex[fB]);
      gl.uniform1i(U.u_pos, 0); gl.uniform1i(U.u_windA, 1); gl.uniform1i(U.u_windB, 2);
      gl.uniform1f(U.u_mix, mixv);
      gl.uniform1f(U.u_dt, Math.min(dt, 0.05));
      gl.uniform1f(U.u_time, this.time);
      gl.uniform1f(U.u_dropRate, cfg.dropRate);
      gl.uniform1f(U.u_simRate, view.simRate);
      gl.uniform1f(U.u_speedScale, cfg.speedScale);
      gl.uniform4f(U.u_gridWorld, view.gx0, view.gy0, view.gx1, view.gy1);
      gl.uniform2f(U.u_geoScale, view.pxPerM, view.N);
      gl.uniform3f(U.u_debug, dbg[0], dbg[1], dbg[2]);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      this._posIdx = 1 - this._posIdx;
      if (this.debugGL) { const e = gl.getError(); if (e) this._dbg.push('update:' + e); }

      /* 2 — fade the trail texture */
      const trailR = this._trail[this._trailIdx], trailW = this._trail[1 - this._trailIdx];
      gl.bindFramebuffer(gl.FRAMEBUFFER, trailW.fbo);
      gl.viewport(0, 0, trailW.w, trailW.h);
      gl.useProgram(this._progFade);
      this._quad(this._progFade);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, trailR.tex);
      gl.uniform1i(this._u[this._progFade.__id].u_trail, 0);
      gl.uniform1f(this._u[this._progFade.__id].u_fade, cfg.fade);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      this._trailIdx = 1 - this._trailIdx;
      if (this.debugGL) { const e = gl.getError(); if (e) this._dbg.push('fade:' + e); }

      /* 3 — draw particles additively into the (just faded) trail */
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.useProgram(this._progDraw);
      const D = this._u[this._progDraw.__id];
      const loc = gl.getAttribLocation(this._progDraw, 'a_pos');
      gl.bindBuffer(gl.ARRAY_BUFFER, this._ptBuf);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, posW.tex);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this._windTex[fA]);
      gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, this._windTex[fB]);
      gl.uniform1i(D.u_pos, 0); gl.uniform1i(D.u_windA, 1); gl.uniform1i(D.u_windB, 2);
      gl.uniform1f(D.u_mix, mixv);
      gl.uniform1f(D.u_size, cfg.size);
      gl.uniform1f(D.u_count, cfg.count);
      gl.uniform1f(D.u_texSize, TEX);
      gl.uniform1f(D.u_dpr, view.dpr);
      gl.uniform1f(D.u_speedScale, cfg.speedScale);
      /* grid box on screen (CSS px): origin = world − viewport origin */
      gl.uniform4f(D.u_screenGrid,
        view.gx0 - view.originX, view.gy0 - view.originY,
        view.gx1 - view.gx0, view.gy1 - view.gy0);
      gl.uniform2f(D.u_canvas, this.canvas.width, this.canvas.height);
      gl.uniform3f(D.u_debug, dbg[0], dbg[1], dbg[2]);
      gl.uniform1f(D.u_alpha, cfg.alpha);
      if (this._palette) {
        const st = this._palette.slice(0, 7);
        while (st.length < 7) st.push(st[st.length - 1]);
        gl.uniform4fv(D.u_stops, new Float32Array(st.flat()));
      }
      gl.drawArrays(gl.POINTS, 0, TEX * TEX);
      if (this.debugGL) { const e = gl.getError(); if (e) this._dbg.push('points:' + e); }

      /* 4 — composite to the visible canvas */
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, this.canvas.width, this.canvas.height);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(this._progComp);
      this._quad(this._progComp);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, trailW.tex);
      gl.uniform1i(this._u[this._progComp.__id].u_trail, 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (this.debugGL) { const e = gl.getError(); if (e) this._dbg.push('composite:' + e); }
    } catch (e) {
      /* any GL failure → permanent CPU fallback, never a dead map */
      this.failed = true;
      if (this._onFail) this._onFail(e);
    }
  }

  get particleCount() { return this.config.count; }
}

window.WindGPU = WindGPU;
window.ORCA_WIND_ENC_RANGE = WIND_ENC_RANGE;   /* ±80 m/s (docs §10) */
})();
