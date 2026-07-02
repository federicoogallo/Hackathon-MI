"use client";
import { useEffect, useRef } from "react";

/** Campo particellare ambientale dell'hero (in pausa quando off-screen). */
export default function HeroCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const mouse = { x: 0.72, y: 0.4 };
    type P = { x: number; y: number; vx: number; vy: number; r: number };
    const pts: P[] = [];
    const n = window.innerWidth < 720 ? 42 : 78;
    for (let i = 0; i < n; i++) {
      pts.push({
        x: Math.random(), y: Math.random(),
        vx: (Math.random() - 0.5) * 0.00028, vy: (Math.random() - 0.5) * 0.00028,
        r: Math.random() * 1.6 + 0.5,
      });
    }
    let running = false, rafId = 0, dead = false;
    const draw = () => {
      if (dead || !running) return;
      const r = cv.getBoundingClientRect();
      const d = Math.min(window.devicePixelRatio || 1, 2);
      cv.width = Math.max(1, Math.floor(r.width * d));
      cv.height = Math.max(1, Math.floor(r.height * d));
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(d, 0, 0, d, 0, 0);
      const w = r.width, h = r.height;
      ctx.clearRect(0, 0, w, h);
      const px = (mouse.x - 0.5) * 26, py = (mouse.y - 0.5) * 20;
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > 1) p.vx *= -1;
        if (p.y < 0 || p.y > 1) p.vy *= -1;
        const x = p.x * w + px, y = p.y * h + py;
        for (let j = i + 1; j < pts.length; j++) {
          const q = pts[j];
          const dist = Math.hypot((p.x - q.x) * w, (p.y - q.y) * h);
          if (dist < 118) {
            ctx.strokeStyle = `rgba(61,107,255,${0.14 * (1 - dist / 118)})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(q.x * w + px, q.y * h + py);
            ctx.stroke();
          }
        }
        ctx.fillStyle = i % 7 === 0 ? "rgba(124,160,255,.85)" : "rgba(190,205,245,.45)";
        ctx.beginPath();
        ctx.arc(x, y, p.r, 0, 6.2832);
        ctx.fill();
      }
      rafId = requestAnimationFrame(draw);
    };
    const io = new IntersectionObserver((es) => {
      es.forEach((e) => {
        if (e.isIntersecting && !running) { running = true; rafId = requestAnimationFrame(draw); }
        else if (!e.isIntersecting && running) { running = false; cancelAnimationFrame(rafId); }
      });
    }, { threshold: 0 });
    io.observe(cv);
    const onMove = (e: PointerEvent) => {
      mouse.x = e.clientX / (window.innerWidth || 1);
      mouse.y = e.clientY / (window.innerHeight || 1);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      dead = true;
      cancelAnimationFrame(rafId);
      io.disconnect();
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  return <canvas ref={ref} className="hero-canvas" aria-hidden="true" />;
}
