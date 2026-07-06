import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk, Instrument_Serif } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--f-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--f-mono", display: "swap" });
const grotesk = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--f-grotesk", display: "swap" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--f-serif", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL("https://hackathon-mi.vercel.app"),
  title: "Hackathon Milano",
  description: "Hackathon in programma a Milano e dintorni, verificati da AI e review umana.",
  openGraph: {
    title: "Hackathon Milano",
    description: "Hackathon in programma a Milano e dintorni.",
    type: "website",
    images: ["/hero-hackathon-milano.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#070a11",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" className={`${inter.variable} ${mono.variable} ${grotesk.variable} ${serif.variable}`}>
      <head>
        {/* Intro orbitale solo alla prima visita della sessione: al reload (o
            deep-link con hash) si salta e si va dritti alla pagina. Deciso
            prima del primo paint per non far lampeggiare il globo. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var s=sessionStorage.getItem('hm_intro_seen');" +
              "if(location.hash||s){document.documentElement.classList.add('skip-intro');}" +
              "if(!s){sessionStorage.setItem('hm_intro_seen','1');}}catch(e){}})();",
          }}
        />
      </head>
      <body className="elite-shell">{children}</body>
    </html>
  );
}
