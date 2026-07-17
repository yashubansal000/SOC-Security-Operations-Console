// LandingPage component: renders Hero, Canvas Particle Background, Features, Stack, and Workflow.
const anime = window.anime;

export class LandingPage {
  constructor(containerId, onLaunch) {
    this.container = document.querySelector(containerId);
    this.onLaunch = onLaunch;
    this.canvas = null;
    this.ctx = null;
    this.nodes = [];
    this.maxNodes = 60;
    this.animationId = null;
    this.mouse = { x: null, y: null, radius: 120 };
  }

  render() {
    if (!this.container) return;

    this.container.innerHTML = `
      <canvas class="lg-canvas" id="landingCanvas"></canvas>
      <div class="grid-overlay"></div>
      <div class="lg-wrap">
        <div class="lg-badge">
          <span class="d"></span> Live SOC &bull; UNSW-NB15 &bull; Deterministic Verification
        </div>
        
        <div class="lg-tag" style="margin-top:24px">AI-Powered Network Command Center</div>
        <h1 class="lg-title">Autonomous Threat Detection<br><span>&amp; Root Cause Analysis</span></h1>
        
        <p class="lg-sub">
          An enterprise-grade Security Operations Center (SOC) dashboard. Ingests raw network telemetry, 
          classifies anomalies with explainable machine learning (SHAP), clusters correlations into active incidents, 
          and utilizes grounded LLM reasoning for root cause analysis and automated mitigation.
        </p>
        
        <div style="margin-bottom: 40px;">
          <button class="lg-cta" id="launchBtn">Launch SOC Console &rarr;</button>
          <button class="lg-ghost" id="scrollArchBtn">System Architecture</button>
        </div>

        <div class="lg-sec">Core Capabilities</div>
        <div class="lg-grid lg-feats" id="featGrid">
          <div class="lg-card">
            <div class="ic">🧠</div>
            <h3>Explainable ML Engine</h3>
            <p>Tree-based XGBoost classifier with per-flow SHAP feature attributions across 82,000 scored network telemetry flows.</p>
          </div>
          <div class="lg-card">
            <div class="ic">🔗</div>
            <h3>Grounded Correlation</h3>
            <p>Clusters anomalous telemetry into distinct security incidents. Cross-references confirmed, correlated, and missing evidence.</p>
          </div>
          <div class="lg-card">
            <div class="ic">🛡️</div>
            <h3>Verification Agent</h3>
            <p>LangGraph multi-agent orchestration. A deterministic validator verifies reasoning traces to prevent hallucinated claims.</p>
          </div>
          <div class="lg-card">
            <div class="ic">🧾</div>
            <h3>Immutable Audit Trail</h3>
            <p>Surfaces all system and human-reviewer mutations in a chronological, search-optimized security audit console.</p>
          </div>
        </div>

        <div class="lg-sec" id="archSec">System Ingestion Workflow</div>
        <div class="flow" id="workflowGrid">
          <div class="step">
            <div class="k">Module 1</div>
            <div class="v">Raw Ingestion</div>
            <div class="d" style="color:var(--muted);font-size:11px;margin-top:4px;">Multi-source flow generator</div>
          </div>
          <div class="arrow">&rarr;</div>
          <div class="step">
            <div class="k">Module 2</div>
            <div class="v">XGBoost &amp; SHAP</div>
            <div class="d" style="color:var(--muted);font-size:11px;margin-top:4px;">Anomaly scoring &amp; values</div>
          </div>
          <div class="arrow">&rarr;</div>
          <div class="step">
            <div class="k">Module 3</div>
            <div class="v">Evidence Correlator</div>
            <div class="d" style="color:var(--muted);font-size:11px;margin-top:4px;">Buckets related alerts</div>
          </div>
          <div class="arrow">&rarr;</div>
          <div class="step">
            <div class="k">Module 4</div>
            <div class="v">LangGraph Reasoner</div>
            <div class="d" style="color:var(--muted);font-size:11px;margin-top:4px;">Ranked hypotheses</div>
          </div>
          <div class="arrow">&rarr;</div>
          <div class="step">
            <div class="k">Module 7</div>
            <div class="v">Command API</div>
            <div class="d" style="color:var(--muted);font-size:11px;margin-top:4px;">SIEM auditing &amp; controls</div>
          </div>
        </div>

        <div class="lg-sec">Enterprise Technology Stack</div>
        <div class="stack">
          <span class="chip"><b>FastAPI</b> backend</span>
          <span class="chip"><b>SQLite</b> database</span>
          <span class="chip"><b>XGBoost</b> detection</span>
          <span class="chip"><b>SHAP Explainer</b></span>
          <span class="chip"><b>LangGraph</b> agentic loop</span>
          <span class="chip"><b>NetworkX</b> topology routing</span>
          <span class="chip"><b>D3.js</b> visualization</span>
          <span class="chip"><b>Anime.js</b> motion</span>
        </div>

        <div class="lg-foot">
          <span>Enterprise Incident Command Center &bull; Tech Mahindra Hackathon</span>
          <span>Security Operations Center Dashboard &bull; Live Telemetry Feed</span>
        </div>
      </div>
    `;

    this.initCanvas();
    this.bindEvents();
    this.animateEntrance();
    this.animateWorkflow();
  }

  initCanvas() {
    this.canvas = document.getElementById('landingCanvas');
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    
    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());

    // Populate particles (nodes)
    this.nodes = [];
    for (let i = 0; i < this.maxNodes; i++) {
      this.nodes.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r: Math.random() * 2 + 1.5,
        color: Math.random() > 0.7 ? '#06b6d4' : '#3b82f6'
      });
    }

    // Mouse interactive movement
    window.addEventListener('mousemove', (e) => {
      this.mouse.x = e.clientX;
      this.mouse.y = e.clientY;
    });

    window.addEventListener('mouseout', () => {
      this.mouse.x = null;
      this.mouse.y = null;
    });

    this.runCanvasLoop();
  }

  resizeCanvas() {
    if (this.canvas) {
      this.canvas.width = window.innerWidth;
      this.canvas.height = window.innerHeight;
    }
  }

  runCanvasLoop() {
    const loop = () => {
      if (!this.canvas) return;
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

      // Draw lines
      for (let i = 0; i < this.nodes.length; i++) {
        const n1 = this.nodes[i];
        for (let j = i + 1; j < this.nodes.length; j++) {
          const n2 = this.nodes[j];
          const dist = Math.hypot(n1.x - n2.x, n1.y - n2.y);
          if (dist < 100) {
            const alpha = (1 - dist / 100) * 0.12;
            this.ctx.strokeStyle = `rgba(59, 130, 246, ${alpha})`;
            this.ctx.lineWidth = 0.5;
            this.ctx.beginPath();
            this.ctx.moveTo(n1.x, n1.y);
            this.ctx.lineTo(n2.x, n2.y);
            this.ctx.stroke();
          }
        }
      }

      // Draw and update nodes
      for (const n of this.nodes) {
        n.x += n.vx;
        n.y += n.vy;

        // Bounce on boundaries
        if (n.x < 0 || n.x > this.canvas.width) n.vx *= -1;
        if (n.y < 0 || n.y > this.canvas.height) n.vy *= -1;

        // Interactive mouse connection
        if (this.mouse.x !== null) {
          const mDist = Math.hypot(n.x - this.mouse.x, n.y - this.mouse.y);
          if (mDist < this.mouse.radius) {
            const force = (1 - mDist / this.mouse.radius) * 0.15;
            this.ctx.strokeStyle = `rgba(6, 182, 212, ${force * 0.4})`;
            this.ctx.lineWidth = 0.8;
            this.ctx.beginPath();
            this.ctx.moveTo(n.x, n.y);
            this.ctx.lineTo(this.mouse.x, this.mouse.y);
            this.ctx.stroke();
          }
        }

        this.ctx.fillStyle = n.color;
        this.ctx.beginPath();
        this.ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        this.ctx.fill();
      }

      this.animationId = requestAnimationFrame(loop);
    };

    loop();
  }

  bindEvents() {
    const launchBtn = document.getElementById('launchBtn');
    if (launchBtn) {
      launchBtn.addEventListener('click', () => {
        this.destroy();
        this.onLaunch();
      });
    }

    const scrollBtn = document.getElementById('scrollArchBtn');
    const archSec = document.getElementById('archSec');
    if (scrollBtn && archSec) {
      scrollBtn.addEventListener('click', () => {
        archSec.scrollIntoView({ behavior: 'smooth' });
      });
    }
  }

  animateEntrance() {
    if (!anime) return;
    anime.timeline({ easing: 'easeOutQuad' })
      .add({
        targets: '.lg-badge',
        translateY: [-15, 0],
        opacity: [0, 1],
        duration: 500
      })
      .add({
        targets: ['.lg-tag', '.lg-title', '.lg-sub'],
        translateY: [20, 0],
        opacity: [0, 1],
        delay: anime.stagger(100),
        duration: 600
      }, '-=300')
      .add({
        targets: ['.lg-cta', '.lg-ghost'],
        translateY: [15, 0],
        opacity: [0, 1],
        delay: anime.stagger(80),
        duration: 500
      }, '-=400')
      .add({
        targets: '#featGrid .lg-card',
        translateY: [20, 0],
        opacity: [0, 1],
        delay: anime.stagger(80),
        duration: 600
      }, '-=300');
  }

  animateWorkflow() {
    if (!anime) return;
    anime({
      targets: '#workflowGrid .step',
      scale: [0.96, 1],
      opacity: [0, 1],
      delay: anime.stagger(150, { start: 1000 }),
      duration: 800,
      easing: 'easeOutElastic(1, .8)'
    });
  }

  destroy() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
    }
  }
}
