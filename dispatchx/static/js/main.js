/* DispatchX — Main JavaScript */
"use strict";

const DX = {
  csrfToken: null,

  init() {
    this.csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
                  || getCookie('csrftoken');
    this.initRiskMeters();
    this.initRingScores();
    this.initTabs();
    this.initAlertDismiss();
    this.initAutoRefresh();
    if (document.getElementById('fraud-graph')) this.initFraudGraph();
    if (document.getElementById('ai-simulator')) this.initAISimulator();
    if (document.getElementById('heatmap-container')) this.renderHeatmap();
    this.initAdminActions();
    this.autoHideMessages();
  },

  // ── CSRF helper ──────────────────────────────────────
  async post(url, data) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this.csrfToken,
      },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  // ── Risk Meters ───────────────────────────────────────
  initRiskMeters() {
    document.querySelectorAll('[data-risk-score]').forEach(el => {
      const score = parseFloat(el.dataset.riskScore);
      const fill  = el.querySelector('.risk-fill');
      const label = el.querySelector('.risk-val');
      if (!fill) return;
      const color = score > 0.75 ? '#ef4444' : score > 0.5 ? '#f59e0b' : score > 0.25 ? '#f59e0b' : '#10b981';
      fill.style.width      = `${score * 100}%`;
      fill.style.background = color;
      if (label) { label.textContent = `${(score * 100).toFixed(0)}%`; label.style.color = color; }
    });
  },

  // ── SVG Ring Score ────────────────────────────────────
  initRingScores() {
    document.querySelectorAll('[data-ring-score]').forEach(wrap => {
      const score = parseFloat(wrap.dataset.ringScore);
      const size  = parseInt(wrap.dataset.ringSize || 68);
      const r     = (size - 8) / 2;
      const circ  = 2 * Math.PI * r;
      const color = score > 0.75 ? '#ef4444' : score > 0.5 ? '#f59e0b' : score > 0.25 ? '#f59e0b' : '#10b981';

      wrap.innerHTML = `
        <div class="ring-wrap">
          <svg width="${size}" height="${size}" style="transform:rotate(-90deg)">
            <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="var(--bg4)" stroke-width="5"/>
            <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${color}" stroke-width="5"
              stroke-dasharray="${circ}" stroke-dashoffset="${circ * (1 - score)}"
              stroke-linecap="round" style="transition:stroke-dashoffset .7s ease"/>
          </svg>
          <span class="ring-val" style="color:${color}">${(score*100).toFixed(0)}</span>
          ${wrap.dataset.ringLabel ? `<span class="ring-lbl">${wrap.dataset.ringLabel}</span>` : ''}
        </div>`;
    });
  },

  // ── Tabs ──────────────────────────────────────────────
  initTabs() {
    document.querySelectorAll('.tab-bar').forEach(bar => {
      bar.querySelectorAll('.tab-item').forEach(tab => {
        tab.addEventListener('click', () => {
          const target = tab.dataset.tab;
          bar.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          document.querySelectorAll('[data-tab-pane]').forEach(pane => {
            pane.style.display = pane.dataset.tabPane === target ? '' : 'none';
          });
        });
      });
    });
  },

  // ── Alert Dismiss ─────────────────────────────────────
  initAlertDismiss() {
    document.querySelectorAll('[data-dismiss-alert]').forEach(btn => {
      btn.addEventListener('click', () => {
        btn.closest('.alert')?.remove();
      });
    });
  },

  // ── Auto-hide Django messages ─────────────────────────
  autoHideMessages() {
    document.querySelectorAll('.toast').forEach(t => {
      setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(40px)'; setTimeout(() => t.remove(), 300); }, 4000);
    });
  },

  // ── Admin Actions ─────────────────────────────────────
  initAdminActions() {
    document.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const action = btn.dataset.action;
        const userId = btn.dataset.userId;
        const alertId= btn.dataset.alertId;

        if (!confirm(`Confirm action: ${action.replace('_',' ')}?`)) return;
        btn.disabled = true;
        btn.textContent = '...';

        try {
          let result;
          if (alertId) {
            result = await this.post(`/api/admin/resolve/${alertId}/`, { notes: '' });
            if (result.ok) { btn.closest('.alert')?.remove(); this.showToast('Alert resolved', 'success'); }
          } else if (userId) {
            result = await this.post(`/api/admin/action/${userId}/`, { action, notes: '' });
            if (result.ok) {
              this.showToast(`Action taken: ${action.replace('_',' ')}`, 'success');
              const row = btn.closest('tr');
              if (row && action === 'block') row.style.opacity = '0.4';
            }
          }
        } catch(e) {
          this.showToast('Request failed', 'error');
        }
        btn.disabled = false;
        btn.textContent = action.replace('_',' ');
      });
    });

    // Trigger event form
    const triggerForm = document.getElementById('trigger-event-form');
    if (triggerForm) {
      triggerForm.addEventListener('submit', async e => {
        e.preventDefault();
        const fd = new FormData(triggerForm);
        const result = await this.post('/api/admin/trigger-event/', {
          event_type: fd.get('event_type'),
          zone: fd.get('zone'),
          value: parseFloat(fd.get('value')),
        });
        if (result.ok) {
          this.showToast(`Event triggered! ${result.payouts_created} payouts released — ₹${result.total_amount}`, 'success');
        }
      });
    }
  },

  // ── Toast notification ────────────────────────────────
  showToast(msg, type = 'success') {
    let bar = document.querySelector('.messages-bar');
    if (!bar) { bar = document.createElement('div'); bar.className = 'messages-bar'; document.body.appendChild(bar); }
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    bar.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 4000);
  },

  // ── Fraud Graph (D3-like, vanilla SVG) ───────────────
  async initFraudGraph() {
    const container = document.getElementById('fraud-graph');
    if (!container) return;

    let data;
    try {
      const res = await fetch('/api/admin/fraud-graph/');
      data = await res.json();
    } catch(e) {
      container.innerHTML = '<p style="padding:20px;color:var(--text3)">Graph data unavailable</p>';
      return;
    }

    const W = container.offsetWidth || 700;
    const H = 340;
    const cx = W / 2, cy = H / 2, radius = Math.min(W, H) / 2 - 50;

    // Layout: circular for first 20 nodes
    const nodes = data.nodes.slice(0, 24);
    const positions = {};
    nodes.forEach((n, i) => {
      const angle = (2 * Math.PI * i / nodes.length) - Math.PI / 2;
      positions[n.id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      };
    });

    const riskColor = r => ({ low:'#10b981', medium:'#f59e0b', high:'#ef4444', critical:'#f87171' }[r] || '#64748b');
    const nodeRadius = r => ({ critical: 13, high: 10, medium: 8, low: 7 }[r] || 7);

    let svgHtml = `<svg width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg" style="border-radius:10px">
      <rect width="${W}" height="${H}" fill="var(--bg3)" rx="10"/>`;

    // Edges
    data.edges.forEach(e => {
      const a = positions[e.source], b = positions[e.target];
      if (!a || !b) return;
      const isDevice = e.types.includes('shared_device');
      svgHtml += `<line x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}"
        x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}"
        stroke="${isDevice ? '#f59e0b' : '#ef4444'}"
        stroke-opacity="0.45" stroke-width="1.5"
        ${isDevice ? 'stroke-dasharray="4,3"' : ''} />`;
    });

    // Nodes
    nodes.forEach(n => {
      const p = positions[n.id];
      if (!p) return;
      const c  = riskColor(n.risk);
      const nr = nodeRadius(n.risk);
      svgHtml += `
        <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${nr}"
          fill="${c}" fill-opacity="0.25" stroke="${c}" stroke-width="1.5"/>
        <text x="${p.x.toFixed(1)}" y="${(p.y + 4).toFixed(1)}"
          text-anchor="middle" font-size="7" fill="${c}"
          font-family="'JetBrains Mono',monospace">${n.id}</text>`;
    });

    // Legend
    svgHtml += `
      <text x="10" y="${H - 20}" font-size="9" fill="var(--text3)" font-family="'Space Grotesk',sans-serif">
        Red = shared IP · Yellow dashed = shared device · Node size = risk level
      </text>`;

    svgHtml += '</svg>';
    container.innerHTML = svgHtml;
  },

  // ── AI Simulator ──────────────────────────────────────
  initAISimulator() {
    const sim = document.getElementById('ai-simulator');
    if (!sim) return;

    const inputs = sim.querySelectorAll('input[type=range]');
    const updateAll = () => {
      const speed    = parseFloat(sim.querySelector('#sim-speed').value);
      const behavior = parseFloat(sim.querySelector('#sim-behavior').value);
      const network  = parseFloat(sim.querySelector('#sim-network').value);
      const graph    = parseFloat(sim.querySelector('#sim-graph').value);

      const speedScore = Math.min(speed / 120, 1);
      const composite  = (0.30 * speedScore + 0.30 * (1 - behavior) + 0.20 * network + 0.20 * graph);
      const score      = Math.min(composite, 1.0);

      // Update display values
      sim.querySelector('#val-speed').textContent    = `${speed} km/h`;
      sim.querySelector('#val-behavior').textContent = `${(behavior * 100).toFixed(0)}%`;
      sim.querySelector('#val-network').textContent  = `${(network * 100).toFixed(0)}%`;
      sim.querySelector('#val-graph').textContent    = `${(graph * 100).toFixed(0)}%`;

      // Score components
      sim.querySelector('#comp-speed').textContent    = (0.30 * speedScore).toFixed(3);
      sim.querySelector('#comp-behavior').textContent = (0.30 * (1 - behavior)).toFixed(3);
      sim.querySelector('#comp-network').textContent  = (0.20 * network).toFixed(3);
      sim.querySelector('#comp-graph').textContent    = (0.20 * graph).toFixed(3);
      sim.querySelector('#comp-total').textContent    = score.toFixed(3);

      // Decision
      let decision, dColor;
      if (score < 0.35)      { decision = 'ALLOW';      dColor = '#10b981'; }
      else if (score < 0.55) { decision = 'MONITOR';    dColor = '#818cf8'; }
      else if (score < 0.75) { decision = 'OTP VERIFY'; dColor = '#f59e0b'; }
      else                   { decision = 'BLOCK';       dColor = '#ef4444'; }

      const decEl = sim.querySelector('#sim-decision');
      decEl.textContent = decision;
      decEl.style.color = dColor;
      decEl.style.background = `${dColor}18`;
      decEl.style.borderColor = `${dColor}40`;

      // Update risk meter
      const fill = sim.querySelector('#sim-risk-fill');
      if (fill) {
        fill.style.width = `${score * 100}%`;
        fill.style.background = dColor;
      }
    };

    inputs.forEach(inp => inp.addEventListener('input', updateAll));
    updateAll();
  },

  // ── Heatmap ───────────────────────────────────────────
  renderHeatmap() {
    // Heatmap is server-rendered; just add hover tooltips
    document.querySelectorAll('.heatmap-cell').forEach(cell => {
      cell.addEventListener('mouseenter', () => {
        cell.title = `Zone: ${cell.dataset.zone}\nAvg Risk: ${cell.dataset.risk}%\nUsers: ${cell.dataset.count}`;
      });
    });
  },

  // ── Auto-refresh stats every 30s ─────────────────────
  initAutoRefresh() {
    const refreshEl = document.querySelector('[data-auto-refresh]');
    if (!refreshEl) return;
    const interval = parseInt(refreshEl.dataset.autoRefresh || 30000);
    setInterval(() => {
      const indicator = document.querySelector('.live-dot');
      if (indicator) { indicator.style.background = '#818cf8'; setTimeout(() => { indicator.style.background = '#10b981'; }, 600); }
    }, interval);
  },
};

// ── Utility ──────────────────────────────────────────────
function getCookie(name) {
  const v = document.cookie.match('(^|;) ?' + name + '=([^;]*)(;|$)');
  return v ? v[2] : null;
}

// ── Plan selector ─────────────────────────────────────────
function selectPlan(planId, color) {
  document.querySelectorAll('.plan-card').forEach(c => c.classList.remove('selected'));
  document.querySelectorAll('.plan-checkmark').forEach(c => c.style.display = 'none');
  const card = document.querySelector(`[data-plan="${planId}"]`);
  if (card) {
    card.classList.add('selected');
    const mark = card.querySelector('.plan-checkmark');
    if (mark) { mark.style.display = 'flex'; mark.style.background = color; }
  }
  const hidden = document.getElementById('selected-plan-id');
  if (hidden) hidden.value = planId;
}

// ── Boot ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => DX.init());
