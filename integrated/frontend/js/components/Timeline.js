// Timeline Component: Renders pipeline progress and interactive chronological event lists.

const PIPELINE_STAGES = [
  { step: "01", name: "Flow Ingestion", desc: "Telemetry generator Ingests logs" },
  { step: "02", name: "ML Classification", desc: "XGBoost scoring + SHAP values" },
  { step: "03", name: "Evidence Correlation", desc: "Clusters anomalies into bucketed facts" },
  { step: "04", name: "Grounded Reasoner", desc: "LangGraph proposes root causes" },
  { step: "05", name: "Ground-Check", desc: "Deterministic validation check", special: true },
  { step: "06", name: "Mitigation", desc: "Ranked actions proposed to analyst" }
];

export class Timeline {
  constructor(pipelineId, eventTlId) {
    this.pipelineContainer = document.querySelector(pipelineId);
    this.eventTlContainer = document.querySelector(eventTlId);
  }

  render(selectedId, detail) {
    this.renderPipeline();

    if (!selectedId) {
      if (this.eventTlContainer) {
        this.eventTlContainer.innerHTML = `<div class="empty">Please select an incident to view its detailed timeline.</div>`;
      }
      return;
    }

    if (!detail) {
      if (this.eventTlContainer) {
        this.eventTlContainer.innerHTML = `<div class="empty"><span class="spinner"></span> Loading incident timeline...</div>`;
      }
      return;
    }

    this.renderEvents(detail.timeline || []);
  }

  renderPipeline() {
    if (!this.pipelineContainer) return;

    this.pipelineContainer.innerHTML = PIPELINE_STAGES.map(s => `
      <div class="stage ${s.special ? 'det' : ''}">
        <div class="n">STEP ${s.step}</div>
        <div class="t">${s.name}</div>
        <div class="d">${s.desc}</div>
      </div>
    `).join('');
  }

  renderEvents(events) {
    if (!this.eventTlContainer) return;

    if (events.length === 0) {
      this.eventTlContainer.innerHTML = `<div class="empty">No timeline events recorded for this incident.</div>`;
      return;
    }

    // Sort events by timestamp
    const sorted = [...events].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    this.eventTlContainer.innerHTML = sorted.map((e, idx) => {
      // Pick style classes based on event source/type
      let styleClass = 'log';
      let symbol = '📝';
      
      const type = (e.source_type || '').toLowerCase();
      const details = e.details || '';

      if (type.includes('flow') || type.includes('anomaly') || details.includes('alert')) {
        styleClass = 'alert';
        symbol = '🚨';
      } else if (type.includes('config')) {
        styleClass = 'config_change';
        symbol = '⚙️';
      } else if (type.includes('evidence') || details.includes('confirmed')) {
        styleClass = 'evidence';
        symbol = '🔍';
      } else if (type.includes('hypothesis') || type.includes('agent')) {
        styleClass = 'remediation';
        symbol = '🧠';
      } else if (details.includes('approved') || details.includes('rejected')) {
        styleClass = 'action';
        symbol = '🛡️';
      }

      return `
        <li class="${styleClass}" id="tl-event-${idx}">
          <span class="t">${e.timestamp} &bull; <b style="text-transform:uppercase">${e.source_type || 'system'}</b> &bull; Host: ${e.node_id || 'Global'}</span>
          <div class="title-row">${symbol} ${details.slice(0, 100)}${details.length > 100 ? '...' : ''}</div>
          <div class="more">${details}</div>
        </li>
      `;
    }).join('');

    // Bind collapse toggle events
    this.eventTlContainer.querySelectorAll('li').forEach(li => {
      li.addEventListener('click', () => {
        const isOpen = li.classList.contains('open');
        // Close others
        this.eventTlContainer.querySelectorAll('li').forEach(l => l.classList.remove('open'));
        if (!isOpen) {
          li.classList.add('open');
          if (window.anime) {
            window.anime({
              targets: li.querySelector('.more'),
              opacity: [0, 1],
              translateY: [-5, 0],
              duration: 200,
              easing: 'easeOutQuad'
            });
          }
        }
      });
    });
  }
}
