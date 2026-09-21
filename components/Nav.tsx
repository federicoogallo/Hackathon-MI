"use client";

import { Suspense, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import ThemeControl from "./ThemeControl";

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link className={`brand${light ? " brand-light" : ""}`} href="/" aria-label="Hackathon Milano — home">
      <svg className="brand-symbol" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path d="M16 2v8m0 12v8M2 16h8m12 0h8M6.1 6.1l5.7 5.7m8.4 8.4 5.7 5.7M6.1 25.9l5.7-5.7m8.4-8.4 5.7-5.7" stroke="currentColor" strokeWidth="4.5" />
      </svg>
      <span>hackathon<span className="brand-city">milano<span className="brand-period">.</span></span></span>
    </Link>
  );
}

type NavLocation = { hash: string; search: string };

function NavLocationSync({ onChange }: { onChange: Dispatch<SetStateAction<NavLocation | null>> }) {
  const params = useSearchParams();
  const search = params.toString();
  useEffect(() => {
    const sync = () => onChange({ hash: window.location.hash, search: window.location.search });
    sync();
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, [search, onChange]);
  return null;
}

export default function Nav({ children }: { children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [location, setLocation] = useState<NavLocation | null>(null);
  const path = usePathname();
  const params = new URLSearchParams(location?.search);
  const active = path !== "/" || !location ? null : location.hash === "#about" ? "about" : params.get("saved") === "1" ? "saved" : "events";
  params.delete("saved");
  const query = path === "/" ? params.toString() : "";
  const eventsHref = `/${query ? `?${query}` : ""}#events`;
  const aboutHref = path === "/" ? "#about" : "/#about";
  const current = (item: string) => active === item ? "location" as const : undefined;
  return (
    <header className="site-header" onClick={event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a") : null;
      if (!link || link.target === "_blank") return;
      const url = new URL(link.href);
      if (url.origin === window.location.origin && url.pathname === "/") {
        setLocation({ hash: url.hash, search: url.search });
      }
    }}>
      <Suspense fallback={null}><NavLocationSync onChange={setLocation} /></Suspense>
      <div className="container nav-inner">
        <Brand />
        <nav className="desktop-nav" aria-label="Navigazione principale">
          <Link href={eventsHref} aria-current={current("events")} className={`nav-link${active === "events" ? " is-current" : ""}`}>Esplora gli eventi</Link>
          <a href={aboutHref} aria-current={current("about")} className={`nav-link${active === "about" ? " is-current" : ""}`}>Come funziona</a>
          <Link href="/?saved=1#events" aria-current={current("saved")} className={`nav-link nav-saved${active === "saved" ? " is-current" : ""}`}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M6 4h12v17l-6-4-6 4V4Z" /></svg>
            Salvati
          </Link>
        </nav>
        <div className="nav-cta">
          {children || <a href="https://github.com/federicoogallo/Hackathon-MI/issues/new?title=Segnalazione%20hackathon&body=Nome%20evento%3A%0AData%3A%0ALuogo%3A%0ALink%20ufficiale%3A" target="_blank" rel="noopener noreferrer" className="btn btn-nav">Segnala un evento <span aria-hidden="true">↗</span></a>}
        </div>
        <ThemeControl />
        <button className="mobile-menu-button" type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-navigation" aria-label={open ? "Chiudi il menu" : "Apri il menu"}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{open ? <path d="m6 6 12 12M6 18 18 6" /> : <path d="M4 7h16M4 12h16M4 17h16" />}</svg>
        </button>
      </div>
      {open && <nav id="mobile-navigation" className="mobile-navigation" aria-label="Navigazione mobile" onKeyDown={(event) => { if (event.key === "Escape") { setOpen(false); document.querySelector<HTMLButtonElement>(".mobile-menu-button")?.focus(); } }}>
        <Link href={eventsHref} aria-current={current("events")} onClick={() => setOpen(false)}>Esplora gli eventi <span aria-hidden="true">↗</span></Link>
        <Link href="/?saved=1#events" className={`nav-saved${active === "saved" ? " is-current" : ""}`} aria-current={current("saved")} onClick={() => setOpen(false)}>I tuoi eventi salvati <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M6 4h12v17l-6-4-6 4V4Z" /></svg></Link>
        <a href={aboutHref} aria-current={current("about")} onClick={() => setOpen(false)}>Come funziona <span aria-hidden="true">↗</span></a>
        <Link href="/review" onClick={() => setOpen(false)}>Eventi in revisione <span aria-hidden="true">↗</span></Link>
        <a href="https://github.com/federicoogallo/Hackathon-MI/issues/new?title=Segnalazione%20hackathon" target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>Segnala un evento <span aria-hidden="true">↗</span></a>
      </nav>}
    </header>
  );
}
