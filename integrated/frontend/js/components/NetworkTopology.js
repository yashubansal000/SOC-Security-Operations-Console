// NetworkTopology Component: Full 20-node enterprise network D3 topology.
import { forceGraph } from "../graph.js";

const NODE_METADATA = {
  "firewall-01":      { label: "Firewall-01",     tier: "firewall",      icon: "🛡️", desc: "Core Network Firewall" },
  "dns-01":           { label: "DNS-Primary",     tier: "infra",         icon: "⚙️", desc: "Primary Internal DNS Resolver" },
  "dns-02":           { label: "DNS-Secondary",   tier: "infra",         icon: "⚙️", desc: "Secondary Internal DNS Resolver" },
  "lb-01":            { label: "Load-Balancer",   tier: "load_balancer", icon: "🔀", desc: "HTTP Load Balancer & Switch" },
  "web-srv-01":       { label: "Web-Server-01",   tier: "web",           icon: "🌐", desc: "DMZ Web Ingestion Node" },
  "web-srv-02":       { label: "Web-Server-02",   tier: "web",           icon: "🌐", desc: "DMZ Web Ingestion Node" },
  "app-srv-01":       { label: "App-Server-01",   tier: "app",           icon: "💻", desc: "Core Business Application Logic" },
  "app-srv-02":       { label: "App-Server-02",   tier: "app",           icon: "💻", desc: "Core Business Application Logic" },
  "db-primary":       { label: "DB-Primary",      tier: "db",            icon: "🗄️", desc: "Active Transaction SQL Master" },
  "db-replica":       { label: "DB-Replica",      tier: "db",            icon: "🗄️", desc: "Read-Only Replica SQL Node" },
  "cache-01":         { label: "Redis-Cache",     tier: "cache",         icon: "⚡", desc: "Memory Cache Layer" },
  "auth-01":          { label: "Auth-Directory",  tier: "auth",          icon: "🔑", desc: "LDAP / Active Directory Server" },
  "ssh-bastion-01":   { label: "SSH-Bastion",     tier: "remote_access", icon: "🔑", desc: "Secure Remote Shell Gateway" },
  "mail-01":          { label: "SMTP-Mail",       tier: "mail",          icon: "✉️", desc: "Enterprise Exchange Mail Transfer" },
  "ftp-01":           { label: "FTP-Storage",     tier: "file_transfer", icon: "📁", desc: "Public FTP Backup Storage" },
  "dhcp-01":          { label: "DHCP-Alloc",      tier: "infra",         icon: "⚙️", desc: "IP Address Assignment Service" },
  "monitoring-01":    { label: "Zabbix-Mon",      tier: "monitoring",    icon: "📊", desc: "NMS Health Check Node" },
  "logging-01":       { label: "ELK-Log",         tier: "logging",       icon: "📊", desc: "Centralized Audit Logger" },
  "irc-gw-01":        { label: "Chat-IRC-GW",     tier: "messaging",     icon: "💬", desc: "Internal IRC Messaging Server" },
  "external-api":     { label: "Ext-Cloud-API",   tier: "external",      icon: "☁️", desc: "Partner cloud third-party API" }
};

const STATIC_EDGES = [
  { source: "app-srv-01", target: "cache-01" },
  { source: "app-srv-01", target: "db-primary" },
  { source: "app-srv-01", target: "external-api" },
  { source: "app-srv-02", target: "cache-01" },
  { source: "app-srv-02", target: "db-primary" },
  { source: "db-primary", target: "db-replica" },
  { source: "firewall-01", target: "auth-01" },
  { source: "firewall-01", target: "dhcp-01" },
  { source: "firewall-01", target: "dns-01" },
  { source: "firewall-01", target: "dns-02" },
  { source: "firewall-01", target: "ftp-01" },
  { source: "firewall-01", target: "irc-gw-01" },
  { source: "firewall-01", target: "lb-01" },
  { source: "firewall-01", target: "mail-01" },
  { source: "firewall-01", target: "monitoring-01" },
  { source: "firewall-01", target: "ssh-bastion-01" },
  { source: "lb-01", target: "web-srv-01" },
  { source: "lb-01", target: "web-srv-02" },
  { source: "monitoring-01", target: "logging-01" },
  { source: "web-srv-01", target: "app-srv-01" },
  { source: "web-srv-01", target: "app-srv-02" },
  { source: "web-srv-02", target: "app-srv-01" },
  { source: "web-srv-02", target: "app-srv-02" }
];

export class NetworkTopology {
  constructor(containerId, detailId) {
    this.container = document.querySelector(containerId);
    this.detailPanel = document.querySelector(detailId);
  }

  render(selectedId, detail) {
    if (!this.container) return;

    // Build legend
    const legendHtml = `
      <span><span class="dot" style="background:#ef4444"></span>Target Target (Incident Root)</span>
      <span><span class="dot" style="background:#eab308"></span>Upstream Dependency (Root Cause)</span>
      <span><span class="dot" style="background:#3b82f6"></span>Downstream Blast Radius</span>
      <span><span class="dot" style="background:#1e293b; border: 1px solid rgba(255,255,255,0.15)"></span>Normal Node</span>
    `;

    this.container.innerHTML = `
      <div class="legend" id="topoLegend">${legendHtml}</div>
      <div id="topoSvgHost" style="width:100%; height:440px; position:relative;"></div>
    `;

    const host = document.getElementById("topoSvgHost");
    if (!host) return;

    // Parse active path details if an incident is selected
    const activeNode = detail?.incident?.node_id;
    const upCandidates = new Set((detail?.impact_path?.upstream_candidates || []).map(x => x[0]));
    const downImpact = new Set((detail?.impact_path?.downstream_impact || []).map(x => x[0]));

    // Construct the nodes list
    const nodes = Object.entries(NODE_METADATA).map(([id, meta]) => {
      let color = "#1e293b"; // Normal
      let r = 11;
      let status = "Normal operational status";

      if (activeNode && id === activeNode) {
        color = "#ef4444"; // Red - Root affected target
        r = 16;
        status = "CRITICAL TARGET: Primary anomaly detection source";
      } else if (upCandidates.has(id)) {
        color = "#eab308"; // Amber - potential root cause candidate
        r = 13;
        const hops = (detail?.impact_path?.upstream_candidates || []).find(x => x[0] === id)?.[1] || 1;
        status = `SUSPECT HOST: Root Cause Candidate (${hops} hops upstream)`;
      } else if (downImpact.has(id)) {
        color = "#3b82f6"; // Soft Blue - downstream blast radius
        r = 12;
        const hops = (detail?.impact_path?.downstream_impact || []).find(x => x[0] === id)?.[1] || 1;
        status = `IMPACTED TARGET: Downstream Blast Radius (${hops} hops downstream)`;
      }

      return {
        id,
        label: `${meta.icon} ${meta.label}`,
        type: meta.tier,
        meta: `${meta.desc} &bull; ${status}`,
        color,
        r
      };
    });

    // Deep copy static edges
    const links = STATIC_EDGES.map(e => ({
      source: e.source,
      target: e.target,
      isActive: activeNode && (
        (e.source === activeNode || e.target === activeNode) ||
        (upCandidates.has(e.source) && upCandidates.has(e.target)) ||
        (downImpact.has(e.source) && downImpact.has(e.target))
      )
    }));

    // Trigger D3 force directed graph drawing
    try {
      const sim = forceGraph(host, nodes, links, {
        height: 420,
        onSelect: (node) => {
          if (this.detailPanel) {
            const meta = NODE_METADATA[node.id];
            this.detailPanel.innerHTML = `
              <div style="border-left: 3px solid ${node.color}; padding-left: 10px;">
                <h4 style="text-transform: uppercase; font-size:12px; color:${node.color}; margin-bottom:4px;">
                  Tier: ${meta.tier.toUpperCase()}
                </h4>
                <p style="font-weight: 700; font-size: 14px; margin-bottom: 4px;">
                  ${meta.icon} ${meta.label} (${node.id})
                </p>
                <p style="color: var(--txt-secondary); font-size:12.5px;">
                  ${node.meta}
                </p>
              </div>
            `;
            if (window.anime) {
              window.anime({
                targets: this.detailPanel,
                opacity: [0.5, 1],
                translateX: [8, 0],
                duration: 250,
                easing: 'easeOutQuad'
              });
            }
          }
        }
      });
    } catch (err) {
      console.error("Error drawing full Network Topology map:", err);
      host.innerHTML = `<div class="empty">D3 Network Topology render error. Check console.</div>`;
    }
  }
}
