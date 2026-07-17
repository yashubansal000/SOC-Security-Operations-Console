// Anime.js wrappers — subtle, professional motion only. anime is global (vendored).
const A = () => window.anime;

export function countUp(el, to, dur = 900) {
  if (!A() || to == null || isNaN(+to)) { el.textContent = to; return; }
  const obj = { v: 0 };
  A()({ targets: obj, v: +to, round: 1, duration: dur, easing: "easeOutCubic",
    update: () => { el.textContent = Number(obj.v).toLocaleString(); } });
}

export function enter(selector, { delay = 60, y = 14 } = {}) {
  if (!A()) return;
  A()({ targets: selector, translateY: [y, 0], opacity: [0, 1],
    delay: A().stagger(delay), duration: 520, easing: "easeOutQuad" });
}

export function fadeIn(el, dur = 300) {
  if (!A()) { el.style.opacity = 1; return; }
  A()({ targets: el, opacity: [0, 1], duration: dur, easing: "easeOutQuad" });
}

export function pulse(el) {
  if (!A()) return;
  A()({ targets: el, scale: [1, 1.04, 1], duration: 400, easing: "easeOutQuad" });
}
