import { useState, useEffect, useCallback, useRef } from "react";
import LogConsole from "./LogConsole";

// ─── Mock data for preview (replace with real API calls) ───
// Note: Mock data is disabled (USE_MOCK = false). Using real API calls instead.
// const MOCK_PROFILES = [...];
// const MOCK_JOBS = [...];
// const MOCK_HEALTH = {...};
// const MOCK_READY = {...};

// ─── API Configuration ───
// For production: VITE_API_URL should be empty (relative URLs) or full production URL
// For local development: VITE_API_URL=http://localhost:8888
const API_BASE = import.meta.env.VITE_API_URL || '';
const API_KEY = import.meta.env.VITE_PIPELINE_API_KEY || '';
console.log('Frontend: API_BASE =', API_BASE);
const USE_MOCK = false;

async function apiFetch(path, options = {}) {
  console.log(`Frontend: apiFetch called for path: ${path}`);
  if (API_KEY) {
    options.headers = { ...options.headers, "X-API-Key": API_KEY };
    console.log(`Frontend: Added X-API-Key header`);
  }
  options.credentials = 'include';
  const url = `${API_BASE}${path}`;
  console.log(`Frontend: Fetching URL: ${url}`);
  const res = await fetch(url, options);
  console.log(`Frontend: Response status: ${res.status} ${res.statusText}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error(`Frontend: API error ${res.status}:`, err);
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  if (res.status === 204) return null;
  const data = await res.json();
  console.log(`Frontend: API response data received for ${path}`);
  return data;
}

// ─── Icons (inline SVG) ───
const Icons = {
  briefcase: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" ry="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
    </svg>
  ),
  book: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  ),
  users: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  mic: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" /><line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  ),
  zap: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  ),
  upload: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  ),
  check: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  x: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  ),
  loader: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="spin">
      <line x1="12" y1="2" x2="12" y2="6" /><line x1="12" y1="18" x2="12" y2="22" /><line x1="4.93" y1="4.93" x2="7.76" y2="7.76" /><line x1="16.24" y1="16.24" x2="19.07" y2="19.07" /><line x1="2" y1="12" x2="6" y2="12" /><line x1="18" y1="12" x2="22" y2="12" /><line x1="4.93" y1="19.07" x2="7.76" y2="16.24" /><line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
    </svg>
  ),
  clock: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  chevronRight: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  ),
  arrowLeft: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
    </svg>
  ),
  activity: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  ),
  file: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><polyline points="13 2 13 9 20 9" />
    </svg>
  ),
};

const PROFILE_ICONS = {
  business_lecture: Icons.briefcase,
  social_work_lecture: Icons.book,
  meeting: Icons.users,
  supervision: Icons.users,
  braindump: Icons.zap,
  lecture: Icons.mic,
  client: Icons.users,
};

const PROFILE_COLORS = {
  business_lecture: { accent: "#f59e0b", glow: "rgba(245,158,11,0.15)", gradient: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(245,158,11,0.05))" },
  social_work_lecture: { accent: "#a78bfa", glow: "rgba(167,139,250,0.15)", gradient: "linear-gradient(135deg, rgba(167,139,250,0.2), rgba(167,139,250,0.05))" },
  meeting: { accent: "#34d399", glow: "rgba(52,211,153,0.15)", gradient: "linear-gradient(135deg, rgba(52,211,153,0.2), rgba(52,211,153,0.05))" },
  supervision: { accent: "#60a5fa", glow: "rgba(96,165,250,0.15)", gradient: "linear-gradient(135deg, rgba(96,165,250,0.2), rgba(96,165,250,0.05))" },
  braindump: { accent: "#f472b6", glow: "rgba(244,114,182,0.15)", gradient: "linear-gradient(135deg, rgba(244,114,182,0.2), rgba(244,114,182,0.05))" },
};

const STATUS_CONFIG = {
  COMPLETE: { color: "#34d399", bg: "rgba(52,211,153,0.12)", icon: Icons.check, label: "Complete" },
  PROCESSING: { color: "#60a5fa", bg: "rgba(96,165,250,0.12)", icon: Icons.loader, label: "Processing" },
  QUEUED: { color: "#fbbf24", bg: "rgba(251,191,36,0.12)", icon: Icons.clock, label: "Queued" },
  FAILED: { color: "#f87171", bg: "rgba(248,113,113,0.12)", icon: Icons.x, label: "Failed" },
  CANCELLED: { color: "#6b7280", bg: "rgba(107,114,128,0.12)", icon: Icons.x, label: "Cancelled" },
};

// ─── Helpers ───
function getFilename(path) {
  const parts = path.split("/");
  const name = parts[parts.length - 1];
  return name.replace(/^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_/, "").replace(/[-_]/g, " ");
}

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const now = new Date();
  const then = new Date(dateStr);
  const diff = Math.floor((now - then) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatDuration(start, end) {
  if (!start || !end) return null;
  const diff = Math.floor((new Date(end) - new Date(start)) / 1000);
  const m = Math.floor(diff / 60);
  const s = diff % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// ─── Status Badge ───
function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.QUEUED;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "3px 10px", borderRadius: 20,
      background: cfg.bg, color: cfg.color,
      fontSize: 11, fontWeight: 600, letterSpacing: 0.5,
      textTransform: "uppercase",
    }}>
      <span style={{ display: "flex" }}>{cfg.icon}</span>
      {cfg.label}
    </span>
  );
}

// ─── Pipeline Stage Tracker ───
function PipelineTracker({ job, profile }) {
  const stageResults = job.stage_results || [];
  if (stageResults.length === 0 && job.status !== "PROCESSING") return null;

  const STAGE_STYLES = {
    PENDING:  { color: "rgba(255,255,255,0.2)", bg: "rgba(255,255,255,0.03)", border: "rgba(255,255,255,0.04)", icon: "○" },
    RUNNING:  { color: "#60a5fa", bg: "rgba(96,165,250,0.12)", border: "rgba(96,165,250,0.3)", icon: "◌" },
    COMPLETE: { color: "#34d399", bg: "rgba(52,211,153,0.1)", border: "rgba(52,211,153,0.2)", icon: "✓" },
    FAILED:   { color: "#f87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.2)", icon: "✗" },
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
      {stageResults.map((sr, i) => {
        const s = STAGE_STYLES[sr.status] || STAGE_STYLES.PENDING;
        const costStr = sr.cost_estimate > 0 ? ` · $${sr.cost_estimate.toFixed(4)}` : "";
        const tokenStr = (sr.input_tokens || sr.output_tokens)
          ? ` · ${((sr.input_tokens + sr.output_tokens) / 1000).toFixed(1)}k tok`
          : "";
        return (
          <div key={sr.stage_id} style={{ display: "flex", alignItems: "center" }}>
            <div
              title={`${sr.stage_id}: ${sr.status}${sr.model_used ? ` (${sr.model_used})` : ""}${costStr}${tokenStr}${sr.error ? ` — ${sr.error}` : ""}`}
              style={{
                padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 500,
                background: s.bg, color: s.color, border: `1px solid ${s.border}`,
                display: "flex", alignItems: "center", gap: 4, cursor: "default",
              }}
            >
              <span style={{ fontSize: 9 }}>{s.icon}</span>
              {sr.stage_id}
            </div>
            {i < stageResults.length - 1 && (
              <span style={{ color: "rgba(255,255,255,0.1)", fontSize: 10, margin: "0 2px" }}>→</span>
            )}
          </div>
        );
      })}
      {job.cost_estimate > 0 && (
        <span style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", marginLeft: 4 }}>
          ${job.cost_estimate.toFixed(4)}
        </span>
      )}
    </div>
  );
}

// ─── Health Dot ───
function HealthDot({ ok, label }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{
        width: 7, height: 7, borderRadius: "50%",
        background: ok ? "#34d399" : "#f87171",
        boxShadow: ok ? "0 0 8px rgba(52,211,153,0.5)" : "0 0 8px rgba(248,113,113,0.5)",
      }} />
      <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)" }}>{label}</span>
    </div>
  );
}

// ─── Profile Card ───
function ProfileCard({ profile, jobCount, activeCount, onClick, onDelete }) {
  const colors = PROFILE_COLORS[profile.id] || PROFILE_COLORS.meeting;
  const icon = PROFILE_ICONS[profile.id] || Icons.mic;
  const [hovered, setHovered] = useState(false);

  const handleDelete = (e) => {
    e.stopPropagation();
    if (confirm(`Delete profile "${profile.name}"? This will remove the YAML and prompt files.`)) {
      onDelete?.(profile.id);
    }
  };

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered
          ? `linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03))`
          : `linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01))`,
        border: `1px solid ${hovered ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.06)'}`,
        borderRadius: 16, padding: "20px 18px",
        cursor: "pointer", textAlign: "left",
        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        transform: hovered ? "translateY(-2px)" : "none",
        boxShadow: hovered ? `0 8px 32px ${colors.glow}` : "none",
        backdropFilter: "blur(20px)",
        position: "relative", overflow: "hidden",
        width: "100%", minWidth: 220,
      }}
    >
      {/* Accent glow */}
      <div style={{
        position: "absolute", top: -20, right: -20, width: 80, height: 80,
        background: `radial-gradient(circle, ${colors.glow}, transparent 70%)`,
        opacity: hovered ? 1 : 0.5, transition: "opacity 0.3s",
      }} />

      {/* Delete button */}
      {hovered && onDelete && (
        <div
          onClick={handleDelete}
          style={{
            position: "absolute", top: 10, right: 10, zIndex: 5,
            width: 24, height: 24, borderRadius: 6,
            background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.2)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#f87171", fontSize: 12, cursor: "pointer",
            transition: "all 0.15s",
          }}
          onMouseEnter={e => { e.currentTarget.style.background = "rgba(248,113,113,0.2)"; }}
          onMouseLeave={e => { e.currentTarget.style.background = "rgba(248,113,113,0.1)"; }}
          title="Delete profile"
        >
          ✕
        </div>
      )}

      <div style={{ position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: colors.gradient,
            border: `1px solid ${colors.accent}33`,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: colors.accent,
          }}>
            {icon}
          </div>
          {activeCount > 0 && (
            <span style={{
              fontSize: 10, fontWeight: 700, color: "#60a5fa",
              background: "rgba(96,165,250,0.12)", padding: "2px 8px",
              borderRadius: 10, letterSpacing: 0.5,
            }}>
              {activeCount} ACTIVE
            </span>
          )}
        </div>

        <div style={{ fontSize: 16, fontWeight: 600, color: "#fff", marginBottom: 3, fontFamily: "'DM Sans', sans-serif" }}>
          {profile.name}
        </div>
        <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", marginBottom: 14, lineHeight: 1.4 }}>
          {profile.description}
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            {profile.stage_count} stage{profile.stage_count !== 1 ? "s" : ""} · {jobCount} job{jobCount !== 1 ? "s" : ""}
            {profile.syncthing_folder && (
              <span style={{ color: "rgba(52,211,153,0.4)" }}> · ↗ synced</span>
            )}
            {profile.priority && profile.priority !== 5 && (
              <span style={{ color: profile.priority <= 3 ? "rgba(251,191,36,0.5)" : "rgba(255,255,255,0.15)" }}>
                {" "}· P{profile.priority}
              </span>
            )}
            {profile.has_notifications && (
              <span style={{ color: "rgba(255,255,255,0.15)" }}> · 🔔</span>
            )}
          </span>
          <span style={{ color: colors.accent, display: "flex", opacity: hovered ? 1 : 0, transition: "opacity 0.2s" }}>
            {Icons.chevronRight}
          </span>
        </div>
      </div>
    </button>
  );
}

// ─── Job Row ───
function JobRow({ job, profiles, onClick, onDelete }) {
  const profile = profiles.find(p => p.id === job.profile_id);
  const colors = PROFILE_COLORS[job.profile_id] || PROFILE_COLORS.meeting;
  const [hovered, setHovered] = useState(false);
  const canDelete = ["QUEUED", "FAILED", "COMPLETE", "CANCELLED"].includes(job.status);

  const handleDelete = (e) => {
    e.stopPropagation();
    if (confirm(`Delete job "${getFilename(job.filename)}"?`)) {
      onDelete?.(job.id);
    }
  };

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto auto auto auto",
        gap: 16,
        alignItems: "center",
        padding: "12px 16px",
        background: hovered ? "rgba(255,255,255,0.03)" : "transparent",
        border: "none",
        borderBottom: "1px solid rgba(255,255,255,0.04)",
        cursor: "pointer",
        transition: "background 0.15s",
        width: "100%", textAlign: "left",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
        <div style={{
          width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
          background: colors.accent,
          boxShadow: `0 0 6px ${colors.accent}66`,
        }} />
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontSize: 13, fontWeight: 500, color: "#fff",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            fontFamily: "'DM Sans', sans-serif",
          }}>
            {getFilename(job.filename)}
          </div>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 2 }}>
            {profile?.name || job.profile_id}
            {job.current_stage && job.status === "PROCESSING" && (
              <span style={{ color: "rgba(96,165,250,0.8)" }}> · {job.current_stage}</span>
            )}
          </div>
          {(job.status === "PROCESSING" || job.stage_results?.length > 0) && (
            <PipelineTracker job={job} profile={profile} />
          )}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <StatusBadge status={job.status} />
        {job.priority && job.priority !== 5 && (
          <span style={{
            fontSize: 9, fontWeight: 600, padding: "1px 5px", borderRadius: 4,
            background: job.priority <= 3 ? "rgba(251,191,36,0.1)" : "rgba(255,255,255,0.03)",
            color: job.priority <= 3 ? "#fbbf24" : "rgba(255,255,255,0.2)",
            border: `1px solid ${job.priority <= 3 ? "rgba(251,191,36,0.15)" : "rgba(255,255,255,0.03)"}`,
          }}>
            P{job.priority}
          </span>
        )}
      </div>

      <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", minWidth: 50, textAlign: "right" }}>
        {job.cost_estimate > 0 ? `$${job.cost_estimate.toFixed(3)}` : "—"}
      </span>

      <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", minWidth: 60, textAlign: "right" }}>
        {timeAgo(job.created_at)}
      </span>

      {/* Delete button */}
      <div style={{ minWidth: 28, textAlign: "right" }}>
        {hovered && canDelete && onDelete ? (
          <span
            onClick={handleDelete}
            style={{
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              width: 24, height: 24, borderRadius: 6,
              background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.15)",
              color: "#f87171", fontSize: 11, cursor: "pointer",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(248,113,113,0.15)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "rgba(248,113,113,0.08)"; }}
            title="Delete job"
          >
            ✕
          </span>
        ) : null}
      </div>
    </button>
  );
}

// ─── Upload Panel ───
function UploadPanel({ profiles, onUpload }) {
  const [selectedProfile, setSelectedProfile] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState(null);
  const fileInputRef = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  const handleSubmit = async () => {
    if (!file || !selectedProfile) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("profile_id", selectedProfile);
      await apiFetch("/api/jobs", { method: "POST", body: fd });
      onUpload?.(selectedProfile, file.name);
      setFile(null);
      setSelectedProfile("");
    } catch (err) {
      console.error("Upload failed:", err);
      alert("Upload failed: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{
      background: "linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01))",
      border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: 16, padding: 24,
      backdropFilter: "blur(20px)",
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: "#fff", marginBottom: 16, fontFamily: "'DM Sans', sans-serif" }}>
        Upload Audio
      </div>

      {/* Profile selector */}
      <div style={{ marginBottom: 14 }}>
        <select
          value={selectedProfile}
          onChange={e => setSelectedProfile(e.target.value)}
          style={{
            width: "100%", padding: "10px 14px",
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 10, color: "#fff", fontSize: 13,
            outline: "none", cursor: "pointer",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          <option value="" style={{ background: "#1a1a2e" }}>Select profile...</option>
          {profiles.map(p => (
            <option key={p.id} value={p.id} style={{ background: "#1a1a2e" }}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? "rgba(245,158,11,0.5)" : "rgba(255,255,255,0.08)"}`,
          borderRadius: 12, padding: "28px 16px",
          textAlign: "center", cursor: "pointer",
          background: dragOver ? "rgba(245,158,11,0.05)" : "transparent",
          transition: "all 0.2s",
          marginBottom: 14,
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp3,.wav,.m4a,.flac,.ogg,.aac,.mp4,.mov,.webm"
          style={{ display: "none" }}
          onChange={e => { if (e.target.files[0]) setFile(e.target.files[0]); }}
        />
        <div style={{ color: "rgba(255,255,255,0.25)", marginBottom: 8, display: "flex", justifyContent: "center" }}>
          {Icons.upload}
        </div>
        {file ? (
          <div style={{ fontSize: 13, color: "#f59e0b", fontWeight: 500 }}>{file.name}</div>
        ) : (
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>
            Drop audio file here or click to browse
          </div>
        )}
      </div>

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!file || !selectedProfile || uploading}
        style={{
          width: "100%", padding: "11px 0",
          background: file && selectedProfile
            ? "linear-gradient(135deg, #f59e0b, #d97706)"
            : "rgba(255,255,255,0.05)",
          border: "none", borderRadius: 10,
          color: file && selectedProfile ? "#000" : "rgba(255,255,255,0.2)",
          fontSize: 13, fontWeight: 600, cursor: file && selectedProfile ? "pointer" : "not-allowed",
          transition: "all 0.2s",
          fontFamily: "'DM Sans', sans-serif",
        }}
      >
        {uploading ? "Uploading..." : "Upload & Transcribe"}
      </button>
    </div>
  );
}

// ─── Create Profile Modal ───
function CreateProfileModal({ onClose, onSave }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [profileId, setProfileId] = useState("");
  const [description, setDescription] = useState("");
  const [skipDiarization, setSkipDiarization] = useState(false);
  const [icon, setIcon] = useState("mic");
  const [syncthingFolder, setSyncthingFolder] = useState("");
  const [syncthingSubfolder, setSyncthingSubfolder] = useState("");
  const [syncthingFolders, setSyncthingFolders] = useState([]);
  const [syncthingLoading, setSyncthingLoading] = useState(false);
  const [syncthingConfigured, setSyncthingConfigured] = useState(false);

  // Priority and Notifications
  const [priority, setPriority] = useState(5);
  const [ntfyTopic, setNtfyTopic] = useState("");
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [pushoverUser, setPushoverUser] = useState("");
  const [pushoverToken, setPushoverToken] = useState("");

  // Fetch Syncthing folders on mount
  useEffect(() => {
    setSyncthingLoading(true);
    apiFetch("/api/syncthing/folders")
      .then(data => {
        setSyncthingConfigured(data?.configured || false);
        if (data?.folders) {
          setSyncthingFolders(data.folders);
        }
      })
      .catch(() => setSyncthingConfigured(false))
      .finally(() => setSyncthingLoading(false));
  }, []);

  const [stages, setStages] = useState([
    { name: "Clean & Format", model: "deepseek-chat", provider: "", temperature: 0.3, max_tokens: 4096, prompt: "" },
  ]);

  const iconOptions = [
    { id: "briefcase", label: "Briefcase", icon: Icons.briefcase },
    { id: "book", label: "Book", icon: Icons.book },
    { id: "users", label: "People", icon: Icons.users },
    { id: "mic", label: "Mic", icon: Icons.mic },
    { id: "zap", label: "Zap", icon: Icons.zap },
  ];

  const modelOptions = [
    "deepseek-chat",
    "deepseek-reasoner",
    "qwen-2.5-72b",
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
    "gpt-4o",
    "gpt-4o-mini",
    "gemini-2.0-flash",
    "llama-3.3-70b",
  ];

  const providerOptions = [
    { value: "", label: "Auto-detect" },
    { value: "deepseek", label: "DeepSeek" },
    { value: "openrouter", label: "OpenRouter" },
    { value: "openai", label: "OpenAI" },
    { value: "zai", label: "Z.ai" },
  ];

  const autoId = (n) => n.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

  const addStage = () => {
    setStages([...stages, { name: "", model: "deepseek-chat", provider: "", temperature: 0.3, max_tokens: 4096, prompt: "" }]);
  };

  const removeStage = (idx) => {
    if (stages.length > 1) setStages(stages.filter((_, i) => i !== idx));
  };

  const updateStage = (idx, field, value) => {
    const updated = [...stages];
    updated[idx] = { ...updated[idx], [field]: value };
    setStages(updated);
  };

  const handleSave = () => {
    const profile = {
      id: profileId || autoId(name),
      name,
      description,
      skip_diarization: skipDiarization,
      icon,
      priority: priority,
      syncthing_folder: syncthingFolder || null,
      syncthing_subfolder: syncthingSubfolder || null,
      notifications: (ntfyTopic || discordWebhook || pushoverUser) ? {
        ntfy_topic: ntfyTopic || undefined,
        discord_webhook: discordWebhook || undefined,
        pushover_user: pushoverUser || undefined,
        pushover_token: pushoverToken || undefined,
      } : undefined,
      stages: stages.map((s, i) => ({
        name: s.name,
        model: s.model,
        provider: s.provider || null,
        temperature: s.temperature,
        max_tokens: s.max_tokens,
        prompt_content: s.prompt,
        prompt_file: `${profileId || autoId(name)}/stage_${i + 1}_${autoId(s.name)}.md`,
        requires_previous: i > 0,
        save_intermediate: true,
        filename_suffix: `_${autoId(s.name)}`,
      })),
    };
    onSave(profile);
  };

  const canProceed = step === 1 ? name.trim().length > 0 : stages.every(s => s.name.trim().length > 0);

  const inputStyle = {
    width: "100%", padding: "10px 14px",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 10, color: "#fff", fontSize: 13,
    outline: "none", fontFamily: "'DM Sans', sans-serif",
    transition: "border-color 0.2s",
  };

  const labelStyle = {
    fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.45)",
    textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6, display: "block",
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)",
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        width: "90%", maxWidth: 580, maxHeight: "85vh",
        background: "linear-gradient(135deg, #141422, #0e0e1a)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 20, overflow: "hidden",
        display: "flex", flexDirection: "column",
      }}>
        {/* Header */}
        <div style={{
          padding: "20px 24px", borderBottom: "1px solid rgba(255,255,255,0.06)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: "#fff", margin: 0, fontFamily: "'DM Sans', sans-serif" }}>
              New Profile
            </h3>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", margin: "4px 0 0" }}>
              Step {step} of 2 — {step === 1 ? "Basic Info" : "Pipeline Stages"}
            </p>
          </div>
          <button onClick={onClose} style={{
            background: "rgba(255,255,255,0.05)", border: "none",
            width: 32, height: 32, borderRadius: 8, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "rgba(255,255,255,0.4)",
          }}>
            {Icons.x}
          </button>
        </div>

        {/* Step indicator */}
        <div style={{ display: "flex", gap: 4, padding: "0 24px", marginTop: 16 }}>
          {[1, 2].map(s => (
            <div key={s} style={{
              flex: 1, height: 3, borderRadius: 2,
              background: s <= step ? "linear-gradient(90deg, #f59e0b, #a78bfa)" : "rgba(255,255,255,0.06)",
              transition: "background 0.3s",
            }} />
          ))}
        </div>

        {/* Content */}
        <div style={{ padding: 24, overflowY: "auto", flex: 1 }}>
          {step === 1 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              {/* Name */}
              <div>
                <label style={labelStyle}>Profile Name</label>
                <input
                  value={name}
                  onChange={e => { setName(e.target.value); if (!profileId) setProfileId(""); }}
                  placeholder="e.g. Data Protection, Team Standup"
                  style={inputStyle}
                  onFocus={e => e.target.style.borderColor = "rgba(245,158,11,0.4)"}
                  onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.1)"}
                />
              </div>

              {/* ID */}
              <div>
                <label style={labelStyle}>Profile ID (auto-generated)</label>
                <input
                  value={profileId || autoId(name)}
                  onChange={e => setProfileId(e.target.value)}
                  style={{ ...inputStyle, color: "rgba(255,255,255,0.5)" }}
                />
                <div style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", marginTop: 4 }}>
                  Used for folder names and API references
                </div>
              </div>

              {/* Description */}
              <div>
                <label style={labelStyle}>Description</label>
                <input
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="What kind of audio does this profile process?"
                  style={inputStyle}
                />
              </div>

              {/* Icon */}
              <div>
                <label style={labelStyle}>Icon</label>
                <div style={{ display: "flex", gap: 8 }}>
                  {iconOptions.map(opt => (
                    <button
                      key={opt.id}
                      onClick={() => setIcon(opt.id)}
                      style={{
                        width: 44, height: 44, borderRadius: 10,
                        background: icon === opt.id ? "rgba(245,158,11,0.15)" : "rgba(255,255,255,0.04)",
                        border: icon === opt.id ? "1px solid rgba(245,158,11,0.4)" : "1px solid rgba(255,255,255,0.06)",
                        color: icon === opt.id ? "#f59e0b" : "rgba(255,255,255,0.3)",
                        cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                        transition: "all 0.2s",
                      }}
                      title={opt.label}
                    >
                      {opt.icon}
                    </button>
                  ))}
                </div>
              </div>

              {/* Skip diarization */}
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button
                  onClick={() => setSkipDiarization(!skipDiarization)}
                  style={{
                    width: 40, height: 22, borderRadius: 11, border: "none", cursor: "pointer",
                    background: skipDiarization ? "rgba(245,158,11,0.4)" : "rgba(255,255,255,0.1)",
                    position: "relative", transition: "background 0.2s",
                  }}
                >
                  <div style={{
                    width: 16, height: 16, borderRadius: "50%", background: "#fff",
                    position: "absolute", top: 3,
                    left: skipDiarization ? 21 : 3,
                    transition: "left 0.2s",
                  }} />
                </button>
                <span style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>Skip speaker diarization</span>
              </div>

              {/* Syncthing output routing */}
              <div>
                <label style={labelStyle}>Sync Output To</label>
                {syncthingLoading ? (
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", padding: "8px 0" }}>
                    Checking Syncthing...
                  </div>
                ) : !syncthingConfigured ? (
                  <div style={{
                    fontSize: 12, color: "rgba(255,255,255,0.25)", padding: "10px 14px",
                    background: "rgba(255,255,255,0.02)", borderRadius: 10,
                    border: "1px solid rgba(255,255,255,0.04)",
                  }}>
                    Syncthing not configured — outputs will stay on the server in <code style={{ color: "#a5b4fc" }}>outputs/docs/</code>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                      <div>
                        <select
                          value={syncthingFolder}
                          onChange={e => setSyncthingFolder(e.target.value)}
                          style={{ ...inputStyle, cursor: "pointer" }}
                        >
                          <option value="" style={{ background: "#1a1a2e" }}>No sync (local only)</option>
                          {syncthingFolders.map(f => (
                            <option key={f.id} value={f.id} style={{ background: "#1a1a2e" }}>
                              {f.label || f.id} {f.state === "syncing" ? " (syncing)" : ""}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <input
                          value={syncthingSubfolder}
                          onChange={e => setSyncthingSubfolder(e.target.value)}
                          placeholder="Subfolder (optional)"
                          style={inputStyle}
                          disabled={!syncthingFolder}
                        />
                      </div>
                    </div>
                    {syncthingFolder && (
                      <div style={{
                        fontSize: 11, color: "rgba(255,255,255,0.3)",
                        display: "flex", alignItems: "center", gap: 6,
                      }}>
                        <span style={{ color: "#34d399" }}>↗</span>
                        Output syncs to: <code style={{ color: "#a5b4fc" }}>
                          {syncthingFolders.find(f => f.id === syncthingFolder)?.label || syncthingFolder}
                          {syncthingSubfolder ? `/${syncthingSubfolder}` : ""}
                        </code>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Priority */}
              <div>
                <label style={labelStyle}>Queue Priority</label>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <input
                    type="range" min="1" max="10" value={priority}
                    onChange={e => setPriority(parseInt(e.target.value))}
                    style={{ flex: 1, accentColor: "#60a5fa" }}
                  />
                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", minWidth: 60 }}>
                    {priority <= 3 ? "High" : priority <= 7 ? "Normal" : "Low"} ({priority})
                  </span>
                </div>
              </div>

              {/* Notifications */}
              <div>
                <label style={labelStyle}>Notifications (optional)</label>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <input
                    value={ntfyTopic}
                    onChange={e => setNtfyTopic(e.target.value)}
                    placeholder="Ntfy topic (e.g. transcription-alerts)"
                    style={inputStyle}
                  />
                  <input
                    value={discordWebhook}
                    onChange={e => setDiscordWebhook(e.target.value)}
                    placeholder="Discord webhook URL"
                    style={inputStyle}
                  />
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <input
                      value={pushoverUser}
                      onChange={e => setPushoverUser(e.target.value)}
                      placeholder="Pushover user key"
                      style={inputStyle}
                    />
                    <input
                      value={pushoverToken}
                      onChange={e => setPushoverToken(e.target.value)}
                      placeholder="Pushover app token"
                      style={inputStyle}
                    />
                  </div>
                </div>
              </div>

              {/* Output path preview */}
              {name && (
                <div style={{
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.04)",
                  borderRadius: 8, padding: "10px 14px",
                }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
                    Pipeline Flow
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "rgba(255,255,255,0.4)", flexWrap: "wrap" }}>
                    <code style={{ color: "#fbbf24", background: "rgba(251,191,36,0.08)", padding: "2px 6px", borderRadius: 4 }}>
                      uploads/{profileId || autoId(name)}/
                    </code>
                    <span>→</span>
                    <span style={{ color: "rgba(255,255,255,0.5)" }}>{stages.length} stage pipeline</span>
                    <span>→</span>
                    <code style={{ color: "#34d399", background: "rgba(52,211,153,0.08)", padding: "2px 6px", borderRadius: 4 }}>
                      {syncthingFolder
                        ? `${syncthingFolders.find(f => f.id === syncthingFolder)?.label || syncthingFolder}${syncthingSubfolder ? `/${syncthingSubfolder}` : ""}`
                        : `outputs/docs/${syncthingSubfolder || profileId || autoId(name)}/`
                      }
                    </code>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {stages.map((stage, idx) => (
                <div key={idx} style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.06)",
                  borderRadius: 14, padding: 18,
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.5)" }}>
                      Stage {idx + 1}
                    </span>
                    {stages.length > 1 && (
                      <button
                        onClick={() => removeStage(idx)}
                        style={{
                          background: "rgba(248,113,113,0.1)", border: "none",
                          padding: "4px 10px", borderRadius: 6, cursor: "pointer",
                          fontSize: 11, color: "#f87171", fontWeight: 500,
                        }}
                      >
                        Remove
                      </button>
                    )}
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {/* Stage name */}
                    <div>
                      <label style={labelStyle}>Stage Name</label>
                      <input
                        value={stage.name}
                        onChange={e => updateStage(idx, "name", e.target.value)}
                        placeholder="e.g. Clean & Structure, Analysis, Cheat Sheet"
                        style={inputStyle}
                      />
                    </div>

                    {/* Model + Provider + Temp row */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 80px", gap: 10 }}>
                      <div>
                        <label style={labelStyle}>Model</label>
                        <select
                          value={stage.model}
                          onChange={e => updateStage(idx, "model", e.target.value)}
                          style={{ ...inputStyle, cursor: "pointer" }}
                        >
                          {modelOptions.map(m => (
                            <option key={m} value={m} style={{ background: "#1a1a2e" }}>{m}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label style={labelStyle}>Provider</label>
                        <select
                          value={stage.provider || ""}
                          onChange={e => updateStage(idx, "provider", e.target.value)}
                          style={{ ...inputStyle, cursor: "pointer", fontSize: 11 }}
                        >
                          {providerOptions.map(p => (
                            <option key={p.value} value={p.value} style={{ background: "#1a1a2e" }}>{p.label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label style={labelStyle}>Temp</label>
                        <input
                          type="number"
                          min="0" max="2" step="0.1"
                          value={stage.temperature}
                          onChange={e => updateStage(idx, "temperature", parseFloat(e.target.value) || 0)}
                          style={inputStyle}
                        />
                      </div>
                    </div>

                    {/* Prompt */}
                    <div>
                      <label style={labelStyle}>Prompt</label>
                      <textarea
                        value={stage.prompt}
                        onChange={e => updateStage(idx, "prompt", e.target.value)}
                        placeholder={"Write your system prompt here...\n\nDescribe how the AI should process the transcript at this stage."}
                        rows={5}
                        style={{
                          ...inputStyle,
                          resize: "vertical", minHeight: 100,
                          lineHeight: 1.5,
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}

              {/* Add stage button */}
              <button
                onClick={addStage}
                style={{
                  padding: "12px 0", borderRadius: 10,
                  background: "rgba(255,255,255,0.03)",
                  border: "1px dashed rgba(255,255,255,0.1)",
                  color: "rgba(255,255,255,0.35)", fontSize: 13,
                  cursor: "pointer", transition: "all 0.2s",
                  fontFamily: "'DM Sans', sans-serif",
                }}
                onMouseEnter={e => { e.target.style.borderColor = "rgba(245,158,11,0.3)"; e.target.style.color = "#f59e0b"; }}
                onMouseLeave={e => { e.target.style.borderColor = "rgba(255,255,255,0.1)"; e.target.style.color = "rgba(255,255,255,0.35)"; }}
              >
                + Add Stage
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "16px 24px", borderTop: "1px solid rgba(255,255,255,0.06)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <button
            onClick={() => step === 1 ? onClose() : setStep(1)}
            style={{
              padding: "10px 20px", borderRadius: 10,
              background: "rgba(255,255,255,0.05)", border: "none",
              color: "rgba(255,255,255,0.5)", fontSize: 13, cursor: "pointer",
              fontFamily: "'DM Sans', sans-serif",
            }}
          >
            {step === 1 ? "Cancel" : "Back"}
          </button>
          <button
            onClick={() => step === 1 ? setStep(2) : handleSave()}
            disabled={!canProceed}
            style={{
              padding: "10px 24px", borderRadius: 10,
              background: canProceed ? "linear-gradient(135deg, #f59e0b, #d97706)" : "rgba(255,255,255,0.05)",
              border: "none",
              color: canProceed ? "#000" : "rgba(255,255,255,0.2)",
              fontSize: 13, fontWeight: 600, cursor: canProceed ? "pointer" : "not-allowed",
              fontFamily: "'DM Sans', sans-serif",
              transition: "all 0.2s",
            }}
          >
            {step === 1 ? "Next →" : "Create Profile"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Dry Run Panel ───
function DryRunPanel({ profileId, stageIndex, stageName, onClose }) {
  const [transcript, setTranscript] = useState("");
  const [jobId, setJobId] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setAvailableJobs] = useState([]);

  useEffect(() => {
    apiFetch("/api/jobs?status=COMPLETE&limit=10")
      .then(data => setAvailableJobs(data?.jobs || []))
      .catch(() => {});
  }, []);

  const runTest = async () => {
    setLoading(true); setError(""); setResult(null);
    try {
      const body = { stage_index: stageIndex, max_chars: 3000 };
      if (jobId) body.job_id = jobId;
      else body.transcript = transcript;
      
      const data = await apiFetch(`/api/profiles/${profileId}/dry-run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      background: "rgba(0,0,0,0.5)", position: "fixed", inset: 0, zIndex: 1100,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div style={{
        background: "#12121f", borderRadius: 16, padding: 24, maxWidth: 700, width: "90%",
        maxHeight: "80vh", overflow: "auto", border: "1px solid rgba(255,255,255,0.08)",
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h3 style={{ color: "rgba(255,255,255,0.8)", margin: 0, fontSize: 16 }}>
            Dry Run: {stageName}
          </h3>
          <button onClick={onClose} style={{
            background: "none", border: "none", color: "rgba(255,255,255,0.3)", fontSize: 18, cursor: "pointer"
          }}>✕</button>
        </div>

        {/* Input source */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", display: "block", marginBottom: 4 }}>
            From a previous job:
          </label>
          <select
            value={jobId}
            onChange={e => { setJobId(e.target.value); if (e.target.value) setTranscript(""); }}
            style={{
              width: "100%", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 8, color: "rgba(255,255,255,0.6)", fontSize: 12, padding: "6px 10px", outline: "none",
            }}
          >
            <option value="" style={{ background: "#1a1a2e" }}>— Or paste text below —</option>
            {jobs.map(j => (
              <option key={j.id} value={j.id} style={{ background: "#1a1a2e" }}>
                {j.filename?.split("/").pop()} ({j.profile_id})
              </option>
            ))}
          </select>
        </div>

        {!jobId && (
          <div style={{ marginBottom: 12 }}>
            <textarea
              value={transcript}
              onChange={e => setTranscript(e.target.value)}
              placeholder="Paste sample transcript here..."
              rows={6}
              style={{
                width: "100%", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 8, color: "rgba(255,255,255,0.6)", fontSize: 12, padding: 10, outline: "none",
                fontFamily: "'JetBrains Mono', monospace", resize: "vertical",
              }}
            />
          </div>
        )}

        <button
          onClick={runTest}
          disabled={loading || (!transcript && !jobId)}
          style={{
            background: loading ? "rgba(255,255,255,0.05)" : "rgba(96,165,250,0.15)",
            border: "1px solid rgba(96,165,250,0.3)", borderRadius: 8,
            padding: "8px 20px", color: "#60a5fa", fontSize: 13, fontWeight: 600,
            cursor: loading ? "wait" : "pointer", marginBottom: 16,
          }}
        >
          {loading ? "Running..." : "Test Stage"}
        </button>

        {error && (
          <div style={{ color: "#f87171", fontSize: 12, marginBottom: 12, padding: 10, background: "rgba(248,113,113,0.05)", borderRadius: 8 }}>
            {error}
          </div>
        )}

        {result && (
          <div>
            <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
              <span>Model: <strong style={{ color: "#a5b4fc" }}>{result.model}</strong></span>
              <span>Provider: {result.provider}</span>
              <span>Tokens: {((result.input_tokens + result.output_tokens) / 1000).toFixed(1)}k</span>
              <span>Cost: <strong style={{ color: "#34d399" }}>${result.cost.toFixed(4)}</strong></span>
            </div>
            <pre style={{
              background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 8, padding: 12, fontSize: 11, color: "rgba(255,255,255,0.6)",
              whiteSpace: "pre-wrap", maxHeight: 300, overflow: "auto",
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              {result.output}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Profile Detail View ───
function ProfileDetail({ profile, jobs, onBack }) {
  const colors = PROFILE_COLORS[profile.id] || PROFILE_COLORS.meeting;
  const icon = PROFILE_ICONS[profile.id] || Icons.mic;
  const profileJobs = jobs.filter(j => j.profile_id === profile.id);
  const completedCount = profileJobs.filter(j => j.status === "COMPLETE").length;
  const totalCost = profileJobs.reduce((sum, j) => sum + (j.cost_estimate || 0), 0);

  const [editingPrompt, setEditingPrompt] = useState(null);
  const [promptSaving, setPromptSaving] = useState(false);
  const [syncDevices, setSyncDevices] = useState([]);
  const [dryRunStage, setDryRunStage] = useState(null);

  useEffect(() => {
    if (profile.syncthing_folder) {
      apiFetch(`/api/syncthing/folder/${profile.syncthing_folder}/devices`)
        .then(data => {
          if (data?.devices) setSyncDevices(data.devices);
        })
        .catch(() => {});
    }
  }, [profile.syncthing_folder]);

  const loadPrompt = async (stageIndex) => {
    try {
      const data = await apiFetch(`/api/profiles/${profile.id}/prompts/${stageIndex}`);
      if (data) setEditingPrompt({ stageIndex, content: data.prompt, filename: data.filename });
    } catch (err) {
      console.error("Failed to load prompt:", err);
    }
  };

  const savePrompt = async () => {
    if (!editingPrompt) return;
    setPromptSaving(true);
    try {
      await apiFetch(`/api/profiles/${profile.id}/prompts/${editingPrompt.stageIndex}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: editingPrompt.content }),
      });
      setEditingPrompt(null);
    } catch (err) {
      console.error("Failed to save prompt:", err);
    } finally {
      setPromptSaving(false);
    }
  };

  return (
    <div>
      {/* Header */}
      <button
        onClick={onBack}
        style={{
          display: "flex", alignItems: "center", gap: 6,
          background: "none", border: "none", color: "rgba(255,255,255,0.4)",
          cursor: "pointer", fontSize: 13, marginBottom: 20, padding: 0,
          fontFamily: "'DM Sans', sans-serif",
        }}
      >
        {Icons.arrowLeft}
        Back to Dashboard
      </button>

      <div style={{
        display: "flex", alignItems: "center", gap: 16, marginBottom: 28,
      }}>
        <div style={{
          width: 52, height: 52, borderRadius: 14,
          background: colors.gradient,
          border: `1px solid ${colors.accent}33`,
          display: "flex", alignItems: "center", justifyContent: "center",
          color: colors.accent, fontSize: 24,
        }}>
          {icon}
        </div>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: "#fff", margin: 0, fontFamily: "'DM Sans', sans-serif" }}>
            {profile.name}
          </h2>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", margin: "4px 0 0" }}>
            {profile.description}
          </p>
          {/* Pipeline flow summary */}
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginTop: 10,
            fontSize: 12, color: "rgba(255,255,255,0.4)",
            background: "rgba(255,255,255,0.03)", padding: "8px 12px", borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.04)", flexWrap: "wrap",
          }}>
            <code style={{ color: "#fbbf24", fontSize: 11 }}>
              uploads/{profile.id}/
            </code>
            <span style={{ color: "rgba(255,255,255,0.15)" }}>→</span>
            <span>{profile.stages?.length || 0} stages</span>
            <span style={{ color: "rgba(255,255,255,0.15)" }}>→</span>
            {profile.syncthing_folder ? (
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <code style={{ color: "#34d399", fontSize: 11 }}>
                  {profile.syncthing_folder}
                  {profile.syncthing_subfolder ? `/${profile.syncthing_subfolder}` : ""}
                </code>
                {syncDevices.length > 0 && (
                  <span style={{ color: "rgba(255,255,255,0.25)", fontSize: 11 }}>
                    → {syncDevices.map(d => d.name).join(", ")}
                  </span>
                )}
              </span>
            ) : (
              <code style={{ color: "#a5b4fc", fontSize: 11 }}>
                outputs/docs/{profile.syncthing_subfolder || profile.id}/
              </code>
            )}
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 24 }}>
        {[
          { label: "Total Jobs", value: profileJobs.length },
          { label: "Completed", value: completedCount },
          { label: "Total Cost", value: `$${totalCost.toFixed(3)}` },
        ].map((stat, i) => (
          <div key={i} style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 12, padding: "14px 16px", textAlign: "center",
          }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#fff", fontFamily: "'DM Sans', sans-serif" }}>
              {stat.value}
            </div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 2 }}>{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Pipeline stages */}
      <div style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 14, padding: 18, marginBottom: 24,
      }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.5)", marginBottom: 14, textTransform: "uppercase", letterSpacing: 1 }}>
          Pipeline Stages
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 0, flexWrap: "wrap" }}>
          {profile.stages?.map((stage, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{
                  padding: "8px 14px", borderRadius: 8,
                  background: `${colors.accent}15`,
                  border: `1px solid ${colors.accent}30`,
                  fontSize: 12, fontWeight: 500, color: colors.accent,
                }}>
                  {stage}
                </div>
                <button
                  onClick={() => loadPrompt(i)}
                  style={{
                    background: "rgba(255,255,255,0.05)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 6, padding: "4px 8px",
                    color: "rgba(255,255,255,0.4)", fontSize: 10,
                    cursor: "pointer", fontFamily: "'DM Sans', sans-serif",
                  }}
                >
                  Edit Prompt
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setDryRunStage({ index: i, name: stage }); }}
                  style={{
                    background: "rgba(96,165,250,0.08)", border: "1px solid rgba(96,165,250,0.2)",
                    borderRadius: 6, padding: "2px 8px", fontSize: 10, color: "#60a5fa",
                    cursor: "pointer", fontWeight: 500,
                  }}
                >
                  Test
                </button>
              </div>
              {i < (profile.stages?.length || 0) - 1 && (
                <div style={{ padding: "0 6px", color: "rgba(255,255,255,0.15)" }}>→</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Job history */}
      <div style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 14, overflow: "hidden",
      }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.5)", textTransform: "uppercase", letterSpacing: 1 }}>
            Job History
          </span>
        </div>
        {profileJobs.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "rgba(255,255,255,0.2)", fontSize: 13 }}>
            No jobs yet
          </div>
        ) : (
          profileJobs.map(job => (
            <div key={job.id} style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto",
              gap: 16, alignItems: "center",
              padding: "12px 18px",
              borderBottom: "1px solid rgba(255,255,255,0.03)",
            }}>
              <div>
                <div style={{ fontSize: 13, color: "#fff", fontWeight: 500, fontFamily: "'DM Sans', sans-serif" }}>
                  {getFilename(job.filename)}
                </div>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", marginTop: 2 }}>
                  {new Date(job.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                  {job.completed_at && ` · ${formatDuration(job.created_at, job.completed_at)}`}
                </div>
              </div>
              <StatusBadge status={job.status} />
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
                ${job.cost_estimate?.toFixed(3) || "0.000"}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Prompt Editor Modal */}
      {editingPrompt && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
          backdropFilter: "blur(4px)",
        }} onClick={() => setEditingPrompt(null)}>
          <div style={{
            background: "#1a1a2e", borderRadius: 16,
            border: "1px solid rgba(255,255,255,0.08)",
            padding: 24, width: "90%", maxWidth: 720, maxHeight: "85vh",
            display: "flex", flexDirection: "column",
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, color: "#fff", fontSize: 16, fontWeight: 600, fontFamily: "'DM Sans', sans-serif" }}>
                  Edit Prompt — Stage {editingPrompt.stageIndex + 1}
                </h3>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", marginTop: 4 }}>
                  {editingPrompt.filename}
                </div>
              </div>
              <button
                onClick={() => setEditingPrompt(null)}
                style={{
                  background: "none", border: "none", color: "rgba(255,255,255,0.4)",
                  fontSize: 20, cursor: "pointer", padding: "4px 8px",
                }}
              >✕</button>
            </div>
            <textarea
              value={editingPrompt.content}
              onChange={e => setEditingPrompt({ ...editingPrompt, content: e.target.value })}
              style={{
                flex: 1, minHeight: 400, resize: "vertical",
                background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 10, padding: 14, color: "#e0e0e0",
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
                fontSize: 13, lineHeight: 1.6,
                outline: "none",
              }}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 14 }}>
              <button
                onClick={() => setEditingPrompt(null)}
                style={{
                  padding: "8px 18px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)",
                  background: "transparent", color: "rgba(255,255,255,0.5)", cursor: "pointer",
                  fontFamily: "'DM Sans', sans-serif", fontSize: 13,
                }}
              >Cancel</button>
              <button
                onClick={savePrompt}
                disabled={promptSaving}
                style={{
                  padding: "8px 18px", borderRadius: 8, border: "none",
                  background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                  color: "#fff", cursor: "pointer", fontWeight: 600,
                  fontFamily: "'DM Sans', sans-serif", fontSize: 13,
                  opacity: promptSaving ? 0.6 : 1,
                }}
              >{promptSaving ? "Saving..." : "Save"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Dry Run Panel */}
      {dryRunStage && (
        <DryRunPanel
          profileId={profile.id}
          stageIndex={dryRunStage.index}
          stageName={dryRunStage.name}
          onClose={() => setDryRunStage(null)}
        />
      )}
    </div>
  );
}

// ─── Main App ───
export default function ControlHub() {
  const [profiles, setProfiles] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [health, setHealth] = useState(null);
  const [ready, setReady] = useState(null);
  const [activeView, setActiveView] = useState("dashboard");
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Browser back button support
  useEffect(() => {
    const handlePopState = () => {
      setActiveView("dashboard");
      setSelectedProfile(null);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    const load = async () => {
      console.log("Frontend: Starting to load data from API...");
      console.log("Frontend: API_BASE =", API_BASE);
      try {
        console.log("Frontend: Making API calls...");
        const [p, j, h, r] = await Promise.all([
          apiFetch("/api/profiles").then(data => {
            console.log("Frontend: Profiles API response:", data?.length, "profiles");
            return data;
          }).catch(err => {
            console.error("Frontend: Profiles API error:", err);
            throw err;
          }),
          apiFetch("/api/jobs?limit=50").then(data => {
            console.log("Frontend: Jobs API response:", data?.jobs?.length, "jobs");
            return data;
          }).catch(err => {
            console.error("Frontend: Jobs API error:", err);
            throw err;
          }),
          apiFetch("/health").then(data => {
            console.log("Frontend: Health API response:", data);
            return data;
          }).catch(err => {
            console.error("Frontend: Health API error:", err);
            throw err;
          }),
          apiFetch("/ready").then(data => {
            console.log("Frontend: Ready API response:", data);
            return data;
          }).catch(err => {
            console.error("Frontend: Ready API error:", err);
            throw err;
          }),
        ]);
        console.log("Frontend: All API calls successful");
        if (p) {
          console.log("Frontend: Setting profiles:", p.length);
          setProfiles(p);
        }
        if (j) {
          console.log("Frontend: Setting jobs:", j.jobs?.length || 0);
          setJobs(j.jobs || []);
        }
        if (h) {
          console.log("Frontend: Setting health:", h);
          setHealth(h);
        }
        if (r) {
          console.log("Frontend: Setting ready:", r);
          setReady(r);
        }
      } catch (err) {
        console.error("Frontend: Failed to load data:", err);
        console.error("Frontend: Error stack:", err.stack);
      }
    };
    load();

    // WebSocket for real-time updates with polling fallback
    let ws = null;
    let fallbackInterval = null;
    let reconnectTimeout = null;

    const connectWs = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsKeyParam = API_KEY ? `?key=${encodeURIComponent(API_KEY)}` : '';
      ws = new WebSocket(`${protocol}//${window.location.host}/ws${wsKeyParam}`);

      ws.onmessage = (event) => {
        try {
          const { event: evt, data } = JSON.parse(event.data);
          if (evt === "job_update") {
            setJobs(prev => prev.map(j => {
              if (j.id !== data.job_id) return j;
              const updated = { ...j, ...data };
              // Merge stage detail into stage_results array
              if (data.stage_detail) {
                const sd = data.stage_detail;
                const existing = (j.stage_results || []).slice();
                const idx = existing.findIndex(sr => sr.stage_id === sd.stage_id);
                const stageEntry = {
                  stage_id: sd.stage_id,
                  status: sd.stage_status,
                  model_used: sd.model_used,
                };
                if (idx >= 0) {
                  existing[idx] = { ...existing[idx], ...stageEntry };
                } else {
                  existing.push(stageEntry);
                }
                updated.stage_results = existing;
              }
              return updated;
            }));
          }
        } catch (e) {
          console.warn("WS parse error:", e);
        }
      };

      ws.onclose = () => {
        // Fallback to polling if WS drops
        if (!fallbackInterval) {
          fallbackInterval = setInterval(load, 10000);
        }
        // Reconnect after 5s
        reconnectTimeout = setTimeout(connectWs, 5000);
      };

      ws.onopen = () => {
        // Kill polling if WS connects
        if (fallbackInterval) {
          clearInterval(fallbackInterval);
          fallbackInterval = null;
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connectWs();

    return () => {
      ws?.close();
      if (fallbackInterval) clearInterval(fallbackInterval);
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const jobCountByProfile = (id) => jobs.filter(j => j.profile_id === id).length;
  const activeCountByProfile = (id) => jobs.filter(j => j.profile_id === id && ["PROCESSING", "QUEUED"].includes(j.status)).length;

  const handleProfileClick = (profile) => {
    window.history.pushState({ view: "profile" }, "");
    setSelectedProfile(profile);
    setActiveView("profile");
  };

  const handleCreateProfile = async (profileData) => {
    try {
      await apiFetch("/api/profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profileData),
      });
      // Reload profiles from API
      const p = await apiFetch("/api/profiles");
      if (p) setProfiles(p);
      setShowCreateModal(false);
    } catch (err) {
      // Fallback: add to local state if API not ready yet
      console.error("Failed to create profile via API:", err);
      const newProfile = {
        id: profileData.id,
        name: profileData.name,
        description: profileData.description,
        stage_count: profileData.stages.length,
        stages: profileData.stages.map(s => s.name),
      };
      setProfiles([...profiles, newProfile]);
      setShowCreateModal(false);
    }
  };

  const handleDeleteProfile = async (profileId) => {
    try {
      await apiFetch(`/api/profiles/${profileId}`, { method: "DELETE" });
      setProfiles(profiles.filter(p => p.id !== profileId));
    } catch (err) {
      console.error("Failed to delete profile:", err);
      alert("Failed to delete profile: " + err.message);
    }
  };

  const handleDeleteJob = async (jobId) => {
    try {
      await apiFetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      setJobs(jobs.filter(j => j.id !== jobId));
    } catch (err) {
      console.error("Failed to delete job:", err);
      alert("Failed to delete job: " + err.message);
    }
  };

  const recentJobs = [...jobs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 10);
  const activeJobCount = jobs.filter(j => ["PROCESSING", "QUEUED"].includes(j.status)).length;
  const todayJobs = jobs.filter(j => {
    const d = new Date(j.created_at);
    const today = new Date();
    return d.toDateString() === today.toDateString();
  }).length;

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0a0a14",
      color: "#fff",
      fontFamily: "'DM Sans', -apple-system, sans-serif",
    }}>
      {/* Background effects */}
      <div style={{
        position: "fixed", top: 0, left: 0, right: 0, bottom: 0, pointerEvents: "none", zIndex: 0,
      }}>
        <div style={{
          position: "absolute", top: "-20%", left: "-10%", width: "50%", height: "50%",
          background: "radial-gradient(ellipse, rgba(245,158,11,0.06), transparent 70%)",
        }} />
        <div style={{
          position: "absolute", bottom: "-10%", right: "-10%", width: "40%", height: "40%",
          background: "radial-gradient(ellipse, rgba(167,139,250,0.05), transparent 70%)",
        }} />
        {/* Noise texture */}
        <div style={{
          position: "absolute", inset: 0, opacity: 0.015,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, maxWidth: 1100, margin: "0 auto", padding: "0 24px" }}>
        {/* ─── Top Bar ─── */}
        <header style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "20px 0", borderBottom: "1px solid rgba(255,255,255,0.05)",
          marginBottom: 32,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: "linear-gradient(135deg, #f59e0b, #a78bfa)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14,
            }}>
              ⚡
            </div>
            <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.3, fontFamily: "'DM Sans', sans-serif" }}>
              Control Hub
            </span>
            <span style={{
              fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)",
              background: "rgba(255,255,255,0.05)", padding: "2px 8px",
              borderRadius: 6, letterSpacing: 0.5,
            }}>
              v2.0
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <HealthDot ok={ready?.checks?.groq} label="Groq" />
            <HealthDot ok={ready?.checks?.deepseek} label="DeepSeek" />
            <HealthDot ok={health?.checks?.database} label="DB" />
            <div style={{ width: 1, height: 16, background: "rgba(255,255,255,0.08)", margin: "0 4px" }} />
            <div style={{
              fontSize: 11, color: health?.status === "healthy" ? "#34d399" : health === null ? "#64748b" : "#f87171",
              fontWeight: 600,
            }}>
              {health === null ? "Connecting…" : health.status === "healthy" ? "All Systems Operational" : "Degraded"}
            </div>
          </div>
        </header>

        {/* ─── Content ─── */}
        {activeView === "profile" && selectedProfile ? (
          <ProfileDetail
            profile={selectedProfile}
            jobs={jobs}
            onBack={() => { setActiveView("dashboard"); setSelectedProfile(null); }}
          />
        ) : (
          <>
            {/* Stats bar */}
            <div style={{ display: "flex", gap: 24, marginBottom: 28 }}>
              {[
                { label: "Active Jobs", value: activeJobCount, color: "#60a5fa" },
                { label: "Today", value: todayJobs, color: "#f59e0b" },
                { label: "Total Jobs", value: jobs.length, color: "#34d399" },
                { label: "Total Cost", value: `$${jobs.reduce((sum, j) => sum + (j.cost_estimate || 0), 0).toFixed(3)}`, color: "#a78bfa" },
              ].map((stat, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 22, fontWeight: 700, color: stat.color, fontFamily: "'DM Sans', sans-serif" }}>
                    {stat.value}
                  </span>
                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.35)" }}>{stat.label}</span>
                </div>
              ))}
            </div>

            {/* ─── Profiles Row ─── */}
            <div style={{ marginBottom: 24 }}>
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                marginBottom: 12, padding: "0 2px",
              }}>
                <div style={{
                  fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.35)",
                  textTransform: "uppercase", letterSpacing: 1,
                }}>
                  Profiles
                </div>
                <button
                  onClick={() => setShowCreateModal(true)}
                  style={{
                    background: "rgba(245,158,11,0.08)",
                    border: "1px solid rgba(245,158,11,0.2)",
                    borderRadius: 8, padding: "6px 14px",
                    cursor: "pointer",
                    color: "#f59e0b",
                    fontSize: 12, fontWeight: 600,
                    fontFamily: "'DM Sans', sans-serif",
                    transition: "all 0.2s",
                    display: "flex", alignItems: "center", gap: 4,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = "rgba(245,158,11,0.15)"; }}
                  onMouseLeave={e => { e.currentTarget.style.background = "rgba(245,158,11,0.08)"; }}
                >
                  + New Profile
                </button>
              </div>
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                gap: 12,
              }}>
                {profiles.map(p => (
                  <ProfileCard
                    key={p.id}
                    profile={p}
                    jobCount={jobCountByProfile(p.id)}
                    activeCount={activeCountByProfile(p.id)}
                    onClick={() => handleProfileClick(p)}
                    onDelete={["meeting", "supervision", "client", "lecture", "braindump"].includes(p.id) ? null : handleDeleteProfile}
                  />
                ))}
              </div>
            </div>

            {/* ─── Upload + Recent Activity ─── */}
            <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 24, alignItems: "start" }}>
              {/* Left: Upload */}
              <div>
                <UploadPanel profiles={profiles} />
              </div>

              {/* Right: Recent Activity */}
              <div style={{
                background: "linear-gradient(135deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01))",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 16,
                backdropFilter: "blur(20px)",
                overflow: "hidden",
              }}>
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "16px 20px",
                  borderBottom: "1px solid rgba(255,255,255,0.05)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: "rgba(255,255,255,0.4)", display: "flex" }}>{Icons.activity}</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.7)", fontFamily: "'DM Sans', sans-serif" }}>
                      Recent Activity
                    </span>
                  </div>
                  <span style={{ fontSize: 11, color: "rgba(255,255,255,0.2)" }}>
                    {recentJobs.length} jobs
                  </span>
                </div>

                {/* Column headers */}
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "1fr auto auto auto auto",
                  gap: 16, padding: "8px 16px",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                }}>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: 0.5 }}>File</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: 0.5 }}>Status</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: 0.5, textAlign: "right" }}>Cost</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.2)", textTransform: "uppercase", letterSpacing: 0.5, textAlign: "right" }}>When</span>
                  <span style={{ minWidth: 28 }} />
                </div>

                {recentJobs.map(job => (
                  <JobRow
                    key={job.id}
                    job={job}
                    profiles={profiles}
                    onClick={() => {
                      const p = profiles.find(pr => pr.id === job.profile_id);
                      if (p) handleProfileClick(p);
                    }}
                    onDelete={handleDeleteJob}
                  />
                ))}

                {recentJobs.length === 0 && (
                  <div style={{ padding: 48, textAlign: "center", color: "rgba(255,255,255,0.15)", fontSize: 13 }}>
                    No jobs yet — upload an audio file to get started
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        {/* Create Profile Modal */}
        {showCreateModal && (
          <CreateProfileModal
            onClose={() => setShowCreateModal(false)}
            onSave={handleCreateProfile}
          />
        )}

        {/* Footer */}
        <footer style={{
          padding: "32px 0 24px",
          textAlign: "center",
          fontSize: 11,
          color: "rgba(255,255,255,0.15)",
        }}>
          Transcription Pipeline · transcribe.delboysden.uk
        </footer>
      </div>

      {/* Log Console */}
      <LogConsole />

      {/* Global styles */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0a0a14; }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .spin { animation: spin 1.5s linear infinite; }

        select option { background: #1a1a2e; color: #fff; }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
      `}</style>
    </div>
  );
}
