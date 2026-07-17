// // AuditConsole Component: SIEM-style audit trails with search, filters, and review actions.
// const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// export class AuditConsole {
//   constructor(containerId, formControls) {
//     this.container = document.querySelector(containerId);
//     this.searchEl = document.querySelector(formControls.search);
//     this.actorEl = document.querySelector(formControls.actor);
//     this.approveBtn = document.querySelector(formControls.approve);
//     this.rejectBtn = document.querySelector(formControls.reject);
//     this.prevAuditIds = new Set();
//   }

//   render(auditLogs, selectedId, onDecision) {
//     if (!this.container) return;

//     if (auditLogs.length === 0) {
//       this.container.innerHTML = `<div class="empty">No audit trails recorded in system.</div>`;
//       return;
//     }

//     const q = (this.searchEl?.value || "").toLowerCase();
//     const actorFilter = this.actorEl?.value || "";

//     // Filter logs
//     const filtered = auditLogs.filter(r => {
//       const matchActor = !actorFilter || r.actor.startsWith(actorFilter);
//       const matchSearch = !q || JSON.stringify(r).toLowerCase().includes(q);
//       return matchActor && matchSearch;
//     });

//     const currentIds = new Set(auditLogs.map(r => r.audit_id));

//     if (filtered.length === 0) {
//       this.container.innerHTML = `<div class="empty">No audit logs matching search queries.</div>`;
//       return;
//     }

//     this.container.innerHTML = filtered.map(r => {
//       const isReviewer = r.actor.startsWith("reviewer");
//       const actorBadge = isReviewer ? "reviewer" : "system";
      
//       // Determine action colors
//       let actionClass = "tag-none";
//       if (r.action.includes("approved")) actionClass = "tag-ok";
//       if (r.action.includes("rejected")) actionClass = "tag-warn";
//       if (r.action.includes("score")) actionClass = "tag-none";

//       const isNew = !this.prevAuditIds.has(r.audit_id) && this.prevAuditIds.size > 0;
//       const selectHighlight = selectedId && r.incident_id === selectedId ? "border-left: 2px solid var(--cyan);" : "";

//       return `
//         <div class="row ${isNew ? 'new' : ''}" style="${selectHighlight}" id="audit-row-${r.audit_id}">
//           <span class="ts">${esc(r.ts)}</span>
//           <span class="lvl ${actorBadge}">${actorBadge}</span>
//           <span class="msg">
//             <b class="${actionClass}">${esc(r.action)}</b> &bull; actor: ${esc(r.actor)} 
//             ${r.incident_id != null ? `&bull; incident: <span style="color:var(--cyan)">#${r.incident_id}</span>` : ''}
//             <div class="det">Details: ${esc(r.details || "(no details)")}\naudit_id=${r.audit_id}</div>
//           </span>
//         </div>
//       `;
//     }).join('');

//     // Bind click logs to expand
//     this.container.querySelectorAll('.row').forEach(row => {
//       row.addEventListener('click', () => {
//         row.classList.toggle('open');
//       });
//     });

//     this.prevAuditIds = currentIds;

//     // Enable/disable buttons based on selection
//     if (this.approveBtn && this.rejectBtn) {
//       const active = !!selectedId;
//       this.approveBtn.disabled = !active;
//       this.rejectBtn.disabled = !active;
      
//       this.approveBtn.title = active ? `Approve Incident #${selectedId}` : "Select an incident first";
//       this.rejectBtn.title = active ? `Reject Incident #${selectedId}` : "Select an incident first";
//     }
//   }

//   bindEvents(onDecision) {
//     if (this.approveBtn) {
//       this.approveBtn.replaceWith(this.approveBtn.cloneNode(true));
//       this.approveBtn = document.querySelector("#v-audit [data-decide='approve']");
//       this.approveBtn.addEventListener('click', () => onDecision('approve'));
//     }

//     if (this.rejectBtn) {
//       this.rejectBtn.replaceWith(this.rejectBtn.cloneNode(true));
//       this.rejectBtn = document.querySelector("#v-audit [data-decide='reject']");
//       this.rejectBtn.addEventListener('click', () => onDecision('reject'));
//     }
//   }
// }


// AuditConsole Component: SIEM-style audit trails with search, filters, and review actions.
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export class AuditConsole {
  constructor(containerId, formControls) {
    this.container = document.querySelector(containerId);
    this.searchEl = document.querySelector(formControls.search);
    this.actorEl = document.querySelector(formControls.actor);
    this.approveBtn = document.querySelector(formControls.approve);
    this.rejectBtn = document.querySelector(formControls.reject);
    this.prevAuditIds = new Set();
  }

  render(auditLogs, selectedId, onDecision) {
    if (!this.container) return;

    if (auditLogs.length === 0) {
      this.container.innerHTML = `<div class="empty">No audit trails recorded in system.</div>`;
      return;
    }

    const q = (this.searchEl?.value || "").toLowerCase();
    const actorFilter = this.actorEl?.value || "";

    // Filter logs
    const filtered = auditLogs.filter(r => {
      const matchActor = !actorFilter || r.actor.startsWith(actorFilter);
      const matchSearch = !q || JSON.stringify(r).toLowerCase().includes(q);
      return matchActor && matchSearch;
    });

    const currentIds = new Set(auditLogs.map(r => r.audit_id));

    if (filtered.length === 0) {
      this.container.innerHTML = `<div class="empty">No audit logs matching search queries.</div>`;
      return;
    }

    this.container.innerHTML = filtered.map(r => {
      const isReviewer = r.actor.startsWith("reviewer");
      const actorBadge = isReviewer ? "reviewer" : "system";
      
      // Determine action colors
      let actionClass = "tag-none";
      if (r.action.includes("approved")) actionClass = "tag-ok";
      if (r.action.includes("rejected")) actionClass = "tag-warn";
      if (r.action.includes("score")) actionClass = "tag-none";

      const isNew = !this.prevAuditIds.has(r.audit_id) && this.prevAuditIds.size > 0;
      const selectHighlight = selectedId && r.incident_id === selectedId ? "border-left: 2px solid var(--cyan);" : "";

      return `
        <div class="row ${isNew ? 'new' : ''}" style="${selectHighlight}" id="audit-row-${r.audit_id}">
          <span class="ts">${esc(r.ts)}</span>
          <span class="lvl ${actorBadge}">${actorBadge}</span>
          <span class="msg">
            <b class="${actionClass}">${esc(r.action)}</b> &bull; actor: ${esc(r.actor)} 
            ${r.incident_id != null ? `&bull; incident: <span style="color:var(--cyan)">#${r.incident_id}</span>` : ''}
            <div class="det">Details: ${esc(r.details || "(no details)")}\naudit_id=${r.audit_id}</div>
          </span>
        </div>
      `;
    }).join('');

    // Bind click logs to expand
    this.container.querySelectorAll('.row').forEach(row => {
      row.addEventListener('click', () => {
        row.classList.toggle('open');
      });
    });

    this.prevAuditIds = currentIds;

    // Enable/disable buttons based on selection
    if (this.approveBtn && this.rejectBtn) {
      const active = !!selectedId;
      this.approveBtn.disabled = !active;
      this.rejectBtn.disabled = !active;
      
      this.approveBtn.title = active ? `Approve Incident #${selectedId}` : "Select an incident first";
      this.rejectBtn.title = active ? `Reject Incident #${selectedId}` : "Select an incident first";
    }
  }

  bindEvents(onDecision) {
    if (this.approveBtn) {
      this.approveBtn.replaceWith(this.approveBtn.cloneNode(true));
      this.approveBtn = document.querySelector("#v-audit [data-decide='approve']");
      this.approveBtn.addEventListener('click', () => onDecision('approve'));
    }

    if (this.rejectBtn) {
      this.rejectBtn.replaceWith(this.rejectBtn.cloneNode(true));
      this.rejectBtn = document.querySelector("#v-audit [data-decide='reject']");
      this.rejectBtn.addEventListener('click', () => onDecision('reject'));
    }
  }
}