"use client";
import { useEffect } from "react";

/** Micro-interazioni globali: reveal on scroll, count-up, nav state,
 *  scroll progress, rail della sezione 01. Markup server-rendered,
 *  comportamento montato qui (niente contenuto nascosto senza JS). */
export default function Fx() {
  useEffect(() => {
    const doc = document;
    doc.body.classList.add("js");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const clamp = (n: number, a: number, b: number) => Math.max(a, Math.min(b, n));
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);
    const cleanups: Array<() => void> = [];

    /* reveal */
    const reveals = Array.from(doc.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (reduce || !("IntersectionObserver" in window)) {
      reveals.forEach((el) => el.classList.add("in"));
    } else {
      const io = new IntersectionObserver(
        (es) => {
          es.forEach((e) => {
            if (e.isIntersecting) {
              const el = e.target as HTMLElement;
              el.style.transitionDelay = (parseFloat(el.dataset.delay || "0") || 0) + "ms";
              el.classList.add("in");
              io.unobserve(el);
            }
          });
        },
        { threshold: 0.12, rootMargin: "0px 0px -6% 0px" },
      );
      const vh0 = window.innerHeight;
      reveals.forEach((el) => {
        if (el.getBoundingClientRect().top < vh0) el.classList.add("in");
        else io.observe(el);
      });
      cleanups.push(() => io.disconnect());
    }

    /* count-up */
    const countUp = (el: HTMLElement) => {
      const target = parseFloat(el.dataset.count || "");
      if (isNaN(target)) return;
      const suffix = el.dataset.suffix || "";
      const dur = 1100;
      let t0: number | null = null;
      const step = (ts: number) => {
        if (t0 === null) t0 = ts;
        const p = clamp((ts - t0) / dur, 0, 1);
        el.textContent = Math.round(target * ease(p)) + suffix;
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    const counters = Array.from(doc.querySelectorAll<HTMLElement>("[data-count]"));
    if (reduce || !("IntersectionObserver" in window)) counters.forEach(countUp);
    else {
      const io2 = new IntersectionObserver(
        (es) => es.forEach((e) => { if (e.isIntersecting) { countUp(e.target as HTMLElement); io2.unobserve(e.target); } }),
        { threshold: 0.6 },
      );
      counters.forEach((el) => io2.observe(el));
      cleanups.push(() => io2.disconnect());
    }

    /* hero entrance gate (l'intro orbitale sta sopra: parte solo a vista) */
    const hero = doc.querySelector<HTMLElement>(".hero");
    if (hero) {
      if (reduce || !("IntersectionObserver" in window)) hero.classList.add("seen");
      else {
        const ioh = new IntersectionObserver(
          (es) => es.forEach((e) => { if (e.isIntersecting) { hero.classList.add("seen"); ioh.disconnect(); } }),
          { threshold: 0.18 },
        );
        ioh.observe(hero);
        cleanups.push(() => ioh.disconnect());
      }
    }

    /* scroll: nav, progress, rail */
    const nav = doc.getElementById("nav");
    const prog = doc.getElementById("scroll-progress");
    const system = doc.getElementById("system");
    const railFill = doc.getElementById("rail-fill");
    const railSteps = Array.from(doc.querySelectorAll<HTMLElement>("[data-step]"));
    const update = () => {
      if (nav) nav.classList.toggle("is-scrolled", window.scrollY > 24);
      if (prog) {
        const h = doc.documentElement.scrollHeight - window.innerHeight;
        prog.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + "%";
      }
      if (system) {
        const r = system.getBoundingClientRect();
        const vh = window.innerHeight || 1;
        // parte quando la sezione entra (top al 95% vh) e completa solo quando
        // il fondo della sezione arriva a meta' viewport: segue la lettura,
        // non brucia tutte le fasi al primo scroll
        const p = clamp((vh * 0.95 - r.top) / Math.max(1, r.height + vh * 0.4), 0, 1);
        if (railFill) {
          const vertical = window.innerWidth <= 1000;
          railFill.style.transform = vertical ? `scaleY(${p})` : `scaleX(${p})`;
        }
        railSteps.forEach((el, i) => el.classList.toggle("on", p > (i + 0.35) / railSteps.length));
      }
    };
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(() => { ticking = false; update(); });
      }
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    cleanups.push(() => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    });

    return () => cleanups.forEach((fn) => fn());
  }, []);
  return null;
}
