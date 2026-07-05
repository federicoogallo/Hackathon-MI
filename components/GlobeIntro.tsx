"use client";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { feature } from "topojson-client";
import landTopo from "world-atlas/land-110m.json";
import countriesTopo from "world-atlas/countries-110m.json";

/**
 * Intro scrubbed dallo scroll, tutta "di design" e senza servizi a pagamento:
 * Terra notturna (texture NASA Black Marble, pubblico dominio, servita dal
 * repo) su sfondo OLED-dark coerente col brand -> l'Italia si sottolinea in
 * smeraldo -> lock-on Lombardia -> crossfade nella Milano 3D al crepuscolo
 * (isolati, luci stradali e finestre accese) -> arco cinematico sul Duomo 3D
 * in marmo illuminato con la Madonnina dorata. Reversibile, reduced-motion
 * safe; senza texture/WebGL resta il globo a puntini.
 */
const GMAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "";
// Duomo di Milano: geometria reale per l'inquadratura frontale.
// Bearing 250 deg = direzione verso cui GUARDA la facciata (WSW, verso la
// piazza), ricavata dall'asse facciata->abside reale; la camera finale sta a
// questo bearing dal centro, quindi in piazza, e guarda la facciata.
// Mira del finale sul Duomo; la camera sta nella piazza (a ovest) e guarda a
// est la facciata. Valori tarati visivamente sui tile reali di Google.
const DUOMO = { lat: 45.46421, lon: 9.19168, facadeBearing: 256 };

export default function GlobeIntro() {
  const [off, setOff] = useState(false);
  const wrapRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const hintRef = useRef<HTMLDivElement>(null);
  const skipRef = useRef<HTMLButtonElement>(null);
  const attribRef = useRef<HTMLDivElement>(null);
  const gradeRef = useRef<HTMLDivElement>(null);
  const tilesCanvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (location.hash) { setOff(true); return; }

    try {
    let dead = false; // il cleanup dell'effect ferma loop e init asincroni
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch {
      setOff(true);
      return;
    }

    /* ---------- land polygons -> griglie di punti ---------- */
    type Ring = { pts: number[][]; minX: number; minY: number; maxX: number; maxY: number };
    const rings: Ring[] = [];
    try {
      /* eslint-disable @typescript-eslint/no-explicit-any */
      const topo: any = landTopo;
      const fc: any = feature(topo, topo.objects.land);
      const feats: any[] = fc.type === "FeatureCollection" ? fc.features : [fc];
      feats.forEach((f: any) => {
        const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
        polys.forEach((poly: number[][][]) => {
          poly.forEach((ring: number[][]) => {
            let minX = 999, minY = 999, maxX = -999, maxY = -999;
            for (const p of ring) {
              if (p[0] < minX) minX = p[0];
              if (p[0] > maxX) maxX = p[0];
              if (p[1] < minY) minY = p[1];
              if (p[1] > maxY) maxY = p[1];
            }
            rings.push({ pts: ring, minX, minY, maxX, maxY });
          });
        });
      });
      if (!rings.length) throw new Error("no land");
    } catch {
      renderer.dispose();
      setOff(true);
      return;
    }

    const inLand = (lon: number, lat: number): boolean => {
      let inside = false;
      for (const g of rings) {
        if (lon < g.minX || lon > g.maxX || lat < g.minY || lat > g.maxY) continue;
        const pts = g.pts;
        for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
          const xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
          if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
        }
      }
      return inside;
    };

    const R = 1;
    const v3 = (lat: number, lon: number, r: number) => {
      const la = (lat * Math.PI) / 180, lo = (lon * Math.PI) / 180;
      return new THREE.Vector3(r * Math.cos(la) * Math.cos(lo), r * Math.sin(la), -r * Math.cos(la) * Math.sin(lo));
    };
    const MILAN = { lat: 45.4642, lon: 9.19 };
    const milanDir = v3(MILAN.lat, MILAN.lon, 1).normalize();

    // RNG deterministico per un layout urbano stabile
    let seed = 20260702;
    const rand = () => {
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };

    const mobile = window.innerWidth < 640;
    const buildDots = (latStep: number, latMin: number, latMax: number, lonMin: number, lonMax: number, radius: number) => {
      const pos: number[] = [];
      for (let lat = latMin; lat <= latMax; lat += latStep) {
        const c = Math.max(0.12, Math.cos((lat * Math.PI) / 180));
        const lonStep = latStep / c;
        for (let lon = lonMin; lon <= lonMax; lon += lonStep) {
          if (inLand(lon, lat)) {
            const v = v3(lat, lon, radius);
            pos.push(v.x, v.y, v.z);
          }
        }
      }
      return new Float32Array(pos);
    };
    const globalDots = buildDots(mobile ? 1.35 : 0.95, -56, 84, -180, 180, R + 0.002);

    /* ---------- scena base ---------- */
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.002, 30);
    camera.position.set(0, 0, 3.2);
    const globe = new THREE.Group();
    scene.add(globe);

    const oceanMat = new THREE.MeshBasicMaterial({ color: 0x0b1120 });
    globe.add(new THREE.Mesh(new THREE.SphereGeometry(R * 0.996, 96, 96), oceanMat));

    // graticola sottile
    const gratGeo = (() => {
      const seg = 120, pts: number[] = [];
      const push = (a: THREE.Vector3, b: THREE.Vector3) => pts.push(a.x, a.y, a.z, b.x, b.y, b.z);
      for (let lat = -60; lat <= 60; lat += 30)
        for (let i = 0; i < seg; i++)
          push(v3(lat, (i / seg) * 360 - 180, R * 1.001), v3(lat, ((i + 1) / seg) * 360 - 180, R * 1.001));
      const mPt = (t: number, lon: number) => {
        const lat = t <= 180 ? t - 90 : 270 - t;
        return v3(lat, t <= 180 ? lon : lon + 180, R * 1.001);
      };
      for (let lon = 0; lon < 180; lon += 30)
        for (let i = 0; i < seg; i++)
          push(mPt((i / seg) * 360, lon), mPt(((i + 1) / seg) * 360, lon));
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts), 3));
      return g;
    })();
    const graticule = new THREE.LineSegments(
      gratGeo,
      new THREE.LineBasicMaterial({ color: 0x4a6fd8, transparent: true, opacity: 0.08, depthWrite: false }),
    );
    globe.add(graticule);

    const dotTex = (() => {
      const c = document.createElement("canvas");
      c.width = c.height = 64;
      const g = c.getContext("2d")!;
      const grad = g.createRadialGradient(32, 32, 4, 32, 32, 30);
      grad.addColorStop(0, "rgba(255,255,255,1)");
      grad.addColorStop(0.65, "rgba(255,255,255,.9)");
      grad.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = grad;
      g.beginPath();
      g.arc(32, 32, 30, 0, 6.2832);
      g.fill();
      return new THREE.CanvasTexture(c);
    })();
    const pointCloud = (arr: Float32Array, color: number, size: number, opacity: number) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
      return new THREE.Points(
        g,
        new THREE.PointsMaterial({ color, size, sizeAttenuation: true, transparent: true, opacity, depthWrite: false, map: dotTex, alphaTest: 0.04 }),
      );
    };
    const coarse = pointCloud(globalDots, 0x7ca0ff, 0.0105, 0.85);
    globe.add(coarse);

    /* ---------- narrativa progressiva: Italia -> Lombardia -> Milano ---------- */
    // atto 2a: l'Italia si "sottolinea" (contorno + riempimento a punti, verde segnale)
    let italyOutline: THREE.LineSegments | null = null;
    let italyFill: THREE.Points | null = null;
    try {
      const cfc: any = feature(countriesTopo as any, (countriesTopo as any).objects.countries);
      const italy = (cfc.features || []).find(
        (f: any) => String(f.id) === "380" || f?.properties?.name === "Italy",
      );
      if (italy) {
        const polys = italy.geometry.type === "Polygon" ? [italy.geometry.coordinates] : italy.geometry.coordinates;
        const seg: number[] = [];
        const itRings: Ring[] = [];
        polys.forEach((poly: number[][][]) => {
          poly.forEach((ring: number[][]) => {
            let minX = 999, minY = 999, maxX = -999, maxY = -999;
            for (const pt of ring) {
              if (pt[0] < minX) minX = pt[0];
              if (pt[0] > maxX) maxX = pt[0];
              if (pt[1] < minY) minY = pt[1];
              if (pt[1] > maxY) maxY = pt[1];
            }
            itRings.push({ pts: ring, minX, minY, maxX, maxY });
            for (let i = 0; i < ring.length - 1; i++) {
              const a = v3(ring[i][1], ring[i][0], R * 1.0028);
              const b = v3(ring[i + 1][1], ring[i + 1][0], R * 1.0028);
              seg.push(a.x, a.y, a.z, b.x, b.y, b.z);
            }
          });
        });
        const og = new THREE.BufferGeometry();
        og.setAttribute("position", new THREE.BufferAttribute(new Float32Array(seg), 3));
        italyOutline = new THREE.LineSegments(og, new THREE.LineBasicMaterial({
          color: 0x2fe3a7, transparent: true, opacity: 0, depthWrite: false,
        }));
        globe.add(italyOutline);
        const inItaly = (lon: number, lat: number): boolean => {
          let inside = false;
          for (const g of itRings) {
            if (lon < g.minX || lon > g.maxX || lat < g.minY || lat > g.maxY) continue;
            const pts = g.pts;
            for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
              const xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
              if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
            }
          }
          return inside;
        };
        const fill: number[] = [];
        for (let lat = 36.6; lat <= 47.2; lat += 0.3) {
          const lonStep = 0.3 / Math.max(0.4, Math.cos((lat * Math.PI) / 180));
          for (let lon = 6.5; lon <= 18.7; lon += lonStep) {
            if (inItaly(lon, lat)) {
              const v = v3(lat, lon, R * 1.0026);
              fill.push(v.x, v.y, v.z);
            }
          }
        }
        italyFill = pointCloud(new Float32Array(fill), 0x8fe8c8, 0.0036, 0);
        globe.add(italyFill);
      }
    } catch { /* niente evidenziazione Italia: il resto dell'intro regge */ }

    // atto 2b: lock-on HUD sulla Lombardia (anello ad archi con tacche, rotante)
    const lombGroup = new THREE.Group();
    const lombMat = new THREE.LineBasicMaterial({ color: 0x2fe3a7, transparent: true, opacity: 0, depthWrite: false });
    {
      const lombC = v3(45.65, 9.6, 1).normalize();
      const rr = Math.sin((1.45 * Math.PI) / 180); // raggio angolare ~1.45 gradi
      const seg: number[] = [];
      const n = 72;
      for (const r2 of [rr, rr * 0.975]) { // doppio tratto = spessore percepito
        for (let i = 0; i < n; i++) {
          if (i % 18 >= 15) continue; // archi con varchi, stile HUD
          const a1 = (i / n) * 6.2832, a2 = ((i + 1) / n) * 6.2832;
          seg.push(Math.cos(a1) * r2, Math.sin(a1) * r2, 0, Math.cos(a2) * r2, Math.sin(a2) * r2, 0);
        }
      }
      for (let k = 0; k < 4; k++) { // tacche cardinali
        const a = (k / 4) * 6.2832 + 0.7854;
        seg.push(Math.cos(a) * rr * 1.06, Math.sin(a) * rr * 1.06, 0, Math.cos(a) * rr * 1.22, Math.sin(a) * rr * 1.22, 0);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(seg), 3));
      lombGroup.add(new THREE.LineSegments(g, lombMat));
      lombGroup.position.copy(lombC).multiplyScalar(R * 1.004);
      lombGroup.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), lombC);
      globe.add(lombGroup);
    }

    // marker + anello (fase di avvicinamento, poi lascia il posto alla citta')
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(0.003, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 }),
    );
    marker.position.copy(milanDir).multiplyScalar(R + 0.004);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.012, 0.0138, 40),
      new THREE.MeshBasicMaterial({ color: 0x3d6bff, transparent: true, opacity: 0, side: THREE.DoubleSide }),
    );
    ring.position.copy(milanDir).multiplyScalar(R + 0.004);
    ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), milanDir);
    globe.add(marker, ring);

    /* ---------- base ortonormale su Milano (nord in alto) ---------- */
    const Z = new THREE.Vector3(0, 0, 1);
    const pole = new THREE.Vector3(0, 1, 0);
    const e3 = milanDir.clone();
    const e2 = pole.clone().sub(e3.clone().multiplyScalar(pole.dot(e3))).normalize();
    const e1 = new THREE.Vector3().crossVectors(e2, e3).normalize();
    const basis = new THREE.Matrix4().makeBasis(e1, e2, e3);
    const qMilan = new THREE.Quaternion().setFromRotationMatrix(basis).invert();
    // partenza: alta orbita sull'Europa illuminata (non il polo buio)
    // vista d'apertura: Atlantico, con Europa/Africa a destra e le Americhe a
    // sinistra (di notte le loro luci sono ben visibili), poi si ruota su Milano
    const qPole = new THREE.Quaternion().setFromUnitVectors(v3(33, -36, 1).normalize(), Z);
    const qSpin = new THREE.Quaternion(), qA = new THREE.Quaternion(), qOut = new THREE.Quaternion();
    let spin = 0;

    /* ---------- citta' 3D: diorama di Milano ---------- */
    // materiali da dissolvere con cityO (fattore k per intensita' relative)
    const fadeMats: Array<{ m: THREE.Material; k: number }> = [];
    const fm = <T extends THREE.Material>(m: T, k = 1): T => {
      m.transparent = true;
      (m as THREE.Material & { opacity: number }).opacity = 0;
      fadeMats.push({ m, k });
      return m;
    };

    const cityG = new THREE.Group();
    cityG.position.copy(milanDir).multiplyScalar(R + 0.0008);
    cityG.quaternion.setFromRotationMatrix(basis);
    const S = 0.16;
    cityG.scale.setScalar(S);
    globe.add(cityG);

    // luci: sole caldo basso da sud-ovest + ambiente freddo
    const amb = new THREE.AmbientLight(0x36436a, 1.25);
    const sun = new THREE.DirectionalLight(0xffc9a0, 1.35); // sole basso, luce dorata
    sun.position.copy(milanDir.clone().multiplyScalar(1.4).add(e1.clone().multiplyScalar(-0.5)).add(e2.clone().multiplyScalar(-0.4)));
    sun.target.position.copy(milanDir);
    const fill = new THREE.DirectionalLight(0x3d6bff, 0.8); // controluce blu elettrico
    fill.position.copy(milanDir.clone().multiplyScalar(1.4).add(e1.clone().multiplyScalar(0.5)).add(e2.clone().multiplyScalar(0.45)));
    fill.target = sun.target;
    scene.add(amb, sun, sun.target, fill);

    // suolo con bordo dissolto
    const groundTex = (() => {
      const c = document.createElement("canvas");
      c.width = c.height = 256;
      const g = c.getContext("2d")!;
      const grad = g.createRadialGradient(128, 128, 20, 128, 128, 128);
      grad.addColorStop(0, "rgba(13,21,38,1)");
      grad.addColorStop(0.7, "rgba(13,21,38,.95)");
      grad.addColorStop(1, "rgba(13,21,38,0)");
      g.fillStyle = grad;
      g.fillRect(0, 0, 256, 256);
      return new THREE.CanvasTexture(c);
    })();
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(1.4, 64),
      fm(new THREE.MeshBasicMaterial({ map: groundTex, depthWrite: false }), 1),
    );
    cityG.add(ground);

    // trama stradale: cerchie concentriche + radiali (impianto milanese)
    {
      const pts: number[] = [];
      const ringR = [0.3, 0.55, 0.82, 1.1];
      for (const r of ringR) {
        const n = 100;
        for (let i = 0; i < n; i++) {
          const a1 = (i / n) * 6.2832, a2 = ((i + 1) / n) * 6.2832;
          pts.push(Math.cos(a1) * r, Math.sin(a1) * r, 0.002, Math.cos(a2) * r, Math.sin(a2) * r, 0.002);
        }
      }
      for (let k = 0; k < 12; k++) {
        const a = (k / 12) * 6.2832 + 0.13;
        pts.push(Math.cos(a) * 0.3, Math.sin(a) * 0.3, 0.002, Math.cos(a) * 1.28, Math.sin(a) * 1.28, 0.002);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts), 3));
      cityG.add(new THREE.LineSegments(g, fm(new THREE.LineBasicMaterial({ color: 0x4a6fd8, depthWrite: false }), 0.32)));
    }

    // isolati: instanced boxes orientati radialmente + luci finestra
    {
      type B = { x: number; y: number; a: number; sx: number; sy: number; h: number };
      const blocks: B[] = [];
      for (let r = 0.34; r <= 1.12; r += 0.078) {
        const n = Math.round((6.2832 * r) / 0.088);
        for (let i = 0; i < n; i++) {
          const a = (i / n) * 6.2832 + rand() * 0.05;
          const rr = r + (rand() - 0.5) * 0.035;
          const x = Math.cos(a) * rr, y = Math.sin(a) * rr;
          // lascia libera l'area del Duomo e della piazza
          if (Math.abs(x) < 0.27 && y > -0.7 && y < 0.32) continue;
          if (rand() < 0.16) continue; // respiro urbano
          const rim = Math.max(0, 1 - rr / 1.15);
          blocks.push({
            x, y, a: a + (rand() - 0.5) * 0.3,
            sx: 0.042 + rand() * 0.04,
            sy: 0.042 + rand() * 0.04,
            h: (0.014 + rand() * 0.05) * (0.45 + rim * 0.8),
          });
        }
      }
      const bMat = fm(new THREE.MeshLambertMaterial({ color: 0xffffff }), 0.96);
      const inst = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), bMat, blocks.length);
      const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), pv = new THREE.Vector3();
      const col = new THREE.Color();
      blocks.forEach((b, i) => {
        q.setFromAxisAngle(Z, b.a);
        s.set(b.sx, b.sy, b.h);
        pv.set(b.x, b.y, b.h / 2);
        m4.compose(pv, q, s);
        inst.setMatrixAt(i, m4);
        col.setHSL(0.61 + rand() * 0.03, 0.2, 0.065 + rand() * 0.04);
        inst.setColorAt(i, col);
      });
      inst.instanceMatrix.needsUpdate = true;
      if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
      cityG.add(inst);

      // finestre accese
      const wpts: number[] = [];
      blocks.forEach((b) => {
        const n = 2 + Math.floor(rand() * 4);
        for (let k = 0; k < n; k++) {
          wpts.push(b.x + (rand() - 0.5) * b.sx, b.y + (rand() - 0.5) * b.sy, b.h * (0.35 + rand() * 0.65));
        }
      });
      const wg = new THREE.BufferGeometry();
      wg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(wpts), 3));
      cityG.add(new THREE.Points(wg, fm(new THREE.PointsMaterial({
        color: 0xffc37a, size: 0.0018, sizeAttenuation: true, depthWrite: false, map: dotTex, alphaTest: 0.04,
      }), 1)));
    }

    /* ---------- Duomo 3D (facciata verso sud = lato camera) ---------- */
    const marble = fm(new THREE.MeshLambertMaterial({ color: 0xe9eff9, emissive: 0x38301f }), 1);
    const marbleHi = fm(new THREE.MeshLambertMaterial({ color: 0xf6f9fe, emissive: 0x4a4029 }), 1);
    const duomo = new THREE.Group();
    cityG.add(duomo);
    const box = (w: number, d: number, h: number, x: number, y: number, z: number, mat: THREE.Material) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, d, h), mat);
      m.position.set(x, y, z + h / 2);
      duomo.add(m);
      return m;
    };
    box(0.30, 0.56, 0.052, 0, -0.02, 0, marble);        // corpo basilicale a gradoni
    box(0.15, 0.56, 0.042, 0, -0.02, 0.052, marble);    // navata alta
    box(0.42, 0.14, 0.052, 0, 0.055, 0, marble);        // transetto
    box(0.20, 0.14, 0.042, 0, 0.055, 0.052, marble);    // transetto alto
    box(0.20, 0.08, 0.062, 0, 0.255, 0, marble);        // abside
    box(0.33, 0.022, 0.115, 0, -0.30, 0, marbleHi);     // facciata
    {
      // tiburio + guglia maggiore
      const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.052, 0.052, 0.035, 8), marble);
      drum.rotation.x = Math.PI / 2;
      drum.position.set(0, 0.055, 0.094 + 0.0175);
      const spire = new THREE.Mesh(new THREE.ConeGeometry(0.028, 0.15, 8), marbleHi);
      spire.rotation.x = Math.PI / 2;
      spire.position.set(0, 0.055, 0.129 + 0.075);
      duomo.add(drum, spire);
    }
    // selva di guglie (instanced)
    {
      const gm = fm(new THREE.MeshLambertMaterial({ color: 0xf6f9fe, emissive: 0x4a4029 }), 1);
      const positions: Array<[number, number, number, number]> = []; // x, y, z base, scala
      for (let y = -0.27; y <= 0.23; y += 0.05) {
        positions.push([-0.075, y, 0.094, 1], [0.075, y, 0.094, 1]);
      }
      for (let y = -0.28; y <= 0.24; y += 0.065) {
        positions.push([-0.15, y, 0.052, 0.9], [0.15, y, 0.052, 0.9]);
      }
      for (const x of [-0.15, -0.075, 0, 0.075, 0.15]) positions.push([x, -0.30, 0.115, 1.3]);
      for (const y of [0.0, 0.055, 0.11]) positions.push([-0.21, y, 0.052, 0.9], [0.21, y, 0.052, 0.9]);
      for (const x of [-0.07, 0, 0.07]) positions.push([x, 0.29, 0.062, 0.85]);
      const inst = new THREE.InstancedMesh(new THREE.ConeGeometry(0.004, 0.055, 6), gm, positions.length);
      const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));
      const s = new THREE.Vector3(), pv = new THREE.Vector3();
      positions.forEach(([x, y, zb, sc], i) => {
        s.set(sc, sc, sc);
        pv.set(x, y, zb + 0.0275 * sc);
        m4.compose(pv, q, s);
        inst.setMatrixAt(i, m4);
      });
      inst.instanceMatrix.needsUpdate = true;
      duomo.add(inst);
    }
    // Madonnina dorata
    const goldTex = (() => {
      const c = document.createElement("canvas");
      c.width = c.height = 128;
      const g2 = c.getContext("2d")!;
      const grad = g2.createRadialGradient(64, 64, 2, 64, 64, 62);
      grad.addColorStop(0, "rgba(255,224,150,.95)");
      grad.addColorStop(0.3, "rgba(255,200,90,.45)");
      grad.addColorStop(1, "rgba(255,190,70,0)");
      g2.fillStyle = grad;
      g2.fillRect(0, 0, 128, 128);
      return new THREE.CanvasTexture(c);
    })();
    {
      const gold = new THREE.Mesh(
        new THREE.SphereGeometry(0.009, 12, 12),
        fm(new THREE.MeshBasicMaterial({ color: 0xffd166, depthTest: false }), 1),
      );
      gold.position.set(0, 0.055, 0.287);
      gold.renderOrder = 12;
      const halo = new THREE.Sprite(fm(new THREE.SpriteMaterial({ map: goldTex, depthTest: false }), 0.9));
      halo.position.set(0, 0.055, 0.287);
      halo.scale.set(0.085, 0.085, 1);
      halo.renderOrder = 12;
      duomo.add(gold, halo);
    }
    // piazza del Duomo
    {
      const pz = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.34), fm(new THREE.MeshBasicMaterial({ color: 0x1c2942, depthWrite: false }), 0.9));
      pz.position.set(0, -0.5, 0.003);
      cityG.add(pz);
    }

    /* ---------- atmosfera + stelle ---------- */
    const glowTex = (inner: number, alpha: number) => {
      const c = document.createElement("canvas");
      c.width = c.height = 256;
      const g = c.getContext("2d")!;
      const grad = g.createRadialGradient(128, 128, inner, 128, 128, 128);
      grad.addColorStop(0, "rgba(61,107,255,0)");
      grad.addColorStop(0.72, `rgba(61,107,255,${alpha * 0.45})`);
      grad.addColorStop(0.92, `rgba(124,160,255,${alpha})`);
      grad.addColorStop(1, "rgba(124,160,255,0)");
      g.fillStyle = grad;
      g.fillRect(0, 0, 256, 256);
      return new THREE.CanvasTexture(c);
    };
    const atmoOuter = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(70, 0.2), transparent: true, depthWrite: false }));
    atmoOuter.scale.set(3.15, 3.15, 1);
    const atmoInner = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(96, 0.26), transparent: true, depthWrite: false }));
    atmoInner.scale.set(2.44, 2.44, 1);
    scene.add(atmoOuter, atmoInner);

    const starCloud = (n: number, size: number, opacity: number) => {
      const arr = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        const v = new THREE.Vector3().randomDirection().multiplyScalar(6 + Math.random() * 5);
        arr[i * 3] = v.x; arr[i * 3 + 1] = v.y; arr[i * 3 + 2] = v.z;
      }
      return pointCloud(arr, 0xc7cede, size, opacity);
    };
    scene.add(starCloud(320, 0.02, 0.45), starCloud(80, 0.038, 0.7));

    /* ---------- Terra di design: night lights NASA (pubblico dominio) ---------- */
    // Look OLED-dark coerente col brand: oceani neri, citta' che brillano.
    let texOn = false;
    let texRamp = 0; // dissolve i punti quando la texture e' pronta
    {
      const loader = new THREE.TextureLoader();
      loader.load(
        mobile ? "/earth-night-4k.jpg" : "/earth-night-8k.jpg",
        (tex) => {
          if (dead) return;
          tex.colorSpace = THREE.SRGBColorSpace;
          try { tex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy()); } catch { /* opzionale */ }
          oceanMat.map = tex;
          oceanMat.color.set(0xeef2fc); // grading freddo e luminoso: le luci brillano
          oceanMat.needsUpdate = true;
          texOn = true;
        },
        undefined,
        () => { /* niente texture: resta il globo a puntini */ },
      );
    }

    /* ---------- FINALE REALE: Google Photorealistic 3D Tiles ---------- */
    // Vera geometria 3D fotorealistica di Milano e del Duomo (come Google Earth),
    // resa in un secondo canvas/renderer perche' vive in coordinate ECEF (metri).
    // Nessuna chiave / errore rete -> il canvas resta trasparente e sotto suona
    // il diorama stilizzato come fallback.
    /* eslint-disable @typescript-eslint/no-explicit-any */
    let tiles: any = null;
    let tilesRenderer: THREE.WebGLRenderer | null = null;
    let tilesScene: THREE.Scene | null = null;
    let tilesCam: THREE.PerspectiveCamera | null = null;
    let ELL: any = null;
    let tilesReady = false;
    let tilesShown = false;   // abbastanza tile caricati per mostrare la scena
    let loadedModels = 0;
    let tileErr = "";         // diagnostica visibile: perche' il 3D reale non c'e'
    let tilePhaseSince = 0;   // quando si e' entrati nella fase tiles (per timeout)
    const enuMat = new THREE.Matrix4();
    if (GMAPS_KEY && tilesCanvasRef.current) {
      (async () => {
        try {
          const core: any = await import("3d-tiles-renderer");
          const plugins: any = await import("3d-tiles-renderer/plugins");
          const { DRACOLoader } = await import("three/examples/jsm/loaders/DRACOLoader.js");
          if (dead || !tilesCanvasRef.current) return;
          const tr = new THREE.WebGLRenderer({ canvas: tilesCanvasRef.current, antialias: true, alpha: true });
          tr.setPixelRatio(Math.min(window.devicePixelRatio || 1, mobile ? 1.4 : 1.75));
          tr.setSize(wrap.clientWidth || window.innerWidth, window.innerHeight, false);
          const cam = new THREE.PerspectiveCamera(52, camera.aspect, 1, 4e7);
          const sc = new THREE.Scene();
          const t = new core.TilesRenderer();
          t.registerPlugin(new plugins.GoogleCloudAuthPlugin({ apiToken: GMAPS_KEY, autoRefreshToken: true }));
          const draco = new DRACOLoader();
          draco.setDecoderPath("https://www.gstatic.com/draco/gltf/");
          t.registerPlugin(new plugins.GLTFExtensionsPlugin({ dracoLoader: draco }));
          try { if (plugins.TilesFadePlugin) t.registerPlugin(new plugins.TilesFadePlugin()); } catch { /* opzionale */ }
          t.setCamera(cam);
          t.setResolutionFromRenderer(cam, tr);
          t.errorTarget = mobile ? 18 : 10;
          t.addEventListener("load-model", () => { loadedModels++; });
          t.addEventListener("load-error", (e: any) => {
            const msg = String(e?.error?.message || e?.message || e || "");
            console.warn("[intro] Google 3D Tiles load-error:", msg || e);
            // messaggio azionabile per l'utente sul badge in basso a sinistra
            if (/40[13]|denied|referer|referrer|forbidden|key/i.test(msg))
              tileErr = "3D Google negato — abilita 'Map Tiles API' + billing e consenti il referrer *.vercel.app nella chiave";
            else if (!tileErr) tileErr = "3D Google non caricato — controlla la chiave / rete";
          });
          sc.add(t.group);
          ELL = core.WGS84_ELLIPSOID;
          tiles = t; tilesRenderer = tr; tilesScene = sc; tilesCam = cam; tilesReady = true;
        } catch (e) {
          console.warn("[intro] 3D Tiles non disponibili, resto sul diorama:", e);
        }
      })();
    }

    /* ---------- overlay ---------- */
    const captions: Array<[number, string]> = [
      [0, "Low earth orbit — il mondo visto dall’alto"],
      [0.28, "Europa — Italia nel mirino"],
      [0.5, "Nord Italia — Lombardia"],
      [0.66, "Milano — acquisizione citta'"],
      [0.88, "Piazza del Duomo"],
    ];
    let capIdx = -1;
    const setCaption = (p: number) => {
      let idx = 0;
      for (let i = 0; i < captions.length; i++) if (p >= captions[i][0]) idx = i;
      if (idx !== capIdx && captionRef.current) {
        capIdx = idx;
        captionRef.current.textContent = captions[idx][1];
      }
    };
    const onSkip = () => window.scrollTo({ top: wrap.offsetHeight - window.innerHeight + 2, behavior: "smooth" });
    skipRef.current?.addEventListener("click", onSkip);

    /* ---------- render loop ---------- */
    const easeIO = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
    const clamp01 = (n: number) => Math.max(0, Math.min(1, n));
    const smooth = (t: number) => { const c = clamp01(t); return c * c * (3 - 2 * c); };

    let dStart = 3.2, narrow = false;
    const D2R = Math.PI / 180;
    const camWorld = new THREE.Vector3(), tgtWorld = new THREE.Vector3(), upWorld = new THREE.Vector3();
    const enuPos = (east: number, north: number, up: number, out: THREE.Vector3) =>
      out.set(east, north, up).applyMatrix4(enuMat); // ENU locale -> ECEF mondo

    const resize = () => {
      const w = wrap.clientWidth || window.innerWidth, h = window.innerHeight;
      renderer.setSize(w, h, false);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      camera.aspect = w / h;
      narrow = camera.aspect < 0.8;
      dStart = narrow ? 4.4 : 3.2;
      camera.updateProjectionMatrix();
      if (tilesRenderer && tilesCam) {
        tilesRenderer.setSize(w, h, false);
        tilesCam.aspect = w / h;
        tilesCam.updateProjectionMatrix();
      }
    };
    resize();
    window.addEventListener("resize", resize, { passive: true });

    // coreografia camera: discesa verticale -> arco in inquadratura obliqua
    const posStraight = new THREE.Vector3();
    const posFinal = new THREE.Vector3();
    const camPos = new THREE.Vector3();
    const target = new THREE.Vector3();
    const targetFinal = new THREE.Vector3(0, 0, 1.018);
    const upStart = new THREE.Vector3(0, 1, 0);
    const upEnd = new THREE.Vector3(0, 0, 1);
    const up = new THREE.Vector3();

    let visible = true, rafId = 0, last = 0;
    const frame = (now: number) => {
      if (dead || !visible) return;
      const dt = Math.min(0.05, (now - last) * 0.001 || 0.016);
      last = now;
      const denom = Math.max(1, wrap.offsetHeight - window.innerHeight);
      const p = clamp01(window.scrollY / denom);

      // rotazione del globo: lock completo su Milano entro p=0.8
      const eRot = easeIO(clamp01(p / 0.7));
      spin += dt * 0.05 * (1 - eRot);
      qSpin.setFromAxisAngle(Z, spin);
      qA.copy(qSpin).multiply(qPole);
      qOut.copy(qA).slerp(qMilan, eRot);
      globe.quaternion.copy(qOut);

      // discesa verticale fino a quota citta'
      const eDolly = easeIO(clamp01(p / 0.72));
      posStraight.set(0, 0, dStart + (1.52 - dStart) * eDolly);

      // arco finale: la camera scende a sud del Duomo, orizzonte in alto
      const tCam = smooth((p - 0.78) / 0.22);
      const drift = Math.sin(now * 0.00025) * 0.012 * tCam;
      // tre quarti da sud-ovest, quota drone: facciata + fianco in vista
      if (narrow) posFinal.set(drift - 0.07, -0.27, 1.105);
      else posFinal.set(drift - 0.09, -0.21, 1.083);
      camPos.copy(posStraight).lerp(posFinal, tCam);
      camera.position.copy(camPos);
      target.set(0, 0, 0).lerp(targetFinal, tCam);
      up.copy(upStart).lerp(upEnd, tCam).normalize();
      camera.up.copy(up);
      camera.lookAt(target);

      // ---- beat narrativi sequenziali: Italia -> Lombardia -> Milano ----
      const italyO = smooth((p - 0.28) / 0.12) * (1 - smooth((p - 0.55) / 0.1));
      if (italyOutline) (italyOutline.material as THREE.LineBasicMaterial).opacity =
        italyO * (0.75 + Math.sin(now * 0.003) * 0.15);
      if (italyFill) (italyFill.material as THREE.PointsMaterial).opacity = italyO * 0.85;
      const lombO = smooth((p - 0.46) / 0.1) * (1 - smooth((p - 0.62) / 0.08));
      lombMat.opacity = lombO * (0.8 + Math.sin(now * 0.0035) * 0.2);
      lombGroup.scale.setScalar(1.7 - 0.7 * smooth((p - 0.48) / 0.1)); // lock-on
      lombGroup.rotation.z = now * 0.0003;

      // crossfade mappa di punti -> citta' 3D (solo fallback senza tiles)
      const cityO = clamp01((p - 0.62) / 0.14);
      (coarse.material as THREE.PointsMaterial).opacity = 0.85 * (1 - clamp01((p - 0.45) / 0.25)) * (1 - texRamp);
      (graticule.material as THREE.LineBasicMaterial).opacity = 0.08 * (1 - eRot);
      (atmoInner.material as THREE.SpriteMaterial).opacity = 1 - eRot * 0.9;
      for (const { m, k } of fadeMats) (m as THREE.Material & { opacity: number }).opacity = cityO * k;

      const mk = clamp01((p - 0.5) / 0.1) * (1 - clamp01((p - 0.6) / 0.06));
      (marker.material as THREE.MeshBasicMaterial).opacity = mk;
      const pulse = 1 + Math.sin(now * 0.004) * 0.4;
      ring.scale.setScalar((1 + (1 - clamp01((p - 0.62) / 0.12)) * 3) * pulse);
      (ring.material as THREE.MeshBasicMaterial).opacity = mk * (0.5 + Math.sin(now * 0.004) * 0.25);

      if (labelRef.current) labelRef.current.classList.toggle("on", p > 0.9);
      if (hintRef.current) hintRef.current.style.opacity = p > 0.06 ? "0" : "1";
      if (skipRef.current) skipRef.current.style.opacity = p > 0.6 ? "0" : "1";
      if (captionRef.current) captionRef.current.style.opacity = p > 0.985 ? "0" : ".9";
      setCaption(p);

      // ---- dissolvenza punti -> Terra notturna; credit NASA ----
      if (texOn && texRamp < 1) texRamp = Math.min(1, texRamp + dt * 1.2);

      // ---- FINALE: volo in Google 3D Tiles fino alla facciata del Duomo ----
      let tilesO = 0;
      if (tilesReady && tiles && tilesCam && tilesRenderer && tilesScene && ELL) {
        tiles.group.updateMatrixWorld();
        const TUNE: any = (window as any).__TUNE__ || {};
        ELL.getEastNorthUpFrame((TUNE.lat ?? DUOMO.lat) * D2R, (TUNE.lon ?? DUOMO.lon) * D2R, 0, enuMat);
        enuMat.premultiply(tiles.group.matrixWorld);

        // camera in coordinate sferiche ATTORNO al Duomo: resta sempre centrato.
        // g: discesa complessiva (quota+raggio 9km -> hero shot); pitch: da quasi
        // zenitale a quasi frontale sulla facciata (bearing = lato piazza).
        const g0 = smooth(clamp01((p - 0.42) / 0.56));
        const pEnd = TUNE.pitchEnd ?? 52, rEnd = TUNE.radEnd ?? (narrow ? 300 : 212);
        const bEnd = TUNE.brgEnd ?? DUOMO.facadeBearing, thEnd = TUNE.thEnd ?? 76;
        // PRELOAD: durante tutta la prima parte (p<0.55) la camera tiles e' gia'
        // puntata sul Duomo finale (g=1) e update() scarica i tile profondi
        // mentre l'utente guarda globo/Italia/Lombardia. Dalla discesa in poi
        // segue l'animazione. Il "salto" avviene mentre e' invisibile (opacity 0).
        const g = p < 0.55 ? 1 : g0;
        const pitch = (6 + (pEnd - 6) * g) * D2R;             // zenitale -> obliqua aerea (no radente)
        const radius = Math.exp(Math.log(9000) + (Math.log(rEnd) - Math.log(9000)) * g);
        const brg = (bEnd + Math.sin(now * 0.00018) * 4 * g) * D2R;
        const tgtH = 6 + thEnd * g;                           // mira: suolo -> meta' facciata
        const horiz = radius * Math.sin(pitch);
        const vert = radius * Math.cos(pitch);
        enuPos(0, 0, tgtH, tgtWorld);
        enuPos(Math.sin(brg) * horiz, Math.cos(brg) * horiz, tgtH + vert, camWorld);
        upWorld.set(enuMat.elements[8], enuMat.elements[9], enuMat.elements[10]).normalize();
        tilesCam.position.copy(camWorld);
        tilesCam.up.copy(upWorld);
        tilesCam.lookAt(tgtWorld);
        tilesCam.aspect = camera.aspect;
        tilesCam.updateProjectionMatrix();
        tiles.setResolutionFromRenderer(tilesCam, tilesRenderer);
        tiles.update();
        if (!tilesShown && loadedModels >= (mobile ? 6 : 12)) tilesShown = true;
        tilesO = tilesShown ? smooth(clamp01((p - 0.6) / 0.06)) : 0;
        if (tilesCanvasRef.current) tilesCanvasRef.current.style.opacity = String(tilesO);
        if (gradeRef.current) gradeRef.current.style.opacity = String(tilesO); // grading dark-blue
        if (canvas) canvas.style.opacity = String(1 - tilesO); // spegne il globo dietro
        if (tilesO > 0) tilesRenderer.render(tilesScene, tilesCam);
        // timeout: in fase Duomo da >7s senza nemmeno un tile => problema chiave/API
        if (p > 0.6) {
          if (!tilePhaseSince) tilePhaseSince = now;
          if (!tileErr && loadedModels === 0 && now - tilePhaseSince > 7000)
            tileErr = "3D Google non caricato — verifica 'Map Tiles API', billing e referrer della chiave";
        }
      }

      if (attribRef.current) {
        const a = attribRef.current;
        if (tilesO > 0.3) {
          let cred = "Google";
          try {
            const at = (tiles.getAttributions?.() || []) as Array<{ value?: string }>;
            const parts = at.map((x) => x.value).filter(Boolean);
            if (parts.length) cred = parts.join(" · ");
          } catch { /* credit di default */ }
          a.textContent = "© " + cred; a.style.opacity = ".8"; a.classList.remove("warn");
        } else if (GMAPS_KEY && p > 0.62 && tileErr) {
          a.textContent = tileErr; a.style.opacity = ".95"; a.classList.add("warn");
        } else if (!GMAPS_KEY && p > 0.62) {
          a.textContent = "3D reale off — NEXT_PUBLIC_GOOGLE_MAPS_API_KEY assente nel build";
          a.style.opacity = ".95"; a.classList.add("warn");
        } else if (GMAPS_KEY && p > 0.62 && !tilesShown) {
          a.textContent = "caricamento 3D Google…"; a.style.opacity = ".7"; a.classList.remove("warn");
        } else if (texOn && p < 0.7) {
          a.textContent = "Earth at night — NASA Black Marble"; a.style.opacity = ".6"; a.classList.remove("warn");
        } else { a.style.opacity = "0"; a.classList.remove("warn"); }
      }

      if (tilesO < 1) renderer.render(scene, camera); // globo/diorama sotto (fallback)
      rafId = requestAnimationFrame(frame);
    };
    let io: IntersectionObserver | null = null;
    if ("IntersectionObserver" in window) {
      io = new IntersectionObserver((es) => {
        es.forEach((en) => {
          if (en.isIntersecting && !visible) { visible = true; last = 0; rafId = requestAnimationFrame(frame); }
          else if (!en.isIntersecting && visible) { visible = false; cancelAnimationFrame(rafId); }
        });
      }, { threshold: 0 });
      io.observe(wrap);
    }
    rafId = requestAnimationFrame(frame);

    return () => {
      dead = true;
      cancelAnimationFrame(rafId);
      io?.disconnect();
      window.removeEventListener("resize", resize);
      skipRef.current?.removeEventListener("click", onSkip);
      try { tiles?.dispose?.(); } catch { /* già smontato */ }
      try { tilesRenderer?.dispose?.(); } catch { /* già smontato */ }
      renderer.dispose();
    };
    } catch (err) {
      // safety net: scena rotta -> si collassa l'intro, il sito parte dall'hero
      wrap.dataset.err = String((err as Error)?.stack || err);
      setOff(true);
      return;
    }
  }, []);

  return (
    <section ref={wrapRef} className={`intro${off ? " off" : ""}`} id="intro" aria-label="Introduzione: dal mondo al Duomo di Milano">
      <div className="intro-sticky">
        <canvas ref={canvasRef} id="globe-canvas" aria-hidden="true" />
        {/* Il Duomo vero in 3D: Google Photorealistic 3D Tiles */}
        <canvas ref={tilesCanvasRef} className="intro-tiles" aria-hidden="true" />
        {/* grading dark-blue: fonde la vista reale nell'estetica elite del sito */}
        <div ref={gradeRef} className="intro-grade" aria-hidden="true" />
        <div className="intro-ui">
          <div ref={captionRef} className="intro-caption mono" id="intro-caption">Low earth orbit</div>
          <div className="intro-coords mono" id="intro-coords">45.4642&deg; N &mdash; 9.1900&deg; E</div>
          <div ref={labelRef} className="intro-label" id="intro-label">
            <b>DUOMO DI MILANO</b>
            <span>45.4642&deg; N / 9.1900&deg; E</span>
          </div>
          <div ref={hintRef} className="intro-hint mono" id="intro-hint">Scroll</div>
          <button ref={skipRef} className="intro-skip mono" id="intro-skip" type="button">Salta l&apos;intro &darr;</button>
          <div ref={attribRef} className="intro-attrib" id="intro-attrib" aria-hidden="true" />
        </div>
        <div className="intro-fade" />
      </div>
    </section>
  );
}
