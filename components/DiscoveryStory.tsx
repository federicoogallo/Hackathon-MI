"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import "./discovery-story.css";

const STEPS = [
  { number: "01", title: "Scopri cosa si muove.", copy: "Gli hackathon di piattaforme e community, raccolti in un unico posto." },
  { number: "02", title: "Segui quello che ti accende.", copy: "Cerca, confronta e salva le sfide che fanno per te." },
  { number: "03", title: "Porta le idee fuori dallo schermo.", copy: "Apri la fonte, scopri come partecipare e incontra il tuo prossimo team." },
];

function Arrow({ diagonal = false }: { diagonal?: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{diagonal ? <path d="M6 18 18 6M6 6h12v12" /> : <path d="M4 12h16m-6-6 6 6-6 6" />}</svg>;
}

export default function DiscoveryStory() {
  const section = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [motionAllowed, setMotionAllowed] = useState(false);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setMotionAllowed(!preference.matches);
    updatePreference();
    preference.addEventListener("change", updatePreference);

    // Everything is rendered visibly. Intersection only starts the illustration's
    // one-time entrance; no content depends on JavaScript or scroll to appear.
    let observer: IntersectionObserver | undefined;
    if (section.current && "IntersectionObserver" in window) {
      observer = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer?.disconnect();
        }
      }, { threshold: 0.2 });
      observer.observe(section.current);
    }
    return () => {
      observer?.disconnect();
      preference.removeEventListener("change", updatePreference);
    };
  }, []);

  return (
    <section ref={section} className="discovery-story" id="about" aria-labelledby="discovery-story-title" data-visible={visible} data-motion={motionAllowed}>
      <div className="discovery-story-inner container">
        <div className="discovery-story-copy">
          <p className="discovery-story-eyebrow"><span /> DALLE POSSIBILITÀ ALLE PERSONE</p>
          <h2 id="discovery-story-title">Tu porta<br />le <em>idee.</em></h2>
          <p className="discovery-story-lead">Alla ricerca pensiamo noi.</p>
          <ol className="discovery-story-steps">
            {STEPS.map((step) => <li key={step.number}><span className="discovery-story-number" aria-hidden="true">{step.number}</span><div><h3>{step.title}</h3><p>{step.copy}</p></div></li>)}
          </ol>
        </div>

        <div className="discovery-story-art" aria-hidden="true">
          <div className="discovery-story-art-label"><span>IL PERCORSO DI UN’IDEA</span><span>FIG. 02</span></div>
          <div className="discovery-story-stage">
            <div className="discovery-story-orbit discovery-story-orbit--outer" />
            <div className="discovery-story-orbit discovery-story-orbit--inner" />
            <svg className="discovery-story-routes" viewBox="0 0 560 500" fill="none" preserveAspectRatio="none">
              <path className="discovery-story-route discovery-story-route--one" pathLength="1" d="M97 70v46q0 26 26 26h65q26 0 26 26v45" />
              <path className="discovery-story-route discovery-story-route--two" pathLength="1" d="M283 70v143" />
              <path className="discovery-story-route discovery-story-route--three" pathLength="1" d="M458 70v45q0 27-27 27h-65q-26 0-26 26v45" />
              <path className="discovery-story-route discovery-story-route--out" pathLength="1" d="M220 365v54q0 28 28 28h178v-40" />
              <circle cx="97" cy="70" r="3" /><circle cx="283" cy="70" r="3" /><circle cx="458" cy="70" r="3" />
              <circle cx="220" cy="365" r="4" /><circle cx="426" cy="407" r="4" />
              <path className="discovery-story-cross" d="M475 196h18m-9-9v18M74 387h14m-7-7v14" />
            </svg>
            <div className="discovery-story-sources"><span>Community</span><span>Piattaforme</span><span>Fonti pubbliche</span></div>

            <div className="discovery-story-pass">
              <div className="discovery-story-pass-top"><span>IL TUO RADAR</span><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="16" cy="16" r="12" /><circle cx="16" cy="16" r="6" /><path d="M16 1v30M1 16h30m-14 0 8-8" /></svg></div>
              <div className="discovery-story-pass-title">La prossima<br />buona <em>idea.</em></div>
              <div className="discovery-story-pass-bottom"><span>HACKATHON<br /><strong>MILANO E DINTORNI</strong></span><Arrow diagonal /></div>
              <span className="discovery-story-perforation" />
            </div>

            <div className="discovery-story-next"><span>IL PROSSIMO PROGETTO</span><div className="discovery-story-next-visual"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="9" width="36" height="34" rx="4" /><path d="M6 20h36M16 5v9M32 5v9m-15 17 5 5 10-10" /></svg><p>Fai spazio<br /><strong>alle idee.</strong></p></div></div>
            <div className="discovery-story-stamp"><span>LE IDEE</span><svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 3v34M3 20h34M8 8l24 24M8 32 32 8" /></svg><span>PRENDONO FORMA</span></div>
          </div>
          <p className="discovery-story-art-caption">Meno schede aperte. Più possibilità.</p>
        </div>

        <div className="discovery-story-footer"><p><span /> Fonti trasparenti. Scelte tue.</p><Link href="/review">Come selezioniamo gli eventi <Arrow /></Link></div>
      </div>
    </section>
  );
}
