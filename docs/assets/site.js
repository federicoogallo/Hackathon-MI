/* Hackathon Milano — interactions (no framework, transform/opacity only) */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var doc = document;
  doc.body.classList.add('js');
  if ('scrollRestoration' in history) { history.scrollRestoration = 'manual'; }
  if (!location.hash) { window.scrollTo(0, 0); }
  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function ease(t) { return 1 - Math.pow(1 - t, 3); }

  /* ---- fixed nav state ---- */
  var nav = doc.getElementById('nav');
  function updNav() { if (nav) nav.classList.toggle('is-scrolled', window.scrollY > 24); }

  /* ---- hero entrance: animations start only when the hero is on screen
     (the orbital intro sits above it, so load-time playback would be missed) ---- */
  var hero = doc.querySelector('.hero');
  (function () {
    if (!hero) return;
    if (reduce || !('IntersectionObserver' in window)) { hero.classList.add('seen'); return; }
    var ioh = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) { hero.classList.add('seen'); ioh.disconnect(); }
      });
    }, { threshold: .18 });
    ioh.observe(hero);
  })();

  /* ---- scroll progress ---- */
  var prog = doc.getElementById('scroll-progress');
  function updProg() {
    if (!prog) return;
    var h = doc.documentElement.scrollHeight - window.innerHeight;
    prog.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + '%';
  }

  /* ---- reveal on scroll (elements already in viewport show immediately) ---- */
  var reveals = [].slice.call(doc.querySelectorAll('[data-reveal]'));
  if (reveals.length) {
    if (reduce || !('IntersectionObserver' in window)) {
      reveals.forEach(function (el) { el.classList.add('in'); });
    } else {
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (e.isIntersecting) {
            var el = e.target, d = parseFloat(el.getAttribute('data-delay') || '0');
            el.style.transitionDelay = d + 'ms';
            el.classList.add('in');
            io.unobserve(el);
          }
        });
      }, { threshold: .12, rootMargin: '0px 0px -6% 0px' });
      var vh0 = window.innerHeight || 0;
      reveals.forEach(function (el) {
        if (el.getBoundingClientRect().top < vh0) { el.classList.add('in'); }
        else { io.observe(el); }
      });
    }
  }

  /* ---- count up ---- */
  function countUp(el) {
    var target = parseFloat(el.getAttribute('data-count'));
    if (isNaN(target)) return;
    var suffix = el.getAttribute('data-suffix') || '', dur = 1100, t0 = null;
    function step(ts) {
      if (!t0) t0 = ts;
      var p = clamp((ts - t0) / dur, 0, 1);
      el.textContent = Math.round(target * ease(p)) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var counters = [].slice.call(doc.querySelectorAll('[data-count]'));
  if (counters.length) {
    if (reduce || !('IntersectionObserver' in window)) { counters.forEach(countUp); }
    else {
      var io2 = new IntersectionObserver(function (es) {
        es.forEach(function (e) { if (e.isIntersecting) { countUp(e.target); io2.unobserve(e.target); } });
      }, { threshold: .6 });
      counters.forEach(function (el) { io2.observe(el); });
    }
  }

  /* ---- canvas fit helper ---- */
  function fit(cv) {
    var r = cv.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.max(1, Math.floor(r.width * d));
    cv.height = Math.max(1, Math.floor(r.height * d));
    var ctx = cv.getContext('2d');
    ctx.setTransform(d, 0, 0, d, 0, 0);
    return { ctx: ctx, w: r.width, h: r.height };
  }

  /* ---- hero ambient particle field (paused offscreen) ---- */
  var heroCv = doc.getElementById('hero-canvas');
  var mouse = { x: .72, y: .4 };
  if (heroCv && heroCv.getContext && !reduce) {
    var pts = [], running = false, rafId = 0;
    (function seed() {
      var n = (window.innerWidth || 1000) < 720 ? 42 : 78;
      for (var i = 0; i < n; i++) {
        pts.push({ x: Math.random(), y: Math.random(), vx: (Math.random() - .5) * .00028, vy: (Math.random() - .5) * .00028, r: Math.random() * 1.6 + .5 });
      }
    })();
    function drawHero() {
      if (!running) return;
      var f = fit(heroCv), ctx = f.ctx, w = f.w, h = f.h;
      ctx.clearRect(0, 0, w, h);
      var px = (mouse.x - .5) * 26, py = (mouse.y - .5) * 20;
      for (var i = 0; i < pts.length; i++) {
        var p = pts[i];
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > 1) p.vx *= -1;
        if (p.y < 0 || p.y > 1) p.vy *= -1;
        var x = p.x * w + px, y = p.y * h + py;
        for (var j = i + 1; j < pts.length; j++) {
          var q = pts[j], dx = (p.x - q.x) * w, dy = (p.y - q.y) * h, d = Math.hypot(dx, dy);
          if (d < 118) {
            ctx.strokeStyle = 'rgba(61,107,255,' + (0.14 * (1 - d / 118)) + ')';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(q.x * w + px, q.y * h + py); ctx.stroke();
          }
        }
        ctx.fillStyle = i % 7 === 0 ? 'rgba(124,160,255,.85)' : 'rgba(190,205,245,.45)';
        ctx.beginPath(); ctx.arc(x, y, p.r, 0, 6.2832); ctx.fill();
      }
      rafId = requestAnimationFrame(drawHero);
    }
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (e.isIntersecting && !running) { running = true; rafId = requestAnimationFrame(drawHero); }
          else if (!e.isIntersecting && running) { running = false; cancelAnimationFrame(rafId); }
        });
      }, { threshold: 0 }).observe(heroCv);
    } else { running = true; requestAnimationFrame(drawHero); }
    window.addEventListener('pointermove', function (e) {
      mouse.x = e.clientX / (window.innerWidth || 1);
      mouse.y = e.clientY / (window.innerHeight || 1);
    }, { passive: true });
  }

  /* ---- TITLE: materialize from particles.
     Glyph-accurate: draws char-by-char with the element's computed
     letter-spacing so particles land exactly on the real glyphs
     (fixes the "hackathoR" artifact), on an oversized canvas to
     avoid edge clipping. ---- */
  [].slice.call(doc.querySelectorAll('[data-materialize]')).forEach(function (span) {
    if (reduce) return;
    var cv = doc.createElement('canvas');
    if (!cv.getContext) return;
    cv.className = 'materialize-canvas';
    cv.setAttribute('aria-hidden', 'true');
    span.appendChild(cv);
    var ctx = cv.getContext('2d');
    if (!ctx) return;
    var text = span.getAttribute('data-materialize') || '';
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var parts = [], started = 0, done = false, maxEnd = 0, ready = false;
    var padX = 0, padY = 0; // canvas overdraw margins (canvas is inset -12%/-18% in CSS)

    function col(c, a) {
      if (c === 1) return 'rgba(124,160,255,' + a + ')';
      if (c === 2) return 'rgba(38,214,150,' + a + ')';
      return 'rgba(245,247,252,' + a + ')';
    }

    function build() {
      var sw = span.clientWidth, sh = span.clientHeight;
      if (sw < 12 || sh < 12) return false;
      padX = sw * .12; padY = sh * .18;
      var w = sw + padX * 2, h = sh + padY * 2;
      cv.width = Math.floor(w * dpr); cv.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      var off = doc.createElement('canvas');
      off.width = Math.max(1, Math.round(w)); off.height = Math.max(1, Math.round(h));
      var o = off.getContext('2d');
      if (!o) return false;
      var cs = getComputedStyle(span);
      var fs = parseFloat(cs.fontSize) || 80;
      var ls = parseFloat(cs.letterSpacing); if (isNaN(ls)) ls = 0;
      o.fillStyle = '#fff';
      o.textBaseline = 'alphabetic';
      o.font = (cs.fontStyle || 'normal') + ' ' + (cs.fontWeight || '700') + ' ' + fs + 'px ' + cs.fontFamily;

      // per-char advance (canvas has no letter-spacing everywhere; do it by hand)
      var widths = [], total = 0, i;
      for (i = 0; i < text.length; i++) {
        widths.push(o.measureText(text[i]).width);
        total += widths[i] + (i < text.length - 1 ? ls : 0);
      }
      var m = o.measureText(text);
      var asc = m.actualBoundingBoxAscent || fs * .72;
      var desc = m.actualBoundingBoxDescent || fs * .2;
      var gx = padX + Math.max(0, (sw - total) / 2);
      var gy = padY + (sh - (asc + desc)) / 2 + asc;
      var x = gx;
      for (i = 0; i < text.length; i++) { o.fillText(text[i], x, gy); x += widths[i] + ls; }

      var data;
      try { data = o.getImageData(0, 0, off.width, off.height).data; } catch (e) { return false; }
      var step = clamp(Math.round(fs / 17), 3, 8), tg = [];
      for (var y = 0; y < off.height; y += step) {
        for (var xx = 0; xx < off.width; xx += step) {
          if (data[(y * off.width + xx) * 4 + 3] > 135) tg.push([xx, y]);
        }
      }
      while (tg.length > 1900) { var t2 = []; for (var k = 0; k < tg.length; k += 2) t2.push(tg[k]); tg = t2; }
      if (!tg.length) return false;

      parts = tg.map(function (t, idx) {
        var ang = Math.random() * 6.2832, rad = 44 + Math.random() * Math.max(w, h) * .72;
        return {
          tx: t[0], ty: t[1],
          sx: t[0] + Math.cos(ang) * rad,
          sy: t[1] + Math.sin(ang) * rad * .62 + Math.random() * 40,
          delay: ((t[0] - padX) / sw) * 300 + Math.random() * 160,
          dur: 640 + Math.random() * 380,
          c: (idx % 14 === 0 ? 1 : (idx % 26 === 0 ? 2 : 0))
        };
      });
      maxEnd = 0;
      parts.forEach(function (p) { if (p.delay + p.dur > maxEnd) maxEnd = p.delay + p.dur; });
      started = performance.now(); done = false; ready = true;
      span.classList.add('is-animating');
      return true;
    }

    function frame(now) {
      if (!ready) { requestAnimationFrame(frame); return; }
      var w = cv.width / dpr, h = cv.height / dpr;
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = 'lighter';
      var t = now - started;
      if (!done) {
        for (var i = 0; i < parts.length; i++) {
          var p = parts[i], lt = clamp((t - p.delay) / p.dur, 0, 1), e = ease(lt);
          var cx = p.sx + (p.tx - p.sx) * e, cy = p.sy + (p.ty - p.sy) * e;
          ctx.fillStyle = col(p.c, clamp(lt * 1.25, 0, 1) * .92);
          ctx.fillRect(cx, cy, 1.5, 1.5);
        }
        if (t > maxEnd + 90) { done = true; span.classList.remove('is-animating'); }
      } else {
        var s = now * .001;
        for (var j = 0; j < parts.length; j++) {
          var q = parts[j];
          var jx = Math.sin(s * 1.2 + j * .5) * .5, jy = Math.cos(s * 1.05 + j * .7) * .5;
          var aa = .05 + (q.c ? .06 : 0) + Math.sin(s * 1.8 + j) * .02;
          if (aa < 0) aa = 0;
          ctx.fillStyle = col(q.c, aa);
          ctx.fillRect(q.tx + jx, q.ty + jy, 1.1, 1.1);
        }
      }
      ctx.globalCompositeOperation = 'source-over';
      requestAnimationFrame(frame);
    }

    var tries = 0;
    function attempt() {
      if (build()) { requestAnimationFrame(frame); }
      else if (tries++ < 32) { setTimeout(attempt, 110); }
    }
    function start() {
      if (doc.fonts && doc.fonts.ready) { doc.fonts.ready.then(attempt); } else { attempt(); }
    }
    // wait until the title is actually visible before materializing
    if (!('IntersectionObserver' in window)) { start(); }
    else {
      var iom = new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (e.isIntersecting) { iom.disconnect(); start(); }
        });
      }, { threshold: .3 });
      iom.observe(span);
    }
    var rz;
    window.addEventListener('resize', function () {
      clearTimeout(rz);
      rz = setTimeout(function () {
        var was = done;
        if (build() && was) { done = true; span.classList.remove('is-animating'); }
      }, 220);
    }, { passive: true });
  });

  /* ---- SYSTEM (01): rail progress ---- */
  var system = doc.getElementById('system');
  var railFill = doc.getElementById('rail-fill');
  var railSteps = [].slice.call(doc.querySelectorAll('[data-step]'));
  function updRail() {
    if (!system) return;
    var r = system.getBoundingClientRect(), vh = window.innerHeight || 1;
    var p = clamp((vh * .78 - r.top) / Math.max(1, r.height * .9), 0, 1);
    if (railFill) {
      var vertical = (window.innerWidth || 1000) <= 1000;
      railFill.style.transform = vertical ? 'scaleY(' + p + ')' : 'scaleX(' + p + ')';
    }
    railSteps.forEach(function (el, i) { el.classList.toggle('on', p > (i + .35) / railSteps.length); });
  }

  /* ---- scroll dispatcher ---- */
  var ticking = false;
  function onScroll() {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(function () { ticking = false; updNav(); updProg(); updRail(); });
    }
  }
  updNav(); updProg(); updRail();
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });

  /* ---- search + filter ---- */
  var search = doc.getElementById('search'),
      countLabel = doc.getElementById('count-label'),
      noRes = doc.getElementById('no-results');
  var cards = [].slice.call(doc.querySelectorAll('.card')),
      filters = [].slice.call(doc.querySelectorAll('[data-filter]')),
      active = 'all';
  function inFilter(card) {
    var iso = card.getAttribute('data-date');
    if (active === 'all') return true;
    if (!iso) return active === 'later';
    var d = new Date(iso + 'T12:00:00'), now = new Date(), diff = (d - now) / 86400000;
    if (active === 'week') return diff >= 0 && diff <= 7;
    if (active === 'month') return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
    return diff > 31;
  }
  function apply() {
    var q = (search && search.value || '').trim().toLowerCase(), shown = 0;
    cards.forEach(function (c) {
      var ok = (c.getAttribute('data-search') || '').indexOf(q) > -1 && inFilter(c);
      c.hidden = !ok;
      if (ok) shown++;
    });
    if (countLabel) countLabel.textContent = shown + ' ' + (shown === 1 ? 'evento' : 'eventi');
    if (noRes) noRes.style.display = shown ? 'none' : 'block';
  }
  if (search) search.addEventListener('input', apply);
  filters.forEach(function (b) {
    b.addEventListener('click', function () {
      filters.forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      active = b.getAttribute('data-filter') || 'all';
      apply();
    });
  });
  apply();

  /* ---- card spotlight ---- */
  cards.forEach(function (c) {
    c.addEventListener('pointermove', function (e) {
      var r = c.getBoundingClientRect();
      c.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100) + '%');
      c.style.setProperty('--my', ((e.clientY - r.top) / r.height * 100) + '%');
    }, { passive: true });
  });
})();
