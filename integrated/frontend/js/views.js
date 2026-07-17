// View renderers. All data from real backend responses via store.
import { api, store } from "./api.js";
import { hbar, bar, donut, stacked, area, COLORS } from "./charts.js";
import { forceGraph } from "./graph.js";
import { countUp, enter, fadeIn } from "./anim.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = n => n == null ? "—" : Number(n).toLocaleString();

// ---------------- OVERVIEW ----------------
// One spec drives every analytics chart (reuse, not 22 bespoke blocks).
const CHART_SPECS = [
  { id: "incidents_by_severity",        t: "Incident Severity",          fn: donut,   c: COLORS.SEV },
  { id: "evidence_bucket_distribution", t: "Evidence Split",             fn: donut,   c: COLORS.EVI },
  { id: "incidents_by_attack",          t: "Incidents by Attack",        fn: hbar },
  { id: "predicted_attack_distribution",t: "ML Prediction Distribution", fn: bar },
  { id: "confidence_histogram",         t: "Model Confidence Dist.",     fn: bar,     hint: "flows by predicted confidence" },
  { id: "hypothesis_confidence_histogram", t: "Hypothesis Confidence",   fn: bar },
  { id: "shap_top_feature_frequency",   t: "SHAP Top-Feature Frequency", fn: hbar,    hint: "most-driving feature per flow" },
  { id: "root_cause_frequency",         t: "Root-Cause Frequency",       fn: hbar },
  { id: "evidence_type_distribution",   t: "Evidence Types",             fn: hbar },
  { id: "proto_distribution",           t: "Protocol Usage",             fn: hbar },
  { id: "service_distribution",         t: "Service Distribution",       fn: hbar },
  { id: "state_distribution",           t: "Connection State",           fn: bar },
  { id: "binary_label_distribution",    t: "Binary Label (ground truth)",fn: donut,   c: COLORS.EVI },
  { id: "split_distribution",           t: "Train / Test Split",         fn: donut },
  { id: "incidents_over_time",          t: "Incidents Over Time",        fn: area,    wide: true },
  { id: "top_affected_hosts",           t: "Top Affected Hosts",         fn: hbar },
  { id: "config_changes_by_severity",   t: "Config Changes by Severity", fn: donut,   c: COLORS.SEV },
  { id: "config_changes_by_host",       t: "Config Changes by Host",     fn: hbar },
  { id: "audit_action_distribution",    t: "Audit Actions",              fn: hbar },
  { id: "reviewer_actions",             t: "Reviewer Decisions",         fn: donut,   c: { reviewer_approved:"#5aa77f", reviewer_rejected:"#c56b6b" } },
];

export function renderOverview() {
  const s = store.stats; if (!s) return;
  const topA = Object.entries(s.by_attack_cat || {}).sort((a, b) => b[1] - a[1])[0] || ["—", 0];
  const high = (s.by_severity?.critical || 0) + (s.by_severity?.high || 0);
  const kpis = [
    ["Processed Flows", s.flows_scored, "🌊", "batch-scored"],
    ["Anomalous Flows", s.anomalous_flows, "⚡", ((s.anomalous_flows / s.flows_scored * 100) || 0).toFixed(0) + "% of total"],
    ["Incidents", s.total_incidents, "◈", "correlated"],
    ["High-Severity", high, "⚠️", "critical + high"],
    ["Confirmed Evidence", s.evidence_confirmed, "🟢", "direct links"],
    ["Missing Evidence", s.evidence_missing, "🔴", "explicit gaps"],
    ["Hypotheses", s.hypotheses_generated, "🧠", "generated"],
    ["Audit Entries", s.audit_entries, "🧾", "actions logged"],
  ];
  const mEl = $("#metrics");
  mEl.innerHTML = kpis.map(([l, v, i, sub]) => `<div class="metric">
    <div class="top"><span class="lbl">${l}</span><span class="ico">${i}</span></div>
    <div class="val" data-count="${typeof v === "number" ? v : ""}">${typeof v === "number" ? "0" : esc(v)}</div>
    <div class="sub">${esc(sub)}</div></div>`).join("");
  // top-attack card value is a string
  mEl.querySelectorAll(".val").forEach(el => { const c = el.dataset.count; if (c !== "") countUp(el, +c); });
  enter("#metrics .metric");

  // charts grid
  const grid = $("#chartGrid");
  grid.innerHTML = CHART_SPECS.map(sp => `<div class="card ${sp.wide ? "wide" : ""}" data-spec="${sp.id}">
    <h3>${sp.t}${sp.hint ? `<span class="hint">${sp.hint}</span>` : ""}</h3>
    <div class="chart-host" id="ch-${sp.id}"><div class="skel chart-skel"></div></div></div>`).join("");

  const a = store.analytics; if (!a) return;
  for (const sp of CHART_SPECS) {
    const host = document.getElementById("ch-" + sp.id);
    let data = a[sp.id];
    if (sp.id === "avg_bytes_by_attack" && data) data = Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v.sbytes]));
    try { sp.fn(host, data, sp.c); } catch (e) { host.closest(".card").classList.add("hidden"); }
  }
}

// ---------------- INCIDENTS ----------------
let sort = { k: "flow_count", dir: -1 };
export function renderIncidents() {
  const q = ($("#search")?.value || "").toLowerCase();
  const fs = $("#fSeverity")?.value || "", fa = $("#fAttack")?.value || "";
  let rows = store.incidents.filter(i =>
    (!fs || i.severity === fs) && (!fa || i.attack_cat === fa) &&
    (!q || `${i.node_id} ${i.attack_cat} ${i.severity} ${i.incident_id}`.toLowerCase().includes(q)));
  const { k, dir } = sort;
  rows.sort((a, b) => { const x = a[k] ?? "", y = b[k] ?? ""; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
  const rev = store._reviewByIncident || {};   // hypothesis/review sync (set by main.js)
  const hyp = store._hypByIncident || {};
  $("#incBody").innerHTML = rows.map(i => {
    const r = rev[i.incident_id]; const h = hyp[i.incident_id];
    const status = r === "reviewer_approved" ? '<span class="tag-ok">approved</span>'
      : r === "reviewer_rejected" ? '<span class="tag-warn">rejected</span>' : '<span class="tag-none">pending</span>';
    const rc = h ? esc(h.root_cause) : "—";
    const conf = h && h.confidence != null ? Math.round(h.confidence * 100) + "%" : "—";
    return `<tr data-id="${i.incident_id}" class="${store.selected === i.incident_id ? "sel" : ""}">
      <td>#${i.incident_id}</td><td>${esc(i.attack_cat)}</td>
      <td><span class="pill sev-${esc(i.severity)}">${esc(i.severity)}</span></td>
      <td>${esc(i.node_id)}</td><td>${fmt(i.flow_count)}</td><td>${rc}</td><td>${conf}</td>
      <td>${status}</td><td>${esc(i.start_ts)}</td></tr>`;
  }).join("") || '<tr><td colspan="9" class="empty">No matches.</td></tr>';
}
export function bindIncidentSort() {
  document.querySelectorAll("#incTable th").forEach(th => th.onclick = () => {
    const k = th.dataset.k; sort = { k, dir: sort.k === k ? -sort.dir : 1 }; renderIncidents();
  });
}
export function populateFilters() {
  const sevs = [...new Set(store.incidents.map(i => i.severity))];
  const atks = [...new Set(store.incidents.map(i => i.attack_cat))].sort();
  $("#fSeverity").innerHTML = '<option value="">All severities</option>' + sevs.map(s => `<option>${esc(s)}</option>`).join("");
  $("#fAttack").innerHTML = '<option value="">All attacks</option>' + atks.map(a => `<option>${esc(a)}</option>`).join("");
}

// ---------------- INCIDENT DETAIL ----------------
export function renderDetail() {
  const d = store.detail; if (!d) return;
  const inc = d.incident;
  $("#evSub").textContent = `Incident #${inc.incident_id} · ${inc.attack_cat} on ${inc.node_id}`;
  $("#incSummary").innerHTML = `<h3>Incident Summary</h3><div class="grid three" style="gap:10px">
    ${kv("Incident ID", "#" + inc.incident_id)}${kv("Attack", esc(inc.attack_cat))}
    ${kv("Severity", `<span class="pill sev-${esc(inc.severity)}">${esc(inc.severity)}</span>`)}
    ${kv("Primary Node", esc(inc.node_id))}${kv("Cluster Size", fmt(inc.flow_count) + " flows")}
    ${kv("Window", esc(inc.start_ts) + " → " + esc(inc.end_ts))}</div>`;
  renderEvidence(d.evidence_by_bucket);
  renderRelated(inc);
  // root cause reflects engine if already run
  const eng = store.engine && store.engine.incident_id === inc.incident_id ? store.engine : null;
  const top = eng?.ranked_hypotheses?.find(h => h.grounded);
  $("#rootCard").innerHTML = top
    ? `<div style="font-size:19px;font-weight:800;color:var(--accent2)">${esc(top.root_cause_node)}</div>
       <div style="margin:6px 0">${esc(top.claim)}</div><div class="hint">confidence ${Math.round((top.confidence || 0) * 100)}%</div>`
    : '<div class="empty">Run the Hypotheses Engine to derive the root cause.</div>';
  fadeIn($("#incSummary"));
}
const kv = (k, v) => `<div class="ev-item"><div class="type">${k}</div><div>${v}</div></div>`;
function renderEvidence(b) {
  const total = (b.confirmed?.length || 0) + (b.correlated?.length || 0) + (b.missing?.length || 0);
  const col = (key, label, icon) => {
    const it = b[key] || [];
    const body = it.length ? it.map(e => `<div class="ev-item"><div class="type">${esc(e.evidence_type)} · ${esc(e.node_id || "")}</div><div>${esc(e.description)}</div></div>`).join("")
      : (key === "missing"
        ? '<div class="ev-empty">✓ No gaps flagged in this bucket.</div>'
        : `<div class="ev-empty">No ${label.toLowerCase()} evidence — the correlation engine found none for this incident.</div>`);
    return `<div class="ev-col ${key}"><h4>${icon} ${label}<span class="count">${it.length}</span></h4>${body}</div>`;
  };
  $("#evMatrix").innerHTML = col("confirmed", "Confirmed", "🟢") + col("correlated", "Correlated", "🟡") + col("missing", "Missing", "🔴");
  if (total === 0) $("#evMatrix").insertAdjacentHTML("afterbegin",
    '<div class="empty" style="grid-column:1/-1">This incident produced no evidence rows in the backend.</div>');
}
function renderRelated(inc) {
  const rel = store.incidents.filter(i => i.incident_id !== inc.incident_id &&
    (i.node_id === inc.node_id || i.attack_cat === inc.attack_cat)).slice(0, 6);
  $("#related").innerHTML = rel.length ? rel.map(i => `<div class="ev-item" style="cursor:pointer" data-goto="${i.incident_id}">
    <div class="type">${esc(i.attack_cat)} · <span class="pill sev-${esc(i.severity)}">${esc(i.severity)}</span></div>
    <div>#${i.incident_id} on ${esc(i.node_id)} · ${fmt(i.flow_count)} flows</div></div>`).join("")
    : '<div class="empty">No related incidents.</div>';
}

// ---------------- HYPOTHESES ----------------
export function renderHypotheses(r) {
  $("#engineMeta").textContent = `#${r.incident_id} · ${r.attack_cat} · ${r.ranked_hypotheses.length} hypotheses`;
  const rem = r.remediation || [];
  $("#hypList").innerHTML = r.ranked_hypotheses.map((h, i) => {
    const pct = Math.round((h.confidence || 0) * 100);
    const steps = i === 0 && rem.length ? `<div style="margin-top:8px"><b>Remediation</b><ul class="steps">${rem.map(s => `<li>${esc(s.step)}<div class="why">${esc(s.rationale)}</div></li>`).join("")}</ul></div>` : "";
    const reason = !h.grounded && h.rejected_reason ? `<div class="reject-reason">✗ ${esc(h.rejected_reason)}</div>` : "";
    return `<div class="hyp ${h.grounded ? "" : "rejected"}" data-h="${i}"><div class="head"><span class="rank">${i + 1}</span><b>${esc(h.root_cause_node)}</b>
      <span class="badge ${h.grounded ? "grounded" : "rejected"}">${h.grounded ? "grounded" : "rejected"}</span><span class="conf">${pct}%</span></div>
      <div class="confbar"><i style="width:0" data-w="${pct}"></i></div><div>${esc(h.claim)}</div>
      <div class="hint">Cites: ${(h.cited_evidence_ids || []).map(esc).join(", ") || "—"}</div>${reason}
      <button class="toggle">▾ details</button>
      <div class="expand"><div>Tier breakdown: <code>${esc(JSON.stringify(h.evidence_tier_breakdown || {}))}</code></div>${steps}</div></div>`;
  }).join("") || '<div class="empty">No hypotheses — this incident has only <b>missing</b> evidence, so no root cause is asserted from absence (by design).</div>';
  requestAnimationFrame(() => document.querySelectorAll("#hypList .confbar i").forEach(i => i.style.width = i.dataset.w + "%"));
  $("#hypList").querySelectorAll(".toggle").forEach(b => b.onclick = () => b.closest(".hyp").classList.toggle("open"));
  $("#traceCard").classList.remove("hidden");
  $("#traceList").innerHTML = (r.trace_log || []).map(l => `<li>${esc(l)}</li>`).join("");
}

// ---------------- KNOWLEDGE GRAPH ----------------
export async function renderGraph() {
  const wrap = $("#graphWrap");
  if (!store.selected) { wrap.innerHTML = '<div class="empty">Select an incident.</div>'; return; }
  const d = store.detail; if (!d) return;
  let eng = store.engine && store.engine.incident_id === store.selected ? store.engine : null;
  if (!eng) { try { eng = await api(`/incidents/${store.selected}/hypotheses/regenerate`, { method: "POST" }); store.engine = eng; } catch (e) { } }
  const types = { incident: "#4b7bb5", evidence: "#c99a54", host: "#67c5c0", hypothesis: "#7c85c9", root: "#5aa77f", action: "#b96fa3" };
  $("#graphLegend").innerHTML = Object.entries(types).map(([k, c]) => `<span><span class="dot" style="background:${c}"></span>${k}</span>`).join("");
  const nodes = [], links = [], seen = new Set();
  const add = (id, label, type, meta, r) => { if (!seen.has(id)) { seen.add(id); nodes.push({ id, label, type, meta, color: types[type], r }); } };
  const inc = d.incident;
  add("inc", "INC #" + inc.incident_id, "incident", `${inc.attack_cat} · ${inc.severity}`, 15);
  add("host:" + inc.node_id, inc.node_id, "host", "primary affected host");
  links.push({ source: "inc", target: "host:" + inc.node_id });
  (d.evidence || []).slice(0, 8).forEach((e, i) => {
    const id = "ev" + i; add(id, e.evidence_type, "evidence", `[${e.bucket}] ${e.description}`);
    links.push({ source: "inc", target: id });
    if (e.node_id) { add("host:" + e.node_id, e.node_id, "host", "evidence host"); links.push({ source: id, target: "host:" + e.node_id }); }
  });
  const grounded = (eng?.ranked_hypotheses || []).filter(h => h.grounded).slice(0, 4);
  grounded.forEach((h, i) => {
    const id = "hyp" + i; add(id, "Hypothesis", "hypothesis", h.claim); links.push({ source: "inc", target: id });
    add("root:" + h.root_cause_node, h.root_cause_node, "root", "root cause"); links.push({ source: id, target: "root:" + h.root_cause_node });
  });
  (eng?.remediation || []).slice(0, 3).forEach((s, i) => { const id = "act" + i; add(id, "Action", "action", s.step); if (grounded[0]) links.push({ source: "hyp0", target: id }); });
  forceGraph(wrap, nodes, links, { onSelect: n => $("#graphDetail").innerHTML = `<b style="color:${types[n.type]}">${esc(n.type).toUpperCase()}</b> — ${esc(n.label)}<br><span class="hint">${esc(n.meta || "")}</span>`, height: Math.min(560, window.innerHeight * .62) });
}

// ---------------- TOPOLOGY ----------------
export function renderTopology() {
  const wrap = $("#topoWrap"); const ip = store.detail?.impact_path;
  if (!ip) { wrap.innerHTML = '<div class="empty">Select an incident.</div>'; return; }
  $("#topoLegend").innerHTML = ['<span><span class="dot" style="background:#4b7bb5"></span>Root cause</span>',
    '<span><span class="dot" style="background:#c99a54"></span>Upstream candidate</span>',
    '<span><span class="dot" style="background:#8b98ad"></span>Downstream impact</span>'].join("");
  const nodes = [{ id: ip.node, label: ip.node, type: "root", meta: "root cause node", color: "#4b7bb5", r: 15 }];
  const links = [];
  (ip.upstream_candidates || []).slice(0, 8).forEach(([n, dist]) => { nodes.push({ id: n, label: n, type: "up", meta: `upstream · ${dist} hop`, color: "#c99a54" }); links.push({ source: n, target: ip.node }); });
  (ip.downstream_impact || []).slice(0, 10).forEach(([n, dist]) => { nodes.push({ id: n, label: n, type: "down", meta: `downstream · ${dist} hop`, color: "#8b98ad" }); links.push({ source: ip.node, target: n }); });
  forceGraph(wrap, nodes, links, { onSelect: n => $("#topoDetail").innerHTML = `<b>${esc(n.label)}</b> — <span class="hint">${esc(n.meta || "")}</span>`, height: Math.min(520, window.innerHeight * .58) });
}

// ---------------- TIMELINE ----------------
const STAGES = [["01", "Flow Ingestion", "UNSW-NB15 → rca.db", 0], ["02", "ML Classification", "XGBoost + SHAP", 0], ["03", "Evidence Correlation", "confirmed/correlated/missing", 0], ["04", "Hypothesis Generation", "LLM narrative", 0], ["05", "Deterministic Ground-Check", "rejects hallucinations", 1], ["06", "Remediation Output", "ranked causes + steps", 0]];
export function renderPipeline() {
  $("#pipeline").innerHTML = STAGES.map(([n, t, d, det]) => `<div class="stage ${det ? "det" : ""}"><div class="n">STEP ${n}</div><div class="t">${t}</div><div class="d">${d}</div></div>`).join("");
}
export function renderEventTimeline() {
  const ev = store.detail?.timeline || [];
  $("#eventTl").innerHTML = ev.length ? ev.map(e => `<li class="${esc(e.source_type)}">
    <span class="t">${esc(e.timestamp)} · ${esc(e.source_type)} · ${esc(e.node_id || "")}</span>
    <div>${esc(String(e.details).slice(0, 80))}${String(e.details).length > 80 ? "…" : ""}</div>
    <div class="more">${esc(e.details)}</div></li>`).join("") : '<div class="empty">Select an incident.</div>';
  $("#eventTl").querySelectorAll("li").forEach(li => li.onclick = () => li.classList.toggle("open"));
}

// ---------------- AUDIT (SIEM) ----------------
let prevAuditIds = new Set();
export function renderAudit() {
  const q = ($("#logSearch")?.value || "").toLowerCase();
  const fa = $("#logActor")?.value || "";
  const rows = store.audit.filter(r => (!fa || r.actor.startsWith(fa)) && (!q || JSON.stringify(r).toLowerCase().includes(q)));
  const curIds = new Set(store.audit.map(r => r.audit_id));
  $("#auditBody").innerHTML = rows.length ? rows.map(r => {
    const lvl = r.actor.startsWith("reviewer") ? "reviewer" : "system";
    const isNew = !prevAuditIds.has(r.audit_id) && prevAuditIds.size > 0;
    return `<div class="row ${isNew ? "new" : ""}"><span class="ts">${esc(r.ts)}</span><span class="lvl ${lvl}">${lvl}</span>
      <span class="msg"><b>${esc(r.action)}</b> — ${esc(r.actor)}${r.incident_id != null ? ` · inc #${r.incident_id}` : ""}
      <div class="det">${esc(r.details || "(no details)")}\naudit_id=${r.audit_id}</div></span></div>`;
  }).join("") : '<div class="empty">No matching log entries.</div>';
  $("#auditBody").querySelectorAll(".row").forEach(row => row.onclick = () => row.classList.toggle("open"));
  prevAuditIds = curIds;
}
