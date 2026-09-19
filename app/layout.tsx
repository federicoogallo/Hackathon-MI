import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk, Instrument_Serif } from "next/font/google";
import { SITE_URL } from "@/lib/data";
import { THEME_BOOTSTRAP } from "@/lib/theme";
import "./globals.css";
import "./theme.css";

const inter = Inter({ subsets: ["latin"], variable: "--f-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--f-mono", display: "swap" });
const grotesk = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--f-grotesk", display: "swap" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--f-serif", display: "swap" });

export const metadata: Metadata = {
  // deve combaciare col deployment di produzione: og:image e canonical si
  // risolvono da qui (l'host precedente rispondeva 404)
  metadataBase: new URL(SITE_URL),
  title: "Hackathon Milano",
  description: "Trova hackathon a Milano e dintorni. Esplora date e fonti, filtra gli eventi e salva le tue prossime sfide in un unico posto.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Hackathon Milano",
    description: "Le grandi idee iniziano qui. Scopri gli hackathon a Milano, trova la tua prossima sfida e incontra il tuo team.",
    type: "website",
    url: SITE_URL,
    siteName: "Hackathon Milano",
    locale: "it_IT",
    images: [{ url: "/milano-hero.webp", width: 1254, height: 1254, alt: "Un modello del Duomo e dello skyline di Milano attraversato da un’orbita arancio" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Hackathon Milano",
    description: "Le grandi idee iniziano qui. Scopri gli hackathon a Milano, trova la tua prossima sfida e incontra il tuo team.",
    images: [{ url: "/milano-hero.webp", width: 1254, height: 1254, alt: "Un modello del Duomo e dello skyline di Milano attraversato da un’orbita arancio" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#f5f4ee",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" data-scroll-behavior="smooth" suppressHydrationWarning className={`${inter.variable} ${mono.variable} ${grotesk.variable} ${serif.variable}`}>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} /></head>
      <body>
        {/* skip-link: primo elemento focusabile, visibile solo da tastiera */}
        <a className="skip-link" href="#top">Salta al contenuto</a>
        {children}
      </body>
    </html>
  );
}
