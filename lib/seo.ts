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
            url: event.url,
          })),
        },
      },
    ],
  };
}

export function serializeStructuredData(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}
