// Management Dashboard Client Controller
let currentUser = null;
let allBuildings = [];
let campusChart = null;
let activeReviewDecisionId = null;
let activeFeedbackReviewId = null;

document.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("dss_token");
  if (!token) {
    window.location.href = "/login/management";
    return;
  }

  try {
    const res = await fetch("/api/auth/me", {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) throw new Error("Session expired.");
    currentUser = await res.json();

    if (currentUser.role !== "MANAGEMENT" && currentUser.role !== "ADMIN") {
      alert("Unauthorized role. Redirecting to electrician portal.");
      window.location.href = "/electrician";
      return;
    }

    document.getElementById("mSidebarUserName").innerText = currentUser.full_name;

    setupNavigation();
    await loadInitialManagementData();
  } catch (err) {
    localStorage.removeItem("dss_token");
    window.location.href = "/login/management";
  }
});

function setupNavigation() {
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      navItems.forEach(n => n.classList.remove("active"));
      item.classList.add("active");

      const secId = item.getAttribute("data-section");
      document.querySelectorAll(".view-section").forEach(sec => sec.style.display = "none");
      const targetSec = document.getElementById(secId);
      if (targetSec) targetSec.style.display = "block";

      document.getElementById("mActiveSectionTitle").innerText = item.innerText.trim();

      // Refresh section-specific views
      if (secId === "msec-meter-solar") loadMeterSolarAnalysis();
      if (secId === "msec-evidence") loadEvidenceAssessment();
      if (secId === "msec-feedback") loadElectricianFeedback();
      if (secId === "msec-investigations") loadTasks();
      if (secId === "msec-human-ai-compare") loadHumanAIComparison();
      if (secId === "msec-audit") loadAuditLogs();
      if (secId === "msec-dataset") loadDatasetVersions();
      if (secId === "msec-model") loadModelRegistry();
      if (secId === "msec-override-center") populateOverrideSelect();
    });
  });
}

async function loadInitialManagementData() {
  await loadOverviewMetrics();
  await loadBuildingsAndRankings();
  await loadDataQuality();
  await loadDecisions();
  await loadElectricianFeedback();
  await loadTasks();
}

async function loadOverviewMetrics() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/management/overview-metrics", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const m = await res.json();

  document.getElementById("mTotBuildings").innerText = m.total_buildings;
  document.getElementById("mEligibleBuildings").innerText = m.peak_eligible_buildings;
  document.getElementById("mCritHighFindings").innerText = m.critical_high_severity_findings;
  document.getElementById("mOpenTasks").innerText = m.buildings_requiring_investigation;
  document.getElementById("mPendingReviews").innerText = m.pending_management_reviews;
  document.getElementById("mProtectedAssets").innerText = m.protected_buildings;

  document.getElementById("badgePendingReviews").innerText = m.pending_management_reviews;
  document.getElementById("badgePendingFb").innerText = m.pending_electrician_feedback;
}

async function loadBuildingsAndRankings() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/energy/campus-overview", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const data = await res.json();
  allBuildings = data.buildings || [];

  // Populate Peak Rankings Table
  const tbPeak = document.querySelector("#tablePeakRankings tbody");
  tbPeak.innerHTML = "";

  const chartLabels = [];
  const chartValues = [];

  allBuildings.forEach((b, idx) => {
    chartLabels.push(b.building_code);
    chartValues.push(b.peak_demand_kw);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>#${idx + 1}</strong></td>
      <td>
        <strong>${b.building_name}</strong>
        ${b.is_protected ? '<span class=\"badge badge-protected\" style=\"margin-left:4px;\">PROTECTED</span>' : ''}
      </td>
      <td>${b.category}</td>
      <td><strong>${b.peak_demand_kw} kW</strong></td>
      <td>${b.average_demand_kw || 'N/A'} kW</td>
      <td>${b.demand_trend || 'STABLE'}</td>
      <td>
        ${b.spike_vs_baseline_pct ? (b.spike_vs_baseline_pct > 20 ? '<span style=\"color:#dc2626; font-weight:700;\">+' + b.spike_vs_baseline_pct + '%</span>' : '+' + b.spike_vs_baseline_pct + '%') : '0.0%'}
      </td>
      <td><span class=\"badge badge-sev-info\">${b.boundary_type}</span></td>
      <td>
        <span class=\"badge badge-evi-${b.evidence_grade.toLowerCase()}\">${b.evidence_grade}</span>
        <button class=\"btn-why\" ${dssAction("metric-explanation", "EVIDENCE_GRADE", b.evidence_grade, b.building_id)}>Why?</button>
      </td>
      <td>
        <span class=\"badge badge-sev-${b.severity.toLowerCase()}\">${b.severity}</span>
        <button class=\"btn-why\" ${dssAction("metric-explanation", "SEVERITY", b.severity, b.building_id)}>Why?</button>
      </td>
      <td><code>${b.decision_code}</code></td>
    `;
    tbPeak.appendChild(tr);
  });

  // Render Peak Chart
  const ctx = document.getElementById("chartCampusPeak").getContext("2d");
  if (campusChart) campusChart.destroy();

  campusChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: chartLabels,
      datasets: [{
        label: "Peak Demand kW (16:00-20:00 Window)",
        data: chartValues,
        backgroundColor: chartValues.map(v => v > 500 ? "#dc2626" : (v > 300 ? "#ea580c" : "#2563eb")),
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "Peak Demand (kW)" } },
        x: { title: { display: true, text: "Campus Facilities" } }
      }
    }
  });

  // Populate Building Explorer
  const tbExp = document.querySelector("#tableBuildingExplorer tbody");
  tbExp.innerHTML = "";
  allBuildings.forEach(b => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${b.building_code}</strong></td>
      <td>${b.building_name}</td>
      <td>${b.category}</td>
      <td>${b.is_protected ? '<span class=\"badge badge-protected\">PROTECTED ASSET</span>' : '<span style=\"color:#475569;\">Standard Commercial</span>'}</td>
      <td><code>MTR-${b.building_code.replace('BLD-', '')}-01</code></td>
      <td><span class=\"badge badge-evi-${b.evidence_grade.toLowerCase()}\">${b.evidence_grade}</span></td>
      <td><span class=\"badge badge-sev-${b.severity.toLowerCase()}\">${b.severity}</span></td>
      <td><span class=\"badge badge-elig-${b.eligibility.toLowerCase().replace('_', '-')}\">${b.eligibility}</span></td>
      <td>
        <button class=\"btn-why\" ${dssAction("metric-explanation", "ELIGIBILITY", b.eligibility, b.building_id)}>Explain Eligibility</button>
      </td>
    `;
    tbExp.appendChild(tr);
  });

  // Populate Selects
  const taskBSelect = document.getElementById("taskBuildingSelect");
  taskBSelect.innerHTML = "";
  allBuildings.forEach(b => {
    taskBSelect.innerHTML += `<option value="${b.building_id}">${b.building_name} (${b.building_code})</option>`;
  });
}

// =============================================
// SECTION 4: Meter & Solar Analysis
// =============================================
async function loadMeterSolarAnalysis() {
  const container = document.getElementById("meterSolarDetails");
  if (!container) return;
  container.innerHTML = `<div style="text-align:center; padding:20px; color:#475569;">Loading meter boundary topology...</div>`;
  const token = localStorage.getItem("dss_token");

  let html = "";
  for (const b of allBuildings) {
    try {
      const res = await fetch(`/api/energy/buildings/${b.building_id}/metrics`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const data = await res.json();
      const ba = data.boundary_analysis;
      const badgeClass = ba.boundary_type === "GROSS" ? "badge-evi-e2" : (ba.boundary_type === "NET" ? "badge-evi-e1" : "badge-sev-critical");

      html += `
        <div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:18px; margin-bottom:16px; border-left:4px solid #2563eb;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <h4 style="font-size:1.05rem; color:#0f172a;">${b.building_name} (${b.building_code})</h4>
            <div>
              <span class="badge ${badgeClass}">Boundary: ${ba.boundary_type}</span>
              ${ba.has_solar ? '<span class="badge badge-sev-info" style="margin-left:6px;">Solar PV Array</span>' : ''}
            </div>
          </div>
          <p style="font-size:0.88rem; color:#334155; margin-bottom:10px; line-height:1.5;">${ba.explanation}</p>
          <div style="font-size:0.8rem; color:#475569; background:#f8fafc; padding:10px; border-radius:6px; margin-bottom:12px;">
            <strong>Can Reconstruct Gross Demand:</strong> ${ba.can_reconstruct_gross ? '<span style="color:#059669; font-weight:700;">YES (Supported)</span>' : '<span style="color:#dc2626; font-weight:700;">NO (Unresolved or missing solar)</span>'}<br>
            <strong>Solar Generation Available:</strong> ${ba.has_solar ? 'Yes (' + (ba.solar_aligned ? 'Synchronized 15-min intervals' : 'Misaligned timestamps') + ')' : 'None'}
          </div>
          <div style="display:flex; gap:8px;">
            <button class="btn btn-sm btn-secondary" ${dssAction("metric-explanation", "DECISION_CODE", "RESOLVE_BOUNDARY", b.building_id)}>
              Why Boundary Status?
            </button>
          </div>
        </div>
      `;
    } catch (e) {
      html += `<div style="padding:12px; color:#dc2626;">Failed to load metrics for ${b.building_name}.</div>`;
    }
  }
  container.innerHTML = html || `<div style="text-align:center; padding:20px; color:#475569;">No buildings available.</div>`;
}

// =============================================
// SECTION 6: Evidence Assessment
// =============================================
async function loadEvidenceAssessment() {
  const container = document.getElementById("evidenceBreakdownContainer");
  if (!container) return;

  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/dss/decisions", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const decisions = await res.json();

  // Count evidence grades
  const gradeCounts = { E0: 0, E1: 0, E2: 0, E3: 0 };
  decisions.forEach(d => {
    if (gradeCounts.hasOwnProperty(d.evidence_grade)) {
      gradeCounts[d.evidence_grade]++;
    }
  });

  const gradeDescriptions = {
    E0: { label: "E0 — Insufficient Evidence", color: "#dc2626", desc: "Missing or corrupt data prevents analysis. No meter readings verified. Completeness below threshold." },
    E1: { label: "E1 — Partial Evidence", color: "#ea580c", desc: "Some valid readings available but boundary or solar status is unresolved. Evidence exists but cannot be fully verified." },
    E2: { label: "E2 — Adequate Evidence", color: "#2563eb", desc: "Meter readings pass validation. Boundary type is declared. Sufficient data for deterministic analysis, minor gaps acceptable." },
    E3: { label: "E3 — Full Verified Evidence", color: "#059669", desc: "Complete, validated, verified meter and solar readings. Boundary confirmed GROSS. Full confidence in analysis results." }
  };

  let html = `
    <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:16px; margin-bottom:24px;">
      ${Object.entries(gradeCounts).map(([grade, count]) => `
        <div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:16px; text-align:center; border-top:4px solid ${gradeDescriptions[grade].color};">
          <div style="font-size:2rem; font-weight:700; color:${gradeDescriptions[grade].color};">${count}</div>
          <div style="font-size:0.85rem; font-weight:600; color:#0f172a;">${grade}</div>
          <div style="font-size:0.75rem; color:#475569;">buildings</div>
        </div>
      `).join("")}
    </div>
  `;

  // Grade explanation cards
  Object.entries(gradeDescriptions).forEach(([grade, info]) => {
    html += `
      <div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:16px; margin-bottom:12px; border-left:4px solid ${info.color};">
        <h4 style="color:${info.color}; margin-bottom:6px;">${info.label}</h4>
        <p style="font-size:0.85rem; color:#475569; margin-bottom:10px;">${info.desc}</p>
        <div style="font-size:0.8rem; color:#475569;">
          <strong>Buildings at this grade:</strong>
          ${decisions.filter(d => d.evidence_grade === grade).map(d => d.building_name).join(", ") || "None"}
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

async function loadDataQuality() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/dss/decisions", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const decisions = await res.json();

  const tbody = document.querySelector("#tableManageDQ tbody");
  tbody.innerHTML = "";

  decisions.forEach(d => {
    if (d.decision_code === "AUDIT_REGISTER" || d.decision_code === "RESOLVE_BOUNDARY" || d.severity === "CRITICAL" || d.eligibility === "INSUFFICIENT_DATA") {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class=\"badge badge-sev-${d.severity.toLowerCase()}\">${d.severity}</span></td>
        <td><strong>${d.building_name}</strong></td>
        <td><code>${d.meter_code}</code></td>
        <td>${d.decision_code}</td>
        <td>${d.rule_version}</td>
        <td>${d.short_explanation}</td>
        <td>${d.recommended_action}</td>
      `;
      tbody.appendChild(tr);
    }
  });
}

async function loadDecisions() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/dss/decisions", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const decisions = await res.json();

  const container = document.getElementById("manageDecisionsContainer");
  const pendingContainer = document.getElementById("pendingReviewsContainer");
  const historyTbody = document.querySelector("#tableHistory tbody");
  const safetyContainer = document.getElementById("safetyCardsContainer");

  container.innerHTML = "";
  pendingContainer.innerHTML = "";
  historyTbody.innerHTML = "";
  safetyContainer.innerHTML = "";

  decisions.forEach(d => {
    // Recommendation card
    const card = document.createElement("div");
    card.className = `decision-card ${d.severity.toLowerCase()}`;
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
        <span style="font-weight: 700; color: #475569;">${d.building_name} &bull; ${d.meter_code}</span>
        <div>
          <span class="badge badge-sev-${d.severity.toLowerCase()}">${d.severity}</span>
          <span class="badge badge-evi-${d.evidence_grade.toLowerCase()}">${d.evidence_grade}</span>
          <span class="badge badge-elig-${d.eligibility.toLowerCase().replace('_', '-')}">${d.eligibility}</span>
          <span class="badge badge-sev-info">${d.status}</span>
        </div>
      </div>
      <h4 style="margin-bottom: 6px; font-size: 1.05rem;">${d.decision_code}: ${d.recommended_action}</h4>
      <p style="font-size: 0.85rem; color: #475569; margin-bottom: 12px;">${d.short_explanation}</p>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-sm btn-secondary" ${dssAction("decision-explanation", d.id)}>Why this result? (13-Point Panel)</button>
        <button class="btn btn-sm btn-primary" ${dssAction("open-review-modal", d.id, d.building_name, d.decision_code, "APPROVE")}>Review Recommendation</button>
      </div>
    `;
    container.appendChild(card);

    // Pending review item
    if (d.status === "PENDING_REVIEW") {
      const pCard = document.createElement("div");
      pCard.style.padding = "16px";
      pCard.style.background = "#fff";
      pCard.style.border = "1px solid #e2e8f0";
      pCard.style.borderRadius = "8px";
      pCard.style.marginBottom = "12px";
      pCard.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <strong>${d.building_name}</strong> &ndash; <code>${d.decision_code}</code>
            <div style="font-size:0.85rem; color:#475569; margin-top:4px;">${d.recommended_action}</div>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-sm btn-success" ${dssAction("quick-review-decision", d.id, "APPROVE")}>Approve</button>
            <button class="btn btn-sm btn-danger" ${dssAction("open-review-modal", d.id, d.building_name, d.decision_code, "REJECT")}>Reject / Modify</button>
          </div>
        </div>
      `;
      pendingContainer.appendChild(pCard);
    }

    // History table
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${d.created_at.replace('T', ' ').substring(0, 16)}</td>
      <td>${d.building_name}</td>
      <td><code>${d.decision_code}</code></td>
      <td><span class=\"badge badge-evi-${d.evidence_grade.toLowerCase()}\">${d.evidence_grade}</span></td>
      <td><span class=\"badge badge-sev-${d.severity.toLowerCase()}\">${d.severity}</span></td>
      <td><span class=\"badge badge-sev-info\">${d.status}</span></td>
      <td><button class=\"btn-why\" ${dssAction("decision-explanation", d.id)}>Why?</button></td>
    `;
    historyTbody.appendChild(tr);

    // Protected asset card
    if (d.is_protected) {
      const sCard = document.createElement("div");
      sCard.style.borderLeft = "4px solid #b91c1c";
      sCard.style.background = "#fff";
      sCard.style.padding = "16px";
      sCard.style.borderRadius = "6px";
      sCard.style.marginBottom = "16px";
      sCard.style.boxShadow = "0 1px 3px rgba(0,0,0,0.05)";
      sCard.innerHTML = `
        <div style="display: flex; justify-content: space-between;">
          <h4 style="color: #b91c1c;">${d.building_name} (PROTECTED FACILITY)</h4>
          <span class="badge badge-protected">NON-SHEDDABLE LOAD</span>
        </div>
        <p style="font-size: 0.85rem; color: #475569; margin: 8px 0;">
          Strict safety envelope enforced. Automated load curtailment is physically forbidden.
          Advisories on this facility require senior electrical engineering signoff.
        </p>
        <div style="font-size: 0.82rem; color: #0f172a;">
          <strong>Active DSS Decision:</strong> <code>${d.decision_code}</code> &bull; Severity: <span class="badge badge-sev-${d.severity.toLowerCase()}">${d.severity}</span>
        </div>
      `;
      safetyContainer.appendChild(sCard);
    }
  });

  if (pendingContainer.children.length === 0) {
    pendingContainer.innerHTML = `<div style="padding: 20px; text-align: center; color: #059669;">All DSS recommendations have been reviewed. Zero pending items.</div>`;
  }
}

// =============================================
// REVIEW MODAL (Approve / Reject / Modify)
// =============================================
function openReviewModal(decId, bName, code, defaultAction) {
  activeReviewDecisionId = decId;
  document.getElementById("modalReviewTitle").innerText = `Review Recommendation: ${code}`;
  document.getElementById("modalReviewMeta").innerText = `Facility: ${bName}`;
  document.getElementById("modalReasonText").value = "";
  // Pre-select the action dropdown
  const actionSelect = document.getElementById("modalActionSelect");
  if (defaultAction && actionSelect) {
    actionSelect.value = defaultAction;
  }
  document.getElementById("reviewModal").style.display = "flex";
}

function closeReviewModal() {
  document.getElementById("reviewModal").style.display = "none";
  activeReviewDecisionId = null;
}

async function quickReviewDecision(decId, action) {
  const token = localStorage.getItem("dss_token");
  const res = await fetch(`/api/management/decisions/${decId}/review`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ action: action, reason: "Approved by operations management." })
  });
  if (res.ok) {
    alert("Recommendation successfully approved!");
    await loadOverviewMetrics();
    await loadDecisions();
  }
}

async function submitModalReview() {
  if (!activeReviewDecisionId) return;
  const token = localStorage.getItem("dss_token");
  const action = document.getElementById("modalActionSelect").value;
  const reason = document.getElementById("modalReasonText").value.trim();

  if ((action === "REJECT" || action === "MODIFY") && reason.length < 5) {
    alert("Mandatory engineering justification required for rejection or modification.");
    return;
  }

  const res = await fetch(`/api/management/decisions/${activeReviewDecisionId}/review`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ action, reason: reason || "Reviewed by management" })
  });

  if (res.ok) {
    alert(`Recommendation updated with action: ${action}`);
    closeReviewModal();
    await loadOverviewMetrics();
    await loadDecisions();
  } else {
    const err = await res.json();
    alert("Error: " + err.detail);
  }
}

// =============================================
// SECTION 9: Electrician Feedback (with modal)
// =============================================
async function loadElectricianFeedback() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/feedback", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const feedbackList = await res.json();

  const tbody = document.querySelector("#tableManageFeedback tbody");
  tbody.innerHTML = "";

  feedbackList.forEach(f => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${f.created_at.replace('T', ' ').substring(0, 16)}</td>
      <td>Electrician #${f.user_id}</td>
      <td>Building #${f.building_id}</td>
      <td><span class=\"badge badge-sev-info\">${f.feedback_category}</span></td>
      <td>${f.technical_observation}</td>
      <td>${f.suggested_correction || 'None'}</td>
      <td><span class=\"badge badge-elig-${f.status.toLowerCase().replace('_', '-')}\">${f.status}</span></td>
      <td>
        ${f.status === 'PENDING_REVIEW' ? `
          <button class=\"btn btn-sm btn-primary\" ${dssAction("open-feedback-review-modal", f.id, "Building #" + f.building_id, f.feedback_category, f.technical_observation.substring(0, 80))}>Review</button>
        ` : '<span style=\"color:#475569;\">Closed</span>'}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openFeedbackReviewModal(fbId, bName, category, observation) {
  activeFeedbackReviewId = fbId;
  document.getElementById("modalFbTitle").innerText = `Review Electrician Feedback #${fbId}`;
  document.getElementById("modalFbMeta").innerText = `${bName} • Category: ${category} • "${observation}"`;
  document.getElementById("modalFbReasonText").value = "";
  document.getElementById("modalFbActionSelect").value = "ACCEPT_FEEDBACK";
  document.getElementById("feedbackReviewModal").style.display = "flex";
}

function closeFeedbackReviewModal() {
  document.getElementById("feedbackReviewModal").style.display = "none";
  activeFeedbackReviewId = null;
}

async function submitFeedbackReviewModal() {
  if (!activeFeedbackReviewId) return;
  const token = localStorage.getItem("dss_token");
  const action = document.getElementById("modalFbActionSelect").value;
  const reason = document.getElementById("modalFbReasonText").value.trim();

  if (reason.length < 5) {
    alert("Mandatory reason required (minimum 5 characters).");
    return;
  }

  const res = await fetch(`/api/feedback/${activeFeedbackReviewId}/review`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ action, reason })
  });

  if (res.ok) {
    alert(`Feedback review recorded: ${action}`);
    closeFeedbackReviewModal();
    await loadOverviewMetrics();
    await loadElectricianFeedback();
  } else {
    const err = await res.json();
    alert("Error: " + (err.detail || "Failed to review feedback."));
  }
}

// =============================================
// SECTION 10: Investigation Task Management
// =============================================
async function loadTasks() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/management/tasks", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const tasks = await res.json();

  const tbody = document.querySelector("#tableManageTasks tbody");
  tbody.innerHTML = "";

  tasks.forEach(t => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>TSK-${t.id}</strong></td>
      <td><span class=\"badge badge-sev-${t.priority.toLowerCase()}\">${t.priority}</span></td>
      <td>${t.building_name}</td>
      <td>${t.assigned_to_name}</td>
      <td>${t.required_inspection}</td>
      <td><span class=\"badge badge-elig-pending\">${t.status}</span></td>
      <td>
        ${t.status === 'COMPLETED' ? `
          <button class="btn btn-sm btn-secondary" ${dssAction("manage-task", t.id, "REOPENED")}>Reopen</button>
        ` : t.status === 'SUBMITTED_FOR_REVIEW' ? `
          <button class="btn btn-sm btn-success" ${dssAction("manage-task", t.id, "COMPLETED")}>Mark Complete</button>
          <button class="btn btn-sm btn-secondary" ${dssAction("manage-task", t.id, "REOPENED")}>Reopen</button>
        ` : `
          <span style="font-size:0.78rem; color:#475569;">Awaiting field action</span>
        `}
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Populate electrician assign select
  const uSelect = document.getElementById("taskUserSelect");
  uSelect.innerHTML = `
    <option value="1">Marcus Vance (Master Electrician)</option>
    <option value="2">Elena Rostova (High Voltage Specialist)</option>
  `;
}

async function manageTaskAction(taskId, newStatus) {
  const token = localStorage.getItem("dss_token");
  const res = await fetch(`/api/management/tasks/${taskId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ status: newStatus })
  });
  if (res.ok) {
    alert(`Task TSK-${taskId} updated to ${newStatus}`);
    await loadTasks();
    await loadOverviewMetrics();
  } else {
    alert("Failed to update task status.");
  }
}

document.getElementById("createTaskForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const token = localStorage.getItem("dss_token");

  const payload = {
    building_id: parseInt(document.getElementById("taskBuildingSelect").value),
    assigned_to_user_id: parseInt(document.getElementById("taskUserSelect").value),
    priority: document.getElementById("taskPrioritySelect").value,
    required_inspection: document.getElementById("taskRequiredInspection").value,
    instructions: document.getElementById("taskInstructions").value,
    due_date: document.getElementById("taskDueDate").value ? new Date(document.getElementById("taskDueDate").value).toISOString() : null
  };

  const res = await fetch("/api/management/tasks", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    alert("Investigation task successfully assigned to field electrician!");
    document.getElementById("createTaskForm").reset();
    await loadOverviewMetrics();
    await loadTasks();
  } else {
    alert("Error creating task.");
  }
});

// =============================================
// SECTION 11: Human-AI Comparison
// =============================================
async function loadHumanAIComparison() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/management/human-ai-comparison", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const data = await res.json();

  document.getElementById("mAgreementRate").innerText = `${data.summary_statistics.agreement_rate_pct}%`;
  document.getElementById("mApprovedCount").innerText = data.summary_statistics.approved_recommendations;
  document.getElementById("mOverrideCount").innerText = data.summary_statistics.overrides_recorded;

  const tbody = document.querySelector("#tableHumanAICompare tbody");
  tbody.innerHTML = "";

  data.comparison_table.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${row.building_name}</strong></td>
      <td><code>${row.dss_decision_code}</code>: ${row.dss_recommendation}</td>
      <td>${row.dss_reason}</td>
      <td><span class=\"badge badge-evi-${row.dss_evidence_grade.toLowerCase()}\">${row.dss_evidence_grade}</span></td>
      <td><strong>${row.human_recommendation}</strong></td>
      <td>${row.human_reason}</td>
      <td><span class=\"badge badge-sev-info\">${row.human_status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// =============================================
// SECTION 12: Decision Override Center
// =============================================
async function populateOverrideSelect() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/dss/decisions", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const decisions = await res.json();

  const select = document.getElementById("overrideDecisionSelect");
  select.innerHTML = "";
  decisions.forEach(d => {
    select.innerHTML += `<option value="${d.id}">${d.building_name} &ndash; Current: ${d.decision_code} (${d.severity})</option>`;
  });
}

document.getElementById("overrideForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const token = localStorage.getItem("dss_token");

  const decId = parseInt(document.getElementById("overrideDecisionSelect").value);
  const payload = {
    original_decision_id: decId,
    override_decision_code: document.getElementById("overrideCodeSelect").value,
    override_action: document.getElementById("overrideActionText").value,
    justification: document.getElementById("overrideJustification").value
  };

  try {
    const res = await fetch(`/api/management/decisions/${decId}/override`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Override failed.");

    alert("Permitted decision override executed and recorded in immutable audit log!");
    document.getElementById("overrideForm").reset();
    await loadOverviewMetrics();
    await loadDecisions();
  } catch (err) {
    alert("Error: " + err.message);
  }
});

// =============================================
// SECTION 15: Audit Logs
// =============================================
async function loadAuditLogs() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/audit/logs?limit=50", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const logs = await res.json();

  const tbody = document.querySelector("#tableAudit tbody");
  tbody.innerHTML = "";

  logs.forEach(l => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${l.timestamp.replace('T', ' ').substring(0, 19)}</td>
      <td>User #${l.user_id || 'System'}</td>
      <td><span class=\"badge badge-sev-info\">${l.role || 'SYS'}</span></td>
      <td><strong>${l.event_type}</strong></td>
      <td>${l.entity_type || 'N/A'} ${l.entity_id ? '#' + l.entity_id : ''}</td>
      <td><pre style=\"font-size:0.75rem; margin:0;\">${JSON.stringify(l.action_details)}</pre></td>
    `;
    tbody.appendChild(tr);
  });
}

// =============================================
// SECTION 16: Dataset Management
// =============================================
async function previewDatasetFile() {
  const fileInput = document.getElementById("datasetFileInput");
  if (!fileInput.files.length) {
    alert("Please select a CSV, XLSX, or JSON file first.");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/datasets/preview", {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}` },
    body: formData
  });

  if (!res.ok) {
    alert("Failed to parse file.");
    return;
  }

  const data = await res.json();
  const box = document.getElementById("datasetPreviewBox");
  box.style.display = "block";
  document.getElementById("previewMeta").innerText = `Detected ${data.total_rows} records and ${data.columns.length} columns in ${data.filename}.`;

  const mControls = document.getElementById("mappingControls");
  mControls.innerHTML = "";

  ["timestamp", "power_kw", "energy_kwh", "meter_code", "building_code"].forEach(field => {
    const detected = data.suggested_mapping[field] || "";
    let optionsHtml = `<option value="">-- None --</option>`;
    data.columns.forEach(col => {
      optionsHtml += `<option value="${col}" ${col === detected ? 'selected' : ''}>${col}</option>`;
    });

    mControls.innerHTML += `
      <div>
        <label style="font-size:0.75rem;">Canonical: <code>${field}</code></label>
        <select class="form-control" data-canonical="${field}">${optionsHtml}</select>
      </div>
    `;
  });

  document.getElementById("btnConfirmImport").style.display = "inline-flex";
}

document.getElementById("datasetUploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById("datasetFileInput");
  const token = localStorage.getItem("dss_token");

  // Collect mapping
  const mapping = {};
  document.querySelectorAll("#mappingControls select").forEach(sel => {
    const canon = sel.getAttribute("data-canonical");
    if (sel.value) mapping[canon] = sel.value;
  });

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("dataset_name", document.getElementById("datasetNameInput").value);
  formData.append("provenance_source", document.getElementById("datasetSourceInput").value);
  formData.append("column_mapping_json", JSON.stringify(mapping));

  try {
    const res = await fetch("/api/datasets/import", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: formData
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || "Import failed.");

    alert(`Dataset successfully imported! Version #${result.version_num} created with ${result.valid_records} valid records. DSS core pipeline evaluated.`);
    document.getElementById("datasetUploadForm").reset();
    document.getElementById("datasetPreviewBox").style.display = "none";
    document.getElementById("btnConfirmImport").style.display = "none";
    await loadDatasetVersions();
    await loadOverviewMetrics();
    await loadDecisions();
  } catch (err) {
    alert("Import Error: " + err.message);
  }
});

async function loadDatasetVersions() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/datasets", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const datasets = await res.json();

  const container = document.getElementById("datasetVersionsList");
  container.innerHTML = "";

  datasets.forEach(d => {
    d.versions.forEach(v => {
      const card = document.createElement("div");
      card.style.background = "#fff";
      card.style.border = "1px solid #e2e8f0";
      card.style.padding = "16px";
      card.style.borderRadius = "8px";
      card.style.marginBottom = "12px";
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <strong>${d.name} &bull; Version #${v.version_num}</strong>
            <div style="font-size:0.8rem; color:#475569;">Source: ${v.source} &bull; ${v.record_count} records &bull; Provenance: ${v.provenance_type}</div>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-sm btn-secondary" ${dssAction("download-dataset", v.id, "CSV")}>CSV</button>
            <button class="btn btn-sm btn-secondary" ${dssAction("download-dataset", v.id, "XLSX")}>XLSX</button>
            <button class="btn btn-sm btn-primary" ${dssAction("download-dataset", v.id, "ZIP")}>ZIP Bundle &darr;</button>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  });
}

// =============================================
// SECTION 17: Model Management (ML Governance)
// =============================================
async function checkMLSuitability() {
  const token = localStorage.getItem("dss_token");
  // Use the latest dataset version if available
  let versionId = 1;
  try {
    const dsRes = await fetch("/api/datasets", { headers: { "Authorization": `Bearer ${token}` } });
    const datasets = await dsRes.json();
    if (datasets.length > 0 && datasets[0].versions.length > 0) {
      versionId = datasets[0].versions[0].id;
    }
  } catch (_) {}

  const res = await fetch(`/api/ml/suitability?dataset_version_id=${versionId}`, {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const data = await res.json();
  const s = data.suitability;

  const box = document.getElementById("mlSuitabilityBox");
  box.style.display = "block";
  box.style.background = s.is_suitable ? "#ecfdf5" : "#fef2f2";
  box.style.border = `1px solid ${s.is_suitable ? '#a7f3d0' : '#fca5a5'}`;
  box.innerHTML = `
    <h4>Statistical Suitability Assessment: ${s.is_suitable ? '<span style="color:#059669;">SUITABLE</span>' : '<span style="color:#dc2626;">INSUFFICIENT</span>'}</h4>
    <p style="font-size:0.85rem; margin:8px 0;">${s.reason}</p>
    <div style="font-size:0.8rem; color:#475569;">
      Total Records: ${s.record_count} &bull; Valid Intervals: ${s.valid_count} &bull; Completeness: ${s.completeness_pct}% &bull; Span: ${s.date_span_days} days
    </div>
  `;
}

async function trainMLModel() {
  const token = localStorage.getItem("dss_token");
  // Use the latest dataset version if available
  let versionId = 1;
  try {
    const dsRes = await fetch("/api/datasets", { headers: { "Authorization": `Bearer ${token}` } });
    const datasets = await dsRes.json();
    if (datasets.length > 0 && datasets[0].versions.length > 0) {
      versionId = datasets[0].versions[0].id;
    }
  } catch (_) {}

  try {
    const res = await fetch("/api/ml/train", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        dataset_version_id: versionId,
        task_type: "PEAK_FORECASTING",
        model_type: "RIDGE_REGRESSION",
        model_name: "4PM Peak Demand Forecaster"
      })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || "Training failed.");

    const box = document.getElementById("mlTrainingResultBox");
    box.style.display = "block";
    box.innerHTML = `
      <h4>Model Successfully Trained & Registered: Version #${result.version_num}</h4>
      <p style="font-size:0.85rem; margin:6px 0;">${result.comparison_summary}</p>
      <div style="font-size:0.82rem; color:#166534;">
        Candidate MAE: <strong>${result.metrics.mae} kW</strong> &bull; Baseline MAE: <strong>${result.baseline_metrics.baseline_mae} kW</strong> &bull; RMSE: <strong>${result.metrics.rmse} kW</strong>
      </div>
      <div style="font-size:0.75rem; color:#4b5563; margin-top:8px;">
        <strong>Governance:</strong> ${result.governance_note}
      </div>
    `;
    await loadModelRegistry();
  } catch (err) {
    alert("Training Error: " + err.message);
  }
}

async function loadModelRegistry() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/ml/models", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const models = await res.json();

  const container = document.getElementById("modelRegistryList");
  container.innerHTML = "";

  models.forEach(m => {
    m.versions.forEach(v => {
      const card = document.createElement("div");
      card.style.background = "#fff";
      card.style.border = "1px solid #e2e8f0";
      card.style.padding = "16px";
      card.style.borderRadius = "8px";
      card.style.marginBottom = "12px";
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <strong>${m.name} &bull; v${v.version_num}</strong> (${v.model_type})
            <div style="font-size:0.8rem; color:#475569;">
              Training Period: ${v.training_period.substring(0, 10)} &bull; MAE: ${v.metrics.mae} kW &bull; Status: <span class="badge badge-sev-info">${v.status}</span>
            </div>
          </div>
          <div style="display:flex; gap:6px;">
            ${v.status !== 'ACTIVE' ? `
              <button class="btn btn-sm btn-success" ${dssAction("update-model-status", v.id, "ACTIVATE")}>Activate</button>
            ` : '<span class="badge badge-elig-eligible">ACTIVE MODEL</span>'}
            <button class="btn btn-sm btn-secondary" ${dssAction("update-model-status", v.id, "ROLLBACK")}>Rollback</button>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  });

  if (container.children.length === 0) {
    container.innerHTML = `<div style="padding: 20px; text-align: center; color: #475569;">No candidate ML models registered yet. Click 'Train Time-Aware Forecast Model' to initiate.</div>`;
  }
}

async function updateModelStatus(versionId, action) {
  const token = localStorage.getItem("dss_token");
  const res = await fetch(`/api/ml/models/${versionId}/action`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ action: action })
  });
  if (res.ok) {
    alert(`Model status updated with action ${action}!`);
    await loadModelRegistry();
  }
}

// =============================================
// SECTION 18: Report & Export Downloads
// =============================================
async function downloadReport(reportType, formatType) {
  const token = localStorage.getItem("dss_token");
  try {
    const res = await fetch(`/api/reports/generate?report_type=${reportType}&format_type=${formatType}`, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) {
      const err = await res.json();
      alert("Report Error: " + (err.detail || "Failed to generate report."));
      return;
    }
    const blob = await res.blob();
    const contentDisp = res.headers.get("Content-Disposition") || "";
    const filenameMatch = contentDisp.match(/filename=([^\s;]+)/);
    const filename = filenameMatch ? filenameMatch[1] : `dss_${reportType.toLowerCase()}_report.${formatType.toLowerCase()}`;

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("Download failed: " + err.message);
  }
}

async function downloadAuditExport() {
  const token = localStorage.getItem("dss_token");
  try {
    const res = await fetch("/api/audit/export", {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) {
      alert("Failed to export audit trail.");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dss_audit_trail.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("Export failed: " + err.message);
  }
}

async function downloadDatasetExport(versionId, formatType) {
  const token = localStorage.getItem("dss_token");
  try {
    const res = await fetch(`/api/datasets/${versionId}/export/${formatType}`, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) {
      alert("Failed to export dataset.");
      return;
    }
    const blob = await res.blob();
    const ext = formatType.toLowerCase() === "zip" ? "zip" : (formatType.toLowerCase() === "xlsx" ? "xlsx" : formatType.toLowerCase());
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dss_dataset_v${versionId}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("Export failed: " + err.message);
  }
}

// =============================================
// Logout
// =============================================
function logout() {
  localStorage.removeItem("dss_token");
  localStorage.removeItem("dss_user");
  window.location.href = "/login/management";
}

registerDssAction("logout", logout);
registerDssAction("metric-explanation", (...args) => window.dssExplanationPanel.loadMetricExplanation(...args));
registerDssAction("decision-explanation", decisionId => window.dssExplanationPanel.loadDecisionExplanation(decisionId));
registerDssAction("open-review-modal", openReviewModal);
registerDssAction("quick-review-decision", quickReviewDecision);
registerDssAction("open-feedback-review-modal", openFeedbackReviewModal);
registerDssAction("manage-task", manageTaskAction);
registerDssAction("download-dataset", downloadDatasetExport);
registerDssAction("update-model-status", updateModelStatus);
registerDssAction("download-audit", downloadAuditExport);
registerDssAction("preview-dataset", previewDatasetFile);
registerDssAction("check-ml-suitability", checkMLSuitability);
registerDssAction("train-ml-model", trainMLModel);
registerDssAction("download-report", downloadReport);
registerDssAction("close-review-modal", closeReviewModal);
registerDssAction("submit-review", submitModalReview);
registerDssAction("close-feedback-modal", closeFeedbackReviewModal);
registerDssAction("submit-feedback-review", submitFeedbackReviewModal);
