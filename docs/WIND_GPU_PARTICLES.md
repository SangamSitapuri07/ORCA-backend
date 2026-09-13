# ORCA GPU Wind Particles (WebGL) — architecture & data contract

Implements spec §7 (zoom-earth-style wind visualisation), §10 (GPU/texture
architecture), §11 (configurable particle engine), §12 (speed colour ramp)
on top of the existing ORCA weather grid.

## Data flow

```
backend  /api/v1/weather/grid          (real DWD ICON field via Open-Meteo;
  u/v in m/s, meteorological FROM-decomposition: u = −spd·sinθ, v = −spd·cosθ)
    ↓  one RGBA8 texture per forecast frame (n×n grid)
GPU wind textures (hardware bilinear filtering = the CPU sampler's
    interpolation, no resolution invented — §8/§46)
    ↓
vertex/fragment shaders advect 4k–30k particles per frame (ping-pong
    position texture), trails via a fading screen texture
    ↓
#particlesGL canvas (WebGL) over the Leaflet map
```

No per-particle requests are made (§10): the whole field is uploaded once
per data load as ≤8 small textures; the timeline blend is a shader mix
between two frame textures.

## Texture encodings (no silent precision loss)

**Wind texture** — one per forecast frame, `RGBA8`, `n×n` texels
(row 0 = northernmost latitude, `LINEAR` filtering):

| channel | content |
|---------|---------|
| R, G    | u (m/s), 16-bit big-endian split |
| B, A    | v (m/s), 16-bit big-endian split |

```
u = (R·256 + G) / 65535 · 160 − 80   m/s     range ±80 m/s
v = (B·256 + A) / 65535 · 160 − 80   m/s
```

Quantisation: 160/65535 ≈ **0.0024 m/s** — three orders of magnitude
finer than the source model's own precision.

**Position texture** — ping-pong pair, `RGBA8`, 256×256 (65,536 slots):

```
x = (R·256 + G)/65535,  y = (B·256 + A)/65535   in grid-normalised [0,1]²
```

Quantisation: 1/65535 of the grid box ≈ 0.02 px on a 1400 px box.
Positions are grid-normalised, so they are zoom-invariant; the per-frame
screen transform comes from uniforms.

Zero WebGL extensions are required (plain RGBA8 render targets), so the
engine runs anywhere WebGL 1 runs.

## Advection (identical formula to the Canvas-2D engine)

```
dx_world = u · SIM_RATE · dt · pxPerM
dy_world = −v · SIM_RATE · dt · pxPerM / cos φ      (Web-Mercator correction)
```

with the same `SIM_RATE = 20000` sim-seconds per real-second and the same
6 px per-frame jump cap as the CPU path — the two engines are visually
equivalent; the GPU one just draws 10–30× more particles. The timeline
value `t` selects frames `fA = floor(t)`, `fB = fA+1` (both clamped) and
blends with `mix = t − fA` — **decoded values** are mixed, never the raw
bytes. Interpolation is a visualisation technique; it does not create new
observations (§15).

## Colour ramp

Particle colour = `|(u,v)|·3.6` in **km/h**, mapped through the map's
`WIND_KMH` palette (passed in by the page from its single definition —
one source of truth). The unit is stated in the legend and never switched
silently (§12).

## Configuration (rendering defaults, NOT scientific values — §11)

`windGPU.config`:

| key | default | meaning |
|-----|---------|---------|
| count | 30000 desktop / 9000 touch | active particles (auto-sheds if a frame averages >45 ms, floor 4000) |
| size | 1.5 | point size, CSS px |
| fade | 0.94 | trail decay per frame |
| alpha | 0.42 | particle opacity |
| dropRate | 0.006 | random respawn probability |
| speedScale | 1.0 | animation-speed multiplier (UI: ×½ / ×1 / ×2) |

## Honesty & fallback rules

* If the field contains **any missing u/v cell** the engine refuses it
  (`setField → false`): missing data is never rendered as calm wind (§26).
  The page keeps the CPU engine, which respawns particles on nulls.
* If WebGL is unavailable, or the GL context errors at runtime, the page
  falls back to the Canvas-2D engine automatically (`failed` latch) and
  says so in the status panel — never a dead map (§47).
* `windGPU.debugWind = {u, v}` (m/s) overrides the field for automated
  direction verification only; it is never set in normal operation.

## Verification performed (2026-09-13, headless SwiftShader)

* engine initialised, 30k particles stepped, `gl.getError()` clean;
* particles MOVE between frames (frame-diff > 0);
* **direction proof**: with `debugWind` forced to (8, 0) m/s the bright-
  pixel centroid moved east; with (0, 8) m/s it moved north — advection
  follows the wind vectors, not random motion;
* CPU fallback path verified (GPU checkbox off → Canvas-2D particles);
* zero page errors in all runs.
