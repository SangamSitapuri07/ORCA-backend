"use client";

import { useEffect, useState } from "react";
import { DemoZone, INDIAN_COASTAL_ZONES, postFeedback, wsUrl, fetchHealth, gfwDeepStored, setGfwDeep } from "@/lib/orca-client";
import { t, Lang, LANGS } from "@/lib/i18n";

interface Health {
  status: string;
  version: string;
  gfw_token_configured?: boolean;
  data_sources?: Record<string, string>;
  cache?: Record<string, { fresh_for_sec: number }>;
}

export default function SettingsPanel({
  zone,
  setZone,
  lang,
  setLang,
}: {
  zone: DemoZone;
  setZone: (z: DemoZone) => void;
  lang: Lang;
  setLang: (l: Lang) => void;
}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [gfwStored, setGfwStoredState] = useState<boolean | null>(null);
  const [fb, setFb] = useState("");
  const [fbDone, setFbDone] = useState(false);
  const [wsState, setWsState] = useState("checking…");

  useEffect(() => {
    setGfwStoredState(gfwDeepStored());
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));

    // quick WS liveness probe (opens and closes)
    try {
      const ws = new WebSocket(wsUrl());
      const timer = setTimeout(() => { setWsState("not reachable"); ws.close(); }, 6000);
      ws.onopen = () => { clearTimeout(timer); setWsState("connected ✅"); ws.send(JSON.stringify({ type: "ping" })); ws.close(); };
      ws.onerror = () => { clearTimeout(timer); setWsState("not reachable ❌ (HTTP fallback works)"); };
    } catch {
      setWsState("not reachable ❌");
    }
  }, []);

  const sendFeedback = async (useful: boolean) => {
    try {
      await postFeedback({ useful, comment: fb, lat: zone.lat, lon: zone.lon, lang });
      setFbDone(true);
      setFb("");
    } catch { /* offline: silently ignore for now */ }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#070D1A] p-4 space-y-4 max-w-2xl">
      <h2 className="font-bold text-slate-100">{t(lang, "settings_title")}</h2>

      {/* language */}
      <section className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <h3 className="text-sm font-semibold text-slate-200 mb-2">🗣️ {t(lang, "language")}</h3>
        <div className="flex gap-2">
          {LANGS.map((l) => (
            <button
              key={l.id}
              onClick={() => setLang(l.id)}
              className={`rounded-full px-4 py-1.5 text-sm border ${
                lang === l.id ? "bg-cyan-600 text-white border-cyan-500" : "bg-[#131E35] border-[#2B4066] text-slate-300"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-slate-500 mt-2">{t(lang, "settings_language_note")}</p>
      </section>

      {/* home port */}
      <section className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <h3 className="text-sm font-semibold text-slate-200 mb-2">⚓ {t(lang, "home_port")}</h3>
        <select
          className="bg-[#070D1A] border border-[#2B4066] text-slate-200 rounded px-3 py-2 text-sm w-full"
          value={zone.name}
          onChange={(e) => {
            const z = INDIAN_COASTAL_ZONES.find((x) => x.name === e.target.value);
            if (z) setZone(z);
          }}
        >
          {INDIAN_COASTAL_ZONES.map((z) => (
            <option key={z.name} value={z.name}>
              {z.name} — {z.lat.toFixed(2)}°N, {z.lon.toFixed(2)}°E
            </option>
          ))}
          {!INDIAN_COASTAL_ZONES.some((z) => z.name === zone.name) && (
            <option value={zone.name}>{zone.name}</option>
          )}
        </select>
      </section>

      {/* GFW deep data toggle */}
      <section className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <h3 className="text-sm font-semibold text-slate-200 mb-2">🚢 {t(lang, "gfw_title")}</h3>
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={gfwStored ?? Boolean((health as any)?.credentials?.gfw_token_configured)}
            onChange={(e) => {
              setGfwStoredState(e.target.checked);
              setGfwDeep(e.target.checked);
            }}
          />
          <span className="text-sm text-slate-300">{t(lang, "gfw_toggle")}</span>
        </label>
        <p className="text-[11px] text-slate-500 mt-2 leading-relaxed">
          {health && (health as any).credentials?.gfw_token_configured === false
            ? `⚠️ ${t(lang, "gfw_no_token")}`
            : gfwStored === null
              ? `🤖 ${t(lang, "gfw_auto_note")}`
              : t(lang, "gfw_note")}
        </p>
      </section>

      {/* system status / data freshness */}
      <section className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <h3 className="text-sm font-semibold text-slate-200 mb-2">📊 {t(lang, "data_freshness")}</h3>
        {!health ? (
          <p className="text-sm text-red-400">backend unreachable on /api/v1/health</p>
        ) : (
          <div className="text-xs space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-slate-400">{t(lang, "server")}:</span>
              <span className={health.status === "ok" ? "text-emerald-300" : "text-red-400"}>
                {health.status} · v{health.version}
              </span>
              <span className="text-slate-500">GFW token: {health.gfw_token_configured ? "✅" : "not set (.env)"}</span>
            </div>
            <div>
              <span className="font-semibold text-slate-400">{t(lang, "ws_status")}:</span>{" "}
              <span className="text-slate-300">{wsState}</span>
            </div>
            <div>
              <div className="font-semibold text-slate-400 mb-1">{t(lang, "backend_sources")}:</div>
              <ul className="space-y-0.5">
                {Object.entries(health.data_sources ?? {}).map(([k, v]) => (
                  <li key={k} className="text-slate-400">
                    <span className="font-mono text-cyan-300/80">{k}</span>: {v}
                  </li>
                ))}
              </ul>
            </div>
            {health.cache && Object.keys(health.cache).length > 0 && (
              <details>
                <summary className="cursor-pointer text-slate-500">cache ({Object.keys(health.cache).length} warm entries)</summary>
                <ul className="mt-1 space-y-0.5">
                  {Object.entries(health.cache).map(([k, v]) => (
                    <li key={k} className="text-slate-500 font-mono text-[10px]">
                      {k} — fresh {Math.round(v.fresh_for_sec / 60)} min
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </section>

      {/* feedback */}
      <section className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <h3 className="text-sm font-semibold text-slate-200 mb-2">💬 {t(lang, "feedback_title")}</h3>
        {fbDone ? (
          <p className="text-sm text-emerald-300">{t(lang, "feedback_thanks")}</p>
        ) : (
          <div className="space-y-2">
            <textarea
              value={fb}
              onChange={(e) => setFb(e.target.value)}
              className="w-full bg-[#070D1A] border border-[#2B4066] text-slate-200 placeholder:text-slate-600 rounded px-3 py-2 text-sm"
              rows={2}
              placeholder={lang === "hi" ? "टिप्पणी (वैकल्पिक)…" : "comment (optional)…"}
            />
            <div className="flex gap-2">
              <button onClick={() => sendFeedback(true)} className="bg-emerald-600 hover:bg-emerald-500 text-white rounded px-4 py-1.5 text-sm">👍 Yes</button>
              <button onClick={() => sendFeedback(false)} className="bg-slate-600 hover:bg-slate-500 text-white rounded px-4 py-1.5 text-sm">👎 Not really</button>
            </div>
            <p className="text-[10px] text-slate-500">Feedback is saved to data/feedback.jsonl on the server.</p>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4 text-xs text-slate-400">
        <h3 className="text-sm font-semibold text-slate-200 mb-1">⚖️ {t(lang, "disclaimer_title")}</h3>
        {lang === "hi"
          ? "ORCA एक सलाहकार सहायक है — समुद्र में उतरने का अंतिम फैसला नाव के मालिक का है। रवाना होने से पहले नवीनतम INCOIS/IMD बुलेटिन ज़रूर देखें।"
          : "ORCA is a decision-support aid — the final call at sea always rests with the skipper. Cross-check with the latest INCOIS / IMD bulletin before sailing."}
      </section>
    </div>
  );
}
