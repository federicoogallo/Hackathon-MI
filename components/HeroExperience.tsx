"use client";

import Link from "next/link";

import { useEffect, useMemo, useRef, useState, type CSSProperties, type FocusEvent, type PointerEvent, type ReactNode } from "react";
import Image from "next/image";
import { motion, useMotionValue, useScroll, useSpring, useTransform } from "motion/react";
import type { HackEvent } from "@/lib/data";
import { useReducedMotionPreference } from "@/lib/use-reduced-motion";
import { selectRadarEvents, todayInRome } from "@/lib/event-filters";
import "./hero-experience.css";

const RADAR_INTERVAL_MS = 7000;

const radarLayouts = {
  wide: [[34, 57, 116], [44, 52, 176], [95, 49, 118]],
  medium: [[36, 58, 98], [43, 48, 134], [95, 49, 112]],
  small: [[20, 53, 94], [30, 43, 112], [94, 46, 114]],
} as const;

function radarPosition(index: number) {
  return Object.fromEntries(Object.entries(radarLayouts).flatMap(([size, points]) => [
    [`--${size}-x`, `${points[index][0]}%`],
    [`--${size}-y`, `${points[index][1]}%`],
    [`--${size}-lift`, `${points[index][2]}px`],
  ])) as CSSProperties;
}

function Arrow({ direction = "right" }: { direction?: "left" | "right" | "up" }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{direction === "up" ? <path d="M6 18 18 6M6 6h12v12" /> : <path d={direction === "left" ? "M20 12H4m6 6-6-6 6-6" : "M4 12h16m-6-6 6 6-6 6"} />}</svg>;
}

export default function HeroExperience({ events, children }: { events: HackEvent[]; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotionPreference();
  const [compact, setCompact] = useState(true);
  const [paused, setPaused] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [today, setToday] = useState("");
  const [autoplayStopped, setAutoplayStopped] = useState(false);
  const [hoveringRadar, setHoveringRadar] = useState(false);
  const [inView, setInView] = useState(false);
  const [pageVisible, setPageVisible] = useState(true);
  const upcoming = useMemo(() => selectRadarEvents(events, today), [events, today]);
  const selected = Math.max(0, upcoming.findIndex(event => event.id === selectedId));
  const event = upcoming[selected];
  const quiet = reduce !== false || compact || paused;
  const autoplayEnabled = !autoplayStopped && !reduce && !paused && upcoming.length > 1;
  const autoplayRunning = autoplayEnabled && !hoveringRadar && inView && pageVisible;
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const softX = useSpring(x, { stiffness: 70, damping: 23 });
  const softY = useSpring(y, { stiffness: 70, damping: 23 });
  const rotateX = useTransform(softY, [-1, 1], [2, -2]);
  const rotateY = useTransform(softX, [-1, 1], [-3, 3]);
  const offsetX = useTransform(softX, [-1, 1], [-12, 12]);
  const offsetY = useTransform(softY, [-1, 1], [-7, 7]);
  const { scrollYProgress } = useScroll({ target: panel, offset: ["start start", "end start"] });
  const scrollLift = useTransform(scrollYProgress, [0, 1], [0, 75]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px), (pointer: coarse)");
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => { if (quiet) { x.set(0); y.set(0); } }, [quiet, x, y]);

  useEffect(() => {
    const updateDay = () => setToday(todayInRome());
    updateDay();
    const timer = window.setInterval(updateDay, 60_000);
    document.addEventListener("visibilitychange", updateDay);
    window.addEventListener("pageshow", updateDay);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", updateDay);
      window.removeEventListener("pageshow", updateDay);
    };
  }, []);

  useEffect(() => {
    const updateVisibility = () => setPageVisible(document.visibilityState === "visible");
    updateVisibility();
    document.addEventListener("visibilitychange", updateVisibility);
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: .15 });
    if (panel.current) observer.observe(panel.current);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", updateVisibility); };
  }, []);

  useEffect(() => {
    if (!autoplayRunning) return;
    const timer = window.setTimeout(() => setSelectedId(upcoming[(selected + 1) % upcoming.length].id), RADAR_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [autoplayRunning, selected, upcoming]);

  function stopOnInteraction(interaction: PointerEvent<HTMLDivElement> | FocusEvent<HTMLDivElement>) {
    // The explicit playback button controls itself; all other interactions stop
    // rotation for this visit, including keyboard focus and a tap on the card.
    if (!(interaction.target as Element).closest("[data-radar-playback]")) setAutoplayStopped(true);
  }

  function selectEvent(index: number) { setAutoplayStopped(true); setSelectedId(upcoming[index]?.id ?? null); }

  function move(pointer: PointerEvent<HTMLDivElement>) {
    if (quiet || pointer.pointerType !== "mouse" || !panel.current) return;
    const bounds = panel.current.getBoundingClientRect();
    x.set(((pointer.clientX - bounds.left) / bounds.width - .5) * 2);
    y.set(((pointer.clientY - bounds.top) / bounds.height - .5) * 2);
  }

  return (
    <div ref={panel} className="hero-panel cinematic-hero" data-motion={quiet ? "quiet" : "active"} onPointerMove={move} onPointerLeave={() => { x.set(0); y.set(0); }}>
      {children}
      <div className="hero-stage">
        <motion.div className="stage-depth" style={quiet ? undefined : { y: scrollLift }} aria-hidden="true">
          <div className="stage-blueprint"><span>MI</span><span>45.4642° N / 9.1900° E</span></div>
          <motion.div className="stage-city" style={quiet ? undefined : { x: offsetX, y: offsetY, rotateX, rotateY }}>
            <Image src="/milano-hero.webp" alt="" width={1254} height={1254} priority sizes="(max-width: 760px) 100vw, 65vw" className="stage-city-image" />
          </motion.div>
          <div className="stage-fade" />
          <svg className="stage-orbits" viewBox="0 0 700 620" fill="none">
            <path className="orbit-guideline" d="M82 350h20m540 0h20M370 54v20m0 505v20" />
          </svg>
          <span className="stage-watermark">MILANO.</span>
        </motion.div>
        {event && <>
          <motion.div className="radar-callouts" role="group" aria-label="Evento in evidenza nel radar" data-callout-motion={reduce !== false || paused ? "off" : "on"} style={{ ...({ "--radar-duration": `${RADAR_INTERVAL_MS}ms` } as CSSProperties), y: quiet ? 0 : scrollLift }} onPointerDownCapture={stopOnInteraction} onFocusCapture={stopOnInteraction}>
            <motion.div key={event.id} style={{ ...radarPosition(selected), ...(quiet ? {} : { x: offsetX, y: offsetY }) }} className={`radar-callout radar-callout-${selected}`}>
              <span className="radar-callout-stem" aria-hidden="true" />
              <svg className="radar-callout-origin" viewBox="0 0 18 18" fill="none" aria-hidden="true" data-running={autoplayRunning}>
                <circle className="radar-timer-track" cx="9" cy="9" r="6.5" />
                <circle className="radar-callout-dot" cx="9" cy="9" r="2" />
                {autoplayRunning && <circle key={`${event.id}-${today}`} className="radar-timer-progress" cx="9" cy="9" r="6.5" pathLength="1" transform="rotate(-90 9 9)" />}
              </svg>
              <button type="button" className="radar-callout-label" aria-label={`Mantieni in evidenza ${event.title}, ${event.dateCompact}`} aria-pressed={!autoplayEnabled} onClick={() => selectEvent(selected)}>
                <span>{event.day} {event.month}</span>
              </button>
            </motion.div>
          </motion.div>
          <div className="radar-preview" data-autoplay={autoplayRunning ? "running" : "paused"} onPointerDownCapture={stopOnInteraction} onFocusCapture={stopOnInteraction} onPointerEnter={pointer => setHoveringRadar(pointer.pointerType === "mouse")} onPointerLeave={() => setHoveringRadar(false)}>
            <div className="radar-preview-head"><span><i />PROSSIMI NEL RADAR</span><span>{String(selected + 1).padStart(2, "0")} / {String(upcoming.length).padStart(2, "0")}</span></div>
            <div aria-live={autoplayEnabled ? "off" : "polite"} aria-atomic="true"><motion.div key={event.id} initial={quiet ? false : { opacity: .5, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: quiet ? 0 : .2 }} className="radar-event">
              <p className="radar-event-meta">{event.dateCompact} <span>·</span> {event.location}</p>
              <h2>{event.detailPath ? <Link href={event.detailPath}>{event.title}<Arrow direction="up" /></Link> : <a href={event.url} target="_blank" rel="noopener noreferrer">{event.title}<Arrow direction="up" /><span className="sr-only"> (nuova scheda)</span></a>}</h2>
            </motion.div></div>
            <div className="radar-preview-foot">
              {event.detailPath ? <Link href={event.detailPath}>La scheda <Arrow direction="up" /></Link> : <a href={event.url} target="_blank" rel="noopener noreferrer">Scopri <Arrow direction="up" /><span className="sr-only">la sfida (nuova scheda)</span></a>}
              <div>
                <button type="button" aria-label="Evento precedente nel radar" onClick={() => selectEvent((selected + upcoming.length - 1) % upcoming.length)}><Arrow direction="left" /></button>
                {!reduce && upcoming.length > 1 && <button type="button" data-radar-playback aria-label={autoplayEnabled ? "Metti in pausa lo scorrimento automatico" : "Riprendi lo scorrimento automatico"} title={autoplayEnabled ? "Avanza ogni 7 secondi · Metti in pausa" : "Riprendi lo scorrimento automatico"} onClick={() => { setAutoplayStopped(autoplayEnabled); if (paused) setPaused(false); }}><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" aria-hidden="true">{autoplayEnabled ? <path d="M5 3v10m6-10v10" /> : <path d="m5 3 7 5-7 5V3Z" />}</svg></button>}
                <button type="button" aria-label="Evento successivo nel radar" onClick={() => selectEvent((selected + 1) % upcoming.length)}><Arrow /></button>
              </div>
            </div>
          </div>
        </>}
        <div className="stage-caption"><span className="stage-caption-cross" aria-hidden="true" /> UNA CITTÀ. INFINITE POSSIBILITÀ.</div>
      </div>
      <div className="hero-bottom"><span><span className="hero-count">{String(events.length).padStart(2, "0")}</span> opportunità da esplorare</span><div className="hero-bottom-actions">{!compact && !reduce && <button type="button" className="scene-motion-toggle" aria-pressed={!paused} aria-label="Movimento della scena" onClick={() => setPaused(value => !value)}><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" aria-hidden="true">{paused ? <path d="m5 3 7 5-7 5V3Z" /> : <path d="M5 3v10m6-10v10" />}</svg>{paused ? "Movimento disattivato" : "Scena interattiva"}</button>}<a href="#events">Esplora gli eventi <span aria-hidden="true">↓</span></a></div></div>
    </div>
  );
}
