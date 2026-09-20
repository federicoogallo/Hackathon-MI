import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk, Instrument_Serif } from "next/font/google";
import { SITE_URL } from "@/lib/data";
import { SITE_DESCRIPTION, SITE_NAME } from "@/lib/seo";
import { THEME_BOOTSTRAP } from "@/lib/theme";
import "./globals.css";
import "./theme.css";

const inter = Inter({ subsets: ["latin"], variable: "--f-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--f-mono", display: "swap" });
const grotesk = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--f-grotesk", display: "swap" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--f-serif", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  applicationName: SITE_NAME,
  title: "Hackathon Milano — Calendario e prossimi eventi",
  description: SITE_DESCRIPTION,
  alternates: { canonical: "/" },
  robots: { index: true, follow: true, googleBot: { index: true, follow: true, "max-image-preview": "large" } },
  icons: {
    icon: [{ url: "/favicon-96.png", sizes: "96x96", type: "image/png" }],
  },
  openGraph: {
    title: SITE_NAME,
    description: "Le grandi idee iniziano qui. Scopri gli hackathon a Milano, trova la tua prossima sfida e incontra il tuo team.",
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    locale: "it_IT",
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_NAME,
    description: "Le grandi idee iniziano qui. Scopri gli hackathon a Milano, trova la tua prossima sfida e incontra il tuo team.",
    images: [{ url: "/opengraph-image.png", width: 1200, height: 630, alt: "Hackathon Milano — Le grandi idee iniziano qui. Il radar degli hackathon a Milano e dintorni." }],
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
        <a className="skip-link" href="#top">Salta al contenuto</a>
        {children}
      </body>
    </html>
  );
}
