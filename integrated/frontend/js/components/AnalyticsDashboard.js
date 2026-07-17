// AnalyticsDashboard Component: Renders 22 high-fidelity D3 charts from backend responses.
import { hbar, bar, donut, stacked, area, COLORS } from "../charts.js";

const CHART_SPECS = [
  { id: "incidents_by_severity",        t: "Incident Severity Profile",   fn: donut,   c: COLORS.SEV, hint: "Breakdown of incidents by severity levels" },
  { id: "evidence_bucket_distribution", t: "Telemetry Evidence Split",     fn: donut,   c: COLORS.EVI, hint: "Bucketed evidence groups in the correlation engine" },
  { id: "incidents_by_attack",          t: "Incidents by Attack Class",   fn: hbar,    hint: "Number of incidents classified under UNSW categories" },
  { id: "predicted_attack_distribution",t: "ML Prediction Volume",        fn: bar,     hint: "Total anomaly flow predictions by class" },
  { id: "confidence_histogram",         t: "Prediction Confidence Profile", fn: bar,   hint: "Flows partitioned by XGBoost confidence score" },
  { id: "hypothesis_confidence_histogram", t: "Hypothesis Grounding Score", fn: bar,   hint: "Derived agent hypotheses by confidence score" },
  { id: "shap_top_feature_frequency",   t: "Top SHAP Driving Features",   fn: hbar,    hint: "Most frequent features leading to positive predictions" },
  { id: "root_cause_frequency",         t: "Root Cause Node Occurrences", fn: hbar,    hint: "Grounded root causes asserted by agent" },
  { id: "evidence_type_distribution",   t: "Evidence Type Frequency",     fn: hbar,    hint: "Occurrences of specific telemetry evidence rules" },
  { id: "proto_distribution",           t: "Telemetry Protocols",         fn: hbar,    hint: "Network protocols in anomalous flows" },
  { id: "service_distribution",         t: "Target Services",             fn: hbar,    hint: "Target port services identified in telemetry" },
  { id: "state_distribution",           t: "TCP Connection State",         fn: bar,     hint: "Observed TCP states during anomalous sessions" },
  { id: "binary_label_distribution",    t: "Binary Labels (Ground Truth)", fn: donut,   c: COLORS.EVI, hint: "Label counts matching training data label field" },
  { id: "split_distribution",           t: "Model Train / Test Split",    fn: donut,   hint: "Data records split for machine learning" },
  { id: "incidents_over_time",          t: "Incident Timeline Trend",     fn: area,    wide: true,   hint: "Correlated incidents aggregated by ingestion hour" },
  { id: "top_affected_hosts",           t: "Top Affected Targets",        fn: hbar,    hint: "Host nodes experiencing anomaly incidents" },
  { id: "config_changes_by_severity",   t: "Drift Severity",              fn: donut,   c: COLORS.SEV, hint: "Synthetic config changes by severity level" },
  { id: "config_changes_by_host",       t: "Drift Frequency by Node",     fn: hbar,    hint: "Configuration changes recorded per host" },
  { id: "audit_action_distribution",    t: "Console Actions",             fn: hbar,    hint: "Audit trails logged by actions" },
  { id: "reviewer_actions",             t: "Analyst Decision Ratio",      fn: donut,   c: { reviewer_approved: "#10b981", reviewer_rejected: "#ef4444" }, hint: "Decisions completed on incidents" }
];

export class AnalyticsDashboard {
  constructor(containerId) {
    this.container = document.querySelector(containerId);
  }

  render(analytics) {
    if (!this.container) return;

    if (!analytics) {
      this.container.innerHTML = `<div class="empty">No analytics telemetry available from the backend.</div>`;
      return;
    }

    // Build the grid items
    let html = ``;
    for (const sp of CHART_SPECS) {
      const wideClass = sp.wide ? 'wide' : '';
      html += `
        <div class="card ${wideClass}" id="card-${sp.id}">
          <h3>
            ${sp.t}
            ${sp.hint ? `<span class="hint">${sp.hint}</span>` : ''}
          </h3>
          <div class="chart-host" id="chart-host-${sp.id}">
            <div class="skel chart-skel"></div>
          </div>
        </div>
      `;
    }

    // Add special stacked host severity breakdown card
    html += `
      <div class="card wide" id="card-host_severity_breakdown">
        <h3>Host Severity Breakdown <span class="hint">Incident severity profile clustered per node</span></h3>
        <div class="chart-host" id="chart-host-host_severity_breakdown">
          <div class="skel chart-skel"></div>
        </div>
      </div>
    `;

    // Add special sbytes by attack class card
    html += `
      <div class="card" id="card-avg_bytes_by_attack">
        <h3>Average Source Bytes by Attack <span class="hint">Mean sbytes payload by attack category</span></h3>
        <div class="chart-host" id="chart-host-avg_bytes_by_attack">
          <div class="skel chart-skel"></div>
        </div>
      </div>
    `;

    this.container.innerHTML = html;

    // Render D3 charts with micro-timeout to let DOM paint first
    setTimeout(() => {
      // 1. Render standard specs
      for (const sp of CHART_SPECS) {
        const host = document.getElementById(`chart-host-${sp.id}`);
        const card = document.getElementById(`card-${sp.id}`);
        if (!host) continue;

        let data = analytics[sp.id];
        if (!data || Object.keys(data).length === 0) {
          if (card) card.classList.add('hidden');
          continue;
        }

        try {
          sp.fn(host, data, sp.c);
        } catch (err) {
          console.error(`Error rendering chart ${sp.id}:`, err);
          if (card) card.classList.add('hidden');
        }
      }

      // 2. Render Stacked Bar: host_severity_breakdown
      const stackedHost = document.getElementById('chart-host-host_severity_breakdown');
      const stackedCard = document.getElementById('card-host_severity_breakdown');
      if (stackedHost && analytics.host_severity_breakdown && analytics.host_severity_breakdown.length > 0) {
        try {
          stackedHost.innerHTML = '';
          stacked(stackedHost, analytics.host_severity_breakdown, 'host', 'severity', 'count', COLORS.SEV);
        } catch (err) {
          console.error('Error rendering host severity breakdown:', err);
          if (stackedCard) stackedCard.classList.add('hidden');
        }
      } else {
        if (stackedCard) stackedCard.classList.add('hidden');
      }

      // 3. Render Avg Bytes by Attack
      const bytesHost = document.getElementById('chart-host-avg_bytes_by_attack');
      const bytesCard = document.getElementById('card-avg_bytes_by_attack');
      if (bytesHost && analytics.avg_bytes_by_attack && Object.keys(analytics.avg_bytes_by_attack).length > 0) {
        try {
          bytesHost.innerHTML = '';
          // Convert complex {attack: {sbytes: X, dbytes: Y}} structure to simple {attack: X}
          const simplifiedBytes = {};
          Object.entries(analytics.avg_bytes_by_attack).forEach(([attack, payload]) => {
            simplifiedBytes[attack] = payload.sbytes;
          });
          hbar(bytesHost, simplifiedBytes);
        } catch (err) {
          console.error('Error rendering average bytes by attack:', err);
          if (bytesCard) bytesCard.classList.add('hidden');
        }
      } else {
        if (bytesCard) bytesCard.classList.add('hidden');
      }

    }, 30);
  }
}
