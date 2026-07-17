// Data layer — real backend only. No fabrication anywhere.
export const BASE = (location.port === "8000" || location.protocol === "file:")
  ? "http://localhost:8000" : location.origin;

export async function api(path, opts) {
  const r = await fetch(BASE + path, opts);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

// Adapter: persisted hypotheses (GET /incidents/{id}) use the backend schema
// (summary / confidence_pct); the UI expects claim / confidence / grounded.
// Regenerate-endpoint hypotheses already carry the UI shape, so pass them through.
export function adaptHypothesis(h) {
  if (h == null || h.claim !== undefined) return h; // already UI-shaped
  return {
    ...h,                                            // preserve rank, root_cause_node, evidence_refs, next_steps…
    claim: h.summary,
    confidence: h.confidence_pct != null ? h.confidence_pct / 100 : null,
    grounded: true,                                  // persisted hypotheses are already grounded
  };
}

// Fetch incident detail and normalize its persisted hypotheses to the UI shape.
export async function getDetail(id) {
  const detail = await api(`/incidents/${id}`);
  if (Array.isArray(detail.hypotheses)) detail.hypotheses = detail.hypotheses.map(adaptHypothesis);
  return detail;
}

// Shared reactive-ish store. Views read from here; main.js mutates it.
export const store = {
  stats: null, analytics: null, incidents: [], selected: null,
  detail: null, engine: null, audit: [],
  listeners: new Set(),
};
export function emit() { store.listeners.forEach(fn => fn()); }
export function onChange(fn) { store.listeners.add(fn); }

// Efficient poller: single timer, skips if a fetch is in flight, stops on hidden tab.
export function poll(fn, ms) {
  let busy = false;
  const tick = async () => {
    if (document.hidden || busy) return;
    busy = true;
    try { await fn(); } catch (e) { /* transient; keep polling */ }
    busy = false;
  };
  return setInterval(tick, ms);
}
