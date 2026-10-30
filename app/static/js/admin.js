const token = localStorage.getItem("dss_token");
const pageError = document.getElementById("pageError");
const formMessage = document.getElementById("formMessage");
const directoryMessage = document.getElementById("directoryMessage");
const roleSelect = document.getElementById("role");
const allBuildingsInput = document.getElementById("allBuildings");
const buildingAccess = document.getElementById("buildingAccess");
const buildingPicker = document.getElementById("buildingPicker");
const buildingCodes = document.getElementById("buildingCodes");
const createAccountButton = document.getElementById("createAccountButton");
const initialPasswordPanel = document.getElementById("initialPasswordPanel");

function showMessage(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("admin-alert-error", isError);
  element.hidden = false;
}

function clearMessage(element) {
  element.textContent = "";
  element.hidden = true;
  element.classList.remove("admin-alert-error");
}

async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (options.body) headers.set("Content-Type", "application/json");

  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem("dss_token");
    localStorage.removeItem("dss_user");
    window.location.replace("/login/admin");
    throw new Error("Administrator access is required. Please sign in again.");
  }
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "The request could not be completed.";
    throw new Error(detail);
  }
  return data;
}

function updateAssignmentVisibility() {
  const isElectrician = roleSelect.value === "ELECTRICIAN";
  buildingAccess.hidden = !isElectrician;
  buildingPicker.hidden = !isElectrician || allBuildingsInput.checked;
  buildingCodes.required = isElectrician && !allBuildingsInput.checked;
}

async function loadBuildings() {
  const buildings = await apiRequest("/api/buildings");
  buildingCodes.replaceChildren();
  for (const building of buildings) {
    const option = document.createElement("option");
    option.value = building.code;
    option.textContent = `${building.name} (${building.code})`;
    buildingCodes.append(option);
  }
  if (buildings.length === 0) {
    allBuildingsInput.checked = false;
    buildingPicker.hidden = false;
    buildingCodes.disabled = true;
    showMessage(formMessage, "No buildings are available to assign.", true);
  }
}

function addCell(row, value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = value;
  if (className) cell.className = className;
  row.append(cell);
}

async function loadUsers() {
  const tbody = document.getElementById("userTableBody");
  const count = document.getElementById("accountCount");
  const refreshButton = document.getElementById("refreshUsersButton");
  clearMessage(directoryMessage);
  refreshButton.disabled = true;
  try {
    const users = await apiRequest("/api/auth/users");
    tbody.replaceChildren();
    count.textContent = String(users.length);
    if (users.length === 0) {
      showMessage(directoryMessage, "No accounts found.");
      return;
    }

    for (const user of users) {
      const row = document.createElement("tr");
      const identity = document.createElement("td");
      const name = document.createElement("strong");
      name.textContent = user.full_name;
      const username = document.createElement("span");
      username.className = "admin-table-secondary";
      username.textContent = user.username;
      identity.append(name, username);
      row.append(identity);

      addCell(row, user.role);
      const assignments = user.assigned_buildings || [];
      addCell(row, user.role === "ELECTRICIAN"
        ? assignments.length
          ? assignments.map(building => building.code).join(", ")
          : "None assigned"
        : "Campus-wide");
      const status = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = user.is_active ? "admin-status active" : "admin-status inactive";
      badge.textContent = user.is_active ? "Active" : "Inactive";
      status.append(badge);
      row.append(status);
      tbody.append(row);
    }
  } catch (error) {
    showMessage(directoryMessage, error.message, true);
  } finally {
    refreshButton.disabled = false;
  }
}

async function initializePortal() {
  if (!token) {
    window.location.replace("/login/admin");
    return;
  }

  try {
    const currentUser = await apiRequest("/api/auth/me");
    if (currentUser.role !== "ADMIN") {
      localStorage.removeItem("dss_token");
      localStorage.removeItem("dss_user");
      window.location.replace("/login/admin");
      return;
    }
    document.getElementById("adminIdentity").textContent = `${currentUser.full_name} · Administrator`;
    await Promise.all([loadBuildings(), loadUsers()]);
  } catch (error) {
    showMessage(pageError, error.message, true);
  }
}

roleSelect.addEventListener("change", updateAssignmentVisibility);
allBuildingsInput.addEventListener("change", updateAssignmentVisibility);
document.getElementById("refreshUsersButton").addEventListener("click", loadUsers);

document.getElementById("createAccountForm").addEventListener("submit", async event => {
  event.preventDefault();
  clearMessage(formMessage);
  clearMessage(pageError);
  initialPasswordPanel.hidden = true;
  createAccountButton.disabled = true;
  createAccountButton.textContent = "Creating account…";

  const payload = {
    full_name: document.getElementById("fullName").value.trim(),
    username: document.getElementById("username").value.trim(),
    email: document.getElementById("email").value.trim(),
    role: roleSelect.value
  };
  if (payload.role === "ELECTRICIAN") {
    payload.assign_all_buildings = allBuildingsInput.checked;
    payload.building_codes = allBuildingsInput.checked
      ? []
      : Array.from(buildingCodes.selectedOptions, option => option.value);
  }

  try {
    const created = await apiRequest("/api/auth/users", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    document.getElementById("initialPassword").value = created.initial_password;
    document.getElementById("copyMessage").textContent = "";
    initialPasswordPanel.hidden = false;
    showMessage(
      formMessage,
      `Created ${created.role.toLowerCase()} account "${created.username}"${created.assigned_buildings.length ? ` with access to ${created.assigned_buildings.length} buildings` : ""}.`
    );
    event.target.reset();
    allBuildingsInput.checked = true;
    roleSelect.value = "ELECTRICIAN";
    updateAssignmentVisibility();
    await loadUsers();
  } catch (error) {
    showMessage(formMessage, error.message, true);
  } finally {
    createAccountButton.disabled = false;
    createAccountButton.textContent = "Create account";
  }
});

document.getElementById("copyPasswordButton").addEventListener("click", async () => {
  const password = document.getElementById("initialPassword").value;
  try {
    await navigator.clipboard.writeText(password);
    document.getElementById("copyMessage").textContent = "Copied. Store and share the password securely.";
  } catch (error) {
    document.getElementById("copyMessage").textContent = "Clipboard access was blocked. Select and copy the password manually.";
  }
});

document.getElementById("logoutButton").addEventListener("click", async () => {
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
  } catch (error) {
    showMessage(pageError, `Sign-out could not be recorded: ${error.message}`, true);
  } finally {
    localStorage.removeItem("dss_token");
    localStorage.removeItem("dss_user");
    window.location.replace("/login/admin");
  }
});

updateAssignmentVisibility();
initializePortal();
