/* Hackathon Milano — orbital intro.
   Dotted WebGL Earth (three.js + world-atlas land polygons), scroll-scrubbed:
   pole view ("il mondo visto dall'alto") -> gradual zoom onto Milan -> hero.
   Fully reversible on scroll-up. Graceful fallback: on any failure the intro
   stays collapsed and the page starts at the hero exactly as before. */
(async function () {
  'use strict';
  var wrap = document.getElementById('intro');
  var canvas = document.getElementById('globe-canvas');
  if (!wrap || !canvas) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (location.hash) return; // deep link: don't force 320vh of intro

  var html = document.documentElement;
  function bail() {
    html.classList.remove('has-intro');
  }

  var THREE, topojson;
  try {
    THREE = await import('https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.module.js');
    topojson = await import('https://cdn.jsdelivr.net/npm/topojson-client@3/+esm');
  } catch (e) { bail(); return; }

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  } catch (e) { bail(); return; }

  html.classList.add('has-intro'); // idempotente: gia' attivata dal boot inline

  /* ---------- data: land polygons -> dot grid ---------- */
  var land;
  try {
    var ctrl = ('AbortController' in window) ? new AbortController() : null;
    if (ctrl) setTimeout(function () { ctrl.abort(); }, 9000);
    var res = await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/land-110m.json',
      ctrl ? { signal: ctrl.signal } : undefined);
    if (!res.ok) { bail(); return; }
    var topo = await res.json();
    land = topojson.feature(topo, topo.objects.land);
  } catch (e) { bail(); return; }

  // rings with bounding boxes for fast point-in-polygon
  var rings = [];
  land.features.forEach(function (f) {
    var polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    polys.forEach(function (poly) {
      poly.forEach(function (ring) {
        var minX = 999, minY = 999, maxX = -999, maxY = -999;
        for (var i = 0; i < ring.length; i++) {
          var p = ring[i];
          if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
          if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
        }
        rings.push({ pts: ring, minX: minX, minY: minY, maxX: maxX, maxY: maxY });
      });
    });
  });
  function inLand(lon, lat) {
    var inside = false;
    for (var r = 0; r < rings.length; r++) {
      var g = rings[r];
      if (lon < g.minX || lon > g.maxX || lat < g.minY || lat > g.maxY) continue;
      var pts = g.pts;
      for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        var xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
        if (((yi > lat) !== (yj > lat)) && (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside;
      }
    }
    return inside;
  }

  var R = 1;
  function v3(lat, lon, r) {
    var la = lat * Math.PI / 180, lo = lon * Math.PI / 180;
    return new THREE.Vector3(r * Math.cos(la) * Math.cos(lo), r * Math.sin(la), -r * Math.cos(la) * Math.sin(lo));
  }
  var MILAN = { lat: 45.4642, lon: 9.19 };
  var milanDir = v3(MILAN.lat, MILAN.lon, 1).normalize();

  var mobile = (window.innerWidth || 1000) < 640;
  function buildDots(latStep, latMin, latMax, lonMin, lonMax, radius) {
    var pos = [];
    for (var lat = latMin; lat <= latMax; lat += latStep) {
      var c = Math.max(.12, Math.cos(lat * Math.PI / 180));
      var lonStep = latStep / c;
      for (var lon = lonMin; lon <= lonMax; lon += lonStep) {
        if (inLand(lon, lat)) {
          var v = v3(lat, lon, radius);
          pos.push(v.x, v.y, v.z);
        }
      }
    }
    return new Float32Array(pos);
  }
  var globalDots = buildDots(mobile ? 1.5 : 1.1, -56, 84, -180, 180, R + .002);
  // fine detail around Milan, revealed while approaching
  var detailDots = buildDots(.2, 40, 48.5, 5, 14.5, R + .003);

  /* ---------- scene ---------- */
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(42, 1, .01, 30);
  camera.position.set(0, 0, 3.2);
  var globe = new THREE.Group();
  scene.add(globe);

  // base sphere occludes far-side dots
  globe.add(new THREE.Mesh(
    new THREE.SphereGeometry(R * .994, 48, 48),
    new THREE.MeshBasicMaterial({ color: 0x0a0f19 })
  ));

  // round sprite so points stay circular at close zoom
  var dotTex = (function () {
    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d');
    var grad = g.createRadialGradient(32, 32, 4, 32, 32, 30);
    grad.addColorStop(0, 'rgba(255,255,255,1)');
    grad.addColorStop(.65, 'rgba(255,255,255,.9)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grad; g.beginPath(); g.arc(32, 32, 30, 0, 6.2832); g.fill();
    return new THREE.CanvasTexture(c);
  })();
  function pointCloud(arr, color, size, opacity) {
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3));
    return new THREE.Points(g, new THREE.PointsMaterial({
      color: color, size: size, sizeAttenuation: true, transparent: true, opacity: opacity,
      depthWrite: false, map: dotTex, alphaTest: .04
    }));
  }
  var coarse = pointCloud(globalDots, 0x7ca0ff, .0105, .85);
  globe.add(coarse);
  var detail = pointCloud(detailDots, 0xb3c6ff, .004, 0);
  globe.add(detail);

  // Milan marker + pulse ring
  var marker = new THREE.Mesh(
    new THREE.SphereGeometry(.006, 12, 12),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 })
  );
  marker.position.copy(milanDir).multiplyScalar(R + .004);
  globe.add(marker);
  var ring = new THREE.Mesh(
    new THREE.RingGeometry(.014, .016, 40),
    new THREE.MeshBasicMaterial({ color: 0x3d6bff, transparent: true, opacity: 0, side: THREE.DoubleSide })
  );
  ring.position.copy(milanDir).multiplyScalar(R + .004);
  ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), milanDir);
  globe.add(ring);

  // atmosphere rim
  (function () {
    var c = document.createElement('canvas'); c.width = c.height = 256;
    var g = c.getContext('2d');
    var grad = g.createRadialGradient(128, 128, 70, 128, 128, 128);
    grad.addColorStop(0, 'rgba(61,107,255,0)');
    grad.addColorStop(.72, 'rgba(61,107,255,.16)');
    grad.addColorStop(.92, 'rgba(124,160,255,.34)');
    grad.addColorStop(1, 'rgba(124,160,255,0)');
    g.fillStyle = grad; g.fillRect(0, 0, 256, 256);
    var sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false
    }));
    sp.scale.set(3.1, 3.1, 1);
    scene.add(sp);
  })();

  // stars
  (function () {
    var n = 420, arr = new Float32Array(n * 3);
    for (var i = 0; i < n; i++) {
      var v = new THREE.Vector3().randomDirection().multiplyScalar(6 + Math.random() * 5);
      arr[i * 3] = v.x; arr[i * 3 + 1] = v.y; arr[i * 3 + 2] = v.z;
    }
    scene.add(pointCloud(arr, 0xc7cede, .022, .5));
  })();

  /* ---------- orientation: pole view -> Milan ---------- */
  var Z = new THREE.Vector3(0, 0, 1);
  var qPole = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), Z);
  var qMilan = new THREE.Quaternion().setFromUnitVectors(milanDir, Z);
  var qSpin = new THREE.Quaternion(), qA = new THREE.Quaternion(), qOut = new THREE.Quaternion();
  var spin = 0;

  /* ---------- UI overlay ---------- */
  var caption = document.getElementById('intro-caption');
  var label = document.getElementById('intro-label');
  var hint = document.getElementById('intro-hint');
  var skip = document.getElementById('intro-skip');
  var captions = [
    [0, 'Low earth orbit — il mondo visto dall’alto'],
    [.3, 'Europa — triangolazione dei segnali'],
    [.62, 'Italia — Lombardia'],
    [.86, 'Milano — acquisizione target']
  ];
  var capIdx = -1;
  function setCaption(p) {
    var idx = 0;
    for (var i = 0; i < captions.length; i++) { if (p >= captions[i][0]) idx = i; }
    if (idx !== capIdx && caption) { capIdx = idx; caption.textContent = captions[idx][1]; }
  }
  if (skip) {
    skip.addEventListener('click', function () {
      window.scrollTo({ top: wrap.offsetHeight - window.innerHeight + 2, behavior: 'smooth' });
    });
  }

  /* ---------- render loop (gated by visibility) ---------- */
  function easeIO(t) { return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function clamp01(n) { return Math.max(0, Math.min(1, n)); }

  var dStart = 3.2;
  function resize() {
    var w = wrap.clientWidth || window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    camera.aspect = w / h;
    dStart = camera.aspect < .8 ? 4.4 : 3.2; // narrow screens: full globe in frame
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener('resize', resize, { passive: true });

  var visible = true, rafId = 0, last = 0;
  function frame(now) {
    if (!visible) return;
    var dt = Math.min(.05, (now - last) * .001 || .016);
    last = now;
    var denom = Math.max(1, wrap.offsetHeight - window.innerHeight);
    var p = clamp01(window.scrollY / denom);
    var e = easeIO(p);

    spin += dt * .05 * (1 - e);
    qSpin.setFromAxisAngle(Z, spin);
    qA.copy(qSpin).multiply(qPole);
    qOut.copy(qA).slerp(qMilan, e);
    globe.quaternion.copy(qOut);

    camera.position.z = dStart + (1.34 - dStart) * e;

    detail.material.opacity = clamp01((p - .5) / .3) * .95;
    coarse.material.opacity = .85 * (1 - clamp01((p - .68) / .27) * .78);
    var mk = clamp01((p - .55) / .25);
    marker.material.opacity = mk;
    var pulse = 1 + Math.sin(now * .004) * .4;
    ring.scale.setScalar((1 + (1 - mk) * 3) * pulse);
    ring.material.opacity = mk * (0.5 + Math.sin(now * .004) * .25);

    if (label) label.classList.toggle('on', p > .82);
    if (hint) hint.style.opacity = p > .06 ? '0' : '1';
    if (skip) skip.style.opacity = p > .6 ? '0' : '1';
    if (caption) caption.style.opacity = p > .97 ? '0' : '.9';
    setCaption(p);

    renderer.render(scene, camera);
    rafId = requestAnimationFrame(frame);
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (es) {
      es.forEach(function (en) {
        if (en.isIntersecting && !visible) { visible = true; last = 0; rafId = requestAnimationFrame(frame); }
        else if (!en.isIntersecting && visible) { visible = false; cancelAnimationFrame(rafId); }
      });
    }, { threshold: 0 }).observe(wrap);
  }
  rafId = requestAnimationFrame(frame);
})();
