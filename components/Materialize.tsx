"use client";
import { useEffect, useRef } from "react";

/** Titolo che si materializza da particelle. Campionamento glifo-per-glifo
 *  con il letter-spacing computato del DOM (allineamento esatto) su canvas
 *  con margine anti-clipping. Parte solo quando il titolo e' visibile. */
export default function Materialize({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const span = ref.current;
    if (!span) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const cv = document.createElement("canvas");
    cv.className = "materialize-canvas";
    cv.setAttribute("aria-hidden", "true");
    span.appendChild(cv);
    const ctx = cv.getContext("2d");
    if (!ctx) { cv.remove(); return; }

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const clamp = (n: number, a: number, b: number) => Math.max(a, Math.min(b, n));
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);
    type P = { tx: number; ty: number; sx: number; sy: number; delay: number; dur: number; c: number };
    let parts: P[] = [];
    let started = 0, maxEnd = 0, done = false, ready = false, dead = false;
    let padX = 0, padY = 0;

    const col = (c: number, a: number) =>
      c === 1 ? `rgba(124,160,255,${a})` : c === 2 ? `rgba(38,214,150,${a})` : `rgba(245,247,252,${a})`;

    function build(): boolean {
      if (!span) return false;
      const sw = span.clientWidth, sh = span.clientHeight;
      if (sw < 12 || sh < 12) return false;
      padX = sw * 0.12; padY = sh * 0.18;
      const w = sw + padX * 2, h = sh + padY * 2;
      cv.width = Math.floor(w * dpr); cv.height = Math.floor(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);

      const off = document.createElement("canvas");
      off.width = Math.max(1, Math.round(w)); off.height = Math.max(1, Math.round(h));
      const o = off.getContext("2d");
      if (!o) return false;
      const cs = getComputedStyle(span);
      const fs = parseFloat(cs.fontSize) || 80;
      let ls = parseFloat(cs.letterSpacing); if (isNaN(ls)) ls = 0;
      o.fillStyle = "#fff";
      o.textBaseline = "alphabetic";
      o.font = `${cs.fontStyle || "normal"} ${cs.fontWeight || "700"} ${fs}px ${cs.fontFamily}`;

      const widths: number[] = [];
      let total = 0;
      for (let i = 0; i < text.length; i++) {
        widths.push(o.measureText(text[i]).width);
        total += widths[i] + (i < text.length - 1 ? ls : 0);
      }
      const m = o.measureText(text);
      const asc = m.actualBoundingBoxAscent || fs * 0.72;
      const desc = m.actualBoundingBoxDescent || fs * 0.2;
      const gx = padX + Math.max(0, (sw - total) / 2);
      const gy = padY + (sh - (asc + desc)) / 2 + asc;
      let x = gx;
      for (let i = 0; i < text.length; i++) { o.fillText(text[i], x, gy); x += widths[i] + ls; }

      let data: Uint8ClampedArray;
      try { data = o.getImageData(0, 0, off.width, off.height).data; } catch { return false; }
      const step = clamp(Math.round(fs / 17), 3, 8);
      let tg: Array<[number, number]> = [];
      for (let y = 0; y < off.height; y += step)
        for (let xx = 0; xx < off.width; xx += step)
          if (data[(y * off.width + xx) * 4 + 3] > 135) tg.push([xx, y]);
      while (tg.length > 1900) tg = tg.filter((_, k) => k % 2 === 0);
      if (!tg.length) return false;

      parts = tg.map((t, idx) => {
        const ang = Math.random() * 6.2832;
        const rad = 44 + Math.random() * Math.max(w, h) * 0.72;
        return {
          tx: t[0], ty: t[1],
          sx: t[0] + Math.cos(ang) * rad,
          sy: t[1] + Math.sin(ang) * rad * 0.62 + Math.random() * 40,
          delay: ((t[0] - padX) / sw) * 300 + Math.random() * 160,
          dur: 640 + Math.random() * 380,
          c: idx % 14 === 0 ? 1 : idx % 26 === 0 ? 2 : 0,
        };
      });
      maxEnd = parts.reduce((mx, p) => Math.max(mx, p.delay + p.dur), 0);
      started = performance.now(); done = false; ready = true;
      span.classList.add("is-animating");
      return true;
    }

    function frame(now: number) {
      if (dead) return;
      if (!ready) { requestAnimationFrame(frame); return; }
      const w = cv.width / dpr, h = cv.height / dpr;
      ctx!.clearRect(0, 0, w, h);
      ctx!.globalCompositeOperation = "lighter";
      const t = now - started;
      if (!done) {
        for (const p of parts) {
          const lt = clamp((t - p.delay) / p.dur, 0, 1);
          const e = ease(lt);
          ctx!.fillStyle = col(p.c, clamp(lt * 1.25, 0, 1) * 0.92);
          ctx!.fillRect(p.sx + (p.tx - p.sx) * e, p.sy + (p.ty - p.sy) * e, 1.5, 1.5);
        }
        if (t > maxEnd + 90) { done = true; span!.classList.remove("is-animating"); }
      } else {
        const s = now * 0.001;
        parts.forEach((q, j) => {
          const aa = Math.max(0, 0.05 + (q.c ? 0.06 : 0) + Math.sin(s * 1.8 + j) * 0.02);
          ctx!.fillStyle = col(q.c, aa);
          ctx!.fillRect(q.tx + Math.sin(s * 1.2 + j * 0.5) * 0.5, q.ty + Math.cos(s * 1.05 + j * 0.7) * 0.5, 1.1, 1.1);
        });
      }
      ctx!.globalCompositeOperation = "source-over";
      requestAnimationFrame(frame);
    }

    let tries = 0;
    const attempt = () => {
      if (dead) return;
      if (build()) requestAnimationFrame(frame);
      else if (tries++ < 32) setTimeout(attempt, 110);
    };
    const start = () => {
      if (document.fonts?.ready) document.fonts.ready.then(attempt);
      else attempt();
    };
    let iom: IntersectionObserver | null = null;
    if (!("IntersectionObserver" in window)) start();
    else {
      iom = new IntersectionObserver(
        (es) => es.forEach((e) => { if (e.isIntersecting) { iom!.disconnect(); start(); } }),
        { threshold: 0.3 },
      );
      iom.observe(span);
    }
    let rz: ReturnType<typeof setTimeout>;
    const onResize = () => {
      clearTimeout(rz);
      rz = setTimeout(() => {
        const was = done;
        if (ready && build() && was) { done = true; span!.classList.remove("is-animating"); }
      }, 220);
    };
    window.addEventListener("resize", onResize, { passive: true });

    return () => {
      dead = true;
      iom?.disconnect();
      window.removeEventListener("resize", onResize);
      clearTimeout(rz);
      cv.remove();
      span.classList.remove("is-animating");
    };
  }, [text]);

  return (
    <span ref={ref} className="materialize">
      {text}
    </span>
  );
}
