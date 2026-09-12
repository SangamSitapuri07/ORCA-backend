"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertEvaluation, DemoZone, OrcaAlert, fetchAlerts, fetchHealth, simulateAlert } from "@/lib/orca-client";
import { t, Lang } from "@/lib/i18n";

function AlertCard({ a, lang }: { a: OrcaAlert; lang: Lang }) {
  const [open, setOpen] = useState(false);
  const warn = a.severity === "warning";
  return (
    <div
      className={`rounded-lg border p-4 bg-[#0E1729] cursor-pointer ${warn ? "border-red-500/50 shadow-[0_0_14px_#ef444422]" : "border-amber-500/40"}`}
      onClick={() => setOpen((o) => !o)}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-slate-100 text-sm">
            {warn ? "🔴" : "🟡"} {lang === "hi" ? a.title_hi : a.title_en}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {a.code} · issued {a.issued_at.slice(11, 16)} UTC · valid till {a.valid_until.slice(11, 16)} UTC · {a.source}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`text-[10px] font-bold uppercase rounded px-2 py-0.5 text-white ${warn ? "bg-red-600" : "bg-amber-500"}`}>
            {a.severity}
          </span>
          {a.simulated && (
            <span className="text-[10px] font-bold rounded px-2 py-0.5 bg-violet-500/15 text-violet-300 border border-violet-500/40">
              {t(lang, "simulated_badge")}
            </span>
          )}
        </div>
      </div>
      {open && (
        <p className="text-sm text-slate-300 mt-2 whitespace-pre-wrap">{a.msg_en}</p>
      )}
    </div>
  );
}

export default function AlertsPanel({
  zone,
  lang,
  ticker,
  setTicker,
}: {
  zone: DemoZone;
  lang: Lang;
  ticker: OrcaAlert[];
  setTicker: (a: OrcaAlert[]) => void;
}) {
  const [alerts, setAlerts] = useState<OrcaAlert[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [demoEnabled, setDemoEnabled] = useState(false);
  const [evaluation, setEvaluation] = useState<AlertEvaluation | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetchAlerts();
      setAlerts(r.alerts);
      setTicker(r.alerts.filter((a) => a.severity === "warning"));
    } catch {
      /* backend offline — keep old list */
    }
  }, [setTicker]);

  useEffect(() => {
    refresh();
    fetchHealth()
      .then((health) => setDemoEnabled(health.components?.demo_alerts?.status === "enabled"))
      .catch(() => setDemoEnabled(false));
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, [refresh]);

  const evaluate = async () => {
    setBusy("eval");
    setError(null);
    try {
      const r = await fetchAlerts(zone.lat, zone.lon);
      setAlerts(r.alerts);
      setEvaluation(r.evaluation);
      setTicker(r.alerts.filter((a) => a.severity === "warning"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  const simulate = async () => {
    setBusy("sim");
    setError(null);
    try {
      await simulateAlert(zone.lat, zone.lon);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#070D1A] p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-bold text-slate-100">{t(lang, "alerts_title")}</h2>
        <div className="flex gap-2">
          <button
            onClick={evaluate}
            disabled={busy !== null}
            className="text-xs bg-cyan-600 hover:bg-cyan-500 text-white rounded px-3 py-2 disabled:opacity-50"
          >
            {busy === "eval" ? "…" : t(lang, "evaluate_here")}
          </button>
          {demoEnabled && (
            <button
              onClick={simulate}
              disabled={busy !== null}
              className="text-xs bg-violet-700 hover:bg-violet-600 text-white rounded px-3 py-2 disabled:opacity-50"
              title={lang === "hi" ? "अभ्यास अलर्ट — असली नहीं" : "drill alert — not real"}
            >
              {busy === "sim" ? "…" : t(lang, "simulate")}
            </button>
          )}
        </div>
      </div>

      <p className="text-xs text-slate-500">{t(lang, "alerts_note")}</p>
      {error && <p className="rounded border border-red-500/40 bg-red-950/30 p-2 text-xs text-red-200">{error}</p>}

      {alerts.length === 0 ? (
        evaluation && evaluation.sources_used.length > 0 && evaluation.sources_failed.length === 0 ? (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-6 text-center">
            <div className="text-3xl mb-2">✅</div>
            <p className="text-sm text-emerald-300">{t(lang, "no_alerts")}</p>
            <p className="mt-2 text-[11px] text-slate-400">Checked: {evaluation.sources_used.join(" · ")}</p>
          </div>
        ) : (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-5 text-center">
            <div className="text-3xl mb-2">❓</div>
            <p className="text-sm text-amber-200">
              {lang === "hi" ? "अभी कोई अलर्ट उपलब्ध नहीं है — इसे ‘सब सुरक्षित’ न मानें।" : "No alerts are available right now — this is not an all-clear."}
            </p>
            {evaluation?.sources_failed?.length ? (
              <p className="mt-2 text-left text-[11px] text-slate-400">{evaluation.sources_failed.join(" · ")}</p>
            ) : (
              <p className="mt-2 text-[11px] text-slate-400">
                {lang === "hi" ? "इस स्थान पर जाँच चलाने के लिए Evaluate दबाएँ।" : "Select Evaluate to check providers for this point."}
              </p>
            )}
          </div>
        )
      ) : (
        <div className="space-y-2">
          {alerts.map((a) => <AlertCard key={a.id} a={a} lang={lang} />)}
        </div>
      )}
    </div>
  );
}
