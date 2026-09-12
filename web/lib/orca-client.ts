// ORCA API client — talks to FastAPI through same-origin `/api` URLs by
// default. The Next.js server proxies those calls to ORCA_BACKEND_URL, so
// browser code never embeds a deployment address. NEXT_PUBLIC_ORCA_API_URL and
// NEXT_PUBLIC_ORCA_WS_URL are optional explicit overrides for deployments that
// intentionally expose FastAPI directly.

export interface ZoneSnapshot {
  lat: number;
  lon: number;
  date: string;
  fetched_at?: string;
  sst_max?: number;
  sst_min?: number;
  sst_mean?: number;
  wave_max?: number;
  wave_mean?: number;
  chlorophyll?: number;
  chlorophyll_unit?: string;
  chlorophyll_source?: string;
  chlorophyll_date?: string;
  fishing_hours?: number;
  vessel_count?: number;
  fleet_by_flag?: Record<string, number>;
  fleet_by_gear?: Record<string, number>;
  fishing_window_start?: string;
  fishing_window_end?: string;
  fishing_bbox_radius_deg?: number;
  data_sources_used?: string[];
  data_sources_failed?: string[];
}

export interface AgentFinding {
  type: string;
  severity: string;
  value?: any;
  msg: string;
}

export interface AgentResult {
  agent: string;
  agent_id?: string;
  findings: AgentFinding[];
  summary: string;
  recommendation?: string;
  risk_level: string;
  verdict?: string;
  risk_score?: number;
  status?: string;
  duration_ms?: number;
  execution_class?: string;
  llm_attempted?: boolean;
  llm_invoked?: boolean;
  llm_model?: string;
  llm_interpretation?: string | null;
  rag_invoked?: boolean;
}

export interface OrcaInsight {
  zone: { lat: number; lon: number; date: string };
  agents: AgentResult[];
  overall_risk: string;
  summary: string;
  recommendation: string;
  data_sources_used: string[];
  data_sources_failed: string[];
  data_coverage?: { known: number; total: number; sources_failed: number };
  fetched_at: string;
}

export interface DemoZone {
  name: string;
  lat: number;
  lon: number;
}

// Coastal starting coordinates for provider queries. A request attempts the
// configured adapters, but providers may return no data or fail; the response
// reports those outcomes rather than promising a live value.
export const INDIAN_COASTAL_ZONES: DemoZone[] = [
  { name: "Mumbai offshore",      lat: 19.0, lon: 72.8 },
  { name: "Goa offshore",         lat: 15.5, lon: 73.7 },
  { name: "Cochin offshore",      lat:  9.5, lon: 76.0 },
  { name: "Chennai offshore",     lat: 13.5, lon: 80.5 },
  { name: "Visakhapatnam",        lat: 17.5, lon: 83.5 },
  { name: "Kandla/Gujarat",       lat: 22.5, lon: 68.5 },
  { name: "Andaman (Port Blair)", lat: 12.0, lon: 92.5 },
  { name: "Lakshadweep",          lat: 10.5, lon: 72.5 },
];

// Offshore starting point west of Veraval; the bundled GLOBE mask classifies
// 20.90 N, 70.30 E as water (the harbour reference at 70.37 E is land).
export const DEFAULT_ZONE: DemoZone = { name: "Offshore Veraval/Gujarat", lat: 20.9, lon: 70.30 };

// ── Advisory ──────────────────────────────────────────────────────

export interface AdvisoryReason {
  severity: "info" | "caution" | "no_go" | "unknown";
  code: string;
  msg: string;
}

export interface Advisory {
  type: "advisory";
  lat: number;
  lon: number;
  verdict: "go" | "caution" | "no_go" | "unknown";
  icon: string;
  color: string;
  headline: string;
  headline_en: string;
  headline_hi: string;
  reasons: AdvisoryReason[];
  variables: {
    wave_height_m?: number | null;
    swell_m?: number | null;
    wind_kts?: number | null;
    gust_kts?: number | null;
    sst_c?: number | null;
    sst_source?: string | null;
    current_kn?: number | null;
    current_dir?: string | null;
    chlorophyll_mg_m3?: number | null;
    cyclone_dist_km?: number | null;
    cyclone_note?: string | null;
    nearest_pfz_km?: number | null;
    nearest_pfz_nm?: number | null;
    nearest_pfz_bearing?: string | null;
    pfz_advisory_date?: string | null;
  };
  outlook_48h?: Record<string, number | null>;
  /** Downsampled hourly forecast (next 48h, every ~3h) — same arrays the
      verdict uses, rendered as sparklines. */
  hourly_chart?: {
    labels: string[];
    wave_m: (number | null)[];
    swell_m?: (number | null)[];
    wind_kn: (number | null)[];
    gust_kn: (number | null)[];
    current_kn?: (number | null)[];
    sst_c?: (number | null)[];
    rain_mm: (number | null)[];
  } | null;
  /** Plain-language lines a non-technical reader can act on. */
  plain_en?: string[];
  plain_hi?: string[];
  safe_window: { found: boolean; from_utc?: string; to_utc?: string; hours?: number; note?: string };
  sources: string[];
  sources_failed: string[];
  generated_at: string;
  valid_until: string;
  disclaimer: string;
}

// ── Alerts ────────────────────────────────────────────────────────

export interface AlertEvaluation {
  sources_used: string[];
  sources_failed: string[];
  checked_at: string;
}

export interface AlertsResponse {
  alerts: OrcaAlert[];
  count: number;
  newly_evaluated: OrcaAlert[];
  evaluation: AlertEvaluation | null;
}

export interface OrcaAlert {
  id: string;
  code: string;
  severity: "watch" | "warning";
  simulated: boolean;
  title_en: string;
  title_hi: string;
  msg_en: string;
  lat: number;
  lon: number;
  issued_at: string;
  valid_until: string;
  source: string;
  cyclone?: { name?: string; max_wind_kt?: number; intensity?: string };
  distance_km?: number;
}

// ── Chat ──────────────────────────────────────────────────────────

export interface ChatStep {
  agent: string;
  tool: string;
  args: Record<string, any>;
  summary: string;
}

export interface ChatFinal {
  answer: string;
  advisory: Advisory;
  layers: string[];
  routing: { intents: string[]; agents: string[]; tools: string[] };
  sources: string[];
  lang: string;
  steps?: ChatStep[];
}

// ── Fetch helpers ─────────────────────────────────────────────────
//
// Browser requests stay same-origin unless an operator deliberately injects
// a public API URL at build time. The default `/api` path is proxied by Next.js
// using the server-only ORCA_BACKEND_URL value.

const API_BASE = (process.env.NEXT_PUBLIC_ORCA_API_URL ?? "").replace(/\/$/, "");

/** Base used for first-party binary tile requests. */
export function tileCandidateBases(): string[] {
  return [API_BASE];
}

async function apiFetch(path: string, init: RequestInit): Promise<Response> {
  return fetch(API_BASE + path, { cache: "no-store", ...init });
}

/** First-party binary fetch (tiles). The blob result is turned into an object URL,
 *  so canvases reading it are never tainted (CORS disappears). */
export async function apiFetchBlob(path: string): Promise<Blob> {
  const res = await apiFetch(path, {});
  if (!res.ok) throw new Error(apiErrorMessage(res.status, await res.text()));
  return res.blob();
}

/** Hemisphere-aware coordinate labels (N/S, E/W) — a point south of the
 *  equator must never be labelled "°N". */
export const fmtLat = (lat: number): string => `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}`;
export const fmtLon = (lon: number): string => `${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;

/** Turn a non-OK response into a human-readable error. FastAPI error
 * bodies are JSON {"detail": "..."} — surface the DETAIL (it carries our
 * honest 504 retry hint: "still computing in background, retry in 10-30s
 * — answer comes instantly from cache"), not raw JSON braces. */
function apiErrorMessage(status: number, body: string): string {
  try {
    const j = JSON.parse(body);
    if (typeof j?.detail === "string") return `API ${status}: ${j.detail.slice(0, 500)}`;
  } catch { /* not JSON — bare text (e.g. proxy 500) */ }
  return `API ${status}: ${body.slice(0, 300)}`;
}

async function apiGet<T>(path: string, timeoutMs = 125_000): Promise<T> {
  // 125 s — MUST stay above the backend's own 110 s deadline: a slow first
  // fetch (MOSDAC 60 MB granule download + slow public APIs on a home
  // link) legitimately needs ~100 s. At 90 s the frontend used to give up
  // JUST before the backend finished, then showed a fake "unreachable"
  // card while the backend completed the work into cache. Seen live on
  // the laptop at Visakhapatnam (2026-09-04).
  const res = await apiFetch(path, {
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(apiErrorMessage(res.status, body));
  }
  return res.json();
}

async function apiPost<T>(path: string, body: unknown, timeoutMs = 220_000): Promise<T> {
  const res = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(apiErrorMessage(res.status, text));
  }
  return res.json();
}

// ── GFW deep-data switch (tri-state) ──────────────────────────────
// localStorage "orca.gfwDeep": "1" = force ON, "0" = force OFF,
// unset = AUTO — the backend decides from its .env: token present →
// real fishing data even on map clicks; no token → stays fast.
// (Needs GFW_API_TOKEN in the backend .env.)

export function gfwDeepParam(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const v = localStorage.getItem("orca.gfwDeep");
    return v === "1" ? "true" : v === "0" ? "false" : null;
  } catch { return null; }
}

export function gfwDeepStored(): boolean | null {
  const p = gfwDeepParam();
  return p === "true" ? true : p === "false" ? false : null;
}

export function setGfwDeep(v: boolean | null): void {
  try {
    if (v === null) localStorage.removeItem("orca.gfwDeep");
    else localStorage.setItem("orca.gfwDeep", v ? "1" : "0");
  } catch { /* private mode */ }
}

function gfwQuery(): string {
  const p = gfwDeepParam();
  return p === null ? "" : `&include_gfw=${p}`; // omit → backend AUTO
}

export const fetchInsight = (lat: number, lon: number, date?: string) =>
  apiGet<OrcaInsight>(
    `/api/v1/reason?lat=${lat}&lon=${lon}${date ? `&date=${date}` : ""}${gfwQuery()}`,
    220_000
  );

export const fetchAdvisory = (lat: number, lon: number) =>
  apiGet<Advisory>(`/api/v1/advisory?lat=${lat}&lon=${lon}${gfwQuery()}`, 120_000);

// ── Field Explorer (real sampled grid spots) ────────────────────────

export interface FieldPoint {
  lat: number; lon: number;
  observed_at?: string | null;
  chl?: number; wave_m?: number | null; swell_m?: number | null;
  current_kn?: number | null; current_dir_deg?: number | null;
  sst_c?: number | null;
  wind_kn?: number | null; wind_dir_deg?: number | null;
  gust_kn?: number | null;
}
export interface FieldResponse {
  type: "field";
  center: { lat: number; lon: number };
  radius_deg: number;
  chl: { points: FieldPoint[]; date?: string; n: number; source?: string; error?: string | null; land_masked?: number; land_mask?: string };
  met: { points: FieldPoint[]; n: number; source?: string; error?: string | null };
  hotspots: {
    lat: number; lon: number; chl: number;
    distance_km: number; distance_nm: number; bearing: string;
    /** Above the map's high-chlorophyll display threshold; not a HAB diagnosis. */
    bloom?: boolean;
    /** km to nearest land (8-ray probe on the real GLOBE 1 km mask) */
    coast_km?: number | null;
    /** honest turbidity note when a bloom sits within a short sail of land */
    caveat?: string | null;
  }[];
  generated_at: string;
  note: string;
}

export const fetchField = (lat: number, lon: number) =>
  apiGet<FieldResponse>(`/api/v1/field?lat=${lat}&lon=${lon}`, 90_000);

/* ── sea-route check (local math vs the real GLOBE 1 km land mask) ── */
export interface RouteCheckResponse {
  from: [number, number];
  to: [number, number];
  distance_km: number;
  distance_nm: number;
  bearing_deg: number;
  sample_step_km: number;
  method: string;
  /** true = water-only (detour maybe inserted); false = blocked;
   *  null = UNVERIFIED (land mask unavailable — never say "safe") */
  ok: boolean | null;
  detour: boolean;
  legs: [number, number][];
  /** sea-path engine fired: the direct line crossed land and a verified
      multi-waypoint ocean path was computed around it (A* over the
      pooled GLOBE mask, legs re-proven at native 1 km) */
  rerouted?: boolean;
  /** middle vertices of `legs` when rerouted (the "via" points) */
  waypoints?: [number, number][];
  /** distances of the blocked direct line, kept for honest comparison */
  straight_distance_km?: number;
  straight_distance_nm?: number;
  land_hit?: { lat: number; lon: number; sail_km: number };
  reason: string;
}
export const fetchRouteCheck = (fromLat: number, fromLon: number, toLat: number, toLon: number) =>
  apiGet<RouteCheckResponse>(
    `/api/v1/route-check?from_lat=${fromLat}&from_lon=${fromLon}&to_lat=${toLat}&to_lon=${toLon}`,
    20_000);

/* ── whole-route advisory (per-point marine weather, worst-case fold) ── */

/** State of ONE sampled point — "good" (not "go") matches the backend
 *  _point_state vocabulary; the ROUTE verdict folds these into go|nogo. */
export type PointState = "good" | "caution" | "danger" | "unknown";

export interface RouteAdvisoryPoint {
  lat: number;
  lon: number;
  /** km sailed along the course up to this point */
  sail_km: number;
  /** start/end (and any detour corner) marker */
  vertex?: boolean;
  state: PointState;
  wave_m?: number | null;
  wave_48h_max_m?: number | null;
  wind_kn?: number | null;
  wind_48h_max_kn?: number | null;
  gust_48h_max_kn?: number | null;
  current_kn?: number | null;
  sst_c?: number | null;
  /** set on caution/danger — the exact numbers that tripped a rule */
  why?: string;
  /** informational (strong current / fetch failed / no values) */
  note?: string;
}

export interface RouteAdvisory {
  from: [number, number];
  to: [number, number];
  legs: [number, number][];
  detour: boolean;
  /** sea-path reroute info (see RouteCheckResponse) */
  rerouted?: boolean;
  waypoints?: [number, number][];
  straight_distance_km?: number;
  straight_distance_nm?: number;
  distance_km: number;
  distance_nm: number;
  bearing_deg: number;
  /** true = verified water-only · false = BLOCKED by land ·
   *  null = land mask unavailable (must NEVER be shown as "safe") */
  land_ok: boolean | null;
  land_reason?: string;
  land_hit?: { lat: number; lon: number; sail_km: number } | null;
  points: RouteAdvisoryPoint[];
  verdict: {
    level: "go" | "caution" | "nogo" | "unknown";
    points_known: number;
    points_total: number;
    land_verified: boolean | null;
  };
  safe_window_at_start?: {
    found: boolean;
    from_utc?: string;
    to_utc?: string;
    hours?: number;
    note?: string;
  } | null;
  sources_used?: string[];
  sources_failed?: string[];
  sample_spacing_km?: number;
  method?: string;
  fetched_at?: string;
}

export const fetchRouteAdvisory = (fromLat: number, fromLon: number, toLat: number, toLon: number) =>
  apiGet<RouteAdvisory>(
    `/api/v1/route-advisory?from_lat=${fromLat}&from_lon=${fromLon}&to_lat=${toLat}&to_lon=${toLon}`,
    95_000 /* cold compute = land verify + ~5 parallel live forecasts, can take ~60 s */);

/* ── voyage planner: "TU analyze kar — kahan jaun?" ── */

export interface CrowdInfo {
  /** "low|moderate|high" = measured crowd pressure, "unknown" = honest no-data */
  level: "low" | "moderate" | "high" | "unknown";
  /** ORCA fishers already sent to this 0.25° cell in the last 24 h (anonymous) */
  community_recent: number;
  /** same-cell + 0.5×neighbour spill-over load */
  community_load: number;
  community_penalty: number;
  /** REAL GFW AIS fleet hours within ~50 km over last 30 days (top-3 only) */
  gfw_hours_30d?: number | null;
  gfw_penalty: number;
  /** honest note when GFW fleet check failed — no penalty silently added */
  note?: string | null;
}

export interface VoyageReco {
  lat: number;
  lon: number;
  /** Nearest point on an official INCOIS PFZ advisory line. */
  kind: "pfz";
  name: string;
  chl?: number | null;
  distance_nm: number;
  bearing_deg: number;
  state: PointState;
  wave_m?: number | null;
  wind_kn?: number | null;
  sst_c?: number | null;
  why?: string | null;
  score: number;
  /** pre-spread score when community/GFW pressure moved it (B14) */
  score_base?: number;
  /** crowd-spread measurement — "sabko same jagah mat bhejo" (B14) */
  crowd?: CrowdInfo | null;
  /** auditable score arithmetic — every +/− explained in words */
  reasons: string[];
}

export interface VoyageResponse {
  found: boolean;
  from: [number, number];
  max_km: number;
  recommendations: VoyageReco[];
  candidates_evaluated?: number;
  /** B14: recommendations are load-balanced across the community */
  spreading?: boolean;
  /** honest failure log — sources that failed appear here, never hidden */
  notes?: string[];
  sources?: { pfz?: string; chl?: string; weather?: string; fleet?: string; community?: string };
  /** the scoring formula spelled out, exactly as computed */
  scoring?: string;
  ranking_status?: "experimental_non_authoritative" | "unavailable_without_official_pfz";
  ranking_disclaimer?: string;
  analyzed_at?: string;
}

export const fetchVoyage = (lat: number, lon: number, maxKm = 120) =>
  apiGet<VoyageResponse>(
    `/api/v1/voyage?lat=${lat}&lon=${lon}&max_km=${maxKm}`,
    75_000 /* PFZ + chl grid + per-candidate weather gate ≈ 20–40 s cold */);

export interface LayersResponse {
  type: "FeatureCollection";
  generated_at: string;
  features: any[];
  layer_types: string[];
  sources: string[];
  errors: string[];
}

export const fetchLayers = (types?: string[], bbox?: string) =>
  apiGet<LayersResponse>(
    `/api/v1/layers?${types ? `types=${types.join(",")}` : ""}${bbox ? `&bbox=${bbox}` : ""}`,
    90_000
  );

export const fetchAlerts = (lat?: number, lon?: number) =>
  apiGet<AlertsResponse>(
    `/api/v1/alerts${lat != null && lon != null ? `?lat=${lat}&lon=${lon}` : ""}`,
    120_000
  );

export const fetchHealth = () =>
  apiGet<{ status: string; version: string; gfw_token: boolean; [k: string]: any }>(
    `/api/v1/health`,
    15_000
  );

export const simulateAlert = (lat: number, lon: number) =>
  apiPost<{ created: OrcaAlert; note: string }>(
    `/api/v1/alerts/simulate`,
    { type: "cyclone", lat, lon },
    15_000
  );

export const postChatOnce = (
  message: string,
  lat: number,
  lon: number,
  lang?: string
) => apiPost<ChatFinal>(`/api/v1/chat`, { message, lat, lon, lang }, 260_000);

export const postFeedback = (payload: unknown) =>
  apiPost(`/api/v1/feedback`, payload, 15_000);

// ── WebSocket ─────────────────────────────────────────────────────

export function wsUrl(): string {
  const configured = (process.env.NEXT_PUBLIC_ORCA_WS_URL ?? "").trim();
  if (configured) return configured;
  if (typeof window === "undefined") return "/ws/chat";
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/chat`;
}

export type ChatEventHandler = (ev: any) => void;

/**
 * Stream a chat answer over WebSocket (routing → agent steps → tokens →
 * final), with automatic fallback to the one-shot HTTP endpoint when the
 * socket can't connect (some corporate proxies block WS). Events passed
 * to `onEvent` are blueprint-shaped (chat.routing, chat.agent_step,
 * chat.token, chat.final, chat.slow_notice).
 */
export async function streamChat(
  message: string,
  lat: number,
  lon: number,
  lang: string,
  onEvent: ChatEventHandler,
): Promise<void> {
  const url = wsUrl();
  let ws: WebSocket | null = null;
  let gotAny = false;
  let finished = false;

  const wsPromise = new Promise<void>((resolve, reject) => {
    try {
      ws = new WebSocket(url);
    } catch (e) {
      reject(e);
      return;
    }
    const killer = setTimeout(() => {
      if (!finished) {
        try { ws?.close(); } catch { /* noop */ }
        reject(new Error("WebSocket timed out"));
      }
    }, 240_000);

    ws.onopen = () => {
      onEvent({ type: "chat.ws_open" });
      ws!.send(JSON.stringify({
        type: "chat.user_message", message, lat, lon, lang,
      }));
    };
    ws.onmessage = (msg) => {
      try {
        const ev = JSON.parse(String(msg.data));
        gotAny = true;
        if (ev.type === "chat.final") finished = true;
        onEvent(ev);
        if (ev.type === "chat.final" || ev.type === "chat.error") {
          clearTimeout(killer);
          resolve();
          ws?.close();
        }
      } catch { /* ignore non-JSON */ }
    };
    ws.onerror = () => {
      clearTimeout(killer);
      reject(new Error(`WebSocket error connecting to ${url}`));
    };
    ws.onclose = (c) => {
      clearTimeout(killer);
      if (!finished) {
        reject(new Error(`WebSocket closed (code ${c.code}) before final answer`));
      }
    };
  });

  try {
    await wsPromise;
  } catch (e) {
    if (!gotAny) {
      // Honest fallback: same real answer via HTTP, no live trace
      onEvent({ type: "chat.ws_fallback", payload: { reason: String(e) } });
      const final = await postChatOnce(message, lat, lon, lang);
      for (const step of final.steps ?? []) {
        onEvent({ type: "chat.agent_step", payload: step });
      }
      onEvent({ type: "chat.token", payload: { delta: final.answer } });
      onEvent({ type: "chat.final", payload: final });
    } else {
      throw e;
    }
  }
}

/* ── B18: ORCA Live Beacon — "Samudri Rakshak Net" ─────────────────
 * AIS-waali philosophy fisher ke phone pe: voyage ke dauraan anonymous
 * GPS ping → live beacon. SOS → ping ke response mein hi paas ke boats
 * ko alert. Privacy by design: identity kuch nahi, 2 h silence →
 * auto-delete, stop = instant poora delete. */

export interface LiveBoat {
  pub_id: string;
  lat: number;
  lon: number;
  age_sec: number;
  sos: boolean;
  label?: string;
  speed_kn?: number;
  heading_deg?: number;
  sos_age_sec?: number;
  sos_note?: string;
  distance_nm?: number;
  bearing_deg?: number;
  /** B19: ye boat kisi rescue pe gayi hui hai — "madad mein" badge */
  on_rescue?: boolean;
}

export interface LiveStartResponse {
  ok: boolean;
  created: boolean;
  session: string;
  pub_id: string;
}

/* ── B19: rescue dispatch payloads ── */

/** ORCA Radio message (case channel — B20). */
export interface CaseMsg {
  from: string;
  mine: boolean;
  text: string;
  preset: boolean;
  age_sec: number;
}

/** Mujh pe aayi hui RESCUE REQUEST (ping ke andar hi aata hai). */
export interface RescueRequestPayload {
  case_id: string;
  my_state: "pending" | "seen" | "accepted";
  victim: LiveBoat;
  /** mujhSE victim tak (guidance direction) */
  distance_nm: number;
  bearing_deg: number;
  offer_age_sec: number;
  expires_in_sec: number;
  /** 📻 ORCA Radio feed (B20) */
  messages: CaseMsg[];
}

/** Victim ke SOS ka live dispatch status (ping ke andar hi aata hai). */
export interface MySosAccepted {
  pub_id: string;
  label?: string;
  distance_nm: number;
  bearing_deg: number;
  age_sec: number;
  /** sirf real speed pe — warna null (invent kabhi nahi) */
  eta_min: number | null;
}

export interface MySosStatus {
  case_id: string;
  status: "open" | "assigned" | "resolved";
  tier_nm: number;
  tiers_nm: number[];
  case_age_sec: number;
  /** open + accept nahi → kitne sec mein radius badhega (null = final tier) */
  escalate_in_sec: number | null;
  dispatched: number;
  seen: number;
  declined: number;
  expired: number;
  accepted: MySosAccepted[];
  /** 📻 ORCA Radio feed (B20) */
  messages: CaseMsg[];
}

export interface LivePingResponse {
  ok: boolean;
  created: boolean;
  pub_id: string;
  sos_nearby: LiveBoat[];
  sos_nearby_count: number;
  rescue_request: RescueRequestPayload | null;
  my_sos: MySosStatus | null;
  sos_resolved?: { by: "rescuer" | "victim"; case_id: string };
}

export interface LiveNearbyResponse {
  center: { lat: number; lon: number };
  radius_nm: number;
  boats: LiveBoat[];
  count: number;
  sos_count: number;
  /** B20: listener-mode users (radar pe nahi dikhte — privacy) */
  watchers: number;
  generated_at: number;
}

export const liveStart = (lat: number, lon: number, label?: string, session?: string) =>
  apiPost<LiveStartResponse>("/api/v1/live/start",
    { lat, lon, ...(label ? { label } : {}), ...(session ? { session } : {}) }, 15_000);

export const livePing = (session: string, lat: number, lon: number,
  extra?: { speed_kn?: number; heading_deg?: number; label?: string; watch?: boolean }) =>
  apiPost<LivePingResponse>("/api/v1/live/ping",
    { session, lat, lon, ...(extra ?? {}) }, 15_000);

/** B20: ORCA Radio — case channel pe message bhejo. */
export const liveRescueMsg = (session: string, caseId: string, text: string, preset = false) =>
  apiPost<{ ok: boolean; sent: boolean; count: number }>(
    "/api/v1/live/rescue/msg", { session, case_id: caseId, text, preset }, 15_000);

export const liveSos = (session: string, note?: string, lat?: number, lon?: number) =>
  apiPost<{ ok: boolean; sos: boolean; case: MySosStatus } & LiveBoat>("/api/v1/live/sos",
    { session, ...(note ? { note } : {}), ...(lat !== undefined ? { lat } : {}), ...(lon !== undefined ? { lon } : {}) }, 15_000);

export const liveSosClear = (session: string) =>
  apiPost<{ ok: boolean; sos: boolean; pub_id: string }>("/api/v1/live/sos/clear", { session }, 15_000);

export const liveStop = (session: string) =>
  apiPost<{ ok: boolean; deleted: boolean }>("/api/v1/live/stop", { session }, 15_000);

/** B19: rescuer ka jawab — madad karunga (true) ya nahi paaunga (false). */
export const liveRescueAnswer = (session: string, caseId: string, accept: boolean, reason?: string) =>
  apiPost<{ ok: boolean; state: string; case_id: string; rescue?: RescueRequestPayload }>(
    "/api/v1/live/rescue/answer",
    { session, case_id: caseId, accept, ...(reason ? { reason } : {}) }, 15_000);

/** B19: accepted rescuer — "pahunch gaya / sab safe" → victim SOS auto-clear. */
export const liveRescueComplete = (session: string, caseId: string) =>
  apiPost<{ ok: boolean; resolved: boolean; case_id: string; victim_pub_id: string }>(
    "/api/v1/live/rescue/complete", { session, case_id: caseId }, 15_000);

export const liveNearby = (lat: number, lon: number, radiusNm = 20) =>
  apiGet<LiveNearbyResponse>(
    `/api/v1/live/nearby?lat=${lat}&lon=${lon}&radius_nm=${radiusNm}`, 15_000);

export interface LiveSosListResponse {
  sos: LiveBoat[];
  count: number;
  generated_at: number;
}
export const liveSosList = () => apiGet<LiveSosListResponse>("/api/v1/live/sos", 15_000);

export const liveBoat = (pubId: string) =>
  apiGet<{ ok: boolean; boat: LiveBoat }>(`/api/v1/live/boat/${encodeURIComponent(pubId)}`, 15_000);

export interface LiveStats {
  active_boats: number;
  watchers: number;
  sos_active: number;
  oldest_ping_age_sec: number;
  auto_delete_after_sec: number;
  default_radius_nm: number;
  privacy: string;
  model: string;
}
export const liveStats = () => apiGet<LiveStats>("/api/v1/live/stats", 15_000);
