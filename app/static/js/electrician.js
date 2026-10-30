// Electrician Dashboard Client Controller
let currentUser = null;
let assignedBuildings = [];
let chartInstance = null;

document.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("dss_token");
  if (!token) {
    window.location.href = "/login/electrician";
    return;
  }

  try {
    const res = await fetch("/api/auth/me", {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) throw new Error("Session expired.");
    currentUser = await res.json();
    if (currentUser.role !== "ELECTRICIAN" && currentUser.role !== "ADMIN") {
      alert("Unauthorized role. Redirecting to management dashboard.");
      window.location.href = "/management";
      return;
    }

    document.getElementById("sidebarUserName").innerText = currentUser.full_name;
    document.getElementById("profName").innerText = currentUser.full_name;
    document.getElementById("profUsername").innerText = currentUser.username;

    setupNavigation();
    await loadInitialData();
  } catch (err) {
    localStorage.removeItem("dss_token");
    window.location.href = "/login/electrician";
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

      document.getElementById("activeSectionTitle").innerText = item.innerText.trim();

      // Trigger section-specific loads
      if (secId === "sec-meter-readings") renderReadingsChart();
      if (secId === "sec-fb-history") loadFeedbackHistory();
      if (secId === "sec-boundaries") loadBoundaries();
      if (secId === "sec-tasks") loadTasks();
    });
  });
}

async function loadInitialData() {
  await loadBuildings();
  await loadTasks();
  await loadDataQuality();
  await loadDSSDecisions();
}

async function loadBuildings() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/buildings", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  assignedBuildings = await res.json();

  document.getElementById("mAssignedBuildings").innerText = assignedBuildings.length;
  document.getElementById("profAssigned").innerText = assignedBuildings.map(b => b.name).join(", ");

  // Populate building table
  const tbody = document.querySelector("#tableAssignedBuildings tbody");
  tbody.innerHTML = "";

  const fbSelect = document.getElementById("fbBuildingSelect");
  const chartSelect = document.getElementById("selectBuildingReadings");
  fbSelect.innerHTML = "";
  chartSelect.innerHTML = "";

  assignedBuildings.forEach(b => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${b.code}</strong></td>
      <td>${b.name}</td>
      <td>${b.category}</td>
      <td>${b.is_protected ? '<span class="badge badge-protected">PROTECTED</span>' : 'Standard'}</td>
      <td>
        <span class="badge badge-evi-${b.evidence_grade.toLowerCase()}">${b.evidence_grade}</span>
        <button class="btn-why" onclick="window.dssExplanationPanel.loadMetricExplanation('EVIDENCE_GRADE', '${b.evidence_grade}', ${b.id})">Why?</button>
      </td>
      <td>
        <span class="badge badge-sev-${b.severity.toLowerCase()}">${b.severity}</span>
        <button class="btn-why" onclick="window.dssExplanationPanel.loadMetricExplanation('SEVERITY', '${b.severity}', ${b.id})">Why?</button>
      </td>
      <td>
        <span class="badge badge-elig-${b.eligibility.toLowerCase().replace('_', '-')}">${b.eligibility}</span>
        <button class="btn-why" onclick="window.dssExplanationPanel.loadMetricExplanation('ELIGIBILITY', '${b.eligibility}', ${b.id})">Why?</button>
      </td>
      <td><strong>${b.open_investigation_count}</strong></td>
      <td>
        <button class="btn btn-sm btn-primary" onclick="inspectBuilding(${b.id})">Inspect</button>
      </td>
    `;
    tbody.appendChild(tr);

    fbSelect.innerHTML += `<option value="${b.id}">${b.name} (${b.code})</option>`;
    chartSelect.innerHTML += `<option value="${b.id}">${b.name} (${b.code})</option>`;
  });

  chartSelect.addEventListener("change", () => renderReadingsChart());
}

async function loadTasks() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/management/tasks", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const tasks = await res.json();

  const pending = tasks.filter(t => ["ASSIGNED", "IN_PROGRESS", "NEEDS_INFORMATION", "REOPENED"].includes(t.status));
  document.getElementById("mPendingTasks").innerText = pending.length;
  document.getElementById("badgePendingTasks").innerText = pending.length;

  const critCount = tasks.filter(t => t.priority === "CRITICAL" || t.priority === "HIGH").length;
  document.getElementById("mHighCritIssues").innerText = critCount;

  // Overview table (top 5 pending)
  const tbOverview = document.querySelector("#tableOverviewTasks tbody");
  tbOverview.innerHTML = "";
  pending.slice(0, 5).forEach(t => {
    const nextAction = t.status === 'ASSIGNED' ? 'IN_PROGRESS' : (t.status === 'IN_PROGRESS' ? 'SUBMITTED_FOR_REVIEW' : 'COMPLETED');
    const btnText = t.status === 'ASSIGNED' ? 'Start Work' : (t.status === 'IN_PROGRESS' ? 'Submit for Review' : 'Advance');
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>TSK-${t.id}</strong></td>
      <td><span class="badge badge-sev-${t.priority.toLowerCase()}">${t.priority}</span></td>
      <td>${t.building_name}</td>
      <td>${t.meter_code}</td>
      <td>${t.required_inspection}</td>
      <td><span class="badge badge-elig-pending">${t.status}</span></td>
      <td>
        <button class="btn btn-sm btn-primary" onclick="quickUpdateTask(${t.id}, '${nextAction}')">${btnText}</button>
      </td>
    `;
    tbOverview.appendChild(tr);
  });

  // All tasks table
  const tbAll = document.querySelector("#tableAllTasks tbody");
  tbAll.innerHTML = "";
  tasks.forEach(t => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>TSK-${t.id}</strong></td>
      <td><span class="badge badge-sev-${t.priority.toLowerCase()}">${t.priority}</span></td>
      <td>${t.building_name}</td>
      <td>${t.meter_code}</td>
      <td>${t.required_inspection}</td>
      <td>${t.instructions || "Standard SOP inspection"}</td>
      <td><span class="badge badge-elig-pending">${t.status}</span></td>
      <td>
        <select class="form-control" style="font-size: 0.78rem;" onchange="updateTaskStatus(${t.id}, this.value)">
          <option value="ASSIGNED" ${t.status === 'ASSIGNED' ? 'selected' : ''}>ASSIGNED</option>
          <option value="IN_PROGRESS" ${t.status === 'IN_PROGRESS' ? 'selected' : ''}>IN_PROGRESS</option>
          <option value="NEEDS_INFORMATION" ${t.status === 'NEEDS_INFORMATION' ? 'selected' : ''}>NEEDS_INFO</option>
          <option value="SUBMITTED_FOR_REVIEW" ${t.status === 'SUBMITTED_FOR_REVIEW' ? 'selected' : ''}>SUBMIT_FOR_REVIEW</option>
          <option value="COMPLETED" ${t.status === 'COMPLETED' ? 'selected' : ''}>COMPLETED</option>
        </select>
      </td>
    `;
    tbAll.appendChild(tr);
  });
}

async function updateTaskStatus(taskId, newStatus) {
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
    await loadTasks();
  } else {
    alert("Failed to update task status.");
  }
}

async function quickUpdateTask(taskId, newStatus) {
  await updateTaskStatus(taskId, newStatus);
}

function inspectBuilding(bId) {
  const chartSelect = document.getElementById("selectBuildingReadings");
  if (chartSelect) chartSelect.value = bId;
  const navBtn = document.querySelector('[data-section="sec-meter-readings"]');
  if (navBtn) navBtn.click();
  renderReadingsChart();
}

async function loadBoundaries() {
  const container = document.getElementById("boundaryCardsContainer");
  if (!container) return;
  container.innerHTML = `<div style="text-align:center; padding:20px; color:#64748b;">Loading boundary analyses...</div>`;
  const token = localStorage.getItem("dss_token");

  let html = "";
  for (const b of assignedBuildings) {
    try {
      const res = await fetch(`/api/energy/buildings/${b.id}/metrics`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const data = await res.json();
      const ba = data.boundary_analysis;
      const badgeClass = ba.boundary_type === "GROSS" ? "badge-evi-e2" : (ba.boundary_type === "NET" ? "badge-evi-e1" : "badge-sev-critical");

      html += `
        <div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:18px; margin-bottom:16px; border-left:4px solid #2563eb;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <h4 style="font-size:1.05rem; color:#0f172a;">${b.name} (${b.code})</h4>
            <div>
              <span class="badge ${badgeClass}">Boundary: ${ba.boundary_type}</span>
              ${ba.has_solar ? '<span class="badge badge-sev-info" style="margin-left:6px;">Solar PV Array</span>' : ''}
            </div>
          </div>
          <p style="font-size:0.88rem; color:#334155; margin-bottom:10px; line-height:1.5;">${ba.explanation}</p>
          <div style="font-size:0.8rem; color:#64748b; background:#f8fafc; padding:10px; border-radius:6px; margin-bottom:12px;">
            <strong>Can Reconstruct Gross Demand:</strong> ${ba.can_reconstruct_gross ? '<span style="color:#059669; font-weight:700;">YES (Supported)</span>' : '<span style="color:#dc2626; font-weight:700;">NO (Unresolved or missing solar)</span>'}<br>
            <strong>Solar Generation Available:</strong> ${ba.has_solar ? 'Yes (' + (ba.solar_aligned ? 'Synchronized 15-min intervals' : 'Misaligned timestamps') + ')' : 'None'}
          </div>
          <div style="display:flex; gap:8px;">
            <button class="btn btn-sm btn-secondary" onclick="window.dssExplanationPanel.loadMetricExplanation('DECISION_CODE', 'RESOLVE_BOUNDARY', ${b.id})">
              Why Boundary Status?
            </button>
            <button class="btn btn-sm btn-primary" onclick="openFeedbackForDecision(null, ${b.id}, 'METER_BOUNDARY')">
              Submit Boundary Correction
            </button>
          </div>
        </div>
      `;
    } catch (e) {
      console.error(e);
    }
  }
  container.innerHTML = html || `<div style="text-align:center; padding:20px; color:#64748b;">No assigned buildings found.</div>`;
}

async function renderReadingsChart() {
  let bId = document.getElementById("selectBuildingReadings").value;
  if (!bId && assignedBuildings.length > 0) {
    bId = assignedBuildings[0].id;
    document.getElementById("selectBuildingReadings").value = bId;
  }
  if (!bId) return;

  const token = localStorage.getItem("dss_token");
  const res = await fetch(`/api/energy/buildings/${bId}/intervals?peak_only=true`, {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const data = await res.json();

  // Populate interval table
  const tbody = document.querySelector("#tableIntervals tbody");
  tbody.innerHTML = "";
  data.forEach(item => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.timestamp.replace("T", " ")}</td>
      <td><strong>${item.power_kw !== null ? item.power_kw + ' kW' : '<span style=\"color:#dc2626;\">MISSING</span>'}</strong></td>
      <td>${item.solar_kw ? item.solar_kw + ' kW' : '0.0 kW'}</td>
      <td>${item.is_valid ? '<span class=\"badge badge-sev-low\">VALID</span>' : '<span class=\"badge badge-sev-critical\">INVALID</span>'}</td>
      <td>${item.validation_flags || "VALID"}</td>
    `;
    tbody.appendChild(tr);
  });

  // Render Chart
  const ctx = document.getElementById("chartMeterReadings").getContext("2d");
  const labels = data.map(d => d.timestamp.split("T")[1].substring(0, 5));
  const powerData = data.map(d => d.power_kw);
  const solarData = data.map(d => d.solar_kw);

  if (chartInstance) chartInstance.destroy();

  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Measured Power Demand (kW)",
          data: powerData,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.1)",
          fill: true,
          tension: 0.3,
          borderWidth: 2
        },
        {
          label: "Solar PV Generation (kW)",
          data: solarData,
          borderColor: "#eab308",
          backgroundColor: "rgba(234, 179, 8, 0.1)",
          borderDash: [5, 5],
          fill: false,
          tension: 0.3,
          borderWidth: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            footer: () => "Analysis window: 16:00 to 20:00 (15-min intervals)"
          }
        }
      },
      scales: {
        y: {
          title: { display: true, text: "Power (kW)" },
          beginAtZero: true
        },
        x: {
          title: { display: true, text: "Interval Time (Campus Local)" }
        }
      }
    }
  });
}

async function loadDataQuality() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/dss/decisions", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const decisions = await res.json();

  const tbody = document.querySelector("#tableDQ tbody");
  tbody.innerHTML = "";

  decisions.forEach(d => {
    if (d.decision_code === "AUDIT_REGISTER" || d.decision_code === "RESOLVE_BOUNDARY" || d.severity === "CRITICAL") {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge badge-sev-${d.severity.toLowerCase()}">${d.severity}</span></td>
        <td><strong>${d.decision_code}</strong></td>
        <td>${d.building_name} (${d.meter_code})</td>
        <td>${d.rule_version}</td>
        <td>${d.short_explanation}</td>
        <td>${d.recommended_action}</td>
        <td>
          <button class="btn-why" onclick="window.dssExplanationPanel.loadDecisionExplanation(${d.id})">Why?</button>
        </td>
      `;
      tbody.appendChild(tr);
    }
  });

  if (tbody.children.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #059669;">Zero active data corruption flags in assigned buildings.</td></tr>`;
  }
}

async function loadDSSDecisions() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/dss/decisions", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const decisions = await res.json();

  const container = document.getElementById("dssDecisionsContainer");
  const expContainer = document.getElementById("explanationsListContainer");
  container.innerHTML = "";
  expContainer.innerHTML = "";

  decisions.forEach(d => {
    const card = document.createElement("div");
    card.className = `decision-card ${d.severity.toLowerCase()}`;
    card.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
        <span style="font-size: 0.82rem; font-weight: 700; color: #64748b;">${d.building_name} &bull; ${d.meter_code}</span>
        <div>
          <span class="badge badge-sev-${d.severity.toLowerCase()}">${d.severity}</span>
          <span class="badge badge-evi-${d.evidence_grade.toLowerCase()}">${d.evidence_grade}</span>
          <span class="badge badge-elig-${d.eligibility.toLowerCase().replace('_', '-')}">${d.eligibility}</span>
        </div>
      </div>
      <h4 style="font-size: 1.05rem; color: #0f172a; margin-bottom: 6px;">${d.decision_code}: ${d.recommended_action}</h4>
      <p style="font-size: 0.85rem; color: #475569; margin-bottom: 12px;">${d.short_explanation}</p>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-sm btn-secondary" onclick="window.dssExplanationPanel.loadDecisionExplanation(${d.id})">
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          Why this result? (13-Point Panel)
        </button>
        <button class="btn btn-sm btn-primary" onclick="openFeedbackForDecision(${d.id}, ${d.building_id}, '${d.decision_code}')">
          Submit Technical Feedback
        </button>
      </div>
    `;
    container.appendChild(card);

    // Explanations list item
    const expItem = document.createElement("div");
    expItem.style.padding = "12px";
    expItem.style.borderBottom = "1px solid #e2e8f0";
    expItem.style.display = "flex";
    expItem.style.alignItems = "center";
    expItem.style.justifyContent = "space-between";
    expItem.innerHTML = `
      <div>
        <strong>${d.building_name}</strong> &ndash; <code>${d.decision_code}</code> (${d.severity})
      </div>
      <button class="btn btn-sm btn-secondary" onclick="window.dssExplanationPanel.loadDecisionExplanation(${d.id})">Open Explanation</button>
    `;
    expContainer.appendChild(expItem);
  });
}

function openFeedbackForDecision(decId, buildingId, code) {
  document.querySelector('[data-section="sec-submit-fb"]').click();
  document.getElementById("fbBuildingSelect").value = buildingId;
  document.getElementById("fbObservation").value = `Investigated DSS decision ${code}. `;
}

document.getElementById("feedbackForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const token = localStorage.getItem("dss_token");

  const payload = {
    building_id: parseInt(document.getElementById("fbBuildingSelect").value),
    feedback_category: document.getElementById("fbCategorySelect").value,
    technical_observation: document.getElementById("fbObservation").value,
    explanation: document.getElementById("fbExplanation").value,
    supporting_evidence: document.getElementById("fbEvidence").value,
    suggested_correction: document.getElementById("fbCorrection").value
  };

  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Submission failed.");
    }
    alert("Technical field feedback successfully submitted to Management!");
    document.getElementById("feedbackForm").reset();
    document.querySelector('[data-section="sec-fb-history"]').click();
  } catch (err) {
    alert("Error: " + err.message);
  }
});

async function loadFeedbackHistory() {
  const token = localStorage.getItem("dss_token");
  const res = await fetch("/api/feedback", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  const feedbackList = await res.json();

  document.getElementById("mAwaitingFeedback").innerText = feedbackList.filter(f => f.status === "PENDING_REVIEW").length;

  const tbody = document.querySelector("#tableFeedbackHistory tbody");
  tbody.innerHTML = "";

  feedbackList.forEach(f => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${f.created_at.replace("T", " ").substring(0, 16)}</td>
      <td>Building #${f.building_id}</td>
      <td><span class="badge badge-sev-info">${f.feedback_category}</span></td>
      <td>${f.technical_observation}</td>
      <td>${f.suggested_correction || "None"}</td>
      <td><span class="badge badge-elig-${f.status.toLowerCase().replace('_', '-')}">${f.status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function logout() {
  localStorage.removeItem("dss_token");
  localStorage.removeItem("dss_user");
  window.location.href = "/login/electrician";
}

