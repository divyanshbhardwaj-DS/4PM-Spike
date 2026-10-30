// Universal Decision Explanation Panel Component (Section 14 & 20.6)
class ExplanationPanel {
  constructor() {
    this.createPanelDOM();
    this.bindEvents();
  }

  createPanelDOM() {
    const overlay = document.createElement("div");
    overlay.className = "explanation-panel-overlay";
    overlay.id = "expPanelOverlay";

    const panel = document.createElement("div");
    panel.className = "explanation-panel";
    panel.id = "expPanel";

    panel.innerHTML = `
      <div class="panel-header">
        <h3>
          <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          Decision Explanation Panel
        </h3>
        <button class="panel-close-btn" id="expPanelClose">&times;</button>
      </div>
      <div class="panel-body" id="expPanelBody">
        <div style="text-align: center; padding: 40px; color: #475569;">Loading explanation...</div>
      </div>
    `;

    document.body.appendChild(overlay);
    document.body.appendChild(panel);

    this.overlay = overlay;
    this.panel = panel;
    this.body = document.getElementById("expPanelBody");
  }

  bindEvents() {
    document.getElementById("expPanelClose").addEventListener("click", () => this.close());
    this.overlay.addEventListener("click", () => this.close());
  }

  open() {
    this.overlay.classList.add("open");
    this.panel.classList.add("open");
  }

  close() {
    this.overlay.classList.remove("open");
    this.panel.classList.remove("open");
  }

  async loadDecisionExplanation(decisionId) {
    this.open();
    this.body.innerHTML = `<div style="text-align: center; padding: 40px; color: #475569;">Fetching deterministic explanation...</div>`;

    try {
      const token = localStorage.getItem("dss_token");
      const res = await fetch(`/api/dss/decisions/${decisionId}`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (!res.ok) throw new Error("Failed to load explanation.");
      const data = await res.json();
      this.render13Points(data.explanation, data);
    } catch (err) {
      this.body.innerHTML = `<div style="color: #dc2626; padding: 20px;">Explanation unavailable — ${err.message}</div>`;
    }
  }

  async loadMetricExplanation(metricType, value, buildingId) {
    this.open();
    this.body.innerHTML = `<div style="text-align: center; padding: 40px; color: #475569;">Analyzing rule provenance...</div>`;

    try {
      const token = localStorage.getItem("dss_token");
      let url = `/api/dss/explain-metric?metric_type=${encodeURIComponent(metricType)}&value=${encodeURIComponent(value)}`;
      if (buildingId) url += `&building_id=${buildingId}`;

      const res = await fetch(url, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (!res.ok) throw new Error("Failed to query explanation engine.");
      const exp = await res.json();
      this.render13Points(exp, { decision_code: value, severity: value });
    } catch (err) {
      this.body.innerHTML = `<div style="color: #dc2626; padding: 20px;">Explanation unavailable — ${err.message}</div>`;
    }
  }

  render13Points(exp, meta) {
    if (!exp) {
      this.body.innerHTML = `<div style="padding: 20px; color: #475569;">Explanation unavailable — insufficient supporting information.</div>`;
      return;
    }

    const items = [
      { num: 1, label: "What was decided", val: exp.what_decided },
      { num: 2, label: "Why it was decided", val: exp.why_decided },
      { num: 3, label: "Which data was used", val: `<pre style="font-size: 0.76rem; background: #0f172a; color: #e2e8f0; padding: 10px; border-radius: 4px; overflow-x: auto;">${JSON.stringify(exp.data_used_json, null, 2)}</pre>` },
      { num: 4, label: "Which rule was applied", val: `<strong>${exp.rule_applied}</strong>` },
      { num: 5, label: "Calculation Details", val: exp.calculation_details || "Deterministic direct mapping" },
      { num: 6, label: "Supporting Evidence", val: `<pre style="font-size: 0.76rem; background: #0f172a; color: #e2e8f0; padding: 10px; border-radius: 4px; overflow-x: auto;">${JSON.stringify(exp.supporting_evidence_json, null, 2)}</pre>` },
      { num: 7, label: "Missing Information", val: exp.missing_information || "None. Complete data present." },
      { num: 8, label: "Uncertainty Assessment", val: exp.uncertainty || "Grounded in verified historical records." },
      { num: 9, label: "What could change the result", val: exp.what_could_change || "Updated telemetry ingestion or physical field verification." },
      { num: 10, label: "Recommended Next Step", val: `<strong>${exp.recommended_next_step}</strong>` },
      { num: 11, label: "Responsible Role", val: `<span class="badge badge-sev-info">${exp.responsible_role}</span>` },
      { num: 12, label: "Source & Provenance", val: exp.source_provenance },
      { num: 13, label: "Decision Timestamp", val: exp.decision_timestamp || meta.created_at }
    ];

    let html = `
      <div style="background-color: #f1f5f9; padding: 12px; border-radius: 6px; margin-bottom: 20px; border-left: 4px solid #2563eb;">
        <div style="font-size: 0.75rem; text-transform: uppercase; font-weight: 700; color: #475569;">Context</div>
        <div style="font-size: 0.95rem; font-weight: 700; color: #0f172a;">${meta.building_name || "Campus Meter Analysis"}</div>
      </div>
    `;

    items.forEach(item => {
      html += `
        <div class="panel-item">
          <div class="panel-item-label">
            <span class="panel-item-number">${item.num}</span>
            ${item.label}
          </div>
          <div class="panel-item-content">${item.val}</div>
        </div>
      `;
    });

    this.body.innerHTML = html;
  }
}

// Global singleton instance
window.dssExplanationPanel = new ExplanationPanel();

