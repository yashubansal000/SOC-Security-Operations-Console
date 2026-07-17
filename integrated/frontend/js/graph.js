// D3 force-directed graph — shared by Knowledge Graph and Network Topology.
// Interactive: zoom, pan, drag, click-to-highlight-neighbors. Real nodes only.
const d3 = window.d3;

// nodes: [{id,label,type,meta,color}], links: [{source,target}]
export function forceGraph(el, nodes, links, { onSelect, height = 460 } = {}) {
  el.innerHTML = "";
  if (!nodes.length) { el.innerHTML = '<div class="empty">No graph data for this incident.</div>'; return; }
  const W = el.clientWidth || 800, H = height;
  const svg = d3.select(el).append("svg").attr("class", "gsvg").attr("viewBox", `0 0 ${W} ${H}`);
  const root = svg.append("g");
  svg.call(d3.zoom().scaleExtent([0.3, 4]).on("zoom", e => root.attr("transform", e.transform)));

  const link = root.append("g").selectAll("line").data(links).join("line").attr("class", "gedge")
    .attr("stroke-dasharray", "4 3");
  link.append("animate").attr("attributeName", "stroke-dashoffset").attr("from", 14).attr("to", 0)
    .attr("dur", "1s").attr("repeatCount", "indefinite");

  const node = root.append("g").selectAll("g").data(nodes).join("g").attr("class", "gnode")
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) sim.alphaTarget(.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

  node.append("circle").attr("r", d => d.r || 11).attr("fill", d => d.color)
    .attr("stroke", "#0b111d").attr("stroke-width", 1.5);
  node.append("text").attr("text-anchor", "middle").attr("dy", d => -(d.r || 11) - 5).text(d => d.label);

  const neighbors = new Map(nodes.map(n => [n.id, new Set()]));
  links.forEach(l => {
    const s = l.source.id ?? l.source, t = l.target.id ?? l.target;
    neighbors.get(s)?.add(t); neighbors.get(t)?.add(s);
  });
  node.on("click", (e, d) => {
    const near = neighbors.get(d.id) || new Set();
    node.select("circle").attr("opacity", n => (n.id === d.id || near.has(n.id)) ? 1 : .2);
    link.attr("opacity", l => {
      const s = l.source.id ?? l.source, t = l.target.id ?? l.target;
      return (s === d.id || t === d.id) ? 1 : .1;
    });
    onSelect && onSelect(d);
  });
  svg.on("click", e => { if (e.target === svg.node()) { node.select("circle").attr("opacity", 1); link.attr("opacity", 1); } });

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(90))
    .force("charge", d3.forceManyBody().strength(-320))
    .force("center", d3.forceCenter(W / 2, H / 2))
    .force("collide", d3.forceCollide().radius(d => (d.r || 11) + 14))
    .on("tick", () => {
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y).attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });
  return sim;
}
