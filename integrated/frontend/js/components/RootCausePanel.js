// RootCausePanel Component: Displays primary root cause node, confidence gauges, and remediations.
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export class RootCausePanel {
  constructor(containerId) {
    this.container = document.querySelector(containerId);
  }

  render(detail, engine) {
    if (!this.container) return;

    if (!detail) {
      this.container.innerHTML = `<div class="empty">Please select an incident first.</div>`;
      return;
    }

    // Determine the active hypothesis
    const eng = engine && engine.incident_id === detail.incident.incident_id ? engine : null;
    const hypothesesList = (eng && eng.ranked_hypotheses) || detail.hypotheses || [];
    const topGrounded = hypothesesList.find(h => h.grounded);
    const remediationSteps = (eng && eng.remediation) || [];

    if (!topGrounded) {
      this.container.innerHTML = `
        <div class="empty">
          Run the <b>Hypotheses Engine</b> to synthesize and verify root causes for this incident.
        </div>
      `;
      return;
    }

    const confidence = Math.round((topGrounded.confidence || topGrounded.confidence_pct / 100 || 0) * 100);
    const path = [topGrounded.root_cause_node, detail.incident.node_id];
    
    // Draw Gauge and Details
    this.container.innerHTML = `
      <div style="display:grid; grid-template-columns: 80px 1fr; gap:20px; align-items:center; margin-bottom:16px;">
        <!-- Confidence Radial/Circular Gauge -->
        <div style="position:relative; width:80px; height:80px; display:grid; place-items:center;">
          <svg width="80" height="80" viewBox="0 0 100 100" style="transform: rotate(-90deg);">
            <circle cx="50" cy="50" r="40" stroke="rgba(255,255,255,0.05)" stroke-width="8" fill="none" />
            <circle cx="50" cy="50" r="40" stroke="var(--cyan)" stroke-width="8" fill="none"
              stroke-dasharray="251.2" stroke-dashoffset="${251.2 - (251.2 * confidence) / 100}"
              stroke-linecap="round" style="transition: stroke-dashoffset 1s ease-out;" />
          </svg>
          <div style="position:absolute; font-family:var(--mono); font-weight:800; font-size:16px; color:var(--txt);">
            ${confidence}%
          </div>
        </div>

        <div>
          <h4 style="font-size:16px; font-weight:800; color:var(--cyan); margin-bottom:4px;">
            ${esc(topGrounded.root_cause_node)}
          </h4>
          <p style="font-size:13px; line-height:1.45; color:var(--txt);">
            ${esc(topGrounded.claim)}
          </p>
        </div>
      </div>

      <div class="divider" style="margin: 16px 0;"></div>

      <div style="margin-bottom:16px;">
        <h5 style="font-size:11px; text-transform:uppercase; color:var(--muted); letter-spacing:1px; margin-bottom:6px;">
          Affected Asset Blast Path
        </h5>
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-family:var(--mono); font-size:11.5px;">
          <span style="background:rgba(234,179,8,0.15); border:1px solid var(--warning); padding:2px 8px; border-radius:4px; color:var(--warning)">
            ${esc(topGrounded.root_cause_node)} (Source)
          </span>
          <span style="color:var(--muted)">&rarr;</span>
          <span style="background:rgba(239,68,68,0.15); border:1px solid var(--critical); padding:2px 8px; border-radius:4px; color:var(--critical)">
            ${esc(detail.incident.node_id)} (Anomaly Target)
          </span>
          ${detail.impact_path?.downstream_impact?.length > 0 ? `
            <span style="color:var(--muted)">&rarr;</span>
            <span style="background:rgba(59,130,246,0.15); border:1px solid var(--accent); padding:2px 8px; border-radius:4px; color:var(--accent-light)">
              ${detail.impact_path.downstream_impact.length} Downstream Nodes
            </span>
          ` : ''}
        </div>
      </div>

      <div>
        <h5 style="font-size:11px; text-transform:uppercase; color:var(--muted); letter-spacing:1px; margin-bottom:8px;">
          Mitigation Protocol Steps
        </h5>
        ${remediationSteps.length > 0 ? `
          <ul class="steps" style="margin-top:4px;">
            ${remediationSteps.map((s, idx) => `
              <li style="font-size:12.5px;">
                <b>Step ${idx + 1}: ${esc(s.step)}</b>
                <div class="why">${esc(s.rationale)}</div>
              </li>
            `).join('')}
          </ul>
        ` : `
          <div style="font-size:12px; color:var(--muted); font-style:italic;">
            Mitigation steps not loaded. Run Hypotheses Engine to extract remediation playbook.
          </div>
        `}
      </div>
    `;
  }
}
