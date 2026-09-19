"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
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

export default function Nav({ children }: { children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const path = usePathname();
  return (
    <header className="site-header">
      <div className="container nav-inner">
        <Brand />
        <nav className="desktop-nav" aria-label="Navigazione principale">
          <a href={path === "/" ? "#events" : "/#events"} className={path === "/" ? "nav-link is-current" : "nav-link"}>Esplora gli eventi</a>
          <a href={path === "/" ? "#about" : "/#about"} className="nav-link">Come funziona</a>
          <a href="/?saved=1#events" className="nav-link nav-saved">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M6 4h12v17l-6-4-6 4V4Z" /></svg>
            Salvati
          </a>
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
        <a href={path === "/" ? "#events" : "/#events"} onClick={() => setOpen(false)}>Esplora gli eventi <span aria-hidden="true">↗</span></a>
        <a href="/?saved=1#events" onClick={() => setOpen(false)}>I tuoi eventi salvati <span aria-hidden="true">↗</span></a>
        <a href={path === "/" ? "#about" : "/#about"} onClick={() => setOpen(false)}>Come funziona <span aria-hidden="true">↗</span></a>
        <Link href="/review" onClick={() => setOpen(false)}>Eventi in revisione <span aria-hidden="true">↗</span></Link>
        <a href="https://github.com/federicoogallo/Hackathon-MI/issues/new?title=Segnalazione%20hackathon" target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>Segnala un evento <span aria-hidden="true">↗</span></a>
      </nav>}
    </header>
  );
}
