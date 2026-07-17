// // Main Bootstrap, state coordination, and application shell orchestrator.
// import { api, store, poll, getDetail } from "./api.js";
// import { pulse } from "./anim.js";

// // Import UI components
// import { LandingPage } from "./components/LandingPage.js";
// import { Sidebar } from "./components/Sidebar.js";
// import { KpiCards } from "./components/KpiCards.js";
// import { AnalyticsDashboard } from "./components/AnalyticsDashboard.js";
// import { KnowledgeGraph } from "./components/KnowledgeGraph.js";
// import { NetworkTopology } from "./components/NetworkTopology.js";
// import { Timeline } from "./components/Timeline.js";
// import { ExplainabilityPanel, TELEMETRY_TEMPLATES } from "./components/ExplainabilityPanel.js";
// import { EvidenceMatrix } from "./components/EvidenceMatrix.js";
// import { RootCausePanel } from "./components/RootCausePanel.js";
// import { RelatedIncidents } from "./components/RelatedIncidents.js";
// import { AuditConsole } from "./components/AuditConsole.js";
// import { shapChart } from "./charts.js";

// const $ = s => document.querySelector(s);
// const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// const fmt = n => n == null ? "—" : Number(n).toLocaleString();

// // Local UI Sort state
// let sort = { k: "flow_count", dir: -1 };

// // Instantiate Components
// const landing = new LandingPage("#landing", enterApp);
// const sidebar = new Sidebar("#sidebar", "overview", switchView);
// const kpis = new KpiCards("#metrics");
// const dashboard = new AnalyticsDashboard("#chartGrid");
// const kg = new KnowledgeGraph("#graphWrap", "#graphDetail");
// const topology = new NetworkTopology("#topoWrap", "#topoDetail");
// const timeline = new Timeline("#pipeline", "#eventTl");
// const explainability = new ExplainabilityPanel("#shapContainer");
// const evidenceMatrix = new EvidenceMatrix("#evMatrix");
// const rootCausePanel = new RootCausePanel("#rootCard");
// const relatedIncidents = new RelatedIncidents("#related");
// const auditConsole = new AuditConsole("#auditBody", {
//   search: "#logSearch",
//   actor: "#logActor",
//   approve: "#v-audit [data-decide='approve']",
//   reject: "#v-audit [data-decide='reject']"
// });

// // Setup state mappings
// store._reviewByIncident = {};
// store._hypByIncident = {};

// // Initial render of landing page
// landing.render();

// function enterApp() {
//   $("#landing").classList.add("hide");
//   $("#app").style.display = "grid";
//   setTimeout(() => $("#landing").classList.add("hidden"), 600);
//   if (!store.stats) bootstrap();
// }

// // Check for direct bypass hash
// if (location.hash === "#app") {
//   enterApp();
// }

// async function loadCore() {
//   const [stats, analytics, incidents, audit] = await Promise.all([
//     api("/stats"), 
//     api("/analytics").catch(() => null), 
//     api("/incidents"), 
//     api("/audit-log?limit=300").catch(() => [])
//   ]);
  
//   store.stats = stats; 
//   store.analytics = analytics; 
//   store.incidents = incidents; 
//   store.audit = audit;
  
//   buildReviewMap();
  
//   $("#h-api").className = "dot ok"; 
//   $("#h-db").className = "dot ok";
//   $("#h-updated").textContent = "Updated " + new Date().toLocaleTimeString();
// }

// function buildReviewMap() {
//   const m = {};
//   // Newest first; lock in first status change per incident
//   for (const r of store.audit) {
//     if (r.actor.startsWith("reviewer") && r.incident_id != null && !(r.incident_id in m)) {
//       m[r.incident_id] = r.action;
//     }
//   }
//   store._reviewByIncident = m;
  
//   // Calculate critical alert count for sidebar badge
//   const criticalCount = store.incidents.filter(i => {
//     const isReviewed = i.incident_id in m;
//     return i.severity.toLowerCase() === "critical" && !isReviewed;
//   }).length;
  
//   sidebar.updateBadge(criticalCount);
// }

// async function bootstrap() {
//   try { 
//     await loadCore(); 
//   } catch (e) { 
//     $("#h-api").className = "dot bad"; 
//     $("#h-db").className = "dot bad"; 
//     $("#h-updated").textContent = "API Unreachable"; 
//     return; 
//   }
  
//   sidebar.render();
//   populateFilters();
//   bindIncidentSort();
//   renderIncidentsTable();
  
//   // Render Overview Dashboard
//   kpis.render(store.stats, store.analytics);
//   dashboard.render(store.analytics);
  
//   // Initialize events
//   auditConsole.bindEvents(decide);
//   startAuditPolling();

//   // Prefetch details in background
//   fetchIncidentsDetailsInBackground();
// }

// async function fetchIncidentsDetailsInBackground() {
//   const ids = store.incidents.map(i => i.incident_id);
//   const chunkSize = 5;
//   for (let i = 0; i < ids.length; i += chunkSize) {
//     const chunk = ids.slice(i, i + chunkSize);
//     await Promise.all(chunk.map(async id => {
//       try {
//         const detail = await getDetail(id);
//         const hyps = detail.hypotheses || [];
//         const top = hyps.find(h => h.grounded);
//         if (top) {
//           store._hypByIncident[id] = {
//             root_cause: top.root_cause_node,
//             confidence: top.confidence || (top.confidence_pct / 100)
//           };
//         } else {
//           store._hypByIncident[id] = {
//             root_cause: "none",
//             confidence: null
//           };
//         }
//       } catch (err) {
//         console.error(`Failed to prefetch detail for incident ${id}:`, err);
//       }
//     }));
//     renderIncidentsTable();
//   }
// }

// // Global Refresh Action
// $("#refreshBtn")?.addEventListener("click", async () => {
//   const btn = $("#refreshBtn");
//   btn.disabled = true;
//   btn.textContent = "↻ Syncing...";
//   try {
//     await loadCore(); 
//     renderIncidentsTable(); 
//     kpis.render(store.stats, store.analytics);
//     dashboard.render(store.analytics);
//     if (store.selected) {
//       // Re-query current detail
//       store.detail = await getDetail(store.selected);
//       renderDetailPanels();
//     }
//     auditConsole.render(store.audit, store.selected, decide);
//   } catch (err) {}
//   btn.disabled = false;
//   btn.textContent = "↻ Refresh";
// });

// // ---------- Selection & Pivot ----------
// async function selectIncident(id) {
//   store.selected = id; 
//   store.engine = null;
  
//   // Highlight table selection
//   document.querySelectorAll("#incBody tr").forEach(tr => {
//     tr.classList.toggle("sel", +tr.dataset.id === id);
//   });
  
//   try {
//     store.detail = await getDetail(store.selected);
    
//     // Immediately calculate hypotheses mapping from pre-existing hypotheses
//     const hyps = store.detail.hypotheses || [];
//     const top = hyps.find(h => h.grounded);
//     if (top) {
//       store._hypByIncident[id] = {
//         root_cause: top.root_cause_node,
//         confidence: top.confidence || (top.confidence_pct / 100)
//       };
//     } else {
//       store._hypByIncident[id] = {
//         root_cause: "none",
//         confidence: null
//       };
//     }
//     renderIncidentsTable();

//     renderDetailPanels();
    
//     // Auto-update active visualization states if open
//     if ($("#v-graph").classList.contains("active")) kg.render(store.selected, store.detail);
//     if ($("#v-topology").classList.contains("active")) topology.render(store.selected, store.detail);
//     if ($("#v-timeline").classList.contains("active")) timeline.render(store.selected, store.detail);
//     if ($("#v-shap").classList.contains("active")) explainability.render(store.detail.incident);
    
//     switchView("evidence");
//   } catch (e) {
//     console.error("Failed to select incident:", e);
//   }
// }

// // Render sub panels
// function renderDetailPanels() {
//   const d = store.detail;
//   if (!d) return;

//   const inc = d.incident;
  
//   // Summary Details Card
//   $("#evSub").textContent = `Incident #${inc.incident_id} Target: ${inc.node_id} (${inc.attack_cat})`;
//   $("#incSummary").innerHTML = `
//     <h3>Incident Ingestion Summary</h3>
//     <div class="grid three" style="gap:15px; font-family:var(--font);">
//       <div><span style="color:var(--muted); font-size:11.5px;">Incident ID</span><br><b style="font-family:var(--mono);">#${inc.incident_id}</b></div>
//       <div><span style="color:var(--muted); font-size:11.5px;">Threat Category</span><br><b>${esc(inc.attack_cat)}</b></div>
//       <div><span style="color:var(--muted); font-size:11.5px;">Severity Rank</span><br><span class="pill sev-${esc(inc.severity)}">${esc(inc.severity)}</span></div>
//       <div><span style="color:var(--muted); font-size:11.5px;">Target Node</span><br><b style="font-family:var(--mono);">${esc(inc.node_id)}</b></div>
//       <div><span style="color:var(--muted); font-size:11.5px;">Cluster Volume</span><br><b>${fmt(inc.flow_count)} Scored Flows</b></div>
//       <div><span style="color:var(--muted); font-size:11.5px;">Ingestion Window</span><br><span style="font-family:var(--mono); font-size:12.5px;">${esc(inc.start_ts.slice(11))} &rarr; ${esc(inc.end_ts.slice(11))}</span></div>
//     </div>
//   `;

//   // Render components
//   evidenceMatrix.render(d.evidence_by_bucket);
//   rootCausePanel.render(d, store.engine);
//   relatedIncidents.render(store.incidents, inc);

//   // Trigger automatic SHAP profiling for the details card (Dataset Analysis PRIMARY)
//   const shapHost = document.getElementById("incShapResult");
//   if (shapHost && inc) {
//     const template = TELEMETRY_TEMPLATES[inc.attack_cat] || TELEMETRY_TEMPLATES.DoS;
//     shapHost.innerHTML = `<div class="skel chart-skel"></div>`;
    
//     api("/score", {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({
//         ...template,
//         dinpkt: 0.0,
//         ct_src_dport_ltm: 4,
//         ct_dst_sport_ltm: 2
//       })
//     }).then(response => {
//       if (store.selected === inc.incident_id && document.getElementById("incShapResult")) {
//         shapChart(document.getElementById("incShapResult"), response.shap, response.attack_cat_pred, response.confidence);
//       }
//     }).catch(err => {
//       console.error("SHAP details card failed:", err);
//       if (store.selected === inc.incident_id && document.getElementById("incShapResult")) {
//         document.getElementById("incShapResult").innerHTML = `<div class="reject-reason">Telemetry explainability evaluation failed: ${err.message}</div>`;
//       }
//     });
//   }
// }

// // Event delegation for pivots and row clicks
// document.addEventListener("click", e => {
//   const row = e.target.closest("#incBody tr[data-id]"); 
//   if (row) return selectIncident(+row.dataset.id);
  
//   const goto = e.target.closest("[data-goto]"); 
//   if (goto) return selectIncident(+goto.dataset.goto);
// });

// // Filter triggers
// ["search", "fSeverity", "fAttack"].forEach(id => {
//   const el = $("#" + id);
//   if (el) el.addEventListener("input", renderIncidentsTable);
// });

// // ---------- Hypotheses Engine ----------
// $("#runBtn")?.addEventListener("click", runEngine);
// async function runEngine() {
//   if (!store.selected) return alert("Select an incident from the Incident list first.");
  
//   const btn = $("#runBtn"); 
//   btn.disabled = true; 
//   btn.innerHTML = '<span class="spinner"></span> Running reasoning trace...';
  
//   try {
//     const r = await api(`/incidents/${store.selected}/hypotheses/regenerate`, { method: "POST" });
//     store.engine = r;
    
//     // Set grounding cache
//     const topGrounded = r.ranked_hypotheses.find(h => h.grounded);
//     store._hypByIncident[store.selected] = {
//       root_cause: topGrounded ? topGrounded.root_cause_node : "none",
//       confidence: topGrounded ? topGrounded.confidence : null
//     };

//     // Update Hypotheses view list
//     $("#engineMeta").textContent = `#${r.incident_id} &bull; Vector: ${r.attack_cat} &bull; proposed: ${r.ranked_hypotheses.length} hypotheses`;
    
//     $("#hypList").innerHTML = r.ranked_hypotheses.map((h, i) => {
//       const pct = Math.round((h.confidence || 0) * 100);
//       const steps = i === 0 && r.remediation?.length 
//         ? `<div style="margin-top:12px"><b>Remediation Protocol Playbook</b><ul class="steps">${r.remediation.map(s => `<li>${esc(s.step)}<div class="why">${esc(s.rationale)}</div></li>`).join("")}</ul></div>` 
//         : "";
//       const reason = !h.grounded && h.rejected_reason 
//         ? `<div class="reject-reason">✗ Ground-check rejection: ${esc(h.rejected_reason)}</div>` 
//         : "";

//       return `
//         <div class="hyp ${h.grounded ? '' : 'rejected'}" id="hyp-card-${i}">
//           <div class="head">
//             <span class="rank">${i + 1}</span>
//             <b>${esc(h.root_cause_node)}</b>
//             <span class="badge ${h.grounded ? 'grounded' : 'rejected'}">${h.grounded ? 'grounded' : 'rejected'}</span>
//             <span class="conf">${pct}%</span>
//           </div>
//           <div class="confbar"><i style="width:0%" data-width="${pct}"></i></div>
//           <div style="font-size:13px; line-height:1.45; color:var(--txt);">${esc(h.claim)}</div>
//           <div class="hint" style="margin-top:8px;">Cites Evidence: ${(h.cited_evidence_ids || []).map(esc).join(", ") || "—"}</div>
//           ${reason}
//           <button class="toggle" id="hyp-toggle-${i}">▾ view details</button>
//           <div class="expand">
//             <div style="font-family:var(--mono); font-size:11.5px; background:rgba(0,0,0,0.2); padding:8px; border-radius:6px;">
//               Tier weights: ${esc(JSON.stringify(h.evidence_tier_breakdown || {}))}
//             </div>
//             ${steps}
//           </div>
//         </div>
//       `;
//     }).join("") || '<div class="empty">No hypotheses returned for this cluster.</div>';

//     // Trigger gauge bars transition
//     requestAnimationFrame(() => {
//       document.querySelectorAll("#hypList .confbar i").forEach(bar => {
//         bar.style.width = bar.dataset.width + "%";
//       });
//     });

//     // Bind hyp detail collapses
//     document.querySelectorAll("#hypList .toggle").forEach(b => {
//       b.onclick = () => {
//         const hyp = b.closest(".hyp");
//         hyp.classList.toggle("open");
//         b.textContent = hyp.classList.contains("open") ? "▴ hide details" : "▾ view details";
//       };
//     });

//     $("#traceCard").classList.remove("hidden");
//     $("#traceList").innerHTML = (r.trace_log || []).map(log => `<li>${esc(log)}</li>`).join("");

//     await refreshAuditLogs();
    
//     // Sync incident summaries back to tables
//     renderDetailPanels();
//     renderIncidentsTable();
//   } catch (err) {
//     $("#hypList").innerHTML = `<div class="reject-reason">Hypothesis Engine failed: ${err.message}</div>`;
//   }
  
//   btn.disabled = false; 
//   btn.innerHTML = "▶ Run reasoning engine";
// }

// // ---------- Review Action Decisions ----------
// async function decide(dec) {
//   if (!store.selected) return alert("Select an incident to review first.");
//   try {
//     await api(`/incidents/${store.selected}/review`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({ 
//         decision: dec, 
//         reviewer: "L2 Analyst", 
//         note: `Analyst verification: ${dec} completed via command panel.` 
//       })
//     });
    
//     await refreshAuditLogs();
//     renderIncidentsTable();
    
//     // Trigger immediate updates on details panel
//     if (store.detail) {
//       store.detail = await getDetail(store.selected);
//       renderDetailPanels();
//     }
//   } catch (err) {
//     alert("Decision write failed: " + err.message);
//   }
// }

// // ---------- Log Polling ----------
// async function refreshAuditLogs() {
//   store.audit = await api("/audit-log?limit=300").catch(() => store.audit);
//   buildReviewMap();
//   auditConsole.render(store.audit, store.selected, decide);
// }

// let auditTimer = null;
// function startAuditPolling() {
//   if (auditTimer) return;
//   // Dynamic SIEM Poller: runs when Audit is open and tab is focused
//   auditTimer = poll(async () => {
//     if (!$("#v-audit").classList.contains("active")) return;
//     const before = store.audit[0]?.audit_id;
    
//     store.audit = await api("/audit-log?limit=300");
//     if (store.audit[0]?.audit_id !== before) {
//       buildReviewMap();
//       auditConsole.render(store.audit, store.selected, decide);
//       renderIncidentsTable();
//     }
//   }, 1000); // 1.0s interval
// }

// ["logSearch", "logActor"].forEach(id => {
//   const el = $("#" + id);
//   if (el) {
//     el.addEventListener("input", () => {
//       auditConsole.render(store.audit, store.selected, decide);
//     });
//   }
// });

// // ---------- Routing Views ----------
// function switchView(name) {
//   document.querySelectorAll(".view").forEach(v => {
//     v.classList.toggle("active", v.id === "v-" + name);
//   });
  
//   sidebar.setActive(name);

//   // Lazy render triggers
//   if (name === "overview") {
//     kpis.render(store.stats, store.analytics);
//     dashboard.render(store.analytics);
//   }
//   if (name === "graph") {
//     kg.render(store.selected, store.detail);
//   }
//   if (name === "topology") {
//     topology.render(store.selected, store.detail);
//   }
//   if (name === "timeline") {
//     timeline.render(store.selected, store.detail);
//   }
//   if (name === "shap") {
//     explainability.render(store.detail?.incident);
//   }
//   if (name === "audit") {
//     auditConsole.render(store.audit, store.selected, decide);
//   }
//   if (name === "hypotheses" && store.selected && !$("#hypList").children.length) {
//     runEngine();
//   }

//   $(".main").scrollTop = 0;
// }

// // ---------- Incident Table Helper ----------
// function renderIncidentsTable() {
//   const q = ($("#search")?.value || "").toLowerCase();
//   const fs = $("#fSeverity")?.value || "";
//   const fa = $("#fAttack")?.value || "";
  
//   let rows = store.incidents.filter(i => 
//     (!fs || i.severity === fs) && 
//     (!fa || i.attack_cat === fa) &&
//     (!q || `${i.node_id} ${i.attack_cat} ${i.severity} ${i.incident_id}`.toLowerCase().includes(q))
//   );

//   // Sort logic
//   const { k, dir } = sort;
//   rows.sort((a, b) => {
//     const x = a[k] ?? "";
//     const y = b[k] ?? "";
//     return (x > y ? 1 : x < y ? -1 : 0) * dir;
//   });

//   const rev = store._reviewByIncident || {};
//   const hyp = store._hypByIncident || {};

//   $("#incBody").innerHTML = rows.map(i => {
//     const statusVal = rev[i.incident_id];
//     const statusHtml = statusVal === "reviewer_approved" 
//       ? '<span class="tag-ok">Approved</span>'
//       : statusVal === "reviewer_rejected" 
//         ? '<span class="tag-warn">Rejected</span>' 
//         : '<span class="tag-none">Pending Review</span>';

//     const h = hyp[i.incident_id];
    
//     let rc = `<span style="color:var(--muted); font-size:11px;">Syncing...</span>`;
//     let conf = `<span style="color:var(--muted); font-size:11px;">Syncing...</span>`;
    
//     if (h) {
//       if (h.root_cause === "none" || !h.root_cause) {
//         rc = `<span style="color:var(--muted)">Not Generated</span>`;
//         conf = `<span style="color:var(--muted)">Not Generated</span>`;
//       } else {
//         rc = esc(h.root_cause);
//         conf = h.confidence != null ? Math.round(h.confidence * 100) + "%" : `<span style="color:var(--muted)">Not Generated</span>`;
//       }
//     }

//     return `
//       <tr data-id="${i.incident_id}" class="${store.selected === i.incident_id ? 'sel' : ''}">
//         <td>#${i.incident_id}</td>
//         <td><b>${esc(i.attack_cat)}</b></td>
//         <td><span class="pill sev-${esc(i.severity)}">${esc(i.severity)}</span></td>
//         <td style="font-family:var(--mono);">${esc(i.node_id)}</td>
//         <td style="font-family:var(--mono);">${fmt(i.flow_count)}</td>
//         <td style="font-family:var(--mono); color:var(--cyan);">${rc}</td>
//         <td style="font-family:var(--mono);">${conf}</td>
//         <td>${statusHtml}</td>
//         <td style="font-family:var(--mono); color:var(--muted);">${esc(i.start_ts)}</td>
//       </tr>
//     `;
//   }).join("") || '<tr><td colspan="9" class="empty">No incidents found in workspace.</td></tr>';
// }

// function bindIncidentSort() {
//   document.querySelectorAll("#incTable th").forEach(th => {
//     th.onclick = () => {
//       const k = th.dataset.k;
//       sort = { k, dir: sort.k === k ? -sort.dir : 1 };
//       renderIncidentsTable();
//     };
//   });
// }

// function populateFilters() {
//   const sevs = [...new Set(store.incidents.map(i => i.severity))];
//   const atks = [...new Set(store.incidents.map(i => i.attack_cat))].sort();
  
//   $("#fSeverity").innerHTML = '<option value="">All Severities</option>' + sevs.map(s => `<option>${esc(s)}</option>`).join("");
//   $("#fAttack").innerHTML = '<option value="">All Attack Types</option>' + atks.map(a => `<option>${esc(a)}</option>`).join("");
// }

// // hamb toggle navigation collapse
// $("#hamb").addEventListener("click", () => {
//   $("#app").classList.toggle("collapsed");
//   pulse($("#hamb"));
// });

// // Resize visual elements dynamically
// window.addEventListener("resize", () => {
//   if ($("#v-topology").classList.contains("active")) topology.render(store.selected, store.detail);
//   else if ($("#v-graph").classList.contains("active")) kg.render(store.selected, store.detail);
//   else if ($("#v-overview").classList.contains("active")) dashboard.render(store.analytics);
// });


// Main Bootstrap, state coordination, and application shell orchestrator.
import { api, store, poll, getDetail } from "./api.js";
import { pulse } from "./anim.js";

// Import UI components
import { LandingPage } from "./components/LandingPage.js";
import { Sidebar } from "./components/Sidebar.js";
import { KpiCards } from "./components/KpiCards.js";
import { AnalyticsDashboard } from "./components/AnalyticsDashboard.js";
import { KnowledgeGraph } from "./components/KnowledgeGraph.js";
import { NetworkTopology } from "./components/NetworkTopology.js";
import { Timeline } from "./components/Timeline.js";
import { ExplainabilityPanel, TELEMETRY_TEMPLATES } from "./components/ExplainabilityPanel.js";
import { EvidenceMatrix } from "./components/EvidenceMatrix.js";
import { RootCausePanel } from "./components/RootCausePanel.js";
import { RelatedIncidents } from "./components/RelatedIncidents.js";
import { AuditConsole } from "./components/AuditConsole.js";
import { shapChart } from "./charts.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = n => n == null ? "—" : Number(n).toLocaleString();

// Local UI Sort state
let sort = { k: "flow_count", dir: -1 };

// Instantiate Components
const landing = new LandingPage("#landing", enterApp);
const sidebar = new Sidebar("#sidebar", "overview", switchView);
const kpis = new KpiCards("#metrics");
const dashboard = new AnalyticsDashboard("#chartGrid");
const kg = new KnowledgeGraph("#graphWrap", "#graphDetail");
const topology = new NetworkTopology("#topoWrap", "#topoDetail");
const timeline = new Timeline("#pipeline", "#eventTl");
const explainability = new ExplainabilityPanel("#shapContainer");
const evidenceMatrix = new EvidenceMatrix("#evMatrix");
const rootCausePanel = new RootCausePanel("#rootCard");
const relatedIncidents = new RelatedIncidents("#related");
const auditConsole = new AuditConsole("#auditBody", {
  search: "#logSearch",
  actor: "#logActor",
  approve: "#v-audit [data-decide='approve']",
  reject: "#v-audit [data-decide='reject']"
});

// Setup state mappings
store._reviewByIncident = {};
store._hypByIncident = {};

// Initial render of landing page
landing.render();

function enterApp() {
  $("#landing").classList.add("hide");
  $("#app").style.display = "grid";
  setTimeout(() => $("#landing").classList.add("hidden"), 600);
  if (!store.stats) bootstrap();
}

// Check for direct bypass hash
if (location.hash === "#app") {
  enterApp();
}

async function loadCore() {
  const [stats, analytics, incidents, audit] = await Promise.all([
    api("/stats"), 
    api("/analytics").catch(() => null), 
    api("/incidents"), 
    api("/audit-log?limit=300").catch(() => [])
  ]);
  
  store.stats = stats; 
  store.analytics = analytics; 
  store.incidents = incidents; 
  store.audit = audit;
  
  buildReviewMap();
  
  $("#h-api").className = "dot ok"; 
  $("#h-db").className = "dot ok";
  $("#h-updated").textContent = "Updated " + new Date().toLocaleTimeString();
}

function buildReviewMap() {
  const m = {};
  // Newest first; lock in first status change per incident
  for (const r of store.audit) {
    if (r.actor.startsWith("reviewer") && r.incident_id != null && !(r.incident_id in m)) {
      m[r.incident_id] = r.action;
    }
  }
  store._reviewByIncident = m;
  
  // Calculate critical alert count for sidebar badge
  const criticalCount = store.incidents.filter(i => {
    const isReviewed = i.incident_id in m;
    return i.severity.toLowerCase() === "critical" && !isReviewed;
  }).length;
  
  sidebar.updateBadge(criticalCount);
}

async function bootstrap() {
  try { 
    await loadCore(); 
  } catch (e) { 
    $("#h-api").className = "dot bad"; 
    $("#h-db").className = "dot bad"; 
    $("#h-updated").textContent = "API Unreachable"; 
    return; 
  }
  
  sidebar.render();
  populateFilters();
  bindIncidentSort();
  renderIncidentsTable();
  
  // Render Overview Dashboard
  kpis.render(store.stats, store.analytics);
  dashboard.render(store.analytics);
  
  // Initialize events
  auditConsole.bindEvents(decide);
  startAuditPolling();

  // Download Logs button — reads store.audit + current filters at click time
  const dlBtn = document.getElementById('downloadLogsBtn');
  if (dlBtn) {
    dlBtn.addEventListener('click', () => {
      const q = (document.getElementById('logSearch')?.value || '').toLowerCase();
      const actorFilter = document.getElementById('logActor')?.value || '';

      const rows = (store.audit || []).filter(r => {
        const matchActor = !actorFilter || r.actor.startsWith(actorFilter);
        const matchSearch = !q || JSON.stringify(r).toLowerCase().includes(q);
        return matchActor && matchSearch;
      });

      const csvEsc = v => {
        const s = String(v ?? '');
        return (s.includes(',') || s.includes('"') || s.includes('\n'))
          ? `"${s.replace(/"/g, '""')}"`
          : s;
      };

      const lines = [
        ['Timestamp', 'Action', 'Actor', 'Incident', 'Details'].join(','),
        ...rows.map(r => [
          csvEsc(r.ts),
          csvEsc(r.action),
          csvEsc(r.actor),
          csvEsc(r.incident_id != null ? `#${r.incident_id}` : ''),
          csvEsc(r.details || '')
        ].join(','))
      ];

      const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const pad = n => String(n).padStart(2, '0');
      const now = new Date();
      const stamp = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;

      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_logs_${stamp}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  // Prefetch details in background
  fetchIncidentsDetailsInBackground();
}

async function fetchIncidentsDetailsInBackground() {
  const ids = store.incidents.map(i => i.incident_id);
  const chunkSize = 5;
  for (let i = 0; i < ids.length; i += chunkSize) {
    const chunk = ids.slice(i, i + chunkSize);
    await Promise.all(chunk.map(async id => {
      try {
        const detail = await getDetail(id);
        const hyps = detail.hypotheses || [];
        const top = hyps.find(h => h.grounded);
        if (top) {
          store._hypByIncident[id] = {
            root_cause: top.root_cause_node,
            confidence: top.confidence || (top.confidence_pct / 100)
          };
        } else {
          store._hypByIncident[id] = {
            root_cause: "none",
            confidence: null
          };
        }
      } catch (err) {
        console.error(`Failed to prefetch detail for incident ${id}:`, err);
      }
    }));
    renderIncidentsTable();
  }
}

// Global Refresh Action
$("#refreshBtn")?.addEventListener("click", async () => {
  const btn = $("#refreshBtn");
  btn.disabled = true;
  btn.textContent = "↻ Syncing...";
  try {
    await loadCore(); 
    renderIncidentsTable(); 
    kpis.render(store.stats, store.analytics);
    dashboard.render(store.analytics);
    if (store.selected) {
      // Re-query current detail
      store.detail = await getDetail(store.selected);
      renderDetailPanels();
    }
    auditConsole.render(store.audit, store.selected, decide);
  } catch (err) {}
  btn.disabled = false;
  btn.textContent = "↻ Refresh";
});

// ---------- Selection & Pivot ----------
async function selectIncident(id) {
  store.selected = id; 
  store.engine = null;
  
  // Highlight table selection
  document.querySelectorAll("#incBody tr").forEach(tr => {
    tr.classList.toggle("sel", +tr.dataset.id === id);
  });
  
  try {
    store.detail = await getDetail(store.selected);
    
    // Immediately calculate hypotheses mapping from pre-existing hypotheses
    const hyps = store.detail.hypotheses || [];
    const top = hyps.find(h => h.grounded);
    if (top) {
      store._hypByIncident[id] = {
        root_cause: top.root_cause_node,
        confidence: top.confidence || (top.confidence_pct / 100)
      };
    } else {
      store._hypByIncident[id] = {
        root_cause: "none",
        confidence: null
      };
    }
    renderIncidentsTable();

    renderDetailPanels();
    
    // Auto-update active visualization states if open
    if ($("#v-graph").classList.contains("active")) kg.render(store.selected, store.detail);
    if ($("#v-topology").classList.contains("active")) topology.render(store.selected, store.detail);
    if ($("#v-timeline").classList.contains("active")) timeline.render(store.selected, store.detail);
    if ($("#v-shap").classList.contains("active")) explainability.render(store.detail.incident);
    
    switchView("evidence");
  } catch (e) {
    console.error("Failed to select incident:", e);
  }
}

// Render sub panels
function renderDetailPanels() {
  const d = store.detail;
  if (!d) return;

  const inc = d.incident;
  
  // Summary Details Card
  $("#evSub").textContent = `Incident #${inc.incident_id} Target: ${inc.node_id} (${inc.attack_cat})`;
  $("#incSummary").innerHTML = `
    <h3>Incident Ingestion Summary</h3>
    <div class="grid three" style="gap:15px; font-family:var(--font);">
      <div><span style="color:var(--muted); font-size:11.5px;">Incident ID</span><br><b style="font-family:var(--mono);">#${inc.incident_id}</b></div>
      <div><span style="color:var(--muted); font-size:11.5px;">Threat Category</span><br><b>${esc(inc.attack_cat)}</b></div>
      <div><span style="color:var(--muted); font-size:11.5px;">Severity Rank</span><br><span class="pill sev-${esc(inc.severity)}">${esc(inc.severity)}</span></div>
      <div><span style="color:var(--muted); font-size:11.5px;">Target Node</span><br><b style="font-family:var(--mono);">${esc(inc.node_id)}</b></div>
      <div><span style="color:var(--muted); font-size:11.5px;">Cluster Volume</span><br><b>${fmt(inc.flow_count)} Scored Flows</b></div>
      <div><span style="color:var(--muted); font-size:11.5px;">Ingestion Window</span><br><span style="font-family:var(--mono); font-size:12.5px;">${esc(inc.start_ts.slice(11))} &rarr; ${esc(inc.end_ts.slice(11))}</span></div>
    </div>
  `;

  // Render components
  evidenceMatrix.render(d.evidence_by_bucket);
  rootCausePanel.render(d, store.engine);
  relatedIncidents.render(store.incidents, inc);

  // Trigger automatic SHAP profiling for the details card (Dataset Analysis PRIMARY)
  const shapHost = document.getElementById("incShapResult");
  if (shapHost && inc) {
    const template = TELEMETRY_TEMPLATES[inc.attack_cat] || TELEMETRY_TEMPLATES.DoS;
    shapHost.innerHTML = `<div class="skel chart-skel"></div>`;
    
    api("/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...template,
        dinpkt: 0.0,
        ct_src_dport_ltm: 4,
        ct_dst_sport_ltm: 2
      })
    }).then(response => {
      if (store.selected === inc.incident_id && document.getElementById("incShapResult")) {
        shapChart(document.getElementById("incShapResult"), response.shap, response.attack_cat_pred, response.confidence);
      }
    }).catch(err => {
      console.error("SHAP details card failed:", err);
      if (store.selected === inc.incident_id && document.getElementById("incShapResult")) {
        document.getElementById("incShapResult").innerHTML = `<div class="reject-reason">Telemetry explainability evaluation failed: ${err.message}</div>`;
      }
    });
  }
}

// Event delegation for pivots and row clicks
document.addEventListener("click", e => {
  const row = e.target.closest("#incBody tr[data-id]"); 
  if (row) return selectIncident(+row.dataset.id);
  
  const goto = e.target.closest("[data-goto]"); 
  if (goto) return selectIncident(+goto.dataset.goto);
});

// Filter triggers
["search", "fSeverity", "fAttack"].forEach(id => {
  const el = $("#" + id);
  if (el) el.addEventListener("input", renderIncidentsTable);
});

// ---------- Hypotheses Engine ----------
$("#runBtn")?.addEventListener("click", runEngine);
async function runEngine() {
  if (!store.selected) return alert("Select an incident from the Incident list first.");
  
  const btn = $("#runBtn"); 
  btn.disabled = true; 
  btn.innerHTML = '<span class="spinner"></span> Running reasoning trace...';
  
  try {
    const r = await api(`/incidents/${store.selected}/hypotheses/regenerate`, { method: "POST" });
    store.engine = r;
    
    // Set grounding cache
    const topGrounded = r.ranked_hypotheses.find(h => h.grounded);
    store._hypByIncident[store.selected] = {
      root_cause: topGrounded ? topGrounded.root_cause_node : "none",
      confidence: topGrounded ? topGrounded.confidence : null
    };

    // Update Hypotheses view list
    $("#engineMeta").textContent = `#${r.incident_id} &bull; Vector: ${r.attack_cat} &bull; proposed: ${r.ranked_hypotheses.length} hypotheses`;
    
    $("#hypList").innerHTML = r.ranked_hypotheses.map((h, i) => {
      const pct = Math.round((h.confidence || 0) * 100);
      const steps = i === 0 && r.remediation?.length 
        ? `<div style="margin-top:12px"><b>Remediation Protocol Playbook</b><ul class="steps">${r.remediation.map(s => `<li>${esc(s.step)}<div class="why">${esc(s.rationale)}</div></li>`).join("")}</ul></div>` 
        : "";
      const reason = !h.grounded && h.rejected_reason 
        ? `<div class="reject-reason">✗ Ground-check rejection: ${esc(h.rejected_reason)}</div>` 
        : "";

      return `
        <div class="hyp ${h.grounded ? '' : 'rejected'}" id="hyp-card-${i}">
          <div class="head">
            <span class="rank">${i + 1}</span>
            <b>${esc(h.root_cause_node)}</b>
            <span class="badge ${h.grounded ? 'grounded' : 'rejected'}">${h.grounded ? 'grounded' : 'rejected'}</span>
            <span class="conf">${pct}%</span>
          </div>
          <div class="confbar"><i style="width:0%" data-width="${pct}"></i></div>
          <div style="font-size:13px; line-height:1.45; color:var(--txt);">${esc(h.claim)}</div>
          <div class="hint" style="margin-top:8px;">Cites Evidence: ${(h.cited_evidence_ids || []).map(esc).join(", ") || "—"}</div>
          ${reason}
          <button class="toggle" id="hyp-toggle-${i}">▾ view details</button>
          <div class="expand">
            <div style="font-family:var(--mono); font-size:11.5px; background:rgba(0,0,0,0.2); padding:8px; border-radius:6px;">
              Tier weights: ${esc(JSON.stringify(h.evidence_tier_breakdown || {}))}
            </div>
            ${steps}
          </div>
        </div>
      `;
    }).join("") || '<div class="empty">No hypotheses returned for this cluster.</div>';

    // Trigger gauge bars transition
    requestAnimationFrame(() => {
      document.querySelectorAll("#hypList .confbar i").forEach(bar => {
        bar.style.width = bar.dataset.width + "%";
      });
    });

    // Bind hyp detail collapses
    document.querySelectorAll("#hypList .toggle").forEach(b => {
      b.onclick = () => {
        const hyp = b.closest(".hyp");
        hyp.classList.toggle("open");
        b.textContent = hyp.classList.contains("open") ? "▴ hide details" : "▾ view details";
      };
    });

    $("#traceCard").classList.remove("hidden");
    $("#traceList").innerHTML = (r.trace_log || []).map(log => `<li>${esc(log)}</li>`).join("");

    await refreshAuditLogs();
    
    // Sync incident summaries back to tables
    renderDetailPanels();
    renderIncidentsTable();
  } catch (err) {
    $("#hypList").innerHTML = `<div class="reject-reason">Hypothesis Engine failed: ${err.message}</div>`;
  }
  
  btn.disabled = false; 
  btn.innerHTML = "▶️ Run reasoning engine";
}

// ---------- Review Action Decisions ----------
async function decide(dec) {
  if (!store.selected) return alert("Select an incident to review first.");
  try {
    await api(`/incidents/${store.selected}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        decision: dec, 
        reviewer: "L2 Analyst", 
        note: `Analyst verification: ${dec} completed via command panel.` 
      })
    });
    
    await refreshAuditLogs();
    renderIncidentsTable();
    
    // Trigger immediate updates on details panel
    if (store.detail) {
      store.detail = await getDetail(store.selected);
      renderDetailPanels();
    }
  } catch (err) {
    alert("Decision write failed: " + err.message);
  }
}

// ---------- Log Polling ----------
async function refreshAuditLogs() {
  store.audit = await api("/audit-log?limit=300").catch(() => store.audit);
  buildReviewMap();
  auditConsole.render(store.audit, store.selected, decide);
}

let auditTimer = null;
function startAuditPolling() {
  if (auditTimer) return;
  // Dynamic SIEM Poller: runs when Audit is open and tab is focused
  auditTimer = poll(async () => {
    if (!$("#v-audit").classList.contains("active")) return;
    const before = store.audit[0]?.audit_id;
    
    store.audit = await api("/audit-log?limit=300");
    if (store.audit[0]?.audit_id !== before) {
      buildReviewMap();
      auditConsole.render(store.audit, store.selected, decide);
      renderIncidentsTable();
    }
  }, 1000); // 1.0s interval
}

["logSearch", "logActor"].forEach(id => {
  const el = $("#" + id);
  if (el) {
    el.addEventListener("input", () => {
      auditConsole.render(store.audit, store.selected, decide);
    });
  }
});

// ---------- Routing Views ----------
function switchView(name) {
  document.querySelectorAll(".view").forEach(v => {
    v.classList.toggle("active", v.id === "v-" + name);
  });
  
  sidebar.setActive(name);

  // Lazy render triggers
  if (name === "overview") {
    kpis.render(store.stats, store.analytics);
    dashboard.render(store.analytics);
  }
  if (name === "graph") {
    kg.render(store.selected, store.detail);
  }
  if (name === "topology") {
    topology.render(store.selected, store.detail);
  }
  if (name === "timeline") {
    timeline.render(store.selected, store.detail);
  }
  if (name === "shap") {
    explainability.render(store.detail?.incident);
  }
  if (name === "audit") {
    auditConsole.render(store.audit, store.selected, decide);
  }
  if (name === "hypotheses" && store.selected && !$("#hypList").children.length) {
    runEngine();
  }

  $(".main").scrollTop = 0;
}

// ---------- Incident Table Helper ----------
function renderIncidentsTable() {
  const q = ($("#search")?.value || "").toLowerCase();
  const fs = $("#fSeverity")?.value || "";
  const fa = $("#fAttack")?.value || "";
  
  let rows = store.incidents.filter(i => 
    (!fs || i.severity === fs) && 
    (!fa || i.attack_cat === fa) &&
    (!q || `${i.node_id} ${i.attack_cat} ${i.severity} ${i.incident_id}`.toLowerCase().includes(q))
  );

  // Sort logic
  const { k, dir } = sort;
  rows.sort((a, b) => {
    const x = a[k] ?? "";
    const y = b[k] ?? "";
    return (x > y ? 1 : x < y ? -1 : 0) * dir;
  });

  const rev = store._reviewByIncident || {};
  const hyp = store._hypByIncident || {};

  $("#incBody").innerHTML = rows.map(i => {
    const statusVal = rev[i.incident_id];
    const statusHtml = statusVal === "reviewer_approved" 
      ? '<span class="tag-ok">Approved</span>'
      : statusVal === "reviewer_rejected" 
        ? '<span class="tag-warn">Rejected</span>' 
        : '<span class="tag-none">Pending Review</span>';

    const h = hyp[i.incident_id];
    
    let rc = `<span style="color:var(--muted); font-size:11px;">Syncing...</span>`;
    let conf = `<span style="color:var(--muted); font-size:11px;">Syncing...</span>`;
    
    if (h) {
      if (h.root_cause === "none" || !h.root_cause) {
        rc = `<span style="color:var(--muted)">Not Generated</span>`;
        conf = `<span style="color:var(--muted)">Not Generated</span>`;
      } else {
        rc = esc(h.root_cause);
        conf = h.confidence != null ? Math.round(h.confidence * 100) + "%" : `<span style="color:var(--muted)">Not Generated</span>`;
      }
    }

    return `
      <tr data-id="${i.incident_id}" class="${store.selected === i.incident_id ? 'sel' : ''}">
        <td>#${i.incident_id}</td>
        <td><b>${esc(i.attack_cat)}</b></td>
        <td><span class="pill sev-${esc(i.severity)}">${esc(i.severity)}</span></td>
        <td style="font-family:var(--mono);">${esc(i.node_id)}</td>
        <td style="font-family:var(--mono);">${fmt(i.flow_count)}</td>
        <td style="font-family:var(--mono); color:var(--cyan);">${rc}</td>
        <td style="font-family:var(--mono);">${conf}</td>
        <td>${statusHtml}</td>
        <td style="font-family:var(--mono); color:var(--muted);">${esc(i.start_ts)}</td>
      </tr>
    `;
  }).join("") || '<tr><td colspan="9" class="empty">No incidents found in workspace.</td></tr>';
}

function bindIncidentSort() {
  document.querySelectorAll("#incTable th").forEach(th => {
    th.onclick = () => {
      const k = th.dataset.k;
      sort = { k, dir: sort.k === k ? -sort.dir : 1 };
      renderIncidentsTable();
    };
  });
}

function populateFilters() {
  const sevs = [...new Set(store.incidents.map(i => i.severity))];
  const atks = [...new Set(store.incidents.map(i => i.attack_cat))].sort();
  
  $("#fSeverity").innerHTML = '<option value="">All Severities</option>' + sevs.map(s => `<option>${esc(s)}</option>`).join("");
  $("#fAttack").innerHTML = '<option value="">All Attack Types</option>' + atks.map(a => `<option>${esc(a)}</option>`).join("");
}

// hamb toggle navigation collapse
$("#hamb").addEventListener("click", () => {
  $("#app").classList.toggle("collapsed");
  pulse($("#hamb"));
});

// Resize visual elements dynamically
window.addEventListener("resize", () => {
  if ($("#v-topology").classList.contains("active")) topology.render(store.selected, store.detail);
  else if ($("#v-graph").classList.contains("active")) kg.render(store.selected, store.detail);
  else if ($("#v-overview").classList.contains("active")) dashboard.render(store.analytics);
});