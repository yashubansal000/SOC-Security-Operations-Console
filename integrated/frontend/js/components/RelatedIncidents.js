// RelatedIncidents Component: Lists correlated alerts sharing host targets or attack classes.
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export class RelatedIncidents {
  constructor(containerId) {
    this.container = document.querySelector(containerId);
  }

  render(incidentsList, activeIncident) {
    if (!this.container) return;

    if (!activeIncident) {
      this.container.innerHTML = `<div class="empty">—</div>`;
      return;
    }

    // Filter related incidents (sharing host or attack category, excluding itself)
    const related = incidentsList.filter(i => 
      i.incident_id !== activeIncident.incident_id &&
      (i.node_id === activeIncident.node_id || i.attack_cat === activeIncident.attack_cat)
    ).slice(0, 5);

    if (related.length === 0) {
      this.container.innerHTML = `<div class="empty">No related alerts found on target nodes.</div>`;
      return;
    }

    this.container.innerHTML = related.map(i => {
      // Calculate realistic similarity score based on overlaps
      const matchHost = i.node_id === activeIncident.node_id;
      const matchAttack = i.attack_cat === activeIncident.attack_cat;
      
      let simScore = 50;
      let matchReason = "Common attack vector";
      
      if (matchHost && matchAttack) {
        simScore = 95;
        matchReason = "Identical host & attack vector";
      } else if (matchHost) {
        simScore = 80;
        matchReason = "Co-located on same target host";
      }

      return `
        <div class="ev-item" style="cursor:pointer; display:flex; justify-content:space-between; align-items:center;" data-goto="${i.incident_id}">
          <div style="flex:1;">
            <div class="type" style="display:flex; align-items:center; gap:6px;">
              <span>${esc(i.attack_cat)}</span>
              <span class="pill sev-${esc(i.severity)}" style="font-size:8px; padding:1px 5px;">${esc(i.severity)}</span>
            </div>
            <div style="font-size:12.5px; color:var(--txt); margin-top:2px;">
              #${i.incident_id} on <b>${esc(i.node_id)}</b>
            </div>
            <div style="font-size:10px; color:var(--muted); margin-top:4px;">
              Reason: ${matchReason}
            </div>
          </div>
          <div style="text-align:right; font-family:var(--mono);">
            <div style="font-size:14px; font-weight:800; color:var(--cyan);">${simScore}%</div>
            <div style="font-size:8px; color:var(--muted); text-transform:uppercase;">match</div>
          </div>
        </div>
      `;
    }).join('');
  }
}
