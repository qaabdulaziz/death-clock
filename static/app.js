const state = {
  settings: null,
  projects: [],
  projection: null,
  saveTimer: null,
  savePromise: null,
  resetting: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) { /* no JSON body */ }
    throw new Error(Array.isArray(message) ? message[0]?.msg || "Please check the fields." : message);
  }
  return response.status === 204 ? null : response.json();
}

function money(value) {
  const amount = Number(value || 0);
  const code = state.settings?.currency || "USD";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: code, maximumFractionDigits: 2 }).format(amount);
  } catch (_) {
    return `${code} ${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
}

function monthLabel(key, style = "long") {
  const [year, month] = key.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, { month: style, year: "numeric" }).format(new Date(year, month - 1, 1));
}

function monthDiff(fromDate, toDate) {
  return (toDate.getFullYear() - fromDate.getFullYear()) * 12 + toDate.getMonth() - fromDate.getMonth();
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("visible"), 2600);
}

async function loadData() {
  [state.settings, state.projects] = await Promise.all([api("/api/settings"), api("/api/projects")]);
  if (!state.settings.setup_complete) {
    showSetup();
    return;
  }
  await loadProjection();
  showMain();
}

async function loadProjection() {
  state.projection = await api("/api/projection");
}

function showSetup() {
  $("#main-view").hidden = true;
  $("#setup-view").hidden = false;
  const form = $("#setup-form");
  form.reset();
  for (const [name, value] of Object.entries(state.settings || {})) {
    if (form.elements[name]) form.elements[name].value = value ?? "";
  }
}

function showMain() {
  $("#setup-view").hidden = true;
  $("#main-view").hidden = false;
  fillSettingsForm();
  renderAll();
}

function fillSettingsForm() {
  const form = $("#settings-form");
  for (const [name, value] of Object.entries(state.settings)) {
    if (form.elements[name] && value !== null) form.elements[name].value = value;
  }
  const contribution = Number(state.settings.monthly_contribution);
  const contributionRange = $("#contribution-range");
  contributionRange.max = Math.max(1000, Math.ceil(contribution * 2 / 100) * 100);
  contributionRange.value = contribution;
  $("#return-range").value = state.settings.annual_return_rate;
  updateTactileOutputs();
}

function updateTactileOutputs() {
  const form = $("#settings-form");
  $("#contribution-output").textContent = money(form.elements.monthly_contribution.value);
  $("#return-output").textContent = `${Number(form.elements.annual_return_rate.value).toLocaleString()}%`;
}

function renderAll() {
  renderSummary();
  renderGrid();
  renderProjects();
}

function renderSummary() {
  const meta = state.projection.metadata;
  $("#header-summary").textContent = `${meta.months_remaining.toLocaleString()} months remain in the current assumption.`;
  $("#grid-summary").innerHTML = `
    <span><strong>${meta.current_age_years}y ${meta.current_age_months}m</strong> current age</span>
    <span><strong>${meta.months_lived.toLocaleString()}</strong> months lived</span>
    <span><strong>${meta.months_remaining.toLocaleString()}</strong> months remaining</span>`;
}

function renderGrid() {
  const meta = state.projection.metadata;
  const birth = new Date(`${meta.birth_date}T00:00:00`);
  const end = new Date(`${meta.end_date}T00:00:00`);
  const today = new Date();
  const currentKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const birthKey = `${birth.getFullYear()}-${String(birth.getMonth() + 1).padStart(2, "0")}`;
  const endKey = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}`;
  const starts = new Map();
  state.projection.projects.filter(project => project.start_month).forEach(project => {
    if (!starts.has(project.start_month)) starts.set(project.start_month, []);
    starts.get(project.start_month).push(project);
  });
  const balances = new Map(state.projection.balances.map(item => [item.month, item.balance]));
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const scroll = document.createElement("div");
  scroll.className = "grid-scroll";
  const header = document.createElement("div");
  header.className = "month-header";
  header.innerHTML = `<span>Year</span>${months.map(month => `<span>${month}</span>`).join("")}`;
  scroll.append(header);

  for (let year = birth.getFullYear(); year <= end.getFullYear(); year += 1) {
    const row = document.createElement("div");
    row.className = "year-row";
    row.innerHTML = `<span class="year-label">${year}</span>`;
    for (let month = 1; month <= 12; month += 1) {
      const key = `${year}-${String(month).padStart(2, "0")}`;
      const outside = key < birthKey || key >= endKey;
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "month-cell";
      if (outside) {
        cell.classList.add("outside");
        cell.disabled = true;
        cell.setAttribute("aria-hidden", "true");
      } else {
        const status = key === currentKey ? "current" : key < currentKey ? "lived" : "future";
        cell.classList.add(status);
        const projects = starts.get(key) || [];
        cell.setAttribute("aria-label", `${monthLabel(key)}${projects.length ? `, ${projects.length} project start` : ""}`);
        if (projects.length) {
          const marker = document.createElement("span");
          marker.className = `project-marker${projects.length > 1 ? " multiple" : ""}`;
          cell.append(marker);
        }
        cell.addEventListener("click", () => openMonth(key, birth, balances.get(key), projects, key < currentKey));
      }
      row.append(cell);
    }
    scroll.append(row);
  }
  const grid = $("#life-grid");
  grid.replaceChildren(scroll);
}

function openMonth(key, birth, balance, projects, isPast) {
  const [year, month] = key.split("-").map(Number);
  const point = new Date(year, month - 1, 1);
  const completedMonths = monthDiff(birth, point) - (point.getDate() < birth.getDate() ? 1 : 0);
  const ageMonths = Math.max(0, completedMonths);
  const ageYears = Math.floor(ageMonths / 12);
  const remainingMonths = ageMonths % 12;
  const projectMarkup = projects.length
    ? projects.map(project => `<div class="popover-project"><strong>${escapeHtml(project.name)}</strong><br>${money(project.cost)}</div>`).join("")
    : `<div class="popover-project">No project begins this month.</div>`;
  $("#month-popover-content").innerHTML = `
    <h3 class="popover-date">${monthLabel(key)}</h3>
    <div class="popover-meta">Age ${ageYears} years, ${remainingMonths} months · ${isPast ? "Past" : "Future"}</div>
    ${isPast || balance === undefined ? "" : `<div class="popover-balance"><small>Projected balance after project deductions</small><br><strong>${money(balance)}</strong></div>`}
    ${projectMarkup}`;
  $("#month-popover").showModal();
}

function renderProjects() {
  const container = $("#projects-list");
  if (!state.projects.length) {
    container.innerHTML = `<div class="empty-state"><strong>No projects yet.</strong><p>Add a first project to see when it becomes feasible.</p></div>`;
    return;
  }
  const computed = new Map(state.projection.projects.map(project => [project.id, project]));
  container.replaceChildren(...state.projects.map(project => {
    const timing = computed.get(project.id);
    const row = document.createElement("div");
    row.className = "project-row";
    row.dataset.id = project.id;
    const timingMarkup = timing?.start_month
      ? `<strong>${monthLabel(timing.start_month, "short")}</strong>Age ${timing.start_age_years}y ${timing.start_age_months}m · ${timing.months_away} months away`
      : `<strong>Not reachable</strong>Within projected lifetime`;
    row.innerHTML = `
      <input class="project-name" value="${escapeHtml(project.name)}" aria-label="Project name">
      <input class="project-cost" type="number" min="0" max="1000000000000000" step="0.01" value="${project.cost}" aria-label="Project cost">
      <div class="project-timing">${timingMarkup}</div>
      <div class="row-actions"><button class="icon-button save-project" type="button">Update</button><button class="icon-button delete-project" type="button">Delete</button></div>`;
    $(".save-project", row).addEventListener("click", () => updateProject(row));
    $(".delete-project", row).addEventListener("click", () => deleteProject(project.id));
    return row;
  }));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

async function refreshAfterChange() {
  [state.settings, state.projects] = await Promise.all([api("/api/settings"), api("/api/projects")]);
  await loadProjection();
  renderAll();
}

async function updateProject(row) {
  try {
    await api(`/api/projects/${row.dataset.id}`, {
      method: "PUT",
      body: JSON.stringify({ name: $(".project-name", row).value, cost: Number($(".project-cost", row).value) }),
    });
    await refreshAfterChange();
    showToast("Project updated");
  } catch (error) { showToast(error.message); }
}

async function deleteProject(id) {
  try {
    await api(`/api/projects/${id}`, { method: "DELETE" });
    await refreshAfterChange();
    showToast("Project deleted");
  } catch (error) { showToast(error.message); }
}

function collectSettingsPayload() {
  const form = $("#settings-form");
  const payload = Object.fromEntries(new FormData(form));
  for (const field of ["life_expectancy_years", "starting_balance", "monthly_contribution", "annual_return_rate"]) {
    payload[field] = Number(payload[field]);
  }
  return payload;
}

function scheduleSettingsSave() {
  if (state.resetting) return;
  clearTimeout(state.saveTimer);
  $("#save-status").textContent = "Saving…";
  $("#save-status").classList.add("saving");
  state.saveTimer = setTimeout(saveSettings, 350);
}

async function saveSettings() {
  if (state.resetting) return;
  const form = $("#settings-form");
  if (!form.checkValidity()) {
    $("#save-status").textContent = "Check value";
    return;
  }
  const serializedPayload = JSON.stringify(collectSettingsPayload());
  const previousSave = state.savePromise;
  const operation = (previousSave ? previousSave.catch(() => {}) : Promise.resolve()).then(async () => {
    if (state.resetting) return;
    state.settings = await api("/api/settings", {
      method: "PUT",
      body: serializedPayload,
    });
    await loadProjection();
    updateTactileOutputs();
    renderAll();
    $("#save-status").textContent = "Saved";
    $("#save-status").classList.remove("saving");
  });
  state.savePromise = operation;
  try {
    await operation;
  } catch (error) {
    $("#save-status").textContent = "Could not save";
    showToast(error.message);
  } finally {
    if (state.savePromise === operation) state.savePromise = null;
  }
}

$("#setup-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  for (const field of ["life_expectancy_years", "starting_balance", "monthly_contribution", "annual_return_rate"]) data[field] = Number(data[field]);
  data.setup_complete = true;
  try {
    state.settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(data) });
    state.projects = await api("/api/projects");
    await loadProjection();
    showMain();
  } catch (error) { $("#setup-error").textContent = error.message; }
});

$("#settings-form").addEventListener("input", event => {
  const input = event.target;
  if (!input.name) return;
  if (input.name === "monthly_contribution") $("#contribution-range").value = input.value;
  if (input.name === "annual_return_rate") $("#return-range").value = input.value;
  updateTactileOutputs();
  scheduleSettingsSave();
});

$("#contribution-range").addEventListener("input", event => {
  const input = $("#settings-form").elements.monthly_contribution;
  input.value = event.target.value;
  updateTactileOutputs();
  scheduleSettingsSave();
});
$("#return-range").addEventListener("input", event => {
  const input = $("#settings-form").elements.annual_return_rate;
  input.value = event.target.value;
  updateTactileOutputs();
  scheduleSettingsSave();
});

$("#add-project-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  data.cost = Number(data.cost);
  try {
    await api("/api/projects", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await refreshAfterChange();
    showToast("Project added");
  } catch (error) { showToast(error.message); }
});

$("#reset-data").addEventListener("click", async () => {
  if (!window.confirm("Reset settings and remove every project? This cannot be undone.")) return;
  state.resetting = true;
  clearTimeout(state.saveTimer);
  try {
    if (state.savePromise) {
      try { await state.savePromise; } catch (_) { /* reset still wins after a failed save */ }
    }
    state.settings = await api("/api/reset", { method: "POST" });
    state.projects = [];
    state.projection = null;
    showSetup();
    showToast("All local data reset");
  } catch (error) {
    showToast(error.message);
  } finally {
    state.resetting = false;
  }
});

$(".dialog-close").addEventListener("click", () => $("#month-popover").close());
$("#month-popover").addEventListener("click", event => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});

loadData().catch(error => {
  document.body.innerHTML = `<main class="setup-shell"><section class="setup-card"><h1>Death Clock</h1><p>${escapeHtml(error.message)}</p><p>Restart the server and refresh this page.</p></section></main>`;
});
