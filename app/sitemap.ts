import type { MetadataRoute } from "next";
import { SITE_URL, getSiteData } from "@/lib/data";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  // lastModified dall'ultimo scan della pipeline: cambia solo quando i dati
  // cambiano davvero, cosi' il segnale resta onesto
  const d = getSiteData();
  const lastModified = d.lastScanIso ? new Date(d.lastScanIso) : new Date();

  return [
    { url: `${SITE_URL}/`, lastModified, changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/review`, lastModified, changeFrequency: "daily", priority: 0.5 },
  ];
}
