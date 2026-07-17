// Reusable D3 chart components. d3 is global (vendored UMD).
// Every chart takes real {label: value} data; renders nothing + hides host on empty.
const d3 = window.d3;
const CSS = getComputedStyle(document.documentElement);
const C = n => CSS.getPropertyValue(n).trim();
export const PALETTE = ["#3b82f6", "#ef4444", "#f97316", "#10b981", "#8b5cf6", "#06b6d4", "#a855f7", "#ec4899", "#84cc16", "#f59e0b"];
const SEV = { critical: "#ef4444", high: "#f97316", medium: "#3b82f6", low: "#64748b",
              CRITICAL: "#ef4444", HIGH: "#f97316", MEDIUM: "#3b82f6", LOW: "#64748b" };
const EVI = { confirmed: "#10b981", correlated: "#f59e0b", missing: "#ef4444",
              Confirmed: "#10b981", Correlated: "#f59e0b", Missing: "#ef4444",
              Attack: "#ef4444", Normal: "#10b981" };

let tipEl;
function tip(){ if(!tipEl){ tipEl=document.createElement("div"); tipEl.className="d3-tip"; document.body.appendChild(tipEl);} return tipEl; }
function showTip(html,e){ const t=tip(); t.innerHTML=html; t.style.opacity=1; t.style.left=(e.clientX+12)+"px"; t.style.top=(e.clientY-10)+"px"; }
function hideTip(){ if(tipEl) tipEl.style.opacity=0; }
const colorFor = (k,i) => SEV[k] || EVI[k] || PALETTE[i % PALETTE.length];

// Hide the whole card if there is no real data (per "hide, don't fabricate").
export function guard(el, obj){
  const entries = Array.isArray(obj) ? obj : Object.entries(obj||{}).filter(([,v])=>v>0);
  if (!entries.length){ const card = el.closest(".card"); if (card) card.classList.add("hidden"); return null; }
  const card = el.closest(".card"); if (card) card.classList.remove("hidden");
  el.innerHTML=""; return entries;
}

// -------- horizontal bar --------
export function hbar(el, obj, colors){
  const e = guard(el, obj); if(!e) return;
  const data = e.map(([label,value],i)=>({label,value,c:(colors&&colors[label])||colorFor(label,i)}));
  const W=el.clientWidth||360, rowH=26, H=data.length*rowH+10, m={l:120,r:46};
  const x=d3.scaleLinear().domain([0,d3.max(data,d=>d.value)]).range([0,W-m.l-m.r]);
  const svg=d3.select(el).append("svg").attr("width","100%").attr("viewBox",`0 0 ${W} ${H}`);
  const g=svg.selectAll("g").data(data).join("g").attr("transform",(d,i)=>`translate(0,${i*rowH})`);
  g.append("text").attr("x",m.l-8).attr("y",rowH/2+4).attr("text-anchor","end").attr("fill",C("--muted")).attr("font-size",11)
    .text(d=>d.label.length>16?d.label.slice(0,15)+"…":d.label);
  g.append("rect").attr("x",m.l).attr("y",4).attr("height",rowH-10).attr("rx",5).attr("fill",d=>d.c)
    .attr("width",0).transition().duration(700).attr("width",d=>Math.max(2,x(d.value)));
  g.append("text").attr("x",d=>m.l+x(d.value)+6).attr("y",rowH/2+4).attr("fill",C("--txt")).attr("font-size",11)
    .text(d=>d.value.toLocaleString());
  g.on("mousemove",(ev,d)=>showTip(`<b>${d.label}</b>: ${d.value.toLocaleString()}`,ev)).on("mouseleave",hideTip);
}

// -------- vertical bar --------
export function bar(el, obj, colors){
  const e = guard(el, obj); if(!e) return;
  const data=e.map(([label,value],i)=>({label,value,c:(colors&&colors[label])||colorFor(label,i)}));
  const W=el.clientWidth||360, H=210, m={t:10,b:46,l:36,r:8};
  const x=d3.scaleBand().domain(data.map(d=>d.label)).range([m.l,W-m.r]).padding(.25);
  const y=d3.scaleLinear().domain([0,d3.max(data,d=>d.value)]).nice().range([H-m.b,m.t]);
  const svg=d3.select(el).append("svg").attr("width","100%").attr("viewBox",`0 0 ${W} ${H}`);
  svg.append("g").attr("transform",`translate(0,${H-m.b})`).call(d3.axisBottom(x).tickSize(0))
    .call(g=>g.select(".domain").remove()).selectAll("text").attr("fill",C("--muted")).attr("font-size",10)
    .attr("transform","rotate(-30)").attr("text-anchor","end");
  svg.append("g").attr("transform",`translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W-m.l-m.r)))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("line").attr("stroke",C("--line")).attr("opacity",.5))
    .selectAll("text").attr("fill",C("--muted")).attr("font-size",10);
  svg.selectAll(".b").data(data).join("rect").attr("x",d=>x(d.label)).attr("width",x.bandwidth()).attr("rx",4)
    .attr("fill",d=>d.c).attr("y",H-m.b).attr("height",0)
    .on("mousemove",(ev,d)=>showTip(`<b>${d.label}</b>: ${d.value.toLocaleString()}`,ev)).on("mouseleave",hideTip)
    .transition().duration(700).attr("y",d=>y(d.value)).attr("height",d=>H-m.b-y(d.value));
}

// -------- donut --------
export function donut(el, obj, colors){
  const e = guard(el, obj); if(!e) return;
  const data=e.map(([label,value])=>({label,value})); const tot=d3.sum(data,d=>d.value);
  const W=el.clientWidth||360, H=210, R=Math.min(W,H)/2-6, r=R*0.62;
  const svg=d3.select(el).append("svg").attr("width","100%").attr("viewBox",`0 0 ${W} ${H}`);
  const g=svg.append("g").attr("transform",`translate(${W/2},${H/2})`);
  const arc=d3.arc().innerRadius(r).outerRadius(R).cornerRadius(2);
  const pie=d3.pie().sort(null).value(d=>d.value);
  g.selectAll("path").data(pie(data)).join("path").attr("fill",(d,i)=>(colors&&colors[d.data.label])||colorFor(d.data.label,i))
    .attr("d",arc).each(function(d){this._c=d;})
    .on("mousemove",(ev,d)=>showTip(`<b>${d.data.label}</b>: ${d.data.value.toLocaleString()} (${(d.data.value/tot*100).toFixed(1)}%)`,ev)).on("mouseleave",hideTip)
    .attr("opacity",0).transition().duration(600).attr("opacity",1);
  g.append("text").attr("text-anchor","middle").attr("dy",-2).attr("fill",C("--txt")).attr("font-size",22).attr("font-weight",800).text(tot.toLocaleString());
  g.append("text").attr("text-anchor","middle").attr("dy",16).attr("fill",C("--muted")).attr("font-size",10).text("total");
  // legend
  const leg=svg.append("g").attr("transform",`translate(8,10)`);
  leg.selectAll("g").data(data).join("g").attr("transform",(d,i)=>`translate(0,${i*16})`).each(function(d,i){
    const s=d3.select(this);
    s.append("rect").attr("width",10).attr("height",10).attr("rx",2).attr("fill",(colors&&colors[d.label])||colorFor(d.label,i));
    s.append("text").attr("x",15).attr("y",9).attr("fill",C("--muted")).attr("font-size",10).text(`${d.label} (${d.value.toLocaleString()})`);
  });
}

// -------- stacked bar (host x severity) --------
export function stacked(el, rows, keyOuter, keyStack, keyVal, colors){
  // rows: [{host, severity, count}] → group by outer, stack by keyStack
  const outers=[...new Set(rows.map(r=>r[keyOuter]))];
  const stacks=[...new Set(rows.map(r=>r[keyStack]))];
  if(!outers.length){ const c=el.closest(".card"); if(c)c.classList.add("hidden"); return; }
  el.closest(".card")?.classList.remove("hidden"); el.innerHTML="";
  const matrix=outers.map(o=>{const row={_o:o}; stacks.forEach(s=>row[s]=0);
    rows.filter(r=>r[keyOuter]===o).forEach(r=>row[r[keyStack]]=r[keyVal]); return row;});
  const W=el.clientWidth||360, H=230, m={t:10,b:56,l:36,r:8};
  const x=d3.scaleBand().domain(outers).range([m.l,W-m.r]).padding(.25);
  const y=d3.scaleLinear().domain([0,d3.max(matrix,d=>stacks.reduce((a,s)=>a+d[s],0))]).nice().range([H-m.b,m.t]);
  const series=d3.stack().keys(stacks)(matrix);
  const svg=d3.select(el).append("svg").attr("width","100%").attr("viewBox",`0 0 ${W} ${H}`);
  svg.append("g").selectAll("g").data(series).join("g").attr("fill",(d,i)=>(colors&&colors[d.key])||colorFor(d.key,i))
    .selectAll("rect").data(d=>d.map(v=>(v.key=d.key,v))).join("rect")
    .attr("x",d=>x(d.data._o)).attr("width",x.bandwidth()).attr("rx",3)
    .attr("y",d=>y(d[1])).attr("height",d=>y(d[0])-y(d[1]))
    .on("mousemove",(ev,d)=>showTip(`<b>${d.data._o}</b> · ${d.key}: ${(d[1]-d[0]).toLocaleString()}`,ev)).on("mouseleave",hideTip);
  svg.append("g").attr("transform",`translate(0,${H-m.b})`).call(d3.axisBottom(x).tickSize(0))
    .call(g=>g.select(".domain").remove()).selectAll("text").attr("fill",C("--muted")).attr("font-size",10)
    .attr("transform","rotate(-35)").attr("text-anchor","end");
}

// -------- line / area (ordered pairs) --------
export function area(el, obj){
  const e = guard(el, obj); if(!e) return;
  const data=e.map(([label,value])=>({label,value}));
  const W=el.clientWidth||680, H=200, m={t:12,b:38,l:34,r:10};
  const x=d3.scalePoint().domain(data.map(d=>d.label)).range([m.l,W-m.r]);
  const y=d3.scaleLinear().domain([0,d3.max(data,d=>d.value)]).nice().range([H-m.b,m.t]);
  const svg=d3.select(el).append("svg").attr("width","100%").attr("viewBox",`0 0 ${W} ${H}`);
  const grad=svg.append("defs").append("linearGradient").attr("id","ag").attr("x1",0).attr("y1",0).attr("x2",0).attr("y2",1);
  grad.append("stop").attr("offset",0).attr("stop-color",C("--accent")).attr("stop-opacity",.45);
  grad.append("stop").attr("offset",1).attr("stop-color",C("--accent")).attr("stop-opacity",0);
  svg.append("g").attr("transform",`translate(0,${H-m.b})`).call(d3.axisBottom(x)).call(g=>g.select(".domain").attr("stroke",C("--line")))
    .selectAll("text").attr("fill",C("--muted")).attr("font-size",9);
  svg.append("g").attr("transform",`translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W-m.l-m.r)))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("line").attr("stroke",C("--line")).attr("opacity",.5))
    .selectAll("text").attr("fill",C("--muted")).attr("font-size",10);
  svg.append("path").datum(data).attr("fill","url(#ag)").attr("d",d3.area().x(d=>x(d.label)).y0(H-m.b).y1(d=>y(d.value)).curve(d3.curveMonotoneX));
  svg.append("path").datum(data).attr("fill","none").attr("stroke",C("--accent")).attr("stroke-width",2).attr("d",d3.line().x(d=>x(d.label)).y(d=>y(d.value)).curve(d3.curveMonotoneX));
  svg.selectAll("circle").data(data).join("circle").attr("cx",d=>x(d.label)).attr("cy",d=>y(d.value)).attr("r",3).attr("fill",C("--accent"))
    .on("mousemove",(ev,d)=>showTip(`<b>${d.label}</b>: ${d.value.toLocaleString()}`,ev)).on("mouseleave",hideTip);
}

// -------- SHAP Force Horizontal Chart with Gauge --------
export function shapChart(el, shapData, attackCat, confidence) {
  el.innerHTML = "";
  if (!shapData || !shapData.length) { el.innerHTML = '<div class="empty">No explainability vectors returned.</div>'; return; }
  
  const W = el.clientWidth || 400, H = 220;
  
  // Outer structure: circular gauge on left, D3 force bars on right
  const grid = d3.select(el).append("div")
    .style("display", "grid")
    .style("grid-template-columns", "110px 1fr")
    .style("gap", "15px")
    .style("align-items", "center");
  
  // Left: Circular Confidence Gauge
  const gaugeBox = grid.append("div")
    .style("position", "relative")
    .style("width", "110px")
    .style("height", "110px")
    .style("display", "grid")
    .style("place-items", "center");
    
  const pct = Math.round(confidence * 100);
  
  const gSvg = gaugeBox.append("svg").attr("width", "100").attr("height", "100").attr("viewBox", "0 0 100 100")
    .style("transform", "rotate(-90deg)");
    
  gSvg.append("circle").attr("cx", 50).attr("cy", 50).attr("r", 40)
    .attr("stroke", "rgba(255,255,255,0.05)").attr("stroke-width", 7).attr("fill", "none");
  
  const fillArc = gSvg.append("circle").attr("cx", 50).attr("cy", 50).attr("r", 40)
    .attr("stroke", attackCat === "Normal" ? "#10b981" : "#ef4444")
    .attr("stroke-width", 7).attr("fill", "none")
    .attr("stroke-dasharray", 251.2).attr("stroke-dashoffset", 251.2);
  
  fillArc.transition().duration(800).attr("stroke-dashoffset", 251.2 - (251.2 * pct) / 100);
  
  gaugeBox.append("div")
    .style("position", "absolute")
    .style("font-family", "var(--mono)")
    .style("font-weight", "800")
    .style("font-size", "14.5px")
    .style("text-align", "center")
    .style("line-height", "1.2")
    .html(`<span>${pct}%</span><br><span style="font-size:7.5px; text-transform:uppercase; color:var(--muted); letter-spacing:0.5px;">conf</span>`);

  // Right: SHAP Force Horizontal Bar Chart
  const chartBox = grid.append("div");
  const svg = chartBox.append("svg").attr("width", "100%").attr("viewBox", `0 0 ${W - 125} ${H}`);
  
  const m = { t: 10, r: 52, b: 20, l: 110 };
  const w = W - 125;
  
  const maxAbs = d3.max(shapData, d => Math.abs(d.contribution)) || 0.1;
  const x = d3.scaleLinear().domain([-maxAbs * 1.1, maxAbs * 1.1]).range([m.l, w - m.r]);
  const y = d3.scaleBand().domain(shapData.map(d => d.feature)).range([m.t, H - m.b]).padding(0.24);
  
  // Center baseline at 0
  svg.append("line").attr("x1", x(0)).attr("y1", m.t).attr("x2", x(0)).attr("y2", H - m.b)
    .attr("stroke", C("--line")).attr("stroke-width", 1.5);
  
  // Grid lines
  svg.append("g").attr("transform", `translate(0,${H - m.b})`)
    .call(d3.axisBottom(x).ticks(3).tickSize(-(H - m.t - m.b)))
    .call(g => g.select(".domain").remove())
    .call(g => g.selectAll("line").attr("stroke", C("--line")).attr("opacity", 0.3))
    .selectAll("text").attr("fill", C("--muted")).attr("font-size", 9);

  // Bars
  svg.selectAll(".bar").data(shapData).join("rect")
    .attr("class", "bar")
    .attr("y", d => y(d.feature))
    .attr("height", y.bandwidth())
    .attr("rx", 3)
    .attr("fill", d => d.contribution > 0 ? "#ef4444" : "#10b981")
    .attr("x", x(0))
    .attr("width", 0)
    .on("mousemove", (ev, d) => {
      const valPercent = (d.contribution * 10).toFixed(1);
      const sign = d.contribution > 0 ? "+" : "";
      showTip(`<b>Feature:</b> ${d.feature}<br><b>Contribution:</b> ${sign}${valPercent}% towards classification`, ev);
    })
    .on("mouseleave", hideTip)
    .transition().duration(800)
    .attr("x", d => d.contribution > 0 ? x(0) : x(d.contribution))
    .attr("width", d => Math.abs(x(d.contribution) - x(0)));

  // Feature labels (left-aligned)
  svg.append("g").selectAll("text").data(shapData).join("text")
    .attr("x", m.l - 8)
    .attr("y", d => y(d.feature) + y.bandwidth() / 2 + 4)
    .attr("text-anchor", "end")
    .attr("fill", C("--txt-secondary"))
    .attr("font-size", 10.5)
    .attr("font-family", "var(--mono)")
    .text(d => d.feature.length > 14 ? d.feature.slice(0, 13) + "…" : d.feature);

  // Value labels (outside the end of bars)
  svg.append("g").selectAll("text").data(shapData).join("text")
    .attr("x", d => d.contribution > 0 ? x(d.contribution) + 4 : x(d.contribution) - 4)
    .attr("y", d => y(d.feature) + y.bandwidth() / 2 + 4)
    .attr("text-anchor", d => d.contribution > 0 ? "start" : "end")
    .attr("fill", d => d.contribution > 0 ? "#ef4444" : "#10b981")
    .attr("font-size", 10)
    .attr("font-weight", "600")
    .attr("font-family", "var(--mono)")
    .text(d => (d.contribution > 0 ? "+" : "") + (d.contribution * 10).toFixed(1) + "%");
}

export const COLORS = { SEV, EVI };
