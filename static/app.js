/**
 * app.js — SATS Companion Karnataka School Micro-ERP Client
 *
 * Offline-first middleware client featuring:
 * - Bilingual UI engine (Kannada & English)
 * - Karnataka Government design system
 * - Optimistic offline mutations with local queueing & background sync
 * - Complete modules: Dashboard, Students, Attendance, Assessments (CCE), TC, CSV Import, Sync Audit
 */

"use strict";

const API_BASE = "/api/v1";
const TOKEN_KEY = "sats_auth_token";
const TEACHER_KEY = "sats_teacher_data";
const OFFLINE_QUEUE_KEY = "sats_offline_queue";
const LANG_KEY = "sats_lang";
const FONT_SCALE_KEY = "sats_font_scale";
const SYNC_INTERVAL_MS = 20000;

function getStoredToken() {
  const raw = localStorage.getItem(TOKEN_KEY);
  if (!raw || raw === "undefined" || raw === "null" || raw.length < 20) {
    return null;
  }
  return raw;
}

let authToken = getStoredToken();
let currentTeacher = JSON.parse(localStorage.getItem(TEACHER_KEY) || "null");
let currentLang = localStorage.getItem(LANG_KEY) || "kn";
let isOnline = navigator.onLine;
let syncPoller = null;
let cachedStudents = [];

// ── Bilingual Translation Dictionary ──────────────────────────────────────────
const I18N = {
  kn: {
    // Navigation
    nav_core: "ಮುಖ್ಯ ಕಾರ್ಯಗಳು",
    nav_dashboard: "ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
    nav_students: "ವಿದ್ಯಾರ್ಥಿಗಳ ಪಟ್ಟಿ",
    nav_attendance: "ದಿನನಿತ್ಯದ ಹಾಜರಾತಿ",
    nav_assessments: "ಮೌಲ್ಯಮಾಪನ / ಅಂಕಗಳು (CCE)",
    nav_bridge: "SATS ಅಂಕಗಳ ಸೇತು (Marks Bridge)",
    nav_tc: "ವರ್ಗಾವಣೆ ಪತ್ರ (TC)",
    nav_data: "ಮಾಹಿತಿ ಮತ್ತು ಸಿಂಕ್",
    nav_import: "ಸಿಎಸ್‌ವಿ ಆಮದು",
    nav_sync: "ಸಿಂಕ್ ಇತಿಹಾಸ",

    // Header & User
    logout_btn: "ನಿರ್ಗಮಿಸಿ",
    online_synced: "ಆನ್‌ಲೈನ್ / ಸಿಂಕ್ ಆಗಿದೆ",
    offline_pending: "ಆಫ್‌ಲೈನ್ / {n} ಬಾಕಿ",
    online_pending: "ಆನ್‌ಲೈನ್ / {n} ಬಾಕಿ",

    // Dashboard
    dash_title: "📊 ಶಾಲಾ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
    dash_subtitle: "ವಿದ್ಯಾರ್ಥಿಗಳ ದಾಖಲಾತಿ, ಹಾಜರಾತಿ ಮತ್ತು SATS ಸಿಂಕ್ರೊನೈಸೇಶನ್ ಸ್ಥಿತಿ",
    sync_now_btn: "ಈಗಲೇ ಸಿಂಕ್ ಮಾಡಿ",
    stat_students: "ದಾಖಲಾದ ಒಟ್ಟು ವಿದ್ಯಾರ್ಥಿಗಳು",
    stat_pending: "ಸಿಂಕ್ ಬಾಕಿ ಇರುವ ದಾಖಲೆಗಳು",
    stat_attendance: "ಹಾಜರಾತಿ ದಾಖಲೆಗಳು",
    stat_last_sync: "ಕೊನೆಯ ಸಿಂಕ್ ಸಮಯ",
    quick_actions: "⚡ ಶೀಘ್ರ ಕಾರ್ಯಾಚರಣೆಗಳು",
    qa_mark_att: "ಹಾಜರಾತಿ ನಮೂದಿಸಿ",
    qa_bridge: "SATS ಅಂಕಗಳ ಸೇತು (Marks Bridge)",
    qa_enroll: "ವಿದ್ಯಾರ್ಥಿ ಹೊಸ ನೋಂದಣಿ",
    qa_cce: "ಅಂಕಗಳನ್ನು ನಮೂದಿಸಿ (CCE)",
    qa_tc: "ವರ್ಗಾವಣೆ ಪತ್ರ (TC)",
    qa_import: "ಸಿಎಸ್‌ವಿ ಆಮದು",
    dash_recent_students: "📋 ಇತ್ತೀಚಿನ ವಿದ್ಯಾರ್ಥಿಗಳ ವಿವರ",
    view_all: "ಎಲ್ಲವನ್ನೂ ವೀಕ್ಷಿಸಿ",

    // SATS Marks Bridge
    bridge_title: "🌉 SATS ಅಂಕಗಳ ಸೇತು (Marks Bridge)",
    bridge_subtitle: "ಎಕ್ಸೆಲ್ (Excel), ಫೋಟೋ (Photo/Camera), ಅಥವಾ PDF ನಿಂದ ಅಂಕಗಳನ್ನು ಕ್ಷಣಾರ್ಧದಲ್ಲಿ ಕರ್ನಾಟಕ SATS/ನಿರಂತರ ಸ್ವರೂಪಕ್ಕೆ ಪರಿವರ್ತಿಸಿ!",
    bridge_motto_title: "ಮುಖ್ಯೋಪಾಧ್ಯಾಯರಿಗೆ ಸಹಾಯಕ ಸೇತು (Bridge for Headmasters):",
    bridge_motto_desc: "ಶಿಕ್ಷಕರು ನೀಡುವ ಯಾವುದೇ ನಮೂನೆಯ ಎಕ್ಸೆಲ್ ಶೀಟ್, ಮಾರ್ಕ್ಸ್ ರಿಜಿಸ್ಟರ್ ಫೋಟೋ ಅಥವಾ ಪಿಡಿಎಫ್ ಅನ್ನು ನೇರವಾಗಿ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ. ನಮ್ಮ ಸಿಸ್ಟಂ ಅದನ್ನು ಕರ್ನಾಟಕ SATS CCE ಸ್ವರೂಪಕ್ಕೆ ಹೊಂದಿಸುತ್ತದೆ. ನೀವು ಒಬ್ಬೊಬ್ಬ ವಿದ್ಯಾರ್ಥಿಯ ಅಂಕಗಳನ್ನು ಗಂಟೆಗಟ್ಟಲೆ ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿ ಟೈಪ್ ಮಾಡುವ ಅಗತ್ಯವಿಲ್ಲ!",
    bridge_upload_heading: "📤 ಅಂಕಪಟ್ಟಿ ಅಪ್‌ಲೋಡ್ (Upload Score Sheet)",
    bridge_file_label: "ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ (Select File or Capture Photo) *",
    bridge_extract_btn: "ಡೇಟಾ ಹೊರತೆಗೆದು SATS ಗೆ ಜೋಡಿಸಿ (Extract & Bridge)",
    bridge_demo_btn: "ಮಾದರಿ ಡೇಟಾ ಪರಿಶೀಲಿಸಿ (Load Demo Sample)",
    bridge_review_heading: "📋 ಹೊರತೆಗೆದ ಅಂಕಗಳ ಪರಿಶೀಲನೆ (Review & Verify Before SATS Upload)",
    bridge_action_hint: "ಖಚಿತಪಡಿಸಿಕೊಂಡ ನಂತರ SATS ಗೆ ಬ್ಯಾಚ್ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ ಅಥವಾ ನಿರಂತರ CSV ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ.",
    bridge_save_sats: "SATS ಗೆ ಬ್ಯಾಚ್ ಸೇವ್ ಮಾಡಿ (Batch Save)",
    bridge_download_csv: "ಅಧಿಕೃತ SATS/ನಿರಂತರ CSV ಡೌನ್‌ಲೋಡ್",

    // Students
    students_title: "👥 ವಿದ್ಯಾರ್ಥಿ ನಾಮಾವಳಿ",
    students_subtitle: "ಕರ್ನಾಟಕ SATS ID, ವರ್ಗ ಮತ್ತು ಜಾತಿ ವರ್ಗಾವಾರು ಶಾಲಾ ವಿದ್ಯಾರ್ಥಿ ಪಟ್ಟಿ",
    enroll_student_btn: "ಹೊಸ ವಿದ್ಯಾರ್ಥಿ ಸೇರಿಸಿ",
    search_label: "ಹುಡುಕಿ (ಹೆಸರು ಅಥವಾ SATS ID)",
    filter_class: "ತರಗತಿ",
    filter_gender: "ಲಿಂಗ",
    search_btn: "ಶೋಧಿಸಿ",
    col_sats_id: "SATS ID",
    col_name: "ವಿದ್ಯಾರ್ಥಿ ಹೆಸರು",
    col_class: "ತರಗತಿ",
    col_sec: "ವಿಭಾಗ",
    col_gender: "ಲಿಂಗ",
    col_category: "ಜಾತಿ ವರ್ಗ",
    col_status: "ಸ್ಥಿತಿ",
    col_actions: "ಕ್ರಮ",
    status_active: "ಸಕ್ರಿಯ",
    status_withdrawn: "ಬಿಟ್ಟಿದ್ದಾರೆ",
    withdraw_btn: "ಶಾಲೆ ಬಿಡಿಸಿ",

    // Attendance
    att_title: "📋 ದಿನನಿತ್ಯದ ಹಾಜರಾತಿ",
    att_subtitle: "ಆಫ್‌ಲೈನ್ ಅಥವಾ ಆನ್‌ಲೈನ್‌ನಲ್ಲಿ ತರಗತಿವಾರು ಹಾಜರಾತಿ ನಮೂದಿಸಿ SATS ಗೇಟ್‌ವೇಗೆ ಸಿಂಕ್ ಮಾಡಿ",
    att_date_label: "ದಿನಾಂಕ:",
    att_class_label: "ತರಗತಿ:",
    mark_all_present: "ಎಲ್ಲರೂ ಹಾಜರು",
    refresh_btn: "ಮರುಲೋಡ್",
    att_save_btn: "💾 ಹಾಜರಾತಿಯನ್ನು ಉಳಿಸಿ",
    opt_present: "✅ ಹಾಜರು",
    opt_absent: "❌ ಗೈರುಹಾಜರು",
    opt_holiday: "🏖️ ರಜೆ",
    opt_half_day: "½ ಅರ್ಧ ದಿನ",

    // Assessments
    cce_title: "📝 ಮೌಲ್ಯಮಾಪನ ಮತ್ತು ಅಂಕಗಳ ನಮೂದು (CCE)",
    cce_subtitle: "ರೂಪಣಾತ್ಮಕ (FA1/FA2) ಮತ್ತು ಸಂಕಲನಾತ್ಮಕ (SA1/SA2) ಮೌಲ್ಯಮಾಪನ ಅಂಕಗಳು",
    add_marks_btn: "ಹೊಸ ಅಂಕಗಳನ್ನು ನಮೂದಿಸಿ",
    cce_records_heading: "📊 ಇತ್ತೀಚಿನ ಪರೀಕ್ಷಾ ಮೌಲ್ಯಮಾಪನಗಳು",
    col_subject: "ವಿಷಯ",
    col_exam_type: "ಪರೀಕ್ಷೆ",
    col_marks_obtained: "ಪಡೆದ ಅಂಕಗಳು",
    col_max_marks: "ಗರಿಷ್ಠ ಅಂಕ",
    col_percentage: "ಶೇಕಡಾ",
    col_date: "ದಿನಾಂಕ",

    // TC
    tc_title: "📜 ವರ್ಗಾವಣೆ ಪ್ರಮಾಣಪತ್ರ ನಿರ್ವಹಣೆ (TC)",
    tc_subtitle: "ವಿದ್ಯಾರ್ಥಿ ಶಾಲೆ ಬಿಡುವಿಕೆ ಮತ್ತು ವರ್ಗಾವಣೆ ಪ್ರಮಾಣಪತ್ರ (TC) ಅನುಮೋದನೆ ಪ್ರಕ್ರಿಯೆ",
    request_tc_btn: "ಹೊಸ TC ಕೋರಿಕೆ",
    tc_table_heading: "📋 TC ಕೋರಿಕೆಗಳ ಸ್ಥಿತಿ",
    col_tc_num: "TC ಸಂಖ್ಯೆ",
    col_reason: "ಕಾರಣ",
    col_req_date: "ಕೋರಿಕೆಯ ದಿನಾಂಕ",
    approve_btn: "ಅನುಮೋದಿಸಿ (Approve)",

    // CSV Import
    import_title: "📤 ಸಿಎಸ್‌ವಿ ಬ್ಯಾಚ್ ಆಮದು",
    import_subtitle: "ಹೊರಗಿನ ದಾಖಲೆಗಳಿಂದ ವಿದ್ಯಾರ್ಥಿಗಳ ಪಟ್ಟಿ ಅಥವಾ ಹಾಜರಾತಿ ಫೈಲ್ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ",
    import_students_title: "ವಿದ್ಯಾರ್ಥಿ ಪಟ್ಟಿ ಆಮದು",
    import_students_desc: "SATS ID, ಹೆಸರು, ತರಗತಿ, ವಿಭಾಗ, ಲಿಂಗ, ಜಾತಿ ವರ್ಗ ಹೊಂದಿರುವ CSV ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ.",
    import_att_title: "ಹಾಜರಾತಿ ಆಮದು",
    import_att_desc: "ದಿನಾಂಕ, SATS ID ಮತ್ತು ಹಾಜರಾತಿ ಸ್ಥಿತಿ ಹೊಂದಿರುವ CSV ಫೈಲ್ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ.",
    dry_run_label: "ಪೂರ್ವಪರೀಕ್ಷೆ ಮಾತ್ರ (Validate only / Dry run)",
    upload_btn: "ಅಪ್‌ಲೋಡ್ ಮಾಡಿ",
    download_sample: "ಮಾದರಿ CSV ಡೌನ್‌ಲೋಡ್",

    // Sync
    sync_title: "🔄 ಸಿಂಕ್ರೊನೈಸೇಶನ್ ಪರಿಶೀಲನೆ ಲಾಗ್",
    sync_subtitle: "ಆಫ್‌ಲೈನ್‌ನಿಂದ ಕೇಂದ್ರ SATS ಪೋರ್ಟಲ್‌ಗೆ ರವಾನೆಯಾದ ವಹಿವಾಟುಗಳು ಮತ್ತು ದೃಢೀಕರಣಗಳು",
    sync_log_heading: "📋 ಸಿಂಕ್ ಅವಧಿಗಳ ಇತಿಹಾಸ",
    col_session: "ಅಧಿವೇಶನ ID",
    col_pushed: "ರವಾನಿಸಿದ ದಾಖಲೆ",
    col_conflicts: "ವ್ಯತ್ಯಾಸಗಳು",
    col_duration: "ಸಮಯ",

    // Login
    login_kgid_label: "ಕೆ.ಜಿ.ಐ.ಡಿ ಸಂಖ್ಯೆ / KGID (Employee ID)",
    login_pass_label: "ಗುಪ್ತಪದ / Password",
    login_btn: "ಪ್ರವೇಶಿಸಿ (Sign In)",
  },

  en: {
    // Navigation
    nav_core: "Core Modules",
    nav_dashboard: "Dashboard",
    nav_students: "Student Roster",
    nav_attendance: "Daily Attendance",
    nav_assessments: "CCE Assessments",
    nav_bridge: "SATS Marks Bridge",
    nav_tc: "Transfer Certificate (TC)",
    nav_data: "Data & Sync",
    nav_import: "CSV Import",
    nav_sync: "Sync Audit",

    // Header & User
    logout_btn: "Logout",
    online_synced: "Online / Synced",
    offline_pending: "Offline / {n} Pending",
    online_pending: "Online / {n} Pending",

    // Dashboard
    dash_title: "📊 School Dashboard",
    dash_subtitle: "Student enrollment, daily attendance, and SATS synchronization status",
    sync_now_btn: "Sync Now",
    stat_students: "Total Enrolled Students",
    stat_pending: "Records Pending Sync",
    stat_attendance: "Attendance Records",
    stat_last_sync: "Last Sync Time",
    quick_actions: "⚡ Quick Actions",
    qa_mark_att: "Mark Attendance",
    qa_bridge: "SATS Marks Bridge (Universal Ingest)",
    qa_enroll: "Enroll Student",
    qa_cce: "Record Marks (CCE)",
    qa_tc: "Transfer Certificate",
    qa_import: "Import CSV",
    dash_recent_students: "📋 Student Roster Overview",
    view_all: "View All",

    // SATS Marks Bridge
    bridge_title: "🌉 SATS Marks Bridge (Universal Format Ingestor)",
    bridge_subtitle: "Convert marks from Excel, Photo register, or PDF to Karnataka SATS/Nirantara format in seconds!",
    bridge_motto_title: "Helping Bridge for Headmasters:",
    bridge_motto_desc: "Upload any Excel file, notebook photo, or PDF marks sheet provided by teachers. The system standardizes it to Karnataka SATS CCE format, eliminating hours of repetitive manual data entry.",
    bridge_upload_heading: "📤 Upload Score Sheet",
    bridge_file_label: "Select File or Capture Photo *",
    bridge_extract_btn: "Extract & Bridge to SATS",
    bridge_demo_btn: "Load Demo Sample",
    bridge_review_heading: "📋 Review & Verify Before SATS Upload",
    bridge_action_hint: "Verify entries, then batch-upload to SATS or download official Nirantara CSV.",
    bridge_save_sats: "Batch Save to SATS",
    bridge_download_csv: "Download Official SATS CSV",

    // Students
    students_title: "👥 Student Roster",
    students_subtitle: "School student directory indexed by Karnataka SATS ID and Class",
    enroll_student_btn: "Enroll New Student",
    search_label: "Search (Name or SATS ID)",
    filter_class: "Class",
    filter_gender: "Gender",
    search_btn: "Search",
    col_sats_id: "SATS ID",
    col_name: "Student Name",
    col_class: "Class",
    col_sec: "Section",
    col_gender: "Gender",
    col_category: "Category",
    col_status: "Status",
    col_actions: "Action",
    status_active: "Active",
    status_withdrawn: "Withdrawn",
    withdraw_btn: "Withdraw",

    // Attendance
    att_title: "📋 Daily Student Attendance",
    att_subtitle: "Record student attendance offline or online and sync to central SATS gateway",
    att_date_label: "Date:",
    att_class_label: "Class:",
    mark_all_present: "Mark All Present",
    refresh_btn: "Refresh",
    att_save_btn: "💾 Save Attendance",
    opt_present: "✅ Present",
    opt_absent: "❌ Absent",
    opt_holiday: "🏖️ Holiday",
    opt_half_day: "½ Half Day",

    // Assessments
    cce_title: "📝 Continuous & Comprehensive Evaluation (CCE)",
    cce_subtitle: "Formative (FA1/FA2) and Summative (SA1/SA2) assessment marks",
    add_marks_btn: "Enter Student Marks",
    cce_records_heading: "📊 Recent Assessment Records",
    col_subject: "Subject",
    col_exam_type: "Exam Type",
    col_marks_obtained: "Marks Obtained",
    col_max_marks: "Max Marks",
    col_percentage: "Percentage",
    col_date: "Date",

    // TC
    tc_title: "📜 Transfer Certificate Management",
    tc_subtitle: "Student school leaving and official Transfer Certificate (TC) approvals",
    request_tc_btn: "Request New TC",
    tc_table_heading: "📋 TC Applications & Approvals",
    col_tc_num: "TC Number",
    col_reason: "Reason",
    col_req_date: "Request Date",
    approve_btn: "Approve TC",

    // CSV Import
    import_title: "📤 CSV Bulk Import",
    import_subtitle: "Bulk upload student roster or daily attendance exported from databases",
    import_students_title: "Import Students CSV",
    import_students_desc: "Select a CSV file containing SATS ID, name, class, section, gender, caste category.",
    import_att_title: "Import Attendance CSV",
    import_att_desc: "Upload a CSV file containing attendance date, SATS ID, and status.",
    dry_run_label: "Validate only (Dry run)",
    upload_btn: "Upload CSV",
    download_sample: "Download Sample CSV",

    // Sync
    sync_title: "🔄 Synchronization Audit Log",
    sync_subtitle: "Audit trails of offline mutations synchronized to central SATS gateway",
    sync_log_heading: "📋 Recent Sync Sessions",
    col_session: "Session ID",
    col_pushed: "Pushed",
    col_conflicts: "Conflicts",
    col_duration: "Duration",

    // Login
    login_kgid_label: "KGID / Employee ID",
    login_pass_label: "Password",
    login_btn: "Sign In",
  }
};

function t(key, fallback = "") {
  return I18N[currentLang]?.[key] || I18N["en"]?.[key] || fallback || key;
}

function setLanguage(lang) {
  currentLang = lang;
  localStorage.setItem(LANG_KEY, lang);

  document.querySelectorAll(".lang-btn").forEach((btn) => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`lang-btn-${lang}`);
  if (activeBtn) activeBtn.classList.add("active");

  applyLanguage();
  updateSyncBadge();

  // Re-render active view if logged in
  if (authToken) {
    const activePage = document.querySelector(".page.active");
    if (activePage) {
      const pageId = activePage.id.replace("page-", "");
      showPage(pageId);
    }
  }
}

function applyLanguage() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key && I18N[currentLang]?.[key]) {
      el.textContent = I18N[currentLang][key];
    }
  });

  const knBtn = document.getElementById("lang-btn-kn");
  const enBtn = document.getElementById("lang-btn-en");
  if (knBtn && enBtn) {
    knBtn.classList.toggle("active", currentLang === "kn");
    enBtn.classList.toggle("active", currentLang === "en");
  }

  // Update document title
  document.title = currentLang === "kn"
    ? "SATS Companion | ಕರ್ನಾಟಕ ಸರ್ಕಾರ - ಶಾಲಾ ಮೈಕ್ರೋ-ಇಆರ್‌ಪಿ"
    : "SATS Companion | Government of Karnataka - School Micro-ERP";
}

// ── Font Scale Accessibility Controls ──────────────────────────────────────────
function adjustFontSize(delta) {
  let scale = parseFloat(localStorage.getItem(FONT_SCALE_KEY) || "1");
  scale = Math.min(Math.max(scale + delta, 0.85), 1.35);
  localStorage.setItem(FONT_SCALE_KEY, scale.toFixed(2));
  document.documentElement.style.setProperty("--font-scale", scale.toFixed(2));
}

function resetFontSize() {
  localStorage.setItem(FONT_SCALE_KEY, "1");
  document.documentElement.style.setProperty("--font-scale", "1");
}

// ── Service Worker Registration ───────────────────────────────────────────────
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/sw.js").catch(() => {});
}

// ── Connectivity Listeners ────────────────────────────────────────────────────
window.addEventListener("online", () => {
  isOnline = true;
  document.getElementById("offline-banner")?.classList.remove("active");
  updateSyncBadge();
  toast(currentLang === "kn" ? "🟢 ಇಂಟರ್ನೆಟ್ ಸಂಪರ್ಕ ಮರುಸ್ಥಾಪನೆಯಾಗಿದೆ! ಬಾಕಿ ದಾಖಲೆಗಳನ್ನು ಸಿಂಕ್ ಮಾಡಲಾಗುತ್ತಿದೆ..." : "🟢 Connection restored! Syncing pending mutations...", "success");
  syncNow(true);
});

window.addEventListener("offline", () => {
  isOnline = false;
  document.getElementById("offline-banner")?.classList.add("active");
  updateSyncBadge();
  toast(currentLang === "kn" ? "🟠 ಆಫ್‌ಲೈನ್ ಮೋಡ್ ಸಕ್ರಿಯವಾಗಿದೆ. ನಮೂದುಗಳು ಸ್ಥಳೀಯವಾಗಿ ಸಂಗ್ರಹವಾಗುತ್ತವೆ." : "🟠 Offline mode active. Mutations stored locally.", "warning");
});

// ── Toast Notification Engine ─────────────────────────────────────────────────
function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const el = document.createElement("div");
  el.className = `gov-toast ${type}`;
  const icon = type === "success" ? "✅" : type === "warning" ? "⚠️" : type === "error" ? "❌" : "ℹ️";
  el.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
  container.appendChild(el);

  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 4500);
}

// ── API & Offline Mutation Layer ──────────────────────────────────────────────
async function apiCall(method, path, body = null, isFormData = false) {
  const headers = {};
  authToken = getStoredToken();
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  if (!isFormData && body) headers["Content-Type"] = "application/json";

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? (isFormData ? body : JSON.stringify(body)) : undefined,
    });

    if (res.status === 401) {
      console.warn("401 Unauthorized encountered on:", path);
      if (authToken) {
        logout();
        toast(
          currentLang === "kn"
            ? "ಅಧಿವೇಶನದ ಅವಧಿ ಮುಗಿದಿದೆ, ದಯವಿಟ್ಟು ಪುನಃ ಪ್ರವೇಶಿಸಿ."
            : "Session expired or invalid credentials. Please sign in again.",
          "warning"
        );
      }
      return null;
    }

    const data = await res.json();
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    if (["POST", "PUT", "DELETE"].includes(method) && !isFormData) {
      queueOfflineMutation(method, path, body);
      return {
        ok: true,
        offline: true,
        data: {
          status: "success",
          message: currentLang === "kn" ? "ಸ್ಥಳೀಯವಾಗಿ ಉಳಿಸಲಾಗಿದೆ (ಆಫ್‌ಲೈನ್)" : "Saved locally (Offline Mode)",
          data: {}
        }
      };
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

// ── Sync Engine Badge & Trigger ───────────────────────────────────────────────
async function updateSyncBadge() {
  const badge = document.getElementById("sync-badge");
  const indicator = document.getElementById("sync-indicator");
  const text = document.getElementById("sync-text");
  if (!badge || !text) return;

  const localQueueCount = getLocalQueue().length;

  if (!isOnline) {
    badge.className = "sync-badge offline";
    if (indicator) indicator.textContent = "🟠";
    text.textContent = t("offline_pending").replace("{n}", localQueueCount);
    return;
  }

  if (!authToken) {
    badge.className = "sync-badge";
    if (indicator) indicator.textContent = "⚪";
    text.textContent = "Not Logged In";
    return;
  }

  try {
    const res = await apiCall("GET", "/sync/status");
    if (res && res.ok) {
      const pendingCount = res.data?.data?.pending_count || 0;
      const conflictCount = res.data?.data?.conflict_count || 0;
      const totalPending = pendingCount + localQueueCount;

      if (totalPending === 0 && conflictCount === 0) {
        badge.className = "sync-badge synced";
        if (indicator) indicator.textContent = "🟢";
        text.textContent = t("online_synced");
      } else {
        badge.className = "sync-badge pending";
        if (indicator) indicator.textContent = "🟠";
        text.textContent = t("online_pending").replace("{n}", totalPending);
      }
    }
  } catch {
    badge.className = "sync-badge offline";
    if (indicator) indicator.textContent = "🟠";
    text.textContent = t("offline_pending").replace("{n}", localQueueCount);
  }
}

async function syncNow(silent = false) {
  const flushedLocal = await flushOfflineQueue();
  if (authToken && isOnline) {
    const res = await apiCall("POST", "/sync/push", { force: false });
    if (res && res.ok && !silent) {
      const synced = res.data?.data?.synced || 0;
      const conflicts = res.data?.data?.conflicts || 0;
      const total = synced + flushedLocal;
      toast(
        currentLang === "kn"
          ? `✅ ಸಿಂಕ್ ಪೂರ್ಣಗೊಂಡಿದೆ: ${total} ದಾಖಲೆಗಳು ರವಾನೆಯಾಗಿವೆ, ${conflicts} ವ್ಯತ್ಯಾಸಗಳು.`
          : `✅ Sync complete: ${total} records synced, ${conflicts} conflicts.`,
        "success"
      );
    }
  }
  updateSyncBadge();
  loadDashboardMetrics();
}

// ── Auth & Navigation ─────────────────────────────────────────────────────────
async function login(kgid, password) {
  const formData = new FormData();
  formData.append("username", kgid);
  formData.append("password", password);

  const res = await fetch(`${API_BASE}/auth/login`, { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Invalid KGID or password");
  }

  const envelope = await res.json();
  const token = envelope.data?.access_token || envelope.access_token;
  if (!token) throw new Error("Could not retrieve access token");

  authToken = token;
  localStorage.setItem(TOKEN_KEY, authToken);

  currentTeacher = envelope.data || {};
  localStorage.setItem(TEACHER_KEY, JSON.stringify(currentTeacher));
  updateTeacherUI();
}

function logout() {
  authToken = null;
  currentTeacher = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TEACHER_KEY);
  showPage("login");
}

function updateTeacherUI() {
  if (!currentTeacher) return;
  const nameEl = document.getElementById("user-name");
  const desigEl = document.getElementById("user-designation");
  const initEl = document.getElementById("user-initials");

  if (nameEl) nameEl.textContent = currentTeacher.name || currentTeacher.kgid || "Teacher";
  if (desigEl) {
    const isHm = currentTeacher.is_admin || currentTeacher.designation === "headmaster";
    desigEl.textContent = isHm
      ? (currentLang === "kn" ? "ಮುಖ್ಯೋಪಾಧ್ಯಾಯರು (HM)" : "Headmaster")
      : (currentLang === "kn" ? "ಸಹ ಶಿಕ್ಷಕರು (Teacher)" : "Assistant Teacher");
  }
  if (initEl && currentTeacher.name) {
    initEl.textContent = currentTeacher.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
  }
}

function showPage(page, event = null) {
  if (event && event.preventDefault) event.preventDefault();
  if (!page) return;

  const appShell = document.getElementById("app-shell");
  const loginPage = document.getElementById("page-login");

  if (page === "login") {
    if (appShell) appShell.style.display = "none";
    if (loginPage) { loginPage.style.display = "flex"; loginPage.classList.add("active"); }
    return;
  }

  if (loginPage) { loginPage.style.display = "none"; loginPage.classList.remove("active"); }
  if (appShell) appShell.style.display = "block";

  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  const target = document.getElementById(`page-${page}`);
  if (target) target.classList.add("active");

  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
  const navItem = document.querySelector(`[data-page="${page}"]`);
  if (navItem) navItem.classList.add("active");

  applyLanguage();
  updateTeacherUI();

  // Load modules
  if (page === "dashboard") loadDashboardMetrics();
  else if (page === "students") loadStudentsRoster();
  else if (page === "attendance") initAttendancePage();
  else if (page === "assessments") loadAssessmentsModule();
  else if (page === "bridge") initBridgePage();
  else if (page === "tc") loadTCModule();
  else if (page === "sync") loadSyncHistory();
}

// ── Modal Helpers ─────────────────────────────────────────────────────────────
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add("active");
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove("active");
}

// ── 1. Dashboard Module ───────────────────────────────────────────────────────
async function loadDashboardMetrics() {
  const [studentsRes, syncRes, attRes] = await Promise.all([
    apiCall("GET", "/students?limit=5"),
    apiCall("GET", "/sync/status"),
    apiCall("GET", "/attendance/report?limit=1"),
  ]);

  const totalStudents = studentsRes?.data?.data?.total || cachedStudents.length || 0;
  const pendingCount = (syncRes?.data?.data?.pending_count || 0) + getLocalQueue().length;
  const lastSyncAt = syncRes?.data?.data?.last_sync_at;
  const lastSyncText = lastSyncAt ? new Date(lastSyncAt).toLocaleTimeString() : (currentLang === "kn" ? "ಸಿಂಕ್ ಆಗಿಲ್ಲ" : "Never");

  const statTotalEl = document.getElementById("stat-total-students");
  const statPendingEl = document.getElementById("stat-pending-sync");
  const statAttEl = document.getElementById("stat-today-att");
  const statSyncEl = document.getElementById("stat-last-sync");

  if (statTotalEl) statTotalEl.textContent = totalStudents;
  if (statPendingEl) statPendingEl.textContent = pendingCount;
  if (statAttEl) {
    const totalAtt = attRes?.data?.data?.total || 0;
    statAttEl.textContent = `${totalAtt} ದಾಖಲೆ`;
  }
  if (statSyncEl) statSyncEl.textContent = lastSyncText;

  // Mini students preview
  const recentTable = document.getElementById("dash-recent-students-table");
  if (recentTable) {
    const students = studentsRes?.data?.data?.students || [];
    if (students.length === 0) {
      recentTable.innerHTML = `<div class="empty-state">${currentLang === "kn" ? "ವಿದ್ಯಾರ್ಥಿ ವಿವರ ಲಭ್ಯವಿಲ್ಲ." : "No student records found."}</div>`;
    } else {
      recentTable.innerHTML = `
        <table class="gov-table">
          <thead>
            <tr>
              <th>${t("col_sats_id")}</th>
              <th>${t("col_name")}</th>
              <th>${t("col_class")}</th>
              <th>${t("col_gender")}</th>
              <th>${t("col_category")}</th>
              <th>${t("col_status")}</th>
            </tr>
          </thead>
          <tbody>
            ${students.map(s => `
              <tr>
                <td><code>${s.sats_id}</code></td>
                <td><strong>${s.name}</strong></td>
                <td>ತರಗತಿ ${s.current_class}-${s.section || 'A'}</td>
                <td>${s.gender === 'male' ? 'ಗಂಡು (M)' : 'ಹೆಣ್ಣು (F)'}</td>
                <td><span class="gov-badge badge-info">${(s.caste_category || 'general').toUpperCase()}</span></td>
                <td><span class="gov-badge ${s.is_active ? 'badge-success' : 'badge-danger'}">${s.is_active ? t("status_active") : t("status_withdrawn")}</span></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }
  }
}

// ── 2. Students Module ────────────────────────────────────────────────────────
async function loadStudentsRoster(searchTerm = "") {
  const container = document.getElementById("student-list-container");
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><div class="icon">⏳</div>${currentLang === "kn" ? "ವಿದ್ಯಾರ್ಥಿಗಳ ಪಟ್ಟಿ ಲೋಡ್ ಆಗುತ್ತಿದೆ..." : "Loading student roster..."}</div>`;

  const classFilter = document.getElementById("student-class-filter")?.value || "";
  const genderFilter = document.getElementById("student-gender-filter")?.value || "";

  const params = new URLSearchParams({ limit: 100 });
  if (searchTerm) params.append("search", searchTerm);
  if (classFilter) params.append("current_class", classFilter);
  if (genderFilter) params.append("gender", genderFilter);

  const res = await apiCall("GET", `/students?${params.toString()}`);
  const students = res?.data?.data?.students || [];
  cachedStudents = students;

  // Populate student selects for modals
  populateStudentSelects(students);

  if (students.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">🔍</div>${currentLang === "kn" ? "ಯಾವುದೇ ವಿದ್ಯಾರ್ಥಿಗಳು ಕಂಡುಬಂದಿಲ್ಲ. 'ಹೊಸ ವಿದ್ಯಾರ್ಥಿ ಸೇರಿಸಿ' ಬಟನ್ ಬಳಸಿ." : "No students found. Use 'Enroll New Student' to add."}</div>`;
    return;
  }

  container.innerHTML = `
    <table class="gov-table">
      <thead>
        <tr>
          <th>${t("col_sats_id")}</th>
          <th>${t("col_name")}</th>
          <th>${t("col_class")}</th>
          <th>${t("col_sec")}</th>
          <th>${t("col_gender")}</th>
          <th>${t("col_category")}</th>
          <th>${t("col_status")}</th>
          <th>${t("col_actions")}</th>
        </tr>
      </thead>
      <tbody>
        ${students.map(s => `
          <tr>
            <td><code>${s.sats_id}</code></td>
            <td><strong>${s.name}</strong></td>
            <td>ತರಗತಿ ${s.current_class}</td>
            <td>${s.section || "-"}</td>
            <td>${s.gender === 'male' ? 'ಗಂಡು (Male)' : s.gender === 'female' ? 'ಹೆಣ್ಣು (Female)' : 'ಇತರೆ'}</td>
            <td><span class="gov-badge badge-purple">${(s.caste_category || 'general').toUpperCase()}</span></td>
            <td><span class="gov-badge ${s.is_active ? 'badge-success' : 'badge-danger'}">${s.is_active ? t("status_active") : t("status_withdrawn")}</span></td>
            <td>
              ${s.is_active ? `
                <button class="btn btn-secondary btn-sm" onclick="withdrawStudentPrompt('${s.sats_id}', '${s.name}')" title="Withdraw Student">
                  🚫 ${t("withdraw_btn")}
                </button>
              ` : '-'}
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function applyStudentFilters() {
  const search = document.getElementById("student-search-input")?.value?.trim() || "";
  loadStudentsRoster(search);
}

function populateStudentSelects(students) {
  const selects = [document.getElementById("cce-student-select"), document.getElementById("tc-student-select")];
  selects.forEach(sel => {
    if (!sel) return;
    sel.innerHTML = students.map(s => `<option value="${s.sats_id}">${s.sats_id} — ${s.name} (ತರಗತಿ ${s.current_class})</option>`).join("");
  });
}

function openEnrollStudentModal() {
  const form = document.getElementById("enroll-student-form");
  if (form) form.reset();
  openModal("modal-enroll-student");
}

async function handleEnrollStudent(e) {
  e.preventDefault();
  const satsId = document.getElementById("enroll-sats-id").value.trim();
  const name = document.getElementById("enroll-name").value.trim();
  const currentClass = document.getElementById("enroll-class").value;
  const section = document.getElementById("enroll-section").value.trim() || "A";
  const gender = document.getElementById("enroll-gender").value;
  const casteCategory = document.getElementById("enroll-category").value;

  const payload = {
    sats_id: satsId,
    name,
    current_class: currentClass,
    section,
    gender,
    caste_category: casteCategory,
    school_dise_code: currentTeacher?.school_dise_code || "29210101001"
  };

  const res = await apiCall("POST", "/students", payload);
  if (res && res.ok) {
    toast(currentLang === "kn" ? `✅ ವಿದ್ಯಾರ್ಥಿ ${name} (${satsId}) ಯಶಸ್ವಿಯಾಗಿ ದಾಖಲಾಗಿದ್ದಾರೆ!` : `✅ Student ${name} enrolled successfully!`, "success");
    closeModal("modal-enroll-student");
    loadStudentsRoster();
    updateSyncBadge();
  } else {
    toast(res?.data?.detail || "Error enrolling student", "error");
  }
}

async function withdrawStudentPrompt(satsId, studentName) {
  const confirmMsg = currentLang === "kn"
    ? `ನೀವು ವಿದ್ಯಾರ್ಥಿ "${studentName}" (${satsId}) ಅವರನ್ನು ಶಾಲೆಯಿಂದ ಬಿಡಿಸಲು (Withdraw) ಖಚಿತವಾಗಿ ಬಯಸುವಿರಾ?`
    : `Are you sure you want to withdraw student "${studentName}" (${satsId})?`;

  if (!confirm(confirmMsg)) return;

  const res = await apiCall("DELETE", `/students/${satsId}`);
  if (res && res.ok) {
    toast(currentLang === "kn" ? "ವಿದ್ಯಾರ್ಥಿಯನ್ನು ಯಶಸ್ವಿಯಾಗಿ ಬಿಡಿಸಲಾಗಿದೆ" : "Student withdrawn successfully", "success");
    loadStudentsRoster();
    updateSyncBadge();
  } else {
    toast(res?.data?.detail || "Withdraw error", "error");
  }
}

// ── 3. Daily Attendance Module ────────────────────────────────────────────────
function initAttendancePage() {
  const dateInput = document.getElementById("attendance-date");
  if (dateInput && !dateInput.value) {
    dateInput.value = new Date().toISOString().split("T")[0];
  }
  loadAttendanceRoster();
}

async function loadAttendanceRoster() {
  const container = document.getElementById("attendance-form-container");
  const dateInput = document.getElementById("attendance-date");
  const classFilter = document.getElementById("attendance-class-select")?.value || "";
  if (!container || !dateInput) return;

  const selectedDate = dateInput.value;
  container.innerHTML = `<div class="empty-state"><div class="icon">⏳</div>ಹಾಜರಾತಿ ಪಟ್ಟಿ ಲೋಡ್ ಆಗುತ್ತಿದೆ...</div>`;

  const params = new URLSearchParams({ limit: 100 });
  if (classFilter) params.append("current_class", classFilter);

  const res = await apiCall("GET", `/students?${params.toString()}`);
  const students = res?.data?.data?.students || [];

  if (students.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">👥</div>ವಿದ್ಯಾರ್ಥಿಗಳ ವಿವರ ಕಂಡುಬಂದಿಲ್ಲ.</div>`;
    return;
  }

  container.innerHTML = `
    <form onsubmit="submitAttendanceRoster(event, '${selectedDate}')">
      <table class="gov-table">
        <thead>
          <tr>
            <th>${t("col_sats_id")}</th>
            <th>${t("col_name")}</th>
            <th>${t("col_class")}</th>
            <th>${t("col_status")}</th>
          </tr>
        </thead>
        <tbody>
          ${students.map(s => `
            <tr>
              <td><code>${s.sats_id}</code></td>
              <td><strong>${s.name}</strong></td>
              <td>ತರಗತಿ ${s.current_class}-${s.section || 'A'}</td>
              <td>
                <select name="att_${s.sats_id}" class="form-control att-select" style="width:160px;">
                  <option value="present" selected>${t("opt_present")}</option>
                  <option value="absent">${t("opt_absent")}</option>
                  <option value="holiday">${t("opt_holiday")}</option>
                  <option value="half_day">${t("opt_half_day")}</option>
                </select>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      <div style="padding:16px; background:#f8fafc; border-top:1px solid var(--border-light); display:flex; justify-content:flex-end;">
        <button type="submit" class="btn btn-primary" style="padding:10px 24px;">
          ${t("att_save_btn")} (${selectedDate})
        </button>
      </div>
    </form>
  `;
}

function markAllAttendance(statusValue) {
  document.querySelectorAll(".att-select").forEach(sel => sel.value = statusValue);
}

async function submitAttendanceRoster(e, attendanceDate) {
  e.preventDefault();
  const form = e.target;
  const selects = form.querySelectorAll(".att-select");
  const records = [];

  selects.forEach(sel => {
    const satsId = sel.name.replace("att_", "");
    records.push({
      student_sats_id: satsId,
      status: sel.value,
      attendance_date: attendanceDate
    });
  });

  const res = await apiCall("POST", "/attendance/bulk", {
    records,
    attendance_date: attendanceDate
  });

  if (res?.ok) {
    toast(
      currentLang === "kn"
        ? `✅ ${records.length} ವಿದ್ಯಾರ್ಥಿಗಳ ಹಾಜರಾತಿ ದಿನಾಂಕ ${attendanceDate} ಗೆ ದಾಖಲಾಗಿದೆ!`
        : `✅ Attendance recorded for ${records.length} students on ${attendanceDate}!`,
      "success"
    );
    updateSyncBadge();
  } else {
    toast("Error saving attendance", "error");
  }
}

// ── 4. Assessments / CCE Module ───────────────────────────────────────────────
async function loadAssessmentsModule() {
  const container = document.getElementById("assessments-table-container");
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><div class="icon">⏳</div>ಮೌಲ್ಯಮಾಪನ ದಾಖಲೆಗಳು ಲೋಡ್ ಆಗುತ್ತಿವೆ...</div>`;

  if (cachedStudents.length === 0) {
    const sRes = await apiCall("GET", "/students?limit=50");
    cachedStudents = sRes?.data?.data?.students || [];
    populateStudentSelects(cachedStudents);
  }

  // Fetch assessments for the first few students
  const sampleStudents = cachedStudents.slice(0, 5);
  const assessmentPromises = sampleStudents.map(s => apiCall("GET", `/assessments/student/${s.sats_id}`));
  const results = await Promise.all(assessmentPromises);

  const allAssessments = [];
  results.forEach((res, i) => {
    const list = res?.data?.data?.assessments || res?.data?.data || [];
    list.forEach(a => {
      a.student_name = sampleStudents[i]?.name || a.student_sats_id;
      allAssessments.push(a);
    });
  });

  if (allAssessments.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="icon">📝</div>
        <p>${currentLang === "kn" ? "ಯಾವುದೇ ಅಂಕಗಳು ದಾಖಲಾಗಿಲ್ಲ. 'ಹೊಸ ಅಂಕಗಳನ್ನು ನಮೂದಿಸಿ' ಬಟನ್ ಬಳಸಿ." : "No assessment marks recorded yet. Use 'Enter Student Marks'."}</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <table class="gov-table">
      <thead>
        <tr>
          <th>${t("col_sats_id")}</th>
          <th>${t("col_name")}</th>
          <th>${t("col_subject")}</th>
          <th>${t("col_exam_type")}</th>
          <th>${t("col_marks_obtained")}</th>
          <th>${t("col_max_marks")}</th>
          <th>${t("col_percentage")}</th>
          <th>${t("col_date")}</th>
        </tr>
      </thead>
      <tbody>
        ${allAssessments.map(a => {
          const pct = Math.round((a.marks_obtained / a.max_marks) * 100);
          return `
            <tr>
              <td><code>${a.student_sats_id}</code></td>
              <td><strong>${a.student_name}</strong></td>
              <td>${a.subject}</td>
              <td><span class="gov-badge badge-info">${a.assessment_type}</span></td>
              <td><strong>${a.marks_obtained}</strong></td>
              <td>${a.max_marks}</td>
              <td><span class="gov-badge ${pct >= 75 ? 'badge-success' : pct >= 40 ? 'badge-warning' : 'badge-danger'}">${pct}%</span></td>
              <td>${a.assessment_date || "-"}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function openAddAssessmentModal() {
  if (cachedStudents.length === 0) {
    loadStudentsRoster();
  }
  openModal("modal-assessment");
}

async function handleAddAssessment(e) {
  e.preventDefault();
  const studentSatsId = document.getElementById("cce-student-select").value;
  const subject = document.getElementById("cce-subject").value;
  const assessmentType = document.getElementById("cce-type").value;
  const marksObtained = parseFloat(document.getElementById("cce-obtained").value);
  const maxMarks = parseFloat(document.getElementById("cce-max").value);

  if (marksObtained > maxMarks) {
    toast("Marks obtained cannot exceed max marks", "warning");
    return;
  }

  const payload = {
    student_sats_id: studentSatsId,
    subject,
    chapter: "General",
    assessment_type: assessmentType,
    marks_obtained: marksObtained,
    max_marks: maxMarks,
    assessment_date: new Date().toISOString().split("T")[0],
    academic_year: "2026-27"
  };

  const res = await apiCall("POST", "/assessments", payload);
  if (res && res.ok) {
    toast(currentLang === "kn" ? "✅ ಮೌಲ್ಯಮಾಪನ ಅಂಕಗಳು ಯಶಸ್ವಿಯಾಗಿ ದಾಖಲಾಗಿವೆ!" : "✅ Assessment marks saved successfully!", "success");
    closeModal("modal-assessment");
    loadAssessmentsModule();
    updateSyncBadge();
  } else {
    toast(res?.data?.detail || "Error saving assessment", "error");
  }
}

// ── 5. Transfer Certificate (TC) Module ───────────────────────────────────────
async function loadTCModule() {
  const container = document.getElementById("tc-table-container");
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><div class="icon">⏳</div>TC ದಾಖಲೆಗಳು ಲೋಡ್ ಆಗುತ್ತಿವೆ...</div>`;

  if (cachedStudents.length === 0) {
    const sRes = await apiCall("GET", "/students?limit=50");
    cachedStudents = sRes?.data?.data?.students || [];
    populateStudentSelects(cachedStudents);
  }

  const tcPromises = cachedStudents.slice(0, 10).map(s => apiCall("GET", `/tc/student/${s.sats_id}`));
  const results = await Promise.all(tcPromises);

  const tcs = [];
  results.forEach((res, i) => {
    const list = res?.data?.data?.transfer_certificates || [];
    list.forEach(item => {
      item.student_name = cachedStudents[i]?.name || item.student_sats_id;
      tcs.push(item);
    });
  });

  if (tcs.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="icon">📜</div>
        <p>${currentLang === "kn" ? "ಯಾವುದೇ ಸಕ್ರಿಯ TC ಕೋರಿಕೆಗಳು ಕಂಡುಬಂದಿಲ್ಲ. 'ಹೊಸ TC ಕೋರಿಕೆ' ಬಳಸಿ." : "No active Transfer Certificates found. Use 'Request New TC'."}</p>
      </div>
    `;
    return;
  }

  const isHm = currentTeacher?.is_admin || currentTeacher?.designation === "headmaster";

  container.innerHTML = `
    <table class="gov-table">
      <thead>
        <tr>
          <th>${t("col_sats_id")}</th>
          <th>${t("col_name")}</th>
          <th>${t("col_reason")}</th>
          <th>${t("col_req_date")}</th>
          <th>${t("col_status")}</th>
          <th>${t("col_actions")}</th>
        </tr>
      </thead>
      <tbody>
        ${tcs.map(tc => `
          <tr>
            <td><code>${tc.student_sats_id}</code></td>
            <td><strong>${tc.student_name}</strong></td>
            <td>${tc.reason || "ಸ್ಥಳಾಂತರ (Relocation)"}</td>
            <td>${tc.request_date || "-"}</td>
            <td>
              <span class="gov-badge ${tc.status === 'approved' || tc.status === 'issued' ? 'badge-success' : tc.status === 'rejected' ? 'badge-danger' : 'badge-warning'}">
                ${tc.status.toUpperCase()}
              </span>
            </td>
            <td>
              ${isHm && tc.status === 'requested' ? `
                <button class="btn btn-success btn-sm" onclick="approveTCAction('${tc.id}')">
                  ✓ ${t("approve_btn")}
                </button>
              ` : '-'}
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function openRequestTCModal() {
  if (cachedStudents.length === 0) loadStudentsRoster();
  openModal("modal-request-tc");
}

async function handleRequestTC(e) {
  e.preventDefault();
  const studentSatsId = document.getElementById("tc-student-select").value;
  const reason = document.getElementById("tc-reason").value.trim();
  const receivingSchoolDise = document.getElementById("tc-receiving-dise").value.trim() || undefined;

  const payload = {
    student_sats_id: studentSatsId,
    issuing_school_dise: currentTeacher?.school_dise_code || "29210101001",
    reason,
    receiving_school_dise: receivingSchoolDise
  };

  const res = await apiCall("POST", "/tc/request", payload);
  if (res && res.ok) {
    toast(currentLang === "kn" ? "✅ TC ಕೋರಿಕೆಯನ್ನು ಯಶಸ್ವಿಯಾಗಿ ಸಲ್ಲಿಸಲಾಗಿದೆ!" : "✅ TC request submitted successfully!", "success");
    closeModal("modal-request-tc");
    loadTCModule();
    updateSyncBadge();
  } else {
    toast(res?.data?.detail || "TC request error", "error");
  }
}

async function approveTCAction(tcId) {
  const res = await apiCall("PUT", `/tc/${tcId}/approve`, {
    status: "approved",
    remarks: "Approved by Headmaster via SATS Companion"
  });

  if (res && res.ok) {
    toast(currentLang === "kn" ? "✅ TC ಯಶಸ್ವಿಯಾಗಿ ಅನುಮೋದನೆಗೊಂಡಿದೆ!" : "✅ TC approved successfully!", "success");
    loadTCModule();
    updateSyncBadge();
  } else {
    toast(res?.data?.detail || "Approval error", "error");
  }
}

// ── 6. CSV Bulk Import Module ─────────────────────────────────────────────────
async function handleCsvImport(type) {
  const input = document.getElementById(`${type}-csv-input`);
  const dryRun = document.getElementById(`${type}-dry-run`)?.checked || false;
  const resultEl = document.getElementById(`${type}-import-result`);

  if (!input?.files[0]) {
    toast(currentLang === "kn" ? "ದಯವಿಟ್ಟು ಮೊದಲು CSV ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ." : "Please select a CSV file first.", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);

  resultEl.innerHTML = `<div class="empty-state"><div class="icon">⏳</div>${currentLang === "kn" ? "ಫೈಲ್ ಪ್ರಕ್ರಿಯೆ ನಡೆಯುತ್ತಿದೆ..." : "Processing CSV..."}</div>`;
  const endpoint = type === "students" ? "/import/students/csv" : "/import/attendance/csv";

  try {
    const res = await fetch(`${API_BASE}${endpoint}?dry_run=${dryRun}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${authToken}` },
      body: formData,
    });
    const envelope = await res.json();
    const d = envelope.data || {};

    resultEl.innerHTML = `
      <div style="padding:14px; border-radius:4px; margin-top:10px; background:${envelope.status === 'success' ? '#f0fdf4' : '#fffbeb'}; border:1px solid ${envelope.status === 'success' ? '#bbf7d0' : '#fde68a'};">
        <strong style="color:var(--gov-navy); font-size:13.5px;">${envelope.message}</strong>
        <div style="font-size:12.5px; margin-top:8px; line-height:1.7;">
          ${d.created !== undefined ? `<div>✅ ರಚಿಸಿದ ದಾಖಲೆಗಳು: <strong>${d.created}</strong></div>` : ""}
          ${d.updated !== undefined ? `<div>🔄 ನವೀಕರಿಸಿದ ದಾಖಲೆಗಳು: <strong>${d.updated}</strong></div>` : ""}
          ${d.skipped_duplicates !== undefined ? `<div>⏭️ ಬಿಟ್ಟುಬಿಡಲಾದ ನಕಲುಗಳು: <strong>${d.skipped_duplicates}</strong></div>` : ""}
          ${d.failed !== undefined ? `<div>❌ ವಿಫಲವಾದ ಸಾಲುಗಳು: <strong>${d.failed}</strong></div>` : ""}
        </div>
      </div>
    `;
    updateSyncBadge();
    if (type === "students") loadStudentsRoster();
  } catch (err) {
    resultEl.innerHTML = `<p style="color:var(--gov-red); font-size:13px; margin-top:8px;">Import error: ${err.message}</p>`;
  }
}

// ── 7. Sync Audit Module ──────────────────────────────────────────────────────
async function loadSyncHistory() {
  const container = document.getElementById("sync-history-container");
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><div class="icon">⏳</div>ಸಿಂಕ್ ಇತಿಹಾಸ ಲೋಡ್ ಆಗುತ್ತಿದೆ...</div>`;

  const res = await apiCall("GET", "/sync/history?limit=25");
  const logs = res?.data?.data || [];

  if (logs.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">🔄</div>ಯಾವುದೇ ಸಿಂಕ್ ದಾಖಲೆಗಳು ಕಂಡುಬಂದಿಲ್ಲ.</div>`;
    return;
  }

  container.innerHTML = `
    <table class="gov-table">
      <thead>
        <tr>
          <th>${t("col_session")}</th>
          <th>${t("col_pushed")}</th>
          <th>${t("col_conflicts")}</th>
          <th>${t("col_duration")}</th>
          <th>${t("col_status")}</th>
          <th>ದಿನಾಂಕ ಮತ್ತು ಸಮಯ</th>
        </tr>
      </thead>
      <tbody>
        ${logs.map(l => `
          <tr>
            <td><code>${l.session_id.slice(0, 10)}…</code></td>
            <td><strong>${l.pushed}</strong> ದಾಖಲೆ</td>
            <td>${l.conflicts > 0 ? `<span class="gov-badge badge-warning">${l.conflicts} ವ್ಯತ್ಯಾಸ</span>` : '0'}</td>
            <td>${l.duration_seconds || 0} ಸೆಕೆಂಡ್</td>
            <td><span class="gov-badge ${l.success ? 'badge-success' : 'badge-danger'}">${l.success ? 'ಯಶಸ್ವಿ (Success)' : 'ವಿಫಲ'}</span></td>
            <td>${l.started_at ? new Date(l.started_at).toLocaleString() : '-'}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

// ── 8. SATS Marks Bridge Module (Universal Ingestor) ──────────────────────────
let bridgeExtractedRecords = [];

function initBridgePage() {
  if (cachedStudents.length === 0) {
    loadStudentsRoster();
  }
}

async function handleBridgeParse(e) {
  e.preventDefault();
  const fileInput = document.getElementById("bridge-file-input");
  const subject = document.getElementById("bridge-subject").value;
  const assessmentType = document.getElementById("bridge-type").value;
  const maxMarks = document.getElementById("bridge-max-marks").value;
  const btn = document.getElementById("bridge-extract-btn");

  if (!fileInput || !fileInput.files[0]) {
    toast(currentLang === "kn" ? "ದಯವಿಟ್ಟು ಅಂಕಪಟ್ಟಿಯ ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ." : "Please select a score sheet file first.", "warning");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("subject", subject);
  formData.append("assessment_type", assessmentType);
  formData.append("max_marks", maxMarks);

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `⏳ ${currentLang === "kn" ? "ಡೇಟಾ ವಿಶ್ಲೇಷಿಸಲಾಗುತ್ತಿದೆ..." : "Extracting & Matching..."}`;
  }

  try {
    const res = await fetch(`${API_BASE}/marks-bridge/parse`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getStoredToken()}` },
      body: formData,
    });

    const envelope = await res.json();
    if (!res.ok) {
      throw new Error(envelope.detail || "Error parsing marks file");
    }

    const data = envelope.data || {};
    bridgeExtractedRecords = data.records || [];

    toast(
      currentLang === "kn"
        ? `✅ ಯಶಸ್ವಿಯಾಗಿ ${bridgeExtractedRecords.length} ಅಂಕಗಳ ದಾಖಲೆಗಳನ್ನು SATS ಗೆ ಜೋಡಿಸಲಾಗಿದೆ!`
        : `✅ Successfully extracted and matched ${bridgeExtractedRecords.length} marks records!`,
      "success"
    );

    renderBridgeRecords(data);
  } catch (err) {
    toast(`Bridge Error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `⚡ ${t("bridge_extract_btn")}`;
    }
  }
}

function loadBridgeSampleDemo() {
  const subject = document.getElementById("bridge-subject")?.value || "Mathematics";
  const assessmentType = document.getElementById("bridge-type")?.value || "FA1";
  const maxMarks = parseFloat(document.getElementById("bridge-max-marks")?.value || "20");

  const sampleMarks = [19.0, 17.5, 18.0, 14.5, 19.5, 16.0, 12.0, 18.5, 15.0, 20.0];
  const demoRoster = cachedStudents.length > 0 ? cachedStudents : [
    { sats_id: "SATS2901001", name: "Darshan Gowda", current_class: "8" },
    { sats_id: "SATS2901002", name: "Bhavya R", current_class: "8" },
    { sats_id: "SATS2901003", name: "Chetan Kumar", current_class: "8" },
    { sats_id: "SATS2901004", name: "Deepa M", current_class: "8" },
    { sats_id: "SATS2901005", name: "Eshwar Naik", current_class: "8" },
    { sats_id: "SATS2901006", name: "Farzana Begum", current_class: "8" },
    { sats_id: "SATS2901007", name: "Girish Murthy", current_class: "8" },
    { sats_id: "SATS2901008", name: "Hemalatha S", current_class: "8" },
    { sats_id: "SATS2901009", name: "Imran Pasha", current_class: "8" },
    { sats_id: "SATS2901010", name: "Jyothi Bai", current_class: "8" },
  ];

  bridgeExtractedRecords = demoRoster.map((s, idx) => {
    const obtained = sampleMarks[idx % sampleMarks.length];
    const pct = (obtained / maxMarks) * 100;
    const grade = pct >= 90 ? "A+" : pct >= 80 ? "A" : pct >= 70 ? "B+" : "B";
    return {
      student_sats_id: s.sats_id,
      student_name: s.name,
      current_class: s.current_class || "8",
      subject,
      assessment_type: assessmentType,
      marks_obtained: obtained,
      max_marks: maxMarks,
      is_absent: false,
      grade,
      match_status: "exact"
    };
  });

  renderBridgeRecords({
    records: bridgeExtractedRecords,
    total: bridgeExtractedRecords.length,
    matched: bridgeExtractedRecords.length,
    unmatched: 0,
    parser_used: "Sample Demo Mark Sheet",
    school_dise: currentTeacher?.school_dise_code || "29210101001"
  });

  toast(
    currentLang === "kn"
      ? "📋 ಮಾದರಿ SATS CCE ಅಂಕಗಳ ಪಟ್ಟಿಯನ್ನು ಲೋಡ್ ಮಾಡಲಾಗಿದೆ."
      : "📋 Loaded demo SATS CCE marks records for review.",
    "info"
  );
}

function renderBridgeRecords(data = {}) {
  const container = document.getElementById("bridge-results-container");
  const badgesEl = document.getElementById("bridge-summary-badges");
  const tbody = document.getElementById("bridge-table-body");
  if (!container || !tbody) return;

  container.style.display = "block";

  const total = bridgeExtractedRecords.length;
  const matched = bridgeExtractedRecords.filter(r => r.match_status === "exact" || r.match_status === "name_match").length;
  const unmatched = total - matched;

  if (badgesEl) {
    badgesEl.innerHTML = `
      <span class="gov-badge badge-info">${data.parser_used || "Bridge Parser"}</span>
      <span class="gov-badge badge-success">🟢 ${currentLang === "kn" ? "ಹೊಂದಿಕೆಯಾಗಿದೆ" : "Matched"}: ${matched}</span>
      ${unmatched > 0 ? `<span class="gov-badge badge-danger">🔴 ${currentLang === "kn" ? "ಅಪರಿಚಿತ" : "Unmatched"}: ${unmatched}</span>` : ""}
    `;
  }

  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px;">ಯಾವುದೇ ಅಂಕಗಳು ಕಂಡುಬಂದಿಲ್ಲ.</td></tr>`;
    return;
  }

  tbody.innerHTML = bridgeExtractedRecords.map((r, i) => `
    <tr>
      <td>
        <input type="text" class="form-control" style="width:130px; font-size:12.5px; padding:4px 8px;" value="${r.student_sats_id || ''}" onchange="updateBridgeField(${i}, 'student_sats_id', this.value)" />
      </td>
      <td><strong>${r.student_name || 'Student'}</strong></td>
      <td>ತರಗತಿ ${r.current_class || '8'}</td>
      <td>${r.subject}</td>
      <td><span class="gov-badge badge-info">${r.assessment_type}</span></td>
      <td>
        <input type="number" step="0.5" class="form-control" style="width:90px; font-weight:700; padding:4px 8px;" value="${r.marks_obtained}" onchange="updateBridgeMarks(${i}, this.value)" min="0" max="${r.max_marks}" />
      </td>
      <td>${r.max_marks}</td>
      <td>
        <span class="gov-badge ${r.match_status === 'exact' ? 'badge-success' : r.match_status === 'name_match' ? 'badge-warning' : 'badge-danger'}">
          ${r.match_status === 'exact' ? '🟢 SATS Matched' : r.match_status === 'name_match' ? '🟠 Name Match' : '🔴 Unmatched'}
        </span>
      </td>
      <td>
        <button type="button" class="btn btn-secondary btn-sm" onclick="removeBridgeRow(${i})" title="Remove">✕</button>
      </td>
    </tr>
  `).join("");
}

function updateBridgeField(index, field, value) {
  if (bridgeExtractedRecords[index]) {
    bridgeExtractedRecords[index][field] = value.trim();
  }
}

function updateBridgeMarks(index, value) {
  if (bridgeExtractedRecords[index]) {
    const num = parseFloat(value) || 0;
    bridgeExtractedRecords[index].marks_obtained = num;
  }
}

function removeBridgeRow(index) {
  bridgeExtractedRecords.splice(index, 1);
  renderBridgeRecords();
}

async function handleBridgeCommit() {
  if (bridgeExtractedRecords.length === 0) {
    toast("No records to commit", "warning");
    return;
  }

  const btn = document.getElementById("bridge-commit-btn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `⏳ ${currentLang === "kn" ? "SATS ಗೆ ಉಳಿಸಲಾಗುತ್ತಿದೆ..." : "Saving to SATS..."}`;
  }

  try {
    const res = await apiCall("POST", "/marks-bridge/batch-commit", {
      records: bridgeExtractedRecords,
      school_dise_code: currentTeacher?.school_dise_code || "29210101001"
    });

    if (res && res.ok) {
      const data = res.data?.data || {};
      const total = data.total || bridgeExtractedRecords.length;
      toast(
        currentLang === "kn"
          ? `🎉 ಯಶಸ್ವಿಯಾಗಿದೆ! ${total} ವಿದ್ಯಾರ್ಥಿಗಳ ಅಂಕಗಳನ್ನು SATS ಗೆ ಬ್ಯಾಚ್ ಸೇವ್ ಮಾಡಲಾಗಿದೆ!`
          : `🎉 Success! Batch saved ${total} marks to SATS & Offline Sync Queue!`,
        "success"
      );
      updateSyncBadge();
      loadDashboardMetrics();
    } else {
      toast(res?.data?.detail || "Commit error", "error");
    }
  } catch (err) {
    toast(`Commit error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `💾 ${t("bridge_save_sats")}`;
    }
  }
}

async function handleBridgeExportCsv() {
  if (bridgeExtractedRecords.length === 0) {
    toast("No records to export", "warning");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/marks-bridge/export-sats-format`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${getStoredToken()}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        records: bridgeExtractedRecords,
        school_dise_code: currentTeacher?.school_dise_code || "29210101001"
      })
    });

    if (!res.ok) throw new Error("Could not generate SATS CSV");

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sats_cce_marks_upload_${currentTeacher?.school_dise_code || "29210101001"}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    toast(
      currentLang === "kn"
        ? "⬇️ ಅಧಿಕೃತ ಕರ್ನಾಟಕ SATS/ನಿರಂತರ CSV ಫೈಲ್ ಡೌನ್‌ಲೋಡ್ ಆಗಿದೆ!"
        : "⬇️ Official Karnataka SATS/Nirantara CSV downloaded successfully!",
      "success"
    );
  } catch (err) {
    toast(`Export error: ${err.message}`, "error");
  }
}

// ── Application Initialization ────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Apply saved font scale
  const scale = localStorage.getItem(FONT_SCALE_KEY) || "1";
  document.documentElement.style.setProperty("--font-scale", scale);

  // Initialize Language
  applyLanguage();

  // Login form handler
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const kgid = document.getElementById("kgid").value.trim();
      const pwd = document.getElementById("password").value;
      try {
        await login(kgid, pwd);
        toast(currentLang === "kn" ? "SATS Companion ಗೆ ಸ್ವಾಗತ!" : "Welcome to SATS Companion!", "success");
        showPage("dashboard");
        startSyncPolling();
      } catch (err) {
        toast(`Login Error: ${err.message}`, "error");
      }
    });
  }

  // Session check
  authToken = getStoredToken();
  if (authToken) {
    updateTeacherUI();
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
