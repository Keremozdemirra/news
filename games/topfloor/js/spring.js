// A damped spring on one number, stepped on animation frames. It can be given a new target in mid-flight and keeps
// its speed, so a second answer while the lift is still moving bends the ride instead of restarting it.
// stiffness 140, damping 19 (ratio 0.80): arrives in about 0.55 s and passes its target by about 1.5 per cent.
export function spring(x0, onStep, { k = 140, c = 19, rest = 0.05 } = {}) {
  let x = x0, v = 0, target = x0, raf = 0, last = 0, onRest = null;
  const frame = (now) => {
    // fixed 4 ms sub-steps: the same ride on a 60 and a 120 Hz screen, and no blow-up after a dropped frame
    let dt = Math.min(64, now - last); last = now;
    for (; dt > 0; dt -= 4) { const h = Math.min(4, dt) / 1000; v += (-k * (x - target) - c * v) * h; x += v * h; }
    if (Math.abs(x - target) < rest && Math.abs(v) < rest * 20) { x = target; v = 0; raf = 0; onStep(x); const f = onRest; onRest = null; f?.(); return; }
    onStep(x);
    raf = requestAnimationFrame(frame);
  };
  const wake = () => { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } };
  return {
    to(t, done) { target = t; onRest = done || null; wake(); },
    set(t) { cancelAnimationFrame(raf); raf = 0; x = target = t; v = 0; onRest = null; onStep(x); },
    kick(dv) { v += dv; wake(); },
    get value() { return x; },
  };
}
