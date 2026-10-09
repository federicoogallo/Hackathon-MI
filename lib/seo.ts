import type { EventDetail } from "./event-details";
import type { HackEvent } from "./data";

export const SITE_NAME = "Hackathon Milano";
export const SITE_DESCRIPTION = "Trova hackathon a Milano e dintorni. Esplora date e fonti, filtra gli eventi e salva le tue prossime sfide in un unico posto.";

export function homeStructuredData(siteUrl: string, events: HackEvent[]) {
  const homeUrl = `${siteUrl}/`;

  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${homeUrl}#website`,
        url: homeUrl,
        name: SITE_NAME,
        alternateName: "Hackathon MI",
        description: SITE_DESCRIPTION,
        inLanguage: "it-IT",
      },
      {
        "@type": "CollectionPage",
        "@id": `${homeUrl}#webpage`,
        url: homeUrl,
        name: "Hackathon a Milano: calendario e prossimi eventi",
        description: SITE_DESCRIPTION,
        isPartOf: { "@id": `${homeUrl}#website` },
        inLanguage: "it-IT",
        mainEntity: {
          "@type": "ItemList",
          name: "Prossimi hackathon a Milano e dintorni",
          numberOfItems: events.length,
          itemListElement: events.map((event, index) => ({
            "@type": "ListItem",
            position: index + 1,
            name: event.title,
            url: event.detailPath ? `${siteUrl}${event.detailPath}` : event.url,
          })),
        },
      },
    ],
  };
}

export function serializeStructuredData(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

export function eventStructuredData(siteUrl: string, event: EventDetail) {
  const url = `${siteUrl}${event.detailPath}`;
  const graph: Record<string, unknown>[] = [
    { "@type": "WebPage", "@id": `${url}#webpage`, url, name: event.title,
      description: event.description, inLanguage: "it-IT", dateModified: event.checkedAt,
      isPartOf: { "@id": `${siteUrl}/#website` },
      citation: [...new Set([event.url, ...event.facts.map((f) => f.sourceUrl)])] },
    { "@type": "BreadcrumbList", itemListElement: [
      { "@type": "ListItem", position: 1, name: "Hackathon Milano", item: `${siteUrl}/` },
      { "@type": "ListItem", position: 2, name: event.title, item: url },
    ] },
  ];
  // A city alone is not a venue: only emit Event when its physical address is sourced.
  if (event.venue) graph.push({
    "@type": "Event", "@id": `${url}#event`, url, name: event.title,
    description: event.description, startDate: event.dateIso, endDate: event.endDateIso,
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
    location: { "@type": "Place", name: event.venue.name, address: {
      "@type": "PostalAddress", streetAddress: event.venue.streetAddress,
      addressLocality: event.venue.addressLocality, addressCountry: event.venue.addressCountry,
    } },
    organizer: { "@type": "Organization", name: event.organizer, url: event.url },
  });
  return { "@context": "https://schema.org", "@graph": graph };
}
