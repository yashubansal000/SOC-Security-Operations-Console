// ExplainabilityPanel Component: Renders SHAP profile visualizations and interactive What-if simulators using D3.js.
import { api } from "../api.js";
import { shapChart } from "../charts.js";

// Pre-defined telemetry templates by attack category to make simulation seamless
export const TELEMETRY_TEMPLATES = {
  Normal: {
    proto: "tcp", service: "-", state: "FIN", sbytes: 120, dbytes: 80,
    rate: 1.5, sload: 800, dload: 500, dur: 0.8, sinpkt: 0.1, dinpkt: 0.1,
    ct_src_dport_ltm: 1, ct_dst_sport_ltm: 1
  },
  DoS: {
    proto: "tcp", service: "-", state: "INT", sbytes: 1800, dbytes: 0,
    rate: 450.0, sload: 250000.0, dload: 0.0, dur: 0.05, sinpkt: 0.002, dinpkt: 0.0,
    ct_src_dport_ltm: 24, ct_dst_sport_ltm: 18
  },
  Exploits: {
    proto: "tcp", service: "http", state: "REQ", sbytes: 6200, dbytes: 4800,
    rate: 15.0, sload: 12000.0, dload: 8500.0, dur: 0.4, sinpkt: 0.015, dinpkt: 0.012,
    ct_src_dport_ltm: 4, ct_dst_sport_ltm: 2
  },
  Reconnaissance: {
    proto: "tcp", service: "-", state: "CON", sbytes: 44, dbytes: 44,
    rate: 180.0, sload: 6400.0, dload: 6400.0, dur: 0.01, sinpkt: 0.003, dinpkt: 0.003,
    ct_src_dport_ltm: 32, ct_dst_sport_ltm: 32
  },
  Generic: {
    proto: "udp", service: "-", state: "INT", sbytes: 146, dbytes: 0,
    rate: 1200.0, sload: 85000.0, dload: 0.0, dur: 0.001, sinpkt: 0.001, dinpkt: 0.0,
    ct_src_dport_ltm: 12, ct_dst_sport_ltm: 6
  },
  Fuzzers: {
    proto: "udp", service: "-", state: "INT", sbytes: 1520, dbytes: 0,
    rate: 850.0, sload: 620000.0, dload: 0.0, dur: 0.005, sinpkt: 0.0005, dinpkt: 0.0,
    ct_src_dport_ltm: 16, ct_dst_sport_ltm: 8
  },
  Backdoor: {
    proto: "tcp", service: "-", state: "FIN", sbytes: 250, dbytes: 200,
    rate: 2.0, sload: 1500.0, dload: 1200.0, dur: 1.2, sinpkt: 0.05, dinpkt: 0.04,
    ct_src_dport_ltm: 2, ct_dst_sport_ltm: 1
  },
  Analysis: {
    proto: "tcp", service: "-", state: "CON", sbytes: 350, dbytes: 280,
    rate: 12.0, sload: 3500.0, dload: 2800.0, dur: 0.5, sinpkt: 0.02, dinpkt: 0.02,
    ct_src_dport_ltm: 3, ct_dst_sport_ltm: 2
  },
  Shellcode: {
    proto: "tcp", service: "-", state: "REQ", sbytes: 1200, dbytes: 900,
    rate: 8.0, sload: 8000.0, dload: 6000.0, dur: 0.3, sinpkt: 0.03, dinpkt: 0.03,
    ct_src_dport_ltm: 4, ct_dst_sport_ltm: 2
  },
  Worms: {
    proto: "tcp", service: "-", state: "CON", sbytes: 4500, dbytes: 0,
    rate: 50.0, sload: 45000.0, dload: 0.0, dur: 0.8, sinpkt: 0.01, dinpkt: 0.0,
    ct_src_dport_ltm: 8, ct_dst_sport_ltm: 4
  }
};

export class ExplainabilityPanel {
  constructor(containerId) {
    this.container = document.querySelector(containerId);
    this.activeTab = "dataset"; // "dataset" | "simulator"
  }

  render(selectedIncident) {
    if (!this.container) return;

    const attackCat = selectedIncident ? selectedIncident.attack_cat : "DoS";
    const template = TELEMETRY_TEMPLATES[attackCat] || TELEMETRY_TEMPLATES.DoS;

    this.container.innerHTML = `
      <!-- Sub Nav Tab Bar -->
      <div style="display:flex; gap:8px; margin-bottom:20px; border-bottom:1px solid var(--line); padding-bottom:10px;">
        <button class="nav-tab ${this.activeTab === 'dataset' ? 'active' : ''}" id="btnTabShapDataset" style="padding: 6px 16px; font-size:12.5px; border-radius:6px; cursor:pointer;">
          Dataset SHAP Profile (Active Incident)
        </button>
        <button class="nav-tab ${this.activeTab === 'simulator' ? 'active' : ''}" id="btnTabShapSimulator" style="padding: 6px 16px; font-size:12.5px; border-radius:6px; cursor:pointer;">
          What-if Simulator (Manual Form)
        </button>
      </div>

      <div id="shapContentArea">
        <!-- Rendered based on active tab -->
      </div>
    `;

    this.bindTabEvents(selectedIncident);

    if (this.activeTab === "dataset") {
      this.renderDatasetTab(selectedIncident, template);
    } else {
      this.renderSimulatorTab(template);
    }
  }

  bindTabEvents(selectedIncident) {
    const tabDataset = document.getElementById("btnTabShapDataset");
    const tabSimulator = document.getElementById("btnTabShapSimulator");

    if (tabDataset && tabSimulator) {
      tabDataset.addEventListener("click", () => {
        this.activeTab = "dataset";
        this.render(selectedIncident);
      });
      tabSimulator.addEventListener("click", () => {
        this.activeTab = "simulator";
        this.render(selectedIncident);
      });
    }
  }

  // --- TAB 1: DATASET SHAP PROFILE ---
  async renderDatasetTab(selectedIncident, template) {
    const area = document.getElementById("shapContentArea");
    if (!area) return;

    if (!selectedIncident) {
      area.innerHTML = `<div class="empty">Please select an active incident from the Incident Desk first to view its SHAP explanation profile.</div>`;
      return;
    }

    area.innerHTML = `
      <div class="grid two">
        <!-- Telemetry profile card -->
        <div class="card" style="margin-bottom:0">
          <h3>Telemetry Profile Summary</h3>
          <p style="color:var(--txt-secondary); line-height:1.5; margin-bottom:15px;">
            The model evaluated the following representative feature parameters mapped to this incident's attack profile (<b>${selectedIncident.attack_cat}</b>):
          </p>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; font-family:var(--mono); font-size:12px; background:rgba(0,0,0,0.15); padding:14px; border-radius:8px; border:1px solid var(--line);">
            <div>Protocol: <b style="color:var(--cyan)">${template.proto.toUpperCase()}</b></div>
            <div>Service: <b style="color:var(--cyan)">${template.service}</b></div>
            <div>TCP State: <b style="color:var(--cyan)">${template.state}</b></div>
            <div>Source Bytes: <b style="color:var(--cyan)">${template.sbytes.toLocaleString()}</b></div>
            <div>Dest Bytes: <b style="color:var(--cyan)">${template.dbytes.toLocaleString()}</b></div>
            <div>Packet Rate: <b style="color:var(--cyan)">${template.rate.toFixed(1)}/s</b></div>
            <div>Source Load: <b style="color:var(--cyan)">${template.sload.toLocaleString()}</b></div>
            <div>Dest Load: <b style="color:var(--cyan)">${template.dload.toLocaleString()}</b></div>
          </div>
        </div>

        <!-- D3 SHAP chart card -->
        <div class="card" style="margin-bottom:0">
          <h3>ML Model Explainability <span class="hint">Live D3 horizontal SHAP forces</span></h3>
          <div id="datasetShapChartHost" style="min-height:220px; display:grid; place-items:center;">
            <div class="skel chart-skel"></div>
          </div>
        </div>
      </div>
    `;

    // Background call to score typical values using the real model scoring endpoint
    try {
      const response = await api("/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...template,
          dinpkt: 0.0,
          ct_src_dport_ltm: 4,
          ct_dst_sport_ltm: 2
        })
      });

      const host = document.getElementById("datasetShapChartHost");
      if (host) {
        shapChart(host, response.shap, response.attack_cat_pred, response.confidence);
      }
    } catch (err) {
      console.error("SHAP background scoring failed:", err);
      const host = document.getElementById("datasetShapChartHost");
      if (host) host.innerHTML = `<div class="reject-reason">Error querying ML classifier: ${err.message}</div>`;
    }
  }

  // --- TAB 2: WHAT-IF SIMULATOR ---
  renderSimulatorTab(template) {
    const area = document.getElementById("shapContentArea");
    if (!area) return;

    area.innerHTML = `
      <div class="grid two">
        <!-- Telemetry Form -->
        <div class="card" style="margin-bottom:0">
          <h3>Simulation Telemetry Form <span class="hint">Adjust parameters to score custom flows</span></h3>
          <form id="shapForm" style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
            <div>
              <label style="font-size:11px;color:var(--muted)">Protocol</label><br>
              <select name="proto" style="width:100%">
                <option value="tcp" ${template.proto === 'tcp' ? 'selected' : ''}>TCP</option>
                <option value="udp" ${template.proto === 'udp' ? 'selected' : ''}>UDP</option>
                <option value="ospf" ${template.proto === 'ospf' ? 'selected' : ''}>OSPF</option>
              </select>
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Service</label><br>
              <select name="service" style="width:100%">
                <option value="-" ${template.service === '-' ? 'selected' : ''}>None (-)</option>
                <option value="http" ${template.service === 'http' ? 'selected' : ''}>HTTP</option>
                <option value="ftp" ${template.service === 'ftp' ? 'selected' : ''}>FTP</option>
                <option value="dns" ${template.service === 'dns' ? 'selected' : ''}>DNS</option>
                <option value="smtp" ${template.service === 'smtp' ? 'selected' : ''}>SMTP</option>
              </select>
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">TCP State</label><br>
              <input type="text" name="state" value="${template.state}" style="width:100%">
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Source Bytes (sbytes)</label><br>
              <input type="number" name="sbytes" value="${template.sbytes}" style="width:100%">
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Dest Bytes (dbytes)</label><br>
              <input type="number" name="dbytes" value="${template.dbytes}" style="width:100%">
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Packet Rate</label><br>
              <input type="number" step="any" name="rate" value="${template.rate}" style="width:100%">
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Source Load (sload)</label><br>
              <input type="number" step="any" name="sload" value="${template.sload}" style="width:100%">
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Dest Load (dload)</label><br>
              <input type="number" step="any" name="dload" value="${template.dload}" style="width:100%">
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Duration (s)</label><br>
              <input type="number" step="any" name="dur" value="${template.dur}" style="width:100%">
            </div>
            <div>
              <label style="font-size:11px;color:var(--muted)">Source IP Interpacket Time</label><br>
              <input type="number" step="any" name="sinpkt" value="${template.sinpkt}" style="width:100%">
            </div>
            <div style="grid-column: 1 / -1; margin-top:10px;">
              <button class="btn" type="submit" id="shapScoreBtn" style="width:100%; justify-content:center;">
                Evaluate Prediction &amp; SHAP
              </button>
            </div>
          </form>
        </div>

        <!-- D3 SHAP Explanation Results -->
        <div class="card" style="margin-bottom:0">
          <h3>Model Prediction &amp; Feature Contributions</h3>
          <div id="shapResult" class="empty">
            Submit the telemetry form on the left to score the hypothetical flow.
          </div>
        </div>
      </div>
    `;

    this.bindSimulatorEvents();
  }

  bindSimulatorEvents() {
    const form = document.getElementById("shapForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const scoreBtn = document.getElementById("shapScoreBtn");
      const resultDiv = document.getElementById("shapResult");
      
      scoreBtn.disabled = true;
      scoreBtn.innerHTML = `<span class="spinner"></span> Running SHAP Explainer...`;
      resultDiv.innerHTML = `<div class="skel chart-skel"></div>`;

      // Extract form data
      const fd = new FormData(form);
      const payload = {
        proto: fd.get("proto"),
        service: fd.get("service"),
        state: fd.get("state"),
        sbytes: parseInt(fd.get("sbytes")) || 0,
        dbytes: parseInt(fd.get("dbytes")) || 0,
        rate: parseFloat(fd.get("rate")) || 0.0,
        sload: parseFloat(fd.get("sload")) || 0.0,
        dload: parseFloat(fd.get("dload")) || 0.0,
        dur: parseFloat(fd.get("dur")) || 0.0,
        sinpkt: parseFloat(fd.get("sinpkt")) || 0.0,
        dinpkt: 0.0,
        ct_src_dport_ltm: 4,
        ct_dst_sport_ltm: 2
      };

      try {
        const response = await api("/score", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        // Clear host and call D3 SHAP chart renderer
        resultDiv.innerHTML = `
          <div style="margin-bottom:12px; font-weight:700; font-size:13.5px; display:flex; justify-content:space-between; align-items:center;">
            <span>Classified Prediction: <b class="tag-warn">${response.attack_cat_pred}</b></span>
            <span>Decision: <b class="${response.label_pred === 1 ? 'tag-warn' : 'tag-ok'}">${response.label_pred === 1 ? 'ATTACK' : 'NORMAL'}</b></span>
          </div>
          <div class="divider" style="margin-bottom:14px;"></div>
          <div id="simD3ShapHost" style="min-height:220px; display:grid; place-items:center;"></div>
        `;
        
        const host = document.getElementById("simD3ShapHost");
        if (host) {
          shapChart(host, response.shap, response.attack_cat_pred, response.confidence);
        }
      } catch (err) {
        console.error("SHAP Scoring failed:", err);
        resultDiv.innerHTML = `<div class="reject-reason">Error scoring telemetry: ${err.message}</div>`;
      } finally {
        scoreBtn.disabled = false;
        scoreBtn.innerHTML = "Evaluate Prediction &amp; SHAP";
      }
    });
  }
}
