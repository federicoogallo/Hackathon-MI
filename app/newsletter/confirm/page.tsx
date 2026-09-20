import type { Metadata } from "next";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import NewsletterConfirmation from "@/components/NewsletterConfirmation";
import "@/components/secondary-pages.css";

export const metadata: Metadata = {
  title: "Conferma iscrizione — Hackathon Milano",
  robots: { index: false, follow: false },
  alternates: { canonical: "/newsletter/confirm" },
};

export default function ConfirmPage() {
  return <><Nav /><main id="top" tabIndex={-1} className="secondary-page"><NewsletterConfirmation /></main><Footer /></>;
}
