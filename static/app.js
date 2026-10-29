/**
 * app.js — SATS Companion Offline-First Client
 *
 * Implements:
 * - JWT authentication & session management
 * - Persistent online/offline indicator (🟢 Online / Synced, 🟠 Offline / X Pending)
 * - Optimistic local mutations with localStorage sync queue
 * - Student listing, class attendance marking, and CSV import
 * - Automatic background synchronization when network is restored
 */

"use strict";

const API_BASE = "/api/v1";
const TOKEN_KEY = "sats_auth_token";
const TEACHER_KEY = "sats_teacher_data";
const OFFLINE_QUEUE_KEY = "sats_offline_queue";
const SYNC_INTERVAL_MS = 25000;

let authToken = localStorage.getItem(TOKEN_KEY) || null;
let currentTeacher = JSON.parse(localStorage.getItem(TEACHER_KEY) || "null");
let isOnline = navigator.onLine;
let syncPoller = null;

// ── Service Worker ──────────────────────────────────────────────────────────
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/sw.js").catch(() => {});
}

// ── Connectivity Listeners ──────────────────────────────────────────────────
window.addEventListener("online", () => {
  isOnline = true;
  updateSyncBadge();
  toast("🟢 Connection restored! Syncing pending records...", "success");
  syncNow(true);
});

window.addEventListener("offline", () => {
  isOnline = false;
  updateSyncBadge();
  toast("🟠 Running in Offline Mode — Changes queued locally.", "warning");
});

// ── Toast Notifications ────────────────────────────────────────────────────
function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 4000);
}

// ── API & Offline Queue Layer ──────────────────────────────────────────────
async function apiCall(method, path, body = null, isFormData = false) {
  const headers = {};
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  if (!isFormData && body) headers["Content-Type"] = "application/json";

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? (isFormData ? body : JSON.stringify(body)) : undefined,
    });

    if (res.status === 401) {
      logout();
      return null;
    }

    const data = await res.json();
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    // If offline and it's a mutation, enqueue locally
    if (["POST", "PUT", "DELETE"].includes(method) && !isFormData) {
      queueOfflineMutation(method, path, body);
      return { ok: true, offline: true, data: { message: "Saved locally (Offline Mode)" } };
    }
    return { ok: false, offline: true, error: err.message };
  }
}

function getLocalQueue() {
  try {
    return JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}

function queueOfflineMutation(method, path, body) {
  const queue = getLocalQueue();
  queue.push({
    id: (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString()),
    method,
    path,
    body,
    timestamp: new Date().toISOString()
  });
  localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
  updateSyncBadge();
}

async function flushOfflineQueue() {
  const queue = getLocalQueue();
  if (queue.length === 0) return 0;

  const remaining = [];
  let flushed = 0;

  for (const item of queue) {
    try {
      const res = await fetch(`${API_BASE}${item.path}`, {
        method: item.method,
        headers: {
          "Authorization": `Bearer ${authToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(item.body)
      });
      if (res.ok) flushed++;
      else remaining.push(item);
    } catch {
      remaining.push(item);
    }
  }

  localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(remaining));
  return flushed;
}

// ── Sync Engine Badge Status ───────────────────────────────────────────────
async function updateSyncBadge() {
  const badge = document.getElementById("sync-badge");
  if (!badge) return;

  const localQueueCount = getLocalQueue().length;

  if (!isOnline) {
    badge.className = "sync-badge offline";
    badge.textContent = `🟠 Offline / ${localQueueCount} Pending`;
    return;
  }

  if (!authToken) {
    badge.className = "sync-badge";
    badge.textContent = "⚪ Not Logged In";
    return;
  }

  try {
    const res = await apiCall("GET", "/sync/status");
    if (res && res.ok) {
      const { pending_count, conflict_count } = res.data;
      const totalPending = pending_count + localQueueCount;

      if (totalPending === 0 && conflict_count === 0) {
        badge.className = "sync-badge synced";
        badge.textContent = "🟢 Online / Synced";
      } else {
        badge.className = "sync-badge pending";
        badge.textContent = `🟠 Online / ${totalPending} Pending${conflict_count > 0 ? ` (${conflict_count} Conflicts)` : ""}`;
      }
    }
  } catch {
    badge.className = "sync-badge offline";
    badge.textContent = `🟠 Offline / ${localQueueCount} Pending`;
  }
}

async function syncNow(silent = false) {
  const flushedLocal = await flushOfflineQueue();
  if (authToken && isOnline) {
    const res = await apiCall("POST", "/sync/push", { force: false });
    if (res && res.ok && !silent) {
      const { synced, conflicts, errors } = res.data;
      toast(`✅ Sync complete: ${synced + flushedLocal} records synced, ${conflicts} conflicts.`, "success");
    }
  }
  updateSyncBadge();
}

// ── Auth & Navigation ──────────────────────────────────────────────────────
async function login(kgid, password) {
  const formData = new FormData();
  formData.append("username", kgid);
  formData.append("password", password);

  const res = await fetch(`${API_BASE}/auth/login`, { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Invalid KGID or password");
  }

  const data = await res.json();
  authToken = data.access_token;
  localStorage.setItem(TOKEN_KEY, authToken);

  // Fetch teacher profile
  const meRes = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${authToken}` }
  });
  if (meRes.ok) {
    const meData = await meRes.json();
    currentTeacher = meData.data;
    localStorage.setItem(TEACHER_KEY, JSON.stringify(currentTeacher));
  }
}

function logout() {
  authToken = null;
  currentTeacher = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TEACHER_KEY);
  showPage("login");
}

function showPage(page) {
  const appLayout = document.getElementById("app-layout");
  const loginPage = document.getElementById("page-login");

  if (page === "login") {
    if (appLayout) appLayout.style.display = "none";
    if (loginPage) { loginPage.style.display = "flex"; loginPage.classList.add("active"); }
    return;
  }

  if (loginPage) { loginPage.style.display = "none"; loginPage.classList.remove("active"); }
  if (appLayout) appLayout.style.display = "grid";

  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  const target = document.getElementById(`page-${page}`);
  if (target) target.classList.add("active");

  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
  const navItem = document.querySelector(`[data-page="${page}"]`);
  if (navItem) navItem.classList.add("active");

  if (page === "dashboard") loadDashboard();
  else if (page === "students") loadStudents();
  else if (page === "attendance") initAttendancePage();
  else if (page === "sync") loadSyncHistory();
}

// ── Dashboard ──────────────────────────────────────────────────────────────
async function loadDashboard() {
  const statsEl = document.getElementById("dashboard-stats");
  if (!statsEl || !authToken) return;

  statsEl.innerHTML = "<p class='loading'>Loading dashboard metrics...</p>";

  const [studentsRes, syncRes] = await Promise.all([
    apiCall("GET", "/students?limit=1"),
    apiCall("GET", "/sync/status"),
  ]);

  const totalStudents = studentsRes?.data?.data?.total || studentsRes?.data?.data?.students?.length || 0;
  const pendingCount = (syncRes?.data?.pending_count || 0) + getLocalQueue().length;
  const conflicts = syncRes?.data?.conflict_count || 0;
  const lastSync = syncRes?.data?.last_sync_at ? new Date(syncRes.data.last_sync_at).toLocaleTimeString() : "Never";

  statsEl.innerHTML = `
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon">👥</div>
        <div class="stat-value">${totalStudents}</div>
        <div class="stat-label">Students Tracked</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🟠</div>
        <div class="stat-value">${pendingCount}</div>
        <div class="stat-label">Records Pending Sync</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">⚠️</div>
        <div class="stat-value">${conflicts}</div>
        <div class="stat-label">Sync Conflicts</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🔄</div>
        <div class="stat-value stat-value--small">${lastSync}</div>
        <div class="stat-label">Last Sync Time</div>
      </div>
    </div>
    <div class="quick-actions">
      <h3>Quick Actions</h3>
      <button class="btn btn-primary" onclick="syncNow()">🔄 Sync Now</button>
      <button class="btn btn-secondary" onclick="showPage('attendance')">📋 Mark Attendance</button>
      <button class="btn btn-secondary" onclick="showPage('students')">👥 Student Roster</button>
      <button class="btn btn-secondary" onclick="showPage('import')">📤 Import CSV</button>
    </div>
  `;
}

// ── Students List ──────────────────────────────────────────────────────────
async function loadStudents(search = "") {
  const listEl = document.getElementById("student-list");
  if (!listEl) return;
  listEl.innerHTML = "<p class='loading'>Loading students...</p>";

  const params = new URLSearchParams({ limit: 50, ...(search && { name: search }) });
  const res = await apiCall("GET", `/students?${params}`);
  const students = res?.data?.data?.students || res?.data?.data || [];

  if (students.length === 0) {
    listEl.innerHTML = "<p class='empty'>No students found. Use 'CSV Import' or enroll students to start.</p>";
    return;
  }

  listEl.innerHTML = `
    <table class="data-table">
      <thead>
        <tr><th>SATS ID</th><th>Name</th><th>Class</th><th>Sec</th><th>Gender</th><th>Category</th><th>Status</th></tr>
      </thead>
      <tbody>
        ${students.map(s => `
          <tr>
            <td><code>${s.sats_id}</code></td>
            <td><strong>${s.name}</strong></td>
            <td>${s.current_class}</td>
            <td>${s.section || "-"}</td>
            <td>${s.gender}</td>
            <td><span class="badge badge-${s.caste_category}">${s.caste_category.toUpperCase()}</span></td>
            <td><span class="badge ${s.is_active ? 'badge-active' : 'badge-inactive'}">${s.is_active ? 'Active' : 'Withdrawn'}</span></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

// ── Attendance Page ────────────────────────────────────────────────────────
function initAttendancePage() {
  const dateInput = document.getElementById("attendance-date");
  if (dateInput) {
    dateInput.value = new Date().toISOString().split("T")[0];
  }
  loadAttendanceForm();
}

async function loadAttendanceForm() {
  const formEl = document.getElementById("attendance-form");
  const dateInput = document.getElementById("attendance-date");
  if (!formEl || !dateInput) return;

  const selectedDate = dateInput.value;
  formEl.innerHTML = "<p class='loading'>Loading class roster...</p>";

  const res = await apiCall("GET", "/students?limit=50");
  const students = res?.data?.data?.students || res?.data?.data || [];

  if (students.length === 0) {
    formEl.innerHTML = "<p class='empty'>No enrolled students found.</p>";
    return;
  }

  formEl.innerHTML = `
    <form onsubmit="submitAttendance(event, '${selectedDate}')">
      <table class="data-table">
        <thead><tr><th>SATS ID</th><th>Student Name</th><th>Class</th><th>Status</th></tr></thead>
        <tbody>
          ${students.map(s => `
            <tr>
              <td><code>${s.sats_id}</code></td>
              <td>${s.name}</td>
              <td>${s.current_class}</td>
              <td>
                <select name="att_${s.sats_id}" class="att-select">
                  <option value="present" selected>✅ Present</option>
                  <option value="absent">❌ Absent</option>
                  <option value="holiday">🏖️ Holiday</option>
                  <option value="half_day">½ Half Day</option>
                </select>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      <div class="form-actions" style="margin-top:16px;">
        <button type="submit" class="btn btn-primary">💾 Save Attendance for ${selectedDate}</button>
      </div>
    </form>
  `;
}

async function submitAttendance(e, attendanceDate) {
  e.preventDefault();
  const form = e.target;
  const selects = form.querySelectorAll(".att-select");
  const records = [];

  selects.forEach((sel) => {
    const satsId = sel.name.replace("att_", "");
    records.push({ student_sats_id: satsId, status: sel.value, attendance_date: attendanceDate });
  });

  const res = await apiCall("POST", "/attendance/bulk", { records, attendance_date: attendanceDate });
  if (res?.ok) {
    toast(`✅ Attendance recorded for ${records.length} students!`, "success");
    updateSyncBadge();
  } else {
    toast("Error saving attendance", "error");
  }
}

// ── CSV Import Handler ─────────────────────────────────────────────────────
async function handleCsvImport(type) {
  const input = document.getElementById(`${type}-csv-input`);
  const dryRun = document.getElementById(`${type}-dry-run`)?.checked || false;
  const resultEl = document.getElementById(`${type}-import-result`);

  if (!input?.files[0]) {
    toast("Please select a CSV file first.", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);

  resultEl.innerHTML = "<p class='loading'>Processing CSV file...</p>";
  const endpoint = type === "students" ? "/import/students/csv" : "/import/attendance/csv";

  try {
    const res = await fetch(`${API_BASE}${endpoint}?dry_run=${dryRun}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${authToken}` },
      body: formData,
    });
    const data = await res.json();
    const d = data.data || {};

    resultEl.innerHTML = `
      <div class="import-result import-result--${data.status === 'success' ? 'success' : 'warning'}">
        <h4>${data.message}</h4>
        <ul>
          ${d.created !== undefined ? `<li>✅ Created: <strong>${d.created}</strong></li>` : ""}
          ${d.updated !== undefined ? `<li>🔄 Updated: <strong>${d.updated}</strong></li>` : ""}
          ${d.skipped_duplicates !== undefined ? `<li>⏭️ Skipped: <strong>${d.skipped_duplicates}</strong></li>` : ""}
          ${d.failed !== undefined ? `<li>❌ Failed: <strong>${d.failed}</strong></li>` : ""}
        </ul>
      </div>
    `;
    updateSyncBadge();
  } catch (err) {
    resultEl.innerHTML = `<p class="error">Import error: ${err.message}</p>`;
  }
}

// ── Sync History ───────────────────────────────────────────────────────────
async function loadSyncHistory() {
  const histEl = document.getElementById("sync-history");
  if (!histEl) return;
  histEl.innerHTML = "<p class='loading'>Loading sync session logs...</p>";

  const res = await apiCall("GET", "/sync/history?limit=20");
  const logs = res?.data?.data || [];

  if (logs.length === 0) {
    histEl.innerHTML = "<p class='empty'>No sync sessions recorded yet.</p>";
    return;
  }

  histEl.innerHTML = `
    <table class="data-table">
      <thead>
        <tr><th>Session</th><th>Pushed</th><th>Conflicts</th><th>Duration</th><th>Status</th><th>Timestamp</th></tr>
      </thead>
      <tbody>
        ${logs.map(l => `
          <tr>
            <td><code>${l.session_id.slice(0, 8)}…</code></td>
            <td>${l.pushed}</td>
            <td>${l.conflicts}</td>
            <td>${l.duration_seconds || 0}s</td>
            <td><span class="badge ${l.success ? 'badge-active' : 'badge-inactive'}">${l.success ? 'OK' : 'Failed'}</span></td>
            <td>${l.started_at ? new Date(l.started_at).toLocaleString() : '-'}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

// ── App Init ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const kgid = document.getElementById("kgid").value;
      const pwd = document.getElementById("password").value;
      try {
        await login(kgid, pwd);
        toast("Welcome to SATS Companion", "success");
        showPage("dashboard");
        startSyncPolling();
      } catch (err) {
        toast(`Login Error: ${err.message}`, "error");
      }
    });
  }

  if (authToken) {
    showPage("dashboard");
    startSyncPolling();
  } else {
    showPage("login");
  }

  updateSyncBadge();
});

function startSyncPolling() {
  if (syncPoller) clearInterval(syncPoller);
  syncPoller = setInterval(updateSyncBadge, SYNC_INTERVAL_MS);
}
