"use client";

import { useEffect, useState } from "react";
import { Analytics } from "@vercel/analytics/next";
import { analyticsPageUrl } from "@/lib/analytics";

export default function SiteAnalytics({ origin }: { origin: string }) {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    setEnabled(window.location.origin === origin && navigator.doNotTrack !== "1" &&
      !(navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl);
  }, [origin]);
  if (!enabled) return null;
  return <Analytics debug={false} beforeSend={event => {
    if (event.type !== "pageview") return null;
    const url = analyticsPageUrl(event.url, origin);
    return url ? { ...event, url } : null;
  }} />;
}
