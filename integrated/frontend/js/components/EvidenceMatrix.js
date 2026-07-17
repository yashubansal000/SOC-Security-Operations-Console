// EvidenceMatrix Component: Groups and renders telemetry evidence indicators.
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export class EvidenceMatrix {
  constructor(containerId) {
    this.container = document.querySelector(containerId);
  }

  render(evidenceByBucket) {
    if (!this.container) return;

    if (!evidenceByBucket) {
      this.container.innerHTML = `<div class="empty">No evidence matrix compiled. Select an incident.</div>`;
      return;
    }

    const b = evidenceByBucket;
    const total = (b.confirmed?.length || 0) + (b.correlated?.length || 0) + (b.missing?.length || 0);

    if (total === 0) {
      this.container.innerHTML = `<div class="empty" style="grid-column: 1/-1">This incident contains no evidence telemetry logs.</div>`;
      return;
    }

    const renderColumn = (key, title, colorClass, icon) => {
      const list = b[key] || [];
      
      let itemsHtml = ``;
      if (list.length === 0) {
        itemsHtml = `
          <div class="ev-empty">
            ${key === 'missing' ? '✓ No coverage gaps flagged.' : `No ${title.toLowerCase()} evidence correlated.`}
          </div>
        `;
      } else {
        list.forEach((e, idx) => {
          const confidence = e.confidence_weight != null ? Math.round(e.confidence_weight * 100) + "%" : "—";
          itemsHtml += `
            <div class="ev-item" id="ev-card-${key}-${idx}">
              <div class="type" style="display:flex; justify-content:space-between;">
                <span>${esc(e.evidence_type)}</span>
                <span>Conf: ${confidence}</span>
              </div>
              <div class="desc">${esc(e.description)}</div>
              <div style="font-size:10px; color:var(--muted); margin-top:6px; display:flex; justify-content:space-between;">
                <span>Node: <b>${esc(e.node_id || 'Global')}</b></span>
                ${e.ref_id ? `<span>Ref ID: #${e.ref_id}</span>` : ''}
              </div>
            </div>
          `;
        });
      }

      return `
        <div class="ev-col ${key}">
          <h4>
            <span>${icon}</span>
            <span>${title}</span>
            <span class="count">${list.length}</span>
          </h4>
          ${itemsHtml}
        </div>
      `;
    };

    this.container.innerHTML = 
      renderColumn("confirmed", "Confirmed Evidence", "confirmed", "🟢") +
      renderColumn("correlated", "Correlated Evidence", "correlated", "🟡") +
      renderColumn("missing", "Explicit Missing Gaps", "missing", "🔴");
  }
}
