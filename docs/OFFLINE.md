# ORCA Offline & Emergency Architecture (100% real — no fakes)

**Question:** "samundar mein internet nahi toh kaise contact karein?"
**Answer:** first, the honest physics — then what ORCA actually ships.

## The physics (judge-proof)

| Signal | Reaches how far offshore | What works on it |
|---|---|---|
| GPS satellites | unlimited (needs open sky, NOT internet) | position, speed, heading — the phone listens to satellites directly, towers not involved |
| GSM **voice + SMS** (2G signalling) | ~15–30 km from coastal towers, depends on tower location/antenna height | phone calls, SMS text |
| 4G data | less than voice in practice (data sessions die first) | ORCA satellite/API data |
| VHF marine radio (Ch 16) | ~30–50 km ship-to-coast, more ship-to-ship | the REAL distress channel at sea (it's on the boat's radio, not the phone) |
| Satellite messenger (inReach etc.) | pole-to-pole | requires dedicated hardware — a plain smartphone cannot do this, and ORCA will never pretend it can |

## What ORCA ships for the zero-internet case

1. **Everything GPS keeps working offline** — live blue dot, trip trace,
   course guidance, ETA — because GPS never needed internet. (Turn-by-turn
   "routing" doesn't exist at sea; guidance is a course line, like every
   real chartplotter.)
2. **🆘 SOS panel (opens with zero network)** — fully client-side:
   - **big live position readout** (deg, accuracy, UTC time)
   - **📞 Coast Guard 1554** one-tap dial (`tel:` — real distress number)
   - **personal emergency contact** (saved on device) with one-tap **call**
     and **SMS-position** (`sms:` URI, body prefilled: position, accuracy,
     time, speed) — SMS rides GSM signalling and gets through at far
     worse signal than data
   - **nearest 3 of 71 real Indian fishing harbours** (list compiled into
     the JS bundle — no fetch) with distance NM, course° and ETA from the
     phone's live GPS speed; every harbour sanity-checked against the
     GLOBE 1 km land mask
   - **VHF Channel 16** guidance
   - honest offline badge whenever the network drops
3. **Offline maps** — the service worker caches OSM/OpenSeaMap map tiles
   and the app shell while online (cache-first for tiles, capped ~1800).
   **API data is NEVER cached** — stale marine data presented as fresh is
   exactly the dishonesty ORCA exists to fight; offline mode shows
   last-known values with their real timestamps plus an explicit
   OFFLINE badge.
4. **PWA manifest** — the app installs on the phone home screen and
   relaunches fast.

## What we deliberately did NOT build (and why)

- **Fake "satellite SOS"** — phones can't talk to satellites for messaging
  without dedicated hardware. Pretending otherwise at sea is dangerous.
- **Caching `/api/*` answers** — see above; honesty beats convenience.
- **Mesh/Bluetooth boat-to-boat relay** — not possible from a web app
  (browser APIs don't allow background mesh). A native-app Phase-2 idea.

## Phase-2 (documented, not built): SMS shore-bridge

Fisher sends an SMS like `ORCA 19.5 70.8` → shore server with a GSM
gateway replies with a compressed advisory packet (verdict, wave peak,
hotspot bearing). This is a REAL pattern used in developing regions —
but in India it needs SMS-aggregator + DLT registration (TRAI
regulations), so it's post-hackathon work, stated honestly in the pitch.
