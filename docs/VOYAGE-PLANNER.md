# VOYAGE PLANNER — research & design (SIH26176 / ORCA)

> "Ek poori machine jo skip ko 5 sawaal pooch ke — sach ke data se —
> bata de: kahan jao, kyon jao, kitna safe hai, kab niklo."
> Hamesha ka rule: **koi point, koi number, koi reason invent nahi.**
> Evidence aaya live network se; jo na mila uska naam + reason.

## 1. Kya sach me available hai (aaj, isi machine pe verify — 2026-09-09)

| Source | Aaj ka REAL output (live run) | Design use |
|---|---|---|
| **INCOIS PFZ** (govt daily advisory lines, GeoServer WFS `PFZ_Automation:pfzlines`) | Mumbai se 26.7 km: point 18.9772,72.5468 · sector *Maharashtra* · line 63.6 km · **advisory_date 2026-09-09** · `nearest_pfz()` + `get_lines()` existing | Official "kahan jao" candidates — govt ne aaj hi kaha hai wahan fish potential hai |
| **NOAA chl grid** (ERDDAP VIIRS DINEOF 9 km) | 54 pts grid, land-masked; hotspots: **8.5 mg/m³ (bloom) ** 86 NM NNE, 5.8 at 45 NM E… `_hotspots()` pure ranking existing | Independent satellite candidates + productivity evidence |
| **Open-Meteo marine forecast** (96 h) | per-point wave/swell/current/SST + wind/gust — transit verdict me already | Har candidate ka SAFETY gate (advisory thresholds) |
| **GLOBE 1 km mask** | 2-km sampling, detour real math | Selection ke baad verified route |
| **71 harbours DB (app, offline)** | nearest-harbour math existing | "वापस" mode |

Conclusion: **hamesha hota kuch hai** — chaar me se 2 sources fail to bhi
baaki 2 se recommendation banta hai; jo fail hua uska naam likha jayega.

## 2. Paanch flows (user ke exact words → design)

```
Q1: क्या करना है?
 ├─ 🎣 आगे — fishing   → Q2 (start) → Q3 (destination)
 │     Q3 options:
 │      a) "TU analyze kar" ⟶ VOYAGE ENGINE (reco cards)
 │      b) map pe tap → existing tap→target
 │      c) coords → existing
 └─ 🏝️ वापस — kinara/harbour → Q2 → 3 nearest harbours
      (offline DB) + NM + tap select → full route analysis

Q2: कहाँ SE?
 ├─ 📍 Live GPS  (destination side fetch = GPS fix)
 └─ ✍️ Coordinates (PLAN mode — honest pause of live alerts)

Q4 (implicit): रास्ता?  → GLOBE-verified legs (detour if land)
Q5 (implicit): safe?    → transit verdict (30-km sampling, worst-case fold)
```

Har selected target pe EXISTING chain fires automatically:
route-check → transit verdict → Route Analysis screen (rules + per-point
evidence) — recommendation = entry gate hi, analysis = same single truth.

## 3. VOYAGE ENGINE (backend `pipeline/voyage.py`)

**Candidates (REAL only, max ~8):**
1. N nearest UNIQUE PFZ lines (their nearest-point coordinates from the
   actual line geometry — koi ghisiya grid point nahi) · kind=`pfz`
2. Top chlorophyll hotspots (NOAA grid `_hotspots`, land-masked) · kind=`hotspot`

**Score (100 base, sab terms explainable, UI shows them as reasons):**

| Term | Delta | Reason text me |
|---|---|---|
| official daily PFZ | +20 | "INCOIS govt advisory (aaj ki date)" |
| chl ≥ 5 mg/m³ (bloom) | +10 | "satellite bloom 8.5 mg/m³ (fish food chain)" |
| wave now ≥4 m | −80🔴 | advisory threshold |
| gust 48h ≥34 kn | −60🔴 | WMO gale |
| wave 2.5–4 m | −40🟠 | small-craft caution |
| wind 48h ≥20 kn | −15🟠 | Beaufort-5 |
| distance | −0.15/NM | fuel+time honesty |

Final `state` = advisory point-state (good/caution/danger) — score kabhi
danger ko "green" nahi banata: safety gate alag, score sirf ranking.
Sort desc by score → top 5. Har card: reasons[] (jo add/sub hua uska
hissaab) + state dot + numbers.

**Failure honesty:** PFZ fail? note quote hota hai, hotspots se result.
Dono fail? `found:false` + dono reasons (app "retry" dikhata hai).
0 candidates ≠ 200-with-fake — found:false.

**Endpoint:** `GET /api/v1/voyage?lat&lon&max_km=120` — 30-min TTL cache,
per-candidate forecast same shared cache (coast par re-request = instant).

## 4. Stability fixes bundled in same drop
- Navigate target-view overflow (150px user-reported): body → scrollable
  ListView, HUD becomes shrink-wrapped grid — cards kitne bhi ho, kuch crop nahi
- advisory client timeout 35 s → 90 s (destination advisory; MOSDAC cap
  24 s + ERDDAP retry chain worst-case 60 s ke andar rahe)

## 5. Kya NAHI kar rahe (honest scope)
- Species prediction — scientific basis weak hota; hum fish-food-chain
  evidence tak hi bolenge
- Guaranteed catch claims — kabhi nahi ("potential" = advisory language)
- Road-style sea routing — not a real thing at sea; rhumb + detour = real
*Research record — Sangam Sitapuri team · 2026-09-09*
