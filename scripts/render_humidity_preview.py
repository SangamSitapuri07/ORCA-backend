#!/usr/bin/env python3
"""Render the ORCA humidity-map preview PNG (zoom.earth-style RH layer).

Data: LIVE DWD ICON global (Open-Meteo, models=icon_global) fetched
2026-09-13 for the default 9x9 grid around 22.2N 69.4E (span 3.0) — the
exact default response of GET /api/v1/humidity. The build sandbox cannot
reach api.open-meteo.com directly, so the wire payload's
relative_humidity_2m series are embedded below verbatim (81 locations,
8 forecast hours, 06:00-13:00 UTC). Values are untouched model output —
no smoothing, no fabrication. Location 25 was re-fetched as a single
point (it straddled a proxy chunk boundary); temperature/dew point are
omitted from the fixture for brevity (the live API returns them; the
map itself only needs RH).

Usage: python3 scripts/render_humidity_preview.py [out.png]
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pipeline.humidity import color_for_rh, get_humidity_field, legend  # noqa: E402

# ── live ICON fixture: location_id -> RH% at hours 0..7 (06:00-13:00 UTC) ──
RH = [
    [73, 69, 69, 68, 70, 74, 76, 79],  # 0   23.7N row (Rann edge / Kutch)
    [67, 65, 63, 63, 64, 66, 72, 76],  # 1
    [69, 63, 59, 56, 59, 64, 66, 70],  # 2
    [57, 53, 49, 45, 43, 44, 61, 67],  # 3
    [57, 52, 48, 44, 42, 41, 42, 71],  # 4
    [59, 54, 49, 45, 44, 45, 56, 73],  # 5
    [61, 57, 53, 51, 51, 51, 53, 55],  # 6
    [60, 57, 55, 53, 51, 52, 54, 60],  # 7
    [62, 59, 56, 55, 54, 55, 57, 66],  # 8
    [86, 85, 85, 86, 85, 86, 86, 87],  # 9   23.3N row (Gulf of Kutch W)
    [85, 85, 84, 85, 85, 85, 85, 86],  # 10
    [72, 70, 69, 69, 69, 73, 74, 77],  # 11
    [67, 63, 60, 59, 58, 61, 66, 73],  # 12
    [58, 54, 52, 51, 51, 53, 72, 73],  # 13
    [52, 48, 45, 45, 45, 47, 48, 64],  # 14  (Banni plains — driest)
    [56, 51, 49, 49, 50, 50, 52, 60],  # 15
    [63, 59, 57, 56, 55, 64, 70, 73],  # 16
    [67, 63, 60, 57, 56, 59, 72, 73],  # 17
    [85, 84, 85, 85, 84, 85, 85, 84],  # 18  23.0N row (Gulf W)
    [84, 84, 85, 85, 85, 85, 86, 85],  # 19
    [71, 69, 68, 68, 70, 71, 75, 78],  # 20
    [69, 68, 64, 65, 66, 69, 73, 80],  # 21
    [68, 63, 60, 59, 59, 63, 69, 75],  # 22
    [62, 58, 54, 52, 60, 67, 74, 75],  # 23
    [66, 60, 54, 61, 72, 74, 74, 74],  # 24
    [73, 69, 66, 68, 76, 76, 77, 80],  # 25  (single-point refetch)
    [72, 68, 65, 64, 67, 69, 71, 74],  # 26
    [84, 84, 84, 85, 85, 85, 85, 85],  # 27  22.6N row (Kutch S coast / sea)
    [83, 84, 85, 85, 85, 85, 85, 84],  # 28
    [84, 84, 84, 84, 84, 84, 84, 84],  # 29
    [84, 84, 84, 83, 83, 83, 83, 84],  # 30
    [83, 82, 84, 84, 83, 83, 84, 84],  # 31
    [83, 83, 84, 85, 83, 85, 84, 84],  # 32
    [76, 73, 70, 70, 74, 76, 76, 79],  # 33
    [73, 67, 70, 69, 70, 72, 72, 75],  # 34
    [74, 70, 67, 70, 72, 71, 72, 73],  # 35
    [83, 83, 83, 84, 85, 84, 84, 85],  # 36  22.2N row (centre row)
    [85, 84, 84, 83, 83, 84, 83, 83],  # 37
    [87, 84, 84, 84, 84, 84, 84, 84],  # 38
    [73, 72, 73, 75, 75, 75, 76, 79],  # 39
    [65, 63, 65, 65, 64, 67, 69, 70],  # 40  (near requested centre 22.2/69.4)
    [62, 61, 63, 64, 66, 69, 71, 75],  # 41
    [71, 67, 65, 68, 71, 73, 74, 78],  # 42
    [83, 74, 71, 72, 73, 73, 76, 79],  # 43
    [84, 80, 75, 70, 72, 71, 71, 78],  # 44
    [86, 85, 85, 85, 82, 81, 80, 81],  # 45  21.9N row (sea W)
    [86, 86, 85, 85, 85, 82, 81, 82],  # 46
    [84, 84, 83, 83, 83, 84, 82, 81],  # 47
    [85, 83, 83, 83, 83, 83, 83, 83],  # 48
    [71, 68, 69, 76, 75, 76, 77, 79],  # 49
    [68, 62, 62, 61, 64, 70, 76, 80],  # 50
    [78, 73, 69, 62, 62, 68, 73, 75],  # 51
    [86, 82, 83, 81, 77, 75, 78, 81],  # 52
    [84, 82, 84, 84, 86, 89, 90, 91],  # 53
    [86, 85, 82, 85, 84, 81, 80, 82],  # 54  21.5N row
    [86, 85, 85, 81, 80, 80, 79, 79],  # 55
    [83, 84, 83, 81, 81, 80, 80, 79],  # 56
    [82, 83, 84, 82, 82, 80, 80, 80],  # 57
    [84, 83, 83, 84, 83, 82, 81, 81],  # 58
    [79, 75, 78, 77, 80, 81, 82, 84],  # 59
    [84, 83, 80, 79, 79, 80, 81, 83],  # 60
    [89, 86, 89, 89, 91, 92, 90, 90],  # 61
    [85, 82, 83, 89, 93, 94, 94, 92],  # 62
    [83, 83, 82, 83, 82, 85, 83, 82],  # 63  21.1N row
    [84, 85, 83, 82, 83, 81, 83, 80],  # 64
    [82, 83, 84, 83, 83, 82, 81, 81],  # 65
    [84, 83, 83, 84, 84, 84, 83, 82],  # 66
    [84, 84, 83, 84, 84, 83, 83, 85],  # 67
    [83, 87, 85, 86, 86, 85, 86, 85],  # 68
    [83, 86, 89, 88, 89, 89, 90, 92],  # 69
    [89, 89, 92, 88, 90, 93, 95, 96],  # 70  (Gir foothills — most humid +6h)
    [86, 85, 86, 87, 87, 89, 94, 97],  # 71
    [83, 82, 83, 85, 85, 84, 81, 81],  # 72  20.7N row (Saurashtra S)
    [82, 83, 83, 81, 82, 85, 85, 83],  # 73
    [81, 81, 84, 85, 81, 81, 81, 80],  # 74
    [81, 80, 80, 81, 82, 80, 81, 81],  # 75
    [80, 81, 81, 80, 81, 84, 82, 78],  # 76
    [83, 88, 86, 84, 83, 83, 83, 83],  # 77
    [83, 84, 87, 88, 82, 81, 81, 84],  # 78
    [83, 81, 86, 91, 91, 89, 87, 91],  # 79
    [89, 85, 81, 83, 86, 83, 91, 91],  # 80
]

TIMES = [f"2026-09-13T{h:02d}:00" for h in range(6, 14)]


def _rows(pairs, hours_ahead):  # Open-Meteo wire shape (RH-only fixture)
    return [{"hourly": {"time": TIMES, "relative_humidity_2m": RH[i]}}
            for i in range(len(pairs))]


def main() -> None:
    assert len(RH) == 81 and all(len(a) == 8 and all(0 <= v <= 100 for v in a) for a in RH), \
        "fixture must be 81 locations x 8 hourly values"

    # preview runs offline — GLOBE landmask unavailable here -> honest None
    import pipeline.landmask as lm
    lm.is_land = lambda lat, lon: None

    res_now = get_humidity_field(22.2, 69.4, 3.0, hours_ahead=0, grid_n=9, _fetcher=_rows)
    res_6h = get_humidity_field(22.2, 69.4, 3.0, hours_ahead=6, grid_n=9, _fetcher=_rows)
    for r in (res_now, res_6h):
        assert r.get("error") is None, r["error"]
        assert all(p["rh_pct"] is not None for p in r["points"]), "fixture hole"

    render(res_now, res_6h)


# ─────────────────────────────────────────────────────────── rendering ──
SZ = 560   # panel size in px

FDIR = "/usr/share/fonts/truetype/dejavu/"


def font(sz: int, bold: bool = False):
    from PIL import ImageFont
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(FDIR + name, sz)


def _hx(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _ist(iso: str) -> str:
    t = datetime.fromisoformat(iso) + timedelta(hours=5, minutes=30)
    return t.strftime("%H:%M") + " IST"


def _panel(draw, img, res, px: int, py: int, caption: str) -> None:
    from PIL import Image
    import math

    # box derived from the response itself: points[0]=NW, points[-1]=SE
    # (span is the FULL width: span 3 -> 3 deg x 3 deg centred on request)
    p0, p1 = res["points"][0], res["points"][-1]
    lat_top, lat_bot = p0["lat"], p1["lat"]
    lon_l, lon_r = p0["lon"], p1["lon"]

    draw.text((px, py - 30), caption, font=font(19, bold=True),
              fill=(255, 255, 255), stroke_width=1, stroke_fill=(10, 20, 30))

    n = res["grid_n"]
    field = Image.new("RGB", (n, n))
    field.putdata([_hx(p["color"]) for p in res["points"]])
    # Grid point i must land at display x = i*(SZ/(n-1)). A plain resize to
    # SZ puts source pixel CENTERS at (i+0.5)*cell, half a cell off — so
    # resize with cell = SZ/(n-1) and paste offset by half a cell; the
    # outer half-cells clip outside the panel (data does not exist there).
    cell = SZ / (n - 1)
    big = field.resize((round(n * cell), round(n * cell)), Image.BILINEAR)
    img.paste(big, (px - round(cell / 2), py - round(cell / 2)))
    draw.rectangle((px, py, px + SZ - 1, py + SZ - 1),
                   outline=(120, 145, 170), width=2)

    def xy(lon, lat):
        return (px + (lon - lon_l) / (lon_r - lon_l) * SZ,
                py + (lat_top - lat) / (lat_top - lat_bot) * SZ)

    # graticule every 1 degree, inside the box only
    for lon in range(math.ceil(lon_l), math.floor(lon_r) + 1):
        x, _ = xy(lon, 0)
        draw.line((x, py, x, py + SZ), fill=(255, 255, 255), width=1)
        draw.text((x + 3, py + SZ - 18), f"{lon}E", font=font(12),
                  fill=(255, 255, 255), stroke_width=2, stroke_fill=(20, 30, 40))
    for lat in range(math.ceil(lat_bot), math.floor(lat_top) + 1):
        _, y = xy(0, lat)
        draw.line((px, y, px + SZ, y), fill=(255, 255, 255), width=1)
        draw.text((px + 4, y + 2), f"{lat}N", font=font(12),
                  fill=(255, 255, 255), stroke_width=2, stroke_fill=(20, 30, 40))

    # geography anchors (approx. city positions, for orientation only)
    for name, la, lo in [("Bhuj", 23.24, 69.67), ("Dwarka", 22.24, 68.97),
                         ("Jamnagar", 22.47, 70.06), ("Rajkot", 22.30, 70.80),
                         ("Porbandar", 21.64, 69.61)]:
        x, y = xy(lo, la)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 255, 255),
                     outline=(20, 30, 40), width=1)
        tx = x + 6
        if tx + 60 > px + SZ:  # keep the label inside the panel
            tx = x - 8 - draw.textlength(name, font=font(12))
        draw.text((tx, y - 8), name, font=font(12), fill=(255, 255, 255),
                  stroke_width=2, stroke_fill=(20, 30, 40))
    for name, la, lo in [("RANN OF KACHCHH", 23.45, 68.30),
                         ("ARABIAN SEA", 20.90, 68.00)]:
        x, y = xy(lo, la)
        draw.text((x, y), name, font=font(12), fill=(235, 240, 245),
                  stroke_width=2, stroke_fill=(30, 40, 50))

    # requested centre of the request (22.2N 69.4E for this preview)
    cx, cy = xy(res["center"]["lon"], res["center"]["lat"])
    draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), outline=(255, 255, 255), width=2)


def render(res_now: dict, res_6h: dict) -> None:
    from PIL import Image, ImageDraw

    W, H = 1240, 880
    img = Image.new("RGB", (W, H), (15, 25, 35))
    d = ImageDraw.Draw(img)

    s = res_now["summary"]
    d.text((50, 24), "ORCA Humidity Map — Kutch & Saurashtra",
           font=font(30, bold=True), fill=(255, 255, 255))
    d.text((50, 64), "2 m relative humidity · DWD ICON global (~11 km) via Open-Meteo "
                     f"· centre 22.2°N 69.4°E · 3°×3° box · 9×9 grid · "
                     f"now RH {s['rh_min']:.0f}–{s['rh_max']:.0f} % (mean {s['rh_mean']:.0f} %)",
           font=font(16), fill=(170, 190, 210))

    _panel(d, img, res_now, 50, 140,
           f"NOW · {_ist(res_now['valid_time'])} ({res_now['valid_time'][11:16]} UTC)")
    _panel(d, img, res_6h, 630, 140,
           f"+6 HOURS · {_ist(res_6h['valid_time'])} ({res_6h['valid_time'][11:16]} UTC)")

    # legend bar
    lx, ly, lw, lh = 220, 760, 800, 22
    d.text((lx, ly - 26), "Relative humidity at 2 m above ground (%)",
           font=font(15), fill=(200, 215, 230))
    for i in range(lw):
        d.line((lx + i, ly, lx + i, ly + lh), fill=_hx(color_for_rh(i / (lw - 1) * 100)))
    d.rectangle((lx, ly, lx + lw - 1, ly + lh), outline=(120, 145, 170), width=1)
    for stop in legend():
        x = lx + stop["value"] / 100 * (lw - 1)
        d.line((x, ly + lh, x, ly + lh + 5), fill=(220, 230, 240))
        d.text((x - 8, ly + lh + 8), f"{stop['value']}", font=font(13), fill=(220, 230, 240))

    d.text((50, H - 34),
           "Live ICON run of 13 Sep 2026, hours 0–7 · dry Rann interior vs moist "
           "Arabian Sea and Saurashtra coast · same data as zoom.earth's humidity layer, "
           "served by GET /api/v1/humidity",
           font=font(13), fill=(150, 170, 190))

    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "humidity_preview_kutch.png")
    img.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
