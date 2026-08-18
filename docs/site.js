
// The living substrate: the same generated tree, as a fixed background
// that ignites under the cursor and cools behind it. Dull by design; it
// never fights the foreground. Static single render under
// prefers-reduced-motion.
(function () {
  const T = window.__TREE;
  if (!T) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cv = document.createElement('canvas');
  cv.id = 'bgtree';
  cv.setAttribute('aria-hidden', 'true');
  document.body.prepend(cv);
  const ctx = cv.getContext('2d');

  const HOT = ['#5c130a','#8a1f0d','#b62c0f','#d84012','#ff571a',
               '#ff8a4d','#ffc38a','#fff3e0'];
  const n = T.cells.length / 3;
  const gx = new Float32Array(n), gy = new Float32Array(n);
  const heat = new Uint8Array(n), boost = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    gx[i] = T.cells[3*i]; gy[i] = T.cells[3*i+1]; heat[i] = T.cells[3*i+2];
  }

  let s = 1, ox = 0, oy = 0, cs = 8, dpr = 1;
  function layout() {
    if (!innerWidth || !innerHeight) {      // hidden/pre-paint viewport:
      setTimeout(layout, 250);              // retry until it exists
      return;
    }
    dpr = Math.min(devicePixelRatio || 1, 2);
    cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
    cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
    s = Math.max(innerWidth / T.w, innerHeight / T.h);
    cs = T.cell * s;
    ox = 0; oy = innerHeight - T.h * s;   // anchor the trunk to the floor
    draw(true);
  }

  let mx = -1e4, my = -1e4, active = 0;
  addEventListener('pointermove', (e) => {
    mx = e.clientX; my = e.clientY; active = 60;
    if (!raf) loop();
  }, { passive: true });

  const R = 120, R2 = R * R;
  function draw(staticOnly) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (let i = 0; i < n; i++) {
      const x = ox + gx[i] * cs, y = oy + gy[i] * cs;
      if (x < -cs || x > innerWidth || y < -cs || y > innerHeight) continue;
      let b = boost[i];
      if (!staticOnly && active > 0) {
        const dx = x - mx, dy = y - my, d2 = dx*dx + dy*dy;
        if (d2 < R2) {
          const f = 1 - Math.sqrt(d2) / R;
          if (f > b) { boost[i] = f; b = f; }
        }
      }
      const idx = Math.min(7, heat[i] + (b > 0.4 ? 2 : b > 0.15 ? 1 : 0));
      ctx.globalAlpha = 0.13 + 0.45 * b;
      ctx.fillStyle = HOT[idx];
      const sz = Math.max(2, cs - 3 * s);
      ctx.fillRect(x, y, sz, sz);
      boost[i] = b * 0.955;
    }
    ctx.globalAlpha = 1;
  }

  let raf = 0, last = 0;
  function loop(ts) {
    raf = requestAnimationFrame(loop);
    if (ts - last < 33) return;         // ~30 fps is plenty for embers
    last = ts;
    draw(false);
    active--;
    let hotLeft = false;
    for (let i = 0; i < n; i += 7) if (boost[i] > 0.02) { hotLeft = true; break; }
    if (active <= 0 && !hotLeft) { cancelAnimationFrame(raf); raf = 0; }
  }

  addEventListener('resize', layout, { passive: true });
  layout();
  if (reduced) return;                   // static, dim, persistent — no motion
  loop(0);
})();

// Animated counters. Nothing else moves besides the substrate.
(function () {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const els = document.querySelectorAll('[data-count]');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting || e.target.dataset.done) return;
      e.target.dataset.done = '1';
      const target = parseFloat(e.target.dataset.count);
      const dec = (e.target.dataset.count.split('.')[1] || '').length;
      const t0 = performance.now();
      const step = (t) => {
        const p = Math.min((t - t0) / 800, 1);
        const eased = 1 - Math.pow(1 - p, 3);
        e.target.textContent = (target * eased).toFixed(dec);
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }, { threshold: 0.4 });
  els.forEach((el) => io.observe(el));
})();
