import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SITE_URL } from "@/lib/data";
import { getEventDetail, getEventDetails } from "@/lib/event-details";
import { eventStructuredData, serializeStructuredData } from "@/lib/seo";
import EventDetailView from "@/components/EventDetailView";

export const dynamic = "force-static";
export const dynamicParams = false;

type Props = { params: Promise<{ slug: string }> };
export function generateStaticParams() {
  return getEventDetails().map(({ slug }) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const event = getEventDetail((await params).slug);
  if (!event) return {};
  const description = `${event.dateLabel}. ${event.location}. Informazioni pratiche, requisiti e fonte ufficiale per ${event.title}.`;
  return {
    title: `${event.title} | Hackathon Milano`, description,
    alternates: { canonical: event.detailPath },
    openGraph: { title: event.title, description, url: event.detailPath, type: "website", locale: "it_IT", siteName: "Hackathon Milano", images: [{ url: "/opengraph-image.png", width: 1200, height: 630, alt: "Hackathon Milano — il radar degli hackathon" }] },
    twitter: { card: "summary_large_image", title: event.title, description, images: ["/opengraph-image.png"] },
  };
}

export default async function EventPage({ params }: Props) {
  const event = getEventDetail((await params).slug);
  if (!event) notFound();
  const related = getEventDetails().filter((other) => other.id !== event.id && !other.isPast).slice(0, 3);
  return <>
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeStructuredData(eventStructuredData(SITE_URL, event)) }} />
    <EventDetailView event={event} related={related} />
  </>;
}
