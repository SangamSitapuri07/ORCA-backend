"use client";
import { useEffect } from "react";

/** Registers the offline service worker (tiles + app shell only —
 *  API data is never cached-stale; see public/sw.js). */
export default function SwRegister() {
  useEffect(() => {
    if (typeof window !== "undefined" && "serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("/sw.js").catch(() => { /* private mode / blocked */ });
    }
  }, []);
  return null;
}
