import type { MetadataRoute } from "next";
import { SITE_URL, getSiteData } from "@/lib/data";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const d = getSiteData();
  const scanTime = Date.parse(d.lastScanIso);
  const lastModified = Number.isFinite(scanTime) ? new Date(scanTime) : undefined;

  return [
    { url: `${SITE_URL}/`, lastModified, changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/review`, lastModified, changeFrequency: "daily", priority: 0.5 },
    { url: `${SITE_URL}/privacy`, changeFrequency: "yearly", priority: 0.2 },
  ];
}
