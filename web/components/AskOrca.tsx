"use client";

import { useEffect, useRef, useState } from "react";
import {
  Advisory,
  ChatFinal,
  ChatStep,
  DemoZone,
  streamChat,
} from "@/lib/orca-client";
import { t, Lang } from "@/lib/i18n";

interface Message {
  role: "user" | "orca";
  text: string;
  steps?: ChatStep[];
  advisory?: Advisory;
  usedFallback?: boolean;
}

export default function AskOrca({
  zone,
  lang,
  onVerdict,
}: {
  zone: DemoZone;
  lang: Lang;
  onVerdict?: (a: Advisory) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [liveSteps, setLiveSteps] = useState<ChatStep[]>([]);
  const [liveTokens, setLiveTokens] = useState("");
  const [status, setStatus] = useState<string>("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 999999, behavior: "smooth" });
  }, [messages, liveSteps, liveTokens]);

  const ask = async (text: string) => {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setInput("");
    setLiveSteps([]);
    setLiveTokens("");
    setStatus("routing…");
    setMessages((m) => [...m, { role: "user", text: message }]);

    let steps: ChatStep[] = [];
    let tokens = "";
    let usedFallback = false;

    try {
      await streamChat(message, zone.lat, zone.lon, lang, (ev) => {
        if (ev.type === "chat.ws_open") setStatus("connected — agents running…");
        else if (ev.type === "chat.ws_fallback") {
          usedFallback = true;
          setStatus("live channel blocked — answering over HTTP (same real data)…");
        } else if (ev.type === "chat.routing") {
          setStatus(`routing → ${ev.payload.agents.length} agents + ${ev.payload.tools.length} tools`);
        } else if (ev.type === "chat.agent_step") {
          steps = [...steps, ev.payload as ChatStep];
          setLiveSteps(steps);
          setStatus("agents running…");
        } else if (ev.type === "chat.token") {
          tokens += ev.payload.delta;
          setLiveTokens(tokens);
        } else if (ev.type === "chat.final") {
          const f = ev.payload as ChatFinal;
          setMessages((m) => [
            ...m,
            { role: "orca", text: f.answer, steps, advisory: f.advisory, usedFallback },
          ]);
          onVerdict?.(f.advisory);
          setLiveSteps([]);
          setLiveTokens("");
          setStatus("");
        } else if (ev.type === "chat.error") {
          setMessages((m) => [
            ...m,
            { role: "orca", text: `Something failed mid-answer: ${ev.payload.error}`, steps },
          ]);
          setStatus("");
        }
      });
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "orca", text: `Could not reach the ORCA backend. ${e instanceof Error ? e.message : e}` },
      ]);
      setStatus("");
    } finally {
      setBusy(false);
    }
  };

  const quick = [t(lang, "ask_quick_1"), t(lang, "ask_quick_2"), t(lang, "ask_quick_3")];

  return (
    <div className="h-full flex flex-col">
      {/* header */}
      <div className="px-4 py-3 bg-[#0E1729] text-slate-100 border-b border-[#1C2A45]">
        <h2 className="font-bold">{t(lang, "ask_title")}</h2>
        <p className="text-xs text-slate-500">{t(lang, "ask_hint")}</p>
      </div>

      {/* messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#070D1A]">
        {messages.length === 0 && !busy && (
          <div className="text-center text-sm text-slate-500 mt-8">
            <div className="text-4xl mb-3">🐋</div>
            <p className="max-w-md mx-auto">
              {lang === "hi"
                ? `चुना हुआ ज़ोन: ${zone.name}. कुछ भी पूछिए — जवाब असली डेटा से बनेगा, हर एजेंट चलता दिखेगा।`
                : `Selected zone: ${zone.name}. Ask anything — the answer is built from live data, with every agent's run shown.`}
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                m.role === "user"
                  ? "inline-block bg-cyan-700 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-[85%] text-left"
                  : "inline-block bg-[#0E1729] border border-[#1C2A45] rounded-2xl rounded-bl-sm px-4 py-3 max-w-[95%] shadow-lg"
              }
            >
              {m.role === "orca" && m.steps && m.steps.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {m.steps.map((s, j) => (
                    <span key={j} className="text-[10px] bg-[#131E35] border border-[#2B4066] rounded-full px-2 py-0.5 text-slate-400">
                      {s.summary}
                    </span>
                  ))}
                </div>
              )}
              <p className="whitespace-pre-wrap text-sm text-slate-100">{m.text}</p>
              {m.advisory && (
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <span className={`px-2 py-1 rounded font-bold text-white ${
                    m.advisory.verdict === "go" ? "bg-green-600" :
                    m.advisory.verdict === "caution" ? "bg-amber-500" :
                    m.advisory.verdict === "unknown" ? "bg-slate-600" : "bg-red-600"}`}>
                    {m.advisory.icon} {m.advisory.verdict === "go" ? "GO" : m.advisory.verdict === "caution" ? "CAUTION" : m.advisory.verdict === "unknown" ? "NOT VERIFIED" : "NO-GO"}
                  </span>
                  <span className="text-slate-400">
                    {lang === "hi" ? m.advisory.headline_hi : m.advisory.headline_en}
                  </span>
                </div>
              )}
              {m.usedFallback && (
                <div className="mt-1 text-[10px] text-slate-600">
                  answered via HTTP (same agents, trace replayed)
                </div>
              )}
            </div>
          </div>
        ))}

        {/* live trace while running */}
        {busy && (
          <div className="text-left">
            <div className="inline-block bg-[#0E1729] border border-[#1C2A45] rounded-2xl rounded-bl-sm px-4 py-3 max-w-[95%] shadow-lg">
              <div className="flex flex-wrap gap-1 mb-2">
                {liveSteps.map((s, j) => (
                  <span key={j} className="text-[10px] bg-[#10233F] border border-cyan-500/40 rounded-full px-2 py-0.5 text-cyan-200 animate-pulse">
                    {s.summary}
                  </span>
                ))}
                {liveSteps.length === 0 && (
                  <span className="text-[10px] bg-[#131E35] rounded-full px-2 py-0.5 text-slate-500 animate-pulse">
                    {status || "connecting…"}
                  </span>
                )}
              </div>
              {liveTokens ? (
                <p className="whitespace-pre-wrap text-sm text-slate-100">{liveTokens}▌</p>
              ) : (
                <p className="text-xs text-slate-500">{status}</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* quick prompts + input */}
      <div className="border-t border-[#1C2A45] bg-[#0E1729] p-3 space-y-2">
        <div className="flex flex-wrap gap-2">
          {quick.map((q) => (
            <button
              key={q}
              disabled={busy}
              onClick={() => ask(q)}
              className="text-xs bg-[#131E35] hover:bg-[#16243F] border border-[#2B4066] text-slate-300 rounded-full px-3 py-1 disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 bg-[#070D1A] border border-[#2B4066] text-slate-100 placeholder:text-slate-600 rounded-lg px-3 py-2 text-sm outline-none focus:border-cyan-500/60"
            placeholder={t(lang, "ask_placeholder")}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask(input)}
            disabled={busy}
          />
          <button
            onClick={() => ask(input)}
            disabled={busy || !input.trim()}
            className="bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            {t(lang, "send")}
          </button>
        </div>
        <p className="text-[10px] text-slate-600">{t(lang, "ask_mic_note")}</p>
      </div>
    </div>
  );
}
